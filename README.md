# Job-Ad RAG

A Retrieval-Augmented Generation (RAG) pipeline for answering questions about a personal collection of saved job postings. The system is deployed as a publicly accessible HTTP API on AWS.

The project covers local embeddings, vector search, LLM-based answer generation, Docker, AWS Lambda, API Gateway, and the deployment issues encountered along the way.

**Live endpoint:**
```text
POST https://h42cyu93qj.execute-api.us-east-1.amazonaws.com
Content-Type: application/json

{"question": "your question here"}
```

Example request:

```bash
curl -X POST https://h42cyu93qj.execute-api.us-east-1.amazonaws.com \
  -H "Content-Type: application/json" \
  -d '{"question": "What skills does the AWS job ad require?"}'
```

> The first request after a period of inactivity can take up to ~30 seconds because of the Lambda cold start. Subsequent requests are faster.

---

## What it does

1. Takes a natural-language question.
2. Embeds the question locally using `sentence-transformers`.
3. Searches a Pinecone vector index containing 11 saved job ad excerpts.
4. Sends the question and the retrieved excerpts to Claude.
5. Claude is instructed to answer only from the supplied context and cite the relevant sources.
6. Returns the answer and citations.

---

## Architecture

```text
Client → API Gateway (HTTP API) → Lambda (container image)
                                        ├─► Pinecone (vector search)
                                        └─► Anthropic API (Claude)
```

| Layer | Choice | Reason |
|---|---|---|
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`), local | Free and sufficient for the short documents used here |
| Vector store | Pinecone (serverless) | Managed service with a free tier |
| Generation | Anthropic API (Claude) | Generates answers from the retrieved context |
| Orchestration | Raw Python, no framework | The pipeline is small enough to implement directly |
| Compute | AWS Lambda, container image | `sentence-transformers` includes PyTorch, which is too large for a standard Lambda zip deployment |
| API | AWS API Gateway (HTTP API, v2) | Suitable for a single-route API |

---

## Project structure

```text
.
├── rag_chain.py             # Core RAG logic: retrieve() + ask()
├── lambda_handler.py        # Lambda entrypoint, wraps rag_chain.ask()
├── embed_and_store.py       # Embeds job_ads/*.txt and stores them in Pinecone
├── query_test.py            # Retrieval-only test, no LLM call
├── test_claude.py           # Raw API smoke test
├── job-ads-query.html       # Minimal frontend for the live endpoint
├── Dockerfile               # Lambda container image
├── requirements.txt         # Pinned dependencies
├── job_ads/                 # Source job postings (.txt)
└── .env                     # API keys, gitignored
```

---

## Running locally

Create a virtual environment and install the dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:

```text
ANTHROPIC_API_KEY=your-key
PINECONE_API_KEY=your-key
```

Embed and store the job ads:

```bash
python3 embed_and_store.py
```

Run the question-answering pipeline directly:

```bash
python3 rag_chain.py
```

The embedding step needs to be repeated when the contents of `job_ads/` change.

---

## Deploying to AWS

The deployment uses a Docker image stored in Amazon ECR, AWS Lambda for compute, and API Gateway for the HTTP endpoint.

Build the image for Lambda's x86_64 architecture:

```bash
docker build \
  --platform linux/amd64 \
  --provenance=false \
  --sbom=false \
  -t rag-lambda .
```

Push the image to ECR:

```bash
docker tag rag-lambda:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/rag-lambda:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/rag-lambda:latest
```

Create the Lambda function:

```bash
aws lambda create-function \
  --function-name rag-job-ads \
  --package-type Image \
  --code ImageUri=<account-id>.dkr.ecr.us-east-1.amazonaws.com/rag-lambda:latest \
  --role arn:aws:iam::<account-id>:role/rag-lambda-execution-role \
  --timeout 60 \
  --memory-size 3008
```

Create the HTTP API:

```bash
aws apigatewayv2 create-api \
  --name rag-job-ads-api \
  --protocol-type HTTP \
  --target arn:aws:lambda:us-east-1:<account-id>:function:rag-job-ads
```

### Required Lambda environment variables

```text
ANTHROPIC_API_KEY
PINECONE_API_KEY
HF_HOME=/opt/hf_cache
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

---

## Deployment issues

The following issues were encountered while moving the local Python pipeline to Lambda.

1. **Platform mismatch**

   The Docker image was initially built on Apple Silicon (`arm64`), while the Lambda environment used `x86_64`.

   Fixed with:

   ```bash
   --platform linux/amd64
   ```

2. **Docker image metadata**

   Newer versions of Docker Desktop attach provenance and SBOM metadata that Lambda's image parser rejected.

   Fixed with:

   ```bash
   --provenance=false --sbom=false
   ```

3. **Lambda initialization time**

   Loading PyTorch and the embedding model during module initialization exceeded the available initialization time.

   Increasing the Lambda memory to 3008 MB also increased the available CPU and reduced initialization time.

4. **Read-only filesystem**

   Lambda's filesystem is read-only outside `/tmp`. The default `sentence-transformers` cache location therefore could not be used.

   `HF_HOME` was first pointed to `/tmp`, then moved to `/opt/hf_cache` so the model cache could be included in the container image.

5. **Offline model loading**

   Enabling `HF_HUB_OFFLINE` before the model was available in the image caused the model loading step to fail.

   The model weights were instead downloaded during the Docker build and included in the image before enabling offline mode.

6. **API Gateway 403**

   Direct Lambda invocations worked, but requests through API Gateway returned 403 responses without corresponding Lambda logs.

   The Lambda resource policy used the REST API v1 `*/*/*` source ARN pattern instead of the HTTP API v2 `*/*` pattern.

   API Gateway access logging was enabled to identify the source of the 403.

7. **CORS with a `$default` route**

   The API-level `CorsConfiguration` did not handle preflight requests because the `$default` route forwarded `OPTIONS` requests directly to Lambda.

   CORS handling was therefore added explicitly to `lambda_handler.py`.

---

## Known limitations

- **Cold starts:** Requests after periods of inactivity can take approximately 10 to 30 seconds because the Lambda container loads PyTorch and the embedding model.
- **Lambda memory:** The function currently uses 3008 MB. Higher memory requires a service quota increase on this AWS account.
- **API Gateway timeout:** HTTP APIs have a 30-second integration timeout. Provisioned Concurrency would be one option if cold starts became long enough to approach this limit.
- **Retrieval quality:** The system uses a small local embedding model and a relatively small document collection. Retrieval quality is therefore limited compared with larger embedding models and larger-scale retrieval systems.

---

## Frontend

`job-ads-query.html` is a small HTML and JavaScript frontend for the live API. It contains a text input, a submit button, and an area for displaying the response.

There is no build step or frontend dependency.

The page should be served from a local HTTP origin rather than opened directly as a `file://` URL. Some browsers handle CORS differently for local files.

```bash
python3 -m http.server 8000
```

Then open:

```text
http://localhost:8000/job-ads-query.html
```