"""A full run: every frozen fixture through the whole gateway.

Two things happen per fixture, and they are deliberately separate:

  CHECKING is free and automatic -- does the answer have a usable shape?
  GRADING needs the answer key -- is the answer actually right?

The number this run exists to produce is where those two disagree:
answers that PASSED the check and were still WRONG. Those are the ones no
free check can catch and no escalation will ever fix, and they set the floor
on what retrying can buy you.

Refuses to run if the fixture set has drifted from its manifest: grading
against an answer key that changed after it was frozen is not evidence.

Every run writes its own log file, stamped to the second. On 2026-09-17 a
smoke run and a full run shared one dated file, and the summary silently
counted the smoke run's three requests as part of the full sweep.

Usage:
    $env:GROQ_API_KEY="gsk_..."
    python scripts/gateway/bench/run.py --dry-run     # cost bound, no calls
    python scripts/gateway/bench/run.py --limit 3     # a cheap smoke test
    python scripts/gateway/bench/run.py               # the full 24
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gateway import prompts
from gateway.adapters.groq import GroqAdapter
from gateway.bench import fixtures as fx
from gateway.client import GatewayClient
from gateway.gateway import Gateway, GatewayResult
from gateway.logbook import Logbook
from gateway.policy import Policy
from gateway.prices import PriceTable
from gateway.report import read_records, summary
from gateway.router import route
from gateway.tiers import TierConfig

RESULTS_DIR = Path(__file__).with_name("results")
LOG_DIR = Path("logs/gateway/runs")


def grade(fixture: dict[str, Any], result: GatewayResult) -> dict[str, Any]:
    """Compare the final answer with the answer key, where there is one."""
    final = result.records[-1] if result.records else {}
    checked = final.get("validator_result") or {}
    expected = fixture["expected"]

    if "label" in expected:  # label and verdict tasks
        got = checked.get("label") or checked.get("verdict")
        return {"graded": True, "correct": got == expected["label"],
                "expected": expected["label"], "got": got}

    if "cite" in expected:
        cited = checked.get("cited") or []
        return {"graded": True, "correct": expected["cite"] in cited,
                "expected": expected["cite"], "got": cited}

    if "required_keys" in expected:
        return {"graded": False, "correct": None,
                "reason": "the key check cannot tell a right answer from an invented one"}

    return {"graded": False, "correct": None,
            "reason": "open prose; correctness needs the Sprint 5 judge"}


def cost_bound(fixtures: list[dict[str, Any]], policy: Policy, tiers: TierConfig,
               prices: PriceTable) -> float:
    """A loose UPPER bound: every request escalates and fills its token budget."""
    total = 0.0
    for fixture in fixtures:
        rule = policy.rule_for(fixture["task_type"])
        prompt = prompts.build(rule, fixture["input"],
                               context=fixture.get("context"),
                               required_keys=fixture["expected"].get("required_keys"))
        decision = route(task_type=fixture["task_type"], text=fixture["input"],
                         policy=policy, tiers=tiers)
        for tier in filter(None, (decision.tier, decision.escalate_to)):
            spec = tiers.spec(tier)
            total += prices.cost_usd(spec["provider"], spec["model"],
                                     len(prompt), policy.max_tokens(tier))
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen fixtures live.")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would run and the cost bound; make no calls")
    parser.add_argument("--limit", type=int, default=0,
                        help="run only the first N fixtures")
    args = parser.parse_args()

    prices = PriceTable.load()
    if prices.version == "UNSET":
        print("prices.json has no real rates. Nothing was called.")
        return 1

    tiers = TierConfig.load()
    policy = Policy.load(tiers)

    if not fx.MANIFEST_PATH.exists():
        print("The fixture set is not frozen. Run audit.py --freeze first.")
        return 1
    manifest = json.loads(fx.MANIFEST_PATH.read_text(encoding="utf-8"))
    drift = fx.check_manifest(manifest)
    if drift:
        print("The fixture set has changed since it was frozen:")
        for line in drift:
            print(f"  - {line}")
        print("Re-freeze deliberately, or restore the files. Nothing was called.")
        return 1

    items = fx.validate(fx.load(), policy)
    items.sort(key=lambda f: f["id"])
    if args.limit:
        items = items[:args.limit]

    bound = cost_bound(items, policy, tiers, prices)
    print(f"{len(items)} fixtures, frozen {manifest['frozen_on']}")
    print(f"policy {policy.version} · tiers {tiers.version} · prices {prices.version}")
    print(f"at most {len(items) * 2} calls, costing at most ${bound:.4f} "
          f"(every request escalating and filling its budget)")

    if args.dry_run:
        for fixture in items:
            decision = route(task_type=fixture["task_type"], text=fixture["input"],
                             policy=policy, tiers=tiers)
            print(f"  {fixture['id']:<12} {decision.tier:<7} -> "
                  f"{decision.escalate_to or '(no retry)'}")
        print("\nDry run: nothing was called.")
        return 0

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("\nGROQ_API_KEY is not set. Nothing was called.")
        return 1
    if input("\nType 'yes' to make these calls: ").strip().lower() != "yes":
        print("Cancelled. Nothing was called.")
        return 1

    # Stamped to the second: two runs on one day must not share a log file,
    # or the summary counts the earlier run's requests as part of this one.
    run_id = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{run_id}-sprint4-run.jsonl"

    client = GatewayClient(logbook=Logbook(log_path, prices),
                           adapters={"groq": GroqAdapter(api_key=api_key)},
                           tiers=tiers.as_client_map(),
                           policy_version=policy.version)
    gateway = Gateway(client=client, policy=policy, tiers=tiers, caller="bench/run.py")

    rows: list[dict[str, Any]] = []
    print(f"\n{'fixture':<12}{'route':<16}{'att':>4}{'outcome':>15}"
          f"{'graded':>9}{'cost':>11}")

    for fixture in items:
        result = gateway.handle(task_type=fixture["task_type"], text=fixture["input"],
                                context=fixture.get("context"),
                                required_keys=fixture["expected"].get("required_keys"))
        scored = grade(fixture, result)
        final = result.records[-1] if result.records else {}
        checked = final.get("validator_result") or {}

        rows.append({
            "id": fixture["id"], "task_type": fixture["task_type"],
            "difficulty": fixture["difficulty"],
            "expected_tier": fixture["expected_tier"],
            "routed_tier": result.decision.tier, "final_tier": result.final_tier,
            "attempts": result.attempts, "escalated": result.escalated,
            "passed_check": result.passed, "check_reason": checked.get("reason", ""),
            "outcome": final.get("outcome"), "error": result.error,
            "cost_usd": result.total_cost_usd, "latency_ms": result.total_latency_ms,
            "text": result.text, "request_id": result.request_id, **scored,
        })

        graded = ("-" if not scored["graded"]
                  else "correct" if scored["correct"] else "WRONG")
        route_shown = (f"{result.decision.tier}->{result.final_tier}"
                       if result.escalated else result.decision.tier)
        print(f"{fixture['id']:<12}{route_shown:<16}{result.attempts:>4}"
              f"{str(final.get('outcome')):>15}{graded:>9}"
              f"{result.total_cost_usd:>11.6f}")

    # -- what the run measured -------------------------------------------

    # Scoped to this run's own requests, never the whole file.
    run_request_ids = {r["request_id"] for r in rows}
    stats = summary([x for x in read_records(log_path)
                     if x["request_id"] in run_request_ids])

    graded_rows = [r for r in rows if r["graded"]]
    correct = [r for r in graded_rows if r["correct"]]
    wrong_but_valid = [r for r in graded_rows
                       if not r["correct"] and r["passed_check"]]
    agreed = [r for r in rows if r["routed_tier"] == r["expected_tier"]]
    errored = [r for r in rows if r["error"]]

    print(f"\nrequests {stats['requests']} · attempts {stats['attempts']} · "
          f"escalation {stats['escalation_rate']:.0%} · "
          f"failure {stats['failure_rate']:.0%}")
    print(f"cost ${stats['total_cost_usd']:.5f} total, "
          f"${stats['mean_cost_per_request_usd']:.6f} per request")
    print(f"latency p50 {stats['p50_latency_ms']:.0f} ms · "
          f"p95 {stats['p95_latency_ms']:.0f} ms")
    print(f"graded {len(graded_rows)}/{len(rows)} · "
          f"correct {len(correct)}/{len(graded_rows)}")
    print(f"router agreed with the labels on {len(agreed)}/{len(rows)}")

    if errored:
        print(f"\nprovider errors: {len(errored)} "
              f"(these graded as wrong without the model answering)")
        for row in errored:
            print(f"  {row['id']:<12} {str(row['error'])[:100]}")

    print(f"\nWRONG BUT PASSED THE CHECK: {len(wrong_but_valid)}")
    for row in wrong_but_valid:
        print(f"  {row['id']:<12} expected {row['expected']!r}, got {row['got']!r}")
    print("  (no free check can catch these, and no retry will fix them)")

    results_path = RESULTS_DIR / f"{run_id}-sprint4-run.json"
    results_path.write_text(json.dumps({
        "run_id": run_id, "run_on": date.today().isoformat(),
        "policy_version": policy.version, "tiers_version": tiers.version,
        "prices_version": prices.version,
        "fixtures_frozen_on": manifest["frozen_on"],
        "summary": stats, "rows": rows,
    }, indent=2) + "\n", encoding="utf-8")

    print(f"\nlogbook  {log_path}")
    print(f"results  {results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())