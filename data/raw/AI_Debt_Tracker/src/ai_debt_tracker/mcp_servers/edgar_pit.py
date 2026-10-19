"""`edgar_pit` MCP server (stdio): point-in-time access to SEC filings for the agent graph.

A thin binding of `edgar_pit_core.PointInTimeEdgar` to MCP tool names; the rule lives in the core.
Configured from the environment when the process starts, so one process serves one episode:

    EDGAR_PIT_AS_OF     cut-off, EDGAR acceptance time, exclusive (required; "now" for live mode)
    EDGAR_PIT_EXCLUDE   comma-separated accessions to withhold (the episode's target report)

Run:  python -m ai_debt_tracker.mcp_servers.edgar_pit
"""

from __future__ import annotations

import os
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from .edgar_pit_core import DEFAULT_MAX_CHARS, PointInTimeEdgar, Refused


def _make() -> PointInTimeEdgar:
    as_of = os.environ.get("EDGAR_PIT_AS_OF", "").strip()
    if not as_of:
        raise SystemExit("EDGAR_PIT_AS_OF is required: the cut-off this server enforces (or 'now' for live mode)")
    if as_of == "now":
        as_of = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    exclude = {a.strip() for a in os.environ.get("EDGAR_PIT_EXCLUDE", "").split(",") if a.strip()}
    return PointInTimeEdgar(as_of, exclude)


PIT = _make()
mcp = FastMCP(
    "edgar_pit",
    instructions=(f"Point-in-time SEC EDGAR. Only filings accepted before {PIT.as_of} exist here. "
                  "Start with timeline(cik, start, end); then exhibits(cik, accession); then fetch(cik, accession, doc). "
                  "A refusal means the filing is outside this episode — do not retry it."),
)


def _refusal(ex: Refused) -> dict:
    return {"refused": True, "reason": str(ex)}


@mcp.tool()
def timeline(cik: int, start: str, end: str, forms: list[str] | None = None) -> dict:
    """Filings of one company with filing date in [start, end] (YYYY-MM-DD), oldest first, with
    form, 8-K item codes and acceptance time. Optionally restrict to `forms`, e.g. ["8-K", "FWP"]."""
    rows = PIT.timeline(cik, start, end, forms)
    return {"as_of": PIT.as_of, "count": len(rows), "filings": rows}


@mcp.tool()
def exhibits(cik: int, accession: str) -> dict:
    """The documents inside one filing (main document and exhibits such as EX-99.1 or EX-4.1)."""
    try:
        return {"accession": accession, "documents": PIT.exhibits(cik, accession)}
    except Refused as ex:
        return _refusal(ex)


@mcp.tool()
def fetch(cik: int, accession: str, doc: str, offset: int = 0) -> dict:
    """One document as plain text, at most ~20,000 characters per call; pass `next_offset` back as
    `offset` to read on."""
    try:
        return PIT.fetch(cik, accession, doc, offset, DEFAULT_MAX_CHARS)
    except Refused as ex:
        return _refusal(ex)


if __name__ == "__main__":
    mcp.run()
