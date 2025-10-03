"""FastAPI application entry point for the Splunk AI Agent."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .openai_client import AzureOpenAIClient
from .splunk_client import SplunkClient, SplunkClientError

load_dotenv()

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)

app = FastAPI(title="Splunk AI Agent", version="1.0.0")


class AskRequest(BaseModel):
    question: str = Field(
        ..., min_length=1, description="Natural language question to translate into SPL."
    )
    splunk_host: str | None = Field(
        default=None,
        description=(
            "Optional Splunk host override for this request. When omitted the service uses"
            " the default host configured via environment variables."
        ),
        example="splunk.internal.example.com",
    )
    splunk_verify_ssl: bool | None = Field(
        default=None,
        description=(
            "Override for Splunk SSL verification. Set to false to disable certificate"
            " validation for this specific request."
        ),
        example=False,
    )
    splunk_request_timeout: float | None = Field(
        default=None,
        description="Override for the Splunk request timeout, in seconds, for this call.",
        example=120,
    )


class AskResponse(BaseModel):
    question: str
    spl_query: str
    results: List[Dict[str, Any]]
    summary: str


# Instantiate clients once during startup.
openai_client = AzureOpenAIClient()
splunk_client = SplunkClient()


@app.get("/health")
def health() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    """Generate an SPL query for the question, execute it, and summarize the results."""
    logger.info("Received question: %s", request.question)
    try:
        spl_query = openai_client.generate_spl(request.question)
    except Exception as exc:  # pragma: no cover - network failure.
        logger.exception("Failed to generate SPL query")
        raise HTTPException(status_code=502, detail=f"Failed to generate SPL query: {exc}") from exc

    if (
        request.splunk_host is None
        and request.splunk_verify_ssl is None
        and request.splunk_request_timeout is None
    ):
        client = splunk_client
    else:
        client = SplunkClient(
            host=request.splunk_host,
            verify_ssl=request.splunk_verify_ssl,
            timeout=request.splunk_request_timeout,
        )

    try:
        results = client.run_query(spl_query)
    except SplunkClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - network failure.
        logger.exception("Unexpected error when running SPL query")
        raise HTTPException(status_code=500, detail="Unexpected error executing SPL query") from exc

    summary: str
    try:
        summary = openai_client.summarize_results(request.question, results)
    except Exception as exc:  # pragma: no cover - network failure.
        logger.exception("Failed to generate summary")
        summary = "Unable to generate summary at this time."

    response = AskResponse(
        question=request.question,
        spl_query=spl_query,
        results=results,
        summary=summary,
    )
    logger.info("Responding with %d results", len(results))
    return response


__all__ = ["app"]
