# Codex Validation Log

> Append-only log of Validator agent sessions. Never delete or overwrite previous entries.

---

## Session 0 — 2026-03-22 — BOOTSTRAP

### Context
- **Reading from:** N/A
- **Validating:** N/A (project not yet scaffolded with source code)
- **Claude session referenced:** Session 0

### Test Results
No tests to run — project is in bootstrap phase.

### Summary
- **Total:** 0 passed, 0 failed, 0 blockers
- **Modules validated:** None
- **Modules blocked:** None

### Handoff
- **Status:** READY_FOR_BUILD
- **Claude should:** Begin first implementation session after human fills out `.spec/system_spec.md`
- **Blockers:** None

---

## Session 1 — 2026-03-22 — VALIDATION

### Context
- **Reading from:** `.agent/handoff.json`, `.agent/claude_log.md` (Session 1), `.spec/system_spec.md`, `src/config.py`, `src/models.py`, `.env.example`
- **Validating:** `config.py`, `models.py`, and Session 1 security claims
- **Claude session referenced:** Session 1

### Test Results

#### Correctness
- [PASSED] settings_fail_fast_without_api_key: `Settings(_env_file=None)` raises `ValidationError` when `OPENAI_API_KEY` is missing.
- [PASSED] settings_load_defaults_with_only_api_key: `Settings(_env_file=None)` loads the expected defaults when only `OPENAI_API_KEY` is provided.
- [PASSED] secretstr_masks_api_key: `openai_api_key` is wrapped as `SecretStr`, returns the real value only through `.get_secret_value()`, and masks its repr.
- [PASSED] get_settings_singleton_cache: `get_settings()` returns the same cached `Settings` instance across repeated calls.
- [PASSED] query_request_accepts_valid_company_slug: `QueryRequest` accepts alphanumeric, hyphen, and underscore company slugs.
- [PASSED] query_request_rejects_invalid_company_values: `QueryRequest` rejects `../`, spaces, semicolons, and slash-based collection names.
- [PASSED] query_request_enforces_question_length_bounds: `QueryRequest` rejects empty questions and questions longer than 500 characters.
- [PASSED] query_response_requires_confidence_and_sources: `QueryResponse` rejects payloads missing `confidence` or `sources`.
- [PASSED] query_response_enforces_confidence_range: `QueryResponse` rejects confidence values outside `0.0..1.0`.
- [PASSED] source_document_page_optional: `SourceDocument.page` may be omitted and resolves to `None`.
- [PASSED] upload_response_chunk_count_non_negative: `UploadResponse` rejects negative chunk counts.

#### Spec Compliance
- [PASSED] config_fail_fast_invariant: `src/config.py` enforces the required `OPENAI_API_KEY` with no default, matching the startup fail-fast invariant.
- [PASSED] response_shape_invariant: `src/models.py` enforces `answer`, `sources`, and `confidence` on `QueryResponse`, matching the API shape invariant.
- [PASSED] company_sanitization_invariant: `src/models.py` constrains `company` to a strict slug format, reducing collection-name injection risk at the request boundary.
- [FAILED] example_secret_hardcoded: `.env.example` contains a full API-key-shaped value instead of a placeholder.
  - **Expected:** Session 1 claims `.env.example` contains no real secrets, and the spec requires secrets to be externalized rather than hardcoded in repo files.
  - **Actual:** `.env.example:1` includes a complete `sk-proj-...` token-shaped string.
  - **Likely cause:** The example file was populated with a copied key-like value instead of a redacted placeholder during scaffolding.
  - **Fix needed:** Replace the value with a non-secret placeholder such as `your-openai-api-key-here`, then rotate the key immediately if it was ever real.

#### Adversarial
- [PASSED] collection_name_injection_attempts: path traversal and separator-based `company` inputs are rejected at model validation time.
- [PASSED] malformed_response_payloads: incomplete or out-of-range retrieval payloads are rejected before reaching the API response contract.
- [BLOCKER] repository_secret_exposure: a key-like token is committed in `.env.example`, creating avoidable secret-exposure risk if the value is valid.

### Regressions
- None.

### Summary
- **Total:** 13 passed, 1 failed, 1 blocker
- **Modules validated:** `config`, `models`
- **Modules blocked:** Repository security hygiene for `.env.example`

### Handoff
- **Status:** BLOCKED
- **Claude should:** Replace the API-key-like value in `.env.example` with a clear placeholder, confirm no real secrets are tracked, then continue with the next implementation module.
- **Blockers:** `B-001`: `.env.example` contains a committed API-key-shaped value that must be removed or rotated before proceeding.

---

## Session 2 — 2026-03-22 — VALIDATION

### Context
- **Reading from:** `.agent/handoff.json`, `.agent/claude_log.md` (Session 2), `.spec/system_spec.md`, `src/ingest.py`, `.env.example`
- **Validating:** `ingest.py` and Session 2 blocker resolution
- **Claude session referenced:** Session 2

### Test Results

#### Correctness
- [PASSED] get_loader_supported_extensions: `_get_loader()` returns `PyPDFLoader` for `.pdf` and `TextLoader` for `.txt` / `.md`.
- [PASSED] get_loader_rejects_unsupported_extensions: `_get_loader()` raises `ValueError` for unsupported file types such as `.exe`, `.docx`, and `.csv`.
- [PASSED] ingest_missing_file: `ingest_document()` raises `FileNotFoundError` for nonexistent paths.
- [PASSED] ingest_oversized_file: `ingest_document()` raises `ValueError` when file size exceeds `MAX_FILE_SIZE_MB`.
- [PASSED] ingest_empty_document: `ingest_document()` raises `ValueError` when the loader returns no documents.
- [PASSED] ingest_persists_with_basename_metadata: `ingest_document()` passes `persist_directory=settings.chroma_persist_dir` to Chroma and rewrites source metadata to the file basename.
- [PASSED] ingest_cleanup_on_loader_failure: unsupported `/tmp` uploads are removed when loader validation fails inside the `try/finally`.
- [FAILED] ingest_cleanup_on_oversized_failure: oversized `/tmp` uploads are not removed after the size guard rejects them.
  - **Expected:** Session 2 states temp files are cleaned up in the `finally` block on any failure path.
  - **Actual:** The oversized file remains on disk because execution raises before entering the `try/finally`.
  - **Likely cause:** The size check at `src/ingest.py:71` runs before the cleanup block starts at `src/ingest.py:114`.
  - **Fix needed:** Move the size guard inside the `try` block or widen the `try/finally` so oversized temporary uploads are also cleaned up.

#### Spec Compliance
- [PASSED] blocker_b001_resolved: `.env.example` now uses a placeholder value instead of a real API-key-shaped token.
- [PASSED] persist_directory_required: `Chroma.from_documents()` is called with `persist_directory`, maintaining the "never in-memory only" invariant.
- [PASSED] basename_only_source_metadata: document metadata uses `os.path.basename(file_path)`, avoiding server-path leakage in citations.
- [FAILED] temp_file_deleted_after_ingestion_failure: the technical/trust-boundary expectation that temp files are deleted after ingestion failure does not hold for oversized uploads.

#### Adversarial
- [PASSED] unsupported_extension_attack: disallowed file types are rejected before any embedding or vectorstore interaction.
- [PASSED] path_leakage_reduction: citation metadata strips directory information before persistence.
- [BLOCKER] oversized_tmp_file_persists: a malicious or accidental oversized upload can leave sensitive document data in `/tmp`, violating the stated cleanup guarantee and allowing disk accumulation over repeated failures.

### Regressions
- None.

### Summary
- **Total:** 10 passed, 2 failed, 1 blocker
- **Modules validated:** `ingest`
- **Modules blocked:** `ingest`

### Handoff
- **Status:** BLOCKED
- **Claude should:** Fix `src/ingest.py` so oversized `/tmp` files are also cleaned up on failure, then rerun the ingest validation path.
- **Blockers:** `B-002`: oversized uploads bypass the `finally` cleanup and remain on disk.

---

## Session 3 — 2026-03-22 — VALIDATION

### Context
- **Reading from:** `.agent/handoff.json`, `.agent/claude_log.md` (Session 3), `.spec/system_spec.md`, `src/ingest.py`, `src/retrieval.py`
- **Validating:** `ingest.py` B-002 fix and new `retrieval.py`
- **Claude session referenced:** Session 3

### Test Results

#### Correctness
- [PASSED] ingest_cleanup_on_oversized_failure: oversized `/tmp` uploads are now removed after the size guard rejects them.
- [PASSED] query_brain_declines_when_no_results: `query_brain()` returns a declined response with confidence `0.0` when retrieval returns no matches.
- [PASSED] query_brain_declines_below_threshold_without_llm_call: `query_brain()` returns a declined response and does not instantiate the LLM when top relevance is below the confidence threshold.
- [PASSED] query_brain_answers_above_threshold_with_sources: `query_brain()` calls the LLM when confidence passes, returns an answered shape, and includes deduplicated source metadata.
- [PASSED] query_brain_collection_scope: `Chroma` is instantiated with the provided `collection_name` and configured `persist_directory`.
- [PASSED] query_brain_system_prompt_injected: the first LLM message is always the rigid `SYSTEM_PROMPT`.
- [PASSED] query_brain_error_propagation: vectorstore initialization errors propagate to the caller for FastAPI to translate.
- [PASSED] extract_sources_deduplicates_by_source_and_page: `_extract_sources()` emits unique citations by `(source, page)` and truncates content to 200 chars.
- [PASSED] declined_response_queryresponse_compatible: both declined and answered paths remain compatible with the `QueryResponse` schema.

#### Spec Compliance
- [PASSED] b002_resolved: the oversized-upload cleanup guarantee now holds, matching the temp-file cleanup invariant.
- [PASSED] confidence_gate_before_llm: retrieval scores are evaluated before any `ChatOpenAI` call is made.
- [PASSED] no_llm_on_declined: low-confidence and no-result paths return early without invoking the LLM.
- [PASSED] response_shape_invariant_retrieval: retrieval responses always include `answer`, `sources`, `confidence`, and `declined`.
- [PASSED] collection_isolation_contract: the query is scoped to the requested Chroma collection only.

#### Adversarial
- [PASSED] low_relevance_query_rejected: irrelevant retrieval results are declined instead of being handed to the model.
- [PASSED] injected_document_prompt_not_promoted: the rigid system prompt is placed ahead of document-derived user content in the LLM message list.
- [PASSED] duplicate_source_chunks_collapsed: repeated chunks from the same source/page do not produce duplicate citations.

### Regressions
- None.

### Summary
- **Total:** 17 passed, 0 failed, 0 blockers
- **Modules validated:** `ingest`, `retrieval`
- **Modules blocked:** None

### Handoff
- **Status:** READY_FOR_BUILD
- **Claude should:** Continue with the next implementation module, likely `main.py`, using the validated `config`, `models`, `ingest`, and `retrieval` layers.
- **Blockers:** None

---

## Session 4 — 2026-03-23 — VALIDATION

### Context
- **Reading from:** `.agent/handoff.json`, `.agent/claude_log.md` (Session 4), `.spec/system_spec.md`, `src/main.py`
- **Validating:** `main.py` endpoint wiring, startup behavior, and API boundary handling
- **Claude session referenced:** Session 4

### Test Results

#### Correctness
- [PASSED] health_endpoint_shape: `/health` returns `200` with `{"status": "ok", "version": "1.0.0"}`.
- [PASSED] startup_fail_fast_without_api_key: importing `src.main` without `OPENAI_API_KEY` fails immediately with `ValidationError`.
- [PASSED] upload_rejects_unsupported_file_types: `/upload` returns `422` before disk write for unsupported extensions.
- [PASSED] upload_rejects_invalid_company_values: `/upload` rejects collection names containing traversal or special characters.
- [PASSED] upload_success_response_shape: `/upload` returns `UploadResponse` with the chunk count from `ingest_document()`.
- [PASSED] upload_unexpected_errors_sanitized: unexpected ingestion failures return `502` with structured JSON and no traceback text.
- [PASSED] query_structured_response: `/query` returns a `QueryResponse`-compatible payload when `query_brain()` succeeds.
- [PASSED] query_request_validation: `/query` rejects empty questions and questions longer than 500 chars via `QueryRequest`.
- [PASSED] query_missing_collection_maps_to_404: `/query` translates collection-not-found failures into `404`.
- [PASSED] query_unexpected_errors_sanitized: `/query` returns `503` with structured JSON and no traceback text on unexpected failures.

#### Spec Compliance
- [PASSED] response_model_contracts: `/health`, `/upload`, and `/query` all return shapes compatible with their declared response models.
- [PASSED] trust_boundary_company_validation: `company` is validated at both the form boundary (`/upload`) and the JSON body boundary (`/query`).
- [PASSED] no_raw_tracebacks_in_responses: error responses expose safe `detail` strings instead of internal stack traces.
- [PASSED] cors_enabled: CORS middleware responds to preflight requests with allow-origin headers.
- [PASSED] fail_fast_startup_invariant: config validation is triggered during module import before the app begins serving requests.

#### Adversarial
- [PASSED] upload_extension_attack_rejected: unsupported upload types are blocked before ingestion starts.
- [PASSED] collection_hopping_input_rejected: malicious company names are rejected at the API boundary.
- [PASSED] error_surface_reduced: runtime failures do not leak Python tracebacks in HTTP responses.

### Regressions
- None.

### Summary
- **Total:** 18 passed, 0 failed, 0 blockers
- **Modules validated:** `main`
- **Modules blocked:** None

### Handoff
- **Status:** READY_FOR_BUILD
- **Claude should:** Continue to the next phase, likely frontend or deployment wiring, with the backend stack now fully validated.
- **Blockers:** None

---

## Session 5 — 2026-03-23 — VALIDATION

### Context
- **Reading from:** `.agent/handoff.json`, `.agent/claude_log.md` (Session 5), `.spec/system_spec.md`, `frontend/index.html`, `src/main.py`
- **Validating:** Frontend serving, client-side request wiring, XSS-safe rendering, and updated root route
- **Claude session referenced:** Session 5

### Test Results

#### Correctness
- [PASSED] root_serves_frontend_html: `GET /` returns the frontend HTML with the expected Company Brain UI content.
- [PASSED] api_routes_take_priority_over_frontend: `/health` still resolves to the API endpoint rather than the frontend route.
- [PASSED] upload_form_request_wiring: the frontend appends `file` and `company` fields and posts multipart data to `/upload`.
- [PASSED] query_form_request_wiring: the frontend posts JSON `{question, company}` to `/query` with the correct content type.
- [PASSED] file_input_resets_after_success: the upload success path clears the file input and restores the default label state.
- [PASSED] declined_visual_state_present: declined responses toggle the `.declined` answer styling path.
- [PASSED] confidence_bar_thresholds_present: the frontend maps confidence to green/yellow/red thresholds matching Claude’s stated design.
- [PASSED] error_messages_render_from_structured_detail: upload/query error paths display `data.detail` or a bounded fallback message.

#### Spec Compliance
- [PASSED] frontend_same_origin_serving: `src/main.py` serves `frontend/index.html` from `/`, supporting same-origin frontend/API deployment.
- [PASSED] citation_rendering_contract: source tags are rendered for returned citations, matching the "frontend renders answer with citation tags" data-flow spec.
- [PASSED] xss_safe_answer_rendering: answer text is written with `textContent`, not `innerHTML`.
- [PASSED] xss_safe_source_tag_rendering: source labels are escaped through `escapeHtml()` before insertion into HTML markup.
- [PASSED] client_file_type_hint_present: the file input advertises `.pdf,.txt,.md`, matching the backend-supported types.

#### Adversarial
- [PASSED] filename_xss_not_directly_injected: source names are escaped before rendering, reducing filename-based XSS risk.
- [PASSED] answer_xss_not_directly_injected: answer content is rendered as plain text, preventing script execution from response text.
- [PASSED] structured_error_surface_preserved: frontend error display paths are bounded to structured messages rather than raw exception objects.

### Regressions
- None.

### Summary
- **Total:** 16 passed, 0 failed, 0 blockers
- **Modules validated:** `frontend`
- **Modules blocked:** None

### Handoff
- **Status:** READY_FOR_BUILD
- **Claude should:** Continue with the next phase, likely deployment or further product polish, with the current backend and frontend stack validated.
- **Blockers:** None
