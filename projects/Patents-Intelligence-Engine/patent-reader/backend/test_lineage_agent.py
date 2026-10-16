"""
test_lineage_agent.py — first real test of LineageAgent, using an
already-cached patent (US-10822628-B2) so this costs nothing new.
Tests the actual field-access pattern for the citation REPEATED
RECORD field, which is genuinely unverified until run against real
output.
"""
from google.cloud import bigquery
from lineage_agent import LineageAgent
import json

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

print("Querying (should be free — cached from earlier)...")
result = list(client.query(query, job_config=job_config).result())
row = result[0]

print(f"\nRaw citation field type: {type(row.citation)}")
print(f"Number of citation entries: {len(row.citation)}")

if row.citation:
    print("\nFirst citation entry, raw repr:")
    print(repr(row.citation[0]))
    print("\nTrying dict-style access on first entry:")
    try:
        print("publication_number:", row.citation[0]["publication_number"])
    except Exception as e:
        print(f"dict-style access failed: {e}")

agent = LineageAgent()

# Convert BigQuery Row/dict-like objects to plain dicts before passing
# to the agent, since Row objects may not support .get() directly.
raw_rows = []
for c in row.citation:
    if hasattr(c, "items"):
        raw_rows.append(dict(c.items()))
    elif hasattr(c, "keys"):
        raw_rows.append(dict(c))
    else:
        raw_rows.append(dict(zip(c.keys(), c.values())) if hasattr(c, "values") else {})

backward = agent.parse_backward_citations(row.publication_number, raw_rows)
print("\n--- LineageAgent result ---")
print(json.dumps(agent.summarize(backward), indent=2))
