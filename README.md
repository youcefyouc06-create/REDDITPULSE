# IDEA STOCK MARKET (RedditPulse)

> "The tightest feedback loop between community pain and product creation."

The Idea Stock Market is an autonomous, multi-layered OSINT (Open Source Intelligence) pipeline designed to discover, enrich, and ruthlessly validate SaaS and product opportunities before a single line of code is written.

It doesn't look for ideas. It looks for **pain**.

---

## 🏗️ System Architecture

The ecosystem is divided into three distinct chronological phases: **Scan (Broad)**, **Enrich (Deep)**, and **Validate (AI Debate)**.

### Phase 1: The Pulse Engine (Broad Scanning)
The Pulse Engine is responsible for ingesting thousands of raw signals from across the internet, clustering them by topic, and surfacing anomalies (sudden spikes in complaints or requests).

*   **`scraper_job.py` (The Orchestrator):** The heart of the broad scan. It monitors 42+ subreddits, dynamically categories posts into 45+ tracking topics using NLP, and calculates a base signal score using velocity, volume, and specific "pain phrases".
*   **`ph_scraper.py` (v3):** A hardened, persistent session scraper for Product Hunt. It utilizes background cookie warmup, exponential backoff, and automatic graceful degradation from GraphQL down to RSS feeds if blocked.
*   **`ih_scraper.py` (v3):** A resilient IndieHackers scraper that dynamically dissects JavaScript bundles to extract live Algolia API keys, with multi-layer fallback chains (Algolia → JSON API → HTML → RSS).
*   **`hn_scraper.py`:** Hacker News integration targeting high-value "Ask HN" and "Show HN" threads.

### Phase 2: Deep Signals Enrichment Layer
While Phase 1 finds the *smoke*, Phase 2 looks for the *fire*. It triggers on-demand when a user inspects a specific opportunity.

*   **`enrich_idea.py`:** Coalesces deep technical data. It implements a triangulation algorithm to find **Confirmed Gaps**—if developers are complaining about it on Stack Overflow AND requesting it on GitHub, it's a real problem. Caches results in Supabase with a 7-day TTL (`schema_enrichment.sql`).
*   **`engine/stackoverflow_scraper.py`:** Bypasses answered questions entirely. It specifically hunts for *unanswered*, *high-voted* questions via the StackExchange API, ranking them by a composite score of `votes * log(views)`.
*   **`engine/github_issues_scraper.py`:** Searches globally and within known repositories for open issues sorted by extreme community reaction (👍 emojis and comment volume).

### Phase 3: The Multi-Agent Validation Pipeline
Once an opportunity is confirmed, it undergoes rigorous, simulated adversarial stress testing.

*   **`validate_idea.py`:** The handler that pushes an idea into the crucible.
*   **`engine/multi_brain.py` (The Debate Engine):** Instantiates three distinct AI personas (The Cynic, The Optimist, The Realist). They read the aggregated data and mathematically debate the viability of the product, tearing down weak assumptions.
*   **`engine/scorer.py`:** Quantifies the debate into a strict 0-100 score across 12 vectors (ICP readiness, Moat probability, Technical Complexity, etc.).

---

## 💻 The Interface

The frontend is built on **Next.js 14** (App Router), styled with vanilla **Tailwind CSS**, and fueled by **Supabase**.

*   **The Stock Market Dashboard (`StockMarket.tsx`):** A live, Bloomberg-terminal-esque glassmorphism interface. Opportunities are ranked natively by signal momentum.
*   **Expandable Intelligence:** Clicking any row seamlessly slides open the Deep Signals panel, injecting Stack Overflow and GitHub insights asynchronously.

---

## 🚀 Deployment & Setup

### 1. Database Provisioning (Supabase)
Execute the following schemas in your Supabase SQL Editor:
1.  `sql/schema_stock_market.sql` - Core ideas table
2.  `sql/schema_queue.sql` - Background worker queue
3.  `sql/schema_enrichment.sql` - 7-day TTL cache

### 2. Environment Variables
You will need a `.env.local` inside the `/app` directory:
```env
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
GEMINI_API_KEY=... # Or OPENAI_API_KEY / GROQ_API_KEY
```

### 3. Execution Run-book
To run the front-end dashboard:
```bash
cd app
npm install
npm run dev
```

To run a raw manual scan from the backend:
```bash
python scraper_job.py
```

---

## 🔒 Ethos

Code is purely functional. This repository exists to systematically eliminate the gamble of product creation by turning qualitative human complaints into quantitative market signals.
