# github-api-lite

[![CI](https://github.com/Trysac/u154-github-api-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u154-github-api-lite/actions/workflows/ci.yml)

A minimal, zero-dependency GitHub REST client over an injected transport featuring standard RFC 8288 Link header pagination, primary and secondary rate limit handling, and origin-enforced page traversal.

## Installation

```bash
pip install trysac-github-api-lite
```

## Usage

```python
from github_api_lite import GitHubClient, Response


class SimpleTransport:
    def get(self, url: str, headers: dict[str, str]) -> Response:
        # Integrate your HTTP library (e.g. urllib or requests)
        return Response(200, {}, b"[]")


client = GitHubClient(SimpleTransport(), token="ghp_sample")
for issue in client.paginate("/repos/owner/repo/issues"):
    print(issue)
```

## Public API Summary

- `GitHubClient(transport, token, base_url, clock, sleep, max_wait_s, max_body_bytes)`: The primary interface. Requires a `Transport` protocol implementation.
- `get_json(path, params)`: Performs a GET request and returns parsed JSON.
- `paginate(path, params, max_pages, per_page)`: Returns an iterator over paginated results.
- `parse_link_header(value)`: Parses RFC 8288 headers into a `rel -> target` dictionary.

### Errors & Limits
- **Error Codes**: `invalid_path`, `invalid_header`, `foreign_link`, `http_error`, `rate_limited`, `response_too_large`, `invalid_json`.
- **Limits**: `Link` headers must be < 8,192 bytes; responses must be < 10,485,760 bytes; wait time for rate limits capped at 60s.

## Why not PyGithub?

PyGithub provides a full object-model wrapper for the GitHub API which requires dependencies. `github-api-lite` is designed for use-cases requiring zero dependencies, direct control over the HTTP transport, and strict adherence to GitHub pagination and rate-limit specs.

## Security
See [docs/SECURITY.md](docs/SECURITY.md) for the threat model and safety guarantees.
