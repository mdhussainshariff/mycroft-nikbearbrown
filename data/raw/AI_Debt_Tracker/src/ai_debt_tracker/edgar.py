"""A company's EDGAR filing index (D1), shared by the agent's `edgar_pit` server and the build scripts.

`load_filings` reads `data.sec.gov/submissions` including the older pages EDGAR splits off once a
filer passes ~1,000 filings (Alphabet and Amazon do, through their bond prospectuses). Filings
whose acceptance time cannot be read are dropped, so a point-in-time check can fail closed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .sec import SecClient

SUBMISSIONS = "https://data.sec.gov/submissions/{name}"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/"


@dataclass(frozen=True)
class FilingRef:
    accession: str
    form: str
    filing_date: str
    accepted: str            # normalised YYYY-MM-DDTHH:MM:SS
    items: str
    primary_document: str
    report_date: str


def normalise_time(t: str) -> str:
    """'2026-08-12T16:05:23.000Z' / '2026-08-12 16:05:23' / '2026-08-12' -> '2026-08-12T16:05:23'."""
    t = t.strip().replace(" ", "T").rstrip("Z")
    t = t.split(".")[0]
    if len(t) == 10:
        t += "T00:00:00"
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", t):
        raise ValueError(f"not a timestamp: {t!r}")
    return t


def load_filings(client: SecClient, cik: int) -> dict[str, FilingRef]:
    first = json.loads(client.get(SUBMISSIONS.format(name=f"CIK{int(cik):010d}.json"), cache=False))
    pages = [first["filings"]["recent"]]
    for f in first["filings"].get("files", []):
        pages.append(json.loads(client.get(SUBMISSIONS.format(name=f["name"]), cache=False)))
    refs = {}
    for p in pages:
        n = len(p["accessionNumber"])

        def col(k, i, p=p, n=n):
            return (p.get(k) or [""] * n)[i]

        for i in range(n):
            try:
                accepted = normalise_time(col("acceptanceDateTime", i))
            except ValueError:
                continue  # cannot be dated -> never visible to a point-in-time reader
            refs[p["accessionNumber"][i]] = FilingRef(
                accession=p["accessionNumber"][i], form=col("form", i), filing_date=col("filingDate", i),
                accepted=accepted, items=col("items", i) or "", primary_document=col("primaryDocument", i),
                report_date=col("reportDate", i) or "")
    return refs


def filers_in_header(client: SecClient, cik: int, accession: str) -> list[tuple[int, str]]:
    """Every (CIK, name) listed as a filer on one filing — co-registrants such as an issuing
    subsidiary appear here (P12)."""
    url = ARCHIVE.format(cik=int(cik), acc_nodash=accession.replace("-", "")) + f"{accession}.hdr.sgml"
    text = client.get(url).decode("utf-8", "ignore")
    out = []
    for block in re.findall(r"(?s)<(?:FILER|SUBJECT-COMPANY)>(.*?)</(?:FILER|SUBJECT-COMPANY)>", text):
        name = re.search(r"<CONFORMED-NAME>([^\n<]+)", block)
        c = re.search(r"<CIK>(\d+)", block)
        if name and c:
            out.append((int(c.group(1)), name.group(1).strip()))
    return out
