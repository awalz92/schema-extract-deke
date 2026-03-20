---
title: "Session 2: Response cleaning, Pydantic validation, retry logic, confidence scoring"
type: feat
status: completed
date: 2026-03-19
---

# Session 2: Response Cleaning, Validation, Retry, and Confidence Scoring

## Overview

Session 1 produced a working end-to-end pipeline that gets the right data out of the model — but wrapped in markdown fences, unvalidated, and returned as a raw string. Session 2 makes the pipeline production-worthy: clean the output, validate it against the schema, retry with corrective prompts on failure, and score extraction confidence.

The `run_extraction()` return type changes from `str` to `ExtractionResult`. This is the central change that everything else connects to.

---

## Proposed Solution

Four new components, each in its own module, wired together in the pipeline:

```
raw str (from OllamaClient)
    → clean_response()          extraction/cleaner.py
    → json.loads()              stdlib
    → validate_extraction()     extraction/validator.py
    → ExtractionResult          models/results.py
         └─ confidence: float
         └─ is_partial: bool
         └─ validation_errors: list[str]
         └─ attempts: int
    ↑ retry loop in pipeline.py (up to MAX_RETRIES=3)
         └─ build_retry_prompt() in extraction/prompt.py
```

---

## New Files

- **`src/schema_extract/extraction/cleaner.py`** — `clean_response(raw: str) -> str`
- **`src/schema_extract/extraction/validator.py`** — `validate_extraction(parsed: Any, schema: ExtractionSchema) -> ExtractionResult`
- **`src/schema_extract/models/results.py`** — `ExtractionResult` Pydantic model

## Modified Files

- **`src/schema_extract/extraction/prompt.py`** — add `build_retry_prompt(schema, document, errors, previous_response)`
- **`src/schema_extract/pipeline.py`** — retry loop, `OllamaClient` lifetime change, updated `__main__` demo block
- **`src/schema_extract/extraction/__init__.py`** — re-export new public symbols
- **`src/schema_extract/models/__init__.py`** — re-export `ExtractionResult`

## New Test Files

- **`tests/test_cleaner.py`** — pure function, no Ollama needed
- **`tests/test_validator.py`** — pure function, no Ollama needed

---

## Technical Decisions

### Response cleaning contract (`cleaner.py`)

`clean_response()` always strips leading/trailing whitespace first. Then:
- If the string contains a ` ``` ` opening fence, extract the content between the first opening fence and the last closing fence
- Truncate anything after the closing fence (trailing prose is discarded, not treated as a parse failure)
- If no fences are found, return the stripped string as-is (the model may have followed instructions correctly)
- Language tag after the opening fence (e.g., `json`) is stripped but does not affect behavior

Three cases to test:
1. ` ```json\n{...}\n``` ` → `{...}` ✅
2. `{...}` (no fences) → `{...}` ✅
3. ` ```json\n{...}\n```\nNote: salary not listed.` → `{...}` ✅ (trailing prose discarded)

### Two distinct failure modes

`json.loads()` failure and field validation failure require different retry prompts:
- **Parse failure**: model returned non-JSON text. Retry prompt includes the raw bad response and says "this was not valid JSON — return only a bare JSON object."
- **Validation failure**: model returned valid JSON but with wrong types or missing required fields. Retry prompt includes the specific field errors.

### `null` on required fields → soft failure

At `temperature=0.0`, retrying the identical document with the same required field missing will produce the same null output. Nulls on required fields are therefore treated as soft failures: they reduce confidence but do not trigger a retry *on their own*. Type errors and parse errors are hard failures that trigger retry.

After MAX_RETRIES with hard failures still present, return `ExtractionResult` with `is_partial=True` rather than raising — callers check the flag. Raising would give the caller nothing; a partial result with a flag lets them decide.

### Type coercion policy

Attempt coercion for obviously correct values with wrong JSON type (e.g., `"5"` → `5` for an `int` field, `"true"` → `True` for a `bool` field). Log a warning. Accept the coerced value — the model identified the right value, just with the wrong JSON type. Non-coercible mismatches (e.g., `"five"` for `int`) are hard validation failures.

### `ExtractionResult` shape

```python
# models/results.py
class ExtractionResult(BaseModel):
    extracted: dict[str, Any]        # validated (and coerced) field values
    confidence: float                # 0.0–1.0, see formula below
    is_partial: bool                 # True if required fields are null after all attempts
    validation_errors: list[str]     # empty on full success
    attempts: int                    # number of generate() calls made
```

### Confidence formula

```
confidence = (required_nonnull / max(required_count, 1)) * 0.7
           + (all_nonnull / max(all_count, 1)) * 0.3
```

- Required fields weighted 70%, all fields 30%
- Empty string `""` and empty list `[]` count as null (no information extracted)
- Computed at validation time, stored in `ExtractionResult`

### `OllamaClient` lifetime

The `with OllamaClient() as client:` block in `run_extraction()` must wrap the entire retry loop, not a single `generate()` call. This is a structural change to `pipeline.py` — the client stays open across all attempts (connection reuse, not reconnection per attempt).

### `MAX_RETRIES`

```python
MAX_RETRIES = 3  # module-level constant in pipeline.py, same style as MODEL = "llama3.1:8b"
```

### `run_extraction()` new signature

```python
def run_extraction(schema_path: Path, document_text: str) -> ExtractionResult:
```

The `__main__` demo block is updated to print `confidence`, `is_partial`, `validation_errors`, `attempts`, and the extracted dict.

---

## System-Wide Impact

- **API surface**: `run_extraction()` return type changes. Nothing currently calls it except the `__main__` block, but Session 4 FastAPI endpoints will depend on the new `ExtractionResult` type — keep it stable from here.
- **`OllamaClient` lifetime**: The `with` block in `pipeline.py` changes scope. No impact on `client.py` itself.
- **`prompt.py`**: Adding `build_retry_prompt()` alongside `build_prompt()`. Both are pure functions; no shared state.
- **Imports**: `extraction/__init__.py` and `models/__init__.py` need updated re-exports.

---

## Acceptance Criteria

- [ ] `clean_response()` handles fenced, unfenced, and fenced-with-trailing-prose model output
- [ ] `clean_response()` has unit tests covering all three cases (no Ollama needed)
- [ ] `json.loads()` failure triggers a parse-error retry prompt (distinct from validation-error prompt)
- [ ] Field type errors trigger a validation-error retry prompt listing the specific bad fields
- [ ] Type coercion is attempted for obvious mismatches (`"5"` → `5`); failures are hard errors
- [ ] `null` on a required field reduces confidence but does not trigger retry
- [ ] `ExtractionResult.confidence` is computed using the documented formula
- [ ] `ExtractionResult.is_partial` is `True` when any required field is null after all attempts
- [ ] Retry loop uses the same `OllamaClient` session across all attempts
- [ ] `run_extraction()` returns `ExtractionResult` in all code paths (no bare `raise` to caller)
- [ ] `validate_extraction()` has unit tests covering type pass, type coercion, type failure, missing required, null required
- [ ] `MAX_RETRIES = 3` is a named constant; retry count is visible in `ExtractionResult.attempts`
- [ ] `__main__` demo block prints the `ExtractionResult` fields cleanly
- [ ] All new function signatures have type hints and docstrings

## Testing Requirements

Write tests before wiring into the pipeline:
- `tests/test_cleaner.py` — test all three cleaning cases; no network calls
- `tests/test_validator.py` — test field-level validation: correct types, coercible types, non-coercible types, required-null, optional-null, confidence formula

Integration test (requires Ollama):
- Run `python -m schema_extract.pipeline` against `sample_01.txt` and assert `confidence > 0.7` and `is_partial == False`

---

## Dependencies & Risks

- **Determinism at temperature=0.0**: Retrying the identical prompt produces identical output. The retry prompt *must* differ meaningfully from the original. The current `build_prompt()` output becomes the baseline; retry prompts add error context and the model's previous response.
- **Context window**: `llama3.1:8b` has an 8192-token context window. Long documents + previous bad response + error context may approach the limit. Monitor `eval_count` from Ollama response metadata.
- **Session 4 compatibility**: `ExtractionResult` will be serialized to JSON by FastAPI. Pydantic v2 models serialize cleanly with `.model_dump()` — no extra work needed, but keep field names stable.

---

## Sources & References

- Existing pipeline entry point: `src/schema_extract/pipeline.py:23`
- Prompt builder (to add retry variant): `src/schema_extract/extraction/prompt.py`
- Schema models (field types, required flag): `src/schema_extract/models/schemas.py:14-35`
- OllamaClient context manager: `src/schema_extract/extraction/client.py:117-121`
- Session 1 failure mode: model output was correct data in ` ```json ... ``` ` fences; `json.loads()` failed on the fences
