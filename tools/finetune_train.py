#!/usr/bin/env python3
"""
tools/finetune_train.py — Train a LoRA adapter on Echo's conversation history.
Uses Unsloth for fast fine-tuning on the RTX 3060 (12GB VRAM).
Reads review-gated or verified reasoning datasets in ShareGPT conversations format.
"""
import json
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
# Dataset priority (intelligence > reviewed voice):
#   1. verified REASONING traces, once the corpus is real (>=50) — trains task-solving
#      (intelligence), not just persona. Built by tools/build_reasoning_dataset.py.
#   2. review-gated conversation examples exported by
#      core.conversation_learning_candidates. Legacy raw chat is retained for audit
#      but is no longer a training fallback.
def _pick_dataset():
    reasoning = BASE / "memory/reasoning_dataset.jsonl"
    if reasoning.exists():
        n = sum(1 for ln in reasoning.read_text().splitlines() if ln.strip())
        if n >= 50:
            return reasoning
    reviewed = BASE / "memory/finetune_dataset_reviewed.jsonl"
    return reviewed

DATASET = _pick_dataset()
ADAPTERS_DIR = BASE / "memory/lora_adapters"
LOG = BASE / "logs/finetune_train.log"

logging.basicConfig(filename=str(LOG), level=logging.INFO, format="%(asctime)s %(message)s")

def log(msg):
    print(msg, flush=True)
    logging.info(msg)

BASE_MODEL = "unsloth/DeepSeek-R1-Distill-Qwen-1.5B-bnb-4bit"
LORA_RANK = 8
EPOCHS = 3
MIN_EXAMPLES = 20


def load_dataset():
    if not DATASET.exists():
        return []
    examples = []
    for line in DATASET.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            convs = d.get("conversations", [])
            if len(convs) >= 2:
                human = next((c["value"] for c in convs if c["from"] == "human"), "")
                gpt = next((c["value"] for c in convs if c["from"] == "gpt"), "")
                if human and gpt and len(gpt) > 20:
                    examples.append({"conversations": convs})
        except Exception:
            continue
    return examples


def run():
    examples = load_dataset()
    if len(examples) < MIN_EXAMPLES:
        log(f"Only {len(examples)} examples — skipping (need {MIN_EXAMPLES}+)")
        return False

    log(f"Loaded {len(examples)} training examples")

    try:
        from unsloth import FastLanguageModel
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import Dataset
    except ImportError as e:
        log(f"Import error: {e}")
        return False

    # Python 3.14 changed pickle.Pickler._batch_setitems to (self, items, obj).
    # HuggingFace datasets (<=4.x) overrides it with the old (self, items) signature,
    # so dataset fingerprinting / .map() raises TypeError on 3.14. Replace the override
    # with one that sorts dict keys (datasets' original behavior) and forwards the
    # optional obj arg only on 3.14+. (inspect.signature can't read the C Pickler, so
    # gate on the interpreter version instead.)
    import sys as _sys, dill
    from datasets.utils import _dill as _ds_dill
    _PY314 = _sys.version_info >= (3, 14)
    def _batch_setitems_compat(self, items, obj=None):
        if not getattr(self, "_legacy_no_dict_keys_sorting", False):
            try:
                items = sorted(items)
            except Exception:
                from datasets.fingerprint import Hasher
                items = sorted(items, key=lambda x: Hasher.hash(x[0]))
        if _PY314:
            return dill.Pickler._batch_setitems(self, items, obj)
        return dill.Pickler._batch_setitems(self, items)
    _ds_dill.Pickler._batch_setitems = _batch_setitems_compat

    ADAPTERS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    adapter_dir = ADAPTERS_DIR / f"echo-soul-{ts}"

    log(f"Loading base model: {BASE_MODEL}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=2048,
        load_in_4bit=True,
    )

    log("Applying LoRA...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
    )

    def format_example(ex):
        text = ""
        for c in ex["conversations"]:
            role = "User" if c["from"] == "human" else "Echo"
            text += f"{role}: {c['value']}\n"
        return {"text": text}

    dataset = Dataset.from_list(examples).map(format_example)

    log(f"Starting training...")
    t0 = time.time()

    # Match trainer precision to the model/hardware. Unsloth loads this 4bit model in
    # bf16 on Ampere+ GPUs (RTX 3060 supports bf16) and now errors if fp16 is forced.
    import torch
    _use_bf16 = torch.cuda.is_bf16_supported()
    log(f"Precision: {'bf16' if _use_bf16 else 'fp16'}")

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=2048,
        args=TrainingArguments(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            num_train_epochs=EPOCHS,
            learning_rate=2e-4,
            fp16=not _use_bf16,
            bf16=_use_bf16,
            logging_steps=10,
            # No mid-training checkpoints: unsloth's compiled-cache makes a duplicate
            # SFTConfig class, so HF's _save_checkpoint -> torch.save(self.args) raises
            # PicklingError on Python 3.14. The adapter is saved once at the end via
            # model.save_pretrained() (PEFT safetensors), which never pickles SFTConfig.
            save_strategy="no",
            output_dir="/tmp/echo_train_checkpoints",
            report_to="none",
        ),
    )

    trainer_stats = trainer.train()
    elapsed = time.time() - t0
    final_loss = trainer_stats.training_loss

    log(f"Training complete in {elapsed / 60:.1f} min")
    log(f"Final loss: {final_loss:.4f}")
    log(f"Saving LoRA adapter to {adapter_dir}")

    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))

    (adapter_dir / "training_log.json").write_text(json.dumps({
        "model": BASE_MODEL,
        "dataset_size": len(examples),
        "epochs": EPOCHS,
        "lora_rank": LORA_RANK,
        "final_loss": final_loss,
        "elapsed_seconds": elapsed,
        "completed_at": datetime.now().isoformat(),
        "output_dir": str(adapter_dir),
    }, indent=2))

    log("Training log saved")
    log(f"Success: adapter saved to {adapter_dir}")
    log("Run finetune_export.py to create the Ollama model.")
    return True


if __name__ == "__main__":
    sys.path.insert(0, str(BASE))
    ok = run()
    sys.exit(0 if ok else 1)
