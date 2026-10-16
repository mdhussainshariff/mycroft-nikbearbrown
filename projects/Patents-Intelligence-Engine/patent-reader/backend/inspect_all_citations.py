"""
inspect_all_citations.py — prints every raw citation entry for
US-10822628-B2 (already cached, free) so we can honestly verify
whether the 1 patent / 11 NPL split is correct.
"""
from google.cloud import bigquery

client = bigquery.Client(project="patent-intelligence-system")

query = """
SELECT publication_number, citation
FROM `patents-public-data.patents.publications`
WHERE publication_number = @pub_number
LIMIT 1
"""
job_config = bigquery.QueryJobConfig(
    query_parameters=[bigquery.ScalarQueryParameter("pub_number", "STRING", "US-10822628-B2")]
)

result = list(client.query(query, job_config=job_config).result())
row = result[0]

for i, c in enumerate(row.citation):
    print(f"Citation {i}: {dict(c)}")
