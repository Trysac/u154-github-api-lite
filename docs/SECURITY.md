# Security Model

## Threat Model

### Defended

1. **Credential Exposure**: Authorization tokens are never included in exception messages or `repr()` output. The client explicitly masks these as `'***'` in `__repr__`.
2. **SSRF / Token Leakage**: Pagination follows `Link` headers only when the destination matches the base URL's scheme, host, and port. Requests to foreign domains are rejected with `foreign_link`.
3. **Denial of Service**: The client enforces strict limits:
   - `Link` headers > 8,192 bytes are rejected.
   - Responses > 10,485,760 bytes are rejected (`response_too_large`).
   - Wait time for rate limits is capped at 60 seconds.

### Not Defended

- **Transport Security**: TLS/SSL verification and network-level security are delegated entirely to the user-provided `Transport` implementation.
- **Write Endpoint Vulnerabilities**: The client is limited to GET requests and does not address risks associated with mutating API methods.
