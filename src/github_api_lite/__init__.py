"""Minimal GitHub REST client over an injected transport."""

from __future__ import annotations

import contextlib
import json
import logging
import re
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urlencode, urlparse

__all__ = [
    "ErrorCode",
    "GitHubClient",
    "GitHubError",
    "RateLimitedError",
    "Response",
    "Transport",
    "__version__",
    "parse_link_header",
]

__version__ = "0.1.0"

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

ErrorCode = Literal[
    "invalid_path",
    "invalid_header",
    "foreign_link",
    "http_error",
    "rate_limited",
    "response_too_large",
    "invalid_json",
]

MAX_LINK_HEADER_LEN = 8_192
MAX_ERROR_MESSAGE_LEN = 200
DEFAULT_MAX_BODY_BYTES = 10_485_760
DEFAULT_MAX_WAIT_S = 60.0
DEFAULT_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
USER_AGENT = "github-api-lite"


class GitHubError(Exception):
    """Base exception raised by github-api-lite."""

    def __init__(
        self,
        code: ErrorCode,
        status: int | None = None,
        message: str | None = None,
    ) -> None:
        super().__init__(message or code)
        self.code: ErrorCode = code
        self.status: int | None = status
        self.message: str | None = message

    def __str__(self) -> str:
        base = f"{self.code}"
        if self.status is not None:
            base += f" (status {self.status})"
        if self.message:
            base += f": {self.message}"
        return base


class RateLimitedError(GitHubError):
    """Raised when a rate limit cannot be waited out or persists after retry."""

    def __init__(
        self,
        status: int | None = None,
        message: str | None = None,
        *,
        reset_at: int | None = None,
    ) -> None:
        super().__init__(code="rate_limited", status=status, message=message)
        self.reset_at: int | None = reset_at


@dataclass(frozen=True)
class Response:
    """HTTP response returned by a Transport."""

    status: int
    headers: Mapping[str, str]
    body: bytes

    def __post_init__(self) -> None:
        # Ensure header keys are stored lowercase
        lowered = {k.lower(): v for k, v in self.headers.items()}
        object.__setattr__(self, "headers", lowered)


class Transport(Protocol):
    """Protocol for low-level HTTP transport."""

    def get(self, url: str, headers: Mapping[str, str]) -> Response:
        """Send a GET request to the given url with the provided headers."""
        ...


_PARAM_RE = re.compile(r'([a-zA-Z*_-]+)\\s*=\\s*(?:"([^"]*)"|([^;]*))')


def parse_link_header(value: str) -> dict[str, str]:
    """Parse an RFC 8288 Link header value into a rel -> target mapping.

    Raises:
        GitHubError: with code 'invalid_header' if value exceeds 8,192 characters.
    """
    if len(value) > MAX_LINK_HEADER_LEN:
        raise GitHubError("invalid_header", message="Link header exceeds maximum length limit")

    if not value.strip():
        return {}

    # Split top-level entries by commas outside angle brackets <...>
    entries: list[str] = []
    inside_angle = False
    curr: list[str] = []
    for char in value:
        if char == "<":
            inside_angle = True
            curr.append(char)
        elif char == ">":
            inside_angle = False
            curr.append(char)
        elif char == "," and not inside_angle:
            entry = "".join(curr).strip()
            if entry:
                entries.append(entry)
            curr = []
        else:
            curr.append(char)

    last_entry = "".join(curr).strip()
    if last_entry:
        entries.append(last_entry)

    links: dict[str, str] = {}
    for entry in entries:
        # Must contain target URI inside <...>
        start = entry.find("<")
        end = entry.find(">")
        if start == -1 or end == -1 or start >= end:
            continue

        target = entry[start + 1 : end].strip()
        params_str = entry[end + 1 :]
        if not params_str:
            continue

        # Parse parameters
        param_parts = [p.strip() for p in params_str.split(";") if p.strip()]
        rel_val: str | None = None
        for part in param_parts:
            if "=" not in part:
                continue
            name, val = part.split("=", 1)
            name = name.strip().lower()
            val = val.strip()
            if val.startswith('"') and val.endswith('"') and len(val) >= 2:
                val = val[1:-1]
            if name == "rel":
                rel_val = val
                break

        if rel_val:
            # rel may list several space-separated types, each mapped
            for rel in rel_val.split():
                links[rel] = target

    return links


def _is_same_origin(url: str, base_url: str) -> bool:
    u = urlparse(url)
    b = urlparse(base_url)
    u_port = u.port or (443 if u.scheme == "https" else 80 if u.scheme == "http" else None)
    b_port = b.port or (443 if b.scheme == "https" else 80 if b.scheme == "http" else None)
    return (
        u.scheme.lower() == b.scheme.lower()
        and (u.hostname or "").lower() == (b.hostname or "").lower()
        and u_port == b_port
    )


class GitHubClient:
    """Lightweight GitHub REST API client."""

    def __init__(
        self,
        transport: Transport,
        *,
        token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        max_wait_s: float = DEFAULT_MAX_WAIT_S,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        self._transport = transport
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._clock = clock
        self._sleep = sleep
        self._max_wait_s = max_wait_s
        self._max_body_bytes = max_body_bytes

    def __repr__(self) -> str:
        masked_token = "'***'" if self._token is not None else "None"
        return (
            f"GitHubClient(base_url={self._base_url!r}, token={masked_token}, "
            f"max_wait_s={self._max_wait_s}, max_body_bytes={self._max_body_bytes})"
        )

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": USER_AGENT,
        }
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _validate_path(self, path: str) -> None:
        if not path.startswith("/") or "://" in path:
            raise GitHubError("invalid_path", message=f"Invalid API path: {path[:50]}")

    def _send_request(self, url: str) -> Response:
        headers = self._build_headers()
        resp = self._transport.get(url, headers)

        if len(resp.body) > self._max_body_bytes:
            raise GitHubError(
                "response_too_large",
                status=resp.status,
                message=f"Response body size {len(resp.body)} exceeds limit {self._max_body_bytes}",
            )

        if resp.status < 400:
            return resp

        # Handle 403 / 429 rate limits
        if resp.status in (403, 429):
            wait_time, reset_at = self._extract_wait_time(resp)
            if wait_time is not None:
                if 0.0 <= wait_time <= self._max_wait_s:
                    self._sleep(wait_time)
                    # One retry
                    retry_resp = self._transport.get(url, headers)
                    if len(retry_resp.body) > self._max_body_bytes:
                        raise GitHubError(
                            "response_too_large",
                            status=retry_resp.status,
                            message=(
                                f"Response body size {len(retry_resp.body)} "
                                f"exceeds limit {self._max_body_bytes}"
                            ),
                        )
                    if retry_resp.status < 400:
                        return retry_resp
                    if retry_resp.status in (403, 429):
                        _, retry_reset_at = self._extract_wait_time(retry_resp)
                        raise RateLimitedError(
                            status=retry_resp.status,
                            message="Rate limit exceeded on retry",
                            reset_at=retry_reset_at if retry_reset_at is not None else reset_at,
                        )
                    self._raise_http_error(retry_resp)
                else:
                    raise RateLimitedError(
                        status=resp.status,
                        message=f"Wait time {wait_time:.1f}s exceeds max_wait_s {self._max_wait_s}",
                        reset_at=reset_at,
                    )
            elif resp.status == 429:
                raise RateLimitedError(status=429, message="Too Many Requests", reset_at=reset_at)
            else:
                # 403 without rate limit headers
                self._raise_http_error(resp)

        self._raise_http_error(resp)
        return resp

    def _extract_wait_time(self, resp: Response) -> tuple[float | None, int | None]:
        headers = resp.headers
        retry_after = headers.get("retry-after")
        if retry_after is not None:
            try:
                wait = float(retry_after.strip())
                return wait, None
            except ValueError:
                pass

        remaining = headers.get("x-ratelimit-remaining")
        reset_str = headers.get("x-ratelimit-reset")
        if remaining == "0" and reset_str is not None:
            try:
                reset_epoch = int(reset_str.strip())
                wait = reset_epoch - self._clock()
                return wait, reset_epoch
            except ValueError:
                pass

        reset_epoch_fallback: int | None = None
        if reset_str is not None:
            with contextlib.suppress(ValueError):
                reset_epoch_fallback = int(reset_str.strip())

        return None, reset_epoch_fallback

    def _raise_http_error(self, resp: Response) -> None:
        msg: str | None = None
        try:
            payload = json.loads(resp.body.decode("utf-8"))
            if isinstance(payload, dict) and "message" in payload:
                msg = str(payload["message"])[:MAX_ERROR_MESSAGE_LEN]
        except Exception:
            msg = None
        raise GitHubError("http_error", status=resp.status, message=msg)

    def get_json(self, path: str, params: Mapping[str, str] | None = None) -> Any:
        """Perform a GET request to path with optional query params and return parsed JSON."""
        self._validate_path(path)
        url = f"{self._base_url}{path}"
        if params:
            query_str = urlencode(params)
            if query_str:
                url = f"{url}?{query_str}"

        resp = self._send_request(url)
        try:
            return json.loads(resp.body.decode("utf-8"))
        except Exception as exc:
            raise GitHubError(
                "invalid_json", status=resp.status, message="Invalid JSON response"
            ) from exc

    def paginate(
        self,
        path: str,
        params: Mapping[str, str] | None = None,
        *,
        max_pages: int = 10,
        per_page: int = 100,
    ) -> Iterator[Any]:
        """Paginate through items returned across multiple pages."""
        self._validate_path(path)

        # Build initial query params
        query_items: list[tuple[str, str]] = [("per_page", str(per_page))]
        if params:
            for k, v in params.items():
                query_items.append((k, str(v)))
        query_str = urlencode(query_items)
        next_url: str | None = f"{self._base_url}{path}?{query_str}"

        pages_fetched = 0
        while next_url and pages_fetched < max_pages:
            # Validate origin
            if not _is_same_origin(next_url, self._base_url):
                raise GitHubError(
                    "foreign_link",
                    message=f"Next page URL {next_url[:50]} does not match base origin",
                )

            resp = self._send_request(next_url)
            pages_fetched += 1

            try:
                data = json.loads(resp.body.decode("utf-8"))
            except Exception as exc:
                raise GitHubError(
                    "invalid_json", status=resp.status, message="Invalid JSON in paginated response"
                ) from exc

            if not isinstance(data, list):
                raise GitHubError(
                    "invalid_json",
                    status=resp.status,
                    message="Expected a JSON array for paginated response",
                )

            yield from data

            if pages_fetched >= max_pages:
                break

            link_header = resp.headers.get("link")
            if link_header:
                links = parse_link_header(link_header)
                next_url = links.get("next")
            else:
                next_url = None
