"""Purpose: Run the recipe's approved analysis tool, the six-pattern contradiction detector, over verified signal bundles, and prepare (never send) the optional LLM review as an approval-required handoff.
Input: per-company verified bundles from step 4 (data/verified/contradiction-detection-agent/runs/<run>/quality-checked/<TICKER>.json) and the run envelope.
Output: per-company detection results and LLM handoff specs under logs/contradiction-detection-agent/runs/<run>/, plus a run summary on stdout (and --output).
Side effects: writes under logs/ only. No network: the LLM is never called, and live mode stops.
Idempotent: Yes; every timestamp comes from the envelope's frozen_clock, never from now().
Recipe: recipes/contradiction-detection-agent.md

What this ports, and how faithfully. `aggregate()` and `detect()` are a line-by-line port of the
original workflow's `Aggregate All Signals` and `Run Pattern Detection Engine` code nodes
(data/mycroft-main/n8n-workflows/originals/n8n_Workflows/Contradiction_Detection_Agent/). It aims to be
a faithful port: thresholds, wording and ordering are reproduced exactly (the recipe's Notes from porting
list the details worth knowing when reading the flags), because P6 forbids an artifact silently winning
over its source. Any change in behaviour belongs in a separate, reviewed change. JavaScript semantics that differ from Python are emulated explicitly
(`js_truthy`, `js_or`, `js_str`, `js_to_fixed`, `js_slice`). The parity check
(scripts/tools/contradiction-detection-agent-parity-check.py) proves the port against the original JS.

Layer contract. A tools-layer script: it reads only verified data (P2), never touches the network, and
labels every model judgment as a judgment. The original sends flags to an LLM ("Build Groq Prompt" ->
Groq). Here that prompt is built exactly as the original builds it and written as a handoff with
approved_for_live_action=false. Sending it is a gate-5 decision for a named human, and gate 5 is not cleared.
"""

from __future__ import annotations

import argparse
import json
import math
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

WORKFLOW_NAME = "Contradiction_detection_agent"
WORKFLOW_SLUG = "contradiction-detection-agent"
NODE_NAME = "Run approved tools"
NODE_TYPE = "recipe-step"
CLASSIFICATION = "tools"
ROOT = Path(__file__).resolve().parents[2]
SOURCES = ["guidance-signals", "risk-admissions", "qa-pressure-map", "news-signals", "tech-stack-signals"]


# ── JavaScript semantics, emulated where Python differs ────────────────────────────────────────────
def js_truthy(v: Any) -> bool:
    """JS truthiness: false for undefined/null/false/0/NaN/''; TRUE for [] and {} (unlike Python)."""
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return not (v == 0 or (isinstance(v, float) and math.isnan(v)))
    if isinstance(v, str):
        return v != ""
    return True


def js_or(*vals: Any) -> Any:
    """`a || b || c`: the first JS-truthy operand, else the last operand."""
    for v in vals[:-1]:
        if js_truthy(v):
            return v
    return vals[-1]


def js_str(v: Any) -> str:
    """String(v) as a JS template literal renders it."""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if v.is_integer() and abs(v) < 1e21:
            return str(int(v))
        return repr(v)
    if isinstance(v, list):
        return ",".join("" if x is None else js_str(x) for x in v)
    return str(v)


def js_to_fixed(x: float, digits: int = 2) -> str:
    """Number.prototype.toFixed: exact binary value, ties rounded away from zero (Python rounds half-even)."""
    q = Decimal(1).scaleb(-digits)
    return str(Decimal(x).quantize(q, rounding=ROUND_HALF_UP))


def js_slice(s: str, end: int) -> str:
    """String.prototype.slice(0, end) counts UTF-16 code units, not characters."""
    units = s.encode("utf-16-le")[: end * 2]
    return units.decode("utf-16-le", errors="ignore")


def num(v: Any) -> float:
    """`(v || 0)` for a value step 3 has already verified to be a number or null."""
    return v if js_truthy(v) else 0


def iso_millis(clock: str) -> str:
    """`new Date().toISOString()` under the frozen clock: 2026-09-30T00:00:00.000Z."""
    from datetime import datetime, timezone
    d = datetime.fromisoformat(clock).astimezone(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"


# ── port of "Aggregate All Signals" ─────────────────────────────────────────────────────────────────
def aggregate(ctx: dict, rows: dict) -> dict:
    def collect(src: str) -> list:
        return [r for r in rows.get(src, []) if r and len(r) > 0]

    guidance = [r for r in collect("guidance-signals") if js_truthy(r.get("claim_id"))]
    risks = [r for r in collect("risk-admissions") if js_truthy(r.get("risk_category"))]
    qa = [r for r in collect("qa-pressure-map") if js_truthy(r.get("question_topic"))]
    news = [r for r in collect("news-signals") if js_truthy(r.get("headline"))]
    tech = [r for r in collect("tech-stack-signals") if js_truthy(r.get("ticker"))]
    n = len(news)
    pos = sum(1 for x in news if x.get("sentiment_label") == "positive")
    neg = sum(1 for x in news if x.get("sentiment_label") == "negative")
    avg = (sum(num(x.get("sentiment_score")) for x in news) / n) if n > 0 else None
    direction = ("UNAVAILABLE" if avg is None else "POSITIVE" if avg > 0.2 else "NEGATIVE" if avg < -0.2 else "NEUTRAL")
    return {**ctx,
            "signals": {"guidance_signals": guidance, "risk_admissions": risks, "qa_pressure": qa,
                        "news_signals": news, "tech_stack_signals": tech},
            "signal_counts": {"guidance": len(guidance), "risks": len(risks), "qa_items": len(qa),
                              "news": n, "tech_stack": len(tech)},
            "summaries": {"news_sentiment_direction": direction, "avg_news_score": avg, "pos_news": pos,
                          "neg_news": neg,
                          "strengthened_guidance_count": sum(1 for g in guidance if g.get("direction") == "strengthened"),
                          "weakened_guidance_count": sum(1 for g in guidance if g.get("direction") == "weakened"),
                          "unchanged_guidance_count": sum(1 for g in guidance if g.get("direction") == "unchanged"),
                          "has_tech_stack": len(tech) > 0, "latest_tech": tech[0] if tech else None}}


# ── port of "Run Pattern Detection Engine" ──────────────────────────────────────────────────────────
def detect(ctx: dict) -> dict:
    sigs, summ = ctx["signals"], ctx["summaries"]
    active = ctx.get("active_patterns") or [1, 2, 3, 4, 5, 6]
    ticker, resolve_id = ctx.get("ticker"), ctx.get("resolve_id")
    flagged_at = iso_millis(ctx["frozen_clock"])
    flags, skipped, results = [], [], {}
    seq = [0]
    news_all = sigs.get("news_signals") or []

    def make_flag(pid, name, severity, a, b, conflict, ev_a, ev_b):
        seq[0] += 1
        a, b = a or {}, b or {}
        return {"flag_id": f"{resolve_id}-P{pid}-F{seq[0]:03d}", "resolve_id": resolve_id, "ticker": ticker,
                "pattern_id": pid, "pattern_name": name, "severity": severity, "conflict_description": conflict,
                "claim_a_id": js_or(a.get("claim_id"), None), "claim_a_source": js_or(a.get("_source"), None),
                "claim_a_text": js_or(a.get("claim_text"), a.get("headline"), a.get("risk_description"), None),
                "claim_a_direction": js_or(a.get("direction"), a.get("sentiment_label"), None),
                "claim_b_id": js_or(b.get("claim_id"), None), "claim_b_source": js_or(b.get("_source"), None),
                "claim_b_text": js_or(b.get("claim_text"), b.get("headline"), None),
                "claim_b_direction": js_or(b.get("direction"), b.get("sentiment_label"), None),
                "evidence_for_a": ev_a, "evidence_for_b": ev_b, "resolution_status": "UNRESOLVED",
                "requires_human_review": True, "schema_valid": True, "flagged_at": flagged_at}

    avg2 = js_to_fixed(js_or(summ.get("avg_news_score"), 0))

    # PATTERN 1: Sentiment vs Guidance Direction
    if 1 in active:
        weakened = [g for g in sigs["guidance_signals"] if g.get("direction") == "weakened" and num(g.get("direction_confidence")) >= 0.6]
        news_pos = summ["news_sentiment_direction"] == "POSITIVE"
        news_neg = summ["news_sentiment_direction"] == "NEGATIVE"
        p = []
        if weakened and news_pos and len(news_all) > 0:
            for g in weakened[:3]:
                best_pos = next((x for x in news_all if x.get("sentiment_label") == "positive"), None)
                if best_pos:
                    p.append(make_flag(1, "Sentiment vs Guidance Direction", "HIGH", {**g, "_source": "earnings_agent"},
                                       {**best_pos, "_source": "news_agent"},
                                       f"Guidance for \"{js_or(g.get('guidance_topic'), g.get('claim_type'), 'topic')}\" marked WEAKENED but news sentiment is POSITIVE",
                                       f"Earnings: direction={js_str(g.get('direction'))}, confidence={js_str(g.get('direction_confidence'))}",
                                       f"News: {summ['pos_news']} positive articles, avg score {avg2}"))
        if summ["strengthened_guidance_count"] > 0 and news_neg and len(news_all) > 0:
            best_str = next((g for g in sigs["guidance_signals"] if g.get("direction") == "strengthened"), None)
            worst_neg = next((x for x in news_all if x.get("sentiment_label") == "negative"), None)
            if best_str and worst_neg:
                p.append(make_flag(1, "Sentiment vs Guidance Direction", "HIGH", {**best_str, "_source": "earnings_agent"},
                                   {**worst_neg, "_source": "news_agent"},
                                   "Guidance STRENGTHENED on call but news sentiment is NEGATIVE",
                                   f"Earnings: {summ['strengthened_guidance_count']} strengthened signals",
                                   f"News: {summ['neg_news']} negative articles, avg score {avg2}"))
        results[1] = {"active": True, "flags_raised": len(p)}
        flags += p
    else:
        skipped.append({"pattern_id": 1, "reason": "excluded_by_caller"})

    # PATTERN 2: Risk Admission vs News Coverage
    if 2 in active:
        high = [r for r in sigs["risk_admissions"] if r.get("severity") in ("high", "critical")]
        p = []
        for r in high[:3]:
            cat = r.get("risk_category")
            matching = [x for x in news_all if any(js_truthy(cat) and t.lower().find(cat.lower()) != -1
                                                    for t in (js_or(x.get("topic_tags"), []) or []))]
            pos_match = [x for x in matching if x.get("sentiment_label") == "positive"]
            if len(news_all) > 0 and len(matching) == 0:
                p.append(make_flag(2, "Risk Admission vs News Coverage Gap", "MEDIUM", {**r, "_source": "earnings_agent"}, None,
                                   f"High-severity risk \"{js_str(cat)}\" admitted on call but absent from news coverage",
                                   f"Earnings: severity={js_str(r.get('severity'))}",
                                   f"News: {len(news_all)} articles scanned, zero match topic"))
            elif pos_match:
                p.append(make_flag(2, "Risk Admission vs Coverage Tone", "HIGH", {**r, "_source": "earnings_agent"},
                                   {**pos_match[0], "_source": "news_agent"},
                                   f"High-severity risk \"{js_str(cat)}\" admitted on call; matching news has POSITIVE sentiment",
                                   f"Earnings: severity={js_str(r.get('severity'))}",
                                   f"News: sentiment=positive, headline=\"{js_slice(js_or(pos_match[0].get('headline'), ''), 80)}\""))
        results[2] = {"active": True, "flags_raised": len(p)}
        flags += p
    else:
        skipped.append({"pattern_id": 2, "reason": "excluded_by_caller"})

    # PATTERN 3: QA Evasion vs Analyst Coverage (`evasion_flag` is set from is_repeated_topic)
    if 3 in active:
        evaded = [q for q in sigs["qa_pressure"] if q.get("evasion_flag") is True or q.get("evasion_flag") == "true"
                  or (q.get("pressure_score") is not None and q.get("pressure_score") >= 7)]
        analyst = [x for x in news_all if any(t.lower() in ("analyst", "rating", "upgrade", "target", "price")
                                              for t in (js_or(x.get("topic_tags"), []) or []))]
        pos_analyst = [x for x in analyst if x.get("sentiment_label") == "positive"]
        p = []
        if len(evaded) >= 2 and pos_analyst:
            evaded = sorted(evaded, key=lambda q: -q.get("pressure_score"))  # JS sort is stable, like Python's
            top, an = evaded[0], pos_analyst[0]
            p.append(make_flag(3, "QA Evasion vs Analyst Confidence", "MEDIUM",
                               {**top, "_source": "earnings_agent",
                                "claim_id": f"QA-{js_str(top.get('earnings_call_id'))}-{js_str(top.get('question_topic'))}",
                                "claim_text": f"Topic: {js_str(top.get('question_topic'))}, pressure_score: {js_str(top.get('pressure_score'))}"},
                               {**an, "_source": "news_agent"},
                               f"Management evaded {len(evaded)} high-pressure Q&A topics but analyst coverage is positive",
                               f"Q&A: {len(evaded)} evaded topics, top=\"{js_str(top.get('question_topic'))}\"",
                               "Analyst news: sentiment=positive"))
        results[3] = {"active": True, "flags_raised": len(p)}
        flags += p
    else:
        skipped.append({"pattern_id": 3, "reason": "excluded_by_caller"})

    tech = summ.get("latest_tech")
    # PATTERN 4: Tech Stack Decline vs Positive Guidance
    if 4 in active:
        if not summ["has_tech_stack"]:
            skipped.append({"pattern_id": 4, "reason": "tech_stack_data_unavailable"})
            results[4] = {"active": False, "flags_raised": 0, "data_available": False}
        else:
            declining = tech.get("declining_languages") if isinstance(tech.get("declining_languages"), list) else []
            stale = js_or(tech.get("stale_repo_count"), 0)
            has_decline = len(declining) >= 2 or stale >= 5
            pos_g = [g for g in sigs["guidance_signals"] if g.get("direction") == "strengthened" and num(g.get("direction_confidence")) >= 0.6]
            p = []
            if has_decline and pos_g:
                top_g = pos_g[0]
                p.append(make_flag(4, "Tech Stack Decline vs Positive Guidance", "HIGH", {**top_g, "_source": "earnings_agent"},
                                   {"claim_id": f"TS-{js_str(tech.get('ticker'))}-{js_str(tech.get('snapshot_date'))}",
                                    "_source": "tech_stack_agent",
                                    "claim_text": f"Declining: {', '.join(js_str(x) for x in declining[:3])}; stale repos: {js_str(stale)}",
                                    "direction": "declining"},
                                   "Management projects strengthened guidance but engineering footprint shows decline",
                                   f"Earnings: {len(pos_g)} strengthened signals, top={js_str(top_g.get('guidance_topic'))}",
                                   f"Tech stack: {len(declining)} declining languages, {js_str(stale)} stale repos"))
            results[4] = {"active": True, "flags_raised": len(p), "data_available": True}
            flags += p
    else:
        skipped.append({"pattern_id": 4, "reason": "excluded_by_caller"})

    # PATTERN 5: Engineering Burst vs No Management Disclosure (keywords match as substrings)
    if 5 in active:
        if not summ["has_tech_stack"]:
            skipped.append({"pattern_id": 5, "reason": "tech_stack_data_unavailable"})
            results[5] = {"active": False, "flags_raised": 0, "data_available": False}
        else:
            has_burst = tech.get("burst_detected") is True or tech.get("burst_detected") == "true"
            has_vel = (tech.get("velocity_anomaly") is True or tech.get("velocity_anomaly") == "true"
                       or num(tech.get("velocity_z_score")) >= 2.0)
            emerging = tech.get("emerging_languages") if isinstance(tech.get("emerging_languages"), list) else []
            pivots = [g for g in sigs["guidance_signals"] if g.get("direction") == "strengthened" or (
                js_truthy(g.get("guidance_topic")) and any(kw in js_or(g.get("guidance_topic"), "").lower()
                                                           for kw in ("strategy", "pivot", "expansion", "new", "direction")))]
            p = []
            if (has_burst or has_vel) and len(pivots) == 0:
                p.append(make_flag(5, "Engineering Burst vs Undisclosed Pivot", "HIGH", None,
                                   {"claim_id": f"TS-{js_str(tech.get('ticker'))}-{js_str(tech.get('snapshot_date'))}",
                                    "_source": "tech_stack_agent",
                                    "claim_text": f"Burst ratio={js_str(tech.get('burst_ratio'))}, velocity z-score={js_str(tech.get('velocity_z_score'))}, emerging: {', '.join(js_str(x) for x in emerging[:3])}",
                                    "direction": "burst"},
                                   "Significant engineering burst detected but no corresponding management disclosure on earnings call",
                                   "No earnings guidance matches the engineering direction change",
                                   f"Tech stack: burst={js_str(has_burst)}, velocity_anomaly={js_str(has_vel)}, emerging={js_or(', '.join(js_str(x) for x in emerging), 'none')}"))
            results[5] = {"active": True, "flags_raised": len(p), "data_available": True}
            flags += p
    else:
        skipped.append({"pattern_id": 5, "reason": "excluded_by_caller"})

    # PATTERN 6: Guidance Optimism vs Negative News Momentum (can flag the same guidance claim as Pattern 1, branch 2)
    if 6 in active:
        strong = [g for g in sigs["guidance_signals"] if g.get("direction") == "strengthened" and num(g.get("direction_confidence")) >= 0.7]
        momentum = (summ["news_sentiment_direction"] == "NEGATIVE" and summ["neg_news"] > summ["pos_news"] and len(news_all) >= 5)
        p = []
        if strong and momentum:
            top = sorted(strong, key=lambda g: -num(g.get("direction_confidence")))[0]
            worst = next((x for x in news_all if x.get("sentiment_label") == "negative"), None)
            p.append(make_flag(6, "Guidance Optimism vs Negative News Momentum", "HIGH", {**top, "_source": "earnings_agent"},
                               {**worst, "_source": "news_agent"} if worst else {"_source": "news_agent"},
                               "Management projects high-confidence strengthened guidance against sustained negative news momentum",
                               f"Earnings: {len(strong)} strengthened signals, confidence={js_str(top.get('direction_confidence'))}",
                               f"News: {summ['neg_news']} negative vs {summ['pos_news']} positive, avg={avg2}"))
        results[6] = {"active": True, "flags_raised": len(p)}
        flags += p
    else:
        skipped.append({"pattern_id": 6, "reason": "excluded_by_caller"})

    high = sum(1 for f in flags if f["severity"] == "HIGH")
    med = sum(1 for f in flags if f["severity"] == "MEDIUM")
    has = len(flags) > 0
    level = ("CRITICALLY_COMPROMISED" if high >= 2 else "CONFIDENCE_REDUCED" if high >= 1
             else "REVIEW_WARRANTED" if med >= 2 else "NO_CONTRADICTIONS_DETECTED" if not has else "LOW_CONCERN")
    return {**ctx, "contradiction_flags": flags, "pattern_results": results, "skipped_patterns": skipped,
            "detection_summary": {"total_flags": len(flags), "high_severity": high, "medium_severity": med,
                                  "low_severity": sum(1 for f in flags if f["severity"] == "LOW"),
                                  "patterns_active": sum(1 for v in results.values() if v["active"]),
                                  "patterns_skipped": len(skipped), "has_contradictions": has,
                                  "overall_confidence_level": level, "requires_human_review": has}}


# ── port of "Build Groq Prompt": built exactly, never sent ──────────────────────────────────────────
SYSTEM_PROMPT = ("You are a senior investment intelligence analyst for the Mycroft platform. You receive structured "
                 "contradiction flags produced by automated detection logic. Your job is to: 1. Assess the plausibility of "
                 "each contradiction. 2. Assign an investment relevance score (1-10) to each flag. 3. Identify which "
                 "contradictions are self-resolving vs genuinely irreconcilable. 4. Produce a concise analyst memo (3-5 "
                 "sentences) per flag. 5. Produce a single overall portfolio-level assessment paragraph. Rules: Never "
                 "recommend buy/sell/hold. Surface conflict, do not resolve it. Flag INSUFFICIENT_EVIDENCE when data is "
                 "thin. Cite only evidence provided. Return ONLY valid JSON. No markdown, no preamble.")


def llm_handoff(det: dict) -> dict:
    """The original's prompt, built and recorded as an approval-required handoff. Never sent from this script."""
    base = {"action": "llm_review_of_flags", "model_named_by_original": "llama-3.3-70b-versatile",
            "endpoint_named_by_original": "https://api.groq.com/openai/v1/chat/completions",
            "approved_for_live_action": False, "live_call_performed": False,
            "approval_required_by": "Gate 5 - Approval gate", "judgment_label": "MODEL JUDGMENT (not produced in sample mode)"}
    if not det["detection_summary"]["has_contradictions"]:
        return {**base, "llm_needed": False, "reason": "no flags: the original skips the model (No-Flag Passthrough)"}
    flags, sc, summ = det["contradiction_flags"], det["signal_counts"], det["summaries"]
    flag_summary = "\n\n".join(
        f"[Flag {i + 1}] Pattern {f['pattern_id']} — {f['pattern_name']} | Severity: {f['severity']}\n"
        f"Conflict: {f['conflict_description']}\n"
        f"Evidence A ({js_or(f['claim_a_source'], 'N/A')}): {js_slice(js_or(f['evidence_for_a'], ''), 200)}\n"
        f"Evidence B ({js_or(f['claim_b_source'], 'N/A')}): {js_slice(js_or(f['evidence_for_b'], ''), 200)}"
        for i, f in enumerate(flags))
    user = (f"TICKER: {det['ticker']} | COMPANY: {det['company_name']} | RESOLVE_ID: {det['resolve_id']}\n\n"
            f"SIGNAL INVENTORY:\n- Guidance signals: {sc['guidance']}\n- Risk admissions: {sc['risks']}\n"
            f"- QA pressure items: {sc['qa_items']}\n- News articles: {sc['news']}\n- Tech stack snapshots: {sc['tech_stack']}\n\n"
            f"NEWS SENTIMENT: {summ['news_sentiment_direction']}\n\nDETECTED CONTRADICTION FLAGS ({len(flags)} total):\n\n"
            f"{flag_summary}\n\nReturn JSON (schema as in the original Build Groq Prompt node).")
    return {**base, "llm_needed": True, "payload": {"model": "llama-3.3-70b-versatile", "max_tokens": 2000,
            "temperature": 0.1, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]},
            "credential_policy": "GROQ_API_KEY from the environment only; never hardcoded",
            "live_precondition": "before any live send, confirm the request body carries this prompt (in the exported "
                                 "workflow JSON the Groq node's body parameters are empty)"}


# ── step I/O ────────────────────────────────────────────────────────────────────────────────────────
def emit(data: Any, output: str | None) -> None:
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
    print(text)


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--envelope", default=str(ROOT / f"data/raw/{WORKFLOW_SLUG}/run-envelope.json"))
    ap.add_argument("--fixture-set", help="override the envelope's fixture_set for one run")
    ap.add_argument("--output")
    a = ap.parse_args()
    stops: list[str] = []
    env_path = Path(a.envelope)
    if not env_path.exists():
        emit({"status": "stop", "stop_conditions": [f"run envelope missing: {env_path}"]}, a.output)
        return 1
    env = json.loads(env_path.read_text(encoding="utf-8"))
    if env.get("mode") != "sample":
        emit({"status": "stop", "stop_conditions": ["live mode requested: the LLM handoff needs a gate-5 approval "
                                                     "record naming a human; none exists"],
              "live_call_performed": False}, a.output)
        return 1
    fixture_set = a.fixture_set or env["fixture_set"]
    run = f"{env['run_id']}-{fixture_set}"
    src = ROOT / f"data/verified/{WORKFLOW_SLUG}/runs/{run}/quality-checked"
    bundles = sorted(src.glob("*.json")) if src.exists() else []
    if not bundles:
        stops.append(f"no verified bundles at {src.relative_to(ROOT)}: run steps 2-4 first")
    out_dir = ROOT / f"logs/{WORKFLOW_SLUG}/runs/{run}"
    per = []
    for b in bundles:
        bundle = json.loads(b.read_text(encoding="utf-8"))
        det = detect(aggregate(bundle["ctx"], bundle["rows"]))
        hand = llm_handoff(det)
        write_json(out_dir / "detection" / b.name, det)
        write_json(out_dir / "llm-handoff" / b.name, hand)
        s = det["detection_summary"]
        per.append({"ticker": det["ticker"], "total_flags": s["total_flags"], "high": s["high_severity"],
                    "medium": s["medium_severity"], "overall_confidence_level": s["overall_confidence_level"],
                    "skipped_patterns": [p["pattern_id"] for p in det["skipped_patterns"]],
                    "llm_needed": hand["llm_needed"]})
    result = {"workflow": WORKFLOW_NAME, "node": NODE_NAME, "node_type": NODE_TYPE, "classification": CLASSIFICATION,
              "run": run, "mode": env["mode"], "tool_name": "six-pattern contradiction detector (ported)",
              "input_path": str(src.relative_to(ROOT)), "output_path": str(out_dir.relative_to(ROOT)),
              "action_taken": f"detected over {len(per)} companies; LLM review prepared as handoff, not sent",
              "approval_id": None, "no_write_mode": False, "companies": per,
              "flags_total": sum(p["total_flags"] for p in per), "status": "stop" if stops else "ok",
              "stop_conditions": stops, "live_call_performed": False, "network_access": "none",
              "generated_at": env["frozen_clock"], "next_step": "produce-human-report",
              "human_gate": {"gate": 5, "capacity": "[EI]", "cleared_by": None,
                             "note": "Sending flags to a model is a live action; it needs a gate-5 approval record."}}
    emit(result, a.output)
    return 1 if stops else 0


if __name__ == "__main__":
    raise SystemExit(main())
