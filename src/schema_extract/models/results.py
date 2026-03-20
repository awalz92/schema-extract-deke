"""Pydantic model for extraction results."""

from typing import Any

from pydantic import BaseModel


class ExtractionResult(BaseModel):
    """The output of a run_extraction() call.

    Contains the extracted field values, a confidence score, a flag for
    partial results (required fields that came back null), the list of
    validation errors encountered, and the number of model calls made.
    """

    extracted: dict[str, Any]
    confidence: float
    is_partial: bool
    validation_errors: list[str]
    attempts: int
