# Project Record

## Objective

Implement a lightweight, standard-library-only GitHub REST client with reliable pagination and rate-limit handling.

## Scope

- `GitHubClient` class with `get_json` and `paginate` methods.
- `parse_link_header` utility for RFC 8288 compliance.
- Transport injection for I/O decoupling.
- Token protection: masking in representation and logs.
- Rate limit compliance for primary and secondary limits (403/429).
- Origin enforcement for pagination links.

## Out-of-Scope

- GraphQL API support.
- Helper methods for write-heavy endpoints (POST/PATCH/DELETE).
- Conditional requests (ETags).
- GitHub App authentication flows.
- Retries for HTTP 5xx errors.

## Factory run u154 (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | gemini-3.8-flash | yes | 4207 | 10176 | 0 | 0 | 0.0207 |
| fix-1 | gemini-3.1-flash-lite | no | 31444 | 981 | 0 | 73247 | 0.0112 |
| audit | gemini-3.1-flash-lite | no | 47886 | 209 | 0 | 103724 | 0.0149 |
| docs | gemini-3.1-flash-lite | no | 187210 | 1900 | 0 | 0 | 0.0497 |

Total: $0.0964. Prices: Anthropic list prices.
