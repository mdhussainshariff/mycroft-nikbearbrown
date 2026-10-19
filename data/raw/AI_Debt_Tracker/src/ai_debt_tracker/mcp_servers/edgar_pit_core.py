"""Point-in-time EDGAR: the agent's only window onto SEC filings, and the place look-ahead is refused.

DESIGN.md P11: the agent must never see the report it is graded on, or anything filed after it.
This module is that rule as code, kept apart from the MCP binding (`edgar_pit.py`) so it can be
tested without a server:

* Started with an `as_of` cut-off (EDGAR acceptance time, **exclusive**) and an optional set of
  excluded accessions (the episode's target report).
* `timeline` only lists filings accepted before the cut-off. It does not say how many it held
  back — a count of later filings would itself leak the future.
* `exhibits` and `fetch` **refuse** (raise `Refused`) any accession that is unknown for the
  company, accepted at or after the cut-off, or excluded. Fail closed: an accession we cannot
  date is treated as the future.
* Every call, allowed or refused, is appended to a JSONL access log, so a backtest can prove
  afterwards what the agent did and did not read.

Times: cut-offs are compared with EDGAR's `acceptanceDateTime` exactly as EDGAR writes it, as
`YYYY-MM-DDTHH:MM:SS` strings, never converted between time zones. An episode's cut-off is copied
from the target report's own `acceptanceDateTime`, so both sides are always in the same clock
(CoreWeave's June 2026 10-Q reads `2026-08-12T03:24:42.000Z`; which zone that is does not matter).
"""

from __future__ import annotations

import html
import json
import re
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .. import config
from ..edgar import ARCHIVE, FilingRef, load_filings, normalise_time  # noqa: F401 (re-exported)
from ..sec import SecClient

ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")
DOC_NAME = re.compile(r"^[\w.-]+$")
DEFAULT_MAX_CHARS = 20_000


class Refused(PermissionError):
    """A request the point-in-time rule does not allow. The message says why, never what."""


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|table)>", "\n", raw)
    raw = re.sub(r"(?i)</t[dh]>", " | ", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw)).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


class PointInTimeEdgar:
    def __init__(self, as_of: str, exclude: set[str] | None = None, client: SecClient | None = None,
                 log_path: Path | None = None):
        self.as_of = normalise_time(as_of)
        self.exclude = set(exclude or ())
        self.client = client or SecClient()
        self.log_path = log_path or config.data_dir() / "logs" / "edgar_pit_access.jsonl"
        self._index: dict[int, dict[str, FilingRef]] = {}
        self._lock = threading.Lock()

    # ---- the rule ---------------------------------------------------------------------------
    def visible(self, ref: FilingRef) -> bool:
        return ref.accepted < self.as_of and ref.accession not in self.exclude

    def _check(self, cik: int, accession: str) -> FilingRef:
        if not ACCESSION.match(accession or ""):
            raise Refused("malformed accession number")
        ref = self.index(cik).get(accession)
        if ref is None:
            raise Refused("accession is not a filing of this company (or cannot be dated)")
        if accession in self.exclude:
            raise Refused("this filing is withheld for this episode")
        if ref.accepted >= self.as_of:
            raise Refused("filing accepted at or after the cut-off")
        return ref

    # ---- index of a company's filings -------------------------------------------------------
    def index(self, cik: int) -> dict[str, FilingRef]:
        cik = int(cik)
        if cik not in self._index:
            self._index[cik] = load_filings(self.client, cik)
        return self._index[cik]

    # ---- tools ------------------------------------------------------------------------------
    def timeline(self, cik: int, start: str, end: str, forms: list[str] | None = None) -> list[dict]:
        """Filings with filing date in [start, end] that were accepted before the cut-off."""
        try:
            rows = [asdict(r) for r in sorted(self.index(cik).values(), key=lambda r: r.accepted)
                    if self.visible(r) and start <= r.filing_date <= end and (not forms or r.form in forms)]
        except Exception as ex:
            self._log("timeline", {"cik": cik, "start": start, "end": end, "forms": forms}, "error", str(ex))
            raise
        self._log("timeline", {"cik": cik, "start": start, "end": end, "forms": forms}, "ok", n=len(rows))
        return rows

    def exhibits(self, cik: int, accession: str) -> list[dict]:
        """The documents in a filing: sequence, description, file name, type (e.g. EX-99.1), size."""
        args = {"cik": cik, "accession": accession}
        try:
            self._check(cik, accession)
        except Refused as ex:
            self._log("exhibits", args, "refused", str(ex))
            raise
        url = ARCHIVE.format(cik=int(cik), acc_nodash=accession.replace("-", "")) + f"{accession}-index.htm"
        page = self.client.get(url).decode("utf-8", "ignore")
        docs = []
        for row in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", page):
            cells = [html_to_text(c) for c in re.findall(r"(?is)<td[^>]*>(.*?)</td>", row)]
            link = re.search(r'href="[^"]*/([^/"]+)"', row)
            if len(cells) >= 5 and link:
                docs.append({"seq": cells[0], "description": cells[1], "document": link.group(1).split("?")[0],
                             "type": cells[3], "size": cells[4]})
        self._log("exhibits", args, "ok", n=len(docs))
        return docs

    def fetch(self, cik: int, accession: str, doc: str, offset: int = 0, max_chars: int = DEFAULT_MAX_CHARS) -> dict:
        """One document as plain text, paged: `text` holds chars [offset, offset+max_chars)."""
        args = {"cik": cik, "accession": accession, "doc": doc, "offset": offset}
        try:
            self._check(cik, accession)
            if not DOC_NAME.match(doc or ""):
                raise Refused("document name must be a plain file name from exhibits()")
        except Refused as ex:
            self._log("fetch", args, "refused", str(ex))
            raise
        raw = self.client.get(ARCHIVE.format(cik=int(cik), acc_nodash=accession.replace("-", "")) + doc)
        text = raw.decode("utf-8", "ignore")
        if doc.lower().endswith((".htm", ".html", ".xml")) or "<html" in text[:2000].lower():
            text = html_to_text(text)
        offset = max(0, int(offset))
        chunk = text[offset: offset + max_chars]
        self._log("fetch", args, "ok", n=len(chunk))
        return {"accession": accession, "document": doc, "offset": offset, "total_chars": len(text),
                "next_offset": offset + len(chunk) if offset + len(chunk) < len(text) else None, "text": chunk}

    # ---- audit trail ------------------------------------------------------------------------
    def _log(self, tool: str, args: dict, outcome: str, reason: str = "", n: int | None = None) -> None:
        rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "as_of": self.as_of, "tool": tool,
               "args": args, "outcome": outcome}
        if reason:
            rec["reason"] = reason
        if n is not None:
            rec["n"] = n
        with self._lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
