---
title: "LLM extraction pipeline: response cleaning, validation, retry, and confidence scoring"
date: "2026-03-19"
category: "logic-errors"
tags: ["llm", "ollama", "response-cleaning", "pydantic-v2", "retry-logic", "confidence-scoring", "python"]
problem_type: "llm_output_processing"
components:
  - "extraction/cleaner.py"
  - "extraction/validator.py"
  - "extraction/prompt.py"
  - "models/results.py"
  - "pipeline.py"
symptoms:
  - "json.loads() fails because model wraps output in markdown fences"
  - "No type validation of extracted fields against schema"
  - "Single failure blocks the entire extraction with no result returned"
  - "No measure of extraction quality"
---

# LLM Extraction Pipeline: Response Cleaning, Validation, Retry, and Confidence Scoring

Four patterns established in Session 2 for making local LLM extraction reliable. Applied together, they turn raw model output into a validated, scored, retried result with a stable return type.

---

## Problem

Raw Ollama output looks like:

```
```json
{"company_name": "Meridian Financial Technologies", "salary_min": "155000"}
```
Note: salary_max not found.
```

Four things are wrong: (1) it's fenced, so `json.loads()` fails; (2) `salary_min` is a string, not an int; (3) there's trailing prose after the closing fence; (4) there's no way to tell callers how good the extraction was.

---

## Solutions

### 1. Fence stripping — `extraction/cleaner.py`

Regex extracts content between the first opening fence and last closing fence. Anything after the closing fence is discarded.

```python
_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)

def clean_response(raw: str) -> str:
    stripped = raw.strip()
    match = _FENCE_RE.search(stripped)
    if match:
        return match.group(1).strip()
    return stripped  # model followed instructions; no fences
```

Three cases covered: fenced with language tag, fenced without tag, unfenced. Trailing prose after the closing fence is automatically dropped.

---

### 2. Validation with type coercion — `extraction/validator.py`

Per-field type checking against `ExtractionSchema.fields`. Coercion is attempted before rejecting a value as a hard error.

```python
def _coerce(value: Any, target_type: str) -> tuple[Any, bool]:
    try:
        if target_type == "int":
            return int(str(value)), True
        if target_type == "float":
            return float(str(value)), True
        if target_type == "bool" and isinstance(value, str):
            if value.lower() in ("true", "1", "yes"):
                return True, True
            if value.lower() in ("false", "0", "no"):
                return False, True
    except (ValueError, TypeError):
        pass
    return value, False
```

**Key policy:** Null on a required field is a **soft failure** (reduces confidence, sets `is_partial=True`) but does not trigger retry. At `temperature=0.0`, the model produces identical output on retry when the document simply does not contain the field. Type mismatches are **hard failures** and do trigger retry.

Empty string `""` and empty list `[]` count as null for confidence purposes.

---

### 3. ExtractionResult — `models/results.py`

All code paths return this. Never raises to the caller.

```python
class ExtractionResult(BaseModel):
    extracted: dict[str, Any]     # validated + coerced values
    confidence: float              # 0.0–1.0
    is_partial: bool               # True if any required field is null
    validation_errors: list[str]   # empty on full success
    attempts: int                  # number of model calls made
```

**Confidence formula:**
```
confidence = (required_nonnull / max(required_count, 1)) * 0.7
           + (all_nonnull / max(all_count, 1)) * 0.3
```

Required fields are weighted 70% — missing a required field is penalized more than missing an optional one.

---

### 4. Retry with corrective prompts — `pipeline.py` + `extraction/prompt.py`

`build_retry_prompt()` includes the model's previous bad response and specific errors. This is more effective than just repeating the original prompt because the model can see exactly what it got wrong.

```python
def build_retry_prompt(schema, document, errors, previous_response) -> str:
    errors_block = "\n".join(f"- {e}" for e in errors)
    # includes: previous response, list of specific errors, full schema + document
```

**OllamaClient lifetime:** The `with OllamaClient() as client:` block wraps the entire retry loop — not a single `generate()` call. Connection reuse across attempts, not reconnection per attempt.

```python
MAX_RETRIES = 3

with OllamaClient() as client:
    for attempt in range(1, MAX_RETRIES + 1):
        raw = client.generate(model=MODEL, prompt=current_prompt)
        cleaned = clean_response(raw)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            # parse failure → retry with parse-error prompt
            current_prompt = build_retry_prompt(schema, document, [str(exc)], raw)
            continue
        result, hard_errors = validate_extraction(parsed, schema)
        if not hard_errors:
            break  # success or soft failure — done
        # hard validation failure → retry with validation-error prompt
        current_prompt = build_retry_prompt(schema, document, hard_errors, raw)
```

---

## Live Result

First real run against the job posting sample:

```
confidence   : 0.9455
is_partial   : False
attempts     : 1
errors       : none
```

The model returned correct data on attempt 1 with no retry needed.

---

## Prevention

### Checklist for LLM extraction pipelines

- Always strip output before `json.loads()` — assume every model will produce fences at least sometimes
- Distinguish parse errors from validation errors — they need different retry prompts
- Attempt type coercion before treating a mismatch as a hard failure
- Keep the HTTP client open across all retry attempts (one `with` block at the outermost level)
- Include the model's previous bad response in the retry prompt — not just the error
- Null on required fields is a soft failure, not a retry trigger, when `temperature=0.0`
- Return a result object in all code paths; never raise to the caller on extraction failure

### What to test (non-obvious)

- All three fence variants: with language tag, without tag, unfenced, trailing prose
- Coercion: `"42"` → `int`, `"true"` → `bool`, non-coercible `"five"` → hard error
- Required field null: soft failure (`is_partial=True`), no retry, confidence < 1.0
- Optional field null: not partial, no error
- Non-dict response (`null`, `[]`, bare string): hard error, `confidence=0.0`
- Confidence formula: all-required-nonnull = 1.0, half-required-nonnull = 0.5

---

## Related

- `docs/solutions/build-errors/python-project-bootstrap.md` — project setup gotchas this work builds on
