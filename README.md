# schema-extract

Schema-driven LLM extraction pipeline. Takes unstructured text and a user-defined schema, sends it to a local LLM via Ollama, and returns validated structured JSON.

The same pipeline handles medical notes, financial documents, job postings, or any domain. The schema is the only thing that changes.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Requires Ollama running locally at `http://localhost:11434` with `llama3.1:8b` pulled.

## Usage

### Run the demo

```bash
python -m schema_extract.pipeline
```

Runs the job posting schema against the included sample document and prints the prompt, extraction result, confidence score, and any validation errors.

### Use in code

```python
from pathlib import Path
from schema_extract.pipeline import run_extraction

result = run_extraction(
    schema_path=Path("schemas/job_posting.json"),
    document_text=Path("samples/job_postings/sample_01.txt").read_text(),
)

print(result.confidence)          # 0.9455
print(result.is_partial)          # False
print(result.extracted["salary_min"])  # 155000
```

### Define a schema

Create a JSON file in `schemas/` matching this structure:

```json
{
  "name": "my_schema",
  "description": "What this schema extracts.",
  "version": "1.0",
  "fields": [
    {
      "name": "company_name",
      "type": "str",
      "description": "The name of the hiring company.",
      "required": true,
      "examples": ["Acme Corp", "Stripe"]
    }
  ]
}
```

Field types: `str`, `int`, `float`, `bool`, `list`.

Then pass its path to `run_extraction()`.

## Result shape

`run_extraction()` returns an `ExtractionResult`:

| Field | Type | Description |
|---|---|---|
| `extracted` | `dict` | Validated field values keyed by field name |
| `confidence` | `float` | 0.0 to 1.0, weighted toward required fields |
| `is_partial` | `bool` | True if any required field came back null |
| `validation_errors` | `list[str]` | Field-level errors encountered |
| `attempts` | `int` | Number of model calls made |

## Run tests

```bash
pytest
```

Tests for the cleaner and validator run without Ollama.
