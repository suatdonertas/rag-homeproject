# Job-Ad RAG

A Retrieval-Augmented Generation (RAG) pipeline that answers natural-language
questions about a personal collection of saved job postings — deployed as a
live, publicly callable HTTP API on AWS.

Built as a hands-on, end-to-end learning project covering the full stack:
local embeddings, vector search, LLM generation, containerized serverless
deployment, and the real debugging that comes with it.

**Live endpoint:**
```
POST https://h42cyu93qj.execute-api.us-east-1.amazonaws.com
Content-Type: application/json

{"question": "your question here"}
```

```bash
curl -X POST https://h42cyu93qj.execute-api.us-east-1.amazonaws.com \
  -H "Content-Type: application/json" \
  -d '{"question": "What skills does the AWS job ad require?"}'
```

> First request after idle time can take up to ~30 seconds (cold start).
> Subsequent requests are much faster.

---

## What it does

1. Takes a natural-language question
2. Embeds it locally using `sentence-transformers`
3. Searches a Pinecone vector index of 11 saved job ad excerpts for the most
   relevant matches
4. Sends the question + matched excerpts to Claude, instructed to answer
   **only** from the provided context and cite its sources
5. Returns a grounded, cited answer

---

## Architecture

```
Client → API Gateway (HTTP API) → Lambda (container image)
                                        ├─► Pinecone (vector search)
                                        └─► Anthropic API (Claude)
```

| Layer | Choice | Why |
|---|---|---|
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`), local | Free, no extra signup, sufficient for short documents |
| Vector store | Pinecone (serverless) | Managed, free tier, zero infra |
| Generation | Anthropic API (Claude) | Grounded answer generation |
| Orchestration | Raw Python, no framework | Small scale — writing the chain by hand teaches the mechanism directly |
| Compute | AWS Lambda, container image | `sentence-transformers` pulls in PyTorch, too large for a zip deployment (250MB limit); container images support up to 10GB |
| API | AWS API Gateway (HTTP API, v2) | Simpler/cheaper than REST API for a single-route proxy |

---

## Project structure

```
.
├── rag_chain.py            # Core RAG logic: retrieve() + ask()
├── lambda_handler.py        # Lambda entrypoint, wraps rag_chain.ask()
├── embed_and_store.py       # One-time script: embeds job_ads/*.txt → Pinecone
├── query_test.py            # Retrieval-only test (no LLM call)
├── test_claude.py           # Original raw API smoke test
├── job-ads-query.html       # Minimal frontend, calls the live endpoint
├── Dockerfile                # Builds the Lambda container image
├── requirements.txt          # Pinned dependencies
├── job_ads/                  # Source job postings (.txt)
└── .env                       # API keys (gitignored, not in repo)
```

---

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:
```
ANTHROPIC_API_KEY=your-key
PINECONE_API_KEY=your-key
```

Embed and store the job ads (one-time, or whenever `job_ads/` changes):
```bash
python3 embed_and_store.py
```

Ask a question directly:
```bash
python3 rag_chain.py
```

---

## Deploying to AWS

The short version — see the full build log below for the real debugging.

```bash
# Build for Lambda's architecture, disable metadata Lambda can't parse
docker build --platform linux/amd64 --provenance=false --sbom=false -t rag-lambda .

# Push to ECR
docker tag rag-lambda:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/rag-lambda:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/rag-lambda:latest

# Create the function
aws lambda create-function \
  --function-name rag-job-ads \
  --package-type Image \
  --code ImageUri=<account-id>.dkr.ecr.us-east-1.amazonaws.com/rag-lambda:latest \
  --role arn:aws:iam::<account-id>:role/rag-lambda-execution-role \
  --timeout 60 \
  --memory-size 3008

# Front it with an HTTP API
aws apigatewayv2 create-api \
  --name rag-job-ads-api \
  --protocol-type HTTP \
  --target arn:aws:lambda:us-east-1:<account-id>:function:rag-job-ads
```

### Required Lambda environment variables

```
ANTHROPIC_API_KEY
PINECONE_API_KEY
HF_HOME=/opt/hf_cache
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

---

## What made this non-trivial (real bugs hit and fixed)

Deploying a local Python ML script to Lambda is not just "zip it up" once
PyTorch is involved. In order encountered:

1. **Platform mismatch** — building on Apple Silicon (arm64) produces an
   image Lambda (x86_64) can't run. Fixed with `--platform linux/amd64`.
2. **Docker manifest format** — newer Docker Desktop attaches
   provenance/SBOM metadata Lambda's image parser rejects. Fixed with
   `--provenance=false --sbom=false`.
3. **Lambda's hidden 10-second init cap** — a hard ceiling on module-level
   initialization (loading PyTorch + the embedding model), separate from
   the function's configured timeout. Fixed by raising memory (which
   scales CPU) to 3008MB.
4. **Read-only filesystem** — Lambda's filesystem is read-only outside
   `/tmp`; `sentence-transformers`' default cache path isn't writable.
   Fixed by pointing `HF_HOME` at `/tmp` initially, then at a path baked
   into the image (`/opt/hf_cache`) as the permanent fix.
5. **Offline mode with no cache** — enabling `HF_HUB_OFFLINE` before the
   model was actually cached anywhere durable caused a different failure.
   Fixed by baking the model weights into the Docker image at build time,
   *then* enabling offline mode.
6. **API Gateway 403, not a timeout** — direct Lambda invokes worked, but
   calls through API Gateway failed with no Lambda logs at all. Root
   cause: the Lambda resource policy's `--source-arn` used the wrong
   wildcard pattern for HTTP API (v2) — `*/*/*` (REST API v1 format)
   instead of `*/*` (HTTP API v2 format). API Gateway access logging
   (off by default) was needed to actually see this 403 in the first
   place.
7. **CORS on a `$default` route** — the API-level `CorsConfiguration`
   didn't apply because the catch-all `$default` route proxies `OPTIONS`
   preflight requests straight to Lambda instead of letting API Gateway
   handle them. Fixed by handling `OPTIONS` and CORS headers explicitly
   inside `lambda_handler.py`.

---

## Known limitations

- **Cold starts are slow** (~10–30s) after idle periods — inherent to
  running a heavy ML dependency (PyTorch) in a serverless container. Warm
  requests are much faster.
- **Lambda memory capped at 3008MB** on this AWS account by default (higher
  requires a service quota increase).
- **API Gateway's 30-second integration timeout** is a hard, non-configurable
  ceiling for HTTP APIs — the real fix if cold starts ever exceeded it would
  be Provisioned Concurrency (small continuous cost to keep an instance warm).
- **Retrieval quality is moderate**, using a small local embedding model over
  Voyage AI's paid offering — an intentional cost tradeoff, acceptable at
  this document count.

---

## Frontend

`job-ads-query.html` is a minimal, self-contained HTML+JS page that queries
the live endpoint directly via `fetch()` — a text box, a submit button, and
the answer rendered below. No build step, no dependencies.

It needs to be served from a real local origin rather than opened directly as
a `file://` page, since some browsers handle CORS unpredictably for `file://`
origins regardless of server-side configuration:

```bash
python3 -m http.server 8000
# then open http://localhost:8000/job-ads-query.html
```
