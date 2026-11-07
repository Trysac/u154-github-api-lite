# Protocol-based Transport and Origin-Guarded Pagination for GitHub REST Client

Status: accepted (generated, pending human review)

## Context

Calling GitHub's REST API requires robust Link header pagination, rate limit handling (both primary quota and secondary concurrency limits), and protection against credential leaks. Standardizing on an injected Transport protocol allows users to employ their HTTP library of choice without imposing dependencies.

## Decision

Implement GitHubClient using an injected Transport protocol, deterministic clock/sleep callables, and a strict RFC 8288 Link header parser. Enforce same-origin checks comparing scheme, hostname, and port before following pagination links, and mask tokens in repr and error representations.

## Consequences

Zero external dependencies are introduced. Applications can easily test GitHub integration logic with in-memory mock transports. Pagination guarantees that tokens are never dispatched to foreign hosts.
