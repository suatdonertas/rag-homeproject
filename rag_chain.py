import os
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from anthropic import Anthropic

load_dotenv()

# --- Setup ---
embed_model = SentenceTransformer("all-MiniLM-L6-v2")
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("job-ads")
claude = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def retrieve(question, top_k=3):
    query_vector = embed_model.encode(question).tolist()
    results = index.query(vector=query_vector, top_k=top_k, include_metadata=True)
    return results["matches"]


def ask(question):
    matches = retrieve(question)

    # Build context block from retrieved job ads
    context = "\n\n---\n\n".join(
        f"Source: {m['metadata']['source']}\n{m['metadata']['text']}"
        for m in matches
    )

    prompt = f"""You are analyzing a set of job ad excerpts. Answer the question using ONLY the information in these excerpts. Cite which source(s) support your answer.

Job ad excerpts:
{context}

Question: {question}"""

    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text


if __name__ == "__main__":
    question = "Which roles require experience with forward deployed engineering or customer-facing AI implementation?"
    answer = ask(question)
    print(f"Question: {question}\n")
    print(f"Answer:\n{answer}")
