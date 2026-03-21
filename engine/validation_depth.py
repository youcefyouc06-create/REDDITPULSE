"""
Validation Depth Mode configurations.

Each mode defines budget parameters that control evidence collection depth
across the entire pipeline — from Phase 1 keyword decomposition through
Phase 2 scraping to Phase 3 evidence sampling.

Usage:
    from validation_depth import get_depth_config
    config = get_depth_config("deep")
    reddit_duration = config["reddit_duration"]  # "1h"
"""

DEPTH_CONFIGS = {
    "quick": {
        "mode": "quick",
        "label": "Quick Validation",
        "description": "Fast first-pass screening",
        "target_duration_minutes": 5,
        # Phase 1 decomposition caps
        "formal_keyword_cap": 15,
        "colloquial_keyword_cap": 10,
        "subreddit_cap": 8,
        # Reddit collection
        "reddit_colloquial_budget": 4,
        "reddit_formal_budget": 4,
        "reddit_duration": "10min",
        "reddit_min_keyword_matches": 1,
        # Cross-source: HN / PH / IH
        "hn_keyword_budget": 8,
        "hn_max_pages": 2,
        "ph_keyword_budget": 8,
        "ph_max_pages": 2,
        "ih_keyword_budget": 8,
        "ih_max_pages": 2,
        # Cross-source: SO / GH
        "so_keyword_budget": 3,
        "so_time_budget": 30,
        "so_pages": 1,
        "gh_keyword_budget": 3,
        "gh_time_budget": 30,
        "gh_pages": 1,
        # Evidence sampling
        "evidence_sample_budget": 100,
        # Method depth — evidence knobs
        "fallback_rescue_threshold": 10,
        "batch_pain_cap": 25,
        "batch_wtp_cap": 15,
        "batch_comp_cap": 10,
        "batch_insight_cap": 20,
        "pass3_competitor_depth": 5,
        # Enrichment
        "competitor_sweep_depth": 1,
        "enable_extra_enrichment": False,
        "enable_followup_recheck": False,
        # Queue
        "queue_timeout_seconds": 20 * 60,
    },
    "deep": {
        "mode": "deep",
        "label": "Deep Validation",
        "description": "Broader market scan with stronger evidence",
        "target_duration_minutes": 35,
        "formal_keyword_cap": 18,
        "colloquial_keyword_cap": 12,
        "subreddit_cap": 10,
        "reddit_colloquial_budget": 6,
        "reddit_formal_budget": 6,
        "reddit_duration": "10min",
        "reddit_min_keyword_matches": 1,
        "hn_keyword_budget": 10,
        "hn_max_pages": 3,
        "ph_keyword_budget": 10,
        "ph_max_pages": 3,
        "ih_keyword_budget": 10,
        "ih_max_pages": 3,
        "so_keyword_budget": 5,
        "so_time_budget": 45,
        "so_pages": 2,
        "gh_keyword_budget": 5,
        "gh_time_budget": 45,
        "gh_pages": 2,
        "evidence_sample_budget": 150,
        # Method depth — evidence knobs
        "fallback_rescue_threshold": 15,
        "batch_pain_cap": 35,
        "batch_wtp_cap": 20,
        "batch_comp_cap": 15,
        "batch_insight_cap": 30,
        "pass3_competitor_depth": 8,
        # Enrichment
        "competitor_sweep_depth": 2,
        "enable_extra_enrichment": True,
        "enable_followup_recheck": False,
        "queue_timeout_seconds": 60 * 60,
    },
    "investigation": {
        "mode": "investigation",
        "label": "Market Investigation",
        "description": "Exhaustive premium research for serious decisions",
        "target_duration_minutes": 100,
        "formal_keyword_cap": 20,
        "colloquial_keyword_cap": 15,
        "subreddit_cap": 12,
        "reddit_colloquial_budget": 8,
        "reddit_formal_budget": 8,
        "reddit_duration": "10min",
        "reddit_min_keyword_matches": 1,
        "hn_keyword_budget": 12,
        "hn_max_pages": 4,
        "ph_keyword_budget": 12,
        "ph_max_pages": 4,
        "ih_keyword_budget": 12,
        "ih_max_pages": 4,
        "so_keyword_budget": 6,
        "so_time_budget": 60,
        "so_pages": 2,
        "gh_keyword_budget": 6,
        "gh_time_budget": 60,
        "gh_pages": 2,
        "evidence_sample_budget": 180,
        # Method depth — evidence knobs
        "fallback_rescue_threshold": 20,
        "batch_pain_cap": 50,
        "batch_wtp_cap": 30,
        "batch_comp_cap": 20,
        "batch_insight_cap": 40,
        "pass3_competitor_depth": 10,
        # Enrichment
        "competitor_sweep_depth": 3,
        "enable_extra_enrichment": True,
        "enable_followup_recheck": True,  # Flag only — no-op in v1
        "queue_timeout_seconds": 150 * 60,
    },
}

VALID_MODES = tuple(DEPTH_CONFIGS.keys())


def get_depth_config(mode: str = "quick") -> dict:
    """Return the depth config dict for the given mode. Falls back to 'quick'."""
    return DEPTH_CONFIGS.get(mode, DEPTH_CONFIGS["quick"]).copy()


def log_depth_config(config: dict) -> None:
    """Print observability block for the active depth mode."""
    mode = config.get("mode", "unknown")
    print(f"  [Mode] {mode}")
    print(f"  [Reddit] lookback={config.get('reddit_duration')}, "
          f"keyword_budget={config.get('reddit_colloquial_budget', 0) + config.get('reddit_formal_budget', 0)}, "
          f"subreddits={config.get('subreddit_cap')}, "
          f"min_matches={config.get('reddit_min_keyword_matches')}")
    print(f"  [HN] keyword_budget={config.get('hn_keyword_budget')}, max_pages={config.get('hn_max_pages')}")
    print(f"  [PH] keyword_budget={config.get('ph_keyword_budget')}, max_pages={config.get('ph_max_pages')}")
    print(f"  [IH] keyword_budget={config.get('ih_keyword_budget')}, max_pages={config.get('ih_max_pages')}")
    print(f"  [SO] keyword_budget={config.get('so_keyword_budget')}, "
          f"time_budget={config.get('so_time_budget')}s, pages={config.get('so_pages')}")
    print(f"  [GH] keyword_budget={config.get('gh_keyword_budget')}, "
          f"time_budget={config.get('gh_time_budget')}s, pages={config.get('gh_pages')}")
    print(f"  [Evidence] sample_budget={config.get('evidence_sample_budget')}")
    print(f"  [Method] fallback_rescue={config.get('fallback_rescue_threshold')}, "
          f"batch_caps=pain:{config.get('batch_pain_cap')}/wtp:{config.get('batch_wtp_cap')}/"
          f"comp:{config.get('batch_comp_cap')}/insight:{config.get('batch_insight_cap')}, "
          f"pass3_comp_depth={config.get('pass3_competitor_depth')}")
    print(f"  [Enrichment] competitor_sweep={config.get('competitor_sweep_depth')}, "
          f"extra={config.get('enable_extra_enrichment')}, "
          f"recheck={'reserved' if config.get('enable_followup_recheck') else 'off'}")
