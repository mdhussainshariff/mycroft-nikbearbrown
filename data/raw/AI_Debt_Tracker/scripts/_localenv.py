"""Load this project's gitignored .env into os.environ, so machine-specific paths stay out of the repo.

Plain KEY=VALUE lines; '#' starts a comment. Variables already set in the environment win, and
placeholder values ("<...>") are ignored. Imported for its side effect by the scripts in this folder.
"""

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load(path=ENV_FILE):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if value and not value.startswith("<"):
            os.environ.setdefault(key, value)


load()
