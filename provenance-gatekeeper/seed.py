import chromadb
from sentence_transformers import SentenceTransformer

print("Loading model...")
model = SentenceTransformer('all-MiniLM-L6-v2')
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="financial_ledger")

# The ground truth fact we want the Gatekeeper to know
truth_text = "The company revenue grew to exactly 5000000 this quarter."
print("Encoding truth data...")
embedding = model.encode(truth_text).tolist()

collection.add(
    documents=[truth_text],
    embeddings=[embedding],
    ids=["fact_001"]
)

print("Ground truth successfully added to ChromaDB!")