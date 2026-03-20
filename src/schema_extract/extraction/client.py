"""Synchronous HTTP client wrapper for the Ollama API."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT = 120.0  # seconds — local models can be slow on first token


class OllamaClient:
    """Thin wrapper around the Ollama HTTP API.

    Handles connection errors and surfaces clear messages when Ollama is not running.
    Does not manage model lifecycle — assumes the model is already pulled.
    """

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        # Python note: httpx.Client is a context manager but also works as a plain
        # object with an explicit .close(). Here we hold it as an instance attribute
        # and reuse it across calls (connection pooling, keep-alive).
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self.base_url = base_url

    def health_check(self) -> bool:
        """Return True if Ollama is reachable and has at least one model available.

        Hits GET /api/tags — the lightweight Ollama endpoint for listing local models.
        """
        try:
            response = self._client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            logger.info("Ollama reachable. Available models: %s", models)
            return True
        except httpx.ConnectError:
            logger.error(
                "Cannot reach Ollama at %s — is Ollama running?", self.base_url
            )
            return False
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama health check failed: HTTP %s", exc.response.status_code)
            return False

    def generate(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.0,
        extra_params: dict[str, Any] | None = None,
    ) -> str:
        """Send a generation request to Ollama and return the model's text response.

        Args:
            model: The model name as known to Ollama (e.g. "llama3.1:8b").
            prompt: The full prompt string to send.
            temperature: Sampling temperature. 0.0 = deterministic (good for extraction).
            extra_params: Optional additional Ollama options (e.g. {"num_predict": 512}).

        Returns:
            The raw text response from the model.

        Raises:
            RuntimeError: If Ollama is unreachable or returns an error response.
        """
        # Python note: `or {}` handles the None default for a mutable argument.
        # Never use a mutable default like `extra_params: dict = {}` — it's shared
        # across all calls (a classic Python gotcha from Java/C# background).
        options: dict[str, Any] = {"temperature": temperature}
        if extra_params:
            options.update(extra_params)

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,  # Get the full response in one shot, not streamed chunks
            "options": options,
        }

        logger.debug("Sending generate request to Ollama (model=%s)", model)

        try:
            response = self._client.post("/api/generate", json=payload)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.base_url} — is Ollama running?"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Ollama returned HTTP {exc.response.status_code}: {exc.response.text}"
            ) from exc

        data = response.json()
        raw_text: str = data["response"]
        logger.debug(
            "Received response (%d chars, eval_count=%s tokens)",
            len(raw_text),
            data.get("eval_count"),
        )
        return raw_text

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    # Python note: __enter__/__exit__ make this usable as a context manager:
    # `with OllamaClient() as client: ...` — same pattern as Java's AutoCloseable.
    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
