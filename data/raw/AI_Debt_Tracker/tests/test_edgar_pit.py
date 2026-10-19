"""The point-in-time rule (DESIGN.md P11), tested offline against a fake SEC.

These are the tests the design says must fail the build: the agent's EDGAR server must refuse the
target report and anything accepted at or after the cut-off, and must log every request.
"""

import ast
import json
from pathlib import Path

import pytest

from ai_debt_tracker.mcp_servers.edgar_pit_core import PointInTimeEdgar, Refused, normalise_time
from ai_debt_tracker.sec import RateLimiter

CIK = 9999999
BEFORE, TARGET, AFTER, OLD = "0000000001-26-000001", "0000000001-26-000002", "0000000001-26-000003", "0000000001-24-000009"


class FakeSec:
    def __init__(self):
        self.calls = []

    def get(self, url, cache=True, **_):
        self.calls.append(url)
        if url.endswith(f"CIK{CIK:010d}.json"):
            return json.dumps({"filings": {"recent": {
                "accessionNumber": [AFTER, TARGET, BEFORE],
                "form": ["8-K", "10-Q", "FWP"],
                "filingDate": ["2026-08-20", "2026-08-12", "2026-05-20"],
                "acceptanceDateTime": ["2026-08-20T09:00:00.000Z", "2026-08-12T16:05:23.000Z", "2026-05-20T17:30:00.000Z"],
                "items": ["2.03", "", ""], "primaryDocument": ["a.htm", "q.htm", "fwp.htm"], "reportDate": ["", "2026-06-30", ""],
            }, "files": [{"name": "CIK9999999-submissions-001.json"}]}}).encode()
        if url.endswith("submissions-001.json"):
            return json.dumps({"accessionNumber": [OLD], "form": ["424B2"], "filingDate": ["2024-03-01"],
                               "acceptanceDateTime": ["2024-03-01T10:00:00.000Z"], "items": [""],
                               "primaryDocument": ["p.htm"], "reportDate": [""]}).encode()
        if url.endswith("-index.htm"):
            return (b'<table><tr><td>1</td><td>Term sheet</td><td><a href="/Archives/edgar/data/9999999/x/fwp.htm">fwp.htm</a></td>'
                    b"<td>FWP</td><td>4321</td></tr></table>")
        if url.endswith("fwp.htm"):
            return b"<html><p>$1,250,000,000 4.750% Notes due 2031</p><p>Settlement: May 27, 2026</p></html>"
        raise AssertionError(f"unexpected url {url}")


@pytest.fixture
def pit(tmp_path):
    # cut-off = the target report's acceptance time, exactly as an episode would set it
    return PointInTimeEdgar("2026-08-12T16:05:23.000Z", exclude={TARGET}, client=FakeSec(),
                            log_path=tmp_path / "access.jsonl")


def log(pit):
    return [json.loads(line) for line in pit.log_path.read_text().splitlines()]


def test_timeline_hides_the_target_and_the_future(pit):
    accs = [r["accession"] for r in pit.timeline(CIK, "2020-01-01", "2026-12-31")]
    assert accs == [OLD, BEFORE]            # old page included, target and later filing absent
    assert log(pit)[-1]["n"] == 2           # the log says how many were shown, never how many were held back


def test_timeline_filters_by_form_and_date(pit):
    assert [r["form"] for r in pit.timeline(CIK, "2025-01-01", "2026-12-31", ["FWP"])] == ["FWP"]
    assert pit.timeline(CIK, "2025-01-01", "2026-12-31", ["8-K"]) == []


@pytest.mark.parametrize("acc,why", [(TARGET, "withheld"), (AFTER, "cut-off"), ("0000000001-26-999999", "not a filing"),
                                     ("../../etc", "malformed")])
def test_fetch_refuses_target_future_unknown_and_malformed(pit, acc, why):
    with pytest.raises(Refused, match=why):
        pit.fetch(CIK, acc, "q.htm")
    with pytest.raises(Refused):
        pit.exhibits(CIK, acc)
    assert [e["outcome"] for e in log(pit)] == ["refused", "refused"]


def test_cutoff_is_exclusive_even_without_exclude(tmp_path):
    p = PointInTimeEdgar("2026-08-12T16:05:23", client=FakeSec(), log_path=tmp_path / "a.jsonl")
    with pytest.raises(Refused, match="cut-off"):
        p.fetch(CIK, TARGET, "q.htm")       # accepted exactly at the cut-off: not visible
    p2 = PointInTimeEdgar("2026-08-12T16:05:24", client=FakeSec(), log_path=tmp_path / "b.jsonl")
    assert TARGET in [r["accession"] for r in p2.timeline(CIK, "2026-01-01", "2026-12-31")]


def test_fetch_and_exhibits_work_before_the_cutoff(pit):
    docs = pit.exhibits(CIK, BEFORE)
    assert docs == [{"seq": "1", "description": "Term sheet", "document": "fwp.htm", "type": "FWP", "size": "4321"}]
    out = pit.fetch(CIK, BEFORE, "fwp.htm")
    assert "4.750% Notes due 2031" in out["text"] and "<p>" not in out["text"]
    assert out["next_offset"] is None


def test_fetch_pages_long_documents(pit):
    first = pit.fetch(CIK, BEFORE, "fwp.htm", max_chars=10)
    assert len(first["text"]) == 10 and first["next_offset"] == 10
    rest = pit.fetch(CIK, BEFORE, "fwp.htm", offset=first["next_offset"], max_chars=10_000)
    assert first["text"] + rest["text"] == pit.fetch(CIK, BEFORE, "fwp.htm")["text"]


def test_document_names_cannot_escape_the_filing(pit):
    with pytest.raises(Refused, match="plain file name"):
        pit.fetch(CIK, BEFORE, "../../other/doc.htm")


def test_every_call_is_logged(pit):
    pit.timeline(CIK, "2026-01-01", "2026-12-31")
    pit.fetch(CIK, BEFORE, "fwp.htm")
    with pytest.raises(Refused):
        pit.fetch(CIK, TARGET, "q.htm")
    assert [(e["tool"], e["outcome"]) for e in log(pit)] == [("timeline", "ok"), ("fetch", "ok"), ("fetch", "refused")]
    assert all(e["as_of"] == "2026-08-12T16:05:23" for e in log(pit))


def test_undatable_filings_are_never_visible(tmp_path):
    class NoDate(FakeSec):
        def get(self, url, cache=True, **kw):
            if url.endswith(f"CIK{CIK:010d}.json"):
                return json.dumps({"filings": {"recent": {"accessionNumber": [BEFORE], "form": ["8-K"],
                                   "filingDate": ["2026-01-01"], "acceptanceDateTime": [""], "items": [""],
                                   "primaryDocument": ["a.htm"], "reportDate": [""]}}}).encode()
            return super().get(url, cache, **kw)
    p = PointInTimeEdgar("2030-01-01", client=NoDate(), log_path=tmp_path / "a.jsonl")
    assert p.timeline(CIK, "2000-01-01", "2030-01-01") == []
    with pytest.raises(Refused):
        p.fetch(CIK, BEFORE, "a.htm")


def test_normalise_time():
    assert normalise_time("2026-08-12T16:05:23.000Z") == "2026-08-12T16:05:23"
    assert normalise_time("2026-08-12") == "2026-08-12T00:00:00"
    with pytest.raises(ValueError):
        normalise_time("yesterday")


def test_rate_limiter_spaces_requests():
    t = [0.0]
    slept = []
    lim = RateLimiter(8.0, clock=lambda: t[0], sleep=lambda s: slept.append(s))
    for _ in range(4):
        lim.acquire()
    assert slept == pytest.approx([0.125, 0.25, 0.375])   # 8 per second, never a burst


def test_agent_side_never_imports_the_grader():
    """P11, structurally: nothing outside eval/ may import eval/ (the answer key)."""
    src = Path(__file__).resolve().parents[1] / "src" / "ai_debt_tracker"
    offenders = []
    for py in src.rglob("*.py"):
        if "eval" in py.relative_to(src).parts:
            continue
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            if any("eval" in n.split(".") for n in names):
                offenders.append(str(py.relative_to(src)))
    assert offenders == []
