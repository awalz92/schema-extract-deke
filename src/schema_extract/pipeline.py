"""Minimal extraction pipeline orchestrator — Session 1."""

import json
import logging
from pathlib import Path

from schema_extract.extraction.client import OllamaClient
from schema_extract.extraction.prompt import build_prompt
from schema_extract.models.schemas import ExtractionSchema

logger = logging.getLogger(__name__)

MODEL = "llama3.1:8b"

# Resolve paths relative to this file so the module works from any working directory.
# Python note: `__file__` is the path to the current module. `.parent` walks up the
# directory tree — equivalent to File.getParentFile() in Java.
_REPO_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_SCHEMA = _REPO_ROOT / "schemas" / "job_posting.json"
_DEFAULT_SAMPLE = _REPO_ROOT / "samples" / "job_postings" / "sample_01.txt"


def run_extraction(schema_path: Path, document_text: str) -> str:
    """Load a schema, build a prompt, call Ollama, and return the raw model response.

    Args:
        schema_path: Path to the JSON schema definition file.
        document_text: The raw unstructured text to extract from.

    Returns:
        Raw text response from the model (not yet validated or parsed).

    Raises:
        RuntimeError: If Ollama is unreachable.
        FileNotFoundError: If the schema file does not exist.
        ValueError: If the schema file does not match the expected format.
    """
    schema = ExtractionSchema.from_file(schema_path)
    logger.info("Loaded schema '%s' with %d fields", schema.name, len(schema.fields))

    prompt = build_prompt(schema, document_text)
    logger.info("Prompt built (%d chars)", len(prompt))

    with OllamaClient() as client:
        if not client.health_check():
            raise RuntimeError("Ollama is not reachable. Is it running?")
        raw_response = client.generate(model=MODEL, prompt=prompt)

    return raw_response


if __name__ == "__main__":
    # Demo block — prints intermediate artifacts for inspection during development.
    # Using print here intentionally (not logging) so output is visible without
    # configuring a log handler.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    schema_path = _DEFAULT_SCHEMA
    document_text = _DEFAULT_SAMPLE.read_text(encoding="utf-8")

    schema = ExtractionSchema.from_file(schema_path)
    prompt = build_prompt(schema, document_text)

    print("=" * 70)
    print("CONSTRUCTED PROMPT")
    print("=" * 70)
    print(prompt)

    print("\n" + "=" * 70)
    print(f"CALLING OLLAMA  (model={MODEL})")
    print("=" * 70)

    with OllamaClient() as client:
        if not client.health_check():
            print("ERROR: Ollama is not reachable.")
            raise SystemExit(1)
        raw_response = client.generate(model=MODEL, prompt=prompt)

    print("\n" + "=" * 70)
    print("RAW MODEL RESPONSE")
    print("=" * 70)
    print(raw_response)

    print("\n" + "=" * 70)
    print("JSON PARSE ATTEMPT")
    print("=" * 70)
    try:
        parsed = json.loads(raw_response)
        print("SUCCESS — parsed JSON:")
        # Python note: `json.dumps(..., indent=2)` pretty-prints a dict/list.
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError as exc:
        print(f"FAILED to parse as JSON: {exc}")
        print("(This is expected on first run — retry logic comes in Session 2)")
