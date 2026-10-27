"""
agent/research_agent.py  —  Sprint 2 (improved): LangGraph research agent.

Improvements over the first version:
1. The agent tries a DIFFERENT search strategy each round instead of repeating the
   same one. Now looping actually does something — which is what makes it agentic.
2. A per-round "confidence" note: the agent reasons about whether it's making progress.
3. Cleaner decision log with round-by-round strategy shown.

Still CONTROL FLOW ONLY (Sprint 2). No LLM extraction yet (that's Sprint 3).

Requires: langgraph  (pip install langgraph)
Run:
    python -m agent.research_agent --company openai
    python -m agent.research_agent --company nvidia --target 3 --max-rounds 4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.graph import StateGraph, END  # noqa: E402

from ingest.fetch_news import fetch, TRACKED_VENDORS  # noqa: E402


# Each round the agent widens its net: exact match -> alias match -> broad keyword.
# This is the "try a different angle" strategy that makes looping meaningful.
STRATEGIES = ["exact", "alias", "broad"]


class AgentState(TypedDict):
    company: str
    rounds: int
    max_rounds: int
    target: int
    gathered: list
    decisions: list
    done: bool
    no_progress_streak: int   # rounds in a row that found nothing new


def _keywords(company: str, strategy: str) -> list[str]:
    """Return the search terms for this round's strategy."""
    aliases = TRACKED_VENDORS.get(company, [company])
    if strategy == "exact":
        return [company]
    if strategy == "alias":
        return aliases
    # broad: aliases plus generic AI terms, to catch adjacent mentions
    return aliases + ["ai", "model", "funding", "launch"]


def plan(state: AgentState) -> AgentState:
    strategy = STRATEGIES[min(state["rounds"], len(STRATEGIES) - 1)]
    state["decisions"].append(
        f"[plan] round {state['rounds'] + 1}: strategy='{strategy}' "
        f"(have {len(state['gathered'])}/{state['target']})"
    )
    return state


def search_and_read(state: AgentState) -> AgentState:
    state["rounds"] += 1
    strategy = STRATEGIES[min(state["rounds"] - 1, len(STRATEGIES) - 1)]
    company = state["company"].lower()
    terms = _keywords(company, strategy)

    all_candidates = fetch()
    found = [
        c for c in all_candidates
        if c["company_id"] == company
        or any(t in c["signal_title"].lower() for t in terms)
    ]
    have_ids = {g["signal_id"] for g in state["gathered"]}
    new = [c for c in found if c["signal_id"] not in have_ids]
    state["gathered"].extend(new)

    if new:
        state["no_progress_streak"] = 0
    else:
        state["no_progress_streak"] += 1

    state["decisions"].append(
        f"[search] round {state['rounds']} ('{strategy}'): found {len(new)} new "
        f"(total {len(state['gathered'])})"
    )
    return state


def decide(state: AgentState) -> AgentState:
    enough = len(state["gathered"]) >= state["target"]
    exhausted = state["rounds"] >= state["max_rounds"]
    # new stop condition: if the last 2 rounds found nothing, widening won't help
    stuck = state["no_progress_streak"] >= 2

    if enough:
        state["decisions"].append(f"[decide] STOP: reached target ({state['target']})")
        state["done"] = True
    elif exhausted:
        state["decisions"].append(
            f"[decide] STOP: hit max_rounds ({state['max_rounds']}) with "
            f"{len(state['gathered'])} signals -- not inventing data"
        )
        state["done"] = True
    elif stuck:
        state["decisions"].append(
            f"[decide] STOP: 2 rounds with no new signals -- more looping won't help "
            f"(have {len(state['gathered'])})"
        )
        state["done"] = True
    else:
        state["decisions"].append("[decide] LOOP: not enough yet -- try a wider strategy")
        state["done"] = False
    return state


def route(state: AgentState) -> str:
    return "stop" if state["done"] else "loop"


def build_agent():
    g = StateGraph(AgentState)
    g.add_node("plan", plan)
    g.add_node("search", search_and_read)
    g.add_node("decide", decide)
    g.set_entry_point("plan")
    g.add_edge("plan", "search")
    g.add_edge("search", "decide")
    g.add_conditional_edges("decide", route, {"loop": "plan", "stop": END})
    return g.compile()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--target", type=int, default=2)
    ap.add_argument("--max-rounds", type=int, default=3)
    args = ap.parse_args()

    agent = build_agent()
    initial: AgentState = {
        "company": args.company, "rounds": 0, "max_rounds": args.max_rounds,
        "target": args.target, "gathered": [], "decisions": [], "done": False,
        "no_progress_streak": 0,
    }
    final = agent.invoke(initial)

    print(f"\nRESEARCH AGENT -- {args.company}")
    print("=" * 52)
    print("Agent decision log (the agentic part):")
    for d in final["decisions"]:
        print("  " + d)
    print()
    print(f"Gathered {len(final['gathered'])} signal(s) in {final['rounds']} round(s):")
    for s in final["gathered"]:
        print(f"  - {s['company_id']}: {s['signal_title'][:60]}")
    print()
    print("NOTE: signals UNVALIDATED (P2). Structured extraction is Sprint 3.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
