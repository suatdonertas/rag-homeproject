# Serverless Document Intelligence RAG

An end-to-end Retrieval-Augmented Generation (RAG) system for querying custom document collections using natural language. The pipeline leverages local embeddings, vector similarity search, and LLM reasoning, packaged as a containerized serverless API on AWS.

The project covers local embedding pipelines, vector search optimization, Docker containerization, AWS Lambda integration, and production deployment patterns.

---

## What It Does

1. Receives natural language questions via a REST API endpoint.
2. Generates document embeddings locally using `sentence-transformers`.
3. Performs similarity search across a Pinecone vector index.
4. Synthesizes answers strictly using retrieved context via the Anthropic Claude API.
5. Returns grounded answers complete with source citations.

---

## Architecture

```text
Client → API Gateway (HTTP API) → Lambda (Container Image)
                                        ├─► Pinecone (Vector Search)
                                        └─► Anthropic API (Claude)
```

| Layer | Technology | Role |
|---|---|---|
| **Embeddings** | `sentence-transformers` (`all-MiniLM-L6-v2`) | Local execution, zero-cost embedding generation |
| **Vector Store** | Pinecone (Serverless) | Managed index for fast similarity lookup |
| **Generation** | Anthropic API (Claude) | Contextual answer generation with source grounding |
| **Orchestration** | Python (Native) | Lightweight, framework-free pipeline orchestration |
| **Compute** | AWS Lambda (Docker Image) | Serverless execution accommodating PyTorch dependencies |
| **API** | AWS API Gateway (HTTP API v2) | Single-route HTTP entry point |

---

## Project Structure

```text
.
├── rag_chain.py             # Core RAG logic: retrieve() + ask()
├── lambda_handler.py        # Lambda entrypoint & API response wrapper
├── embed_and_store.py       # Embeds local documents and populates Pinecone
├── query_test.py            # Retrieval-only evaluation script
├── test_claude.py           # LLM API smoke test
├── job-ads-query.html       # Minimal Web Frontend for API interaction
├── Dockerfile               # Lambda container configuration
├── requirements.txt         # Dependency lockfile
├── job_ads/                 # Document source files (.txt)
└── .env                     # Local environment secrets
```

---

## Quick Start (Local Setup)

1. **Environment Setup:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables (`.env`):**
   ```text
   ANTHROPIC_API_KEY=your-key
   PINECONE_API_KEY=your-key
   ```

3. **Index Documents & Run:**
   ```bash
   # Generate and push vector embeddings
   python3 embed_and_store.py

   # Query the pipeline directly
   python3 rag_chain.py
   ```

---

## AWS Deployment Workflow

1. **Build x86_64 Container Image:**
   ```bash
   docker build --platform linux/amd64 --provenance=false --sbom=false -t rag-lambda .
   ```

2. **Push to Amazon ECR:**
   ```bash
   docker tag rag-lambda:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/rag-lambda:latest
   docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/rag-lambda:latest
   ```

3. **Deploy Lambda & API Gateway:**
   ```bash
   aws lambda create-function \
     --function-name rag-doc-query \
     --package-type Image \
     --code ImageUri=<account-id>.dkr.ecr.us-east-1.amazonaws.com/rag-lambda:latest \
     --role arn:aws:iam::<account-id>:role/rag-lambda-execution-role \
     --timeout 60 \
     --memory-size 3008

   aws apigatewayv2 create-api \
     --name rag-doc-api \
     --protocol-type HTTP \
     --target arn:aws:lambda:us-east-1:<account-id>:function:rag-doc-query
   ```

---

## Technical Challenges & Key Learnings

* **Lambda Cold Starts:** Mitigated initialization overhead for PyTorch & embedding models by provisioning 3008 MB RAM to boost CPU allocations.
* **Read-Only File System Workarounds:** Configured `HF_HOME=/opt/hf_cache` to bake HuggingFace models directly into the Docker image, avoiding dynamic runtime writes to read-only paths.
* **Architecture Mismatches:** Built explicit x86_64 Docker binaries to eliminate platform incompatibilities between Apple Silicon development environments and AWS Lambda runtimes.