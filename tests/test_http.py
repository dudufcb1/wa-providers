from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import Any

import httpx
import pytest

from wa_providers import ProviderAPIError, ProviderTransportError
from wa_providers.http import PooledHTTPClient

TransportHandler = Callable[[httpx.Request], httpx.Response]


async def _client_with_mock_transport(
    handler: TransportHandler,
    *,
    max_retries: int = 3,
    backoff_base: float = 0,
    backoff_max: float = 0,
) -> PooledHTTPClient:
    client = PooledHTTPClient(
        base_url="https://provider.example.test",
        max_retries=max_retries,
        backoff_base=backoff_base,
        backoff_max=backoff_max,
    )
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://provider.example.test",
        transport=httpx.MockTransport(handler),
    )
    return client


@pytest.mark.asyncio
async def test_post_does_not_retry_retryable_status_by_default() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "temporarily unavailable"})

    client = await _client_with_mock_transport(handler)
    try:
        with pytest.raises(ProviderTransportError) as error:
            await client.request("POST", "/messages", json={"text": "Hola"})

        assert calls == 1
        assert error.value.status_code == 503
        assert error.value.body == {"error": "temporarily unavailable"}
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_post_does_not_retry_timeout_by_default() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("provider timeout", request=request)

    client = await _client_with_mock_transport(handler)
    try:
        with pytest.raises(ProviderTransportError, match="provider timeout"):
            await client.request("POST", "/messages", json={"text": "Hola"})

        assert calls == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_get_retries_transient_failure_by_default() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "temporarily unavailable"})
        return httpx.Response(200, json={"health_status": "GREEN"})

    client = await _client_with_mock_transport(handler, max_retries=1)
    try:
        response = await client.request("GET", "/phone-number-id")

        assert calls == 2
        assert response == {"health_status": "GREEN"}
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_retry_true_allows_post_retry() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "temporarily unavailable"})
        return httpx.Response(200, json={"message_id": "accepted-after-retry"})

    client = await _client_with_mock_transport(handler, max_retries=1)
    try:
        response = await client.request(
            "POST",
            "/safe-operation",
            retry=True,
            json={"operation_id": "operation-1"},
        )

        assert calls == 2
        assert response == {"message_id": "accepted-after-retry"}
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_retry_false_disables_get_retry() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "temporarily unavailable"})

    client = await _client_with_mock_transport(handler)
    try:
        with pytest.raises(ProviderTransportError):
            await client.request("GET", "/health", retry=False)

        assert calls == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_unexpected_redirect_is_not_returned_as_binary_success() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"Location": "https://other.example.test/media"},
        )

    client = await _client_with_mock_transport(handler)
    try:
        with pytest.raises(ProviderTransportError, match="redirect") as error:
            await client.request_bytes("GET", "/media")

        assert error.value.status_code == 302
    finally:
        await client.aclose()


@pytest.mark.parametrize("max_retries", [0, 1, 3])
@pytest.mark.asyncio
async def test_max_retries_produces_exact_number_of_attempts(max_retries: int) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "temporarily unavailable"})

    client = await _client_with_mock_transport(handler, max_retries=max_retries)
    try:
        with pytest.raises(ProviderTransportError):
            await client.request("GET", "/health")

        assert calls == max_retries + 1
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "invalid_config",
    [
        {"max_retries": -1},
        {"backoff_base": -0.1},
        {"backoff_max": -0.1},
        {"backoff_base": float("inf")},
        {"backoff_base": float("-inf")},
        {"backoff_base": float("nan")},
        {"backoff_max": float("inf")},
        {"backoff_max": float("-inf")},
        {"backoff_max": float("nan")},
    ],
)
def test_invalid_retry_configuration_is_rejected(
    invalid_config: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: object())

    with pytest.raises(ValueError):
        PooledHTTPClient(
            base_url="https://provider.example.test",
            **invalid_config,
        )


@pytest.mark.asyncio
async def test_retry_after_numeric_controls_retry_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    sleep_delays: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                503,
                headers={"Retry-After": "2.5"},
                json={"error": "temporarily unavailable"},
            )
        return httpx.Response(200, json={"health_status": "GREEN"})

    async def record_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    client = await _client_with_mock_transport(
        handler,
        max_retries=1,
        backoff_max=10,
    )
    try:
        response = await client.request("GET", "/health")

        assert response == {"health_status": "GREEN"}
        assert calls == 2
        assert sleep_delays == [2.5]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_retry_after_http_date_is_capped_to_backoff_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    sleep_delays: list[float] = []
    retry_at = datetime.now(timezone.utc) + timedelta(hours=1)

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                503,
                headers={"Retry-After": format_datetime(retry_at, usegmt=True)},
                json={"error": "temporarily unavailable"},
            )
        return httpx.Response(200, json={"health_status": "GREEN"})

    async def record_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    client = await _client_with_mock_transport(
        handler,
        max_retries=1,
        backoff_max=1.25,
    )
    try:
        response = await client.request("GET", "/health")

        assert response == {"health_status": "GREEN"}
        assert calls == 2
        assert sleep_delays == [1.25]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_exponential_jitter_never_exceeds_backoff_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        sleep_delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    monkeypatch.setattr(random, "uniform", lambda _low, high: high)
    client = PooledHTTPClient(
        base_url="https://provider.example.test",
        backoff_base=4,
        backoff_max=4,
    )
    try:
        await client._sleep_backoff(attempt=10)

        assert sleep_delays == [4]
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "error_type",
    [httpx.LocalProtocolError, httpx.UnsupportedProtocol],
    ids=["local-protocol-error", "unsupported-protocol"],
)
@pytest.mark.asyncio
async def test_local_request_errors_are_not_retried_or_wrapped(
    error_type: type[httpx.TransportError],
) -> None:
    calls = 0
    raised_errors: list[httpx.TransportError] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        error = error_type("invalid local request", request=request)
        raised_errors.append(error)
        raise error

    client = await _client_with_mock_transport(handler, max_retries=3)
    try:
        with pytest.raises(error_type) as caught:
            await client.request("GET", "/health")

        assert calls == 1
        assert caught.value is raised_errors[0]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_context_manager_closes_underlying_client() -> None:
    client = PooledHTTPClient(base_url="https://provider.example.test")
    underlying_client = client._client

    async with client as entered_client:
        assert entered_client is client
        assert underlying_client.is_closed is False

    assert underlying_client.is_closed is True


@pytest.mark.asyncio
async def test_request_bytes_returns_content_and_headers_after_safe_get_retry() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "temporarily unavailable"})
        return httpx.Response(
            200,
            content=b"binary-content",
            headers={"content-type": "application/octet-stream", "x-media-id": "media-1"},
        )

    client = await _client_with_mock_transport(handler, max_retries=1)
    try:
        response = await client.request_bytes("GET", "/media")

        assert calls == 2
        assert response.content == b"binary-content"
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["x-media-id"] == "media-1"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_request_bytes_post_does_not_retry_by_default() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "temporarily unavailable"})

    client = await _client_with_mock_transport(handler, max_retries=3)
    try:
        with pytest.raises(ProviderTransportError):
            await client.request_bytes("POST", "/media")

        assert calls == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_request_bytes_preserves_api_error_details() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "media not found"})

    client = await _client_with_mock_transport(handler)
    try:
        with pytest.raises(ProviderAPIError) as error:
            await client.request_bytes("GET", "/missing-media")

        assert error.value.status_code == 404
        assert error.value.body == {"error": "media not found"}
    finally:
        await client.aclose()
