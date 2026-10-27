"""
inspect_parse_failure.py — investigates why claims_parser.split_claims()
returned 0 claims for US-12551228-B2 despite real, non-empty claims_text
(9359 characters). Uses the already-cached query, costs nothing new.
"""
from google.cloud import bigquery
from claims_parser import split_claims

client = bigquery.Client(project="patent-intelligence-system")

query = """
SELECT claims_localized[0].text AS claims_text
FROM `patents-public-data.patents.publications`
WHERE publication_number = @pub_number
LIMIT 1
"""
job_config = bigquery.QueryJobConfig(
    query_parameters=[bigquery.ScalarQueryParameter("pub_number", "STRING", "US-12551228-B2")]
)

result = list(client.query(query, job_config=job_config).result())
claims_text = result[0].claims_text

print("First 500 characters of the real claims text:")
print("=" * 60)
print(claims_text[:500])
print("=" * 60)

print(f"\nTotal length: {len(claims_text)} characters")

claims = split_claims(claims_text)
print(f"Parsed: {len(claims)} claims")
