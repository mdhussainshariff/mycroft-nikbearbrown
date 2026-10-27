"""
ingest/fetch_news.py  —  Sprint 1 (second half): basic real-data ingestion.

Pulls recent news items from public RSS feeds, keeps the ones that mention one of
our tracked AI vendors, and turns each into a CANDIDATE signal (unvalidated).

Design honesty:
- This is BASIC ingestion, per Sprint 1. It just fetches and shapes raw items.
  The *smart* gathering (an agent deciding what to search, looping) is Sprint 2.
- Every candidate is UNVALIDATED (validated_by = None). Per P2, a human must
  validate before anything counts. Ingestion gathers; the human still judges.
- Signal type here is always 'news_mention' with a low confidence score. Turning
  a headline into a precise funding_round/amount is the LLM extraction job (Sprint 3),
  not this step.

Requires: feedparser  (pip install feedparser)  — already in requirements.txt

Usage:
    python -m ingest.fetch_news                 # fetch + print candidates
    python -m ingest.fetch_news --out data/raw/news_signals.json   # also save
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import feedparser
except ImportError:
    print("feedparser not installed. Run: pip install -r requirements.txt", file=sys.stderr)
    raise

# --- config: which vendors to track, and which public feeds to read -----------
# Edit these freely. company_id is the stable slug; aliases are what we match in text.
TRACKED_VENDORS = {
    "openai":       ["openai", "chatgpt", "sam altman"],
    "anthropic":    ["anthropic", "claude"],
    "google-ai":    ["gemini", "deepmind", "google ai"],
    "nvidia":       ["nvidia"],
    "meta-ai":      ["meta ai", "llama"],
}

# Public tech-news RSS feeds. No API key needed.
FEEDS = [
    "https://techcrunch.com/feed/",
    "https://venturebeat.com/feed/",
    "https://www.theverge.com/rss/index.xml",
]


def match_vendor(text: str) -> str | None:
    """Return the company_id if the text mentions a tracked vendor, else None."""
    low = text.lower()
    for company_id, aliases in TRACKED_VENDORS.items():
        if any(alias in low for alias in aliases):
            return company_id
    return None


def entry_date(entry) -> str:
    """Best-effort published date -> ISO string; fall back to today."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                d = date(t.tm_year, t.tm_mon, t.tm_mday)
                if d <= date.today():
                    return d.isoformat()
            except Exception:
                pass
    return date.today().isoformat()


def make_candidate(company_id: str, entry) -> dict:
    """Shape one feed entry into a candidate signal dict (schema-shaped, UNVALIDATED)."""
    title = getattr(entry, "title", "").strip()
    link = getattr(entry, "link", "").strip()
    sid = "news-" + hashlib.sha1((company_id + title + link).encode()).hexdigest()[:12]
    return {
        "signal_id": sid,
        "company_id": company_id,
        "signal_type": "news_mention",     # basic ingest: everything is a mention
        "signal_title": title[:200] or "news item",
        "signal_value": "neutral",         # LLM extraction (Sprint 3) refines this
        "occurred_date": entry_date(entry),
        "source_url": link or "https://example.com/no-link",
        "score": 40,                       # news is low-confidence by default
        "validated_by": None,              # P2: a human must validate before it counts
    }


def fetch() -> list[dict]:
    """Read all feeds, keep entries that mention a tracked vendor, shape candidates."""
    candidates: list[dict] = []
    seen_ids: set[str] = set()
    for url in FEEDS:
        print(f"[fetch] reading {url}", file=sys.stderr)
        parsed = feedparser.parse(url)
        for entry in getattr(parsed, "entries", []):
            text = f"{getattr(entry,'title','')} {getattr(entry,'summary','')}"
            company_id = match_vendor(text)
            if not company_id:
                continue
            cand = make_candidate(company_id, entry)
            if cand["signal_id"] in seen_ids:
                continue
            seen_ids.add(cand["signal_id"])
            candidates.append(cand)
    return candidates


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="optional path to save candidates as JSON")
    args = ap.parse_args()

    candidates = fetch()

    print("\nREAL-DATA INGESTION (basic, Sprint 1)")
    print("=" * 50)
    print(f"Tracked vendors: {', '.join(TRACKED_VENDORS)}")
    print(f"Candidate signals found: {len(candidates)}")
    print("(all UNVALIDATED — a human must validate before they count)\n")
    for c in candidates:
        print(f"  - {c['company_id']}: {c['signal_title'][:70]}")
        print(f"      {c['occurred_date']}  {c['source_url']}")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump(candidates, fh, indent=2)
        print(f"\n[saved] {len(candidates)} candidates -> {args.out}")
        print("Next: run these through the validator:")
        print(f"  python -m ingest.load_signals {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
