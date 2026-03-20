"""Pydantic models for extraction schema definitions."""

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Python note: Literal from typing lets you constrain a str to a fixed set of values.
# Pydantic v2 uses it for validation — the field will reject anything not in the union.
FieldType = Literal["str", "int", "float", "bool", "list"]


class FieldDefinition(BaseModel):
    """Describes a single field to be extracted from a document."""

    name: str
    type: FieldType
    description: str
    required: bool = True
    # Python note: `Field(default=None)` lets us set metadata alongside the default.
    # `list[str] | None` is the modern union syntax (Python 3.10+, works in 3.12).
    examples: list[str] | None = Field(default=None)


class ExtractionSchema(BaseModel):
    """A named, versioned schema defining what fields to extract from unstructured text."""

    name: str
    description: str
    version: str = "1.0"
    fields: list[FieldDefinition]

    @classmethod
    def from_file(cls, path: Path) -> "ExtractionSchema":
        """Load and parse an ExtractionSchema from a JSON file.

        Args:
            path: Path to the JSON schema definition file.

        Returns:
            A validated ExtractionSchema instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the JSON does not match the expected schema.
        """
        logger.debug("Loading schema from %s", path)
        text = path.read_text(encoding="utf-8")
        # Python note: `cls(...)` here is equivalent to `ExtractionSchema(...)` but
        # works correctly in subclasses — a classmethod best practice in Python.
        return cls.model_validate(json.loads(text))
