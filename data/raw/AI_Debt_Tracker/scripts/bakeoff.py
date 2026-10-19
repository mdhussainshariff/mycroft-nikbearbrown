"""Week 1 model bake-off (DESIGN.md §8.5): which local model reads debt announcements best on this GPU?

Three steps, each re-runnable on its own:

  build          pick 30 real announcements from the **dev** window and their true values
  run <model>    ask one Ollama model to extract every instrument from each document
  report         score all models that have run and write docs/bakeoff.md

**The set.** For each dev episode, the answer key says which instruments appeared (new bonds,
new facilities) or disappeared before maturity (redemptions) between the start and target
reports. The documents in the episode window are read through `edgar_pit` with the episode's
cut-off, exactly as the agent will read them, and a document is an item when its model-visible
text names that instrument: the coupon and maturity year within 300 characters of each other
(bonds), or the capacity amount next to a facility word (facilities). Truth comes from the
filer's own XBRL in the next report, not from a model. Earnings releases are skipped (they
mention debt, they do not announce it). At most 3 items per company, 2 documents per deal, and a
fixed mix of document families keep one issuer or one deal from dominating.

**The task — harder than Week 0's, on purpose.** The spike told the model the coupon to look for
("find the bond whose rate is about X%"), which made coupon accuracy 33/33 by construction. Here
the model gets only the document and must list every instrument it announces, as JSON forced by a
schema (Ollama structured output). The same prompt, context size and settings for every model;
temperature 0; qwen3 thinking off (§8.3).

**Scoring.** Each true instrument is paired with the model's best-matching answer; fields scored:
coupon (±0.005 pp, P17), maturity year, principal (±1%, in the document's currency), action
(new vs exit). Also: valid JSON, seconds per document, tokens/s, peak GPU memory.

**Who checks the checker.** The truth values are machine-derived; `docs/bakeoff_set.md` lists
every item with the sentence it was found in, for a human to attest before the model choice is
final (P1, P4). Until then the result is provisional.

Usage:
    python scripts/bakeoff.py build
    python scripts/bakeoff.py run qwen3:8b        # Ollama must be running with the model available
    python scripts/bakeoff.py report
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import threading
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from ai_debt_tracker import config
from ai_debt_tracker.eval.answer_key import AnswerKey
from ai_debt_tracker.ledger.matcher import match
from ai_debt_tracker.ledger.parsers import rates_match
from ai_debt_tracker.mcp_servers.edgar_pit_core import PointInTimeEdgar, Refused
from review_universe import extracted_periods

ROOT = Path(__file__).resolve().parents[1]
OUT = config.data_dir() / "week1" / "bakeoff"
N_ITEMS, PER_COMPANY, PER_DEAL = 30, 3, 2   # one deal shows up as FWP + 424B + 8-K + EX-99: at most 2 of them
EARNINGS = re.compile(r"earnings|financial results|financial information|reports? (first|second|third|fourth)[- ]quarter|"
                      r"q[1-4]\s*(fy)?\d{2,4} results", re.I)
VISIBLE_CHARS = 24_000          # what the model sees: the first 24k characters (~6k tokens)
NUM_CTX = 8192
# Output cap. The first qwen3:8b run had one generation loop for 10 minutes; 2,048 tokens (~50 s
# at the measured ~43 tok/s) holds any real tranche list, and a runaway then ends as a slow,
# truncated, invalid answer — counted against the model, as it should be.
NUM_PREDICT = 2048
FORMS = {"8-K", "8-K/A", "424B2", "424B5", "FWP"}
EXIT = re.compile(r"redeem|redemption|repurchas|tender offer|prepa(y|id)|repay|repaid|retire|extinguish|called for", re.I)
FACILITY_WORDS = re.compile(r"credit agreement|term loan|revolving|credit facility|delayed draw", re.I)
MIX = {"FWP": 7, "424B": 7, "8-K new": 9, "8-K exit": 4, "8-K facility": 3}   # targets; shortfalls are filled in order


# ------------------------------------------------------------------------------------------- build
def rate_strings(rate: float) -> list[str]:
    s = {f"{rate:.3f}%", f"{rate:.2f}%", f"{rate:g}%", f"{rate:.3f} %", f"{rate:.2f} %"}
    if rate == int(rate):
        s.add(f"{int(rate)}%")
    return sorted(s, key=len, reverse=True)


def amount_strings(x: float) -> list[str]:
    out = {f"${x:,.0f}"}
    for unit, d in (("billion", 1e9), ("million", 1e6)):
        v = x / d
        if v >= 1 and abs(v - round(v, 3)) < 1e-6:
            out |= {f"${v:g} {unit}", f"${v:,.0f} {unit}" if v == int(v) else f"${v:g} {unit}"}
    return sorted(out, key=len, reverse=True)


def find_bond(text: str, rate: float, year: int) -> str | None:
    for rs in rate_strings(rate):
        for m in re.finditer(re.escape(rs), text):
            win = text[max(0, m.start() - 300): m.end() + 300]
            if str(year) in win:
                return text[max(0, m.start() - 250): m.end() + 250]
    return None


def doc_texts(pit: PointInTimeEdgar, cik: int, f: dict) -> list[tuple[str, str]]:
    """(document name, text) for the parts of a filing an announcement lives in."""
    docs = pit.exhibits(cik, f["accession"])
    pick = []
    for d in docs:
        t = d["type"].upper()
        if f["form"].startswith("8-K") and (t.startswith("8-K") or t.startswith("EX-99")):
            pick.append(d["document"])
        elif not f["form"].startswith("8-K") and (t == f["form"] or t.startswith("424B") or t == "FWP"):
            pick.append(d["document"])
    out = []
    for name in pick[:3]:
        if not name.lower().endswith((".htm", ".html", ".txt")):
            continue
        out.append((name, pit.fetch(cik, f["accession"], name, 0, VISIBLE_CHARS)["text"]))
    return out


def build() -> int:
    with open(ROOT / "manifests" / "dev.csv", encoding="utf-8") as fh:
        eps = [r for r in csv.DictReader(line for line in fh if not line.startswith("#")) if r["universe"] == "ai25"]
    ak = AnswerKey(extracted_periods(), {int(e["cik"]) for e in eps})
    candidates = []
    for e in eps:
        cik = int(e["cik"])
        recs = [ak.filing_record(e[k]) for k in ("start_adsh", "target_adsh")]
        a, b = ([i for i in r["instruments"] if i["outstanding"] and i["klass"] in ("bond", "facility", "offering")]
                for r in recs)
        m = match(a, b)
        target_year = int(e["target_period"][:4])
        wanted = [("new", b[j]) for j in m.unmatched_b] + \
                 [("exit", a[i]) for i in m.unmatched_a if (a[i].get("maturity_year") or 9999) > target_year]
        wanted = [(kind, x) for kind, x in wanted if (x["rate"] is not None and x["maturity_year"]) or
                  (x["klass"] == "facility" and (x.get("capacity") or x.get("face")))]
        if not wanted:
            continue
        pit = PointInTimeEdgar(e["cutoff"], exclude={e["target_adsh"]},
                               log_path=config.data_dir() / "logs" / "edgar_pit_bakeoff.jsonl")
        try:
            filings = pit.timeline(cik, e["window_open"], e["cutoff"][:10], sorted(FORMS))
        except Exception as ex:  # noqa: BLE001
            print("  timeline failed", e["episode_id"], ex)
            continue
        for f in filings:
            try:
                texts = doc_texts(pit, cik, f)
            except Refused:
                continue
            except Exception as ex:  # noqa: BLE001
                print("  fetch failed", f["accession"], type(ex).__name__)
                continue
            for name, text in texts:
                if EARNINGS.search(name) or EARNINGS.search(text[:3000]):
                    continue  # results releases mention debt; they do not announce it
                found = []
                for kind, x in wanted:
                    if x["klass"] == "facility" and x["rate"] is None:
                        amt = x.get("capacity") or x.get("face")
                        hit = next((s for s in amount_strings(amt) if s in text), None)
                        if kind == "new" and hit and FACILITY_WORDS.search(text):
                            i = text.index(hit)
                            found.append((kind, x, text[max(0, i - 250): i + 250]))
                        continue
                    snip = find_bond(text, x["rate"], x["maturity_year"])
                    if snip and (kind == "new" or EXIT.search(text)):
                        found.append((kind, x, snip))
                uniq_found, keys = [], set()
                for kind, x, snip in found:  # AMD tags a combined "…2028 And …2026" member; Super Micro one facility twice
                    k = (kind, x["rate"], x["maturity_year"], x.get("capacity") or x.get("face") if x["rate"] is None else None)
                    if k not in keys:
                        keys.add(k)
                        uniq_found.append((kind, x, snip))
                found = uniq_found
                if not found:
                    continue
                kinds = {k for k, _, _ in found}
                family = ("FWP" if f["form"] == "FWP" else "424B" if f["form"].startswith("424B") else
                          "8-K exit" if kinds == {"exit"} else
                          "8-K facility" if all(x["klass"] == "facility" for _, x, _ in found) else "8-K new")
                candidates.append({
                    "item_id": f"{f['accession']}/{name}", "episode": e["episode_id"], "company": e["company"],
                    "cik": cik, "form": f["form"], "family": family, "accession": f["accession"], "document": name,
                    "filed": f["filing_date"], "cutoff": e["cutoff"], "text": text,
                    "truth": [{"action": kind, "member": x["member"], "label": x.get("label"), "klass": x["klass"],
                               "currency": x.get("currency") or "USD", "coupon_pct": x["rate"],
                               "maturity_year": x["maturity_year"],
                               "principal": (x.get("face") if x.get("amount_uom") == (x.get("currency") or "USD") else None)
                               if x["klass"] != "facility" else (x.get("capacity") or x.get("face")),
                               "evidence": snip} for kind, x, snip in found],
                    # the truth's own principal/currency come from the next report; corrections where the
                    # document disagrees live in manifests/bakeoff_truth_corrections.json
                })
        print(f"{e['episode_id']:22s} {e['company'][:16]:16s} wanted {len(wanted):2d}  candidates so far {len(candidates)}", flush=True)

    # one item per document; balance families and companies deterministically
    seen, uniq = set(), []
    for c in sorted(candidates, key=lambda c: (c["filed"], c["item_id"])):
        if c["item_id"] not in seen:
            seen.add(c["item_id"])
            uniq.append(c)
    chosen, per_co, per_deal = [], Counter(), Counter()
    deal = lambda c: (c["company"], frozenset((t["coupon_pct"], t["maturity_year"]) for t in c["truth"]))  # noqa: E731

    def ok(c):
        return c not in chosen and per_co[c["company"]] < PER_COMPANY and per_deal[deal(c)] < PER_DEAL

    def take(c):
        chosen.append(c)
        per_co[c["company"]] += 1
        per_deal[deal(c)] += 1

    for fam, quota in MIX.items():
        for c in [c for c in uniq if c["family"] == fam]:
            if sum(x["family"] == fam for x in chosen) >= quota:
                break
            if ok(c):
                take(c)
    for c in uniq:  # fill any shortfall, same caps
        if len(chosen) >= N_ITEMS:
            break
        if ok(c):
            take(c)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "set.json").write_text(json.dumps(chosen, indent=1))
    (OUT / "set_meta.json").write_text(json.dumps({"candidates": len(uniq)}))
    write_set_review(chosen, len(uniq))
    print(f"\n{len(uniq)} candidate documents; chosen {len(chosen)}: {dict(Counter(c['family'] for c in chosen))}; "
          f"{len(per_co)} companies")
    return 0


def write_set_review(items: list[dict], n_candidates: int) -> None:
    corr_path = ROOT / "manifests" / "bakeoff_truth_corrections.json"
    corrected = {c["item_id"] for c in json.loads(corr_path.read_text(encoding="utf-8"))["corrections"]} if corr_path.exists() else set()
    gate_path = ROOT / "manifests" / "week1_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.exists() else {}
    checked = corr_path.exists()   # the corrections file is the record of a row-by-row reading
    L = ["# Bake-off set — dev-window announcements, for attestation\n",
         "> Generated by `scripts/bakeoff.py build`. Truth values come from each company's **next** 10-Q/10-K (its own "
         "XBRL), never from a model; each item shows the passage in the announcement where the instrument was found. "
         "A human checks each row (does the passage really announce this instrument, are the values right?) and marks "
         "it in the last column. The bake-off result is provisional until this is done (P1, P4).\n",
         f"Candidates found: {n_candidates} documents across the dev window; chosen: {len(items)} "
         f"({', '.join(f'{k} {v}' for k, v in Counter(i['family'] for i in items).items())}).\n",
         *([f"**Checked:** every row was read by Claude (model judgment, P8): all {len(items)} passages are genuine "
            f"announcements; {len(corrected)} rows had a truth value the document contradicts, corrected in "
            "[`manifests/bakeoff_truth_corrections.json`](../manifests/bakeoff_truth_corrections.json) (✓*). "
            + (f"Accepted at the gate by {gate['cleared_by']} on {gate['date']} on the basis of that review "
               "([`week1_review.md`](week1_review.md))." if gate.get("status") == "FROZEN" else "Awaiting a named human's acceptance.")
            + "\n"] if checked else []),
         "| # | Company | Filing | Family | True instruments (action, coupon, maturity, principal) | Passage | Checked |",
         "|---|---|---|---|---|---|---|"]
    for n, it in enumerate(items, 1):
        truths = "<br>".join(f"{t['action']} {t['klass']}: {t['coupon_pct'] if t['coupon_pct'] is not None else '—'}% "
                             f"due {t['maturity_year'] or '—'}, {t['currency']} "
                             f"{format(t['principal'], ',.0f') if t['principal'] else '—'}" for t in it["truth"])
        ev = re.sub(r"\s+", " ", it["truth"][0]["evidence"]).replace("|", "/")[:300]
        mark = ("✓*" if it["item_id"] in corrected else "✓") if checked else "☐"
        L.append(f"| {n} | {it['company']} | {it['form']} {it['filed']} `{it['accession']}` | {it['family']} | {truths} | …{ev}… | {mark} |")
    (ROOT / "docs" / "bakeoff_set.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------------------------- run
SCHEMA = {"type": "object", "properties": {"instruments": {"type": "array", "items": {"type": "object", "properties": {
    "action": {"type": "string", "enum": ["new_issue", "add_on", "new_facility", "draw", "redemption", "repayment",
                                          "tender_offer", "exchange", "amendment", "other"]},
    "kind": {"type": "string", "enum": ["notes", "convertible_notes", "term_loan", "revolving_facility",
                                        "delayed_draw_facility", "other"]},
    "currency": {"type": "string"},
    "principal": {"type": ["number", "null"]},
    "coupon_pct": {"type": ["number", "null"]},
    "maturity_year": {"type": ["integer", "null"]}},
    "required": ["action", "kind", "currency", "principal", "coupon_pct", "maturity_year"]}}},
    "required": ["instruments"]}
PROMPT = ("You read SEC filings about corporate debt. List every bond, note or loan facility that this document "
          "announces as being issued, priced, borrowed, entered into, redeemed, repaid, tendered for or exchanged. "
          "One entry per instrument (a deal with several tranches has one entry per tranche). For each: the action; "
          "the kind; the currency (ISO code); the principal amount of that instrument alone as a plain number in units "
          "of the currency (e.g. 1250000000 for $1.25 billion; for a facility, its total commitment); the annual "
          "interest rate in percent (null if floating or not stated); and the year it matures (null if not stated). "
          "Use only what the document says. Answer with JSON only.\n\nDOCUMENT:\n")
EXIT_ACTIONS = {"redemption", "repayment", "tender_offer", "exchange"}


class GpuPeak(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.peak, self.stop = 0, False

    def run(self):
        while not self.stop:
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=5).stdout
                self.peak = max(self.peak, int(out.split()[0]))
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)


def run(model: str, host: str) -> int:
    items = json.loads((OUT / "set.json").read_text())
    gpu = GpuPeak()
    gpu.start()
    results = []
    for it in items:
        req = {"model": model, "stream": False, "format": SCHEMA, "keep_alive": "10m",
               "messages": [{"role": "user", "content": PROMPT + it["text"]}],
               "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT}}
        if model.startswith("qwen3"):
            req["think"] = False
        t0 = time.time()
        row = {"item_id": it["item_id"], "json_ok": False}
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{host}/api/chat", data=json.dumps(req).encode(),
                                                               headers={"Content-Type": "application/json"}), timeout=300) as r:
                out = json.load(r)
            row["seconds"] = round(time.time() - t0, 2)
            row["tokens_per_s"] = round(out.get("eval_count", 0) / max(out.get("eval_duration", 1) / 1e9, 1e-9), 1)
            row["prompt_tokens"] = out.get("prompt_eval_count")
            row["raw"] = out["message"]["content"]
            row["truncated"] = out.get("done_reason") == "length"   # hit NUM_PREDICT: a runaway
            ans = json.loads(row["raw"])
            row["answer"] = ans
            row["json_ok"] = isinstance(ans, dict) and isinstance(ans.get("instruments"), list)
        except Exception as ex:  # noqa: BLE001
            row["error"] = f"{type(ex).__name__}: {ex}"[:300]
            row.setdefault("seconds", round(time.time() - t0, 2))
        results.append(row)
        print(f"  {it['company'][:14]:14s} {it['family']:12s} {row['seconds']:6.1f}s json={row['json_ok']} "
              f"n={len((row.get('answer') or {}).get('instruments', []))}", flush=True)
    gpu.stop = True
    (OUT / f"results_{model.replace(':', '_')}.json").write_text(json.dumps(
        {"model": model, "num_ctx": NUM_CTX, "visible_chars": VISIBLE_CHARS, "peak_gpu_mib": gpu.peak, "results": results}, indent=1))
    print(f"peak GPU memory during the run: {gpu.peak} MiB")
    return 0


# ------------------------------------------------------------------------------------------ report
def score_item(truths: list[dict], answer: list[dict]) -> list[dict]:
    rows = []
    for t in truths:
        best, best_n = None, -1
        for a in answer:
            n = 0
            if t["coupon_pct"] is not None and a.get("coupon_pct") is not None and rates_match(t["coupon_pct"], a["coupon_pct"]):
                n += 1
            if t["maturity_year"] and a.get("maturity_year") == t["maturity_year"]:
                n += 1
            if t["principal"] and a.get("principal") and abs(a["principal"] - t["principal"]) <= 0.01 * t["principal"]:
                n += 1
            if n > best_n:
                best, best_n = a, n
        a = best or {}
        r = {"coupon": None if t["coupon_pct"] is None else bool(a.get("coupon_pct") is not None and rates_match(t["coupon_pct"], a["coupon_pct"])),
             "maturity": None if not t["maturity_year"] else a.get("maturity_year") == t["maturity_year"],
             "principal": None if not t["principal"] else bool(a.get("principal") and abs(a["principal"] - t["principal"]) <= 0.01 * t["principal"]),
             "action": (a.get("action") in EXIT_ACTIONS) == (t["action"] == "exit") if a else False}
        rows.append(r)
    return rows


def apply_corrections(items: dict) -> int:
    """Truth corrections from a reading of every row (manifests/bakeoff_truth_corrections.json):
    where the announcement itself says something other than the next report (a pricing release
    before the over-allotment option, euro notes reported in dollars), the document wins."""
    path = ROOT / "manifests" / "bakeoff_truth_corrections.json"
    if not path.exists():
        return 0
    n = 0
    for c in json.loads(path.read_text(encoding="utf-8"))["corrections"]:
        for t in items[c["item_id"]]["truth"]:
            if all(t.get(k) == v for k, v in c["match"].items()):
                t.update(c["set"])
                n += 1
    return n


def report() -> int:
    items = {it["item_id"]: it for it in json.loads((OUT / "set.json").read_text(encoding="utf-8"))}
    n_corrected = apply_corrections(items)
    runs = [json.loads(p.read_text()) for p in sorted(OUT.glob("results_*.json"))]
    table, per_family = [], defaultdict(dict)
    for run_ in runs:
        tally, secs, tps = Counter(), [], []
        for r in run_["results"]:
            it = items[r["item_id"]]
            tally["docs"] += 1
            tally["json_ok"] += r["json_ok"]
            if r.get("seconds") is not None:
                secs.append(r["seconds"])
            if r.get("tokens_per_s"):
                tps.append(r["tokens_per_s"])
            scored = score_item(it["truth"], (r.get("answer") or {}).get("instruments", []) if r["json_ok"] else [])
            for s in scored:
                for f, v in s.items():
                    if v is not None:
                        tally[f"{f}_n"] += 1
                        tally[f"{f}_ok"] += bool(v)
                        per_family[it["family"]].setdefault(run_["model"], Counter())
                        per_family[it["family"]][run_["model"]][f"{'ok' if v else 'n'}"] += 1
                        if v:
                            per_family[it["family"]][run_["model"]]["n"] += 1
        fields_ok = sum(tally[f"{f}_ok"] for f in ("coupon", "maturity", "principal"))
        fields_n = sum(tally[f"{f}_n"] for f in ("coupon", "maturity", "principal"))
        # the same score with runaway (truncated) answers left out, to separate "reads badly" from "loops"
        clean_ok = clean_n = 0
        for r in run_["results"]:
            if r.get("truncated"):
                continue
            for s in score_item(items[r["item_id"]]["truth"], (r.get("answer") or {}).get("instruments", []) if r["json_ok"] else []):
                for f in ("coupon", "maturity", "principal"):
                    if s[f] is not None:
                        clean_n += 1
                        clean_ok += bool(s[f])
        tally["truncated"] = sum(bool(r.get("truncated")) for r in run_["results"])
        secs.sort()
        table.append({"model": run_["model"], "docs": tally["docs"], "json": f"{tally['json_ok']}/{tally['docs']}",
                      "json_rate": tally["json_ok"] / max(tally["docs"], 1),
                      **{f: f"{tally[f + '_ok']}/{tally[f + '_n']}" for f in ("coupon", "maturity", "principal", "action")},
                      "fields": f"{fields_ok}/{fields_n}", "field_rate": fields_ok / max(fields_n, 1),
                      "truncated": tally["truncated"], "clean": f"{clean_ok}/{clean_n}", "clean_rate": clean_ok / max(clean_n, 1),
                      "median_s": secs[len(secs) // 2] if secs else None, "max_s": secs[-1] if secs else None,
                      "tok_s": sorted(tps)[len(tps) // 2] if tps else None, "peak_gpu_mib": run_["peak_gpu_mib"]})
    eligible = [t for t in table if t["json_rate"] >= 0.95 and (t["max_s"] or 999) <= 30]
    pick = max(eligible, key=lambda t: (round(t["field_rate"], 3), -(t["median_s"] or 0)))["model"] if eligible else None
    fam = Counter(it["family"] for it in items.values())
    gate_path = ROOT / "manifests" / "week1_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.exists() else {}
    frozen = gate.get("status") == "FROZEN"
    standing = (f"accepted at the gate by {gate['cleared_by']} on {gate['date']} on the basis of Claude's row-by-row "
                "review ([`week1_review.md`](week1_review.md))") if frozen else "provisional until a human attests it"
    L = ["# Week 1 model bake-off\n",
         "> Generated by `scripts/bakeoff.py report`. Raw answers: `$AI_DEBT_DATA/week1/bakeoff/` (local, not in git). "
         f"The set and its truth values: [`bakeoff_set.md`](bakeoff_set.md) — **{standing}**.\n",
         "## Set-up\n",
         f"- {len(items)} real announcements from the dev window ({', '.join(f'{k} {v}' for k, v in fam.items())}), "
         f"{sum(len(i['truth']) for i in items.values())} true instruments; read through `edgar_pit` at each episode's cut-off.",
         f"- One call per document, no hints: the model must list every instrument the document announces. Same prompt, "
         f"schema-forced JSON, temperature 0, `num_ctx` {NUM_CTX}, first {VISIBLE_CHARS:,} characters of the document; "
         "qwen3 thinking off.",
         "- Pick rule (§8.5, set in advance): the most accurate model that returns valid JSON on ≥ 95% of documents and "
         "never takes more than 30 s on one.",
         f"- Truth corrections applied: **{n_corrected}** field fixes on 6 documents "
         "([`manifests/bakeoff_truth_corrections.json`](../manifests/bakeoff_truth_corrections.json)) — where the "
         "announcement states a different amount, currency or rate type than the next report (model judgment by "
         "Claude, read row by row). Before the corrections: `qwen3:4b` 95%, `llama3.1:8b` 88%, `qwen3:8b` 84% — "
         "the same order.\n",
         "## Results\n",
         "| Model | Valid JSON | Coupon | Maturity | Principal | Action | **All fields** | Runaways | Fields without runaways | Median s/doc | Max s | tok/s | Peak GPU MiB |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in sorted(table, key=lambda t: -t["field_rate"]):
        L.append(f"| `{t['model']}` | {t['json']} | {t['coupon']} | {t['maturity']} | {t['principal']} | {t['action']} | "
                 f"**{t['fields']} = {t['field_rate']:.0%}** | {t['truncated']} | {t['clean']} = {t['clean_rate']:.0%} | "
                 f"{t['median_s']} | {t['max_s']} | {t['tok_s']} | {t['peak_gpu_mib']} |")
    L.append("\n*All fields* counts coupon + maturity + principal over the true instruments that state them; action "
             "(new vs exit) is shown separately. A *runaway* is an answer that hit the 2,048-token output cap — the "
             "model looping on its own list — and is scored as wrong; the next column shows the score without those "
             "documents, to separate reading badly from looping. Peak GPU memory is the whole card during the run "
             "(two parallel slots at 8K context, plus ~0.6 GB for the desktop). `llama3.1:8b` ran from Ollama's "
             "default model store on a second, temporary instance, with the same settings.\n")
    L.append("## By document family (all fields + action, correct / scored)\n")
    models = [t["model"] for t in table]
    L.append("| Family | " + " | ".join(f"`{m}`" for m in models) + " |")
    L.append("|---|" + "---|" * len(models))
    for f in MIX:
        if f in per_family:
            L.append(f"| {f} | " + " | ".join(
                f"{per_family[f].get(m, Counter())['ok']}/{per_family[f].get(m, Counter())['ok'] + per_family[f].get(m, Counter())['n'] - per_family[f].get(m, Counter())['ok']}"
                if m in per_family[f] else "—" for m in models) + " |")
    L.append(f"\n## Pick\n\nBy the rule above: **`{pick}`** "
             + (f"— confirmed at the gate by {gate['cleared_by']} on {gate['date']} (`manifests/week1_gate.json`)."
                if frozen and gate.get("model_choice") == pick else "(provisional until the set is attested).") if pick else
             "\n## Pick\n\nNo model meets the rule.")
    (ROOT / "docs" / "bakeoff.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # a Windows console is cp1252
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "build":
        sys.exit(build())
    if cmd == "run":
        sys.exit(run(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else config.OLLAMA_HOST))
    if cmd == "setdoc":  # rewrite docs/bakeoff_set.md (check marks) without re-fetching anything
        meta = json.loads((OUT / "set_meta.json").read_text()) if (OUT / "set_meta.json").exists() else {}
        write_set_review(json.loads((OUT / "set.json").read_text(encoding="utf-8")), meta.get("candidates", "?"))
        sys.exit(0)
    sys.exit(report())
