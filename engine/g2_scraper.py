"""
Lightweight G2 review scraper for competitor pain signals.
Focuses on extracting recent low-rating review snippets and common complaint themes.
"""

from __future__ import annotations

import re
import time
from collections import Counter

import requests


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15",
]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


class G2Scraper:
    BASE_URL = "https://www.g2.com/products"

    def __init__(self):
        self.last_status_code = None
        self.last_url = ""
        self.last_error = ""

    def _headers(self, idx: int = 0):
        return {
            "User-Agent": USER_AGENTS[idx % len(USER_AGENTS)],
            "Accept-Language": "en-US,en;q=0.9",
        }

    def scrape_competitor_reviews(self, product_slug: str, max_reviews: int = 50):
        url = f"{self.BASE_URL}/{product_slug}/reviews"
        reviews = []
        self.last_url = url
        self.last_status_code = None
        self.last_error = ""

        try:
            response = requests.get(url, headers=self._headers(), timeout=20)
            self.last_status_code = response.status_code
            if response.status_code != 200:
                self.last_error = f"http_{response.status_code}"
                return reviews

            html = response.text
            blocks = re.split(r'data-testid="review-item"|class="paper paper--white review"', html)
            for block in blocks[1:max_reviews + 1]:
                title_match = re.search(r'aria-label="Review title">\s*([^<]+)', block)
                dislikes_match = re.search(r"What do you dislike\?\s*</[^>]+>\s*<[^>]+>(.*?)</", block, re.I | re.S)
                likes_match = re.search(r"What do you like best\?\s*</[^>]+>\s*<[^>]+>(.*?)</", block, re.I | re.S)
                rating_match = re.search(r'(\d(?:\.\d)?)\s*out of 5', block)
                industry_match = re.search(r'Industry:\s*</[^>]+>\s*<[^>]+>(.*?)</', block, re.I | re.S)
                company_match = re.search(r'Company Size:\s*</[^>]+>\s*<[^>]+>(.*?)</', block, re.I | re.S)
                date_match = re.search(r'datetime="([^"]+)"', block)

                rating = int(float(rating_match.group(1))) if rating_match else 0

                dislikes = _clean(dislikes_match.group(1)) if dislikes_match else ""
                if not dislikes:
                    continue

                reviews.append({
                    "product": product_slug,
                    "rating": rating or 0,
                    "title": _clean(title_match.group(1)) if title_match else "",
                    "dislikes": dislikes,
                    "likes": _clean(likes_match.group(1)) if likes_match else "",
                    "use_case": "",
                    "industry": _clean(industry_match.group(1)) if industry_match else "",
                    "company_size": _clean(company_match.group(1)) if company_match else "",
                    "date": date_match.group(1) if date_match else "",
                })
                time.sleep(0.25)
        except Exception as exc:
            self.last_error = str(exc)[:200]
            return reviews

        return reviews[:max_reviews]

    def get_top_complaints(self, product_slug: str, top_n: int = 10):
        reviews = self.scrape_competitor_reviews(product_slug, max_reviews=100)
        phrases = []
        for review in reviews:
            text = re.sub(r"[^a-z0-9\s]", " ", review.get("dislikes", "").lower())
            words = [word for word in text.split() if len(word) > 3]
            phrases.extend(" ".join(words[i:i + 2]) for i in range(len(words) - 1))

        top = Counter(phrases).most_common(top_n)
        return [{"phrase": phrase, "count": count} for phrase, count in top if phrase.strip()]


def scrape_g2_signals(product_slug: str):
    scraper = G2Scraper()
    reviews = scraper.scrape_competitor_reviews(product_slug, max_reviews=30)
    return {
        "reviews": reviews,
        "total": len(reviews),
        "top_complaints": scraper.get_top_complaints(product_slug, top_n=10),
    }
