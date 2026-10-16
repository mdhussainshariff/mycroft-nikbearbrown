"""
schema/signal.py  —  the typed schema every signal must conform to (Week 1).

This is the contract for the whole pipeline. Any signal that reaches the scorer
must be a valid Signal: correct types, a real source_url, a parseable date.
Malformed records are rejected HERE, at the door, before they can poison anything
downstream. That is the point of a schema-first design.

Requires: pydantic v2  (pip install pydantic)
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class SignalType(str, Enum):
    """The kinds of signal the runway scorer understands.

    Using an Enum means a typo like 'funding_rnd' is rejected automatically —
    the schema will only accept these exact values.
    """
    funding_round = "funding_round"
    funding_stage = "funding_stage"
    layoff = "layoff"
    executive_change = "executive_change"
    security_issue = "security_issue"
    product_launch = "product_launch"
    news_mention = "news_mention"


class Signal(BaseModel):
    """One validated fact about a company.

    Every field is typed. pydantic enforces the types at construction time:
    build a Signal with a bad date, a missing source, or an unknown signal_type
    and it raises a ValidationError instead of silently accepting garbage.
    """

    signal_id: str = Field(..., min_length=1, description="unique id for this signal")
    company_id: str = Field(..., min_length=1, description="stable company slug")
    signal_type: SignalType
    signal_title: str = Field(..., min_length=1)
    signal_value: str = Field(..., description="e.g. '$45M', 'Series B', 'negative'")
    occurred_date: date = Field(..., description="when the event happened")
    source_url: HttpUrl = Field(..., description="provenance — where this came from (P3)")

    # confidence 0-100; softer sources (news) score lower than filings
    score: int = Field(..., ge=0, le=100)

    # P2: a signal only counts once a human has validated it. Null until then.
    validated_by: Optional[str] = None
    validation_note: Optional[str] = None
    validation_date: Optional[date] = None

    ingested_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("occurred_date")
    @classmethod
    def not_in_future(cls, v: date) -> date:
        """A signal can't have happened in the future. Reject impossible dates."""
        if v > date.today():
            raise ValueError(f"occurred_date {v} is in the future")
        return v

    @property
    def is_validated(self) -> bool:
        """P2: only human-validated signals inform the brief."""
        return bool(self.validated_by)
