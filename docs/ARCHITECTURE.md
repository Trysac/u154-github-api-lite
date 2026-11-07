# Architecture

## Overview

`github-api-lite` provides a zero-dependency client for GitHub's REST API designed for high testability and security.

## Core Concepts

### 1. Injected Transport Protocol
The `GitHubClient` performs no network I/O. It consumes a `Transport` protocol:

```python
class Transport(Protocol):
    def get(self, url: str, headers: Mapping[str, str]) -> Response: ...
```

This decouples the library from specific HTTP stacks like `urllib`, `requests`, or `httpx`.

### 2. RFC 8288 Link Header Pagination
The `paginate()` method consumes `Link` headers, extracting `next` targets. To prevent token leakage, pagination traverses only to URLs matching the base URL's scheme, host, and port (verified by `_is_same_origin`).

### 3. Rate Limit Recovery
The client handles `403` and `429` status codes by analyzing `Retry-After` or `x-ratelimit-reset` headers. If the calculated wait time is within `max_wait_s` (default 60s), the client blocks using the injected `sleep` callback before attempting a single retry. Exceeding this limit or failing on retry raises `RateLimitedError`.
