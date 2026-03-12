"""
RedditPulse — PRAW Authenticated Reddit Scraper (Layer 4)
Uses Reddit's official API via PRAW for authenticated access.
100 req/min (vs ~10/min anonymous). Optional — falls back to Layer 1 if no credentials.

Setup:
    1. Go to https://www.reddit.com/prefs/apps
    2. Create a "script" app
    3. Set env vars: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET

Usage:
    from reddit_auth import search_authenticated, scrape_sub_authenticated
    posts = search_authenticated(["invoice", "billing"], subreddit="SaaS")
"""

import os
import time
from datetime import datetime

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = "RedditPulse/1.0 (opportunity intelligence)"


def _get_reddit() -> "praw.Reddit | None":
    """Create a PRAW Reddit instance if credentials are available."""
    if not PRAW_AVAILABLE:
        return None
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        return None

    try:
        return praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
        )
    except Exception as e:
        print(f"    [PRAW] Init failed: {e}")
        return None


def is_available() -> bool:
    """Check if authenticated Reddit access is available."""
    return PRAW_AVAILABLE and bool(REDDIT_CLIENT_ID) and bool(REDDIT_CLIENT_SECRET)


def _submission_to_post(submission) -> dict:
    """Convert a PRAW Submission object to our normalized post format."""
    selftext = (submission.selftext or "")[:3000]
    full_text = f"{submission.title} {selftext}".strip()

    return {
        "source": "reddit",
        "external_id": submission.id,
        "subreddit": str(submission.subreddit),
        "title": submission.title,
        "body": selftext,
        "full_text": full_text,
        "author": str(submission.author) if submission.author else "[deleted]",
        "score": submission.score,
        "num_comments": submission.num_comments,
        "created_utc": submission.created_utc,
        "permalink": f"https://reddit.com{submission.permalink}",
    }


def search_authenticated(
    keywords: list[str],
    subreddit: str = "",
    sort: str = "new",
    time_filter: str = "month",
    limit: int = 100,
) -> list[dict]:
    """
    Search Reddit using authenticated API (100 req/min).

    Args:
        keywords: search terms
        subreddit: specific subreddit (empty = all)
        sort: "new", "hot", "top", "relevance"
        time_filter: "hour", "day", "week", "month", "year", "all"
        limit: max results (up to 250 per query)

    Returns:
        list of normalized post dicts
    """
    reddit = _get_reddit()
    if not reddit:
        return []

    query = " OR ".join(f'"{kw}"' if " " in kw else kw for kw in keywords)

    try:
        if subreddit:
            sub = reddit.subreddit(subreddit)
            results = sub.search(query, sort=sort, time_filter=time_filter, limit=limit)
        else:
            results = reddit.subreddit("all").search(query, sort=sort, time_filter=time_filter, limit=limit)

        posts = []
        for submission in results:
            post = _submission_to_post(submission)
            if len(post["full_text"]) >= 20:
                posts.append(post)

        print(f"    [PRAW] Search '{query[:40]}': {len(posts)} posts")
        return posts

    except Exception as e:
        print(f"    [PRAW] Search error: {e}")
        return []


def scrape_sub_authenticated(
    subreddit: str,
    sort: str = "new",
    limit: int = 100,
) -> list[dict]:
    """
    Scrape a subreddit using authenticated API.

    Args:
        subreddit: subreddit name
        sort: "new", "hot", "top", "rising"
        limit: max posts

    Returns:
        list of normalized post dicts
    """
    reddit = _get_reddit()
    if not reddit:
        return []

    try:
        sub = reddit.subreddit(subreddit)
        if sort == "new":
            submissions = sub.new(limit=limit)
        elif sort == "hot":
            submissions = sub.hot(limit=limit)
        elif sort == "top":
            submissions = sub.top(time_filter="month", limit=limit)
        elif sort == "rising":
            submissions = sub.rising(limit=limit)
        else:
            submissions = sub.new(limit=limit)

        posts = [_submission_to_post(s) for s in submissions if len(s.title) > 5]
        print(f"    [PRAW] r/{subreddit}/{sort}: {len(posts)} posts")
        return posts

    except Exception as e:
        print(f"    [PRAW] r/{subreddit} error: {e}")
        return []


def scrape_all_authenticated(
    subreddits: list[str],
    sorts: list[str] | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    Scrape multiple subreddits using authenticated API.
    Much faster than anonymous — no 2.5s delay needed.
    """
    reddit = _get_reddit()
    if not reddit:
        return []

    sort_modes = sorts or ["new", "hot"]
    seen = set()
    all_posts = []
    start = time.time()

    print(f"  [PRAW] Authenticated scrape: {len(subreddits)} subs × {len(sort_modes)} sorts")

    for sub in subreddits:
        for sort in sort_modes:
            posts = scrape_sub_authenticated(sub, sort, limit)
            for post in posts:
                if post["external_id"] not in seen:
                    seen.add(post["external_id"])
                    all_posts.append(post)
            time.sleep(0.6)  # 100 req/min = 1.67 per sec, stay safe at 0.6s

    elapsed = time.time() - start
    print(f"  [PRAW] Done: {len(all_posts)} unique posts in {elapsed:.1f}s")
    return all_posts


# ═══════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  PRAW Authenticated Scraper — Test")
    print("=" * 60)

    if not is_available():
        print("\n  ⚠ PRAW not available. Set env vars:")
        print("    REDDIT_CLIENT_ID=your_client_id")
        print("    REDDIT_CLIENT_SECRET=your_client_secret")
        print("\n  To register: https://www.reddit.com/prefs/apps")
        print("  (Create a 'script' type app)")
    else:
        print("\n  ✅ PRAW available — testing authenticated access")
        posts = search_authenticated(["invoice", "billing"], subreddit="SaaS", limit=10)
        print(f"\n  Search results: {len(posts)} posts")
        for p in posts[:3]:
            print(f"    [{p['score']}⬆] r/{p['subreddit']} — {p['title'][:60]}")
