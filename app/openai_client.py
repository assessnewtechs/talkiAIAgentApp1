"""Azure OpenAI client utilities for the Splunk AI Agent application."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, List

from openai import AzureOpenAI

logger = logging.getLogger(__name__)


def _get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Environment variable '{name}' is required but was not set.")
    return value


class AzureOpenAIClient:
    """Wrapper around the Azure OpenAI Chat Completions API."""

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
        deployment: str | None = None,
        api_version: str | None = None,
    ) -> None:
        self._endpoint = endpoint or _get_env("AZURE_OPENAI_ENDPOINT")
        self._api_key = api_key or _get_env("AZURE_OPENAI_KEY")
        self._deployment = deployment or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-35-turbo")
        self._api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

        self._client = AzureOpenAI(
            api_key=self._api_key,
            api_version=self._api_version,
            azure_endpoint=self._endpoint,
        )

    @property
    def deployment(self) -> str:
        return self._deployment

    def _chat_completion(self, messages: List[dict[str, str]], temperature: float = 0.0) -> str:
        response = self._client.chat.completions.create(
            model=self._deployment,
            temperature=temperature,
            messages=messages,
        )

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError) as exc:  # pragma: no cover - defensive.
            logger.exception("Unexpected response format from Azure OpenAI: %s", response)
            raise RuntimeError("Azure OpenAI response missing content") from exc

        if not content:
            raise RuntimeError("Azure OpenAI returned empty content")

        return content.strip()

    def generate_spl(self, question: str) -> str:
        """Generate an SPL query for the provided natural language question."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert Splunk Search Processing Language (SPL) assistant. "
                    "Given a natural language question, respond with only the SPL query that "
                    "should be executed in Splunk. The query must be valid SPL and should not "
                    "include explanations or backticks."
                ),
            },
            {"role": "user", "content": question},
        ]

        spl_query = self._chat_completion(messages)
        logger.debug("Generated SPL query: %s", spl_query)
        return spl_query

    def summarize_results(self, question: str, results: List[dict[str, Any]]) -> str:
        """Generate a natural language summary of SPL results."""
        # Limit payload size when summarising large result sets.
        snippet = json.dumps(results[:20], ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "You help security analysts understand Splunk search results. "
                    "Summarize the results in clear, concise language, referencing the "
                    "original question when relevant. If no results are available, say so."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Question: {question}\n\n"
                    "First rows of SPL results (JSON array):\n{results}\n\n"
                    "Provide a short summary."
                ).format(question=question, results=snippet),
            },
        ]

        summary = self._chat_completion(messages, temperature=0.2)
        logger.debug("Generated summary: %s", summary)
        return summary


__all__ = ["AzureOpenAIClient"]
