"""HTTP helpers, pacing, and proxy-safe error reporting."""
import asyncio
import os
import re
import time
from contextlib import asynccontextmanager

from curl_cffi.requests import AsyncSession
from .errors import RetailerError

_lock = asyncio.Lock()
_last_request = 0.0

@asynccontextmanager
async def paced():
    global _last_request
    async with _lock:
        await asyncio.sleep(max(0, 1.0 - (time.monotonic() - _last_request)))
        _last_request = time.monotonic()
        yield

def request_error(context, exc):
    detail = str(exc).lower()
    if "connect tunnel failed" in detail or "proxy authentication" in detail or re.search(r"curl: \(\s*(5|97)\)", detail):
        return RetailerError(f"{context}: proxy connection or authentication failed; check proxy settings.", code="proxy_error")
    return RetailerError(f"{context} ({type(exc).__name__}); check network and proxy settings.", code="network_error")


def validate_proxy_environment():
    if os.environ.get("APPLE_STORE_PROXY") or os.environ.get("APPLE_STORE_PROXY_FILE"):
        raise RetailerError(
            "APPLE_STORE_PROXY and APPLE_STORE_PROXY_FILE are not supported; configure HTTPS_PROXY.",
            code="invalid_input",
        )


def _session(*, timeout):
    validate_proxy_environment()
    return AsyncSession(impersonate="chrome", timeout=timeout)


DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.apple.com/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Upgrade-Insecure-Requests": "1",
}

async def fetch_text(url, *, timeout=20, headers=None, retries=2, session=None):
    merged = {**DEFAULT_HEADERS, **(headers or {})}
    last_status = None
    for attempt in range(retries + 1):
        async def request(active_session):
            async with paced():
                try:
                    return await active_session.get(url, headers=merged, allow_redirects=True)
                except Exception as exc:
                    raise request_error("Request failed", exc) from exc
        if session is None:
            async with _session(timeout=timeout) as active_session:
                response = await request(active_session)
        else:
            response = await request(session)
        last_status = response.status_code
        if response.status_code in (429, 500, 502, 503, 504, 541) and attempt < retries:
            await asyncio.sleep(3 * (attempt + 1))
            continue
        break
    if last_status == 429:
        raise RetailerError(f"Request returned HTTP {last_status}.", code="rate_limited")
    if last_status == 541:
        raise RetailerError("Apple rejected the request (HTTP 541).", code="blocked")
    if last_status == 404:
        raise RetailerError("Request returned HTTP 404.", code="not_found")
    if last_status == 403:
        raise RetailerError("Request was blocked (HTTP 403).", code="blocked")
    if last_status >= 500:
        raise RetailerError(f"Request returned HTTP {last_status}.", code="upstream_error")
    if last_status != 200:
        raise RetailerError(f"Request returned HTTP {last_status}.")
    return response.text, str(response.url)
