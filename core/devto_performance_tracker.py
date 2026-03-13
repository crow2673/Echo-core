#!/usr/bin/env python3
"""
Dev.to performance tracker — extends devto_analytics with:
- Trend detection (views growing/stagnating/declining per article)
- Topic extraction from top performers
- Direct draft_queue injection when a topic is trending
- Event ledger logging
Runs after devto_analytics (daily 9am) or standalone.
"""
import json, sys, re
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parents[1]
ANALYTICS = BASE / "memory/devto_analytics.json"
HISTORY = BASE / "memory/devto_history.json"
DRAFT_QUEUE = BASE / "content/draft_queue.json"
LOG = BASE / "logs/devto_tracker.log"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default

def extract_topics(title):
    """Extract key topics from article title."""
    stopwords = {"a","an","the","and","or","but","in","on","at","to","for",
                 "of","with","by","from","is","are","was","were","be","been",
                 "how","what","why","when","where","i","my","your","their"}
    words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9+#.-]{2,}\b', title.lower())
    return [w for w in words if w not in stopwords]

def run():
    log("devto_performance_tracker started")

    if not ANALYTICS.exists():
        log("no analytics data found — run devto_analytics first")
        return

    current = load_json(ANALYTICS, [])
    history = load_json(HISTORY, {})
    draft_queue = load_json(DRAFT_QUEUE, [])
    today = datetime.now().strftime("%Y-%m-%d")

    if not current:
        log("analytics empty")
        return

    insights = []
    trending_topics = []

    for article in current:
        aid = str(article["id"])
        title = article["title"]
        views = article["views"]
        reactions = article["reactions"]

        # Load history for this article
        prev = history.get(aid, {})
        prev_views = prev.get("views", 0)
        prev_reactions = prev.get("reactions", 0)
        prev_date = prev.get("date", "")

        view_delta = views - prev_views
        reaction_delta = reactions - prev_reactions

        # Trend detection
        if prev_views > 0:
            growth_pct = ((views - prev_views) / prev_views) * 100
            if growth_pct > 20:
                trend = "GROWING"
                trending_topics.extend(extract_topics(title))
                insights.append(f"GROWING: '{title}' +{view_delta} views ({growth_pct:.0f}% up)")
            elif growth_pct < -5:
                trend = "DECLINING"
                insights.append(f"DECLINING: '{title}' {view_delta} views")
            else:
                trend = "STABLE"
        else:
            trend = "NEW"
            insights.append(f"NEW: '{title}' {views} views, {reactions} reactions")

        # Update history
        history[aid] = {
            "title": title,
            "views": views,
            "reactions": reactions,
            "trend": trend,
            "date": today,
            "view_delta": view_delta,
            "reaction_delta": reaction_delta,
        }

    # Save updated history
    HISTORY.write_text(json.dumps(history, indent=2))

    # Find best performer
    best = max(current, key=lambda x: x["views"])
    total_views = sum(a["views"] for a in current)
    total_reactions = sum(a["reactions"] for a in current)

    log(f"total: {total_views} views, {total_reactions} reactions across {len(current)} articles")
    for insight in insights:
        log(f"  {insight}")

    # If trending topics found, queue a draft
    if trending_topics:
        # Deduplicate and take top 3
        seen = set()
        unique_topics = []
        for t in trending_topics:
            if t not in seen:
                seen.add(t)
                unique_topics.append(t)
        topic_str = ", ".join(unique_topics[:3])
        
        draft_id = f"perf_tracker_{today}"
        existing_ids = [d.get("id") for d in draft_queue]
        
        if draft_id not in existing_ids:
            draft_queue.append({
                "id": draft_id,
                "source": "devto_performance_tracker",
                "topic": f"Follow-up on trending topics: {topic_str}",
                "prompt": f"Write a dev.to article that builds on the success of '{best['title']}'. Focus on topics: {topic_str}. Target audience: developers interested in local AI and automation.",
                "priority": "high",
                "created_at": datetime.now().isoformat(),
                "status": "queued"
            })
            DRAFT_QUEUE.parent.mkdir(exist_ok=True)
            DRAFT_QUEUE.write_text(json.dumps(draft_queue, indent=2))
            log(f"draft queued: follow-up on topics [{topic_str}]")

    # Log to event ledger
    try:
        sys.path.insert(0, str(BASE))
        from core.event_ledger import log_event
        summary = f"devto: {total_views} total views, {total_reactions} reactions, best='{best['title'][:40]}'"
        if trending_topics:
            summary += f", trending topics: {', '.join(unique_topics[:3])}"
        log_event("feedback", "devto_tracker", summary, score=1.0)
    except Exception as e:
        log(f"ledger error: {e}")

    log("tracker done")

if __name__ == "__main__":
    run()
