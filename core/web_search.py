#!/usr/bin/env python3
"""
core/web_search.py — Web search capability for Echo

Gives Echo the ability to look things up: prices, news, research topics,
verify facts, check market conditions, research Fiverr lead companies.

Uses DuckDuckGo (free, no API key). Falls back gracefully if offline.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
LOG = BASE / "logs/web_search.log"
CACHE_FILE = BASE / "memory/search_cache.json"
CACHE_MAX = 200


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    try:
        LOG.parent.mkdir(exist_ok=True)
        with open(LOG, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_cache(cache):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if len(cache) > CACHE_MAX:
        keys = sorted(cache.keys())
        for k in keys[:len(cache) - CACHE_MAX]:
            del cache[k]
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, default=str))
    tmp.rename(CACHE_FILE)


def search(query: str, max_results: int = 5, cache_hours: float = 6.0) -> list:
    """
    Search the web. Returns list of {title, url, body} dicts.
    Caches results for cache_hours to avoid hammering DDG.
    """
    cache_key = f"web:{query}:{max_results}"
    cache = _load_cache()
    if cache_key in cache:
        cached_at = cache[cache_key].get("cached_at", "")
        if cached_at:
            try:
                age = (datetime.now() - datetime.fromisoformat(cached_at)).total_seconds()
                if age < cache_hours * 3600:
                    return cache[cache_key].get("results", [])
            except Exception:
                pass

    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        normalized = [{"title": r.get("title", ""), "url": r.get("href", ""), "body": r.get("body", "")} for r in results]
        cache[cache_key] = {"results": normalized, "cached_at": datetime.now().isoformat()}
        _save_cache(cache)
        log(f"search: '{query}' → {len(normalized)} results")
        return normalized
    except ImportError:
        log("duckduckgo_search not installed")
        return []
    except Exception as e:
        log(f"search error: {e}")
        return []


def search_news(query: str, max_results: int = 5) -> list:
    """Search recent news. No cache — news is time-sensitive."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=max_results))
        log(f"news: '{query}' → {len(results)} results")
        return results
    except ImportError:
        log("news search failed: duckduckgo_search not installed")
        return []
    except Exception as e:
        log(f"news search failed: {e}")
        return []


def research(query: str, max_results: int = 5) -> str:
    """
    Search + summarize. Returns a plain-text research summary
    suitable for feeding into Echo's context.
    """
    results = search(query, max_results=max_results)
    if not results:
        return f"No results found for: {query}"
    lines = [f"Research: {query}"]
    for i, r in enumerate(results[:5]):
        title = r.get("title", "")
        body = r.get("body", "")[:200]
        lines.append(f"{i+1}. {title}: {body}")
    return "\n".join(lines)


def search_for_lead(company_or_person: str) -> str:
    """Research a Fiverr/Reddit lead — who they are, what they need."""
    results = search(f"{company_or_person} company AI automation needs", max_results=3)
    if not results:
        return f"Could not research: {company_or_person}"
    lines = [f"Lead research: {company_or_person}"]
    for r in results[:3]:
        title = r.get("title", "")
        body = r.get("body", "")[:150]
        lines.append(f"• {title}: {body}")
    return "\n".join(lines)


def get_crypto_price(symbol: str) -> str:
    """Quick price lookup for a crypto symbol."""
    results = search(f"{symbol} price USD today", max_results=2)
    for r in results:
        body = r.get("body", "")
        if "$" in body or "USD" in body:
            return body[:100]
    return ""


def check_market_news(symbols: list = None) -> list:
    """Get recent market/trading news."""
    query = "stock market news today " + " ".join(symbols or [])
    return search_news(query.strip(), max_results=5)
