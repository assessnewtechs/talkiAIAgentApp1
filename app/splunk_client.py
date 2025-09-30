"""Splunk REST API client for executing SPL queries."""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


class SplunkClientError(RuntimeError):
    """Raised when a Splunk API call fails."""


class SplunkClient:
    def __init__(
        self,
        *,
        host: str | None = None,
        port: str | int | None = None,
        username: str | None = None,
        password: str | None = None,
        scheme: str | None = None,
        verify_ssl: bool | None = None,
        timeout: int | float | None = None,
    ) -> None:
        self.host = host or self._get_env("SPLUNK_HOST")
        self.port = str(port or os.getenv("SPLUNK_PORT", "8089"))
        self.username = username or self._get_env("SPLUNK_USERNAME")
        self.password = password or self._get_env("SPLUNK_PASSWORD")
        self.scheme = scheme or os.getenv("SPLUNK_SCHEME", "https")

        verify_env = os.getenv("SPLUNK_VERIFY_SSL", "true").lower()
        if verify_ssl is None:
            verify_ssl = verify_env in {"1", "true", "yes", "on"}
        self.verify_ssl = verify_ssl

        self.timeout = timeout or float(os.getenv("SPLUNK_REQUEST_TIMEOUT", "60"))

        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(self.username, self.password)
        self.session.verify = self.verify_ssl
        self.base_url = f"{self.scheme}://{self.host}:{self.port}"

    @staticmethod
    def _get_env(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise RuntimeError(f"Environment variable '{name}' is required but missing.")
        return value

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}{path}"
        logger.debug("Calling Splunk API %s %s", method, url)
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:  # pragma: no cover - network failure.
            logger.exception("Error calling Splunk API: %s %s", method, url)
            error_message = f"Failed to communicate with Splunk API: {exc}"
            raise SplunkClientError(error_message) from exc

        if not response.ok:
            logger.error(
                "Splunk API error %s for %s %s: %s", response.status_code, method, url, response.text
            )
            raise SplunkClientError(
                f"Splunk API request failed with status {response.status_code}: {response.text}"
            )
        return response

    def run_query(self, spl_query: str, *, max_wait: int = 120, poll_interval: float = 2.0) -> List[Dict[str, Any]]:
        """Execute an SPL query and return the parsed results."""
        logger.info("Submitting Splunk search job")
        data = {
            "search": spl_query if spl_query.strip().startswith("search") else f"search {spl_query}",
            "exec_mode": "normal",
            "output_mode": "json",
        }
        response = self._request("POST", "/services/search/jobs", data=data)
        sid: Optional[str] = None
        if response.headers.get("Content-Type", "").startswith("application/json"):
            try:
                sid = response.json().get("sid")
            except ValueError:
                logger.warning("Failed to parse JSON response when creating search job")

        if not sid:
            # Fallback to parse XML when JSON is not available.
            try:
                sid = response.text.split("<sid>")[1].split("</sid>")[0]
            except Exception as exc:  # pragma: no cover - defensive.
                raise SplunkClientError("Unable to determine Splunk search job SID") from exc

        logger.debug("Splunk search job SID: %s", sid)

        # Poll for job completion
        job_path = f"/services/search/jobs/{sid}"
        start_time = time.time()
        while True:
            job_response = self._request(
                "GET",
                job_path,
                params={"output_mode": "json"},
            )
            try:
                job_payload = job_response.json()
            except ValueError as exc:
                raise SplunkClientError("Invalid JSON received from Splunk when polling job status") from exc
            entry = job_payload.get("entry", [{}])[0]
            content: Dict[str, Any] = entry.get("content", {})
            dispatch_state: Optional[str] = content.get("dispatchState")
            is_done = content.get("isDone")
            logger.debug("Job state: dispatch=%s done=%s", dispatch_state, is_done)

            if is_done or dispatch_state == "DONE":
                break

            if time.time() - start_time > max_wait:
                raise SplunkClientError("Splunk search job timed out")
            time.sleep(poll_interval)

        # Fetch results
        results_response = self._request(
            "GET",
            f"{job_path}/results",
            params={"output_mode": "json"},
        )
        try:
            results_payload = results_response.json()
        except ValueError as exc:
            raise SplunkClientError("Invalid JSON received from Splunk results endpoint") from exc
        results: List[Dict[str, Any]] = results_payload.get("results", [])
        logger.info("Retrieved %s results from Splunk", len(results))
        return results


__all__ = ["SplunkClient", "SplunkClientError"]
