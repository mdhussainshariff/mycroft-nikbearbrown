"""Paths and identity, from the environment only, so no machine path ever lands in the repo.

The project's gitignored `.env` is loaded on import (same rules as `scripts/_localenv.py`):
plain KEY=VALUE lines, variables already set in the shell win, placeholder values ("<...>") are
ignored.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"


def _load_env(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if value and not value.startswith("<"):
            os.environ.setdefault(key, value)


_load_env()


def data_dir() -> Path:
    """The local directory outside the repo that holds every bulky file (P15)."""
    return Path(os.environ.get("AI_DEBT_DATA", ROOT / "data"))


def user_agent() -> str:
    """The SEC's one rule: a declared name and contact email (P14)."""
    name = os.environ.get("EDGAR_NAME", "").strip()
    email = os.environ.get("EDGAR_EMAIL", "").strip()
    if not name or not email:
        raise RuntimeError("EDGAR_NAME and EDGAR_EMAIL must be set (in .env) before contacting the SEC")
    return f"{name} {email}"


OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
