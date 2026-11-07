# Testing Strategy

## Test Implementation

Tests are located in `tests/test_github_api_lite.py`. They use a custom `FakeTransport` class to inject deterministic HTTP responses and mock the system clock/sleep functions. No network calls are made.

## Coverage

- **Pagination**: Validating next-page link extraction, `max_pages` limits, and `per_page` query arguments.
- **Rate Limiting**: Verifying `403` and `429` retry logic based on `Retry-After` and `x-ratelimit-*` headers.
- **Security**: Verifying `foreign_link` blocks for cross-origin URLs, ensuring tokens are masked in `repr()`, and checking input limits.
- **Validation**: Testing path validation, JSON response types, and body size limits.
