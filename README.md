<p align="center">
  <img src="https://img.shields.io/badge/Next.js-16.1-black?logo=nextdotjs" />
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" />
  <img src="https://img.shields.io/badge/Supabase-Backend-3ecf8e?logo=supabase" />
  <img src="https://img.shields.io/badge/AI-Multi--Model%20Debate-orange" />
  <img src="https://img.shields.io/badge/License-Private-red" />
</p>

# 🔥 RedditPulse — Idea Stock Market & Opportunity Intelligence Engine

**Stop guessing what to build next.** RedditPulse scans millions of conversations across Reddit, Hacker News, ProductHunt, and IndieHackers to find people *literally begging* for tools that don't exist yet — then validates those signals with multi-model AI debate and cross-platform triangulation.

> Think of it as a Bloomberg Terminal for startup ideas — live scores, rising/falling trends, AI validation reports, and competitor vulnerability mapping, all powered by real human frustration data.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Core Features](#core-features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Engine Modules (Python)](#engine-modules-python)
- [Frontend (Next.js)](#frontend-nextjs)
- [API Routes](#api-routes)
- [Database Schema](#database-schema)
- [Data Pipeline](#data-pipeline)
- [Multi-Brain AI Debate System](#multi-brain-ai-debate-system)
- [Setup & Installation](#setup--installation)
- [Environment Variables](#environment-variables)
- [Running Locally](#running-locally)
- [Deployment Notes](#deployment-notes)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 16)                     │
│   Landing Page  ─  Dashboard  ─  StockMarket  ─  Validation     │
│   Framer Motion / TailwindCSS / Lucide / Supabase Auth           │
└──────────────────────────┬──────────────────────────────────────┘
                           │  14 API Routes
┌──────────────────────────▼──────────────────────────────────────┐
│                     API LAYER (Next.js Route Handlers)            │
│   /scan  /validate  /ideas  /enrich  /discover  /intelligence    │
│   /settings/ai  /watchlist  /auth/signup  /scan/[id]/report      │
└──────────────────────────┬──────────────────────────────────────┘
                           │  exec() / child_process
┌──────────────────────────▼──────────────────────────────────────┐
│                     PYTHON ENGINE (20 modules)                    │
│                                                                   │
│  ORCHESTRATORS        SCRAPERS           ANALYSIS                │
│  ├─ scraper_job.py    ├─ keyword_scraper ├─ analyzer.py (VADER)  │
│  ├─ run_scan.py       ├─ hn_scraper      ├─ ai_analyzer.py      │
│  ├─ validate_idea.py  ├─ ph_scraper      ├─ scorer.py           │
│  └─ enrich_idea.py    ├─ ih_scraper      ├─ credibility.py      │
│                       ├─ so_scraper      ├─ competition.py      │
│                       └─ gh_issues       ├─ icp.py              │
│                                          ├─ trends.py           │
│  AI ENGINE                               └─ report_synth.py     │
│  ├─ multi_brain.py (9 providers)                                 │
│  └─ config.py (42 subreddits)                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     SUPABASE (PostgreSQL)                         │
│   ideas ─ idea_history ─ watchlists ─ scraper_runs               │
│   scans ─ scan_results ─ enrichment_cache ─ user_ai_config       │
│   RLS policies ─ Indexes ─ Triggers                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Features

| Feature | Description | Signal Type |
|---|---|---|
| **Idea Stock Market** | Live opportunity scores (0–100) that move like stock prices with 24h/7d/30d deltas | Demand |
| **Multi-Platform Scraping** | Reddit (42 subs), Hacker News, ProductHunt, IndieHackers — simultaneously | Community Pain |
| **AI Slop Filter** | 4-pass analysis drops AI-generated noise (30+ ChatGPT signatures detected) | Data Quality |
| **Multi-Brain Debate** | 2–3 AI models analyze independently → debate disagreements → synthesize consensus | Validation |
| **13-Section Intelligence Report** | Executive synthesis, ICP persona card, competition matrix, financial reality check, risk matrix, market timing, first-10 strategy with outreach scripts, and more | Strategy |
| **Expandable Live Terminal** | Click-to-expand terminal showing real-time agent debate with styled role cards | UX |
| **Credibility Engine** | Shannon entropy diversity scoring — source diversity beats raw volume | Confidence |
| **Complaint Velocity** | Tracks posts-per-week growth to detect exploding pain points | Timing |
| **Competition Analyzer** | Deep competitor cards with threat levels, attack angles, user complaints, biggest threat/easiest win | Market |
| **ICP Detector** | Persona + communities + influencers + buying objections + WTP evidence + day-in-life | Customer |
| **Financial Reality Check** | Break-even analysis, time-to-$1K/$10K MRR, CAC budget, gross margin | Finance |
| **Google Trends Velocity** | Checks if pain is growing (🚀 EXPLODING) or dying (💀 DEAD) | Timing |
| **Deep Signal Enrichment** | Stack Overflow unanswered questions + GitHub issues with 👍 reactions | Builder Pain |
| **WTP Extraction** | Detects "I'd pay $X/month" signals with budget evidence | Revenue |
| **Keyword Scan** | Timed scans (10min → 48h) with continuous polling for fresh posts | Discovery |
| **Pain Stream Monitor** | Real-time Reddit pain point alerts with configurable keywords | Discovery |
| **Competitor Deathwatch** | Tracks competitor complaint velocity on G2/Reddit for vulnerability windows | Competitive |

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Frontend | Next.js (Turbopack) | 16.1.6 |
| UI | React + Framer Motion + Lucide Icons | 19.2.3 |
| Styling | TailwindCSS v4 | 4.x |
| Backend API | Next.js Route Handlers (App Router) | — |
| Engine | Python 3.10+ | — |
| NLP | NLTK VADER + Custom 50-Word B2B Matrix | — |
| AI | Gemini, Anthropic, OpenAI, Groq, Grok, DeepSeek, Minimax, Ollama, OpenRouter | — |
| Database | Supabase (PostgreSQL) | — |
| Auth | Supabase Auth | — |
| Payments | Stripe (Lifetime Pro $49) | — |

---

## Project Structure

```
RedditPulse/
├── app/                          # Next.js 16 frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx                # Landing page (hero + features + pricing)
│   │   │   ├── login/page.tsx          # Auth page
│   │   │   ├── layout.tsx              # Root layout
│   │   │   ├── components/
│   │   │   │   ├── motion.tsx          # Reusable animation components
│   │   │   │   ├── app-sidebar.tsx     # Dashboard sidebar navigation
│   │   │   │   └── premium-gate.tsx    # Paywall component
│   │   │   ├── dashboard/
│   │   │   │   ├── StockMarket.tsx     # 910-line Idea Stock Market (main view)
│   │   │   │   ├── DashboardClient.tsx # Client-side dashboard wrapper
│   │   │   │   ├── DashboardHome.tsx   # Dashboard home stats
│   │   │   │   ├── DashboardLayout.tsx # Layout with sidebar
│   │   │   │   ├── page.tsx            # Dashboard page route
│   │   │   │   ├── layout.tsx          # Dashboard layout route
│   │   │   │   ├── scans/page.tsx      # Keyword scan launcher
│   │   │   │   ├── validate/page.tsx   # Idea validator (expandable terminal + live debate cards)
│   │   │   │   ├── explore/page.tsx    # Opportunity explorer
│   │   │   │   ├── trends/page.tsx     # Trend analysis
│   │   │   │   ├── competitors/page.tsx# Competition analysis
│   │   │   │   ├── reports/page.tsx    # Saved reports
│   │   │   │   ├── reports/[id]/page.tsx # 13-section intelligence report
│   │   │   │   ├── alerts/page.tsx     # Pain point alerts
│   │   │   │   ├── saved/page.tsx      # Bookmarks
│   │   │   │   ├── wtp/page.tsx        # WTP signal viewer
│   │   │   │   ├── digest/page.tsx     # Digest view
│   │   │   │   ├── sources/page.tsx    # Source management
│   │   │   │   ├── pricing/page.tsx    # Pricing page
│   │   │   │   └── settings/page.tsx   # AI model configuration
│   │   │   └── api/                    # 14 API route handlers
│   │   │       ├── scan/route.ts       # POST: launch scan, GET: list scans
│   │   │       ├── scan/[id]/route.ts  # GET: scan status + results
│   │   │       ├── scan/[id]/report/   # GET: full AI report for scan
│   │   │       ├── validate/route.ts   # POST: validate idea (3-phase AI)
│   │   │       ├── validate/[id]/      # GET: validation status
│   │   │       ├── ideas/route.ts      # GET: list ideas (stock market data)
│   │   │       ├── ideas/[slug]/       # GET: single idea detail
│   │   │       ├── enrich/route.ts     # GET/POST: deep signal enrichment
│   │   │       ├── discover/route.ts   # GET: opportunity discovery feed
│   │   │       ├── intelligence/       # GET: cross-platform intelligence
│   │   │       ├── watchlist/route.ts  # CRUD: user watchlist
│   │   │       ├── auth/signup/        # POST: user registration
│   │   │       ├── settings/ai/        # GET/POST: AI model config
│   │   │       └── settings/ai/verify/ # POST: verify API key works
│   │   └── lib/                        # Shared utilities
│   ├── package.json
│   ├── .env.local                      # Supabase + AI keys
│   └── tailwind.config.ts
│
├── engine/                             # Python analysis engine (20 modules)
│   ├── config.py                       # 42 subreddits, 50+ pain phrases, scoring weights
│   ├── multi_brain.py                  # 9-provider AI debate engine (599 lines)
│   ├── keyword_scraper.py              # Timed Reddit keyword scanner
│   ├── hn_scraper.py                   # Hacker News Algolia API scraper
│   ├── ph_scraper.py                   # ProductHunt GraphQL → RSS fallback
│   ├── ih_scraper.py                   # IndieHackers Algolia → web scrape fallback
│   ├── stackoverflow_scraper.py        # SO unanswered question finder
│   ├── github_issues_scraper.py        # GitHub issues by reaction count
│   ├── analyzer.py                     # 4-pass VADER + B2B matrix + AI slop filter
│   ├── ai_analyzer.py                  # Per-post LLM opportunity analysis
│   ├── scorer.py                       # Per-subreddit normalization + velocity scoring
│   ├── credibility.py                  # Shannon entropy source diversity scoring
│   ├── competition.py                  # Google-based competition tier analysis
│   ├── icp.py                          # Ideal Customer Profile aggregator
│   ├── trends.py                       # Google Trends velocity layer (pytrends)
│   ├── report_synthesizer.py           # AI-powered Market Signal Report generator
│   ├── pain_stream.py                  # Real-time Reddit pain point monitor
│   ├── competitor_deathwatch.py        # Competitor complaint velocity tracker
│   └── graveyard.py                    # Failed startup idea graveyard engine
│
├── scraper_job.py                      # Main scraper orchestrator (933 lines)
├── run_scan.py                         # Scan runner with multi-brain debate (532 lines)
├── validate_idea.py                    # 3-phase AI idea validator with enriched prompts (1629 lines)
├── enrich_idea.py                      # Deep signal enrichment orchestrator (266 lines)
│
├── sql/
│   ├── schema_stock_market.sql         # ideas, idea_history, watchlists, scraper_runs
│   └── schema_enrichment.sql           # enrichment_cache with 7-day TTL
│
└── output/                             # Generated scan results
```

---

## Engine Modules (Python)

### Scrapers (6 modules)

| Module | Source | Method | Rate Limit Strategy |
|---|---|---|---|
| `keyword_scraper.py` | Reddit | Public JSON API + search | 2.5s delay, user-agent rotation (7 agents) |
| `hn_scraper.py` | Hacker News | Algolia API (free, no auth) | 0.5s delay, exponential backoff on 429 |
| `ph_scraper.py` | ProductHunt | GraphQL → RSS fallback | Session cookies, 3-retry with backoff |
| `ih_scraper.py` | IndieHackers | Algolia → web scrape fallback | Dynamic key refresh from JS bundles |
| `stackoverflow_scraper.py` | Stack Overflow | Stack Exchange API v2.3 | 10K req/day free, quota monitoring |
| `github_issues_scraper.py` | GitHub | REST API v3 | 60 req/hr (unauth), 5K/hr with token |

### Analysis Pipeline (5 modules)

| Module | Function | Key Technique |
|---|---|---|
| `analyzer.py` | 4-pass sentiment + opportunity analysis | Custom 50-word B2B VADER matrix, 30+ AI slop phrases, 25 frustration markers, 15 opportunity markers |
| `ai_analyzer.py` | Per-post LLM opportunity extraction | Gemini → Groq → OpenAI fallback chain, ICP + WTP extraction |
| `scorer.py` | Composite opportunity scoring | Per-subreddit normalization, cross-platform multipliers (1x–3x), complaint velocity tracking |
| `credibility.py` | Evidence quality assessment | Shannon entropy diversity, 5-tier system (INSUFFICIENT → STRONG), cross-platform dedup |
| `competition.py` | Market saturation analysis | Google search → G2/PH product counting, Blue Ocean → Saturated tiers |

### Intelligence Layer (3 modules)

| Module | Function |
|---|---|
| `icp.py` | Aggregates persona, tool sentiment, budget signals, pain intensity from AI results into composite ICP |
| `trends.py` | Google Trends velocity layer via pytrends — EXPLODING/GROWING/STABLE/DECLINING/DEAD tiers with score multipliers |
| `report_synthesizer.py` | Generates Market Signal Reports (BUILD / EXPLORE / SKIP verdicts) using multi-brain debate |

### Core Engine (2 modules)

| Module | Lines | Function |
|---|---|---|
| `config.py` | 238 | 42 target subreddits, 50+ pain-point phrases, 10 industry keyword sets, 7 spam patterns, scoring weights |
| `multi_brain.py` | 599 | 9-provider AI engine (Gemini, Anthropic, OpenAI, Groq, Grok, DeepSeek, Minimax, Ollama, OpenRouter), model alias resolution, parallel debate, majority-vote synthesis with dissent tracking |

### Orchestrators (4 scripts)

| Script | Lines | Function |
|---|---|---|
| `scraper_job.py` | 933 | Full scraper pipeline: Reddit (42 subs + search) → HN → PH → IH → analyze → score → cluster → upsert to Supabase `ideas` table |
| `run_scan.py` | 532 | Keyword-based scan: keyword search → multi-platform collection → AI analysis → multi-brain debate synthesis → update Supabase `scans` |
| `validate_idea.py` | 1629 | 3-phase AI validation with enriched prompts: Phase 1 (evidence gathering + batch analysis) → Phase 2 (ICP + competition with deep schemas) → Phase 3 (roadmap with validation gates + financial reality + risk matrix) → Multi-brain debate verdict |
| `enrich_idea.py` | 266 | Deep signal enrichment: Stack Overflow + GitHub Issues → cache to Supabase `enrichment_cache` with 7-day TTL |

---

## Frontend (Next.js)

### Key Components

| Component | Lines | What It Does |
|---|---|---|
| `StockMarket.tsx` | 910 | The main dashboard view — displays ideas as stock market tickers with live scores, 24h/7d changes, trend direction, confidence levels, category filters, and source badges |
| `page.tsx` (landing) | 306 | Marketing landing page with hero section, animated features grid, validation report demo, and $49 pricing card |
| `DashboardClient.tsx` | — | Client-side wrapper managing auth state and routing |
| `motion.tsx` | — | Reusable Framer Motion components: StaggerContainer, GlassCard, GlowBadge, FloatingDots, AnimatedSparkline, ViewportReveal |
| `premium-gate.tsx` | — | Stripe-powered paywall for premium features |
| `app-sidebar.tsx` | — | Dashboard navigation with 12+ sections |

### Dashboard Pages (12)

Scans · Validate · Explore · Trends · Competitors · Reports · Saved · WTP · Digest · Sources · Pricing · Settings

---

## API Routes

| Route | Method | Auth | Function |
|---|---|---|---|
| `/api/scan` | POST | ✅ Premium | Launch keyword scan (rate limited: 5/hour) |
| `/api/scan` | GET | ✅ | List user's scans |
| `/api/scan/[id]` | GET | ✅ | Get scan status + results |
| `/api/scan/[id]/report` | GET | ✅ | Full AI synthesis report |
| `/api/validate` | POST | ✅ | Validate idea (3-phase AI) |
| `/api/validate/[id]` | GET | ✅ | Get validation status |
| `/api/ideas` | GET | ❌ | List all ideas (stock market data, sortable/filterable) |
| `/api/ideas/[slug]` | GET | ❌ | Single idea with full intelligence |
| `/api/enrich` | GET | ❌ | Get cached enrichment (SO + GH signals) |
| `/api/enrich` | POST | ✅ | Trigger background enrichment |
| `/api/discover` | GET | ❌ | Opportunity discovery feed |
| `/api/intelligence` | GET | ❌ | Cross-platform intelligence summary |
| `/api/watchlist` | CRUD | ✅ | User watchlist management |
| `/api/settings/ai` | GET/POST | ✅ | Configure AI model providers + keys |
| `/api/settings/ai/verify` | POST | ✅ | Verify an API key is valid |
| `/api/auth/signup` | POST | ❌ | User registration |

---

## Database Schema

### `ideas` (Idea Stock Market)
Live opportunity scores with historical deltas, trend tracking, and intelligence data.

| Column | Type | Description |
|---|---|---|
| `current_score` | FLOAT | Live score 0–100 |
| `change_24h/7d/30d` | FLOAT | Score deltas (like stock prices) |
| `trend_direction` | VARCHAR | rising / falling / stable / new |
| `confidence_level` | VARCHAR | LOW / MODERATE / HIGH / STRONG |
| `post_count_total` | INT | Total evidence posts |
| `source_count` | INT | Number of platforms confirming |
| `icp_data` | JSONB | Ideal Customer Profile |
| `competition_data` | JSONB | Market saturation analysis |
| `top_posts` | JSONB | Best evidence posts |

### `idea_history` (Price Charts)
Historical score snapshots for charting, linked to ideas via FK.

### `watchlists` (User Portfolios)
Per-user idea tracking with alert thresholds. Full RLS — users see only their own.

### `enrichment_cache` (Deep Signals)
Stack Overflow + GitHub data cached with 7-day TTL auto-expiry trigger.

### Row Level Security
- **ideas, idea_history, scraper_runs, enrichment_cache**: Publicly readable
- **watchlists**: Users read/write only their own rows
- **scans, scan_results**: Users see only their own data

---

## Data Pipeline

```
              INPUT                          PROCESS                         OUTPUT
        ┌───────────────┐          ┌──────────────────────┐          ┌─────────────────┐
        │ Reddit 42 subs │─────────▶│ PASS 1: AI Slop Filter│─────▶ Drop 30%+ bots    │
        │ HN Algolia     │          │ PASS 2: VADER B2B     │         │                 │
        │ PH GraphQL/RSS │          │   (50-word matrix)    │   ┌────▶│ scored_posts[]  │
        │ IH Algolia/web │          │ PASS 3: Regex scan    │   │    │ (per-sub norm,  │
        └───────────────┘          │   (25 frust + 15 opp) │   │    │  velocity,       │
                                   │ PASS 4: Context valid  │   │    │  cross-plat)     │
                                   └──────────┬─────────────┘   │    └────────┬────────┘
                                              │                 │             │
                                              ▼                 │             ▼
                                   ┌──────────────────────┐     │    ┌─────────────────┐
                                   │ Per-Post AI Analysis  │     │    │ Cluster by Topic │
                                   │ (Gemini→Groq→OpenAI) │     │    │ + Velocity Tags   │
                                   │ → ICP + WTP + urgency │─────┘    └────────┬────────┘
                                   └──────────────────────┘                    │
                                                                               ▼
                                                                    ┌─────────────────┐
                                                                    │ Upsert to        │
                                                                    │ Supabase `ideas` │
                                                                    │ (stock market)    │
                                                                    └─────────────────┘
```

---

## Multi-Brain AI Debate System

The debate engine (`multi_brain.py`) is the core differentiator:

1. **Independent Analysis** — Same prompt sent to 2–3 AI models in parallel via `ThreadPoolExecutor`
2. **Verdict Check** — If all models agree → merge (unanimous consensus)
3. **Debate Round** — If models disagree, each sees the others' analyses and must either HOLD or CHANGE
4. **Final Synthesis** — Majority vote with:
   - **Unanimous** → average confidence
   - **Majority** → majority confidence × 0.9 penalty
   - **No majority** → minimum confidence (most conservative)
   - **Dissent tracking** — minority opinions preserved in output

### Supported Providers

| Provider | Default Model | Paid? |
|---|---|---|
| Gemini | gemini-2.0-flash | Free tier |
| Groq | llama-4-scout-17b | Free tier |
| OpenAI | gpt-4o | Paid |
| Anthropic | claude-sonnet-4 | Paid |
| Grok (xAI) | grok-4.1 | Paid |
| DeepSeek | deepseek-chat | Free tier |
| Minimax | minimax-01 | Free tier |
| Ollama | custom | Self-hosted |
| OpenRouter | any model | Variable |

Model aliases auto-resolve stale names (e.g., `gpt-5.4` → `gpt-4o`, `gemini-3.1-pro` → `gemini-2.0-flash`).

---

## Setup & Installation

### Prerequisites
- **Node.js** 18+
- **Python** 3.10+
- **Supabase** project (free tier works)
- At least **one AI API key** (Gemini or Groq free tiers recommended)

### 1. Clone

```bash
git clone https://github.com/youcefyouc06-create/REDDITPULSE.git
cd REDDITPULSE
```

### 2. Python dependencies

```bash
pip install requests nltk pytrends
python -c "import nltk; nltk.download('vader_lexicon')"
```

### 3. Frontend dependencies

```bash
cd app
npm install
```

### 4. Database setup

Run these SQL files in the **Supabase SQL Editor** (Dashboard → SQL Editor → New Query):

1. `sql/schema_stock_market.sql` — Creates `ideas`, `idea_history`, `watchlists`, `scraper_runs`
2. `sql/schema_enrichment.sql` — Creates `enrichment_cache` with TTL triggers

---

## Environment Variables

Create `app/.env.local`:

```env
# Supabase (required)
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# AI Providers (at least one required)
GEMINI_API_KEY=your-key
GROQ_API_KEY=your-key
OPENAI_API_KEY=your-key

# Optional AI providers
GITHUB_TOKEN=ghp_...          # Increases GitHub API from 60 to 5000 req/hr
AI_ENCRYPTION_KEY=...         # For encrypting stored API keys

# Stripe (for payments)
STRIPE_SECRET_KEY=sk_...
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_...
```

---

## Running Locally

### Start the frontend

```bash
cd app
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Run the scraper (populates Idea Stock Market)

```bash
# From project root (not app/)
python scraper_job.py
```

This scrapes all 42 subreddits + HN + PH + IH, analyzes posts, and upserts scored ideas to Supabase.

### Run a keyword scan

```bash
python run_scan.py --keywords "invoice automation,billing tool" --duration 10min
```

### Validate an idea

```bash
python validate_idea.py "Invoice automation for freelancers"
```

### Enrich with deep signals

```bash
python enrich_idea.py invoice-automation --keywords "invoice,billing"
```

---

## Deployment Notes

- The Python engine runs as **child processes** spawned by Next.js API routes via `exec()`
- For production, consider running the scraper as a **cron job** (every 6–12 hours)
- The `enrichment_cache` has a **7-day TTL** — stale data auto-expires via DB trigger
- **Rate limits**: Reddit (2.5s delay), HN (0.5s), PH (1s per page), IH (0.5s), SO (monitored quota), GitHub (token recommended)
- All Supabase tables have **RLS enabled** — the service role key bypasses RLS for backend writes

---

## Validation Report Sections

The 13-section intelligence report generated by the validation engine:

| # | Section | What It Shows |
|---|---|---|
| 1 | **Executive Synthesis** | AI-generated strategic summary |
| 2 | **Signal Summary** | Posts scraped / analyzed / pain quotes / WTP signals / competitor mentions |
| 3 | **ICP Persona Card** | Primary persona, day-in-life, demographics, communities, influencers, tools, buying objections, WTP evidence |
| 4 | **Price Signals & WTP** | Pricing tiers with features, competitor price benchmarks |
| 5 | **Market Timing Intelligence** | Timing assessment, TAM estimate, pain validation badge |
| 6 | **Competition Network** | Competitor cards with threat level badges, attack angles, user complaints, biggest threat / easiest win, moat strategy |
| 7 | **Financial Reality Check** | Break-even users, time-to-$1K/$10K MRR, CAC budget, gross margin |
| 8 | **Risk Matrix** | Severity × probability badges, mitigation steps, owner tags (min 5 risks) |
| 9 | **Raw Evidence Ingestion** | Platform-tagged evidence posts with scores and relevance notes |
| 10 | **Launch Trajectory** | Roadmap steps with validation gates, channel badges, cost estimates, expected outcomes |
| 11 | **First 10 Customers Strategy** | 3-phase outreach (customers 1-3 / 4-7 / 8-10) with channel, tactic, and word-for-word scripts |
| 12 | **Debate Room** | Multi-model consensus trace with reasoning, verdict shifts, and confidence per round |
| 13 | **MVP vs Cut Features** | Core launch features vs defer-to-later features |

---

<p align="center">
  Built for founders who validate before they build. 🔥
</p>
