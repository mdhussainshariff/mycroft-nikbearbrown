"""
agent/research_agent.py  —  Sprint 2: the LangGraph research agent (control flow only).

Given a company name, the agent runs a loop:
    plan -> search -> read -> decide('enough?') -> (loop or stop)

This sprint is CONTROL FLOW ONLY. The agent decides *what to do and when to stop* --
it does NOT yet use an LLM to extract structured signals (that is Sprint 3). The
"search" step reuses the Sprint 1 RSS ingestion as its source. What Sprint 2 proves
is the AGENTIC part: branching decisions + a hard stop condition, every decision logged.

Why this is genuinely agentic (and why LangGraph fits):
- The agent BRANCHES: after reading, it decides whether to search again or stop.
- It has a HARD STOP: enough signals found, OR max rounds reached (never loops forever).
- decide -> loop is a state machine, which is exactly what LangGraph models.

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

# reuse Sprint 1's real ingestion as the agent's "search" tool
from ingest.fetch_news import fetch, TRACKED_VENDORS  # noqa: E402


# ---- the agent's state (what flows through the graph) ------------------------
class AgentState(TypedDict):
    company: str          # who we're researching
    rounds: int           # how many search rounds done so far
    max_rounds: int       # hard stop: never loop more than this
    target: int           # how many signals is "enough"
    gathered: list        # signals found so far
    decisions: list       # a log of every decision the agent made
    done: bool            # stop flag


# ---- nodes: each is one step the agent can take ------------------------------

def plan(state: AgentState) -> AgentState:
    """Decide the approach for this round. (Simple here; real planning gets richer.)"""
    state["decisions"].append(
        f"[plan] round {state['rounds'] + 1}: search news for '{state['company']}' "
        f"(have {len(state['gathered'])}/{state['target']})"
    )
    return state


def search_and_read(state: AgentState) -> AgentState:
    """
    The 'search + read' step. In Sprint 2 this uses the Sprint 1 RSS fetch as its
    source, keeping only items about the target company. New signals are added; dups skipped.
    """
    state["rounds"] += 1
    all_candidates = fetch()  # real RSS pull (from Sprint 1)
    company = state["company"].lower()
    aliases = TRACKED_VENDORS.get(company, [company])
    found = [
        c for c in all_candidates
        if c["company_id"] == company
        or any(a in c["signal_title"].lower() for a in aliases)
    ]
    have_ids = {g["signal_id"] for g in state["gathered"]}
    new = [c for c in found if c["signal_id"] not in have_ids]
    state["gathered"].extend(new)
    state["decisions"].append(
        f"[search] round {state['rounds']}: found {len(new)} new "
        f"(total {len(state['gathered'])})"
    )
    return state


def decide(state: AgentState) -> AgentState:
    """
    The agentic decision: enough, or loop -- plus the HARD STOP.
    This is the branching brain of the agent.
    """
    enough = len(state["gathered"]) >= state["target"]
    exhausted = state["rounds"] >= state["max_rounds"]
    if enough:
        state["decisions"].append(f"[decide] STOP: reached target ({state['target']})")
        state["done"] = True
    elif exhausted:
        state["decisions"].append(
            f"[decide] STOP: hit max_rounds ({state['max_rounds']}) with "
            f"{len(state['gathered'])} signals -- stopping the loop, not inventing data"
        )
        state["done"] = True
    else:
        state["decisions"].append("[decide] LOOP: not enough yet, search again")
        state["done"] = False
    return state


def route(state: AgentState) -> str:
    """Conditional edge: 'stop' ends the graph, 'loop' returns to plan."""
    return "stop" if state["done"] else "loop"


# ---- build the graph (the state machine) -------------------------------------
def build_agent():
    g = StateGraph(AgentState)
    g.add_node("plan", plan)
    g.add_node("search", search_and_read)
    g.add_node("decide", decide)

    g.set_entry_point("plan")
    g.add_edge("plan", "search")
    g.add_edge("search", "decide")
    # the branch: decide -> loop back to plan, or stop -> END
    g.add_conditional_edges("decide", route, {"loop": "plan", "stop": END})
    return g.compile()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True, help="company_id to research (e.g. openai)")
    ap.add_argument("--target", type=int, default=2, help="how many signals is 'enough'")
    ap.add_argument("--max-rounds", type=int, default=3, help="hard stop: max search rounds")
    args = ap.parse_args()

    agent = build_agent()
    initial: AgentState = {
        "company": args.company,
        "rounds": 0,
        "max_rounds": args.max_rounds,
        "target": args.target,
        "gathered": [],
        "decisions": [],
        "done": False,
    }
    final = agent.invoke(initial)

    print(f"\nRESEARCH AGENT -- {args.company}")
    print("=" * 52)
    print("Agent decision log (this is the 'agentic' part):")
    for d in final["decisions"]:
        print("  " + d)
    print()
    print(f"Gathered {len(final['gathered'])} signal(s) in {final['rounds']} round(s):")
    for s in final["gathered"]:
        print(f"  - {s['company_id']}: {s['signal_title'][:60]}")
    print()
    print("NOTE: signals are UNVALIDATED (Sprint 1 rule). Turning them into precise")
    print("      structured signals is Sprint 3. Sprint 2 = the agent loop only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
