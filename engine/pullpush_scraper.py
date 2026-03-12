"""
RedditPulse — PullPush.io Historical Scraper (Layer 2)
Queries historical Reddit posts (up to 90 days back) via PullPush.io.
Free API, no auth needed. Perfect for backfilling data Reddit's JSON API can't reach.

Usage:
    from pullpush_scraper import scrape_historical, scrape_historical_multi
    posts = scrape_historical("SaaS", "invoice", days_back=90)
"""

import re
import time
import requests
from datetime import datetime

from config import TARGET_SUBREDDITS, SPAM_PATTERNS, HUMOR_INDICATORS

PULLPUSH_API = "https://api.pullpush.io/reddit/search/submission/"
PULLPUSH_COMMENTS = "https://api.pullpush.io/reddit/search/comment/"

_spam_re = [re.compile(p, re.IGNORECASE) for p in SPAM_PATTERNS]
_humor_re = [re.compile(p, re.IGNORECASE) for p in HUMOR_INDICATORS]


def _parse_pullpush_post(item: dict) -> dict | None:
    """Parse a PullPush result into our normalized format."""
    title = item.get("title", "")
    selftext = item.get("selftext", "")[:3000]

    if selftext in ("[removed]", "[deleted]"):
        selftext = ""
    if item.get("removed_by_category"):
        return None

    full_text = f"{title} {selftext}".strip()
    if len(full_text) < 20:
        return None
    if any(p.search(full_text) for p in _spam_re):
        return None
    if sum(1 for p in _humor_re if p.search(full_text)) >= 2:
        return None

    return {
        "source": "reddit",
        "external_id": item.get("id", ""),
        "subreddit": item.get("subreddit", ""),
        "title": title,
        "body": selftext,
        "full_text": full_text,
        "author": item.get("author", ""),
        "score": item.get("score", 0),
        "num_comments": item.get("num_comments", 0),
        "created_utc": item.get("created_utc", 0),
        "permalink": f"https://reddit.com{item.get('permalink', '')}",
    }


def scrape_historical(
    subreddit: str,
    keyword: str = "",
    days_back: int = 90,
    size: int = 100,
    sort_type: str = "score",
    sort: str = "desc",
) -> list[dict]:
    """
    Query PullPush.io for historical Reddit posts.

    Args:
        subreddit: target subreddit name
        keyword: search term (optional)
        days_back: how far back to search (max ~180 days)
        size: results per page (max 100)
        sort_type: "score", "created_utc", "num_comments"
        sort: "asc" or "desc"

    Returns:
        list of normalized post dicts
    """
    params = {
        "subreddit": subreddit,
        "after": int(time.time()) - (days_back * 86400),
        "size": min(size, 100),
        "sort_type": sort_type,
        "sort": sort,
    }
    if keyword:
        params["q"] = keyword

    try:
        resp = requests.get(PULLPUSH_API, params=params, timeout=20)
        if resp.status_code == 429:
            print(f"    [PP] r/{subreddit} rate limited, waiting 5s...")
            time.sleep(5)
            resp = requests.get(PULLPUSH_API, params=params, timeout=20)

        if resp.status_code != 200:
            print(f"    [PP] r/{subreddit} returned {resp.status_code}")
            return []

        data = resp.json()
        items = data.get("data", [])

        posts = []
        for item in items:
            post = _parse_pullpush_post(item)
            if post:
                posts.append(post)

        return posts

    except Exception as e:
        print(f"    [PP] r/{subreddit} error: {e}")
        return []


def scrape_historical_multi(
    subreddits: list[str] | None = None,
    keywords: list[str] | None = None,
    days_back: int = 90,
    size_per_sub: int = 100,
    delay: float = 0.5,
) -> list[dict]:
    """
    Scrape historical posts across multiple subreddits.

    Args:
        subreddits: list of subreddit names (default: TARGET_SUBREDDITS)
        keywords: search terms to include (combined with OR)
        days_back: how far back to search
        size_per_sub: max posts per subreddit
        delay: seconds between requests

    Returns:
        list of unique posts (deduplicated by external_id)
    """
    subs = subreddits or TARGET_SUBREDDITS
    query = " ".join(keywords) if keywords else ""

    seen = set()
    all_posts = []
    start = time.time()

    print(f"  [PP] Historical scrape: {len(subs)} subs, {days_back} days back")

    for sub in subs:
        posts = scrape_historical(sub, keyword=query, days_back=days_back, size=size_per_sub)
        new_count = 0
        for post in posts:
            if post["external_id"] not in seen:
                seen.add(post["external_id"])
                all_posts.append(post)
                new_count += 1

        if new_count > 0:
            print(f"    [PP] r/{sub}: +{new_count} historical posts")

        time.sleep(delay)

    elapsed = time.time() - start
    print(f"  [PP] Done: {len(all_posts)} historical posts in {elapsed:.1f}s")

    return all_posts


def scrape_historical_comments(
    subreddit: str,
    keyword: str = "",
    days_back: int = 30,
    size: int = 100,
) -> list[dict]:
    """
    Query PullPush.io for historical comments (useful for WTP extraction).
    Comments often contain "I'd pay $X for this" signals that posts don't.
    """
    params = {
        "subreddit": subreddit,
        "after": int(time.time()) - (days_back * 86400),
        "size": min(size, 100),
        "sort_type": "score",
        "sort": "desc",
    }
    if keyword:
        params["q"] = keyword

    try:
        resp = requests.get(PULLPUSH_COMMENTS, params=params, timeout=20)
        if resp.status_code != 200:
            return []

        data = resp.json()
        comments = []
        for item in data.get("data", []):
            body = item.get("body", "")
            if body in ("[removed]", "[deleted]") or len(body) < 20:
                continue
            comments.append({
                "source": "reddit_comment",
                "external_id": item.get("id", ""),
                "subreddit": item.get("subreddit", ""),
                "title": "",
                "body": body[:3000],
                "full_text": body[:3000],
                "author": item.get("author", ""),
                "score": item.get("score", 0),
                "num_comments": 0,
                "created_utc": item.get("created_utc", 0),
                "permalink": f"https://reddit.com{item.get('permalink', '')}",
            })
        return comments

    except Exception as e:
        print(f"    [PP] Comments error for r/{subreddit}: {e}")
        return []


# ═══════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  PullPush.io Historical Scraper — Test")
    print("=" * 60)

    # Test single sub
    posts = scrape_historical("SaaS", keyword="invoice", days_back=90)
    print(f"\n  r/SaaS 'invoice' (90 days): {len(posts)} posts")
    for p in posts[:3]:
        print(f"    [{p['score']}⬆] {p['title'][:80]}")

    # Test multi-sub
    print("\n  Multi-sub test (5 subs, 30 days):")
    posts = scrape_historical_multi(
        subreddits=["SaaS", "Entrepreneur", "smallbusiness", "startups", "freelance"],
        days_back=30,
    )
    print(f"  Total: {len(posts)} posts")
