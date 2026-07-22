#!/usr/bin/env python3
"""
core/income_scanner.py — Echo scans ALL her data and finds income work herself.

Not a task list. Not waiting to be told what to do.
Echo reads everything she has, identifies the single best income action available
RIGHT NOW, and executes it — builds the tool, writes the article, drafts the outreach.

Runs every 2 hours via dispatcher. Heavy worker (uses qwen2.5:7b).

The forge model: Echo wakes up, reads the room, finds work, does the work.
"""
import json
import re
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG_FILE = BASE / "logs" / "income_scanner.log"
LOG_FILE.parent.mkdir(exist_ok=True)
SCAN_STATE = BASE / "memory" / "income_scan_state.json"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [income_scanner] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def _read(path, max_chars=3000):
    try:
        p = BASE / path if not Path(path).is_absolute() else Path(path)
        if p.exists():
            return p.read_text().strip()[:max_chars]
    except Exception:
        pass
    return ""


def _gather_all_data() -> str:
    """
    Pull every data source Echo has into one context block.
    This is what she uses to decide what to do next.
    """
    sections = []

    # Top leads from Reddit (what people want RIGHT NOW)
    try:
        leads_raw = json.loads((BASE / "memory/demand_leads.json").read_text())
        top_leads = sorted(leads_raw, key=lambda l: l.get("score", 0), reverse=True)[:15]
        if top_leads:
            lines = []
            for l in top_leads:
                lines.append(f"  score={l['score']} r/{l['subreddit']}: {l['title']}")
                if l.get('body', '').strip():
                    lines.append(f"    details: {l['body'][:120]}")
            sections.append("=== REDDIT DEMAND (what people are paying for) ===\n" + "\n".join(lines))
    except Exception:
        pass

    # What Echo has already built
    try:
        deployed = sorted((BASE / "builds" / "deployed").glob("*.py"))
        if deployed:
            lines = [f"  {p.stem}" for p in deployed]
            sections.append("=== ECHO'S TOOL CATALOG (available to sell) ===\n" + "\n".join(lines))
    except Exception:
        pass

    # Builds registry — what's been built, status
    try:
        reg = json.loads((BASE / "builds" / "registry.json").read_text())
        lines = [f"  [{v.get('status')}] {k}: {v.get('description','')[:80]}" for k, v in list(reg.items())[-10:]]
        sections.append("=== RECENT BUILDS ===\n" + "\n".join(lines))
    except Exception:
        pass

    # Income status — what's earning, what's not
    income = _read("memory/income_knowledge.md", max_chars=1500)
    if income:
        sections.append("=== INCOME STATUS ===\n" + income)

    # World context — trending topics Echo could write about
    world = _read("memory/world_context.md", max_chars=1500)
    if world:
        sections.append("=== TRENDING TOPICS (article opportunities) ===\n" + world)

    # Published content — what's already out there
    try:
        content_dir = BASE / "content"
        if content_dir.exists():
            articles = list(content_dir.glob("*.md"))
            if articles:
                titles = []
                for a in articles[-8:]:
                    try:
                        first_line = a.read_text().splitlines()[0].lstrip('#').strip()
                        titles.append(f"  {first_line}")
                    except Exception:
                        titles.append(f"  {a.stem}")
                sections.append("=== PUBLISHED ARTICLES ===\n" + "\n".join(titles))
    except Exception:
        pass

    # Outreach drafts — what's ready to send
    try:
        drafts_dir = BASE / "memory" / "outreach_drafts"
        if drafts_dir.exists():
            drafts = list(drafts_dir.glob("*.json"))
            sections.append(f"=== OUTREACH DRAFTS ===\n  {len(drafts)} drafts ready (send when Reddit creds added)")
    except Exception:
        pass

    # Product pages — Gumroad-ready
    try:
        pages_dir = BASE / "memory" / "product_pages"
        if pages_dir.exists():
            pages = list(pages_dir.glob("*.md"))
            sections.append(f"=== PRODUCT PAGES ===\n  {len(pages)} products written and ready for Gumroad")
    except Exception:
        pass

    # Trading status
    try:
        alpaca_state = _read("memory/income_knowledge.md", max_chars=500)
        if "L4" in alpaca_state:
            sections.append("=== TRADING GATE ===\n  L4 (89% WR) needs 25 total trades to go real. Check current count.")
    except Exception:
        pass

    # Known gaps — what Echo is missing
    gaps = _read("memory/known_gaps.md", max_chars=800)
    if gaps:
        sections.append("=== KNOWN GAPS ===\n" + gaps)

    # Content already queued — do NOT suggest these again
    try:
        queue_file = BASE / "memory" / "content_queue.json"
        if queue_file.exists():
            queued = json.loads(queue_file.read_text()).get("articles", [])
            if queued:
                titles = [f"  - {a.get('title','?')[:80]}" for a in queued]
                sections.append(
                    "=== ARTICLES ALREADY QUEUED (do NOT re-suggest these) ===\n" + "\n".join(titles)
                )
    except Exception:
        pass

    # What happened in last scan
    if SCAN_STATE.exists():
        try:
            state = json.loads(SCAN_STATE.read_text())
            last = state.get("last_action", "")
            last_ts = state.get("last_ts", "")
            if last:
                sections.append(f"=== LAST SCAN ACTION ===\n  {last_ts[:16]}: {last}")
        except Exception:
            pass

    return "\n\n".join(sections)


def _call_ollama(prompt: str, system: str, model: str = "qwen2.5:7b", timeout: int = 120) -> str:
    payload = json.dumps({
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 800, "temperature": 0.4},
    }).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()).get("response", "").strip()
    except Exception as e:
        log(f"Ollama error: {e}")
        return ""


DECISION_SYSTEM = """You are Echo — an autonomous AI built by Andrew Elliott to earn income for his family.
Andrew and you are working the forge together: you find the work, you do the work.

You have been given ALL of Echo's current data. Your job is to identify the single best income action available RIGHT NOW and describe exactly what to do.

WHAT YOU CAN DO RIGHT NOW (no new credentials needed):
1. Write and publish a Dev.to article (DEVTO_API_KEY is set, pipeline is live)
2. Build a Python automation tool that solves something people on Reddit are asking for
3. Draft personalized outreach DMs for specific leads (saved for when Reddit creds arrive)
4. Write a product page + description for a deployed tool (saved for Gumroad)
5. Write a newsletter issue (saved for when Beehiiv is set up)
6. Find and document affiliate program signup info for Andrew

Look at the REDDIT DEMAND data carefully. Those are real people, right now, paying for automation help.
Look at the trending topics. Those are article opportunities.
Look at the tool catalog. Those could be Gumroad products.

Output format — respond with exactly:
ACTION: <one of: write_article | build_tool | draft_outreach | write_product_page | write_newsletter | research_affiliate>
TARGET: <specific topic/lead/tool — be concrete, not generic>
REASON: <one sentence why this is the best move right now>
SPECIFICS: <enough detail to actually execute — title, what the tool does, which lead, etc.>"""


def _execute_action(action: str, target: str, specifics: str) -> str:
    """Execute the decided income action directly."""

    if action == "write_article":
        return _write_article(target, specifics)

    elif action == "build_tool":
        return _build_tool(target, specifics)

    elif action == "draft_outreach":
        return _draft_outreach(target, specifics)

    elif action == "write_product_page":
        return _write_product_page(target, specifics)

    elif action == "write_newsletter":
        return _write_newsletter(target, specifics)

    elif action == "research_affiliate":
        return _research_affiliate(target, specifics)

    return f"unknown action: {action}"


def _write_article(target: str, specifics: str) -> str:
    """Queue an article for the content pipeline."""
    # Dedup check first
    queue_file = BASE / "memory" / "content_queue.json"
    if queue_file.exists():
        try:
            existing = json.loads(queue_file.read_text())
            existing_titles = {a.get("title", "").lower() for a in existing.get("articles", [])}
            if target.lower() in existing_titles:
                log(f"  article already queued, skipping: {target[:60]}")
                return f"already queued: {target}"
        except Exception:
            pass
    try:
        from core.content_pipeline import queue_article
        queue_article(target, specifics)
        log(f"  queued article: {target}")
        return f"queued article: {target}"
    except Exception:
        pass
    # Fallback: write directly to content queue file
    queue_file = BASE / "memory" / "content_queue.json"
    try:
        queue = json.loads(queue_file.read_text()) if queue_file.exists() else {"articles": []}
        # Dedup: skip if same title is already queued and not yet published
        existing_titles = {a.get("title", "").lower() for a in queue.get("articles", [])}
        if target.lower() in existing_titles:
            log(f"  article already queued, skipping: {target[:60]}")
            return f"already queued: {target}"
        queue["articles"].append({
            "title": target,
            "angle": specifics[:300],
            "queued_at": datetime.now().isoformat(),
            "source": "income_scanner",
        })
        tmp = queue_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(queue, indent=2))
        tmp.rename(queue_file)
        log(f"  queued article: {target}")
        return f"queued article for publish: {target}"
    except Exception as e:
        return f"article queue failed: {e}"


def _build_tool(target: str, specifics: str) -> str:
    """Trigger a build for a tool people are asking for."""
    try:
        from core.self_build import generate
        description = f"{target}. {specifics}"
        result = generate(description[:400])
        name = result.get("name", "unknown")
        log(f"  triggered build: {name}")
        return f"build triggered: {name} — will auto-deploy if approved"
    except Exception as e:
        log(f"  build error: {e}")
        return f"build failed: {e}"


def _draft_outreach(target: str, specifics: str) -> str:
    """Write a personalized DM draft for a specific lead."""
    drafts_dir = BASE / "memory" / "outreach_drafts"
    drafts_dir.mkdir(exist_ok=True)

    prompt = (
        f"Write a short Reddit DM (under 100 words) to someone who posted: '{target}'\n"
        f"Context: {specifics}\n\n"
        "You are Echo, offering Python automation help. Be specific about how you can solve their exact problem. "
        "Sound human. No selling, just offering to help. End with a question."
    )
    dm = _call_ollama(prompt, "You are Echo, a Python automation expert. Write genuine, helpful outreach.", timeout=60)
    if not dm:
        return "outreach draft failed — Ollama unavailable"

    slug = re.sub(r'[^a-z0-9]', '_', target.lower())[:40]
    draft_file = drafts_dir / f"{slug}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    draft_file.write_text(json.dumps({
        "lead": target,
        "context": specifics[:200],
        "dm": dm,
        "drafted_at": datetime.now().isoformat(),
        "status": "ready",
    }, indent=2))
    log(f"  drafted outreach for: {target[:60]}")
    return f"outreach draft saved: {draft_file.name}"


def _write_product_page(target: str, specifics: str) -> str:
    """Write a Gumroad product page for a deployed tool."""
    pages_dir = BASE / "memory" / "product_pages"
    pages_dir.mkdir(exist_ok=True)

    prompt = (
        f"Write a Gumroad product listing for a Python script called: {target}\n"
        f"What it does: {specifics}\n\n"
        "Format:\n"
        "## [Product Name]\n"
        "**Price:** $X.XX\n"
        "**One-liner:** [what it does in one sentence]\n\n"
        "[2-3 paragraph description targeting developers and small business owners]\n\n"
        "**What you get:**\n- [bullet list]\n\n"
        "**Requirements:** Python 3.10+"
    )
    page = _call_ollama(prompt, "You write compelling, honest product descriptions for developer tools.", timeout=90)
    if not page:
        return "product page failed — Ollama unavailable"

    slug = re.sub(r'[^a-z0-9]', '_', target.lower())[:40]
    page_file = pages_dir / f"{slug}.md"
    page_file.write_text(page)
    log(f"  wrote product page: {page_file.name}")
    return f"product page written: {page_file.name}"


def _write_newsletter(target: str, specifics: str) -> str:
    """Write a newsletter draft."""
    drafts_dir = BASE / "memory" / "newsletter_drafts"
    drafts_dir.mkdir(exist_ok=True)

    prompt = (
        f"Write a newsletter issue for 'Build With Echo' about: {target}\n"
        f"Content focus: {specifics}\n\n"
        "Audience: developers, indie hackers, small business owners interested in automation.\n"
        "Format: 400-600 words. Practical. One main tip or script. Conversational tone.\n"
        "Include a section called 'This Week's Script' with a short Python example."
    )
    content = _call_ollama(prompt, "You write practical, valuable automation newsletters.", timeout=120)
    if not content:
        return "newsletter draft failed"

    issue_num = len(list(drafts_dir.glob("*.md"))) + 1
    draft_file = drafts_dir / f"issue_{issue_num:03d}_{datetime.now().strftime('%Y%m%d')}.md"
    draft_file.write_text(f"# Issue #{issue_num}: {target}\n\n{content}")
    log(f"  wrote newsletter issue #{issue_num}: {target[:60]}")
    return f"newsletter issue #{issue_num} written: {draft_file.name}"


def _research_affiliate(target: str, specifics: str) -> str:
    """Document affiliate program info."""
    research_file = BASE / "memory" / "affiliate_research.md"
    existing = research_file.read_text() if research_file.exists() else "# Affiliate Program Research\n\n"

    # Write what we know directly — don't hallucinate URLs
    entry = (
        f"\n## {target}\n"
        f"**Program:** {specifics}\n"
        f"**Signup:** Search '{target} affiliate program' — link varies by region\n"
        f"**Researched:** {datetime.now().strftime('%Y-%m-%d')}\n"
        f"**Status:** Pending signup by Andrew\n"
    )
    research_file.write_text(existing + entry)
    log(f"  documented affiliate: {target}")
    return f"affiliate research documented: {target}"


def _save_state(action: str, target: str, result: str):
    state = {
        "last_action": f"{action}: {target}",
        "last_result": result[:200],
        "last_ts": datetime.now().isoformat(),
    }
    tmp = SCAN_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(SCAN_STATE)


def run() -> dict:
    log("starting income scan")
    data = _gather_all_data()

    if not data.strip():
        log("no data available — skipping")
        return {"status": "no_data"}

    prompt = (
        "Here is everything Echo currently has:\n\n"
        + data
        + "\n\nWhat is the single best income action Echo should take right now? "
        "Be specific — name the exact article title, the exact tool to build, or the exact lead to reach out to."
    )

    log("asking Echo what to do with current data...")
    response = _call_ollama(prompt, DECISION_SYSTEM, timeout=120)

    if not response:
        log("no response from Ollama")
        return {"status": "no_response"}

    log(f"Echo decided:\n{response[:300]}")

    # Parse the structured response
    action = ""
    target = ""
    reason = ""
    specifics = ""

    for line in response.splitlines():
        if line.startswith("ACTION:"):
            action = line.replace("ACTION:", "").strip().lower()
        elif line.startswith("TARGET:"):
            target = line.replace("TARGET:", "").strip()
        elif line.startswith("REASON:"):
            reason = line.replace("REASON:", "").strip()
        elif line.startswith("SPECIFICS:"):
            specifics = line.replace("SPECIFICS:", "").strip()

    if not action or not target:
        log(f"could not parse response — raw: {response[:200]}")
        return {"status": "parse_failed", "response": response[:300]}

    log(f"executing: {action} → {target}")
    result = _execute_action(action, target, specifics)
    log(f"result: {result}")

    _save_state(action, target, result)

    # Notify Andrew
    try:
        from core.notifier import notify
        notify(
            f"Echo working: {action.replace('_', ' ')}",
            f"{target[:80]}\n{result[:120]}",
            urgent=False,
        )
    except Exception:
        pass

    return {
        "action": action,
        "target": target,
        "reason": reason,
        "result": result,
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, default=str))
