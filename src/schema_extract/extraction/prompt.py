"""Prompt construction from an ExtractionSchema and a document string."""

import logging

from schema_extract.models.schemas import ExtractionSchema, FieldDefinition

logger = logging.getLogger(__name__)


def _format_field(field: FieldDefinition) -> str:
    """Format a single FieldDefinition into a human-readable prompt line."""
    required_label = "required" if field.required else "optional"
    examples_text = ""
    if field.examples:
        formatted = ", ".join(f'"{e}"' for e in field.examples)
        examples_text = f"\n    Examples: {formatted}"

    return (
        f"- {field.name} ({field.type}, {required_label}): {field.description}"
        f"{examples_text}"
    )


def build_prompt(schema: ExtractionSchema, document: str) -> str:
    """Build an extraction prompt from a schema and a raw document string.

    The prompt instructs the model to extract each field defined in the schema
    and return ONLY a valid JSON object — no preamble, explanation, or markdown.

    Args:
        schema: The ExtractionSchema defining which fields to extract.
        document: The raw unstructured text to extract from.

    Returns:
        A formatted prompt string ready to send to the model.
    """
    fields_block = "\n".join(_format_field(f) for f in schema.fields)

    # Python note: Triple-quoted f-strings are the idiomatic way to write multi-line
    # template strings. No string concatenation, no template engine needed for this.
    # The backslash at the end of the first line avoids a leading newline in the result.
    prompt = f"""\
You are a structured data extraction assistant. Your task is to extract specific fields \
from the document below and return them as a single valid JSON object.

SCHEMA: {schema.name}
{schema.description}

FIELDS TO EXTRACT:
{fields_block}

RULES:
- Return ONLY a valid JSON object. No explanation, no markdown, no code fences.
- Use null for any field that cannot be determined from the document.
- For list fields, return a JSON array of strings.
- For int fields, return a number with no units or currency symbols.
- Do not infer or guess values that are not present in the document.

DOCUMENT:
{document}

JSON:"""

    logger.debug(
        "Built prompt for schema '%s' (%d chars, %d fields)",
        schema.name,
        len(prompt),
        len(schema.fields),
    )
    return prompt
