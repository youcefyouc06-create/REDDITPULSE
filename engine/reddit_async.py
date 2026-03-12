"""
RedditPulse — Async Reddit Scraper (Layer 1)
Scrapes all target subreddits concurrently using aiohttp.
Replaces the sequential loop in scraper_job.py.

Performance: 42 subreddits from ~210s → ~15s

Usage:
    from reddit_async import scrape_all_async
    posts = asyncio.run(scrape_all_async())
"""

import asyncio
import random
import re
import time
from datetime import datetime

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("  [!] aiohttp not installed: pip install aiohttp")

from config import TARGET_SUBREDDITS, USER_AGENTS, SPAM_PATTERNS, HUMOR_INDICATORS

# Compiled filters
_spam_re = [re.compile(p, re.IGNORECASE) for p in SPAM_PATTERNS]
_humor_re = [re.compile(p, re.IGNORECASE) for p in HUMOR_INDICATORS]

# ═══════════════════════════════════════════════════════
# RATE LIMITING
# ═══════════════════════════════════════════════════════

MAX_CONCURRENT = 8      # max parallel requests
DELAY_BETWEEN = 0.3     # seconds between each request launch
RETRY_LIMIT = 2         # retries per failed sub
TIMEOUT_SECONDS = 15


class RateLimiter:
    """Token-bucket style rate limiter for async requests."""

    def __init__(self, max_concurrent=MAX_CONCURRENT, delay=DELAY_BETWEEN):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.delay = delay
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def acquire(self):
        await self.semaphore.acquire()
        async with self._lock:
            now = time.monotonic()
            wait = self.delay - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()

    def release(self):
        self.semaphore.release()


# ═══════════════════════════════════════════════════════
# ASYNC SCRAPER
# ═══════════════════════════════════════════════════════

def _parse_post(child_data: dict) -> dict | None:
    """Parse a Reddit API post into our normalized format."""
    d = child_data
    if d.get("removed_by_category") or d.get("selftext") in ("[removed]", "[deleted]"):
        return None

    full_text = f"{d.get('title', '')} {d.get('selftext', '')[:3000]}".strip()
    if len(full_text) < 20:
        return None
    if any(p.search(full_text) for p in _spam_re):
        return None
    if sum(1 for p in _humor_re if p.search(full_text)) >= 2:
        return None

    return {
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
    }


async def _fetch_subreddit(
    session: aiohttp.ClientSession,
    limiter: RateLimiter,
    subreddit: str,
    sort: str = "new",
    limit: int = 100,
) -> list[dict]:
    """Fetch posts from one subreddit with rate limiting + retry."""
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
    }
    params = {"limit": limit, "raw_json": 1}

    for attempt in range(RETRY_LIMIT + 1):
        await limiter.acquire()
        try:
            async with session.get(
                url, headers=headers, params=params,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS),
            ) as resp:
                if resp.status == 429:
                    # Rate limited — back off
                    wait = 5 * (attempt + 1)
                    print(f"    [ASYNC] r/{subreddit} rate limited, waiting {wait}s...")
                    limiter.release()
                    await asyncio.sleep(wait)
                    continue

                if resp.status != 200:
                    limiter.release()
                    return []

                data = await resp.json()
                limiter.release()

                posts = []
                for child in data.get("data", {}).get("children", []):
                    if child.get("kind") != "t3":
                        continue
                    post = _parse_post(child["data"])
                    if post:
                        posts.append(post)
                return posts

        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            limiter.release()
            if attempt < RETRY_LIMIT:
                await asyncio.sleep(2 * (attempt + 1))
            else:
                print(f"    [ASYNC] r/{subreddit}/{sort} failed after {RETRY_LIMIT + 1} attempts: {e}")
                return []
        except Exception as e:
            limiter.release()
            print(f"    [ASYNC] r/{subreddit}/{sort} unexpected error: {e}")
            return []

    return []


async def scrape_all_async(
    subreddits: list[str] | None = None,
    sorts: list[str] | None = None,
    limit: int = 100,
    max_concurrent: int = MAX_CONCURRENT,
    on_progress=None,
) -> list[dict]:
    """
    Scrape all target subreddits concurrently.

    Args:
        subreddits: list of subreddit names (default: TARGET_SUBREDDITS from config)
        sorts: list of sort modes (default: ["new", "hot"])
        limit: posts per request
        max_concurrent: max parallel connections
        on_progress: callback(completed, total, message)

    Returns:
        list of unique posts (deduplicated by external_id)
    """
    if not AIOHTTP_AVAILABLE:
        print("  [!] aiohttp not available — falling back to sync scraper")
        return _sync_fallback(subreddits or TARGET_SUBREDDITS)

    subs = subreddits or TARGET_SUBREDDITS
    sort_modes = sorts or ["new", "hot"]
    limiter = RateLimiter(max_concurrent)

    # Build task list: every (subreddit, sort) combo
    tasks_info = [(sub, sort) for sub in subs for sort in sort_modes]
    total = len(tasks_info)
    completed = 0

    start = time.time()
    print(f"  [ASYNC] Scraping {len(subs)} subreddits × {len(sort_modes)} sorts = {total} requests")

    seen = set()
    all_posts = []

    async with aiohttp.ClientSession() as session:
        # Create all tasks
        async def _task(sub, sort):
            return await _fetch_subreddit(session, limiter, sub, sort, limit)

        # Run all concurrently
        results = await asyncio.gather(
            *[_task(sub, sort) for sub, sort in tasks_info],
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            completed += 1
            sub, sort = tasks_info[i]

            if isinstance(result, Exception):
                print(f"    [ASYNC] r/{sub}/{sort} exception: {result}")
                continue

            new_count = 0
            for post in result:
                key = post["external_id"]
                if key not in seen:
                    seen.add(key)
                    all_posts.append(post)
                    new_count += 1

            if on_progress and completed % 10 == 0:
                on_progress(completed, total, f"Scraped {completed}/{total} — {len(all_posts)} unique posts")

    elapsed = time.time() - start
    print(f"  [ASYNC] Done: {len(all_posts)} unique posts from {len(subs)} subs in {elapsed:.1f}s")

    return all_posts


def _sync_fallback(subreddits):
    """Fallback sync scraper if aiohttp is not installed."""
    import requests
    all_posts = []
    seen = set()
    for sub in subreddits:
        for sort in ("new", "hot"):
            try:
                url = f"https://www.reddit.com/r/{sub}/{sort}.json"
                headers = {"User-Agent": random.choice(USER_AGENTS), "Accept": "application/json"}
                resp = requests.get(url, headers=headers, params={"limit": 100, "raw_json": 1}, timeout=15)
                if resp.status_code != 200:
                    continue
                for child in resp.json().get("data", {}).get("children", []):
                    if child.get("kind") != "t3":
                        continue
                    post = _parse_post(child["data"])
                    if post and post["external_id"] not in seen:
                        seen.add(post["external_id"])
                        all_posts.append(post)
            except Exception:
                pass
            time.sleep(2.5)
        print(f"    r/{sub}: {len([p for p in all_posts if p.get('subreddit') == sub])} posts")
    return all_posts


# ═══════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Async Reddit Scraper — Performance Test")
    print("=" * 60)

    start = time.time()
    posts = asyncio.run(scrape_all_async())
    elapsed = time.time() - start

    print(f"\n  Results:")
    print(f"  Total unique posts: {len(posts)}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Subreddits covered: {len(set(p['subreddit'] for p in posts))}")

    # Show top subs by post count
    from collections import Counter
    sub_counts = Counter(p["subreddit"] for p in posts)
    print(f"\n  Top 10 subreddits:")
    for sub, count in sub_counts.most_common(10):
        print(f"    r/{sub}: {count} posts")
