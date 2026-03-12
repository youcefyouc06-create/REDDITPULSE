"""
RedditPulse — GitHub Issues Scraper
Finds open issues with most 👍 reactions on repos related to a topic.
Uses the free GitHub API (60 req/hour unauthenticated, 5K/hour with token).
"""

import os
import time
import math
import requests
from datetime import datetime
from pathlib import Path

# Load .env from project root
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


GH_API = "https://api.github.com"
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")

def _headers():
    """Build headers, optionally including auth token."""
    h = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "RedditPulse-Enrichment/1.0",
    }
    if GH_TOKEN:
        h["Authorization"] = f"token {GH_TOKEN}"
    return h


# Map idea topics to GitHub search queries and popular repos
TOPIC_REPO_MAP = {
    "invoice-automation": {
        "search": "invoice OR invoicing OR billing",
        "repos": ["invoiceninja/invoiceninja", "crater-invoice/crater", "killbill/killbill"],
    },
    "accounting-software": {
        "search": "accounting OR bookkeeping",
        "repos": ["akaunting/akaunting", "frappe/erpnext", "ledgersmb/LedgerSMB"],
    },
    "project-management": {
        "search": "project management OR task management",
        "repos": ["makeplane/plane", "AppFlowy-IO/AppFlowy", "toeverything/AFFiNE"],
    },
    "note-taking": {
        "search": "note taking OR knowledge base",
        "repos": ["logseq/logseq", "siyuan-note/siyuan", "joplinapp/joplin"],
    },
    "no-code-tools": {
        "search": "no-code OR low-code OR visual builder",
        "repos": ["appwrite/appwrite", "nocodb/nocodb", "n8n-io/n8n"],
    },
    "ai-writing": {
        "search": "AI writing OR LLM writing OR GPT content",
        "repos": ["open-webui/open-webui", "mckaywrigley/chatbot-ui"],
    },
    "ai-coding": {
        "search": "AI code generation OR code assistant",
        "repos": ["continuedev/continue", "TabbyML/tabby", "paul-gauthier/aider"],
    },
    "ai-automation": {
        "search": "AI agent OR autonomous agent OR AI automation",
        "repos": ["Significant-Gravitas/AutoGPT", "langchain-ai/langchain"],
    },
    "customer-support": {
        "search": "helpdesk OR customer support OR ticketing",
        "repos": ["chatwoot/chatwoot", "freescout-helpdesk/freescout"],
    },
    "crm-tools": {
        "search": "CRM OR customer relationship",
        "repos": ["twentyhq/twenty", "SuiteCRM/SuiteCRM", "erxes/erxes"],
    },
    "ecommerce-tools": {
        "search": "ecommerce OR online store",
        "repos": ["medusajs/medusa", "saleor/saleor", "spree/spree"],
    },
    "data-analytics": {
        "search": "analytics dashboard OR data visualization",
        "repos": ["metabase/metabase", "apache/superset", "getredash/redash"],
    },
    "email-marketing": {
        "search": "email marketing OR newsletter",
        "repos": ["listmonk/listmonk", "Mailtrain-org/mailtrain"],
    },
    "ci-cd-devops": {
        "search": "CI CD OR deployment OR DevOps",
        "repos": ["dagger/dagger", "woodpecker-ci/woodpecker"],
    },
    "scheduling-booking": {
        "search": "booking system OR appointment scheduling",
        "repos": ["calcom/cal.com", "calendso/calendso"],
    },
    "forms-surveys": {
        "search": "form builder OR survey tool",
        "repos": ["heyform/heyform", "formbricks/formbricks"],
    },
    "web-scraping": {
        "search": "web scraping OR web crawler",
        "repos": ["mendableai/firecrawl", "apify/crawlee"],
    },
    "design-tools": {
        "search": "design tool OR UI builder",
        "repos": ["penpot/penpot", "excalidraw/excalidraw"],
    },
    "feedback-tools": {
        "search": "user feedback OR feature request",
        "repos": ["formbricks/formbricks", "fider/fider"],
    },
    "vpn-privacy": {
        "search": "VPN OR privacy tool",
        "repos": ["nicollassilva/adguard-unbound", "firezone/firezone"],
    },
}


def search_github_issues(query, per_page=30, pages=2):
    """
    Search GitHub issues globally for a query.
    Returns issues sorted by reactions (most 👍 = strongest signal).
    """
    all_issues = []
    seen = set()

    for page in range(1, pages + 1):
        params = {
            "q": f"{query} is:issue is:open sort:reactions-+1-desc",
            "per_page": per_page,
            "page": page,
        }

        try:
            resp = requests.get(
                f"{GH_API}/search/issues",
                params=params,
                headers=_headers(),
                timeout=15,
            )

            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])

                for item in items:
                    issue_id = item.get("id")
                    if issue_id in seen:
                        continue
                    seen.add(issue_id)

                    # Extract repo name from URL
                    repo_url = item.get("repository_url", "")
                    repo_name = "/".join(repo_url.split("/")[-2:]) if repo_url else ""

                    reactions = item.get("reactions", {})
                    thumbs_up = reactions.get("+1", 0)
                    total_reactions = reactions.get("total_count", 0)

                    all_issues.append({
                        "id": issue_id,
                        "title": item.get("title", ""),
                        "body_excerpt": (item.get("body") or "")[:300],
                        "repo": repo_name,
                        "thumbs_up": thumbs_up,
                        "total_reactions": total_reactions,
                        "comments": item.get("comments", 0),
                        "url": item.get("html_url", ""),
                        "created_at": item.get("created_at", ""),
                        "labels": [l.get("name", "") for l in item.get("labels", [])],
                        "state": "open",
                    })

                if not items:
                    break

            elif resp.status_code == 403:
                remaining = resp.headers.get("X-RateLimit-Remaining", "0")
                if remaining == "0":
                    reset_time = int(resp.headers.get("X-RateLimit-Reset", "0"))
                    wait = max(reset_time - int(time.time()), 10)
                    print(f"    [GH] Rate limited — waiting {wait}s")
                    time.sleep(min(wait, 60))
                    continue
                break

            elif resp.status_code == 422:
                print(f"    [GH] Validation error — query too complex")
                break

            else:
                print(f"    [GH] Error: {resp.status_code}")
                break

        except Exception as e:
            print(f"    [GH] Request error: {e}")
            break

        time.sleep(1)  # Be nice to GitHub API

    return all_issues


def get_repo_issues(repo, per_page=30, sort="reactions-+1"):
    """
    Get top issues from a specific repo, sorted by reactions.
    """
    issues = []

    try:
        params = {
            "state": "open",
            "sort": "reactions-+1",
            "direction": "desc",
            "per_page": per_page,
        }

        resp = requests.get(
            f"{GH_API}/repos/{repo}/issues",
            params=params,
            headers=_headers(),
            timeout=15,
        )

        if resp.status_code == 200:
            items = resp.json()
            for item in items:
                if item.get("pull_request"):
                    continue  # Skip PRs

                reactions = item.get("reactions", {})
                issues.append({
                    "id": item.get("id"),
                    "title": item.get("title", ""),
                    "body_excerpt": (item.get("body") or "")[:300],
                    "repo": repo,
                    "thumbs_up": reactions.get("+1", 0),
                    "total_reactions": reactions.get("total_count", 0),
                    "comments": item.get("comments", 0),
                    "url": item.get("html_url", ""),
                    "created_at": item.get("created_at", ""),
                    "labels": [l.get("name", "") for l in item.get("labels", [])],
                    "state": "open",
                })

    except Exception as e:
        print(f"    [GH] Repo issues error for {repo}: {e}")

    return issues


def run_github_scrape(topic_slug, keywords=None):
    """
    Full GitHub scrape for a topic.
    Combines global issue search + known repo scraping.
    Returns top issues ranked by reaction count.
    """
    print(f"    [GH] Enriching: '{topic_slug}'...")

    topic_config = TOPIC_REPO_MAP.get(topic_slug, {})
    search_query = topic_config.get("search", topic_slug.replace("-", " "))
    known_repos = topic_config.get("repos", [])

    # Layer 1: Global issue search
    global_issues = search_github_issues(search_query)
    time.sleep(1)

    # Layer 2: Known repo issues (if mapped)
    repo_issues = []
    for repo in known_repos[:3]:  # Max 3 repos to stay in rate limits
        issues = get_repo_issues(repo, per_page=15)
        repo_issues.extend(issues)
        time.sleep(0.5)

    # Merge + deduplicate
    seen_ids = set()
    all_issues = []
    for issue in global_issues + repo_issues:
        if issue["id"] not in seen_ids:
            seen_ids.add(issue["id"])
            all_issues.append(issue)

    # Rank by signal strength: thumbs_up * log(comments + 1) + total_reactions
    for issue in all_issues:
        issue["signal_score"] = (
            issue["thumbs_up"] * 3 +
            issue["total_reactions"] +
            issue["comments"] * math.log(issue["comments"] + 1)
        )

    all_issues.sort(key=lambda x: x["signal_score"], reverse=True)

    # Extract top repos
    repo_counts = {}
    for issue in all_issues:
        repo = issue.get("repo", "")
        if repo:
            repo_counts[repo] = repo_counts.get(repo, 0) + 1
    top_repos = sorted(repo_counts.items(), key=lambda x: x[1], reverse=True)[:8]

    print(f"    [GH] Found {len(all_issues)} open issues ({len(known_repos)} known repos checked)")

    return {
        "issues": all_issues[:15],  # Top 15 by signal
        "total": len(all_issues),
        "top_repos": [{"repo": r[0], "issue_count": r[1]} for r in top_repos],
    }


if __name__ == "__main__":
    result = run_github_scrape("project-management")
    print(f"\n{result['total']} issues found")
    for issue in result["issues"][:5]:
        print(f"  [👍{issue['thumbs_up']} 💬{issue['comments']}] {issue['repo']}")
        print(f"    {issue['title'][:80]}")
