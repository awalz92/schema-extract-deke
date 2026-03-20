"""Extraction pipeline orchestrator."""

import json
import logging
from pathlib import Path

from schema_extract.extraction.cleaner import clean_response
from schema_extract.extraction.client import OllamaClient
from schema_extract.extraction.prompt import build_prompt, build_retry_prompt
from schema_extract.extraction.validator import validate_extraction
from schema_extract.models.results import ExtractionResult
from schema_extract.models.schemas import ExtractionSchema

logger = logging.getLogger(__name__)

MODEL = "llama3.1:8b"
MAX_RETRIES = 3

# Python note: `__file__` is the path to the current module. `.parent` walks up the
# directory tree — equivalent to File.getParentFile() in Java.
_REPO_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_SCHEMA = _REPO_ROOT / "schemas" / "job_posting.json"
_DEFAULT_SAMPLE = _REPO_ROOT / "samples" / "job_postings" / "sample_01.txt"


def run_extraction(schema_path: Path, document_text: str, model: str = MODEL) -> ExtractionResult:
    """Load a schema, build a prompt, call Ollama, clean + validate the response.

    Retries up to MAX_RETRIES times on hard failures (JSON parse errors or field
    type mismatches). Null values on required fields are soft failures: they reduce
    confidence and set is_partial=True but do not trigger a retry, because at
    temperature=0.0 retrying the same document produces the same result.

    Args:
        schema_path: Path to the JSON schema definition file.
        document_text: The raw unstructured text to extract from.

    Returns:
        ExtractionResult with extracted fields, confidence score, is_partial flag,
        validation errors, and the number of model calls made.

    Raises:
        RuntimeError: If Ollama is unreachable.
        FileNotFoundError: If the schema file does not exist.
        ValueError: If the schema file does not match the expected format.
    """
    schema = ExtractionSchema.from_file(schema_path)
    logger.info("Loaded schema '%s' with %d fields", schema.name, len(schema.fields))

    current_prompt = build_prompt(schema, document_text)
    previous_response: str = ""
    last_result: ExtractionResult | None = None

    with OllamaClient() as client:
        if not client.health_check():
            raise RuntimeError("Ollama is not reachable. Is it running?")

        for attempt in range(1, MAX_RETRIES + 1):
            logger.info("Attempt %d/%d", attempt, MAX_RETRIES)

            raw = client.generate(model=model, prompt=current_prompt)
            previous_response = raw
            cleaned = clean_response(raw)

            # --- JSON parse ---
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                errors = [f"Response is not valid JSON: {exc}"]
                logger.warning("Attempt %d: parse failure — %s", attempt, exc)
                if attempt < MAX_RETRIES:
                    current_prompt = build_retry_prompt(
                        schema, document_text, errors, previous_response
                    )
                    continue
                # Exhausted retries on parse failure — return empty partial result
                last_result = ExtractionResult(
                    extracted={},
                    confidence=0.0,
                    is_partial=True,
                    validation_errors=errors,
                    attempts=attempt,
                )
                break

            # --- Validation ---
            result, hard_errors = validate_extraction(parsed, schema)
            result = result.model_copy(update={"attempts": attempt})
            last_result = result

            if not hard_errors:
                logger.info(
                    "Attempt %d: success (confidence=%.2f, is_partial=%s)",
                    attempt,
                    result.confidence,
                    result.is_partial,
                )
                break

            logger.warning(
                "Attempt %d: %d hard validation error(s): %s",
                attempt,
                len(hard_errors),
                hard_errors,
            )
            if attempt < MAX_RETRIES:
                current_prompt = build_retry_prompt(
                    schema, document_text, hard_errors, previous_response
                )

    if last_result is None:
        raise RuntimeError("Extraction loop exited without producing a result")
    return last_result


if __name__ == "__main__":
    # Demo block — prints intermediate artifacts for inspection.
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
    print(f"CALLING OLLAMA  (model={MODEL}, max_retries={MAX_RETRIES})")
    print("=" * 70)

    result = run_extraction(schema_path, document_text)

    print("\n" + "=" * 70)
    print("EXTRACTION RESULT")
    print("=" * 70)
    print(f"  confidence   : {result.confidence:.4f}")
    print(f"  is_partial   : {result.is_partial}")
    print(f"  attempts     : {result.attempts}")
    print(f"  errors       : {result.validation_errors or 'none'}")
    print()
    print(json.dumps(result.extracted, indent=2))
