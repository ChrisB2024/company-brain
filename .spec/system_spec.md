# System Thinking Spec — Company Brain

> **Version:** 1.0
> **Date:** 2026-03-22
> **Author:** Chris
> **Status:** Draft

---

## Phase 0 — Problem Thinking

### Who Hurts and Why

**The Person:**
A SaaS founder or ops lead at a 5–50 person company. They have internal knowledge scattered across Notion, Google Drive, PDFs, and Slack threads. New hires take weeks to get up to speed. The same questions get answered over and over.

**The Pain:**
There is no single place to ask a question and get a grounded, sourced answer. People either interrupt a senior teammate, search manually through docs and give up, or make decisions based on incomplete information.

**The Ugly Workaround:**
They pin docs in Slack, maintain a wiki nobody keeps updated, or designate a person as the "institutional memory" — which doesn't scale and creates a single point of failure.

**The Sentence Test:**
> "Ops leads currently interrupt senior teammates or search manually through stale wikis because their internal knowledge is fragmented across tools, and Company Brain eliminates this by letting anyone ask a question in plain English and get a grounded, cited answer from the company's own documents."

---

### Product Invariants

1. The user must never receive an answer that isn't grounded in an uploaded document
2. Every answer must always include a source citation with the document name and location
3. The system must never fabricate information — if confidence is low, it must say so explicitly
4. When a document doesn't contain the answer, the system must return an honest "I don't know" rather than hallucinate
5. The system must be honest about confidence level on every response

---

### Security Invariants

1. User documents must never be accessible across company collections — strict collection-level isolation
2. No endpoint should return chunks or raw document content outside of an answer context
3. API keys must never be hardcoded — always loaded from environment variables
4. If the vector store is compromised, blast radius is limited to that company's collection only — no cross-tenant exposure
5. On deletion, all vectors and source metadata for that collection must be purged from Chroma

---

### Technical Invariants

1. Every query must run the confidence gate before hitting the LLM — no LLM call on low-relevance retrieval
2. API responses must always return `answer`, `sources`, and `confidence` — never a partial shape
3. No state transition from ingestion to queryable should occur without chunk count confirmation

---

### Product Causality Chains

| Change | Technical Impact | UX Impact | Business Impact | Security Impact |
|--------|-----------------|-----------|-----------------|-----------------|
| Lower confidence threshold (0.75 → 0.5) | More chunks pass the gate | More answers returned, some may be wrong | Higher perceived utility short-term, trust erosion long-term | Increases hallucination surface |
| Increase chunk size (500 → 1000) | Fewer, broader chunks stored | Answers more complete but less precise citations | Better for narrative docs, worse for structured FAQs | Larger context window = higher token cost |
| Add multi-tenant auth | JWT validation layer added | No UX change | Unlocks paid per-company plans | Reduces blast radius on breach |
| Switch vector DB from Chroma to Pinecone | Remote DB, network latency added | Slightly slower queries | Enables cloud deploy, scales beyond local | Adds external dependency to threat model |

---

### Threat Model

| Data Touched | Who Should Access It | Blast Radius if Compromised | Regulatory Requirements |
|-------------|---------------------|-----------------------------|------------------------|
| Uploaded documents (PDFs, text) | Only the uploading company | Exposure of that company's internal docs | GDPR if EU clients — right to deletion must work |
| Chroma vector embeddings | Backend only — never exposed via API | Embeddings alone are not reversible to raw text, low risk | None currently |
| OpenAI API key | Backend config only | Full API access under that key, billing exposure | Store in env var, rotate on breach |
| Query logs (question + answer) | System only — no logging by default | Could reveal internal company questions | Log opt-in only — don't log by default |

---

## Phase 1 — System Model

### State Machine

Document lifecycle:

```
[UPLOADED] --ingest()--> [CHUNKED] --embed()--> [STORED] --query()--> [ANSWERED]
                                                               |
                                                     confidence < 0.75
                                                               |
                                                          [DECLINED]
```

**States:**
- `UPLOADED`: File received by FastAPI, written to `/tmp`
- `CHUNKED`: Document split into 500-token chunks with 50-token overlap
- `STORED`: Chunks embedded and persisted in Chroma under `collection_name`
- `ANSWERED`: LLM returned a grounded response with sources
- `DECLINED`: Confidence gate rejected the retrieval — honest "I don't know" returned

**Transitions:**
- `UPLOADED → CHUNKED`: triggered by `ingest_document()`, requires valid file path and supported file type
- `CHUNKED → STORED`: triggered by `Chroma.from_documents()`, requires valid OpenAI API key
- `STORED → ANSWERED`: triggered by `query_brain()`, requires similarity score ≥ 0.75 on top chunk
- `STORED → DECLINED`: triggered by `query_brain()`, when similarity score < 0.75

**Invalid transitions:**
- `DECLINED → ANSWERED` must never happen in the same request — once the confidence gate fires, the LLM is not called

---

### Trust Boundaries

| Boundary | From (Trust Level) | To (Trust Level) | Validation Required |
|----------|--------------------|------------------|---------------------|
| Client → `/upload` | Untrusted | Trusted | File type check, size limit, company param sanitized |
| Client → `/query` | Untrusted | Trusted | Question length limit, company param sanitized |
| FastAPI → Chroma | Trusted | Trusted | Collection name scoped per company, no cross-collection reads |
| FastAPI → OpenAI API | Trusted | Semi-trusted | API key from env only, response validated before returning |
| FastAPI → `/tmp` | Trusted | Trusted | Temp file deleted after ingestion |

---

### Data Flow

```
[User uploads PDF]
        ↓
[FastAPI /upload] → [PyPDFLoader] → [RecursiveCharacterTextSplitter]
        ↓
[OpenAIEmbeddings] → [Chroma vectorstore] (persisted by collection)
        ↓
[User sends query]
        ↓
[FastAPI /query] → [similarity_search_with_relevance_scores]
        ↓
   score < 0.75?
   YES → return DECLINED response (no LLM call)
   NO  → [RetrievalQA chain] → [ChatOpenAI gpt-4o]
        ↓
[QueryResponse: answer + sources + confidence]
        ↓
[Frontend renders answer with citation tags]
```

---

## Phase 2 — Decomposition

### Module Breakdown

#### Module: `ingest.py`
- **Purpose:** Loads, chunks, embeds, and stores documents into the vector DB
- **Inputs:** File path (str), collection name (str)
- **Outputs:** Chunk count (int)
- **Invariants:** Must always persist to `settings.chroma_persist_dir` — never in-memory only
- **Security surface:** File path traversal if `file_path` is user-controlled — sanitize before passing
- **Failure modes:**
  - Unsupported file type → raise `ValueError` with clear message, don't silently skip
  - OpenAI embedding API down → exception propagates to FastAPI, returns 502
  - Chroma write failure → exception propagates, file cleaned up in finally block
  - File too large → chunk count explodes, add size guard before loading
- **What the user sees on failure:** "Ingestion failed — please check your file format and try again"

#### Module: `retrieval.py`
- **Purpose:** Runs the confidence gate and RAG chain to produce a grounded answer
- **Inputs:** Question (str), collection name (str)
- **Outputs:** Dict with `answer`, `sources`, `confidence`
- **Invariants:** LLM must never be called if confidence gate fails; system prompt must always be injected
- **Security surface:** Prompt injection via malicious document content — system prompt must be rigid
- **Failure modes:**
  - Collection doesn't exist → Chroma raises exception, return 404 with "Collection not found"
  - OpenAI API timeout → wrap in try/except, return 503 with retry suggestion
  - Confidence gate fires → return DECLINED shape, never call LLM
  - LLM ignores system prompt and hallucinates → system prompt hardened with explicit constraints
- **What the user sees on failure:** "I couldn't find a confident answer in the provided documents"

#### Module: `main.py`
- **Purpose:** FastAPI app — exposes `/upload`, `/query`, `/health` endpoints
- **Inputs:** HTTP requests
- **Outputs:** JSON responses typed by Pydantic models
- **Invariants:** All blocking I/O must be wrapped in `run_in_threadpool`; CORS must be configured
- **Security surface:** Unvalidated `company` param could be used to access other collections — sanitize to alphanumeric
- **Failure modes:**
  - Invalid file type uploaded → return 422 with descriptive error
  - `company` param missing → default to `"default"` collection
  - Ingest or query raises → FastAPI exception handler returns structured error
- **What the user sees on failure:** HTTP error with JSON `{"detail": "..."}` — never a raw traceback

#### Module: `config.py`
- **Purpose:** Single source of truth for all environment-driven configuration
- **Inputs:** `.env` file via `pydantic-settings`
- **Outputs:** `Settings` singleton via `get_settings()`
- **Invariants:** `openai_api_key` must always be present — app must fail fast on startup if missing
- **Security surface:** `.env` file must never be committed — add to `.gitignore`
- **Failure modes:**
  - Missing required env var → `ValidationError` on startup, clear message naming the missing field
- **What the user sees on failure:** Server fails to start with config error in logs

#### Module: `models.py`
- **Purpose:** Pydantic request/response schemas — enforces API contract
- **Inputs:** Raw dicts from FastAPI or retrieval layer
- **Outputs:** Validated, serialized JSON
- **Invariants:** `QueryResponse` must always include `confidence` field — never omit
- **Security surface:** None directly — models are internal validation only
- **Failure modes:**
  - Missing field in response dict → Pydantic raises `ValidationError`, caught by FastAPI → 422
- **What the user sees on failure:** 422 Unprocessable Entity with field-level error detail

---

### Module Communication

| Module A | Module B | Communication Pattern | Coupling Level | Contract |
|----------|-----------|-----------------------|----------------|----------|
| `main.py` | `ingest.py` | sync call via `run_in_threadpool` | low | returns `int` (chunk count) |
| `main.py` | `retrieval.py` | sync call via `run_in_threadpool` | low | returns `dict` with `answer`, `sources`, `confidence` |
| `ingest.py` | `config.py` | import `get_settings()` | low | reads `chunk_size`, `chunk_overlap`, `chroma_persist_dir` |
| `retrieval.py` | `config.py` | import `get_settings()` | low | reads `model_name`, `temperature`, `retrieval_k`, `confidence_threshold` |
| `main.py` | `models.py` | Pydantic response typing | low | `response_model=QueryResponse` enforced by FastAPI |

---

### Evolution Check

| Module | Likely Future Change | Current Architecture Supports It? | Risk |
|--------|---------------------|-----------------------------------|------|
| `ingest.py` | Add hybrid search (keyword + vector) | Partially — Chroma supports it but requires retriever swap | Low |
| `ingest.py` | Support Notion/Google Docs URLs | Yes — add new loader, same chunking pipeline | Low |
| `retrieval.py` | Add re-ranking (top 10 → best 3) | Yes — insert reranker between retrieval and LLM call | Low |
| `retrieval.py` | Stream response tokens to frontend | No — current chain returns full string; needs streaming refactor | Medium |
| `main.py` | Add per-company auth (JWT) | Yes — add FastAPI dependency injection layer | Low |
| `config.py` | Switch from OpenAI to Anthropic | Yes — swap `openai_api_key` for `anthropic_api_key`, update model name | Low |

---

## Phase 3 — Implementation Plan

### Build Order

| Order | Module | Depends On | Estimated Sessions |
|-------|--------|------------|--------------------|
| 1 | `config.py` | — | 0.5 |
| 2 | `models.py` | — | 0.5 |
| 3 | `ingest.py` | `config.py` | 1 |
| 4 | `retrieval.py` | `config.py`, `models.py` | 1.5 |
| 5 | `main.py` | All above | 1 |
| 6 | `frontend/index.html` | `main.py` running | 1.5 |
| 7 | Deploy (Railway/Render) | All above | 1 |

---

### Per-Module Security Checklist

| Module | Handles Sensitive Data? | Auth Required? | Input Validation Plan | What If Attacker Controls Input? | What If Storage Breached? |
|--------|------------------------|----------------|----------------------|----------------------------------|--------------------------|
| `ingest.py` | Yes — raw documents | No (v1) | File type whitelist, size cap | Path traversal via filename — sanitize with `os.basename()` | Documents exposed — scope to collection only |
| `retrieval.py` | Yes — document chunks + queries | No (v1) | Question length cap (500 chars) | Prompt injection via doc content — rigid system prompt | Embeddings exposed — not reversible to raw text |
| `main.py` | No directly | No (v1) | `company` param alphanumeric only | Collection hopping via `company` param — sanitize strictly | No sensitive data held in app layer |
| `config.py` | Yes — API keys | N/A | Pydantic validates on startup | N/A | Key rotation required — never log key values |

---

## Phase 4 — Validation Plan

### Technical Validation
- [ ] Upload a PDF and confirm chunk count returned is > 0
- [ ] Query against uploaded doc and confirm answer references correct source
- [ ] Query with a question not in any doc and confirm DECLINED response returned
- [ ] Query against empty collection and confirm 404 or DECLINED — never a hallucination
- [ ] Send malformed request (missing `question`) and confirm 422 returned

### Security Validation
- [ ] Confirm `OPENAI_API_KEY` not present in any committed file
- [ ] Confirm `company` param with `../` or special characters is rejected or sanitized
- [ ] Confirm querying collection A with collection B's name returns no results
- [ ] Confirm `/health` endpoint does not expose API keys or file paths
- [ ] Confirm `.env` is in `.gitignore` before first push

### Product Validation
- [ ] Load 3 real-looking company docs (onboarding, FAQ, refund policy)
- [ ] Run the 5 demo questions — all return cited answers
- [ ] Ask 2 questions not in any doc — both return honest DECLINED response
- [ ] Record Loom demo — upload → query → citation visible in under 90 seconds
- [ ] Send live demo link to 1 real person and observe where they get confused

---

## Appendix A: Lifecycle Maps

### Entity: Document Collection

```
Uploaded → Chunked → Embedded → Queryable → Deleted
                                                ↑
                              Chroma collection purged
                              All vectors removed
                              /tmp source file already deleted post-ingest
```

### Entity: Query Request

```
Received → Validated → Retrieved → Gate Check → Answered
                                        ↑
                                   score < 0.75
                                        ↓
                                    Declined
                                   (no LLM call)
```

---

## Appendix B: Decision Log

| Decision | Options Considered | Chosen | Tradeoff | Reversible? |
|----------|--------------------|--------|----------|-------------|
| Vector DB | Pinecone, Weaviate, Chroma | Chroma (local) | No network latency, no cost, but doesn't scale beyond single machine | Yes — swap in `retrieval.py` and `ingest.py` |
| LLM provider | Anthropic Claude, OpenAI GPT-4o | OpenAI GPT-4o | Wider LangChain support, slightly cheaper at demo scale | Yes — config change + swap `ChatOpenAI` for `ChatAnthropic` |
| Chunking strategy | Fixed size, semantic, recursive | RecursiveCharacterTextSplitter | Good default for mixed doc types, easy to tune | Yes — swap splitter in `ingest.py` |
| Confidence threshold | 0.5, 0.65, 0.75, 0.9 | 0.75 | Balances recall vs hallucination risk — tunable per client via config | Yes — env var |
| Auth in v1 | JWT, API key, none | None | Faster to ship, good enough for demo; adds attack surface if skipped too long | Yes — FastAPI dependency injection |
| Retrieval k | 2, 4, 8 | 4 | Enough context for most questions without bloating the prompt | Yes — env var |