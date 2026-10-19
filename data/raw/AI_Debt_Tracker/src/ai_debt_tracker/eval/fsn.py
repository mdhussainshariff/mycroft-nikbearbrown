"""SEC Financial Statement and Notes data (D4): download each month and keep only the debt part.

The SEC publishes the latest twelve months as monthly files (`2026_08_notes.zip`) and older
periods as quarterly ones (`2025q3_notes.zip`); a "period" below is either. A monthly zip is ~55 MB compressed and ~2.5 GB unzipped (`num.tsv` alone is ~1.1 GB), and only a
few percent of it is about debt. `extract_month` scans it once and writes a small debt subset
under `$AI_DEBT_DATA/fsn_debt/<yyyy_mm>/`, for every filer, so the answer key, the generalisation
set and the matcher all read megabytes instead of gigabytes:

    sub.tsv       every 10-K / 10-Q (and amendments) in the month, with the columns we use
    dim.tsv       dimension hashes whose segments touch a debt axis
    num.tsv.gz    numeric facts on those dimensions, plus undimensioned company-level debt totals
    txt.tsv.gz    text facts on debt dimensions (maturity dates, when a filer tags them)
    labels.tsv    the human label of every member used on a debt axis (P20: names spell numbers)

This module is used by the grader side only; the agent graph must never import it (P11).
"""

from __future__ import annotations

import csv
import gzip
import io
import re
import zipfile
from pathlib import Path

from .. import config
from ..sec import SecClient

csv.field_size_limit(2**31 - 1)

URL = "https://www.sec.gov/files/dera/data/financial-statement-notes-data-sets/{month}_notes.zip"
LISTING = "https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets"
PERIODIC_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT", "10-KT/A"}
DEBT_AXES = ("DebtInstrument=", "LongtermDebtType=", "ShortTermDebtType=", "CreditFacility=", "LineOfCreditFacility=")
# Company-level totals (no dimensions) kept for L3 grading and the signals (D6 stand-in).
TOTAL_TAGS = {
    "LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent", "DebtCurrent", "LongTermDebtFairValue",
    "DebtInstrumentCarryingAmount", "DebtInstrumentFaceAmount", "CommercialPaper", "ShortTermBorrowings",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
    "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
    "ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromIssuanceOfSeniorLongTermDebt", "RepaymentsOfLongTermDebt",
    "CashAndCashEquivalentsAtCarryingValue", "PaymentsToAcquirePropertyPlantAndEquipment", "InterestExpense",
    "InterestExpenseDebt", "LongTermDebtAndCapitalLeaseObligations", "OperatingLeaseLiability",
    # total debt goes by other names too: Oracle reports LongTermNotesAndLoans + NotesPayableCurrent
    "LongTermNotesAndLoans", "NotesPayableCurrent", "DebtLongtermAndShorttermCombinedAmount",
    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", "LongTermDebtAndCapitalLeaseObligationsCurrent",
}
DEBT_TAG = re.compile(r"^(Debt|LongTermDebt|LongTermLineOfCredit|LineOfCredit|SeniorNotes|SeniorLongTermNotes|"
                      r"ConvertibleNotes|ConvertibleDebt|NotesPayable|LongTermNotesPayable|SecuredDebt|UnsecuredDebt|"
                      r"CommercialPaper|ShortTermBorrowings|OtherLongTermDebt|SubordinatedDebt|LoansPayable|"
                      r"LongTermNotesAndLoans)")
SUB_COLS = ["adsh", "cik", "name", "sic", "countryba", "form", "period", "fy", "fp", "filed", "accepted",
            "prevrpt", "fye", "afs", "aciks"]
NUM_COLS = ["adsh", "tag", "version", "ddate", "qtrs", "uom", "dimh", "coreg", "value", "dcml"]
TXT_TAGS = {"DebtInstrumentMaturityDate", "DebtInstrumentMaturityDateDescription", "DebtInstrumentMaturityDateRangeEnd",
            "DebtInstrumentIssuanceDate", "DebtInstrumentDescription", "DebtInstrumentName"}
TXT_COLS = ["adsh", "tag", "ddate", "qtrs", "dimh", "coreg", "value"]
NO_DIMS = "0x00000000"


def month_dir(month: str) -> Path:
    return config.data_dir() / "fsn_debt" / month


def zip_path(month: str) -> Path:
    return config.data_dir() / "fsn" / f"{month}_notes.zip"


def ensure_zip(month: str, client: SecClient | None = None) -> Path:
    # The Week 0 spike cached ten months under spike/fsn; reuse them rather than download twice.
    old = config.data_dir() / "spike" / "fsn" / f"{month}_notes.zip"
    if old.exists() and not zip_path(month).exists():
        return old
    return (client or SecClient()).download(URL.format(month=month), zip_path(month))


def _reader(z: zipfile.ZipFile, name: str):
    with z.open(name) as f:
        rows = csv.reader(io.TextIOWrapper(f, "utf-8", errors="replace", newline=""), delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(rows)
        idx = {c: i for i, c in enumerate(header)}
        yield idx
        yield from rows


def extract_month(month: str, client: SecClient | None = None, force: bool = False) -> Path:
    out = month_dir(month)
    done = out / "_complete"
    if done.exists() and not force:
        return out
    z = zipfile.ZipFile(ensure_zip(month, client))
    out.mkdir(parents=True, exist_ok=True)

    rows = _reader(z, "sub.tsv")
    idx = next(rows)
    keep = set()
    with open(out / "sub.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(SUB_COLS)
        for r in rows:
            if r[idx["form"]] in PERIODIC_FORMS:
                keep.add(r[idx["adsh"]])
                w.writerow([r[idx[c]] if c in idx else "" for c in SUB_COLS])

    rows = _reader(z, "dim.tsv")
    idx = next(rows)
    dims, members = {}, set()
    for r in rows:
        seg = r[idx["segments"]]
        if any(a in seg for a in DEBT_AXES):
            dims[r[idx["dimhash"]]] = seg
            for part in seg.split(";"):
                if "=" in part:
                    members.add(part.split("=", 1)[1] + "Member")
    with open(out / "dim.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["dimhash", "segments"])
        w.writerows(sorted(dims.items()))

    rows = _reader(z, "tag.tsv")
    idx = next(rows)
    with open(out / "labels.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["tag", "version", "tlabel"])
        for r in rows:
            if r[idx["tag"]] in members:
                w.writerow([r[idx["tag"]], r[idx["version"]], r[idx["tlabel"]]])

    rows = _reader(z, "num.tsv")
    idx = next(rows)
    cols = [idx[c] for c in NUM_COLS]
    i_adsh, i_tag, i_dimh = idx["adsh"], idx["tag"], idx["dimh"]
    n = 0
    with gzip.open(out / "num.tsv.gz", "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(NUM_COLS)
        for r in rows:
            if r[i_adsh] not in keep:
                continue
            dimh, tag = r[i_dimh], r[i_tag]
            if (dimh in dims or dimh == NO_DIMS and tag not in TOTAL_TAGS) and DEBT_TAG.match(tag) \
                    or dimh == NO_DIMS and tag in TOTAL_TAGS:
                w.writerow([r[c] for c in cols])
                n += 1

    rows = _reader(z, "txt.tsv")
    idx = next(rows)
    cols = [idx[c] for c in TXT_COLS]
    with gzip.open(out / "txt.tsv.gz", "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(TXT_COLS)
        for r in rows:
            if r[idx["adsh"]] in keep and r[idx["tag"]] in TXT_TAGS and r[idx["dimh"]] in dims:
                w.writerow([r[c] for c in cols])

    done.write_text(f"{len(keep)} periodic filings, {len(dims)} debt dimensions, {n} numeric facts\n")
    return out


def read_tsv(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)


def months_between(first: str, last: str) -> list[str]:
    y, m = map(int, first.split("_"))
    ly, lm = map(int, last.split("_"))
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}_{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def available_periods(client: SecClient | None = None) -> set[str]:
    html = (client or SecClient()).get(LISTING, cache=False).decode("utf-8", "ignore")
    return set(re.findall(r"financial-statement-notes-data-sets/(\w+)_notes\.zip", html))


def periods_covering(first: str, last: str, available: set[str]) -> list[str]:
    """Each month from `first` to `last` (yyyy_mm), mapped to the file that holds it: the monthly
    file when published, else the quarterly one. Raises if a month is in neither."""
    out = []
    for m in months_between(first, last):
        y, mo = m.split("_")
        q = f"{y}q{(int(mo) - 1) // 3 + 1}"
        pick = m if m in available else q if q in available else None
        if pick is None:
            raise LookupError(f"no notes data set covers {m}")
        if pick not in out:
            out.append(pick)
    return out


if __name__ == "__main__":
    import sys
    from concurrent.futures import ProcessPoolExecutor

    client = SecClient()
    months = periods_covering(sys.argv[1], sys.argv[2], available_periods(client))
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    for m in months:  # downloads one at a time (one rate limit), extraction in parallel
        ensure_zip(m, client)
        print("downloaded", m, flush=True)
    with ProcessPoolExecutor(workers) as ex:
        for m, out in zip(months, ex.map(extract_month, months)):
            print(m, (out / "_complete").read_text().strip(), flush=True)
