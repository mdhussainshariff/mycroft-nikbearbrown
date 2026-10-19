"""Feasibility spike F2 (are debt changes announced?) and a mini F4 (can a local model read them?).

F2: for every bond that appeared or disappeared between consecutive reports (spike_episodes.json),
    search the company's filings in the window (8-K, 424B*, FWP) for its interest rate.
F4: for the explained new bonds that are single bonds, give a local Ollama model the announcement
    text around the match and ask for principal / coupon / maturity year as JSON (one naive call —
    baseline B2); compare with the official XBRL values. Raw answers go to f4_results_<model>.json.

Usage (run spike_f1_f3_matching_and_headroom.py first; Ollama must be running for F4):
    python scripts/spike_f2_f4_announcements_and_model.py [ollama-model|none] [N|all]
    e.g.  ... qwen3:8b all      (the 2026-10-16 run: 33 announcements)
Results of the 2026-10-16 run are recorded in docs/feasibility.md.
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import _localenv  # noqa: F401  (loads the gitignored .env)

UA = {"User-Agent": f"{os.environ.get('EDGAR_NAME', 'ai-debt-tracker-spike')} {os.environ.get('EDGAR_EMAIL', '')}".strip()}
ROOT = Path(__file__).resolve().parent.parent
HERE = Path(os.environ.get("AI_DEBT_DATA", ROOT / "data")) / "spike"
DOCS = HERE / "subs"
DOCS.mkdir(parents=True, exist_ok=True)
MODEL = sys.argv[1] if len(sys.argv) > 1 else "llama3.1:8b"
FORMS = {"8-K", "8-K/A", "424B2", "424B3", "424B5", "FWP"}
EXIT_WORDS = re.compile(r"redeem|redemption|repurchas|tender offer|prepa|repay|repaid|retire|extinguish|exchange offer|convert|payoff|paid off", re.I)


def get(url):
    for t in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if t == 2:
                raise
            time.sleep(3)


def text_of(cik, acc):
    p = DOCS / f"{acc}.txt"
    if not p.exists():
        raw = get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}.txt").decode("utf-8", "ignore")
        t = re.sub(r"<[^>]+>", " ", raw)
        t = re.sub(r"&#160;|&nbsp;|&#xa0;", " ", t)
        t = re.sub(r"&#8217;|&rsquo;", "'", t)
        p.write_text(re.sub(r"\s+", " ", t), encoding="utf-8")
        time.sleep(0.15)
    return p.read_text(encoding="utf-8")


def rate_patterns(r):
    """The bulk notes data stores rates to 4 decimals of a fraction (6.125% -> 0.0613 -> 6.13),
    so search every 3-decimal rate that rounds to the stored value."""
    s = set()
    for k in range(-5, 6):
        x = round(r + k / 1000, 3)
        if x <= 0 or round(x, 2) != round(r, 2):
            continue
        for v in {f"{x:.3f}", f"{x:.2f}" if round(x, 2) == x else None, f"{x:g}"}:
            if v:
                s.update({v + "%", v + " %"})
    return [re.escape(x) for x in s]


def report_text(cik, rec, adsh):
    """Text of a 10-Q/10-K primary document (to tell real changes from tagging churn)."""
    p = DOCS / f"{adsh}_primary.txt"
    if not p.exists():
        i = rec["accessionNumber"].index(adsh)
        raw = get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{rec['primaryDocument'][i]}").decode("utf-8", "ignore")
        t = re.sub(r"<[^>]+>", " ", raw)
        t = re.sub(r"&#160;|&nbsp;|&#xa0;", " ", t)
        p.write_text(re.sub(r"\s+", " ", t), encoding="utf-8")
        time.sleep(0.15)
    return p.read_text(encoding="utf-8")


episodes = json.loads((HERE / "spike_episodes.json").read_text())
subs_cache = {}
f2 = {"added": 0, "added_with_rate": 0, "added_explained": 0, "added_tagging_churn": 0, "added_unexplained": 0,
      "removed": 0, "removed_with_rate": 0, "removed_matured": 0, "removed_explained": 0, "removed_tagging_churn": 0,
      "removed_unexplained": 0}
by_form = {}
samples = []
for ep in episodes:
    if not ep["added"] and not ep["removed"]:
        continue
    cik = ep["cik"]
    if cik not in subs_cache:
        subs_cache[cik] = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))["filings"]["recent"]
        time.sleep(0.15)
    rec = subs_cache[cik]
    start = ep["from"]["period"]
    start = f"{start[:4]}-{start[4:6]}-{start[6:]}" if "-" not in start else start
    end = ep["to"]["period"]
    end = f"{end[:4]}-{end[4:6]}-{end[6:]}" if "-" not in end else end
    end_plus = (date.fromisoformat(end) + timedelta(days=7)).isoformat()
    window = [(rec["form"][i], rec["accessionNumber"][i]) for i in range(len(rec["form"]))
              if rec["form"][i] in FORMS and start < rec["filingDate"][i] <= end_plus]
    texts = {}
    for form, acc in window:
        try:
            texts[acc] = (form, text_of(cik, acc))
        except Exception as ex:  # noqa: BLE001
            print("  fetch failed", acc, ex)
    print(f"{ep['company']:20s} {start}->{end}: {len(window)} filings in window, +{len(ep['added'])} / -{len(ep['removed'])}")
    for m in ep["added"]:
        f2["added"] += 1
        d = ep["added_detail"][m]
        if not d.get("rate"):  # missing, or 0% (zero-coupon) — a "0%" search would match anything
            continue
        f2["added_with_rate"] += 1
        pat = re.compile("|".join(rate_patterns(d["rate"])))
        hit = next(((acc, form, mm) for acc, (form, t) in texts.items() for mm in [pat.search(t)] if mm), None)
        verdict = None
        if hit:
            f2["added_explained"] += 1
            verdict = "announced in " + hit[1]
            by_form[hit[1]] = by_form.get(hit[1], 0) + 1
            t = texts[hit[0]][1]
            samples.append({"company": ep["company"], "member": m, "truth": d, "form": hit[1], "acc": hit[0],
                            "snippet": t[max(0, hit[2].start() - 1500): hit[2].end() + 1500]})
        else:
            # already described in the previous report's text, just not tagged per instrument then?
            try:
                prev = report_text(cik, rec, ep["from"]["adsh"])
            except Exception:  # noqa: BLE001
                prev = ""
            if pat.search(prev):
                f2["added_tagging_churn"] += 1
                verdict = "tagging churn (already in previous report)"
            else:
                f2["added_unexplained"] += 1
                verdict = "UNEXPLAINED"
        print(f"    + {m:45s} rate={d.get('rate')} face={d.get('face')} -> {verdict}")
    end_year = int(end[:4])
    for m in ep["removed"]:
        f2["removed"] += 1
        d = ep["removed_detail"][m]
        ys = re.findall(r"(20[2-6]\d)", (d.get("maturity") or "") + " " + m)
        if ys and int(ys[-1]) <= end_year:
            f2["removed_matured"] += 1
            print(f"    - {m:45s} -> matured (due {ys[-1]})")
            continue
        if not d.get("rate"):  # missing, or 0% (zero-coupon) — a "0%" search would match anything
            continue
        f2["removed_with_rate"] += 1
        pat = re.compile("|".join(rate_patterns(d["rate"])))
        hit = next((form for acc, (form, t) in texts.items() if pat.search(t) and EXIT_WORDS.search(t)), None)
        if hit:
            f2["removed_explained"] += 1
            verdict = "announced in " + hit
        else:
            try:
                nxt = report_text(cik, rec, ep["to"]["adsh"])
            except Exception:  # noqa: BLE001
                nxt = ""
            if pat.search(nxt):
                f2["removed_tagging_churn"] += 1
                verdict = "tagging churn (still in next report)"
            else:
                f2["removed_unexplained"] += 1
                verdict = "UNEXPLAINED"
        print(f"    - {m:45s} rate={d.get('rate')} -> {verdict}")

print("\n=== F2 summary ===")
for k, v in f2.items():
    print(f"{k}: {v}")
print("explaining document types (new bonds):", by_form)

# ---- mini F4 -------------------------------------------------------------------------------
SCHEMA = {"type": "object", "properties": {
    "principal_usd": {"type": "number"}, "coupon_pct": {"type": "number"}, "maturity_year": {"type": "integer"}},
    "required": ["principal_usd", "coupon_pct", "maturity_year"]}


def ask(snippet, rate):
    prompt = ("This is an excerpt from an SEC filing announcing or describing bonds. Several bonds may be listed. "
              f"Find the ONE bond whose annual interest rate is about {rate}% and report: its own principal amount "
              "(that bond only, not the total of all bonds), its interest rate in percent, and the year it is due "
              "(the maturity year, not the issue year). Answer only with JSON.\n\n" + snippet)
    req = {"model": MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False,
           "format": SCHEMA, "options": {"temperature": 0, "num_ctx": 4096}}
    if MODEL.startswith("qwen3"):
        req["think"] = False  # DESIGN.md §8.3: thinking off for extraction
    t0 = time.time()
    with urllib.request.urlopen(urllib.request.Request("http://localhost:11434/api/chat", data=json.dumps(req).encode(),
                                                       headers={"Content-Type": "application/json"}), timeout=300) as r:
        out = json.load(r)
    tps = out.get("eval_count", 0) / (out.get("eval_duration", 1) / 1e9)
    return json.loads(out["message"]["content"]), time.time() - t0, tps


def year_from(member, truth):
    ys = re.findall(r"(20[2-6]\d)", (truth.get("maturity") or "") + " " + member)
    return int(ys[-1]) if ys else None


def single_bond(s):
    """Keep only members that are one bond: a maturity year (>= 2027) in the name, not an issue-date
    group like 'A2026USDollarNotes' or 'March2026SeniorUnsecuredNotes'."""
    y = year_from(s["member"], s["truth"])
    return y is not None and y >= 2027


def summarise(rows, label):
    n = len(rows)
    ok_json = sum(r["json_ok"] for r in rows)
    coupon = sum(bool(r["coupon_ok"]) for r in rows)
    year_rows = [r for r in rows if r["truth_year"] is not None]
    year = sum(bool(r["year_ok"]) for r in year_rows)
    p_rows = [r for r in rows if r["principal_ok"] is not None]
    principal = sum(bool(r["principal_ok"]) for r in p_rows)
    secs = sorted(r["seconds"] for r in rows if r["json_ok"])
    fields = coupon + year + principal
    field_n = n + len(year_rows) + len(p_rows)
    print(f"[{label}] valid JSON {ok_json}/{n}; coupon {coupon}/{n}; maturity year {year}/{len(year_rows)}; "
          f"principal {principal}/{len(p_rows)}; all fields {fields}/{field_n} = {fields / max(field_n, 1):.0%}; "
          f"median {secs[len(secs) // 2]:.1f}s per document" if secs else f"[{label}] no results")


LIMIT = sys.argv[2] if len(sys.argv) > 2 else "15"
fair = [s for s in samples if single_bond(s)]
todo = fair if LIMIT == "all" else fair[: int(LIMIT)]
if todo and MODEL != "none":
    print(f"\n=== mini F4 with {MODEL} on {len(todo)} real single-bond announcements ===")
    results = []
    for s in todo:
        truth = s["truth"]
        ty = year_from(s["member"], truth)
        row = {"company": s["company"], "member": s["member"], "form": s["form"], "acc": s["acc"],
               "truth_rate": truth["rate"], "truth_face": truth.get("face"), "truth_year": ty,
               "json_ok": False, "coupon_ok": False, "year_ok": None, "principal_ok": None, "seconds": None}
        try:
            ans, dt, tps = ask(s["snippet"], truth["rate"])
        except Exception as ex:  # noqa: BLE001
            print("  model error", ex)
            results.append(row)
            continue
        # the answer key rounds rates to 2 decimals (P17), so 5.625 vs a stored 5.63 is a match
        row.update(json_ok=True, answer=ans, seconds=round(dt, 2), tokens_per_s=round(tps, 1),
                   coupon_ok=abs(ans.get("coupon_pct", -1) - truth["rate"]) <= 0.0051,
                   year_ok=(ans.get("maturity_year") == ty) if ty is not None else None,
                   principal_ok=(abs(ans.get("principal_usd", 0) - truth["face"]) <= 0.01 * truth["face"]) if truth.get("face") else None)
        results.append(row)
        print(f"  {s['company']:16s} {s['form']:6s} truth: rate={truth['rate']} face={truth.get('face')} year={ty} | "
              f"model: {ans} | coupon {'ok' if row['coupon_ok'] else 'X'} year {row['year_ok']} principal {row['principal_ok']} "
              f"({dt:.1f}s, {tps:.0f} tok/s)")
    summarise(results[:15], "first 15 — same set as the llama3.1:8b run")
    if len(results) > 15:
        summarise(results, f"all {len(results)}")
    (HERE / f"f4_results_{MODEL.replace(':', '_')}.json").write_text(json.dumps(results, indent=1, default=str))
(HERE / "spike_f2_samples.json").write_text(json.dumps(samples, indent=1, default=str))
