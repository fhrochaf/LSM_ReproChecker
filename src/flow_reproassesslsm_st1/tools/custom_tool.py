import re
from typing import Any

from bs4 import BeautifulSoup
from crewai.tools import BaseTool
from crewai_tools.security.safe_requests import safe_get
from pydantic import BaseModel, Field
from requests.exceptions import RequestException


class PublicationAvailabilityToolSchema(BaseModel):
    """Input for PublicationAvailabilityTool."""

    url: str = Field(..., description="The publication or DOI URL to check.")


class PublicationAvailabilityTool(BaseTool):
    """Fetches a publication page exactly once and reports whether it is reachable.

    Makes a single request and returns a
    final, structured result even on failure (blocked, timed out, 404, ...).
    """

    name: str = "Check publication availability"
    description: str = (
        "Fetches the given publication URL exactly once and returns its "
        "cleaned text content, or a clear NOT_ACCESSIBLE result if the page "
        "could not be reached. This result is final: do not call this tool "
        "again with a different URL variant (e.g. /pdf, /htm) or search "
        "elsewhere for the same publication."
    )
    args_schema: type[BaseModel] = PublicationAvailabilityToolSchema
    headers: dict[str, str] = Field(
        default_factory=lambda: {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    max_chars: int = Field(default=8000)

    def _run(self, **kwargs: Any) -> str:
        url: str | None = kwargs.get("url")
        if not url:
            raise ValueError("A publication URL must be provided.")

        try:
            response = safe_get(url, timeout=15, headers=self.headers)
        except (RequestException, ValueError) as exc:
            return (
                f"NOT_ACCESSIBLE: request to {url} failed "
                f"({exc.__class__.__name__}: {exc}).\n"
                "This is the final result for this publication — do not retry "
                "with alternate URLs or other sources."
            )

        if response.status_code != 200:
            return (
                f"NOT_ACCESSIBLE: {url} returned HTTP {response.status_code} "
                f"(final URL after redirects: {response.url}).\n"
            )

        response.encoding = response.apparent_encoding
        parsed = BeautifulSoup(response.text, "html.parser")
        text = parsed.get_text(" ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s*\n\s*", "\n", text).strip()

        if len(text) > self.max_chars:
            text = text[: self.max_chars] + "\n...[truncated]"

        return (
            f"ACCESSIBLE: {url} returned HTTP 200 "
            f"(final URL after redirects: {response.url}).\n\n{text}"
        )


def publication_availability_tool() -> PublicationAvailabilityTool:
    return PublicationAvailabilityTool()
