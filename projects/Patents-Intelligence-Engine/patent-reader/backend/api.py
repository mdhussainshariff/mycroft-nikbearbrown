"""
api.py — FastAPI backend wrapping the already-verified ClaimsAgent and
LineageAgent, exposing the same real logic as patent_reader.py through
a real HTTP endpoint instead of a CLI.

Run with:
    .venv/bin/uvicorn api:app --reload --port 8000

Real cost note (same as patent_reader.py): a genuinely new patent
number costs ~$0.71 in BigQuery scan cost; a cached one is free.
Classification (if enabled) always costs a small, real, fresh
Claude API fee, since Claude doesn't cache the way BigQuery does.
"""
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import bigquery

from claims_agent import ClaimsAgent
from lineage_agent import LineageAgent
from dotenv import load_dotenv
load_dotenv()
app = FastAPI(title="Patent Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

bq_client = bigquery.Client(project="patent-intelligence-system")


class PatentReading(BaseModel):
    publication_number: str
    claims: Optional[dict]
    lineage: Optional[dict]


def fetch_patent_row(pub_number: str):
    query = """
    SELECT publication_number, claims_localized[0].text AS claims_text, citation
    FROM `patents-public-data.patents.publications`
    WHERE publication_number = @pub_number
    LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("pub_number", "STRING", pub_number)]
    )
    result = list(bq_client.query(query, job_config=job_config).result())
    return result[0] if result else None


@app.get("/patent/{publication_number}", response_model=PatentReading)
def read_patent(publication_number: str, classify: bool = True):
    """
    Real endpoint: mirrors patent_reader.py exactly. `classify` defaults
    to True but can be set to false to skip the Claude API call entirely.
    """
    row = fetch_patent_row(publication_number)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No row found for {publication_number}. "
                    f"Check the exact publication number format (kind code, dashes)."
        )

    result = {"publication_number": row.publication_number, "claims": None, "lineage": None}

    if row.claims_text:
        claims_agent = ClaimsAgent()
        claims_reading = claims_agent.read_claims(
            publication_number=row.publication_number,
            claims_text=row.claims_text,
            classify_independent=classify,
        )
        result["claims"] = claims_agent.summarize(claims_reading)

    if row.citation:
        lineage_agent = LineageAgent()
        raw_rows = []
        for c in row.citation:
            raw_rows.append(dict(c.items()) if hasattr(c, "items") else dict(c))
        backward = lineage_agent.parse_backward_citations(row.publication_number, raw_rows)
        result["lineage"] = lineage_agent.summarize(backward)
    else:
        result["lineage"] = {"total_citations": 0}

    return result


@app.get("/health")
def health_check():
    return {"status": "ok"}
