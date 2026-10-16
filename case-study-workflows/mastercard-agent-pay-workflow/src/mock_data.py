"""
Fabricated mock data for the Agent Pay reference pipeline.

Nothing here is Mastercard data. No agent IDs, consumer IDs, merchant names,
or permission structures below come from Mastercard, any Mastercard partner,
or any real cardholder. The shape of this data (agents registered/verified;
permissions scoped by category, spending limit, and timeframe) follows
Mastercard's own public description of what Agentic Tokens can be
restricted by (Section 3.2 of the case study: "restrictable by agent,
merchant, category, spending limit, timeframe or usage rules"). The
specific schema below -- field names, data types, how a timeframe is
represented -- is this repository's own invented structure, not a disclosed
Mastercard schema. See docs/DESIGN_DECISIONS.md, Decision 005.

Note on scope: this repository implements category, spending limit, and an
active date window as one illustrative, non-exhaustive realization of the
confirmed restriction dimensions above. Merchant-level and usage-rule-level
restriction are accepted as input fields (so callers can supply them and
they flow through to the Gate context and the intent record) but are not
themselves checked against any consumer-configured value anywhere in this
pipeline -- see README.md, "Known limitations."
"""

from datetime import date

# --- Registered agents -------------------------------------------------
# agent_id -> {"registered": bool, "verified": bool, "consumer_id": str}
#
# "registered" and "verified" are kept as two separate booleans on purpose:
# Mastercard's own language treats registration and verification as two
# distinct preconditions ("agents ... must be registered and verified before
# they can transact"), and this repository preserves that as two separately
# testable failure states rather than collapsing them into one flag.
#
# Two consumers are represented here (not one) specifically so tests can
# exercise a real agent-consumer ownership mismatch -- an agent genuinely
# registered to one consumer, claimed as acting for a different, real
# consumer -- rather than only a claim against a made-up string. See
# docs/DESIGN_DECISIONS.md, Decision 009.
REGISTERED_AGENTS = {
    "agent-concierge-01": {
        "registered": True,
        "verified": True,
        "consumer_id": "devon-01",
    },
    "agent-concierge-02": {
        # Registered on the network, but its verification check has not
        # (or no longer) passed -- e.g. a stand-in for a signature that
        # failed Web Bot Auth validation.
        "registered": True,
        "verified": False,
        "consumer_id": "devon-01",
    },
    "agent-concierge-03": {
        # A second, real, fully valid agent belonging to a DIFFERENT
        # consumer -- used to test that agent-concierge-01 cannot be
        # used to transact on morgan-02's behalf, and vice versa.
        "registered": True,
        "verified": True,
        "consumer_id": "morgan-02",
    },
}

# --- Consumer-configured permissions ------------------------------------
# (consumer_id, agent_id) -> {
#     category: {
#         "spending_limit": float,
#         "active_from": date,
#         "active_until": date,
#         "usage_rule": "one_time" | "recurring",
#     }
# }
#
# A category absent from this dict for a given (consumer_id, agent_id) pair
# means the consumer has never configured that category one way or the
# other -- not that it is blocked. See DD002 / DD003 for why that distinction
# is load-bearing in this pipeline.
CONSUMER_PERMISSIONS = {
    ("devon-01", "agent-concierge-01"): {
        "household_staples": {
            "spending_limit": 150.00,
            "active_from": date(2026, 1, 1),
            "active_until": date(2026, 12, 31),
            "usage_rule": "recurring",
        },
        # NOTE: "footwear" is intentionally NOT configured here. Devon
        # asked the agent, in conversation, to buy the shoes -- but never
        # set a category permission for footwear specifically. This is the
        # UNCONFIGURED case the Authorization Gate exists to handle.
    },
    ("morgan-02", "agent-concierge-03"): {
        "electronics": {
            "spending_limit": 300.00,
            "active_from": date(2026, 1, 1),
            "active_until": date(2026, 12, 31),
            "usage_rule": "one_time",
        },
    },
}
