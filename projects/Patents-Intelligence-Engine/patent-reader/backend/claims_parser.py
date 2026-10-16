"""
claims_parser.py — splits raw patent claims text into individual claims,
classifies independent vs. dependent, and flags genuine multi-dependency
references.

Tested against 4 original real patents (64/64 claims correct) plus 3
more real patents during broader domain testing. That broader test
found a real gap: US-12551228-B2 uses "1 ." (space before the period)
instead of "1." for claim numbering, which the original regex missed
entirely, silently returning 0 claims. Fixed below by allowing optional
whitespace between the number and the period.
"""
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Claim:
    number: int
    text: str
    is_independent: bool
    references: Optional[int]
    all_references: List[int]


# Claims are numbered at the start of a line/segment. Some patents use
# "1." with no space; others (confirmed real case: US-12551228-B2) use
# "1 ." with a space before the period. \s* between the digits and the
# period handles both.
CLAIM_SPLIT_PATTERN = re.compile(
    r"(?:^|\n)\s*(\d+)\s*\.\s+(.*?)(?=(?:\n\s*\d+\s*\.\s+)|\Z)",
    re.DOTALL,
)

DEPENDENCY_PATTERN = re.compile(r"claim[s]?\s+(\d+)", re.IGNORECASE)

# Only matches a genuine multi-claim reference directly after the word
# "claim(s)" — not any "or" elsewhere in the claim body (see README
# "Known limitation" history — this was a real, fixed false-positive bug).
MULTI_DEPENDENCY_PATTERN = re.compile(
    r"claim[s]?\s+\d+\s*(?:,|or|and|-|to)\s*\d+",
    re.IGNORECASE,
)


def split_claims(raw_claims_text: str) -> List[Claim]:
    """
    Split raw claims text into a list of Claim objects.

    NOTE: this regex-based split is a first pass, not a guaranteed-correct
    parser. Known real formatting variations handled: "1." and "1 .".
    Other variations may still exist and haven't been seen yet — if a
    real patent's claims_text is non-empty but split_claims returns an
    empty list, that's a signal to inspect the raw text by hand before
    assuming zero claims, exactly as happened with US-12551228-B2.
    """
    if not raw_claims_text or not raw_claims_text.strip():
        return []

    matches = CLAIM_SPLIT_PATTERN.findall(raw_claims_text)
    claims = []

    for number_str, body in matches:
        number = int(number_str)
        body = body.strip()

        all_refs = [int(n) for n in DEPENDENCY_PATTERN.findall(body)]
        is_independent = len(all_refs) == 0
        first_reference = all_refs[0] if all_refs else None

        claims.append(Claim(
            number=number,
            text=body,
            is_independent=is_independent,
            references=first_reference,
            all_references=all_refs,
        ))

    return claims


def flag_multi_dependency(claim: Claim) -> bool:
    """
    Returns True only if the claim text contains a genuine multi-claim
    reference pattern (e.g. "claim 1 or 2", "claims 1-3").
    """
    if claim.is_independent:
        return False
    return bool(MULTI_DEPENDENCY_PATTERN.search(claim.text))


def summarize(claims: List[Claim]) -> dict:
    independent = [c for c in claims if c.is_independent]
    dependent = [c for c in claims if not c.is_independent]
    return {
        "total_claims": len(claims),
        "independent_count": len(independent),
        "dependent_count": len(dependent),
        "independent_numbers": [c.number for c in independent],
    }
