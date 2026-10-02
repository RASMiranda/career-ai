import json
import urllib.error
import urllib.parse
import urllib.request

UA = "career-ai-jobscan/0.1 (+https://github.com/RASMiranda)"


def get_json(url: str, params: dict | None = None, headers: dict | None = None,
             timeout: int = 20) -> dict | list | None:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            json.JSONDecodeError, OSError):
        return None
