# Company Brain

An internal knowledge base that lets anyone ask a question in plain English and get a grounded, cited answer from their company's own documents.

Upload PDFs, text files, or markdown. Ask questions. Get answers with source citations — or an honest "I don't know" when the documents don't contain the answer.

## How It Works

1. **Upload** a document to a company-scoped collection
2. Documents are chunked, embedded, and stored in a Chroma vector database
3. **Query** in plain English — the system retrieves relevant chunks and scores them
4. If the top chunk scores above the confidence threshold (0.75), the LLM generates a grounded answer with citations
5. If confidence is low, the system **declines** honestly — no hallucination, no LLM call

## Stack

- **Backend:** FastAPI + LangChain + OpenAI GPT-4o
- **Vector Store:** ChromaDB (local, persistent)
- **Frontend:** Single-page HTML/JS app
- **Embeddings:** OpenAI Embeddings
- **Chunking:** RecursiveCharacterTextSplitter (500 tokens, 50 overlap)

## Setup

```bash
# Clone
git clone https://github.com/ChrisB2024/company-brain.git
cd company-brain

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your OpenAI API key

# Run
uvicorn src.main:app --reload
```

Open `http://localhost:8000` in your browser.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/upload` | POST | Upload and ingest a document (multipart form: `file` + `company`) |
| `/query` | POST | Query the knowledge base (JSON: `question` + `company`) |

## Project Structure

```
src/
  config.py       # Environment-driven settings (pydantic-settings)
  models.py       # Pydantic request/response schemas
  ingest.py       # Document loading, chunking, embedding, storage
  retrieval.py    # Confidence gate + RAG chain
  main.py         # FastAPI app and endpoints
frontend/
  index.html      # Single-page frontend
tests/            # Test suite (config, models, ingest, retrieval, main, frontend)
.spec/            # System Thinking Spec — the architectural blueprint
.agent/           # Agent execution logs and handoff state
workflow1/        # DADP protocol definition
```

## Key Design Decisions

- **Confidence gate** — queries with low relevance scores never hit the LLM. This prevents hallucination and saves API costs.
- **Collection isolation** — each company's documents are stored in a separate Chroma collection. No cross-tenant data access.
- **API key as SecretStr** — never serialized to logs or responses.
- **Temp file cleanup** — uploaded files are deleted from `/tmp` after ingestion regardless of success or failure.

---

## Built with DADP (Dual-Agent Development Protocol)

This project was built using **DADP** — a development workflow where two AI agents collaborate asynchronously through structured, file-based communication, with a human architect reviewing and steering.

### The Agents

- **Claude (Builder)** — reads the spec, writes production code, and documents every decision with technical rationale and plain-language explanations in `claude_log.md`
- **Codex (Validator)** — reads Claude's code and reasoning, then writes three categories of tests (correctness, spec compliance, adversarial) and logs findings in `codex_log.md`

### The Loop

```
Human writes System Thinking Spec
        |
        v
Claude reads spec --> writes code + claude_log.md
        |
        v
Human reviews claude_log.md (learning loop)
        |
        v
Codex reads code + claude_log.md --> writes tests + codex_log.md
        |
        v
Claude reads codex_log.md --> addresses failures --> continues building
        |
        v
Repeat until phase complete
```

### What Makes DADP Different

1. **Separation of concerns** — the builder never writes tests, the validator never writes production code. This prevents the "testing your own homework" problem.
2. **File-based handoff** — agents communicate through `handoff.json`, `claude_log.md`, and `codex_log.md`. No shared memory, no chat history. Every decision is auditable.
3. **Human as architect** — the human doesn't just approve PRs. They write the spec (System Thinking), review agent reasoning logs as a learning mechanism, and steer direction when the spec needs to evolve.
4. **Spec-driven development** — everything traces back to the System Thinking Spec, which defines invariants, threat models, state machines, and causality chains *before* any code is written.
5. **Append-only logs** — agent logs are never overwritten. The full decision history is preserved for traceability.

### How It Played Out on This Project

The project was built over 5 sessions:

| Session | What Happened |
|---------|---------------|
| 1 | Claude scaffolded `config.py` and `models.py`. Codex validated and caught a committed API key in `.env.example` (`[BLOCKER B-001]`). |
| 2 | Claude fixed B-001, built `ingest.py`. Codex validated and found oversized uploads bypassed temp cleanup (`[BLOCKER B-002]`). |
| 3 | Claude fixed B-002, built `retrieval.py` with the confidence gate. Codex validated correctness and adversarial cases. |
| 4 | Claude built `main.py` (FastAPI endpoints). Codex validated the full API surface. |
| 5 | Claude built the frontend. Codex validated frontend integration. All modules passed. |

The full agent logs are in [.agent/claude_log.md](.agent/claude_log.md) and [.agent/codex_log.md](.agent/codex_log.md). The protocol definition is in [workflow1/PROTOCOL.md](workflow1/PROTOCOL.md).

---

## License

MIT
