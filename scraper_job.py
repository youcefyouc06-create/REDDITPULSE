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

# Add engine to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "engine"))

from config import TARGET_SUBREDDITS, PAIN_PHRASES, USER_AGENTS, SPAM_PATTERNS, HUMOR_INDICATORS
import random

# ── Supabase config ──
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_KEY", ""))

# ── Spam/humor compiled patterns ──
_spam_re = [re.compile(p, re.IGNORECASE) for p in SPAM_PATTERNS]
_humor_re = [re.compile(p, re.IGNORECASE) for p in HUMOR_INDICATORS]


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
    if on_conflict:
        h["Prefer"] = "resolution=merge-duplicates,return=representation"
    url = f"{SUPABASE_URL}/rest/v1/{table}"
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


def scrape_all_reddit():
    """Scrape all target subreddits."""
    all_posts = []
    seen = set()
    for sub in TARGET_SUBREDDITS:
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
    """Scrape Hacker News via Algolia API."""
    try:
        from hn_scraper import run_hn_scrape
        raw = run_hn_scrape(["startup", "saas", "tool", "problem", "frustrated", "alternative", "invoice", "automation"], max_posts=300)
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
    text = (post.get("full_text", "") or post.get("title", "")).lower()
    matches = []

    for slug, topic_info in TRACKED_TOPICS.items():
        hits = sum(1 for kw in topic_info["keywords"] if kw.lower() in text)
        if hits >= 1:
            matches.append((slug, hits))

    # Sort by hit count, return top 3
    matches.sort(key=lambda x: x[1], reverse=True)

    # If no match found, try dynamic categorization by subreddit
    if not matches:
        subreddit = post.get("subreddit", "")
        if subreddit:
            # Create a dynamic topic from the subreddit
            dynamic_slug = f"sub-{subreddit.lower()}"
            return [dynamic_slug]

    return [m[0] for m in matches[:3]]


# ═══════════════════════════════════════════════════════
# SCORE CALCULATOR — The price formula
# ═══════════════════════════════════════════════════════

def calculate_idea_score(topic_slug, posts, existing_idea=None):
    """
    Calculate the live score (0-100) for an idea topic.
    
    Score = (
        reddit_velocity      * 0.30 +
        google_trend_growth  * 0.25 +
        cross_platform_score * 0.25 +
        engagement_signal    * 0.20
    )
    """
    if not posts:
        return 0.0, {}

    now = time.time()
    seven_days_ago = now - 7 * 86400
    thirty_days_ago = now - 30 * 86400

    # Parse timestamps
    def to_epoch(val):
        if isinstance(val, (int, float)):
            return float(val) if val > 1e9 else 0
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00")).timestamp()
            except (ValueError, TypeError):
                return 0
        return 0

    # ── Velocity (how many posts in last 7 days vs previous) ──
    recent_count = sum(1 for p in posts if to_epoch(p.get("created_utc", 0)) > seven_days_ago)
    older_count = sum(1 for p in posts if seven_days_ago >= to_epoch(p.get("created_utc", 0)) > thirty_days_ago)

    if older_count > 0:
        velocity_ratio = recent_count / older_count
    else:
        velocity_ratio = min(recent_count, 5)

    velocity_score = min(velocity_ratio * 15, 100)

    # ── Cross-platform (how many different sources) ──
    sources = set(p.get("source", "reddit") for p in posts)
    source_count = len(sources)
    cross_platform_multipliers = {1: 1.0, 2: 1.5, 3: 2.2, 4: 3.0}
    cp_mult = cross_platform_multipliers.get(source_count, 3.0)
    cross_platform_score = min(source_count * 25 * cp_mult / 3.0, 100)

    # ── Engagement (avg upvotes + comments) ──
    total_engagement = sum(p.get("score", 0) + p.get("num_comments", 0) for p in posts)
    avg_engagement = total_engagement / max(len(posts), 1)
    engagement_score = min(math.log(avg_engagement + 1) / 7.0 * 100, 100)

    # ── Pain signal (how many match pain phrases) ──
    pain_count = 0
    for p in posts:
        text_lower = (p.get("full_text", "") or "").lower()
        if any(phrase.lower() in text_lower for phrase in PAIN_PHRASES[:20]):
            pain_count += 1
    pain_ratio = pain_count / max(len(posts), 1)
    pain_boost = pain_ratio * 20

    # ── Volume bonus (more data = more confident) ──
    volume_bonus = min(math.log(len(posts) + 1) / math.log(500) * 15, 15)

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
        "sources": sorted(sources),
        "post_count_7d": recent_count,
        "post_count_total": len(posts),
    }

    return final_score, breakdown


def determine_trend(current, previous_24h, previous_7d):
    """Determine trend direction from score history."""
    if previous_7d == 0:
        return "new"
    change_7d = current - previous_7d
    if change_7d > 5:
        return "rising"
    elif change_7d < -5:
        return "falling"
    else:
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

def run_scraper_job(sources=None, topic_filter=None):
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

    print("=" * 60)
    print("  Opportunity Engine — Scraper Job")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Sources: {', '.join(sources)}")
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
    seen_ids = set()

    def _merge(new_posts):
        """Deduplicate and merge posts into all_posts."""
        added = 0
        for p in new_posts:
            eid = p.get("external_id", "")
            if eid and eid not in seen_ids:
                seen_ids.add(eid)
                all_posts.append(p)
                added += 1
        return added

    if "reddit" in sources:
        # ── Layer 1: Async Reddit JSON API (~15s for 42 subs) ──
        print("\n  [1/6] Layer 1 — Async Reddit scrape...")
        try:
            from reddit_async import scrape_all_async
            reddit_posts = asyncio.run(scrape_all_async())
            added = _merge(reddit_posts)
            print(f"  [OK] Layer 1 (async): {added} fresh posts")
        except Exception as e:
            print(f"  [!] Layer 1 async failed, falling back to sync: {e}")
            reddit_posts = scrape_all_reddit()
            added = _merge(reddit_posts)
            print(f"  [OK] Layer 1 (sync fallback): {added} posts")

        # ── Layer 2: PullPush.io Historical (90 days back) ──
        print("\n  [2/6] Layer 2 — PullPush historical scrape...")
        try:
            from pullpush_scraper import scrape_historical_multi
            pp_posts = scrape_historical_multi(days_back=90, size_per_sub=100, delay=0.5)
            added = _merge(pp_posts)
            print(f"  [OK] Layer 2 (PullPush): +{added} historical posts")
        except Exception as e:
            print(f"  [!] Layer 2 (PullPush) skipped: {e}")

        # ── Layer 3: Reddit Sitemap (real-time discovery) ──
        print("\n  [3/6] Layer 3 — Sitemap real-time discovery...")
        try:
            from sitemap_listener import discover_new_posts
            sitemap_posts = discover_new_posts(max_fetch=30)
            added = _merge(sitemap_posts)
            print(f"  [OK] Layer 3 (sitemap): +{added} newly discovered posts")
        except Exception as e:
            print(f"  [!] Layer 3 (sitemap) skipped: {e}")

        # ── Layer 4: PRAW authenticated (optional) ──
        try:
            from reddit_auth import is_available as praw_available, scrape_all_authenticated
            if praw_available():
                print("\n  [3.5/6] Layer 4 — PRAW authenticated deep dive...")
                praw_posts = scrape_all_authenticated(TARGET_SUBREDDITS[:10], sorts=["rising"])
                added = _merge(praw_posts)
                print(f"  [OK] Layer 4 (PRAW): +{added} authenticated posts")
        except Exception as e:
            pass  # PRAW is optional, silent skip

    if "hackernews" in sources:
        print("\n  [4/6] Scraping Hacker News...")
        hn_posts = scrape_hn()
        _merge(hn_posts)
        print(f"  [OK] HN: {len(hn_posts)} posts")

    if "producthunt" in sources:
        print("\n  [5/6] Scraping ProductHunt...")
        ph_posts = scrape_ph()
        _merge(ph_posts)
        print(f"  [OK] PH: {len(ph_posts)} posts")

    if "indiehackers" in sources:
        print("\n  [6/6] Scraping IndieHackers...")
        ih_posts = scrape_ih()
        _merge(ih_posts)
        print(f"  [OK] IH: {len(ih_posts)} posts")

    print(f"\n  Total posts scraped (deduplicated): {len(all_posts)}")

    if not all_posts:
        print("  [!] No posts collected — exiting")
        if run_id:
            sb_patch("scraper_runs", f"id=eq.{run_id}", {
                "status": "failed", "error_text": "No posts collected",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": round(time.time() - start_time, 1),
            })
        return

    # ── 2. Cluster posts → ideas ──
    print("\n  Clustering posts into idea topics...")
    idea_posts = defaultdict(list)

    for post in all_posts:
        topics = classify_post_to_topics(post)
        for topic in topics:
            idea_posts[topic].append(post)

    # Filter by topic if specified
    if topic_filter:
        idea_posts = {k: v for k, v in idea_posts.items() if k in topic_filter}

    matched_ideas = len(idea_posts)
    matched_posts = sum(len(v) for v in idea_posts.values())
    print(f"  [OK] {matched_posts} posts matched into {matched_ideas} idea topics")

    # ── 3. Load existing ideas from Supabase ──
    existing_ideas = {}
    if SUPABASE_URL:
        rows = sb_select("ideas", "select=*")
        for row in rows:
            existing_ideas[row["slug"]] = row

    # ── 4. Calculate scores + upsert ──
    print("\n  Calculating idea scores...")
    ideas_to_upsert = []
    history_to_insert = []
    ideas_updated = 0

    for slug, posts in idea_posts.items():
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

        score, breakdown = calculate_idea_score(slug, posts)
        existing = existing_ideas.get(slug)

        # Get previous scores for trend calculation
        prev_24h = existing["current_score"] if existing else 0
        prev_7d = existing["score_7d_ago"] if existing else 0
        prev_30d = existing["score_30d_ago"] if existing else 0

        trend = determine_trend(score, prev_24h, prev_7d)
        confidence = determine_confidence(len(posts), breakdown.get("source_count", 1))

        # Only skip if truly insufficient (< 3 posts) AND doesn't already exist
        if len(posts) < 3 and not existing:
            continue

        # Get top 5 posts by engagement
        top_posts = sorted(posts, key=lambda p: p.get("score", 0) + p.get("num_comments", 0), reverse=True)[:5]
        top_posts_json = [{
            "title": p.get("title", "")[:200],
            "source": p.get("source", ""),
            "subreddit": p.get("subreddit", ""),
            "score": p.get("score", 0),
            "comments": p.get("num_comments", 0),
            "url": p.get("permalink", ""),
        } for p in top_posts]

        idea_row = {
            "topic": topic_name,
            "slug": slug,
            "current_score": score,
            "score_24h_ago": prev_24h,
            "score_7d_ago": existing["score_7d_ago"] if existing else 0,
            "score_30d_ago": existing["score_30d_ago"] if existing else 0,
            "change_24h": round(score - prev_24h, 1),
            "change_7d": round(score - prev_7d, 1),
            "change_30d": round(score - prev_30d, 1),
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
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

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
        for idea in ideas_to_upsert:
            resp = sb_upsert("ideas", [idea], on_conflict="slug")

        # Insert history (need idea_ids)
        updated_ideas = sb_select("ideas", "select=id,slug")
        slug_to_id = {r["slug"]: r["id"] for r in updated_ideas}

        for i, hist in enumerate(history_to_insert):
            slug = ideas_to_upsert[i]["slug"]
            idea_id = slug_to_id.get(slug)
            if idea_id:
                hist["idea_id"] = idea_id
                sb_upsert("idea_history", [hist])

        print(f"  [OK] {len(ideas_to_upsert)} ideas upserted + {len(history_to_insert)} history records")

    # ── 6. Update run log ──
    duration = round(time.time() - start_time, 1)
    if run_id and SUPABASE_URL:
        sb_patch("scraper_runs", f"id=eq.{run_id}", {
            "status": "completed",
            "posts_collected": len(all_posts),
            "ideas_updated": ideas_updated,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": duration,
        })

    print(f"\n{'=' * 60}")
    print(f"  Done! {len(all_posts)} posts → {ideas_updated} ideas updated")
    print(f"  Duration: {duration}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Opportunity Engine — Scraper Job")
    parser.add_argument("--sources", nargs="+", default=None,
                        choices=["reddit", "hackernews", "producthunt", "indiehackers"],
                        help="Which sources to scrape")
    parser.add_argument("--topics", type=str, default=None,
                        help="Comma-separated topic slugs to update (e.g. 'invoice-automation,crm-for-freelancers')")
    args = parser.parse_args()

    topic_filter = None
    if args.topics:
        topic_filter = [t.strip() for t in args.topics.split(",")]

    try:
        run_scraper_job(sources=args.sources, topic_filter=topic_filter)
    except Exception as e:
        print(f"\n  [FATAL] {e}")
        traceback.print_exc()
