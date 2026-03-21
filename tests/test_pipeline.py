import json
import sys
import time
import types

import validate_idea as pipeline
from engine import keyword_scraper
from engine.competition import analyze_competition, competition_summary
from engine.multi_brain import MultiBrain


class StubBrain:
    def __init__(self, configs=None):
        self.configs = configs or pipeline._dummy_test_configs()

    def single_call(self, prompt, system_prompt, pinned_index=None):
        if "startup market research expert" in system_prompt:
            return json.dumps({
                "keywords": ["invoice automation", "freelance invoicing", "late payments", "payment reminders"],
                "colloquial_keywords": ["clients keep paying late", "hate chasing invoices", "need help getting paid"],
                "subreddits": ["freelance", "graphic_design", "smallbusiness"],
                "competitors": ["FreshBooks", "Wave", "Stripe Invoicing"],
                "audience": "Freelance designers and solo service businesses",
                "pain_hypothesis": "Getting paid is manual, awkward, and time-consuming",
                "search_queries": ["freelance invoice reminder", "late client payment"],
            })

        if "market signal extractor" in system_prompt.lower():
            return json.dumps({
                "pain_quotes": [
                    "I hate chasing invoices every month.",
                    "Clients keep paying late and it wrecks cash flow.",
                ],
                "wtp_signals": ["I'd pay for invoice reminders if it saved me time."],
                "competitor_mentions": ["FreshBooks", "Wave"],
                "key_insight": "Freelancers consistently complain about awkward payment follow-up.",
            })

        if "market research analyst" in system_prompt.lower():
            return json.dumps({
                "pain_validated": True,
                "pain_description": "Freelancers are frustrated by repeated invoice follow-ups and late payments.",
                "pain_frequency": "weekly",
                "pain_intensity": "HIGH",
                "willingness_to_pay": "Multiple posts indicate willingness to pay for less awkward payment reminders.",
                "market_timing": "GROWING",
                "tam_estimate": "Large global freelance market with recurring invoice pain.",
                "evidence": [
                    {
                        "post_title": "Clients keep paying late",
                        "source": "reddit",
                        "score": 42,
                        "what_it_proves": "Late payments are a repeated operational pain point.",
                    },
                    {
                        "post_title": "Need help chasing unpaid invoices",
                        "source": "reddit",
                        "score": 35,
                        "what_it_proves": "Founders actively seek alternatives for invoice follow-up.",
                    },
                ],
            })

        if "startup strategist" in system_prompt.lower():
            return json.dumps({
                "ideal_customer_profile": {
                    "primary_persona": "Freelance designer juggling multiple client invoices",
                    "demographics": "Solo operators, 25-45, remote-first",
                    "psychographics": "Values cash flow, hates awkward collection conversations",
                    "specific_communities": [{"name": "r/freelance", "subscribers": "300000", "relevance": "PRIMARY"}],
                    "influencers_they_follow": ["Creative Boom"],
                    "tools_they_already_use": ["FreshBooks", "Wave"],
                    "buying_objections": ["Worried about trusting an automated reminder tool with clients"],
                    "previous_solutions_tried": ["Manual reminders", "FreshBooks automations"],
                    "day_in_the_life": "Sends invoices in the morning, follows up manually in the afternoon.",
                    "willingness_to_pay_evidence": ["Would pay to avoid awkward collections."],
                    "budget_range": "$15-$49/mo",
                    "buying_triggers": ["Late invoices", "Cash flow crunch"],
                },
                "competition_landscape": {
                    "market_saturation": "HIGH",
                    "total_products_found": 5,
                    "direct_competitors": [
                        {"name": "FreshBooks", "price": "$17/mo", "weakness": "Generic invoicing, weak follow-up UX"},
                        {"name": "Wave", "price": "Free", "weakness": "Limited reminder intelligence"},
                    ],
                    "indirect_competitors": ["Stripe Invoicing"],
                    "your_unfair_advantage": "Founder-friendly invoice follow-up workflows built around freelancer tone.",
                },
                "pricing_strategy": {
                    "recommended_model": "subscription",
                    "price_range": "$19-$39/mo",
                },
                "monetization_channels": [{"channel": "Subscription", "timeline": "Immediate"}],
            })

        if "startup launch advisor" in system_prompt.lower():
            return json.dumps({
                "launch_roadmap": [
                    {"step": "Build invoice reminder MVP"},
                    {"step": "Test with 10 freelancers"},
                    {"step": "Launch onboarding flow"},
                ],
                "revenue_projections": {
                    "month_1": {"mrr": "$190", "users": "50", "paying": "10"},
                    "month_6": {"mrr": "$950", "users": "250", "paying": "50"},
                },
                "risk_matrix": [
                    {"risk": "Clients dislike automated tone", "severity": "MEDIUM"},
                    {"risk": "Competition from invoicing suites", "severity": "HIGH"},
                ],
                "first_10_customers_strategy": {
                    "customers_1_3": {"tactic": "DM freelancers in communities"},
                },
                "mvp_features": ["Invoice reminders", "Payment status tracking"],
            })

        return json.dumps({"ok": True})

    def debate(self, prompt, system_prompt, on_progress=None, metadata=None):
        if on_progress:
            on_progress("debating", "Round 1: 3 models analyzing independently")
            on_progress("debating", "Round 2: Models debating with hidden scores")
        return {
            "verdict": "BUILD_IT",
            "confidence": 72,
            "executive_summary": "Strong buyer pain exists, but differentiation must stay focused on freelancer collections.",
            "summary": "Strong buyer pain exists, but differentiation must stay focused on freelancer collections.",
            "evidence": [
                {"title": "Clients keep paying late", "source": "reddit", "score": 42},
                {"title": "Need help chasing unpaid invoices", "source": "reddit", "score": 35},
            ],
            "evidence_count": 2,
            "risk_factors": ["Competition from invoicing suites"],
            "suggestions": ["Start with freelancers already using generic invoicing tools"],
            "action_plan": ["Launch reminder MVP"],
            "top_posts": [
                {"title": "Clients keep paying late", "source": "reddit", "score": 42},
            ],
            "top_unknowns": ["Churn after first successful invoice cycle"],
            "models_used": [
                "nvidia/test-bull-model",
                "nvidia/test-skeptic-model",
                "openrouter/test-analyst-model",
            ],
            "model_verdicts": {
                "nvidia/test-bull-model": {"verdict": "BUILD_IT", "role": "BULL"},
                "nvidia/test-skeptic-model": {"verdict": "RISKY", "role": "SKEPTIC"},
                "openrouter/test-analyst-model": {"verdict": "BUILD_IT", "role": "MARKET_ANALYST"},
            },
            "debate_mode": True,
            "debate_log": [
                {"model": "nvidia/test-bull-model", "role": "BULL", "round": 1, "verdict": "BUILD_IT", "confidence": 80, "reasoning": "Build it", "changed": False},
                {"model": "nvidia/test-skeptic-model", "role": "SKEPTIC", "round": 2, "verdict": "RISKY", "confidence": 60, "reasoning": "Risky", "changed": False},
            ],
            "debate_transcript": {
                "models": [
                    {"id": "test-bull", "provider": "nvidia", "role": "BULL"},
                    {"id": "test-skeptic", "provider": "nvidia", "role": "SKEPTIC"},
                    {"id": "test-analyst", "provider": "openrouter", "role": "MARKET_ANALYST"},
                ],
                "rounds": [
                    {
                        "round": 1,
                        "entries": [
                            {"model_id": "test-bull", "role": "BULL", "verdict": "BUILD_IT", "confidence": 80, "confidence_delta": 0, "held": True, "argument_text": "Freelancers hate chasing invoices.", "engagement_score": 0, "engagement_label": "Initial position"},
                        ],
                    },
                    {
                        "round": 2,
                        "entries": [
                            {"model_id": "test-skeptic", "role": "SKEPTIC", "verdict": "RISKY", "confidence": 60, "confidence_delta": 0, "held": True, "argument_text": "Still risky because incumbents exist.", "engagement_score": 1, "engagement_label": "Partial engagement (1/2 models)"},
                        ],
                    },
                ],
                "round2_summary": "One model changed its tone but not the final verdict.",
                "final": {
                    "verdict": "BUILD_IT",
                    "confidence": 72,
                    "weights": [
                        {"model_id": "test-bull", "role": "BULL", "weight": 1.2, "verdict": "BUILD_IT"},
                    ],
                    "dissent": {
                        "exists": True,
                        "dissenting_model_id": "test-skeptic",
                        "dissenting_role": "SKEPTIC",
                        "dissenting_verdict": "RISKY",
                        "dissent_reason": "Still risky because incumbents exist.",
                    },
                },
            },
        }


def _make_reddit_child(index, title, body, subreddit="freelance", score=10):
    return {
        "kind": "t3",
        "data": {
            "id": f"reddit-{index}",
            "title": title,
            "selftext": body,
            "score": score,
            "upvote_ratio": 0.9,
            "num_comments": 5 + index,
            "created_utc": 1710892800 + index,
            "subreddit": subreddit,
            "permalink": f"/r/{subreddit}/comments/{index}/example/",
            "author": f"user{index}",
            "url": f"https://reddit.com/r/{subreddit}/comments/{index}/example/",
        },
    }


def test_phase1_decomposition(load_user_configs):
    result = pipeline.run_phase1(
        "invoice chasing for freelancers",
        brain=StubBrain(load_user_configs()),
        test_mode=True,
    )
    assert result["keywords"] is not None
    assert len(result["keywords"]) >= 3
    assert result["subreddits"] is not None
    assert result["competitors"] is not None
    print(f"Phase 1: {len(result['keywords'])} keywords, {len(result['subreddits'])} subreddits")


def test_reddit_scraping(monkeypatch):
    start = time.time()

    monkeypatch.setattr(keyword_scraper.time, "sleep", lambda _: None)
    monkeypatch.setattr(keyword_scraper, "_select_subreddits", lambda keywords, forced_subreddits=None: ["freelance", "graphic_design"])
    monkeypatch.setattr(keyword_scraper, "search_reddit", lambda keywords, after="", limit=100: ([
        _make_reddit_child(1, "Freelancers need help chasing invoices", "Late client payments are a problem."),
        _make_reddit_child(2, "How do I automate invoice reminders?", "Looking for a better workflow."),
    ], ""))
    monkeypatch.setattr(keyword_scraper, "search_subreddit", lambda subreddit, keywords, after="", limit=100: ([
        _make_reddit_child(10, f"{subreddit} invoice reminder workflow", "Need help getting paid faster.", subreddit=subreddit, score=7),
    ], ""))

    fake_reddit_async = types.SimpleNamespace(AIOHTTP_AVAILABLE=False, scrape_all_async=lambda *args, **kwargs: [])
    fake_pullpush = types.SimpleNamespace(scrape_historical=lambda *args, **kwargs: [])
    monkeypatch.setitem(sys.modules, "reddit_async", fake_reddit_async)
    monkeypatch.setitem(sys.modules, "pullpush_scraper", fake_pullpush)

    posts = keyword_scraper.run_keyword_scan(
        ["invoice", "freelance payment"],
        duration="10min",
        min_keyword_matches=1,
    )
    elapsed = time.time() - start
    assert elapsed < 30, f"Reddit took {elapsed}s - too slow"
    assert len(posts) > 0, "Reddit returned 0 posts"
    print(f"Reddit: {len(posts)} posts in {elapsed:.1f}s")


def test_primary_filter(generate_mock_posts):
    mock_posts = generate_mock_posts(50)
    passed = pipeline.apply_primary_filter(mock_posts, "invoice freelance")
    pass_rate = len(passed) / len(mock_posts)
    assert 0.15 < pass_rate < 0.70, f"Filter pass rate {pass_rate:.0%} - out of range"
    print(f"Filter: {len(passed)}/50 passed ({pass_rate:.0%})")


def test_synthesis_pass1(get_sample_posts, load_user_configs):
    brain = StubBrain(load_user_configs())
    result = pipeline.run_synthesis_pass1(
        brain=brain,
        posts=get_sample_posts(20),
        idea="invoice chasing for freelancers",
        test_mode=True,
    )
    assert result is not None
    assert "pain_validated" in result
    assert "evidence" in result
    print(
        f"Synthesis Pass 1: pain_validated={result['pain_validated']}, "
        f"{len(result.get('evidence', []))} evidence points"
    )


def test_debate_engine(monkeypatch, load_user_configs):
    from engine import multi_brain as multi_brain_module

    def fake_call_provider(config, prompt, system_prompt):
        role = "ANALYST"
        prompt_upper = prompt.upper()
        system_upper = system_prompt.upper()
        if "BULL" in system_upper:
            role = "BULL"
        elif "SKEPTIC" in system_upper:
            role = "SKEPTIC"
        elif "MARKET_ANALYST" in system_upper or "MARKET ANALYST" in system_upper:
            role = "MARKET_ANALYST"

        round2 = "OTHER MODELS' REASONING" in prompt_upper or "YOUR ORIGINAL ANALYSIS" in prompt_upper

        if round2:
            payload = {
                "verdict": "BUILD_IT" if role != "SKEPTIC" else "RISKY",
                "confidence": 76 if role == "BULL" else (62 if role == "SKEPTIC" else 71),
                "evidence": [f"{role} follow-up evidence"],
                "suggestions": [f"{role} suggestion"],
                "risk_factors": [f"{role} risk"],
                "action_plan": [f"{role} action"],
                "top_posts": [{"title": f"{role} top post"}],
                "top_unknowns": ["Unknown retention effect"],
                "summary": f"{role} round 2 summary",
                "debate_note": f"[BULL] and [SKEPTIC] arguments were considered by {role}.",
            }
        else:
            payload = {
                "verdict": "BUILD_IT" if role != "SKEPTIC" else "RISKY",
                "confidence": 80 if role == "BULL" else (60 if role == "SKEPTIC" else 70),
                "evidence": [f"{role} evidence point"],
                "suggestions": [f"{role} suggestion"],
                "risk_factors": [f"{role} risk"],
                "action_plan": [f"{role} action"],
                "top_posts": [{"title": f"{role} top post"}],
                "top_unknowns": ["Unknown retention effect"],
                "executive_summary": f"{role} sees meaningful demand.",
                "summary": f"{role} sees meaningful demand.",
            }

        return config["provider"], config["selected_model"], json.dumps(payload)

    monkeypatch.setattr(multi_brain_module, "call_provider", fake_call_provider)

    brain = MultiBrain(load_user_configs())
    result = brain.debate(
        prompt="Strong demand signal for invoice chasing among freelancers.",
        system_prompt="Return JSON with verdict, confidence, evidence, suggestions, action_plan, risk_factors, top_posts, top_unknowns, summary, debate_note.",
        metadata={},
    )
    assert result["verdict"] in ["BUILD_IT", "RISKY", "DONT_BUILD"]
    assert 0 < result["confidence"] <= 100
    assert len(result.get("models_used", [])) >= 1
    print(f"Debate: {result['verdict']} ({result['confidence']}%) - {len(result.get('models_used', []))} models")


def test_competition_tier():
    result = analyze_competition(
        keywords=["invoice software"],
        idea_text="invoice automation for freelancers",
        known_competitors=["FreshBooks", "Wave", "Stripe"],
    )
    summary = competition_summary(result)
    assert summary["overall_tier"] != "BLUE_OCEAN", "BLUE_OCEAN with 3 known competitors - bug!"
    print(f"Competition: {summary['overall_tier']} (not BLUE_OCEAN)")


def test_full_pipeline_quick(monkeypatch, get_sample_posts, load_user_configs):
    start = time.time()

    monkeypatch.setattr(pipeline, "AIBrain", StubBrain)
    monkeypatch.setattr(pipeline, "DEATHWATCH_AVAILABLE", False)
    monkeypatch.setattr(pipeline, "PAIN_STREAM_AVAILABLE", False)

    sample_posts = get_sample_posts(24)
    source_counts = {"reddit": 12, "hackernews": 8, "indiehackers": 4}
    intel = {
        "trends": {"available": True, "overall_trend": "GROWING"},
        "competition": {"available": True, "overall_tier": "EMERGING"},
        "trend_prompt": "",
        "comp_prompt": "",
    }

    monkeypatch.setattr(
        pipeline,
        "phase2_scrape",
        lambda *args, **kwargs: (sample_posts, source_counts, []),
    )
    monkeypatch.setattr(
        pipeline,
        "phase2b_intelligence",
        lambda *args, **kwargs: intel,
    )

    result = pipeline.validate_idea(
        idea="invoice chasing for freelancers",
        depth="quick",
        test_mode=True,
    )
    elapsed = time.time() - start
    assert elapsed < 180, f"Quick validation took {elapsed}s"
    assert result["verdict"] in ["BUILD_IT", "RISKY", "DONT_BUILD"]
    assert result["confidence"] > 0
    assert len(result.get("debate_evidence", [])) > 0, "Empty evidence - synthesis failed"
    print(f"Full pipeline: {result['verdict']} ({result['confidence']}%) in {elapsed:.0f}s")
