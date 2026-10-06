import json
import urllib.error
import urllib.parse
import urllib.request

UA = "career-ai-jobscan/0.1 (+https://github.com/RASMiranda)"


def _transient(exc: Exception) -> bool:
    """Worth one more try: a timeout or a 5xx. A 401/403/404/429 will not change on retry."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500
    return isinstance(getattr(exc, "reason", exc), TimeoutError)


def get_json(url: str, params: dict | None = None, headers: dict | None = None,
             timeout: int = 20, retries: int = 0) -> dict | list | None:
    """JSON from url, or None on any failure. `retries` extra tries, only after a transient failure."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, OSError) as exc:
            if attempt == retries or not _transient(exc):
                return None


def probe_json(url: str, params: dict | None = None, headers: dict | None = None,
               timeout: int = 20) -> tuple[int | None, object, str]:
    """Like get_json but says what went wrong: (HTTP status or None, payload, error class)."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            try:
                return resp.status, json.loads(resp.read().decode("utf-8", "replace")), ""
            except json.JSONDecodeError:
                return resp.status, None, "JSONDecodeError"
    except urllib.error.HTTPError as exc:
        try:
            body = " ".join(exc.read(300).decode("utf-8", "replace").split())
        except Exception:
            body = ""
        return exc.code, None, f"HTTPError: {body}" if body else "HTTPError"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", None) or exc
        return None, None, f"{type(exc).__name__}: {reason}"
