"""Validate parsed extraction output against an ExtractionSchema."""

import logging
from typing import Any

from schema_extract.models.results import ExtractionResult
from schema_extract.models.schemas import ExtractionSchema

logger = logging.getLogger(__name__)

# Maps FieldDefinition.type strings to Python types used for isinstance checks.
_TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
}


def _is_empty(value: Any) -> bool:
    """Return True if a value carries no information (null, empty str, empty list)."""
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def _coerce(value: Any, target_type: str) -> tuple[Any, bool]:
    """Attempt type coercion for obviously-correct values with wrong JSON type.

    Returns:
        (coerced_value, success). If coercion is not possible, success is False
        and the original value is returned.
    """
    try:
        if target_type == "int":
            coerced = int(str(value))
            logger.warning("Coerced %r to int %r", value, coerced)
            return coerced, True
        if target_type == "float":
            coerced = float(str(value))
            logger.warning("Coerced %r to float %r", value, coerced)
            return coerced, True
        if target_type == "bool" and isinstance(value, str):
            if value.lower() in ("true", "1", "yes"):
                return True, True
            if value.lower() in ("false", "0", "no"):
                return False, True
    except (ValueError, TypeError):
        pass
    return value, False


def validate_extraction(parsed: Any, schema: ExtractionSchema) -> tuple[ExtractionResult, list[str]]:
    """Validate a parsed JSON dict against an ExtractionSchema.

    Applies per-field type checking with coercion for obvious mismatches.
    Null on a required field is a soft failure: it reduces confidence and sets
    is_partial=True, but does not appear in the returned hard_errors list.
    Type errors are hard failures returned in hard_errors (triggering retry).

    Args:
        parsed: The result of json.loads() on the cleaned model response.
        schema: The ExtractionSchema to validate against.

    Returns:
        A tuple of (ExtractionResult, hard_errors). hard_errors is a list of
        error strings for type mismatches — empty on success or soft failures.
        The caller uses hard_errors to decide whether to retry.
    """
    all_errors: list[str] = []
    hard_errors: list[str] = []

    if not isinstance(parsed, dict):
        err = f"Model response is not a JSON object (got {type(parsed).__name__})"
        return (
            ExtractionResult(
                extracted={},
                confidence=0.0,
                is_partial=True,
                validation_errors=[err],
                attempts=0,  # caller sets final attempt count
            ),
            [err],
        )

    extracted: dict[str, Any] = {}
    required_count = sum(1 for f in schema.fields if f.required)
    required_nonnull = 0
    all_nonnull = 0

    for field in schema.fields:
        raw_value = parsed.get(field.name)
        expected_python_type = _TYPE_MAP[field.type]

        if _is_empty(raw_value):
            extracted[field.name] = raw_value
            if field.required:
                all_errors.append(f"Required field '{field.name}' is null or empty")
            continue

        # Type check
        if not isinstance(raw_value, expected_python_type):
            # Attempt coercion before treating as hard error
            coerced, ok = _coerce(raw_value, field.type)
            if ok:
                extracted[field.name] = coerced
                all_nonnull += 1
                if field.required:
                    required_nonnull += 1
            else:
                err = (
                    f"Field '{field.name}' expected {field.type}, "
                    f"got {type(raw_value).__name__} ({raw_value!r})"
                )
                all_errors.append(err)
                hard_errors.append(err)
                extracted[field.name] = None
        else:
            extracted[field.name] = raw_value
            all_nonnull += 1
            if field.required:
                required_nonnull += 1

    all_count = len(schema.fields)
    confidence = (
        (required_nonnull / max(required_count, 1)) * 0.7
        + (all_nonnull / max(all_count, 1)) * 0.3
    )

    # Soft failure: any required field is null/empty
    is_partial = any(
        _is_empty(extracted.get(f.name)) for f in schema.fields if f.required
    )

    result = ExtractionResult(
        extracted=extracted,
        confidence=round(confidence, 4),
        is_partial=is_partial,
        validation_errors=all_errors,
        attempts=0,  # caller sets final attempt count
    )
    return result, hard_errors
