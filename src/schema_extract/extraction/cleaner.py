"""Response cleaning: strip markdown fences from raw LLM output."""

import logging
import re

logger = logging.getLogger(__name__)

# Matches the first opening fence (```json or ```) anywhere in the string and
# captures content up to the closing fence. The ^ anchor is intentionally absent
# so preamble sentences ("Here is the JSON:") before the fence are skipped.
_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


def clean_response(raw: str) -> str:
    """Strip markdown code fences from a raw model response.

    Handles three cases:
    - Fenced with language tag:  ```json\\n{...}\\n```  → ``{...}``
    - Fenced without tag:        ```\\n{...}\\n```       → ``{...}``
    - Unfenced (model complied): ``{...}``               → ``{...}``
    - Fenced with trailing prose: fence content is extracted, trailing text discarded

    Args:
        raw: The raw string returned by OllamaClient.generate().

    Returns:
        The cleaned string, ready for json.loads(). Leading/trailing
        whitespace is always stripped.
    """
    stripped = raw.strip()
    match = _FENCE_RE.search(stripped)
    if match:
        content = match.group(1).strip()
        logger.debug("Stripped markdown fences from response (%d → %d chars)", len(stripped), len(content))
        return content

    logger.debug("No markdown fences found; returning stripped response as-is")
    return stripped
