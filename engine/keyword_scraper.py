"""
RedditPulse — Keyword-Based Reddit Scraper
Searches Reddit for user-specified keywords across all relevant subreddits.
Supports timed scans (10min, 1h, 3h, 10h, 48h) with continuous collection.

Priority: Official Reddit API (PRAW) → Async anonymous → Sequential fallback
"""

import re
import time
import random
import requests
from collections import Counter
from datetime import datetime, timezone

# ── Try to import PRAW-based authenticated scraper ──
try:
    import os
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from reddit_auth import is_available as praw_available, search_authenticated, scrape_all_authenticated
    PRAW_IMPORTED = True
except ImportError:
    PRAW_IMPORTED = False
    praw_available = lambda: False

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
    "3h": 3 * 60 * 60,
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


def _parse_post(child: dict, keywords: list, min_keyword_matches: int = 2) -> dict:
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
    matched_kw = [kw for kw in keywords if _keyword_matches(kw, text_lower)]

    if len(matched_kw) < max(1, min_keyword_matches):
        return None

    return {
        "id": d.get("id", ""),
        "title": d.get("title", ""),
        "selftext": d.get("selftext", "")[:3000],
        "full_text": full_text,
        "score": d.get("score", 0),
        "upvote_ratio": d.get("upvote_ratio", 0.5),
        "num_comments": d.get("num_comments", 0),
        "created_utc": datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc).isoformat(),
        "subreddit": d.get("subreddit", ""),
        "permalink": "https://reddit.com" + d.get("permalink", ""),
        "author": d.get("author", "[deleted]"),
        "url": d.get("url", ""),
        "matched_keywords": matched_kw,
    }


def _keyword_matches(keyword: str, text_lower: str) -> bool:
    """
    Smart keyword matching: exact phrase match for short keywords,
    partial word-level match for longer ones.
    """
    kw_lower = keyword.lower()
    # Exact phrase match always wins
    if kw_lower in text_lower:
        return True
    # For multi-word keywords, check if enough individual words match
    words = kw_lower.split()
    if len(words) <= 1:
        return False  # single word didn't match exactly
    # For 2-3 word phrases, require at least 2 words to appear
    matching_words = sum(1 for w in words if len(w) > 2 and w in text_lower)
    return matching_words >= min(2, len(words))


# ═══════════════════════════════════════════════════════
# TOPIC-BASED SUBREDDIT MAPPING
# ═══════════════════════════════════════════════════════

# Core business subs (always searched)
CORE_SUBREDDITS = [
    "SaaS", "Entrepreneur", "smallbusiness", "startups",
    "sideproject", "microsaas", "indiehackers",
]

# Topic-specific subs — matched by keyword triggers
TOPIC_SUBREDDITS = {
    "developer": {
        "triggers": ["code", "coding", "developer", "programming", "api", "sdk",
                     "debug", "deploy", "devops", "git", "github", "CI/CD",
                     "pull request", "PR review", "code review", "testing",
                     "backend", "frontend", "fullstack", "software"],
        "subs": ["programming", "webdev", "learnprogramming", "cscareerquestions",
                 "devops", "AskProgramming", "ExperiencedDevs", "codereview",
                 "softwaredevelopment", "Frontend", "node", "reactjs", "Python",
                 "golang", "rust", "java", "csharp"],
    },
    "design": {
        "triggers": ["design", "UI", "UX", "figma", "prototype", "wireframe",
                     "branding", "logo", "graphic"],
        "subs": ["web_design", "UI_Design", "userexperience", "graphic_design",
                 "design_critiques"],
    },
    "data_ai": {
        "triggers": ["AI", "machine learning", "data", "analytics", "automation",
                     "chatbot", "NLP", "LLM", "GPT", "model", "prediction"],
        "subs": ["MachineLearning", "artificial", "datascience", "LanguageTechnology",
                 "LocalLLaMA", "ChatGPT", "OpenAI"],
    },
    "finance": {
        "triggers": ["invoice", "billing", "payment", "accounting", "fintech",
                     "bookkeeping", "payroll", "tax", "expense"],
        "subs": ["Accounting", "bookkeeping", "personalfinance", "FinancialPlanning", "fintech"],
    },
    "marketing": {
        "triggers": ["marketing", "SEO", "content", "social media", "ads",
                     "growth", "newsletter", "email", "copywriting"],
        "subs": ["marketing", "SEO", "socialmedia", "content_marketing",
                 "digital_marketing", "PPC", "emailmarketing"],
    },
    "productivity": {
        "triggers": ["productivity", "workflow", "automation", "tool", "app",
                     "project management", "task", "notion", "calendar"],
        "subs": ["productivity", "selfhosted", "Notion", "IFTTT",
                 "automation"],
    },
    "ecommerce": {
        "triggers": ["ecommerce", "shopify", "store", "product", "inventory",
                     "dropshipping", "marketplace", "selling"],
        "subs": ["ecommerce", "shopify", "FulfillmentByAmazon",
                 "Etsy", "dropship"],
    },
    "freelance": {
        "triggers": ["freelance", "client", "agency", "contract", "remote work",
                     "consulting", "upwork"],
        "subs": ["freelance", "digitalnomad", "WorkOnline",
                 "freelanceWriters"],
    },
}

ALWAYS_ADD = [
    "smallbusiness",
    "Entrepreneur",
    "startups",
]

DEV_ONLY_SUBREDDITS = {
    "MachineLearning",
    "OpenAI",
    "ChatGPT",
    "webdev",
    "selfhosted",
    "datascience",
    "LocalLLaMA",
}

DEV_TARGET_TERMS = [
    "api",
    "developer",
    "code",
    "saas platform",
    "machine learning",
    "ai model",
    "developer tool",
    "engineering",
    "programming",
    "software engineer",
]

NOISE_SUBREDDITS_FOR_NON_DEV = {
    "artificial", "languagetechnology", "machinelearning",
    "localllama", "openai", "chatgpt", "datascience",
    "learnmachinelearning", "deeplearning", "singularity",
    "adhd", "depression", "anxiety", "teenagers",
    "books", "gaming", "3dprinting", "selfhosted", "homelab",
}


def _is_dev_targeted(idea_text: str = "", keywords: list | None = None) -> bool:
    haystack = " ".join([str(idea_text or "")] + [str(kw or "") for kw in (keywords or [])]).lower()
    return any(term in haystack for term in DEV_TARGET_TERMS)


def filter_subreddits_by_icp(subreddits, icp_category):
    if icp_category == "DEV_TOOL":
        return list(subreddits or [])

    filtered = [
        sub for sub in (subreddits or [])
        if str(sub or "").strip().lower() not in NOISE_SUBREDDITS_FOR_NON_DEV
    ]
    removed = {
        str(sub).strip()
        for sub in (subreddits or [])
        if str(sub or "").strip() and str(sub or "").strip().lower() in NOISE_SUBREDDITS_FOR_NON_DEV
    }
    if removed:
        print(f"  [ICP Filter] Removed {len(removed)} noise subs for {icp_category}: {sorted(removed)}")
    return filtered


def _select_subreddits(
    keywords: list,
    forced_subreddits: list | None = None,
    idea_text: str = "",
) -> list:
    """Pick subreddits based on which topic triggers match the keywords."""
    selected = set(CORE_SUBREDDITS)
    selected.update(ALWAYS_ADD)
    kw_text = " ".join(kw.lower() for kw in keywords)
    dev_targeted = _is_dev_targeted(idea_text=idea_text, keywords=keywords)

    for topic, data in TOPIC_SUBREDDITS.items():
        for trigger in data["triggers"]:
            if trigger.lower() in kw_text:
                for sub in data["subs"]:
                    if sub in DEV_ONLY_SUBREDDITS and not dev_targeted:
                        continue
                    selected.add(sub)
                break  # one trigger match is enough

    for sub in forced_subreddits or []:
        clean = str(sub).strip().replace("r/", "").replace("/r/", "")
        if clean:
            selected.add(clean)

    result = list(selected)
    print(f"    [Subreddits] Selected {len(result)} subs for keywords: {keywords[:5]}")
    return result


def discover_subreddits(
    keywords: list,
    forced_subreddits: list | None = None,
    idea_text: str = "",
) -> list:
    """Discover additional subreddits for a keyword set beyond the core defaults."""
    selected = _select_subreddits(
        keywords,
        forced_subreddits=forced_subreddits,
        idea_text=idea_text,
    )
    extras = [sub for sub in selected if sub not in CORE_SUBREDDITS and sub not in ALWAYS_ADD]
    return extras[:20]


def run_keyword_scan(
    keywords: list,
    duration: str = "10min",
    on_progress=None,
    forced_subreddits: list | None = None,
    min_keyword_matches: int = 2,
    idea_text: str = "",
    icp_category: str = "",
    return_metadata: bool = False,
):
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

    # ── Determine scraping mode: Official API vs Anonymous ──
    use_official_api = PRAW_IMPORTED and praw_available()
    if use_official_api:
        print(f"  [Reddit] ✓ Using official API (PRAW) — 100 req/min, legally compliant")
    else:
        print(f"  [Reddit] ⚠ Using anonymous scraping — consider setting REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET")
        if not getattr(run_keyword_scan, "_proxy_warned", False):
            print("[Reddit] Using proxy rotation (legal risk — apply for API)")
            run_keyword_scan._proxy_warned = True

    print(f"  [>] Scanning for: {keywords}")
    if forced_subreddits:
        print(f"  [>] Forced subreddits: {forced_subreddits}")
    print(f"  [>] Duration: {duration} ({max_seconds}s)")

    # ── Phase 1: Global Reddit search ──
    if on_progress:
        on_progress(0, "Searching Reddit globally...")

    if use_official_api:
        # ── PRAW path: use authenticated search (fast + legal) ──
        praw_posts = search_authenticated(keywords, sort="new", time_filter="month", limit=250)
        for post_data in praw_posts:
            eid = post_data.get("external_id", post_data.get("id", ""))
            if eid and eid not in seen_ids:
                seen_ids.add(eid)
                text_lower = post_data.get("full_text", "").lower()
                matched_kw = [kw for kw in keywords if _keyword_matches(kw, text_lower)]
                if len(matched_kw) >= max(1, min_keyword_matches):
                    post_data["matched_keywords"] = matched_kw
                    post_data["id"] = eid
                    post_data["selftext"] = post_data.get("body", "")
                    all_posts.append(post_data)
        print(f"    [PRAW] Global search: {len(all_posts)} posts")
        if on_progress:
            on_progress(len(all_posts), f"Official API global search: {len(all_posts)} posts")
    else:
        # ── Anonymous path: paginated search ──
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
                post = _parse_post(child, keywords, min_keyword_matches=min_keyword_matches)
                if post and post["id"] not in seen_ids:
                    seen_ids.add(post["id"])
                    all_posts.append(post)

            if on_progress:
                on_progress(len(all_posts), f"Global search page {page+1}: {len(all_posts)} posts")
            
            if not after:
                break
            time.sleep(2.5)

    # ── Phase 2: Subreddit-specific searches ──
    try:
        selected_subs = _select_subreddits(
            keywords,
            forced_subreddits=forced_subreddits,
            idea_text=idea_text,
        )
    except TypeError:
        # Preserve compatibility with tests that monkeypatch _select_subreddits.
        selected_subs = _select_subreddits(keywords, forced_subreddits=forced_subreddits)
    selected_subs = filter_subreddits_by_icp(selected_subs, icp_category)
    if on_progress:
        on_progress(len(all_posts), f"Scanning {len(selected_subs)} subreddits...")

    if use_official_api:
        # ── PRAW path: authenticated subreddit scrape ──
        praw_sub_posts = scrape_all_authenticated(
            subreddits=selected_subs,
            sorts=["new", "hot"],
            limit=100,
        )
        for post_data in praw_sub_posts:
            eid = post_data.get("external_id", post_data.get("id", ""))
            if eid and eid not in seen_ids:
                text_lower = post_data.get("full_text", "").lower()
                matched_kw = [kw for kw in keywords if _keyword_matches(kw, text_lower)]
                if len(matched_kw) >= max(1, min_keyword_matches):
                    seen_ids.add(eid)
                    post_data["matched_keywords"] = matched_kw
                    post_data["id"] = eid
                    post_data["selftext"] = post_data.get("body", "")
                    all_posts.append(post_data)
        print(f"    [PRAW] Subreddit scan: {len(all_posts)} total posts")
        if on_progress:
            on_progress(len(all_posts), f"Official API subreddit scan done: {len(all_posts)} posts")
    else:
        # ── Anonymous path: async or sequential ──
        try:
            import asyncio
            import sys as _sys
            import os as _os
            _sys.path.insert(0, _os.path.dirname(__file__))
            from reddit_async import scrape_all_async, AIOHTTP_AVAILABLE

            if AIOHTTP_AVAILABLE:
                async_posts = asyncio.run(scrape_all_async(
                    subreddits=selected_subs,
                    sorts=["new"],
                    max_concurrent=6,
                ))
                for post_data in async_posts:
                    text_lower = post_data.get("full_text", "").lower()
                    matched_kw = [kw for kw in keywords if _keyword_matches(kw, text_lower)]
                    if len(matched_kw) >= max(1, min_keyword_matches) and post_data.get("external_id") not in seen_ids:
                        seen_ids.add(post_data["external_id"])
                        post_data["matched_keywords"] = matched_kw
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
            for sub in selected_subs:
                if time.time() - start_time > max_seconds:
                    break
                if on_progress:
                    on_progress(len(all_posts), f"Searching r/{sub}...")
                children, _ = search_subreddit(sub, keywords)
                new_count = 0
                for child in children:
                    post = _parse_post(child, keywords, min_keyword_matches=min_keyword_matches)
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
        for sub in selected_subs[:12]:  # Top 12 selected subs for historical depth
            if time.time() - start_time > max_seconds:
                break
            pp_posts = scrape_historical(sub, keyword=query, days_back=90, size=50)
            new_count = 0
            for post_data in pp_posts:
                eid = post_data.get("external_id", "")
                if eid and eid not in seen_ids:
                    text_lower = post_data.get("full_text", "").lower()
                    matched_kw = [kw for kw in keywords if _keyword_matches(kw, text_lower)]
                    if len(matched_kw) >= max(1, min_keyword_matches):
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
                post = _parse_post(child, keywords, min_keyword_matches=min_keyword_matches)
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

    if return_metadata:
        subreddit_post_counts = Counter(
            str(p.get("subreddit") or "").strip().lower().replace("r/", "").replace("/r/", "")
            for p in all_posts
            if str(p.get("subreddit") or "").strip()
        )
        return {
            "posts": all_posts,
            "selected_subreddits": [
                str(sub).strip().lower().replace("r/", "").replace("/r/", "")
                for sub in selected_subs
                if str(sub).strip()
            ],
            "subreddit_post_counts": dict(sorted(subreddit_post_counts.items())),
        }

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
