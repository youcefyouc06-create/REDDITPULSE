"""
RedditPulse — Reddit Sitemap Listener (Layer 3)
Polls Reddit's XML sitemaps to discover brand new posts the moment
they're indexed — before they appear in Reddit search results.

Usage:
    from sitemap_listener import get_recent_post_urls, filter_relevant_urls
    urls = get_recent_post_urls()
    relevant = filter_relevant_urls(urls, TARGET_SUBREDDITS)
"""

import re
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

from config import TARGET_SUBREDDITS

SITEMAP_URL = "https://www.reddit.com/sitemaps/recent.xml"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

# Cache to avoid re-processing already-seen URLs
_seen_urls: set = set()
_MAX_CACHE = 10000


def get_recent_post_urls() -> list[str]:
    """
    Fetch Reddit's recent sitemap and extract all post URLs.
    Returns list of URLs like 'https://www.reddit.com/r/SaaS/comments/abc123/...'
    """
    try:
        resp = requests.get(
            SITEMAP_URL,
            headers={"User-Agent": "RedditPulse/1.0 (research tool)"},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"    [SITEMAP] HTTP {resp.status_code}")
            return []

        root = ET.fromstring(resp.content)

        # Check if this is a sitemap index (points to sub-sitemaps)
        sitemap_urls = [loc.text for loc in root.findall(f".//{NS}loc")]

        # If these are sub-sitemaps, fetch them too
        post_urls = []
        for url in sitemap_urls:
            if "/comments/" in url:
                post_urls.append(url)
            elif url.endswith(".xml"):
                # It's a sub-sitemap, fetch it
                try:
                    sub_resp = requests.get(
                        url,
                        headers={"User-Agent": "RedditPulse/1.0"},
                        timeout=10,
                    )
                    if sub_resp.status_code == 200:
                        sub_root = ET.fromstring(sub_resp.content)
                        for loc in sub_root.findall(f".//{NS}loc"):
                            if loc.text and "/comments/" in loc.text:
                                post_urls.append(loc.text)
                    time.sleep(0.5)
                except Exception:
                    continue

        return post_urls

    except Exception as e:
        print(f"    [SITEMAP] Error: {e}")
        return []


def filter_relevant_urls(
    urls: list[str],
    subreddits: list[str] | None = None,
) -> list[str]:
    """
    Filter sitemap URLs to only include posts from our target subreddits.
    Also deduplicates against previously seen URLs.
    """
    global _seen_urls

    subs = set(s.lower() for s in (subreddits or TARGET_SUBREDDITS))
    relevant = []

    # Pattern: https://www.reddit.com/r/SubName/comments/id/title/
    pattern = re.compile(r"reddit\.com/r/([^/]+)/comments/")

    for url in urls:
        if url in _seen_urls:
            continue

        match = pattern.search(url)
        if match:
            sub = match.group(1).lower()
            if sub in subs:
                relevant.append(url)
                _seen_urls.add(url)

    # Prevent cache from growing forever
    if len(_seen_urls) > _MAX_CACHE:
        _seen_urls = set(list(_seen_urls)[-(_MAX_CACHE // 2):])

    return relevant


def extract_post_ids(urls: list[str]) -> list[dict]:
    """
    Extract subreddit and post ID from sitemap URLs.
    Returns list of {subreddit, post_id, url} dicts.
    """
    pattern = re.compile(r"reddit\.com/r/([^/]+)/comments/([^/]+)")
    results = []

    for url in urls:
        match = pattern.search(url)
        if match:
            results.append({
                "subreddit": match.group(1),
                "post_id": match.group(2),
                "url": url,
            })

    return results


def fetch_post_data(post_id: str, subreddit: str) -> dict | None:
    """
    Fetch full post data for a single post by ID via Reddit JSON API.
    Used to hydrate posts discovered via sitemap.
    """
    url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json"
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "RedditPulse/1.0 (research tool)",
                "Accept": "application/json",
            },
            params={"raw_json": 1},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        if not data or not isinstance(data, list):
            return None

        post_data = data[0].get("data", {}).get("children", [{}])[0].get("data", {})
        if not post_data:
            return None

        full_text = f"{post_data.get('title', '')} {post_data.get('selftext', '')[:3000]}".strip()

        return {
            "source": "reddit",
            "external_id": post_data.get("id", post_id),
            "subreddit": post_data.get("subreddit", subreddit),
            "title": post_data.get("title", ""),
            "body": post_data.get("selftext", "")[:3000],
            "full_text": full_text,
            "author": post_data.get("author", ""),
            "score": post_data.get("score", 0),
            "num_comments": post_data.get("num_comments", 0),
            "created_utc": post_data.get("created_utc", 0),
            "permalink": f"https://reddit.com{post_data.get('permalink', '')}",
        }

    except Exception as e:
        print(f"    [SITEMAP] Fetch error for {post_id}: {e}")
        return None


def discover_new_posts(
    subreddits: list[str] | None = None,
    fetch_full: bool = True,
    max_fetch: int = 20,
) -> list[dict]:
    """
    Full sitemap discovery pipeline:
    1. Fetch sitemap URLs
    2. Filter to relevant subreddits
    3. Optionally hydrate with full post data

    Args:
        subreddits: target subreddits (default: TARGET_SUBREDDITS)
        fetch_full: whether to fetch full post data for each URL
        max_fetch: max posts to hydrate (rate limit protection)

    Returns:
        list of post dicts (or URL info dicts if fetch_full=False)
    """
    print("  [SITEMAP] Checking for new posts...")

    urls = get_recent_post_urls()
    if not urls:
        print("  [SITEMAP] No URLs found in sitemap")
        return []

    relevant = filter_relevant_urls(urls, subreddits)
    print(f"  [SITEMAP] Found {len(relevant)} new relevant posts from {len(urls)} total")

    if not fetch_full:
        return extract_post_ids(relevant)

    # Hydrate posts with full data
    posts = []
    for url_info in extract_post_ids(relevant[:max_fetch]):
        post = fetch_post_data(url_info["post_id"], url_info["subreddit"])
        if post:
            posts.append(post)
        time.sleep(0.3)  # Be nice

    print(f"  [SITEMAP] Hydrated {len(posts)} posts with full data")
    return posts


# ═══════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Reddit Sitemap Listener — Test")
    print("=" * 60)

    # Test URL discovery
    urls = get_recent_post_urls()
    print(f"\n  Total sitemap URLs: {len(urls)}")
    if urls:
        print(f"  Sample: {urls[0][:80]}...")

    # Test filtering
    relevant = filter_relevant_urls(urls)
    print(f"  Relevant (from target subs): {len(relevant)}")

    # Test full pipeline
    if relevant:
        posts = discover_new_posts(max_fetch=3)
        print(f"\n  Hydrated posts: {len(posts)}")
        for p in posts[:3]:
            print(f"    [{p['score']}⬆] r/{p['subreddit']} — {p['title'][:60]}")
