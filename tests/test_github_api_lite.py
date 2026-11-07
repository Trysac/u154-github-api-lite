"""Test suite for github_api_lite."""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from github_api_lite import (
    GitHubClient,
    GitHubError,
    RateLimitedError,
    Response,
    parse_link_header,
)


class FakeTransport:
    """In-memory transport for testing GitHub API interactions."""

    def __init__(self, responses: list[Response] | None = None) -> None:
        self._responses = list(responses) if responses else []
        self.calls: list[tuple[str, Mapping[str, str]]] = []

    def add_response(self, response: Response) -> None:
        self._responses.append(response)

    def get(self, url: str, headers: Mapping[str, str]) -> Response:
        self.calls.append((url, headers))
        if not self._responses:
            raise AssertionError(f"Unexpected call to {url}: no response left")
        return self._responses.pop(0)


def test_acceptance_item_1_parse_link_header() -> None:
    header = (
        '<https://api.github.com/repositories/1/issues?page=2>; rel="next", '
        '<https://api.github.com/repositories/1/issues?page=5>; rel="last"'
    )
    expected = {
        "next": "https://api.github.com/repositories/1/issues?page=2",
        "last": "https://api.github.com/repositories/1/issues?page=5",
    }
    assert parse_link_header(header) == expected
    assert parse_link_header("") == {}
    assert parse_link_header("   ") == {}


def test_link_header_whitespace_and_rel_types() -> None:
    header = '<https://api.github.com/test?page=3>; rel="prev next"; title="previous and next"'
    res = parse_link_header(header)
    assert res == {
        "prev": "https://api.github.com/test?page=3",
        "next": "https://api.github.com/test?page=3",
    }

    # Missing rel or missing angle brackets
    assert parse_link_header('foo, bar; rel="next"') == {}
    assert parse_link_header('<https://api.github.com>; no_rel="test"') == {}


def test_link_header_length_limit() -> None:
    too_long = "a" * 8_193
    with pytest.raises(GitHubError) as exc_info:
        parse_link_header(too_long)
    assert exc_info.value.code == "invalid_header"


def test_acceptance_item_2_paginate() -> None:
    page1 = Response(
        200,
        {"Link": '<https://api.github.com/repos/o/r/issues?per_page=100&page=2>; rel="next"'},
        json.dumps([1, 2]).encode(),
    )
    page2 = Response(
        200,
        {"Link": '<https://api.github.com/repos/o/r/issues?per_page=100&page=3>; rel="next"'},
        json.dumps([3]).encode(),
    )
    page3 = Response(200, {}, json.dumps([4]).encode())

    transport = FakeTransport([page1, page2, page3])
    client = GitHubClient(transport)

    results = list(client.paginate("/repos/o/r/issues"))
    assert results == [1, 2, 3, 4]
    assert len(transport.calls) == 3
    assert transport.calls[0][0] == "https://api.github.com/repos/o/r/issues?per_page=100"

    # max_pages=2 yields [1, 2, 3]
    transport2 = FakeTransport(
        [
            Response(
                200,
                {
                    "Link": (
                        '<https://api.github.com/repos/o/r/issues?per_page=100&page=2>; rel="next"'
                    )
                },
                json.dumps([1, 2]).encode(),
            ),
            Response(
                200,
                {
                    "Link": (
                        '<https://api.github.com/repos/o/r/issues?per_page=100&page=3>; rel="next"'
                    )
                },
                json.dumps([3]).encode(),
            ),
            Response(200, {}, json.dumps([4]).encode()),
        ]
    )
    client2 = GitHubClient(transport2)
    res_max2 = list(client2.paginate("/repos/o/r/issues", max_pages=2))
    assert res_max2 == [1, 2, 3]
    assert len(transport2.calls) == 2


def test_acceptance_item_3_headers() -> None:
    transport = FakeTransport([Response(200, {}, b"{}")])
    client = GitHubClient(transport, token="test-token-123")  # noqa: S106
    client.get_json("/user")

    assert len(transport.calls) == 1
    headers = transport.calls[0][1]
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert headers["User-Agent"] == "github-api-lite"
    assert headers["Authorization"] == "Bearer test-token-123"


def test_acceptance_item_4_rate_limit_primary() -> None:
    slept: list[float] = []
    clock_val = 1000.0

    def fake_clock() -> float:
        return clock_val

    def fake_sleep(dur: float) -> None:
        slept.append(dur)

    # 403 with remaining 0, reset 1030 -> sleep 30.0 and retry success
    transport = FakeTransport(
        [
            Response(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1030"}, b"{}"),
            Response(200, {}, b'{"ok": true}'),
        ]
    )
    client = GitHubClient(transport, clock=fake_clock, sleep=fake_sleep, max_wait_s=60.0)
    res = client.get_json("/rate_limit")
    assert res == {"ok": True}
    assert slept == [30.0]
    assert len(transport.calls) == 2

    # Reset 1061 and max_wait_s 60 -> raises RateLimitedError with reset_at == 1061 without sleeping
    slept.clear()
    transport_exceeded = FakeTransport(
        [
            Response(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1061"}, b"{}"),
        ]
    )
    client_exceeded = GitHubClient(
        transport_exceeded, clock=fake_clock, sleep=fake_sleep, max_wait_s=60.0
    )
    with pytest.raises(RateLimitedError) as exc_info:
        client_exceeded.get_json("/rate_limit")

    assert exc_info.value.code == "rate_limited"
    assert exc_info.value.reset_at == 1061
    assert slept == []


def test_acceptance_item_5_retry_after_429() -> None:
    slept: list[float] = []

    # 429 with retry-after '7' calls sleep(7.0) and retries once, second 429 raises RateLimitedError
    transport = FakeTransport(
        [
            Response(429, {"retry-after": "7"}, b"{}"),
            Response(429, {"retry-after": "5"}, b"{}"),
        ]
    )
    client = GitHubClient(transport, sleep=slept.append)
    with pytest.raises(RateLimitedError) as exc_info:
        client.get_json("/search")
    assert exc_info.value.code == "rate_limited"
    assert slept == [7.0]
    assert len(transport.calls) == 2


def test_acceptance_item_6_foreign_link_and_404() -> None:
    transport = FakeTransport(
        [
            Response(
                200,
                {"link": '<https://evil.example/page2>; rel="next"'},
                json.dumps([{"id": 1}]).encode(),
            ),
        ]
    )
    client = GitHubClient(transport)
    paginator = client.paginate("/repos/o/r/issues")
    # First page yielded
    assert next(paginator) == {"id": 1}

    with pytest.raises(GitHubError) as exc_info:
        next(paginator)
    assert exc_info.value.code == "foreign_link"
    assert len(transport.calls) == 1

    # 404 with body {"message":"Not Found"}
    transport_404 = FakeTransport(
        [
            Response(404, {}, b'{"message":"Not Found"}'),
        ]
    )
    client_404 = GitHubClient(transport_404)
    with pytest.raises(GitHubError) as exc_info_404:
        client_404.get_json("/unknown")
    assert exc_info_404.value.code == "http_error"
    assert exc_info_404.value.status == 404
    assert exc_info_404.value.message == "Not Found"


def test_acceptance_item_7_safety_and_limits() -> None:
    token = "test-token-123"  # noqa: S105
    large_body = b"x" * 10_485_761
    transport = FakeTransport([Response(200, {}, large_body)])
    client = GitHubClient(transport, token=token)

    with pytest.raises(GitHubError) as exc_info:
        client.get_json("/data")
    assert exc_info.value.code == "response_too_large"

    # path 'https://x/y' raises code 'invalid_path'
    with pytest.raises(GitHubError) as exc_path:
        client.get_json("https://x/y")
    assert exc_path.value.code == "invalid_path"

    # Path without leading slash
    with pytest.raises(GitHubError) as exc_path2:
        client.get_json("repos/o/r")
    assert exc_path2.value.code == "invalid_path"

    # Neither str() of any raised error nor repr(client) contains 'test-token-123'
    assert token not in repr(client)
    assert token not in str(exc_info.value)
    assert token not in str(exc_path.value)


def test_edge_cases_and_error_handling() -> None:
    # 403 without rate limit headers raises http_error
    transport = FakeTransport([Response(403, {}, b'{"message": "Forbidden"}')])
    client = GitHubClient(transport)
    with pytest.raises(GitHubError) as exc_info:
        client.get_json("/secret")
    assert exc_info.value.code == "http_error"
    assert exc_info.value.status == 403
    assert exc_info.value.message == "Forbidden"

    # 429 without retry-after or x-ratelimit
    transport2 = FakeTransport([Response(429, {}, b"Too fast")])
    client2 = GitHubClient(transport2)
    with pytest.raises(RateLimitedError) as exc_rl:
        client2.get_json("/fast")
    assert exc_rl.value.code == "rate_limited"
    assert exc_rl.value.status == 429

    # Retry response too large
    large_body = b"a" * 100
    transport_large_retry = FakeTransport(
        [
            Response(429, {"retry-after": "1"}, b"{}"),
            Response(200, {}, large_body),
        ]
    )
    client_lr = GitHubClient(transport_large_retry, max_body_bytes=50, sleep=lambda _: None)
    with pytest.raises(GitHubError) as exc_lr:
        client_lr.get_json("/retry_large")
    assert exc_lr.value.code == "response_too_large"

    # Retry response non-429 error
    transport_err_retry = FakeTransport(
        [
            Response(429, {"retry-after": "1"}, b"{}"),
            Response(500, {}, b'{"message": "Internal Server Error"}'),
        ]
    )
    client_er = GitHubClient(transport_err_retry, sleep=lambda _: None)
    with pytest.raises(GitHubError) as exc_er:
        client_er.get_json("/retry_err")
    assert exc_er.value.code == "http_error"
    assert exc_er.value.status == 500
    assert exc_er.value.message == "Internal Server Error"

    # Non-array paginated response
    transport_non_array = FakeTransport([Response(200, {}, b'{"not": "array"}')])
    client_na = GitHubClient(transport_non_array)
    with pytest.raises(GitHubError) as exc_na:
        list(client_na.paginate("/repos/o/r/issues"))
    assert exc_na.value.code == "invalid_json"

    # Invalid JSON paginated response
    transport_bad_json = FakeTransport([Response(200, {}, b"not json at all")])
    client_bj = GitHubClient(transport_bad_json)
    with pytest.raises(GitHubError) as exc_bj:
        list(client_bj.paginate("/repos/o/r/issues"))
    assert exc_bj.value.code == "invalid_json"

    # Invalid JSON get_json response
    transport_bad_json2 = FakeTransport([Response(200, {}, b"not json")])
    client_bj2 = GitHubClient(transport_bad_json2)
    with pytest.raises(GitHubError) as exc_bj2:
        client_bj2.get_json("/user")
    assert exc_bj2.value.code == "invalid_json"

    # Query params appended to get_json and paginate in order
    transport_params = FakeTransport([Response(200, {}, b'{"status": "ok"}')])
    client_params = GitHubClient(transport_params)
    client_params.get_json("/search", {"q": "python", "sort": "stars"})
    assert transport_params.calls[0][0] == "https://api.github.com/search?q=python&sort=stars"

    # Paginate with custom params
    transport_pag_params = FakeTransport([Response(200, {}, b"[1]")])
    client_pag_params = GitHubClient(transport_pag_params)
    list(client_pag_params.paginate("/issues", {"state": "open"}))
    assert (
        transport_pag_params.calls[0][0] == "https://api.github.com/issues?per_page=100&state=open"
    )


def test_error_formatting_and_repr() -> None:
    err1 = GitHubError("http_error", status=400, message="Bad Request")
    assert str(err1) == "http_error (status 400): Bad Request"

    err2 = GitHubError("invalid_path")
    assert str(err2) == "invalid_path"

    client_no_token = GitHubClient(FakeTransport([]))
    assert "token=None" in repr(client_no_token)
