import os
import sys
from pathlib import Path

import pytest
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _read_env_local():
    env_path = PROJECT_ROOT / "app" / ".env.local"
    values = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


@pytest.fixture(scope="session")
def env_config():
    return _read_env_local()


@pytest.fixture
def load_user_configs(env_config):
    def _load():
        configs = []
        providers = [
            ("GEMINI_API_KEY", "gemini", "gemini-2.0-flash"),
            ("GROQ_API_KEY", "groq", "llama-3.3-70b-versatile"),
            ("OPENAI_API_KEY", "openai", "gpt-4o"),
            ("OPENROUTER_API_KEY", "openrouter", "qwen/qwen3.5-flash-02-23"),
        ]
        for priority, (env_key, provider, model) in enumerate(providers, start=1):
            if env_config.get(env_key):
                configs.append({
                    "id": f"fixture-{provider}",
                    "provider": provider,
                    "api_key": env_config[env_key],
                    "selected_model": model,
                    "is_active": True,
                    "priority": priority,
                })

        if configs:
            return configs

        return [
            {
                "id": "fixture-bull",
                "provider": "nvidia",
                "api_key": "test-key",
                "selected_model": "fixture-bull-model",
                "is_active": True,
                "priority": 1,
            },
            {
                "id": "fixture-skeptic",
                "provider": "nvidia",
                "api_key": "test-key",
                "selected_model": "fixture-skeptic-model",
                "is_active": True,
                "priority": 2,
            },
            {
                "id": "fixture-analyst",
                "provider": "openrouter",
                "api_key": "test-key",
                "selected_model": "fixture-analyst-model",
                "is_active": True,
                "priority": 3,
            },
        ]

    return _load


@pytest.fixture
def generate_mock_posts():
    def _generate(n=50):
        posts = []
        relevant_count = max(1, int(n * 0.4))
        for index in range(n):
            relevant = index < relevant_count
            source = "reddit" if index % 3 != 0 else "hackernews"
            subreddit = "freelance" if relevant else "funny"
            title = (
                f"Invoice follow up problem {index}: freelancers need help getting paid"
                if relevant
                else f"Totally unrelated meme thread {index}"
            )
            body = (
                "Freelancers are struggling with invoice reminders and late client payments."
                if relevant
                else "This is a joke post with no buyer pain or workflow signal."
            )
            matched_keywords = ["invoice", "freelance"] if relevant else []
            posts.append({
                "id": f"mock-{index}",
                "external_id": f"mock-{index}",
                "title": title,
                "selftext": body,
                "body": body,
                "full_text": f"{title} {body}",
                "score": 8 if relevant else 1,
                "num_comments": 5 + index,
                "created_utc": "2026-03-20T00:00:00+00:00",
                "subreddit": subreddit,
                "source": source,
                "permalink": f"https://example.com/posts/{index}",
                "url": f"https://example.com/posts/{index}",
                "matched_keywords": matched_keywords,
            })
        return posts

    return _generate


@pytest.fixture
def get_sample_posts(env_config, generate_mock_posts):
    def _normalize_post(row, index):
        title = str(row.get("title") or row.get("post_title") or f"Sample post {index}")
        body = str(row.get("body") or row.get("selftext") or row.get("full_text") or "")
        return {
            "id": str(row.get("id") or row.get("external_id") or f"sample-{index}"),
            "external_id": str(row.get("external_id") or row.get("id") or f"sample-{index}"),
            "title": title,
            "selftext": body,
            "body": body,
            "full_text": f"{title} {body}".strip(),
            "score": int(row.get("score", 5) or 5),
            "num_comments": int(row.get("num_comments", 0) or 0),
            "created_utc": str(row.get("created_utc") or row.get("created_at") or "2026-03-20T00:00:00+00:00"),
            "subreddit": str(row.get("subreddit") or "freelance"),
            "source": str(row.get("source") or "reddit"),
            "permalink": str(row.get("permalink") or row.get("url") or f"https://example.com/sample/{index}"),
            "url": str(row.get("url") or row.get("permalink") or f"https://example.com/sample/{index}"),
            "matched_keywords": row.get("matched_keywords") or ["invoice", "freelance"],
        }

    def _fetch(n=20):
        supabase_url = env_config.get("NEXT_PUBLIC_SUPABASE_URL") or env_config.get("SUPABASE_URL")
        supabase_key = (
            env_config.get("SUPABASE_SERVICE_ROLE_KEY")
            or env_config.get("SUPABASE_SECRET_KEY")
            or env_config.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        )

        if supabase_url and supabase_key:
            try:
                response = requests.get(
                    f"{supabase_url}/rest/v1/posts",
                    headers={
                        "apikey": supabase_key,
                        "Authorization": f"Bearer {supabase_key}",
                    },
                    params={
                        "select": "*",
                        "limit": n,
                        "order": "created_at.desc",
                    },
                    timeout=10,
                )
                if response.status_code == 200:
                    rows = response.json() or []
                    if rows:
                        return [_normalize_post(row, index) for index, row in enumerate(rows[:n])]
            except requests.RequestException:
                pass

        return generate_mock_posts(n)

    return _fetch
