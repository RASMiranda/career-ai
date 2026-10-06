"""Check that each keyed source works: one tiny real request per source.

    python -m jobscan.doctor --data ../career-data

Run it in a session of the environment the routine uses (a session started AFTER
the keys were saved). It spends one request of each source's monthly quota,
prints only statuses, never a key, and exits 1 if any source fails.
See docs/API-KEYS.md for where the keys come from and how they are set.
"""

import argparse
import sys

from .collect import proxied_sources
from .config import ConfigError, data_root, load_config, secret
from .sources._http import probe_json

HOW = {
    401: "the key was rejected",
    403: "the key was rejected, or the plan is not subscribed, or (proxy) the credential does not match",
    404: "unexpected 404 (wrong path or country)",
    429: "quota or rate limit reached",
}


def _redact(text: str, secrets: list[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text[:200]


def _verdict(name: str, status, payload, error: str, field: str,
             secrets: list[str] = ()) -> tuple[bool, str]:
    detail = _redact(error, list(secrets))
    if status == 200 and isinstance(payload, dict) and isinstance(payload.get(field), list):
        return True, f"OK, HTTP 200, {len(payload[field])} result(s) returned"
    if status is None:
        return False, (f"cannot reach the host ({detail}): add it under Network access → "
                       "Allowed domains in the environment settings")
    reason = HOW.get(status, "unexpected response")
    return False, f"FAILED, HTTP {status}: {reason}" + (f" [provider said: {detail}]" if detail else "")


def check_adzuna() -> tuple[bool, str]:
    app_id, app_key = secret("ADZUNA_APP_ID"), secret("ADZUNA_APP_KEY")
    missing = [n for n, v in (("ADZUNA_APP_ID", app_id), ("ADZUNA_APP_KEY", app_key)) if not v]
    if missing:
        return False, f"NOT SET: {', '.join(missing)} (environment variables; sessions started before they were saved do not have them)"
    status, payload, error = probe_json(
        "https://api.adzuna.com/v1/api/jobs/gb/search/1",
        {"app_id": app_id, "app_key": app_key, "what": "java", "results_per_page": 1,
         "content-type": "application/json"})
    return _verdict("adzuna", status, payload, error, "results", [app_id, app_key])


def check_jsearch(via_proxy: bool) -> tuple[bool, str]:
    key = secret("RAPIDAPI_KEY")
    if not key and not via_proxy:
        return False, "NOT SET: RAPIDAPI_KEY, and config.yaml does not set auth: proxy for jsearch"
    headers = {"X-RapidAPI-Host": "jsearch.p.rapidapi.com", **({"X-RapidAPI-Key": key} if key else {})}
    status, payload, error = probe_json(
        "https://jsearch.p.rapidapi.com/search",
        {"query": "java", "page": "1", "num_pages": "1", "date_posted": "week"}, headers=headers)
    ok, msg = _verdict("jsearch", status, payload, error, "data", [key])
    mode = "key from the environment" if key else "key added by the credential proxy"
    return ok, f"{msg} [{mode}]"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data")
    args = ap.parse_args(argv)
    try:
        cfg = load_config(data_root(args.data))
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    results = {"adzuna": check_adzuna(), "jsearch": check_jsearch("jsearch" in proxied_sources(cfg))}
    for name, (ok, msg) in results.items():
        print(f"{name:8} {msg}")
    return 0 if all(ok for ok, _ in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
