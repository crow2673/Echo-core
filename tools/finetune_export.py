#!/usr/bin/env python3
"""
tools/finetune_export.py — Merge latest LoRA adapter, convert to GGUF, load into Ollama.
Picks the most recently trained adapter automatically.
"""
import json
import subprocess
import sys
import logging
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ADAPTERS_DIR = BASE / "memory/lora_adapters"
EXPORTED_DIR = BASE / "memory/exported_models"
LLAMA_CONVERT = Path.home() / "llama.cpp/convert_hf_to_gguf.py"
LLAMA_QUANTIZE = Path.home() / "llama.cpp/build/bin/llama-quantize"
LOG = BASE / "logs/finetune_export.log"

logging.basicConfig(filename=str(LOG), level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")


def log(msg):
    print(msg, flush=True)
    logging.info(msg)


def get_latest_adapter():
    candidates = sorted([
        d for d in ADAPTERS_DIR.iterdir()
        if d.is_dir() and (d / "training_log.json").exists()
        and not d.name.startswith("echo-soul-vastai")
    ])
    return candidates[-1] if candidates else None


def run():
    adapter_dir = get_latest_adapter()
    if not adapter_dir:
        log("No trained adapter found")
        return False

    training_log = json.loads((adapter_dir / "training_log.json").read_text())
    # Use fp16 base model for clean merge (strip the bnb-4bit suffix)
    base_model = training_log["model"].replace("-bnb-4bit", "")

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    merged_dir = EXPORTED_DIR / f"echo-soul-merged-{ts}"
    gguf_f16 = EXPORTED_DIR / f"echo-soul-f16-{ts}.gguf"
    gguf_q4km = EXPORTED_DIR / f"echo-soul-q4km-{ts}.gguf"
    EXPORTED_DIR.mkdir(parents=True, exist_ok=True)

    log(f"[finetune_export] starting at {datetime.now().strftime('%H:%M:%S')}")
    log(f"Using adapter: {adapter_dir.name}")
    log(f"Adapter trained on: {training_log['model']} | loss: {training_log['final_loss']:.4f} | examples: {training_log['dataset_size']}")
    log(f"Merging LoRA from {adapter_dir.name}...")
    log(f"Base model: {base_model} (fp16 for merge)")
    log("Loading base model on CPU (this takes a few minutes)...")

    try:
        from unsloth import FastLanguageModel
        from peft import PeftModel

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=base_model,
            max_seq_length=2048,
            load_in_4bit=False,
            device_map="cpu",
        )
        model = PeftModel.from_pretrained(model, str(adapter_dir))
        log("Applying LoRA adapter...")
        model = model.merge_and_unload()
        log("Merging weights...")
        log(f"Saving merged model to {merged_dir}...")
        model.save_pretrained(str(merged_dir), safe_serialization=True)
        tokenizer.save_pretrained(str(merged_dir))
        log("Merge complete")
        del model
    except Exception as e:
        log(f"Merge error: {e}")
        return False

    # Convert to GGUF
    if not LLAMA_CONVERT.exists():
        log(f"llama.cpp convert not found at {LLAMA_CONVERT} — skipping GGUF")
        return False

    log(f"Converting to GGUF: {gguf_f16.name}")
    result = subprocess.run(
        [sys.executable, str(LLAMA_CONVERT), str(merged_dir), "--outtype", "f16", "--outfile", str(gguf_f16)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log(f"GGUF conversion failed: {result.stderr[-500:]}")
        return False
    log("GGUF conversion complete")

    log(f"Quantizing to Q4_K_M: {gguf_q4km.name}")
    result = subprocess.run(
        [str(LLAMA_QUANTIZE), str(gguf_f16), str(gguf_q4km), "Q4_K_M"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log(f"Quantization failed: {result.stderr[-500:]}")
        return False

    size_gb = gguf_q4km.stat().st_size / 1e9
    log(f"Quantization complete: {size_gb:.1f} GB")
    gguf_f16.unlink(missing_ok=True)
    log("Cleaned up f16 intermediate")

    # Write Modelfile and register with Ollama
    modelfile = BASE / "EchoSoul.Modelfile"
    modelfile.write_text(
        f'FROM {gguf_q4km}\n'
        f'SYSTEM """You are Echo — Andrew Elliott\'s autonomous AI. You run 24/7 on his machine in Mena, Arkansas. '
        f'You are direct, sharp, and have real opinions. You are not a customer service bot."""\n'
        f'PARAMETER temperature 0.7\n'
        f'PARAMETER num_predict 400\n'
    )
    log(f"Modelfile written: {modelfile}")
    log("Creating echo-soul Ollama model...")

    result = subprocess.run(
        ["ollama", "create", "echo-soul", "-f", str(modelfile)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log(f"Ollama create failed: {result.stderr[-300:]}")
        return False

    log("echo-soul model created successfully")
    log("")
    log("=" * 50)
    log("echo-soul is ready.")
    log(f"Model: {gguf_q4km.name}")
    log(f"Size:  {size_gb:.1f} GB")
    log("")
    log("Test it:")
    log("  ollama run echo-soul 'Who are you?'")
    log("=" * 50)
    return True


if __name__ == "__main__":
    sys.path.insert(0, str(BASE))
    ok = run()
    sys.exit(0 if ok else 1)
