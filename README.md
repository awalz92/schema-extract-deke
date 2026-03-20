# schema-extract

Schema-driven LLM extraction pipeline. Takes unstructured text and a user-defined schema, sends it to a local LLM via Ollama, and returns validated structured JSON.

The same pipeline handles medical notes, financial documents, job postings, or any domain — the schema is the only thing that changes.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Requires Ollama running locally at `http://localhost:11434` with `llama3.1:8b` pulled.

## Run demo extraction

```bash
python -m schema_extract.pipeline
```
