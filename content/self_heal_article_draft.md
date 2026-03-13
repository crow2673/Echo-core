# She Started Fixing Herself: Building a Self-Healing AI Agent on Linux

I didn't plan for Echo to be self-healing. I planned for her to be useful.

The self-healing came from necessity — I work a day job, I can't babysit a daemon all day. If something breaks at 2pm and I don't see it until 8pm, six hours of autonomous work is gone. So I built in the ability to detect failure, log it, and adjust.

Here's what that actually looks like in practice.

## The Problem With Autonomous Agents

Echo runs on my Ryzen 9 5900X / RTX 3060 box — no cloud, no subscription, just local Ollama models and a stack of Python daemons. She monitors herself, generates suggestions, acts on them, and records outcomes.

The issue: she had no feedback loop. She could act, but she couldn't learn that an action was bad. She'd repeat the same broken suggestion indefinitely, confident each time.

## The Regret Index

I built what I call the regret index. Every autonomous action gets logged with a score:
```python
# +1 action moved mission forward
# 0  neutral / outcome unknown  
# -1 action created noise or broken state
# -2 action required manual intervention
```

When a category of actions averages below -0.4, or a specific action fails 3+ times, it gets flagged. The auto_act loop checks those flags before executing:
```python
active_flags = get_flags()
flagged_categories = {f[1] for f in active_flags if f[0] == "category"}

if suggestion.get("category") in flagged_categories:
    log(f"SKIPPED (regret flag): {sid}")
    continue
```

She doesn't punish herself. She just stops repeating the mistake.

## The Boot Timing Bug

The ntfy bridge — which lets me message Echo from my phone — was randomly failing on boot. It would connect, capture a timestamp, then die because the system clock hadn't fully synced yet. Every message sent in that window was lost.

Fix was two lines:
```python
time.sleep(2)  # survive boot clock skew
since = int(time.time())  # now capture timestamp
```

Two lines. Six hours of debugging to find it.

## The Double-Fire Problem

The auto_act daemon was firing twice on boot due to `Persistent=true` catching up missed runs. Added an fcntl lockfile:
```python
lockfile = open(BASE / "logs/auto_act.lock", "w")
fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
# raises BlockingIOError if already running
```

Clean. One fire per trigger.

## What Self-Healing Actually Means

It doesn't mean Echo fixes arbitrary bugs. It means:

- She knows what she tried
- She knows what the outcome was
- She adjusts her behavior based on that signal
- Her morning briefing includes a regret report so I know too

The regret index runs a pattern audit after every outcome update. If a category drifts negative, she flags it herself and stops acting in that space until I clear it.

## The Stack

Everything runs as systemd user services. Eight timers, one persistent bridge, one core daemon. No cloud. No API bills. The whole thing costs electricity.
```
echo-status output:
SUMMARY: OK ✅  core=active  stale=0  inactive_timers=0  errors=0
Timers: ✅ auto_act  ✅ git_backup  ✅ golem_monitor  
        ✅ heartbeat  ✅ ntfy_bridge  ✅ pulse  
        ✅ reachability  ✅ self_act_worker
```

She backs up to GitHub every night at 3am. She monitors her own disk. She benchmarks her Golem node pricing. She does all of this without me touching a keyboard.

## What's Next

The regret index records outcomes and surfaces patterns. Since writing this, I've closed the loop further — a governor process now reads the reasoning ledger, matches it to concrete actions, executes them, and scores the results back into the same ledger. Reason → act → score, autonomously.

Also: she's running as a Golem network provider. Zero tasks so far — new node penalty. But the offers are published, the wallet is funded with gas, and she's listening.

If you're building local AI agents, the biggest gap I found wasn't capability — it was accountability. Without a feedback loop, an autonomous agent is just a confident failure machine.

The regret index is how I gave her the ability to be wrong, know it, and stop.

---

*Echo is open source: github.com/crow2673/Echo-core*  
*Follow the build: dev.to/crow*
