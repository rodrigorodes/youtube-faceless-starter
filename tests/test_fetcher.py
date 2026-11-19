import socket
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))

from app.studio.adapters.fetcher import HttpxFetcher  # noqa: E402
from app.studio.application.editorial import SourceRefused, SourceUnavailable  # noqa: E402

ALLOW = ("amsterdam-dance-event.nl",)
HTML = "<html><head><style>.x{}</style><script>alert('x')</script></head><body><h1>ADE 2026</h1><p>3,600 artists</p><noscript>no</noscript></body></html>"


def ip(addr):
    return lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, port))]


PUBLIC = ip("93.184.216.34")


def make(handler, resolver=PUBLIC, max_bytes=2_000_000, allowlist=ALLOW):
    calls = []

    def wrapped(request):
        calls.append(str(request.url))
        return handler(request)

    fetcher = HttpxFetcher(allowlist, max_bytes=max_bytes, resolver=resolver, transport=httpx.MockTransport(wrapped))
    return fetcher, calls


def ok(request):
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=HTML.encode())


def test_html_becomes_text_without_script_and_style():
    fetcher, _ = make(ok)
    page = fetcher.fetch("https://amsterdam-dance-event.nl/en/x")
    assert "ADE 2026" in page.text and "3,600 artists" in page.text
    assert "alert" not in page.text and ".x{}" not in page.text and "no" not in page.text.split()
    assert page.final_url == "https://amsterdam-dance-event.nl/en/x"


def test_plain_text_is_accepted():
    fetcher, _ = make(lambda r: httpx.Response(200, headers={"content-type": "text/plain"}, content="hello 30 years".encode()))
    assert fetcher.fetch("https://amsterdam-dance-event.nl/a").text == "hello 30 years"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://amsterdam-dance-event.nl/", "https://evil.example/x",
                                 "https://amsterdam-dance-event.nl@evil.example/", "https://evil-amsterdam-dance-event.nl/"])
def test_bad_urls_are_refused_without_any_request(url):
    fetcher, calls = make(ok)
    with pytest.raises(SourceRefused):
        fetcher.fetch(url)
    assert calls == []


@pytest.mark.parametrize("addr", ["10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.1", "172.16.0.9", "::1", "fe80::1", "0.0.0.0", "100.64.0.1"])
def test_hosts_resolving_to_private_addresses_are_refused(addr):
    fetcher, calls = make(ok, resolver=ip(addr))
    with pytest.raises(SourceRefused, match="private"):
        fetcher.fetch("https://amsterdam-dance-event.nl/x")
    assert calls == []


def test_any_private_answer_among_many_refuses():
    mixed = lambda h, p: [(socket.AF_INET, 1, 6, "", ("93.184.216.34", p)), (socket.AF_INET, 1, 6, "", ("10.0.0.1", p))]
    fetcher, _ = make(ok, resolver=mixed)
    with pytest.raises(SourceRefused):
        fetcher.fetch("https://amsterdam-dance-event.nl/x")


def test_redirect_inside_allowlist_is_followed_and_final_url_reported():
    def handler(request):
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return ok(request)

    fetcher, calls = make(handler)
    page = fetcher.fetch("https://amsterdam-dance-event.nl/old")
    assert page.final_url == "https://amsterdam-dance-event.nl/new" and len(calls) == 2


def test_redirect_outside_allowlist_is_refused_before_following():
    fetcher, calls = make(lambda r: httpx.Response(302, headers={"location": "https://evil.example/steal"}))
    with pytest.raises(SourceRefused):
        fetcher.fetch("https://amsterdam-dance-event.nl/x")
    assert calls == ["https://amsterdam-dance-event.nl/x"]


def test_redirect_to_allowlisted_host_that_resolves_private_is_refused():
    def resolver(host, port):
        return ip("10.0.0.1" if host.startswith("www.") else "93.184.216.34")(host, port)

    fetcher, calls = make(lambda r: httpx.Response(302, headers={"location": "https://www.amsterdam-dance-event.nl/x"}), resolver=resolver)
    with pytest.raises(SourceRefused, match="private"):
        fetcher.fetch("https://amsterdam-dance-event.nl/x")
    assert len(calls) == 1


def test_more_than_three_redirects_refused():
    fetcher, calls = make(lambda r: httpx.Response(302, headers={"location": "/again"}))
    with pytest.raises(SourceRefused, match="redirect"):
        fetcher.fetch("https://amsterdam-dance-event.nl/x")
    assert len(calls) == 4  # a original + 3 redirects


@pytest.mark.parametrize("ctype", ["image/png", "application/pdf", "application/octet-stream", ""])
def test_non_text_content_is_refused(ctype):
    fetcher, _ = make(lambda r: httpx.Response(200, headers={"content-type": ctype}, content=b"\x89PNG"))
    with pytest.raises(SourceRefused, match="content"):
        fetcher.fetch("https://amsterdam-dance-event.nl/x")


def test_body_is_cut_at_max_bytes():
    fetcher, _ = make(lambda r: httpx.Response(200, headers={"content-type": "text/plain"}, content=b"abcd " * 100_000), max_bytes=100)
    assert len(fetcher.fetch("https://amsterdam-dance-event.nl/x").text) <= 100


def test_http_error_and_network_failure_are_unavailable_not_refused():
    fetcher, _ = make(lambda r: httpx.Response(404))
    with pytest.raises(SourceUnavailable):
        fetcher.fetch("https://amsterdam-dance-event.nl/x")

    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(SourceUnavailable):
        make(boom)[0].fetch("https://amsterdam-dance-event.nl/x")

    def dns_fail(host, port):
        raise socket.gaierror("nope")

    with pytest.raises(SourceUnavailable):
        make(ok, resolver=dns_fail)[0].fetch("https://amsterdam-dance-event.nl/x")


def test_empty_page_is_refused():
    fetcher, _ = make(lambda r: httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html><script>x</script></html>"))
    with pytest.raises(SourceRefused, match="empty"):
        fetcher.fetch("https://amsterdam-dance-event.nl/x")


def test_ipv4_mapped_ipv6_private_is_refused():
    fetcher, calls = make(ok, resolver=ip("::ffff:10.0.0.1"))
    with pytest.raises(SourceRefused, match="private"):
        fetcher.fetch("https://amsterdam-dance-event.nl/x")
    assert calls == []


@pytest.mark.parametrize("url", ["https://amsterdam-dance-event.nl:abc/x", "https://amsterdam-dance-event.nl:99999/x", "https://amsterdam-dance-event.nl:22/x"])
def test_invalid_or_unusual_ports_are_refused_not_500(url):
    fetcher, calls = make(ok)
    with pytest.raises(SourceRefused):
        fetcher.fetch(url)
    assert calls == []


@pytest.mark.parametrize("charset", ["idna", "punycode", "undefined", "nao-existe"])
def test_weird_charset_falls_back_to_utf8(charset):
    fetcher, _ = make(lambda r: httpx.Response(200, headers={"content-type": f"text/plain; charset={charset}"}, content="ADE 30 anos".encode()))
    assert fetcher.fetch("https://amsterdam-dance-event.nl/x").text == "ADE 30 anos"


def test_https_to_http_downgrade_is_refused():
    fetcher, calls = make(lambda r: httpx.Response(302, headers={"location": "http://amsterdam-dance-event.nl/x"}))
    with pytest.raises(SourceRefused, match="downgrade"):
        fetcher.fetch("https://amsterdam-dance-event.nl/x")
    assert len(calls) == 1


def test_redirect_without_location_is_unavailable():
    fetcher, _ = make(lambda r: httpx.Response(302))
    with pytest.raises(SourceUnavailable):
        fetcher.fetch("https://amsterdam-dance-event.nl/x")


def test_reading_stops_early_instead_of_loading_everything():
    read = []

    def stream():
        for _ in range(1000):
            read.append(1)
            yield b"abcd " * 100

    fetcher, _ = make(lambda r: httpx.Response(200, headers={"content-type": "text/plain"}, content=stream()), max_bytes=1000)
    assert len(fetcher.fetch("https://amsterdam-dance-event.nl/x").text) <= 1000
    assert len(read) < 50


def test_proxy_environment_is_ignored(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    fetcher, calls = make(ok)
    assert fetcher.fetch("https://amsterdam-dance-event.nl/x").text and len(calls) == 1
