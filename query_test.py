import os
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

load_dotenv()

model = SentenceTransformer("all-MiniLM-L6-v2")
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("job-ads")

question = "Which roles require experience with forward deployed engineering or customer-facing AI implementation?"

query_vector = model.encode(question).tolist()

results = index.query(vector=query_vector, top_k=3, include_metadata=True)

print(f"Question: {question}\n")
for match in results["matches"]:
    print(f"Score: {match['score']:.3f} | Source: {match['metadata']['source']}")
    print(f"Snippet: {match['metadata']['text'][:200]}...\n")
