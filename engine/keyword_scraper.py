"""
RedditPulse — Keyword-Based Reddit Scraper
Searches Reddit for user-specified keywords across all relevant subreddits.
Supports timed scans (10min, 1h, 10h, 48h) with continuous collection.
"""

import re
import time
import random
import requests
from datetime import datetime

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

# Duration mapping (seconds)
DURATIONS = {
    "10min": 10 * 60,
    "1h": 60 * 60,
    "10h": 10 * 60 * 60,
    "48h": 48 * 60 * 60,
}

# Spam/low-quality filters
SPAM_PATTERNS = [
    r"\b(check out my|subscribe to|use my code|affiliate|referral link)\b",
    r"\b(buy now|limited time|discount code|promo code)\b",
    r"\[removed\]|\[deleted\]",
]
_spam_re = [re.compile(p, re.IGNORECASE) for p in SPAM_PATTERNS]


def _headers():
    return {"User-Agent": random.choice(USER_AGENTS), "Accept": "application/json"}


def search_reddit(keywords: list, after: str = "", limit: int = 100) -> list:
    """
    Search Reddit globally for keywords.
    Returns list of post dicts.
    """
    query = " OR ".join(f'"{kw}"' if " " in kw else kw for kw in keywords)
    url = "https://www.reddit.com/search.json"
    params = {
        "q": query,
        "sort": "new",
        "limit": min(limit, 100),
        "raw_json": 1,
        "t": "month",  # last month
    }
    if after:
        params["after"] = after

    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        if resp.status_code == 429:
            print("    [!] Rate limited, waiting 10s...")
            time.sleep(10)
            return [], ""
        if resp.status_code != 200:
            print(f"    [x] Search returned {resp.status_code}")
            return [], ""
        return resp.json().get("data", {}).get("children", []), resp.json().get("data", {}).get("after", "")
    except Exception as e:
        print(f"    [x] Search error: {e}")
        return [], ""


def search_subreddit(subreddit: str, keywords: list, after: str = "", limit: int = 100):
    """Search within a specific subreddit."""
    query = " OR ".join(f'"{kw}"' if " " in kw else kw for kw in keywords)
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    params = {
        "q": query,
        "sort": "new",
        "limit": min(limit, 100),
        "restrict_sr": "true",
        "raw_json": 1,
        "t": "month",
    }
    if after:
        params["after"] = after

    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        if resp.status_code == 429:
            time.sleep(10)
            return [], ""
        if resp.status_code != 200:
            return [], ""
        data = resp.json().get("data", {})
        return data.get("children", []), data.get("after", "")
    except Exception as e:
        print(f"    [x] r/{subreddit} search error: {e}")
        return [], ""


def _parse_post(child: dict, keywords: list) -> dict:
    """Parse a Reddit API post child into our format."""
    if child.get("kind") != "t3":
        return None
    d = child["data"]

    # Skip removed/deleted
    if d.get("removed_by_category") or d.get("selftext") in ("[removed]", "[deleted]"):
        return None

    full_text = f"{d.get('title', '')} {d.get('selftext', '')[:3000]}".strip()

    # Spam filter
    if any(pat.search(full_text) for pat in _spam_re):
        return None
    if len(full_text) < 30:
        return None

    # Which keywords matched
    text_lower = full_text.lower()
    matched_kw = [kw for kw in keywords if kw.lower() in text_lower]

    return {
        "id": d.get("id", ""),
        "title": d.get("title", ""),
        "selftext": d.get("selftext", "")[:3000],
        "full_text": full_text,
        "score": d.get("score", 0),
        "upvote_ratio": d.get("upvote_ratio", 0.5),
        "num_comments": d.get("num_comments", 0),
        "created_utc": datetime.utcfromtimestamp(d.get("created_utc", 0)).isoformat() + "Z",
        "subreddit": d.get("subreddit", ""),
        "permalink": "https://reddit.com" + d.get("permalink", ""),
        "author": d.get("author", "[deleted]"),
        "url": d.get("url", ""),
        "matched_keywords": matched_kw,
    }


# ═══════════════════════════════════════════════════════
# RELEVANT BUSINESS SUBREDDITS TO SEARCH
# ═══════════════════════════════════════════════════════
BUSINESS_SUBREDDITS = [
    "SaaS", "Entrepreneur", "smallbusiness", "startups",
    "webdev", "marketing", "ecommerce", "freelance",
    "shopify", "digitalnomad", "Accounting", "ContentCreators",
    "sideproject", "microsaas", "indiehackers",
]


def run_keyword_scan(keywords: list, duration: str = "10min", on_progress=None):
    """
    Run a keyword scan for the specified duration.
    
    Args:
        keywords: list of search terms
        duration: "10min", "1h", "10h", "48h"
        on_progress: callback(posts_found, status_message) for live updates
    
    Returns:
        list of unique posts found
    """
    max_seconds = DURATIONS.get(duration, 600)
    start_time = time.time()
    seen_ids = set()
    all_posts = []

    print(f"  [>] Scanning for: {keywords}")
    print(f"  [>] Duration: {duration} ({max_seconds}s)")

    # ── Phase 1: Global Reddit search ──
    if on_progress:
        on_progress(0, "Searching Reddit globally...")

    after = ""
    for page in range(5):  # Max 5 pages = 500 results from global
        if time.time() - start_time > max_seconds:
            break

        result = search_reddit(keywords, after=after)
        if isinstance(result, tuple):
            children, after = result
        else:
            children, after = result, ""

        for child in children:
            post = _parse_post(child, keywords)
            if post and post["id"] not in seen_ids:
                seen_ids.add(post["id"])
                all_posts.append(post)

        if on_progress:
            on_progress(len(all_posts), f"Global search page {page+1}: {len(all_posts)} posts")
        
        if not after:
            break
        time.sleep(2.5)

    # ── Phase 2: Async subreddit-specific searches ──
    if on_progress:
        on_progress(len(all_posts), "Async scanning subreddits...")

    try:
        import asyncio
        import sys
        import os
        sys.path.insert(0, os.path.dirname(__file__))
        from reddit_async import scrape_all_async, AIOHTTP_AVAILABLE

        if AIOHTTP_AVAILABLE:
            async_posts = asyncio.run(scrape_all_async(
                subreddits=BUSINESS_SUBREDDITS,
                sorts=["new"],
                max_concurrent=6,
            ))
            for post_data in async_posts:
                # Re-check keyword match
                text_lower = post_data.get("full_text", "").lower()
                matched_kw = [kw for kw in keywords if kw.lower() in text_lower]
                if matched_kw and post_data.get("external_id") not in seen_ids:
                    seen_ids.add(post_data["external_id"])
                    post_data["matched_keywords"] = matched_kw
                    # Adapt fields to keyword_scraper format
                    post_data["id"] = post_data.get("external_id", "")
                    post_data["selftext"] = post_data.get("body", "")
                    post_data["permalink"] = post_data.get("permalink", "")
                    all_posts.append(post_data)

            if on_progress:
                on_progress(len(all_posts), f"Async scan done: {len(all_posts)} posts")
        else:
            raise ImportError("aiohttp not available")
    except Exception as e:
        # Fallback to sequential
        print(f"    [!] Async unavailable ({e}), using sequential scan")
        for sub in BUSINESS_SUBREDDITS:
            if time.time() - start_time > max_seconds:
                break
            if on_progress:
                on_progress(len(all_posts), f"Searching r/{sub}...")
            children, _ = search_subreddit(sub, keywords)
            new_count = 0
            for child in children:
                post = _parse_post(child, keywords)
                if post and post["id"] not in seen_ids:
                    seen_ids.add(post["id"])
                    all_posts.append(post)
                    new_count += 1
            if new_count > 0:
                print(f"    r/{sub}: +{new_count} posts (total: {len(all_posts)})")
            time.sleep(2.5)

    # ── Phase 2.5: PullPush.io historical backfill ──
    if on_progress:
        on_progress(len(all_posts), "Fetching historical data (PullPush)...")

    try:
        from pullpush_scraper import scrape_historical
        query = " ".join(keywords[:3])  # Top 3 keywords for historical search
        for sub in BUSINESS_SUBREDDITS[:8]:  # Top 8 subs for historical depth
            if time.time() - start_time > max_seconds:
                break
            pp_posts = scrape_historical(sub, keyword=query, days_back=90, size=50)
            new_count = 0
            for post_data in pp_posts:
                eid = post_data.get("external_id", "")
                if eid and eid not in seen_ids:
                    text_lower = post_data.get("full_text", "").lower()
                    matched_kw = [kw for kw in keywords if kw.lower() in text_lower]
                    if matched_kw:
                        seen_ids.add(eid)
                        post_data["id"] = eid
                        post_data["matched_keywords"] = matched_kw
                        post_data["selftext"] = post_data.get("body", "")
                        all_posts.append(post_data)
                        new_count += 1
            if new_count > 0:
                print(f"    [PP] r/{sub}: +{new_count} historical posts")
            time.sleep(0.5)

        if on_progress:
            on_progress(len(all_posts), f"Historical backfill done: {len(all_posts)} posts")
    except Exception as e:
        print(f"    [!] PullPush backfill skipped: {e}")

    # ── Phase 3: If long scan, keep polling for new posts ──
    if max_seconds > 600:
        cycle = 0
        while time.time() - start_time < max_seconds:
            cycle += 1
            elapsed = int(time.time() - start_time)
            remaining = max_seconds - elapsed

            if on_progress:
                on_progress(len(all_posts), f"Cycle {cycle} — {len(all_posts)} posts, {remaining}s remaining")

            # Re-search global for new posts
            children, _ = search_reddit(keywords)
            new_this_cycle = 0
            for child in (children if isinstance(children, list) else []):
                post = _parse_post(child, keywords)
                if post and post["id"] not in seen_ids:
                    seen_ids.add(post["id"])
                    all_posts.append(post)
                    new_this_cycle += 1

            if new_this_cycle > 0:
                print(f"    Cycle {cycle}: +{new_this_cycle} new posts (total: {len(all_posts)})")

            # Wait between cycles (longer for longer scans)
            wait = min(60, remaining)  # Check every 60s max
            time.sleep(wait)

    elapsed = int(time.time() - start_time)
    print(f"\n  [OK] Scan complete: {len(all_posts)} posts in {elapsed}s")

    if on_progress:
        on_progress(len(all_posts), "Scan complete!")

    return all_posts


# ═══════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    posts = run_keyword_scan(
        keywords=["invoice tool", "invoicing software"],
        duration="10min",
    )
    print(f"\nFound {len(posts)} posts")
    for p in posts[:5]:
        print(f"  [{p['score']}⬆] r/{p['subreddit']} — {p['title'][:80]}")
