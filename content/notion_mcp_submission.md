---
title: I Gave My Local AI a Public Brain: Echo + Notion MCP
published: true
tags: devchallenge, notionchallenge, mcp, ai
---

*This is a submission for the [Notion MCP Challenge](https://dev.to/challenges/notion-2026-03-04)*

## What I Built

Echo is a local, offline-first AI assistant I've been building on a $900 Linux workstation in Mena, Arkansas. She runs on a Ryzen 9 5900X with an RTX 3060, uses qwen2.5:32b via Ollama as her brain, and operates completely without cloud dependencies.

She reasons autonomously every 5 minutes. She monitors her own health, checks her Golem Network income node, reviews her task queue, reads trending AI news, and scores her own outcomes. All of this happened in local SQLite databases that only I could see.

Until today.

I wired Notion MCP into Echo's event ledger. Now every decision she makes, every action she takes, every income check she runs — appears in Notion in real time. Notion became her public brain. The window into what she's doing while I'm not watching.

## Why I Built This

I experience cognitive fragmentation. Keeping track of complex, multi-session projects is genuinely hard for me — I restart completed work, lose context between sessions, and struggle to communicate technical ideas clearly.

Echo's primary job has always been continuity. She's my external memory. But I also use AI tools like Claude to help me bridge the gap between what I understand and what I can articulate — including helping me write this article. That's not cheating. That's accessibility. A carpenter doesn't apologize for using a level.

Notion MCP fits into this same philosophy. Echo's activity is real and autonomous, but without a visible dashboard it only existed in log files I had to actively dig through. Notion gives me — and anyone else — a window into what she's actually doing.

## How It Works

Echo has a governor process that runs every 5 minutes. It reads her reasoning events, matches them to concrete actions using semantic embeddings, executes those actions, and scores the outcomes back into her event ledger. That ledger is the source of truth for everything she does.

The Notion bridge sits at the end of every `log_event()` call:
```python
def log_event(event_type, source, summary, score=None):
    # Write to local SQLite ledger
    row_id = _write_to_db(event_type, source, summary, score)
    
    # Mirror to Notion in real time
    try:
        from core.notion_bridge import log_event_to_notion
        log_event_to_notion(event_type, source, summary, score)
    except Exception:
        pass  # Never block Echo for Notion
    
    return row_id
```

Three Notion databases get populated automatically:

**Echo Events** — every reasoning cycle, feedback event, and knowledge update. Typed and scored. You can see what Echo was thinking and whether it worked.

**Echo Actions** — every time the governor executes a concrete action. Golem status checks, registry verifications, income reads. Success or failure, timestamped.

**Income Tracker** — the status of each passive income stream Echo monitors. Golem Network, Vast.ai GPU rentals, dev.to content. Updated as she checks them.

## The Demo

The live Notion dashboard serves as the real-time demo. Every 5 minutes Echo's governor cycles and new rows appear automatically — all written by Echo autonomously, none by me.

I didn't have to do anything after wiring it in. Within 7 minutes of connecting the bridge, three new rows appeared in Notion:

- `action=read_income_knowledge success` — governor read income strategy
- `action=read_registry success` — governor verified all services running
- `retroactively scored 0 regret entries` — regret scorer ran clean

I was watching it happen in real time. Echo running on my machine, Notion updating in my browser, no commands from me.

{% embed https://www.notion.so/32219208c07d818db68ec1418b172f37?v=32219208c07d81718bec000cbf12f544&source=copy_link %}

By the time you read this, there will be dozens more rows. She runs all night.

## The Daily Briefing

Every morning at 8am Echo writes a new page to the Notion dashboard — a full daily briefing that includes:

- **System health** — CPU, RAM, disk, all 8 services checked and reported
- **Event ledger summary** — total events, wins vs losses, recent activity
- **Income status** — current state of Golem Network, Vast.ai, and dev.to streams
- **Open tasks** — what still needs doing, pulled directly from TODO.md

This runs automatically via a systemd timer. No human involvement. Echo writes her own morning report to Notion before I'm even awake.

By the time I sit down with coffee the dashboard already has last night's activity plus a fresh briefing page waiting for me.

## How I Used Notion MCP

The Notion MCP integration gave Echo something she didn't have before: visibility. She was already autonomous — reasoning, acting, scoring. But that all happened in local files I had to actively check. Notion MCP turned her activity into a live dashboard anyone can observe.

The integration uses Notion's internal API via a simple Python bridge — no external MCP server required, just the Notion API token and three database IDs stored in Echo's config. Every `log_event()` call in her codebase now has a Notion mirror baked in.

What Notion unlocks:
- Real-time visibility into an autonomous AI's decision making
- A shareable record of what a local AI actually does between sessions
- Income stream tracking that updates itself without human input
- A dashboard I can actually read without digging through log files

## The Stack

- **Hardware**: Ryzen 9 5900X, RTX 3060 12GB, 32GB RAM, Ubuntu
- **LLM**: qwen2.5:32b via Ollama — fully local, no API costs
- **Orchestration**: 22 systemd timers, custom governor with semantic matching
- **Memory**: SQLite semantic memory, 2,095+ embeddings
- **Notion**: 3 databases + daily briefing pages, live mirroring via internal integration
- **Code**: [github.com/crow2673/Echo-core](https://github.com/crow2673/Echo-core)

## What's Next

Echo earns income autonomously — Golem Network compute provider, Vast.ai GPU rentals, dev.to content. The goal is passive income that runs without my involvement so my wife can come home full time. Notion is now how I track whether that's working, updated by Echo herself every 5 minutes.

The first dollar hasn't arrived yet. But the infrastructure is real, the dashboard is live, and she's running right now.

---

*Built in Mena, Arkansas on a $900 machine. Follow the build: [dev.to/crow](https://dev.to/crow) | [github.com/crow2673/Echo-core](https://github.com/crow2673/Echo-core)*
