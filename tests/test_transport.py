import os
import httpx
import pytest

from akinator_core_test.game import GameError, UpstreamBlocked
from akinator_core_test.transport import BrowserTransport, HTTPTransport, Options, browser_proxy, check_response


@pytest.mark.parametrize("status", [403, 429, 503])
def test_upstream_blocking_statuses(status):
    with pytest.raises(UpstreamBlocked):
        check_response(status, "private upstream error")


@pytest.mark.parametrize("document", ["cf-chl-test", "challenge-platform", "<title>Just a moment...</title>"])
def test_challenge_page_is_not_accepted_as_a_game(document):
    with pytest.raises(UpstreamBlocked):
        check_response(200, document)


@pytest.mark.parametrize("url", ["file:///tmp/local", "https://user:secret@example.com", "invalid"])
def test_invalid_base_url(url):
    with pytest.raises(ValueError):
        Options(base_url=url)


async def test_http_transport_cookies_isolated_and_no_status_retry():
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(403, text="denied")
    transport = HTTPTransport(Options())
    await transport.client.aclose()
    transport.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with pytest.raises(UpstreamBlocked):
        await transport.start({"sid": "1", "cm": "true"})
    assert len(calls) == 1 and calls[0].url.path == "/game"
    await transport.close()
    assert transport.client.is_closed


def test_proxy_credentials_are_separated_and_hidden_from_options_repr():
    options = Options(proxy="http://user:private@127.0.0.1:8000")
    assert "private" not in repr(options)
    assert browser_proxy(options.proxy) == {"server": "http://127.0.0.1:8000", "username": "user", "password": "private"}


async def test_partial_browser_cleanup_is_local_and_idempotent():
    display_before = os.environ.get("DISPLAY")
    owned = []
    class Browser:
        async def close(self):
            owned.append("browser")
    class Playwright:
        async def stop(self):
            owned.append("playwright")
    transport = BrowserTransport(Options())
    transport.browser, transport.playwright = Browser(), Playwright()
    await transport.close()
    await transport.close()
    assert owned == ["browser", "playwright"]
    assert os.environ.get("DISPLAY") == display_before
