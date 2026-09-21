import os
from pathlib import Path
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

# --- Config ---
JOB_ADS_DIR = Path("job_ads")
INDEX_NAME = "job-ads"
EMBED_DIM = 384  # matches all-MiniLM-L6-v2's output size

# --- Load the local embedding model (downloads once, ~80MB, then cached) ---
print("Loading embedding model...")
model = SentenceTransformer("all-MiniLM-L6-v2")

# --- Connect to Pinecone ---
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

# Create the index if it doesn't exist yet
if INDEX_NAME not in [i.name for i in pc.list_indexes()]:
    print(f"Creating Pinecone index '{INDEX_NAME}'...")
    pc.create_index(
        name=INDEX_NAME,
        dimension=EMBED_DIM,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )

index = pc.Index(INDEX_NAME)

# --- Read, embed, and upload each job ad ---
vectors_to_upsert = []

for filepath in JOB_ADS_DIR.glob("*.txt"):
    text = filepath.read_text(encoding="utf-8")
    embedding = model.encode(text).tolist()

    vectors_to_upsert.append({
        "id": filepath.stem,  # e.g. "techwolf_implementation_consultant"
        "values": embedding,
        "metadata": {"source": filepath.name, "text": text[:1000]}  # store a text snippet for reference
    })
    print(f"Embedded: {filepath.name}")

index.upsert(vectors=vectors_to_upsert)
print(f"\nDone. Uploaded {len(vectors_to_upsert)} job ads to Pinecone.")
