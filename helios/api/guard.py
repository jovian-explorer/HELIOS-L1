"""
Request guard for the local HELIOS-L1 server.

The server listens on 127.0.0.1 at a predictable port, so any web page open in the
user's browser can send requests to it. CORS only stops such a page from reading the
answer; the request itself still runs. The guard therefore rejects, before routing:

* requests whose Host header is not a loopback name (DNS rebinding: a site whose name
  resolves to 127.0.0.1 is "same-origin" with the server in the browser's view);
* /api requests that a browser marks as coming from another site (Sec-Fetch-Site other
  than same-origin or none) or that carry an Origin other than the server's own;
* state-changing /api requests (POST, PUT, PATCH, DELETE) without a JSON Content-Type,
  which no cross-site page can send without a CORS preflight;
* request bodies larger than the endpoint's limit (Content-Length or streamed size).

Requests without these headers (scripts, curl, the test client) pass: they are not a
browser acting on behalf of another site.
"""
import json
from typing import Dict, Optional, Tuple

LOOPBACK_HOSTNAMES = ("127.0.0.1", "localhost", "[::1]", "::1")
UNSAFE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
ALLOWED_FETCH_SITES = ("same-origin", "none")


def _split_host(host: str) -> str:
    """Host header without the port ('[::1]:8765' -> '[::1]', '127.0.0.1:8765' -> '127.0.0.1')."""
    host = host.strip().lower()
    if host.startswith("["):
        return host[:host.find("]") + 1] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def is_loopback_host(host: Optional[str]) -> bool:
    return bool(host) and _split_host(host) in LOOPBACK_HOSTNAMES


class LocalRequestGuard:
    """ASGI middleware applying the rules in the module docstring."""

    def __init__(self, app, body_limits: Dict[str, int], default_body_limit: int):
        self.app = app
        self.body_limits = body_limits
        self.default_body_limit = default_body_limit

    def _body_limit(self, path: str) -> int:
        return self.body_limits.get(path, self.default_body_limit)

    @staticmethod
    def _headers(scope) -> Dict[str, str]:
        return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}

    def check(self, method: str, path: str, headers: Dict[str, str]) -> Optional[Tuple[int, str]]:
        """(status, reason) for a request to reject, None to let it through."""
        host = headers.get("host", "")
        if not is_loopback_host(host):
            return 403, "HELIOS-L1 only answers requests addressed to 127.0.0.1 or localhost."
        if not path.startswith("/api"):
            return None
        site = headers.get("sec-fetch-site")
        if site is not None and site.lower() not in ALLOWED_FETCH_SITES:
            return 403, "Cross-site requests to the HELIOS-L1 API are not accepted."
        origin = headers.get("origin")
        if origin is not None and origin.rstrip("/").lower() not in (f"http://{host}".lower(), f"https://{host}".lower()):
            return 403, "Requests from other origins are not accepted by the HELIOS-L1 API."
        if method in UNSAFE_METHODS:
            ctype = headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return 415, "State-changing requests must send Content-Type: application/json."
            length = headers.get("content-length")
            if length is not None:
                try:
                    too_big = int(length) > self._body_limit(path)
                except ValueError:
                    return 400, "Invalid Content-Length header."
                if too_big:
                    return 413, self._too_large(path)
        return None

    def _too_large(self, path: str) -> str:
        return f"Request body too large (limit {self._body_limit(path) / 1e6:g} MB)."

    @staticmethod
    async def _reject(send, status: int, reason: str) -> None:
        body = json.dumps({"detail": reason}).encode("utf-8")
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method, path = scope.get("method", "GET").upper(), scope.get("path", "")
        refusal = self.check(method, path, self._headers(scope))
        if refusal:
            return await self._reject(send, *refusal)
        if method not in UNSAFE_METHODS:
            return await self.app(scope, receive, send)

        # Read the body here, up to the limit, and hand it on: a chunked body has no
        # Content-Length to check up front. (FastAPI buffers request bodies anyway.)
        limit, chunks, size = self._body_limit(path), [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                return await self._reject(send, 413, self._too_large(path))
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body, delivered = b"".join(chunks), False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)
