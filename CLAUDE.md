# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run the demo pipeline (end-to-end extraction, prints prompt + raw model response)
python -m schema_extract.pipeline

# Run tests
.venv/bin/pytest

# Run a single test file
.venv/bin/pytest tests/test_foo.py

# Run a single test by name
.venv/bin/pytest -k "test_name"
```

Ollama must be running locally at `http://localhost:11434` with `llama3.1:8b` pulled. Verify with `curl http://localhost:11434/api/tags`.

## Architecture

This is a schema-driven LLM extraction pipeline. The data flow is:

```
JSON schema file → ExtractionSchema (Pydantic) → build_prompt() → OllamaClient.generate() → raw text → (validation/parsing in later sessions)
```

**`src/schema_extract/`** — the main package (src layout; `pythonpath = ["src"]` in pytest config means imports work as `from schema_extract.X import Y`).

- **`models/schemas.py`** — Pydantic v2 models that define *what to extract*: `FieldDefinition` (one field: name, type, description, required, examples) and `ExtractionSchema` (a named collection of fields). `ExtractionSchema.from_file(path)` loads from JSON. These are schema *definitions*, not extraction *results*.

- **`extraction/client.py`** — `OllamaClient`: synchronous `httpx.Client` wrapper. Hits `/api/generate` with `"stream": false`. Uses `temperature=0.0` by default for deterministic extraction. Implements `__enter__`/`__exit__` so it's usable as a context manager. The `health_check()` method hits `/api/tags`.

- **`extraction/prompt.py`** — `build_prompt(schema, document)`: assembles the full prompt string from a schema and raw document text. Instructs the model to return bare JSON only.

- **`pipeline.py`** — `run_extraction(schema_path, document_text)` ties the above together. The `__main__` block is the demo entry point: prints the constructed prompt, calls Ollama, prints the raw response, and attempts `json.loads()`.

**`schemas/`** — JSON schema definition files (not JSON Schema spec — our own format matching `ExtractionSchema`). One schema per domain (e.g., `job_posting.json`).

**`samples/`** — Raw input documents for manual testing, organized by schema type.

## Key conventions

- `pathlib.Path` everywhere, no string paths.
- `logging` module in library code; `print` only in `__main__` demo blocks.
- Type hints on all function signatures.
- Mutable defaults use `None` + internal `or {}` — never `def f(x: dict = {})`.
- `OllamaClient` should always be used as a context manager (`with OllamaClient() as client:`).
