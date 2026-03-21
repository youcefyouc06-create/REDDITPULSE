"""
Opportunity Engine — Scraper Job (run from your PC)
Master background script that:
  1. Scrapes Reddit (15 subs) + HN + PH + IH
  2. Clusters posts into idea topics
  3. Calculates the "stock price" for each idea
  4. Stores results in Supabase (ideas + idea_history)
  5. Logs the run in scraper_runs

Usage:
  python scraper_job.py                    # full scan, all sources
  python scraper_job.py --sources reddit   # reddit only
  python scraper_job.py --topics "invoice,crm"  # specific topics only
"""

import os
import sys
import json
import time
import re
import asyncio
import math
import hashlib
import argparse
import traceback
import requests
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
from urllib.parse import quote

# Add engine to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "engine"))

from config import TARGET_SUBREDDITS, PAIN_PHRASES, USER_AGENTS, SPAM_PATTERNS, HUMOR_INDICATORS
from pain_stream import check_alerts_against_posts
from competitor_deathwatch import scan_for_complaints, save_complaints
from competition import KNOWN_COMPETITORS
from trends_aggregator import aggregate_trends
import random

# ── Supabase config ──
SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_KEY")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY", "")
)

# ── Spam/humor compiled patterns ──
_spam_re = [re.compile(p, re.IGNORECASE) for p in SPAM_PATTERNS]
_humor_re = [re.compile(p, re.IGNORECASE) for p in HUMOR_INDICATORS]
BASE_SUBREDDITS = list(TARGET_SUBREDDITS)
_SCHEMA_CACHE = {}


# ═══════════════════════════════════════════════════════
# SUPABASE HELPERS
# ═══════════════════════════════════════════════════════

def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def sb_upsert(table, rows, on_conflict=""):
    """Upsert rows to Supabase. Returns response."""
    h = _headers()
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if on_conflict:
        h["Prefer"] = "resolution=merge-duplicates,return=representation"
        url = f"{url}?on_conflict={quote(on_conflict, safe=',')}"
    r = requests.post(url, json=rows, headers=h, timeout=30)
    if r.status_code >= 400:
        print(f"    [!] Supabase {table} error {r.status_code}: {r.text[:200]}")
    return r


def sb_select(table, query=""):
    """Select from Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
    r = requests.get(url, headers=_headers(), timeout=15)
    if r.status_code == 200:
        return r.json()
    return []


def sb_patch(table, match_query, data):
    """Patch rows in Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?{match_query}"
    h = _headers()
    h["Prefer"] = "return=minimal"
    r = requests.patch(url, json=data, headers=h, timeout=15)
    return r


def sb_rpc(fn_name, params=None):
    """Invoke a Supabase RPC function."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/{fn_name}"
    r = requests.post(url, json=params or {}, headers=_headers(), timeout=30)
    if r.status_code >= 400:
        print(f"    [!] Supabase RPC {fn_name} error {r.status_code}: {r.text[:200]}")
    return r


def table_has_column(table, column):
    """Best-effort schema check so scraper upgrades don't break older DBs."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return True

    cache_key = (table, column)
    if cache_key in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[cache_key]

    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_headers(),
            params={"select": column, "limit": 1},
            timeout=10,
        )
        exists = resp.status_code == 200
    except Exception:
        exists = False

    _SCHEMA_CACHE[cache_key] = exists
    return exists


def load_user_requested_subreddits():
    """Merge user-discovered subreddits with the base scraper coverage."""
    if not SUPABASE_URL:
        return BASE_SUBREDDITS
    rows = sb_select("user_requested_subreddits", "select=subreddit")
    extra_subs = [row["subreddit"] for row in rows if row.get("subreddit")]
    all_subs = list(dict.fromkeys(BASE_SUBREDDITS + extra_subs))
    print(f"  [Scraper] Covering {len(all_subs)} subreddits ({len(extra_subs)} user-discovered)")
    return all_subs


def _to_iso_datetime(value):
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        except Exception:
            return datetime.now(timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _to_epoch_timestamp(value):
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return 0.0
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0
    return 0.0


def _parse_datetime(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None
    return None


def _coerce_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _should_advance_baseline(last_update, now_utc, interval):
    if last_update is None:
        return True
    return now_utc - last_update >= interval


def _resolve_score_baselines(existing, now_utc):
    if not existing:
        return {
            "prev_24h": 0.0,
            "prev_7d": 0.0,
            "prev_30d": 0.0,
            "next_score_24h_ago": 0.0,
            "next_score_7d_ago": 0.0,
            "next_score_30d_ago": 0.0,
            "next_last_24h_update": now_utc.isoformat(),
            "next_last_7d_update": now_utc.isoformat(),
        }

    existing_current = _coerce_float(existing.get("current_score"))
    stored_24h = _coerce_float(existing.get("score_24h_ago"))
    stored_7d = _coerce_float(existing.get("score_7d_ago"))
    stored_30d = _coerce_float(existing.get("score_30d_ago"))

    last_24h_update = _parse_datetime(existing.get("last_24h_update"))
    last_7d_update = _parse_datetime(existing.get("last_7d_update"))

    prev_24h = stored_24h if stored_24h > 0 else existing_current
    next_score_24h_ago = stored_24h
    next_last_24h_update = last_24h_update.isoformat() if last_24h_update else now_utc.isoformat()

    if _should_advance_baseline(last_24h_update, now_utc, timedelta(hours=24)) or stored_24h <= 0:
        prev_24h = existing_current
        next_score_24h_ago = existing_current
        next_last_24h_update = now_utc.isoformat()

    prev_7d = stored_7d if stored_7d > 0 else 0.0
    next_score_7d_ago = stored_7d
    next_last_7d_update = last_7d_update.isoformat() if last_7d_update else now_utc.isoformat()

    if _should_advance_baseline(last_7d_update, now_utc, timedelta(days=7)):
        rolled_7d = stored_24h if stored_24h > 0 else existing_current
        next_score_7d_ago = rolled_7d
        next_last_7d_update = now_utc.isoformat()
        prev_7d = rolled_7d

    prev_30d = stored_30d if stored_30d > 0 else 0.0

    return {
        "prev_24h": prev_24h,
        "prev_7d": prev_7d,
        "prev_30d": prev_30d,
        "next_score_24h_ago": next_score_24h_ago,
        "next_score_7d_ago": next_score_7d_ago,
        "next_score_30d_ago": stored_30d,
        "next_last_24h_update": next_last_24h_update,
        "next_last_7d_update": next_last_7d_update,
    }


def _post_activity_timestamp(post):
    """Recent-signal timestamp with scraped_at fallback for live feeds."""
    created_ts = _to_epoch_timestamp(post.get("created_utc", 0))
    if created_ts > 0:
        return created_ts
    return _to_epoch_timestamp(post.get("scraped_at", 0))


def _build_source_breakdown(posts):
    counter = Counter(post.get("source", "unknown") for post in posts if post.get("source"))
    return [
        {"platform": platform, "count": count}
        for platform, count in counter.most_common()
    ]


def _build_pain_summary(posts, topic_name=""):
    phrase_counter = Counter()
    supporting_titles = []
    matched_posts = 0

    sorted_posts = sorted(
        posts,
        key=lambda post: int(post.get("score", 0) or 0) + int(post.get("num_comments", 0) or 0),
        reverse=True,
    )

    for post in sorted_posts:
        text_lower = f"{post.get('title', '')} {post.get('full_text', '')} {post.get('body', '')}".lower()
        matches = []
        for phrase in PAIN_PHRASES[:30]:
            normalized = phrase.lower()
            if normalized in text_lower:
                matches.append(normalized)

        if not matches:
            continue

        matched_posts += 1
        phrase_counter.update(matches[:3])
        title = (post.get("title", "") or "").strip()
        if title and len(supporting_titles) < 2:
            supporting_titles.append(title[:120])

    if matched_posts == 0:
        return None, 0

    top_phrases = [phrase for phrase, _ in phrase_counter.most_common(2)]
    if top_phrases:
        if len(top_phrases) == 1:
            summary = f"People repeatedly complain about {top_phrases[0]}."
        else:
            summary = f"People repeatedly complain about {top_phrases[0]} and {top_phrases[1]}."
    else:
        summary = f"People repeatedly describe friction around {topic_name.lower() if topic_name else 'this theme'}."

    if supporting_titles:
        summary += f" A representative discussion was: {supporting_titles[0]}."

    return summary[:420], matched_posts


MARKET_PAIN_KEYWORDS = [
    "hate", "frustrated", "struggling", "help",
    "issue", "problem", "broken", "slow",
    "expensive", "annoying", "anyone else",
    "does anyone", "how do i", "why does",
    "can't", "cannot", "won't", "doesn't work",
    "need help", "looking for", "recommendations",
    "alternative", "manual", "tedious", "waste",
    "hours", "every month", "pain", "tired of",
    "sick of", "wish there was", "dream of",
]


def _compose_post_text(post):
    """Combine the post fields we actually scrape across platforms."""
    return " ".join(
        str(part).strip()
        for part in (
            post.get("title", ""),
            post.get("body", ""),
            post.get("selftext", ""),
            post.get("full_text", ""),
        )
        if str(part).strip()
    )


def _normalized_market_source(post):
    """Normalize raw scraper sources for market-card display."""
    source = (post.get("source", "") or "").strip().lower()
    if source.startswith("reddit"):
        return "reddit"
    return source


def is_pain_post(post):
    text = _compose_post_text(post).lower()
    return any(keyword in text for keyword in MARKET_PAIN_KEYWORDS)


def pain_score(post):
    text = _compose_post_text(post).lower()
    return sum(1 for keyword in MARKET_PAIN_KEYWORDS if keyword in text)


def _engagement_score(post):
    return int(post.get("score", 0) or 0) + int(post.get("num_comments", 0) or 0)


def build_top_posts_for_topic(posts):
    """
    Select topic posts for the Market page by pain relevance first, then engagement.
    """
    if not posts:
        return []

    deduped = {}
    for post in posts:
        key = post.get("external_id") or post.get("permalink") or post.get("url") or post.get("title")
        if key and key not in deduped:
            deduped[key] = post

    ranked_posts = sorted(
        deduped.values(),
        key=lambda post: (pain_score(post), _engagement_score(post)),
        reverse=True,
    )
    pain_posts = [post for post in ranked_posts if is_pain_post(post)]

    selected = list(pain_posts[:5])
    if len(selected) < 3:
        for post in sorted(deduped.values(), key=_engagement_score, reverse=True):
            key = post.get("external_id") or post.get("permalink") or post.get("url") or post.get("title")
            if key and all(
                key != (picked.get("external_id") or picked.get("permalink") or picked.get("url") or picked.get("title"))
                for picked in selected
            ):
                selected.append(post)
            if len(selected) >= 5:
                break

    available_sources = []
    for post in ranked_posts:
        source = _normalized_market_source(post)
        if source and source not in available_sources:
            available_sources.append(source)

    def _rank_tuple(post):
        return (pain_score(post), _engagement_score(post))

    selected = selected[:5]
    for source in available_sources:
        if source in {_normalized_market_source(post) for post in selected}:
            continue

        replacement = next((post for post in ranked_posts if _normalized_market_source(post) == source), None)
        if not replacement:
            continue

        if len(selected) < 5:
            selected.append(replacement)
            continue

        selected_counts = Counter(_normalized_market_source(post) for post in selected)
        replace_index = None
        weakest_rank = None
        for index, post in enumerate(selected):
            post_source = _normalized_market_source(post)
            if selected_counts.get(post_source, 0) <= 1:
                continue
            current_rank = _rank_tuple(post)
            if weakest_rank is None or current_rank < weakest_rank:
                weakest_rank = current_rank
                replace_index = index

        if replace_index is not None:
            selected[replace_index] = replacement

    selected.sort(key=_rank_tuple, reverse=True)

    return [{
        "title": (post.get("title", "") or "")[:200],
        "source": _normalized_market_source(post),
        "subreddit": post.get("subreddit", ""),
        "score": int(post.get("score", 0) or 0),
        "comments": int(post.get("num_comments", 0) or 0),
        "url": post.get("permalink") or post.get("url") or "",
        "pain_score": pain_score(post),
    } for post in selected[:5]]


def store_posts(rows):
    """Persist raw posts so Realtime, alerts, and trend aggregation have live data."""
    if not SUPABASE_URL or not rows:
        return 0

    payload = []
    for post in rows[:2000]:
        external_id = post.get("external_id") or post.get("id") or hashlib.md5(
            f"{post.get('source', 'unknown')}::{post.get('title', '')}".encode("utf-8", errors="ignore")
        ).hexdigest()
        payload.append({
            "id": f"{post.get('source', 'src')}_{external_id}",
            "title": post.get("title", "")[:500],
            "selftext": (post.get("body") or post.get("selftext") or "")[:5000],
            "full_text": (post.get("full_text") or post.get("title") or "")[:8000],
            "score": int(post.get("score", 0) or 0),
            "upvote_ratio": float(post.get("upvote_ratio", 0.5) or 0.5),
            "num_comments": int(post.get("num_comments", 0) or 0),
            "created_utc": _to_iso_datetime(post.get("created_utc")),
            "subreddit": post.get("subreddit", ""),
            "permalink": post.get("permalink", ""),
            "author": post.get("author", ""),
            "url": post.get("url", post.get("permalink", "")),
            "matched_phrases": post.get("matched_keywords", post.get("matched_phrases", [])) or [],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        })

    saved = 0
    for row in payload:
        resp = sb_upsert("posts", [row], on_conflict="id")
        if resp.status_code < 400:
            saved += 1
    return saved


def update_validation_scores(new_posts):
    """Small market-pulse confidence nudges for recent completed validations."""
    if not SUPABASE_URL or not new_posts:
        return 0

    recent_validations = sb_select(
        "idea_validations",
        "select=id,confidence,created_at,report&status=eq.done&order=created_at.desc&limit=100",
    )
    now = datetime.now(timezone.utc)
    updated = 0

    for validation in recent_validations:
        created_at = validation.get("created_at", "")
        try:
            created_dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except Exception:
            continue
        if created_dt < now - timedelta(days=30):
            continue

        report = validation.get("report") or {}
        if isinstance(report, str):
            try:
                report = json.loads(report)
            except Exception:
                report = {}

        keywords = report.get("keywords") or report.get("extracted_keywords") or []
        if not keywords:
            continue

        new_matches = 0
        for post in new_posts:
            haystack = f"{post.get('title', '')} {post.get('full_text', '')} {post.get('body', '')}".lower()
            if any(str(keyword).lower() in haystack for keyword in keywords[:5]):
                new_matches += 1

        if new_matches >= 3:
            adjustment = min(3.0, new_matches * 0.5)
        elif new_matches == 0:
            adjustment = -0.5
        else:
            adjustment = 0.0

        if adjustment == 0:
            continue

        current_conf = float(report.get("confidence", validation.get("confidence", 50)) or 50)
        new_conf = max(35.0, min(85.0, current_conf + adjustment))
        report["confidence"] = int(new_conf)
        report["market_pulse"] = {
            "previous_confidence": round(current_conf, 1),
            "current_confidence": int(new_conf),
            "delta": round(new_conf - current_conf, 1),
            "new_matches": new_matches,
            "last_updated_at": now.isoformat(),
        }
        resp = sb_patch("idea_validations", f"id=eq.{validation['id']}", {
            "confidence": int(new_conf),
            "report": report,
        })
        if resp.status_code < 400:
            updated += 1
            direction = "+" if new_conf >= current_conf else ""
            print(f"  [Pulse] {validation['id']}: {current_conf}% -> {new_conf}% ({direction}{new_conf - current_conf:.1f}, {new_matches} new matches)")

    return updated


# ═══════════════════════════════════════════════════════
# SCRAPING (REUSES EXISTING ENGINE SCRAPERS)
# ═══════════════════════════════════════════════════════

def scrape_reddit_sub(subreddit, sort="new", limit=100):
    """Scrape one subreddit via public .json API."""
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    headers = {"User-Agent": random.choice(USER_AGENTS), "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, params={"limit": limit, "raw_json": 1}, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    posts = []
    for child in data.get("data", {}).get("children", []):
        if child.get("kind") != "t3":
            continue
        d = child["data"]
        if d.get("removed_by_category") or d.get("selftext") in ("[removed]", "[deleted]"):
            continue

        full_text = f"{d.get('title', '')} {d.get('selftext', '')[:3000]}".strip()
        if len(full_text) < 20:
            continue
        if any(p.search(full_text) for p in _spam_re):
            continue
        if sum(1 for p in _humor_re if p.search(full_text)) >= 2:
            continue

        posts.append({
            "source": "reddit",
            "external_id": d.get("id", ""),
            "subreddit": d.get("subreddit", ""),
            "title": d.get("title", ""),
            "body": d.get("selftext", "")[:3000],
            "full_text": full_text,
            "author": d.get("author", ""),
            "score": d.get("score", 0),
            "num_comments": d.get("num_comments", 0),
            "created_utc": d.get("created_utc", 0),
            "permalink": f"https://reddit.com{d.get('permalink', '')}",
        })
    return posts


def scrape_all_reddit(subreddits=None):
    """Scrape all target subreddits."""
    all_posts = []
    seen = set()
    for sub in (subreddits or BASE_SUBREDDITS):
        for sort in ("new", "hot"):
            posts = scrape_reddit_sub(sub, sort, limit=100)
            for p in posts:
                key = p["external_id"]
                if key not in seen:
                    seen.add(key)
                    all_posts.append(p)
            time.sleep(2.5)  # respect rate limits
        print(f"    r/{sub}: {len([p for p in all_posts if p.get('subreddit') == sub])} posts")
    return all_posts


def scrape_hn():
    """Scrape recent Hacker News posts for live trend detection."""
    try:
        from hn_scraper import search_hn_recent

        raw = []
        seen_ids = set()
        keywords = ["startup", "saas", "tool", "problem", "frustrated", "alternative", "invoice", "automation"]

        for keyword in keywords:
            keyword_posts = search_hn_recent(keyword, hits_per_page=100)
            added = 0
            for post in keyword_posts:
                post_id = str(post.get("id", post.get("objectID", "")))
                if not post_id or post_id in seen_ids:
                    continue
                seen_ids.add(post_id)
                raw.append(post)
                added += 1
            print(f"    [HN live] '{keyword}': +{added} recent posts (total {len(raw)})")

        # Normalize to our format
        posts = []
        for p in raw:
            posts.append({
                "source": "hackernews",
                "external_id": str(p.get("id", p.get("objectID", ""))),
                "subreddit": "",
                "title": p.get("title", ""),
                "body": p.get("selftext", p.get("story_text", ""))[:3000],
                "full_text": p.get("full_text", p.get("title", "")),
                "author": p.get("author", ""),
                "score": p.get("score", p.get("points", 0)),
                "num_comments": p.get("num_comments", 0),
                "created_utc": p.get("created_utc", 0),
                "permalink": p.get("permalink", p.get("url", "")),
            })
        return posts
    except Exception as e:
        print(f"    [!] HN scrape failed: {e}")
        return []


def scrape_ph():
    """Scrape ProductHunt."""
    try:
        from ph_scraper import run_ph_scrape
        raw = run_ph_scrape(["saas", "tool", "automation", "freelance", "invoice"])
        posts = []
        for p in raw:
            posts.append({
                "source": "producthunt",
                "external_id": str(p.get("id", "")),
                "subreddit": "",
                "title": p.get("title", ""),
                "body": p.get("selftext", "")[:3000],
                "full_text": p.get("full_text", p.get("title", "")),
                "author": p.get("author", ""),
                "score": p.get("score", 0),
                "num_comments": p.get("num_comments", 0),
                "created_utc": p.get("created_utc", 0),
                "permalink": p.get("permalink", ""),
            })
        return posts
    except Exception as e:
        print(f"    [!] PH scrape failed: {e}")
        return []


def scrape_ih():
    """Scrape IndieHackers."""
    try:
        from ih_scraper import run_ih_scrape
        raw = run_ih_scrape(["problem", "struggling", "tool", "expensive", "alternative", "frustrated"])
        posts = []
        for p in raw:
            posts.append({
                "source": "indiehackers",
                "external_id": str(p.get("id", "")),
                "subreddit": "",
                "title": p.get("title", ""),
                "body": p.get("selftext", "")[:3000],
                "full_text": p.get("full_text", p.get("title", "")),
                "author": p.get("author", ""),
                "score": p.get("score", 0),
                "num_comments": p.get("num_comments", 0),
                "created_utc": p.get("created_utc", 0),
                "permalink": p.get("permalink", ""),
            })
        return posts
    except Exception as e:
        print(f"    [!] IH scrape failed: {e}")
        return []


# ═══════════════════════════════════════════════════════
# TOPIC CLUSTERING — Group posts into ideas
# ═══════════════════════════════════════════════════════

# Pre-defined opportunity topics to track (45 topics, 10+ keywords each)
TRACKED_TOPICS = {
    # ══════ FINTECH ══════
    "invoice-automation": {
        "keywords": ["invoice", "invoicing", "billing", "payment automation", "accounts receivable",
                     "billing software", "send invoice", "overdue payment", "bill client", "payment reminder",
                     "stripe billing", "recurring invoice"],
        "category": "fintech",
    },
    "accounting-software": {
        "keywords": ["accounting", "bookkeeping", "quickbooks", "xero", "tax software", "expense tracking",
                     "profit and loss", "balance sheet", "tax filing", "tax return", "financial report",
                     "expense report", "receipt", "accountant", "cpa", "p&l"],
        "category": "fintech",
    },
    "payment-processing": {
        "keywords": ["payment processing", "stripe", "payment gateway", "subscription billing",
                     "recurring payments", "paypal", "square", "merchant account", "checkout",
                     "payment integration", "credit card processing", "payment link"],
        "category": "fintech",
    },
    "personal-finance": {
        "keywords": ["personal finance", "budget app", "budgeting", "savings", "debt tracker",
                     "net worth", "financial planning", "money management", "expense tracker",
                     "financial goal", "spending tracker", "mint alternative"],
        "category": "fintech",
    },

    # ══════ PRODUCTIVITY ══════
    "time-tracking": {
        "keywords": ["time tracking", "time tracker", "toggl", "clockify", "harvest", "track hours",
                     "billable hours", "timesheet", "pomodoro", "time management", "track time",
                     "work hours", "productivity timer"],
        "category": "productivity",
    },
    "project-management": {
        "keywords": ["project management", "task management", "asana", "notion", "clickup", "trello",
                     "jira", "monday.com", "to-do", "todo", "kanban", "project board", "task list",
                     "workflow", "sprint", "scrum", "agile", "backlog"],
        "category": "productivity",
    },
    "note-taking": {
        "keywords": ["note taking", "notes app", "obsidian", "notion", "evernote", "roam research",
                     "logseq", "note-taking", "second brain", "knowledge base", "zettelkasten",
                     "personal wiki", "markdown editor"],
        "category": "productivity",
    },
    "document-signing": {
        "keywords": ["document signing", "esignature", "docusign", "contract signing", "digital signature",
                     "e-sign", "sign document", "contract management", "pdf sign", "electronic signature",
                     "agreement", "nda"],
        "category": "productivity",
    },
    "forms-surveys": {
        "keywords": ["form builder", "survey", "typeform", "google forms", "questionnaire", "feedback form",
                     "contact form", "registration form", "survey tool", "poll", "quiz maker",
                     "tally", "jotform"],
        "category": "productivity",
    },
    "scheduling-booking": {
        "keywords": ["scheduling", "booking", "appointment", "calendly", "cal.com", "calendar booking",
                     "meeting scheduler", "book a call", "time slot", "availability", "schedule meeting",
                     "reservation", "booking system", "appointment booking"],
        "category": "productivity",
    },
    "ai-meeting-notes": {
        "keywords": ["meeting notes", "ai notes", "meeting transcription", "otter", "fireflies",
                     "meeting summary", "ai assistant", "meeting recording", "transcript",
                     "call recording", "ai notetaker", "automatic notes"],
        "category": "ai",
    },

    # ══════ MARKETING ══════
    "email-marketing": {
        "keywords": ["email marketing", "newsletter", "mailchimp", "convertkit", "email automation",
                     "drip campaign", "email sequence", "email list", "cold email", "email outreach",
                     "open rate", "click rate", "substack", "beehiiv", "email blast"],
        "category": "marketing",
    },
    "seo-tools": {
        "keywords": ["seo", "search engine optimization", "keyword research", "backlinks", "ahrefs",
                     "semrush", "google ranking", "organic traffic", "search ranking", "domain authority",
                     "serp", "link building", "on-page seo", "technical seo", "keyword tool"],
        "category": "marketing",
    },
    "social-media-scheduling": {
        "keywords": ["social media scheduler", "social media management", "hootsuite", "buffer",
                     "content calendar", "social media posting", "schedule posts", "social media tool",
                     "instagram scheduler", "twitter scheduler", "linkedin posting",
                     "social media analytics", "later", "sprout social"],
        "category": "marketing",
    },
    "landing-pages": {
        "keywords": ["landing page", "landing page builder", "conversion", "carrd", "leadpages",
                     "squeeze page", "sales page", "opt-in page", "landing page template",
                     "conversion rate", "a/b testing", "split test", "unbounce", "instapage"],
        "category": "marketing",
    },
    "content-creation": {
        "keywords": ["content creation", "blog post", "copywriting", "content writer", "ghostwriter",
                     "article writing", "content strategy", "content marketing", "blog tool",
                     "writing tool", "content calendar", "editorial", "brand voice"],
        "category": "marketing",
    },
    "influencer-marketing": {
        "keywords": ["influencer", "influencer marketing", "brand deal", "sponsorship", "ugc",
                     "user generated content", "creator economy", "brand ambassador", "collab",
                     "micro-influencer", "creator", "tiktok marketing", "instagram marketing"],
        "category": "marketing",
    },

    # ══════ DEV TOOLS ══════
    "no-code-tools": {
        "keywords": ["no-code", "nocode", "low-code", "bubble", "webflow", "without coding",
                     "no code", "zapier", "make.com", "airtable", "retool", "appsmith",
                     "visual builder", "drag and drop", "citizen developer"],
        "category": "dev-tools",
    },
    "api-monitoring": {
        "keywords": ["api monitoring", "uptime", "status page", "downtime", "alerting",
                     "uptime monitoring", "website monitoring", "server monitoring", "incident",
                     "pagerduty", "better uptime", "health check", "ping", "latency"],
        "category": "dev-tools",
    },
    "website-builder": {
        "keywords": ["website builder", "squarespace", "wix", "web design", "portfolio site",
                     "wordpress", "build website", "no code website", "website template",
                     "static site", "web hosting", "domain", "site builder"],
        "category": "dev-tools",
    },
    "ci-cd-devops": {
        "keywords": ["ci/cd", "devops", "deployment", "docker", "kubernetes", "github actions",
                     "pipeline", "continuous integration", "continuous deployment", "terraform",
                     "infrastructure", "cloud", "aws", "vercel", "netlify", "railway"],
        "category": "dev-tools",
    },
    "developer-tools": {
        "keywords": ["developer tool", "dev tool", "vscode", "ide", "code editor", "debugger",
                     "linter", "formatter", "git", "github", "open source", "sdk", "cli tool",
                     "terminal", "shell", "api client", "postman"],
        "category": "dev-tools",
    },

    # ══════ AI ══════
    "ai-writing": {
        "keywords": ["ai writing", "ai content", "chatgpt", "gpt writing", "ai copywriting",
                     "ai text", "ai blog", "ai email", "jasper ai", "ai assistant",
                     "llm", "openai", "claude", "gemini", "ai tool", "gpt-4", "gpt4"],
        "category": "ai",
    },
    "ai-image-generation": {
        "keywords": ["ai image", "midjourney", "dall-e", "stable diffusion", "ai art",
                     "image generation", "ai design", "text to image", "ai photo",
                     "generative ai", "ai graphics", "ai avatar"],
        "category": "ai",
    },
    "ai-automation": {
        "keywords": ["ai automation", "automate with ai", "ai workflow", "ai agent",
                     "autonomous agent", "ai bot", "ai scraper", "ai data entry",
                     "intelligent automation", "rpa", "process automation"],
        "category": "ai",
    },
    "ai-coding": {
        "keywords": ["ai coding", "copilot", "ai code", "code completion", "cursor ai",
                     "ai programming", "ai developer", "code generation", "ai ide",
                     "ai pair programming", "devin", "ai software engineer"],
        "category": "ai",
    },

    # ══════ SAAS ══════
    "customer-support": {
        "keywords": ["customer support", "help desk", "ticketing", "zendesk", "intercom", "live chat",
                     "support ticket", "customer service", "helpdesk", "freshdesk", "chatbot",
                     "knowledge base", "faq", "support tool", "customer success"],
        "category": "saas",
    },
    "crm-tools": {
        "keywords": ["crm", "client management", "client tracking", "pipeline", "hubspot",
                     "salesforce", "deal tracking", "lead management", "customer relationship",
                     "contact management", "sales pipeline", "sales tool", "prospecting"],
        "category": "saas",
    },
    "onboarding-tools": {
        "keywords": ["onboarding", "user onboarding", "product tour", "walkthrough", "activation",
                     "welcome flow", "getting started", "setup wizard", "first time user",
                     "product adoption", "feature adoption", "in-app guide"],
        "category": "saas",
    },
    "feedback-tools": {
        "keywords": ["feedback", "user feedback", "feature request", "roadmap", "changelog",
                     "product feedback", "customer feedback", "nps", "canny", "productboard",
                     "upvote", "feature voting", "beta testing"],
        "category": "saas",
    },

    # ══════ ECOMMERCE ══════
    "ecommerce-tools": {
        "keywords": ["ecommerce", "e-commerce", "shopify", "dropshipping", "online store", "woocommerce",
                     "shopify app", "shopify theme", "print on demand", "product listing",
                     "product photos", "supplier", "wholesale", "dtc", "direct to consumer",
                     "amazon seller", "amazon fba", "fulfillment"],
        "category": "ecommerce",
    },
    "inventory-management": {
        "keywords": ["inventory", "stock management", "warehouse", "supply chain", "fulfillment",
                     "inventory tracking", "order management", "sku", "barcode", "shipment",
                     "logistics", "3pl", "shipping software", "order fulfillment"],
        "category": "ecommerce",
    },

    # ══════ HR ══════
    "recruitment-hiring": {
        "keywords": ["hiring", "recruitment", "applicant tracking", "job posting", "talent acquisition",
                     "ats", "interview", "candidate", "job board", "resume", "cv",
                     "recruiter", "hr software", "onboarding employee", "payroll"],
        "category": "hr",
    },
    "remote-work-tools": {
        "keywords": ["remote work", "remote team", "distributed team", "work from home", "wfh",
                     "async work", "remote collaboration", "virtual office", "team communication",
                     "slack alternative", "remote culture", "hybrid work", "coworking"],
        "category": "hr",
    },

    # ══════ SECURITY ══════
    "vpn-privacy": {
        "keywords": ["vpn", "privacy", "online privacy", "encrypted", "anonymous browsing",
                     "password manager", "2fa", "two factor", "security tool", "cyber security",
                     "data breach", "malware", "antivirus", "firewall", "identity theft"],
        "category": "security",
    },

    # ══════ DATA ══════
    "data-analytics": {
        "keywords": ["analytics", "data visualization", "metabase", "mixpanel", "google analytics",
                     "amplitude", "data dashboard", "business intelligence", "bi tool", "reporting",
                     "data pipeline", "etl", "data warehouse", "sql", "tableau", "chart"],
        "category": "data",
    },
    "web-scraping": {
        "keywords": ["web scraping", "scraper", "scrape data", "web crawler", "data extraction",
                     "automation", "puppeteer", "playwright", "selenium", "beautifulsoup",
                     "parse website", "extract data", "apify"],
        "category": "data",
    },

    # ══════ EDUCATION ══════
    "online-courses": {
        "keywords": ["online course", "course creator", "teachable", "udemy", "skillshare",
                     "learn online", "e-learning", "lms", "create course", "sell course",
                     "course platform", "membership site", "cohort based"],
        "category": "saas",
    },

    # ══════ FREELANCE ══════
    "freelance-tools": {
        "keywords": ["freelance", "freelancer", "client", "proposal", "scope creep",
                     "hourly rate", "retainer", "upwork", "fiverr", "agency", "consulting",
                     "contract", "freelance income", "side gig", "independent contractor"],
        "category": "saas",
    },

    # ══════ REAL ESTATE ══════
    "proptech": {
        "keywords": ["real estate", "rental", "tenant", "property", "mortgage", "landlord",
                     "airbnb", "property management", "lease", "real estate investing",
                     "rental income", "property manager", "vacation rental"],
        "category": "fintech",
    },

    # ══════ DESIGN ══════
    "design-tools": {
        "keywords": ["design tool", "figma", "canva", "graphic design", "ui design", "ux design",
                     "logo maker", "brand kit", "design system", "prototype", "mockup",
                     "wireframe", "illustration", "photo editor"],
        "category": "dev-tools",
    },

    # ══════ COMMUNICATION ══════
    "video-conferencing": {
        "keywords": ["video call", "zoom", "video conferencing", "google meet", "teams",
                     "screen share", "webinar", "virtual meeting", "video chat",
                     "conference call", "video recording", "loom", "screen recording"],
        "category": "saas",
    },
}

# ── Subreddit-to-category mapping for dynamic topic discovery ──
SUBREDDIT_CATEGORIES = {
    "smallbusiness": "saas", "Entrepreneur": "saas", "startups": "saas",
    "SaaS": "saas", "sidehustle": "saas", "indiehackers": "saas",
    "microsaas": "saas", "EntrepreneurRideAlong": "saas", "sweatystartup": "saas",
    "ecommerce": "ecommerce", "shopify": "ecommerce", "dropship": "ecommerce",
    "FulfillmentByAmazon": "ecommerce", "AmazonSeller": "ecommerce",
    "freelance": "saas", "freelanceWriters": "saas", "graphic_design": "dev-tools",
    "web_design": "dev-tools", "Upwork": "saas",
    "marketing": "marketing", "SEO": "marketing", "PPC": "marketing",
    "socialmedia": "marketing", "emailmarketing": "marketing",
    "ContentCreators": "marketing", "juststart": "marketing",
    "webdev": "dev-tools", "devops": "dev-tools", "selfhosted": "dev-tools",
    "nocode": "dev-tools", "ProductManagement": "saas",
    "cscareerquestions": "dev-tools", "learnprogramming": "dev-tools",
    "Accounting": "fintech", "realestateinvesting": "fintech",
    "tax": "fintech", "legaladvice": "saas",
    "digitalnomad": "hr", "remotework": "hr", "WorkOnline": "hr",
    "artificial": "ai", "MachineLearning": "ai", "analytics": "data",
}


def classify_post_to_topics(post):
    """Match a post to one or more tracked topics. Returns list of topic slugs."""
    text = _compose_post_text(post).lower()
    subreddit = (post.get("subreddit", "") or "").lower().strip()
    subreddit_text = subreddit.replace("_", " ").replace("-", " ")
    combined_text = f"{subreddit_text} {text}".strip()
    source = _normalized_market_source(post)
    subreddit_category = SUBREDDIT_CATEGORIES.get(subreddit, "")
    matches = []

    for slug, topic_info in TRACKED_TOPICS.items():
        score = 0
        phrase_hit = False
        keyword_hits = 0
        for keyword in topic_info["keywords"]:
            normalized = keyword.lower().strip()
            if not normalized:
                continue
            if " " in normalized or "-" in normalized or "/" in normalized:
                if normalized in combined_text:
                    score += 2
                    phrase_hit = True
                    keyword_hits += 1
            elif re.search(rf"\b{re.escape(normalized)}\b", combined_text):
                score += 1
                keyword_hits += 1

        if (
            source == "reddit"
            and subreddit_category
            and subreddit_category == topic_info.get("category")
            and (keyword_hits > 0 or is_pain_post(post))
        ):
            # Reddit complaints often use category-native buyer language in body text.
            score += 1

        if phrase_hit or score >= 2:
            matches.append((slug, score))

    # Sort by match score, return top 2 strongest themes.
    matches.sort(key=lambda x: x[1], reverse=True)
    return [match[0] for match in matches[:2]]


# ═══════════════════════════════════════════════════════
# SCORE CALCULATOR — The price formula
# ═══════════════════════════════════════════════════════

def calculate_idea_score(topic_slug, posts, signal_posts=None, existing_idea=None):
    """
    Calculate the live score (0-100) for an idea topic.
    
    Score = (
        reddit_velocity      * 0.30 +
        google_trend_growth  * 0.25 +
        cross_platform_score * 0.25 +
        engagement_signal    * 0.20
    )
    """
    signal_posts = signal_posts or posts

    if not posts or not signal_posts:
        return 0.0, {}

    now = time.time()
    twenty_four_hours_ago = now - 86400
    seven_days_ago = now - 7 * 86400
    thirty_days_ago = now - 30 * 86400

    # Parse timestamps
    post_count_24h = sum(1 for post in signal_posts if _post_activity_timestamp(post) > twenty_four_hours_ago)

    # ── Velocity (how many posts in last 7 days vs previous) ──
    recent_count = sum(1 for post in signal_posts if _post_activity_timestamp(post) > seven_days_ago)
    older_count = sum(
        1 for post in signal_posts
        if seven_days_ago >= _post_activity_timestamp(post) > thirty_days_ago
    )

    if older_count > 0:
        velocity_ratio = recent_count / older_count
    else:
        velocity_ratio = min(recent_count, 5)

    velocity_score = min(velocity_ratio * 15, 100)

    # ── Cross-platform (how many different sources) ──
    source_breakdown = _build_source_breakdown(signal_posts)
    source_names = [item["platform"] for item in source_breakdown]
    source_count = len(source_breakdown)
    cross_platform_multipliers = {1: 1.0, 2: 1.5, 3: 2.2, 4: 3.0}
    cp_mult = cross_platform_multipliers.get(source_count, 3.0)
    cross_platform_score = min(source_count * 25 * cp_mult / 3.0, 100)

    # ── Engagement (avg upvotes + comments) ──
    total_engagement = sum(p.get("score", 0) + p.get("num_comments", 0) for p in signal_posts)
    avg_engagement = total_engagement / max(len(signal_posts), 1)
    engagement_score = min(math.log(avg_engagement + 1) / 7.0 * 100, 100)

    # ── Pain signal (how many match pain phrases) ──
    pain_count = 0
    for p in signal_posts:
        text_lower = (p.get("full_text", "") or "").lower()
        if any(phrase.lower() in text_lower for phrase in PAIN_PHRASES[:20]):
            pain_count += 1
    pain_ratio = pain_count / max(len(signal_posts), 1)
    pain_boost = pain_ratio * 20

    # ── Volume bonus (more data = more confident) ──
    volume_bonus = min(math.log(len(signal_posts) + 1) / math.log(500) * 15, 15)

    # ── Final score ──
    raw_score = (
        velocity_score * 0.30 +
        cross_platform_score * 0.25 +
        engagement_score * 0.25 +
        pain_boost * 0.10 +
        volume_bonus * 0.10
    )

    final_score = max(0, min(100, round(raw_score, 1)))

    breakdown = {
        "velocity": round(velocity_score, 1),
        "cross_platform": round(cross_platform_score, 1),
        "engagement": round(engagement_score, 1),
        "pain_signal": round(pain_boost, 1),
        "volume_bonus": round(volume_bonus, 1),
        "source_count": source_count,
        "sources": source_breakdown,
        "source_names": source_names,
        "post_count_24h": post_count_24h,
        "post_count_7d": recent_count,
        "post_count_total": len(signal_posts),
        "pain_count": pain_count,
    }

    return final_score, breakdown


def determine_trend(current, previous_24h, previous_7d):
    """Determine trend direction from score history."""
    if previous_7d == 0 and previous_24h == 0:
        return "new"

    if previous_7d > 0:
        change_7d = current - previous_7d
        if change_7d > 5:
            return "rising"
        elif change_7d < -5:
            return "falling"

    if previous_24h > 0:
        change_24h = current - previous_24h
        if change_24h > 2:
            return "rising"
        elif change_24h < -2:
            return "falling"

    return "stable"


def determine_confidence(post_count, source_count):
    """Determine confidence level based on evidence thresholds (relaxed)."""
    if post_count < 5:
        return "INSUFFICIENT"
    elif post_count < 15:
        return "LOW"
    elif post_count < 50:
        if source_count >= 2:
            return "MEDIUM"
        return "LOW"
    elif post_count < 150:
        if source_count >= 2:
            return "HIGH"
        return "MEDIUM"
    else:
        if source_count >= 3:
            return "STRONG"
        return "HIGH"


# ═══════════════════════════════════════════════════════
# MAIN JOB
# ═══════════════════════════════════════════════════════

def run_scraper_job(sources=None, topic_filter=None, mode="full", source_label="local"):
    """
    Run the full scraper pipeline:
    1. Scrape all sources
    2. Cluster posts into ideas
    3. Calculate scores
    4. Upsert to Supabase
    """
    start_time = time.time()
    run_id = None
    sources = sources or ["reddit", "hackernews", "producthunt", "indiehackers"]
    if mode == "quick":
        sources = [source for source in sources if source in {"reddit", "hackernews"}]
    elif mode == "trends":
        sources = [source for source in sources if source in {"reddit", "hackernews", "producthunt"}]

    print("=" * 60)
    print("  Opportunity Engine — Scraper Job")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Sources: {', '.join(sources)}")
    print(f"  Mode: {mode}")
    print(f"  Caller: {source_label}")
    print("=" * 60)

    # Log run start
    if SUPABASE_URL:
        resp = sb_upsert("scraper_runs", [{
            "source": ",".join(sources),
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }])
        if resp.status_code < 400:
            data = resp.json()
            if data:
                run_id = data[0].get("id")

    # ── 1. Scrape (4-Layer Architecture) ──
    all_posts = []
    all_post_map = {}
    live_posts = []
    live_ids = set()
    historical_ids = set()

    def _merge(new_posts, bucket="live"):
        """Deduplicate and merge posts into all_posts."""
        added = 0
        for p in new_posts:
            eid = p.get("external_id", "")
            if not eid:
                continue

            if not p.get("scraped_at"):
                p["scraped_at"] = datetime.now(timezone.utc).isoformat()

            if eid not in all_post_map:
                all_post_map[eid] = p
                all_posts.append(p)
                added += 1

            canonical = all_post_map[eid]
            if bucket == "live":
                if eid not in live_ids:
                    live_ids.add(eid)
                    live_posts.append(canonical)
            elif bucket == "historical":
                if eid not in historical_ids and eid not in live_ids:
                    historical_ids.add(eid)
        return added

    all_subs = load_user_requested_subreddits()

    if "reddit" in sources:
        # ── Layer 1: Async Reddit JSON API (~15s for 42 subs) ──
        print("\n  [1/6] Layer 1 — Async Reddit scrape...")
        try:
            from reddit_async import scrape_all_async
            reddit_posts = asyncio.run(scrape_all_async(subreddits=all_subs))
            added = _merge(reddit_posts, bucket="live")
            print(f"  [OK] Layer 1 (async): {added} fresh posts")
            if added < 10:
                print("  [!] Layer 1 async returned too few posts - retrying with sync scraper")
                reddit_posts = scrape_all_reddit(subreddits=all_subs)
                added = _merge(reddit_posts, bucket="live")
                print(f"  [OK] Layer 1 (sync recovery): +{added} posts")
        except Exception as e:
            print(f"  [!] Layer 1 async failed, falling back to sync: {e}")
            reddit_posts = scrape_all_reddit(subreddits=all_subs)
            added = _merge(reddit_posts, bucket="live")
            print(f"  [OK] Layer 1 (sync fallback): {added} posts")

        # ── Layer 2: PullPush.io Historical (90 days back) ──
        print("\n  [2/6] Layer 2 — PullPush historical scrape...")
        try:
            from pullpush_scraper import scrape_historical_multi
            pp_posts = scrape_historical_multi(subreddits=all_subs, days_back=90, size_per_sub=100, delay=0.5)
            added = _merge(pp_posts, bucket="historical")
            print(f"  [OK] Layer 2 (PullPush): +{added} historical posts")
        except Exception as e:
            print(f"  [!] Layer 2 (PullPush) skipped: {e}")

        # ── Layer 3: Reddit Sitemap (real-time discovery) ──
        print("\n  [3/6] Layer 3 — Sitemap real-time discovery...")
        try:
            from sitemap_listener import discover_new_posts
            sitemap_posts = discover_new_posts(max_fetch=30)
            added = _merge(sitemap_posts, bucket="live")
            print(f"  [OK] Layer 3 (sitemap): +{added} newly discovered posts")
        except Exception as e:
            print(f"  [!] Layer 3 (sitemap) skipped: {e}")

        # ── Layer 4: PRAW authenticated (optional) ──
        try:
            from reddit_auth import is_available as praw_available, scrape_all_authenticated
            if praw_available():
                print("\n  [3.5/6] Layer 4 — PRAW authenticated deep dive...")
                praw_posts = scrape_all_authenticated(all_subs[:10], sorts=["rising"])
                added = _merge(praw_posts, bucket="live")
                print(f"  [OK] Layer 4 (PRAW): +{added} authenticated posts")
        except Exception as e:
            pass  # PRAW is optional, silent skip

    if "hackernews" in sources:
        print("\n  [4/6] Scraping Hacker News...")
        hn_posts = scrape_hn()
        _merge(hn_posts, bucket="live")
        print(f"  [OK] HN: {len(hn_posts)} posts")

    if "producthunt" in sources:
        print("\n  [5/6] Scraping ProductHunt...")
        ph_posts = scrape_ph()
        _merge(ph_posts, bucket="live")
        print(f"  [OK] PH: {len(ph_posts)} posts")

    if "indiehackers" in sources:
        print("\n  [6/6] Scraping IndieHackers...")
        ih_posts = scrape_ih()
        _merge(ih_posts, bucket="live")
        print(f"  [OK] IH: {len(ih_posts)} posts")

    print(f"\n  Total posts scraped (deduplicated): {len(all_posts)}")
    print(f"  Live signal corpus: {len(live_posts)} posts")
    print(f"  Historical support corpus: {len(historical_ids)} posts")

    if not all_posts:
        print("  [!] No posts collected — exiting")
        if run_id:
            sb_patch("scraper_runs", f"id=eq.{run_id}", {
                "status": "failed", "error_text": "No posts collected",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": round(time.time() - start_time, 1),
            })
        return

    if SUPABASE_URL:
        try:
            saved_posts = store_posts(all_posts)
            print(f"  [OK] Stored {saved_posts} raw posts in Supabase")
        except Exception as e:
            print(f"  [Posts] Raw post storage skipped: {e}")

        try:
            alert_matches = check_alerts_against_posts(all_posts)
            if alert_matches:
                print(f"  [PainStream] {alert_matches} new alert matches created")
        except Exception as e:
            print(f"  [PainStream] Alert check skipped: {e}")

        try:
            all_known_competitors = []
            for competitor_list in KNOWN_COMPETITORS.values():
                all_known_competitors.extend(competitor_list)
            complaints = scan_for_complaints(all_posts, all_known_competitors)
            if complaints:
                saved_complaints = save_complaints(complaints)
                print(f"  [Deathwatch] {saved_complaints} competitor pain signals saved")
        except Exception as e:
            print(f"  [Deathwatch] Scan skipped: {e}")

        try:
            aggregate_trends(posts=all_posts, select_fn=sb_select, patch_fn=sb_patch, upsert_fn=sb_upsert)
        except Exception as e:
            print(f"  [Trends] Aggregation skipped: {e}")

        try:
            pulse_updates = update_validation_scores(all_posts)
            if pulse_updates:
                print(f"  [Pulse] Updated {pulse_updates} active validations")
        except Exception as e:
            print(f"  [Pulse] Score updates skipped: {e}")

    # ── 2. Cluster posts → ideas ──
    signal_posts = live_posts if live_posts else all_posts

    print("\n  Clustering posts into idea topics...")
    idea_posts = defaultdict(list)
    signal_posts_by_topic = defaultdict(list)

    for post in all_posts:
        topics = classify_post_to_topics(post)
        for topic in topics:
            idea_posts[topic].append(post)

    for post in signal_posts:
        topics = classify_post_to_topics(post)
        for topic in topics:
            signal_posts_by_topic[topic].append(post)

    # Filter by topic if specified
    if topic_filter:
        idea_posts = {k: v for k, v in idea_posts.items() if k in topic_filter}
        signal_posts_by_topic = {k: v for k, v in signal_posts_by_topic.items() if k in topic_filter}

    active_topic_posts = signal_posts_by_topic if signal_posts_by_topic else idea_posts
    matched_ideas = len(active_topic_posts)
    matched_posts = sum(len(v) for v in active_topic_posts.values())
    print(f"  [OK] {matched_posts} live-signal posts matched into {matched_ideas} idea topics")

    # ── 3. Load existing ideas from Supabase ──
    existing_ideas = {}
    if SUPABASE_URL:
        rows = sb_select("ideas", "select=*")
        for row in rows:
            existing_ideas[row["slug"]] = row
    idea_optional_columns = {
        "post_count_24h": table_has_column("ideas", "post_count_24h"),
        "pain_count": table_has_column("ideas", "pain_count"),
        "pain_summary": table_has_column("ideas", "pain_summary"),
        "last_24h_update": table_has_column("ideas", "last_24h_update"),
        "last_7d_update": table_has_column("ideas", "last_7d_update"),
    }

    # ── 4. Calculate scores + upsert ──
    print("\n  Calculating idea scores...")
    ideas_to_upsert = []
    history_to_insert = []
    ideas_updated = 0

    for slug, signal_bucket in active_topic_posts.items():
        posts = idea_posts.get(slug, signal_bucket)
        topic_info = TRACKED_TOPICS.get(slug, {})

        # Handle dynamic topics (sub-<subreddit> from unmatched posts)
        if slug.startswith("sub-"):
            subreddit_name = slug[4:]
            topic_name = f"{subreddit_name.replace('_', ' ').title()} Opportunities"
            # Get category from subreddit mapping
            category = SUBREDDIT_CATEGORIES.get(subreddit_name, "general")
            topic_info = {"category": category, "keywords": [subreddit_name]}
        else:
            topic_name = slug.replace("-", " ").title()

        score, breakdown = calculate_idea_score(
            slug,
            posts,
            signal_posts=signal_bucket,
        )
        existing = existing_ideas.get(slug)
        now_utc = datetime.now(timezone.utc)

        # Roll baselines forward only when their time window has elapsed.
        baselines = _resolve_score_baselines(existing, now_utc)
        prev_24h = baselines["prev_24h"]
        prev_7d = baselines["prev_7d"]
        prev_30d = baselines["prev_30d"]

        trend = determine_trend(score, prev_24h, prev_7d)
        confidence = determine_confidence(len(posts), breakdown.get("source_count", 1))

        # Only skip if truly insufficient (< 3 posts) AND doesn't already exist
        if len(posts) < 3 and not existing:
            continue

        top_posts_json = build_top_posts_for_topic(posts)
        pain_summary, pain_count = _build_pain_summary(posts, topic_name)

        idea_row = {
            "topic": topic_name,
            "slug": slug,
            "current_score": score,
            "score_24h_ago": baselines["next_score_24h_ago"],
            "score_7d_ago": baselines["next_score_7d_ago"],
            "score_30d_ago": baselines["next_score_30d_ago"],
            "change_24h": round(score - prev_24h, 1) if prev_24h > 0 else 0,
            "change_7d": round(score - prev_7d, 1) if prev_7d > 0 else 0,
            "change_30d": round(score - prev_30d, 1) if prev_30d > 0 else 0,
            "trend_direction": trend,
            "confidence_level": confidence,
            "post_count_total": len(posts),
            "post_count_7d": breakdown.get("post_count_7d", 0),
            "source_count": breakdown.get("source_count", 1),
            "sources": json.dumps(breakdown.get("sources", [])),
            "reddit_velocity": breakdown.get("velocity", 0),
            "cross_platform_multiplier": breakdown.get("cross_platform", 0),
            "competition_score": 0,
            "category": topic_info.get("category", "general"),
            "top_posts": json.dumps(top_posts_json),
            "keywords": json.dumps(topic_info.get("keywords", [])),
            "last_updated": now_utc.isoformat(),
        }

        if idea_optional_columns["post_count_24h"]:
            idea_row["post_count_24h"] = breakdown.get("post_count_24h", 0)
        if idea_optional_columns["pain_count"]:
            idea_row["pain_count"] = pain_count or breakdown.get("pain_count", 0)
        if idea_optional_columns["pain_summary"] and pain_summary:
            idea_row["pain_summary"] = pain_summary
        if idea_optional_columns["last_24h_update"]:
            idea_row["last_24h_update"] = baselines["next_last_24h_update"]
        if idea_optional_columns["last_7d_update"]:
            idea_row["last_7d_update"] = baselines["next_last_7d_update"]

        ideas_to_upsert.append(idea_row)
        ideas_updated += 1

        # History record
        history_to_insert.append({
            "score": score,
            "post_count": len(posts),
            "source_count": breakdown.get("source_count", 1),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })

        tier_icon = {"INSUFFICIENT": "---", "LOW": " . ", "MEDIUM": " o ", "HIGH": " O ", "STRONG": " @ "}
        trend_icon = {"rising": "+", "falling": "-", "stable": "=", "new": "*"}
        print(f"    [{tier_icon.get(confidence, '?')}] {slug:30s} {score:5.1f} {trend_icon.get(trend, '?')} ({len(posts)} posts, {breakdown.get('source_count',1)} sources)")

    # ── 5. Upsert to Supabase ──
    if SUPABASE_URL and ideas_to_upsert:
        print(f"\n  Uploading {len(ideas_to_upsert)} ideas to Supabase...")

        # Upsert ideas (use slug as conflict key)
        idea_upsert_successes = 0
        idea_upsert_failures = []
        for idea in ideas_to_upsert:
            resp = sb_upsert("ideas", [idea], on_conflict="slug")
            if resp.status_code < 400:
                idea_upsert_successes += 1
            else:
                idea_upsert_failures.append(idea["slug"])

        # Insert history (need idea_ids)
        updated_ideas = sb_select("ideas", "select=id,slug")
        slug_to_id = {r["slug"]: r["id"] for r in updated_ideas}

        history_successes = 0
        history_failures = []
        for i, hist in enumerate(history_to_insert):
            slug = ideas_to_upsert[i]["slug"]
            idea_id = slug_to_id.get(slug)
            if idea_id:
                hist["idea_id"] = idea_id
                history_resp = sb_upsert("idea_history", [hist])
                if history_resp.status_code < 400:
                    history_successes += 1
                else:
                    history_failures.append(slug)
            else:
                history_failures.append(slug)

        if idea_upsert_failures:
            print(f"  [!] Idea upsert failures: {', '.join(idea_upsert_failures[:8])}")
        if history_failures:
            print(f"  [!] Idea history failures: {', '.join(history_failures[:8])}")

        print(
            f"  [OK] {idea_upsert_successes}/{len(ideas_to_upsert)} ideas upserted + "
            f"{history_successes}/{len(history_to_insert)} history records"
        )

    # ── 6. Update run log ──
    duration = round(time.time() - start_time, 1)
    if run_id and SUPABASE_URL:
        run_status = "completed" if not (SUPABASE_URL and ideas_to_upsert and idea_upsert_failures) else "completed_errors"
        error_text = None
        if SUPABASE_URL and ideas_to_upsert and idea_upsert_failures:
            error_text = f"Idea upsert failures: {', '.join(idea_upsert_failures[:8])}"
        sb_patch("scraper_runs", f"id=eq.{run_id}", {
            "status": run_status,
            "posts_collected": len(all_posts),
            "ideas_updated": ideas_updated,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": duration,
            "error_text": error_text,
        })

    if SUPABASE_URL:
        print("\n  Running database cleanup...")
        sb_rpc("cleanup_old_posts")

    print(f"\n{'=' * 60}")
    print(f"  Done! {len(all_posts)} posts -> {ideas_updated} ideas updated")
    print(f"  Duration: {duration}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Opportunity Engine — Scraper Job")
    parser.add_argument("--sources", nargs="+", default=None,
                        choices=["reddit", "hackernews", "producthunt", "indiehackers"],
                        help="Which sources to scrape")
    parser.add_argument("--topics", type=str, default=None,
                        help="Comma-separated topic slugs to update (e.g. 'invoice-automation,crm-for-freelancers')")
    parser.add_argument("--mode", default="full", choices=["full", "trends", "quick"])
    parser.add_argument("--source", default="local", help="Caller identifier for logging")
    args = parser.parse_args()

    topic_filter = None
    if args.topics:
        topic_filter = [t.strip() for t in args.topics.split(",")]

    try:
        run_scraper_job(
            sources=args.sources,
            topic_filter=topic_filter,
            mode=args.mode,
            source_label=args.source,
        )
    except Exception as e:
        print(f"\n  [FATAL] {e}")
        traceback.print_exc()
