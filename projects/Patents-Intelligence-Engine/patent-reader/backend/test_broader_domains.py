"""
test_broader_domains.py — broadens classifier testing across 3 genuinely
new, unseen patents, chosen for domain variety:
  - US-12179122 — mechanical advantage device (lockable linkage/seesaw)
  - US-11950867 — single-arm robotic device with compact joint design
  - US-12551228 — mechanically operated device for minimally invasive
    surgery (deliberately closer to the medical/biotech boundary)

Real cost: 3 new exact-match lookups, ~$0.71 each (~$2.13 total).
"""
from google.cloud import bigquery
from claims_agent import ClaimsAgent
import json

client = bigquery.Client(project="patent-intelligence-system")

patent_numbers = ["US-12179122-B2", "US-11950867-B2", "US-12551228-B2"]

agent = ClaimsAgent()

for pub_number in patent_numbers:
    print("=" * 70)
    print(f"Querying: {pub_number}")
    print("=" * 70)

    query = """
    SELECT claims_localized[0].text AS claims_text
    FROM `patents-public-data.patents.publications`
    WHERE publication_number = @pub_number
    LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("pub_number", "STRING", pub_number)]
    )

    try:
        result = list(client.query(query, job_config=job_config).result())
    except Exception as e:
        print(f"Query failed: {e}\n")
        continue

    if not result or not result[0].claims_text:
        print(f"No claims text found for {pub_number} — check the exact "
              f"publication number format (kind code may differ).\n")
        continue

    claims_text = result[0].claims_text
    print(f"Claims text length: {len(claims_text)} characters\n")

    reading = agent.read_claims(
        publication_number=pub_number,
        claims_text=claims_text,
        classify_independent=True,
    )

    print(json.dumps(agent.summarize(reading), indent=2))
    print()
