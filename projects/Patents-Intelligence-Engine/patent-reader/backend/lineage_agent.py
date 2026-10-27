"""
lineage_agent.py — the real LineageAgent class. First build: backward
citations only (what a patent cites), since these are a direct field
on the same row already being queried — genuinely cheap, no separate
lookup needed. Forward citations (who cites this patent) would require
searching for this patent's number inside OTHER patents' citation
arrays — a real, different, and likely much more expensive query
pattern, deliberately deferred until backward citations are proven.

Real schema, confirmed via BigQuery console (free, no query cost):
citation is RECORD, REPEATED, with fields: publication_number,
application_number, npl_text, type, category, filing_date.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Citation:
    publication_number: Optional[str]
    application_number: Optional[str]
    npl_text: Optional[str]
    citation_type: Optional[str]
    category: Optional[str]
    filing_date: Optional[int]

    @property
    def is_non_patent_literature(self) -> bool:
        # BigQuery returns empty strings, not None, for missing fields
        # on this table — confirmed by inspecting real output where
        # npl_text was '' (not None) even for a citation that had a
        # real publication_number. Check for genuinely non-empty text
        # instead of "is not None".
        return bool(self.npl_text) and not bool(self.publication_number)


@dataclass
class BackwardCitations:
    publication_number: str
    citations: List[Citation] = field(default_factory=list)

    @property
    def patent_citation_count(self) -> int:
        return sum(1 for c in self.citations if not c.is_non_patent_literature)

    @property
    def npl_citation_count(self) -> int:
        return sum(1 for c in self.citations if c.is_non_patent_literature)


class LineageAgent:
    """
    Traces a patent's citation lineage. Currently backward-only. Forward
    citations are NOT implemented — that requires a different, untested
    query pattern.
    """

    def parse_backward_citations(self, publication_number: str, raw_citation_rows: list) -> BackwardCitations:
        """
        NOTE: untested against real BigQuery output as of writing this
        — verify field access against an actual query result before
        trusting it.
        """
        result = BackwardCitations(publication_number=publication_number)

        for row in raw_citation_rows:
            citation = Citation(
                publication_number=row.get("publication_number") or None,
                application_number=row.get("application_number") or None,
                npl_text=row.get("npl_text") or None,
                citation_type=row.get("type") or None,
                category=row.get("category") or None,
                filing_date=row.get("filing_date") or None,
            )
            result.citations.append(citation)

        return result

    def summarize(self, backward: BackwardCitations) -> dict:
        return {
            "publication_number": backward.publication_number,
            "total_citations": len(backward.citations),
            "patent_citations": backward.patent_citation_count,
            "non_patent_literature_citations": backward.npl_citation_count,
            "cited_publication_numbers": [
                c.publication_number for c in backward.citations
                if c.publication_number
            ],
        }
