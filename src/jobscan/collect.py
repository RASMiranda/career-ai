"""Step 1: collect, normalise, dedupe. No AI, no email, no credentials logged.

Writes candidates.json — the only job data the model ever sees.
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from .config import ConfigError, data_root, load_config, secret
from .blacklist import Blacklist
from .cv import catalog
from .normalize import is_http_url
from .sources import REGISTRY
from .state import Budget, Seen

SECRET_NAMES = ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "RAPIDAPI_KEY")


def proxied_sources(cfg: dict) -> set[str]:
    """Sources whose credential the environment's proxy adds to the request
    (`auth: proxy` in config.yaml → sources), so no key is in the shell."""
    return {name for name, meta in (cfg.get("sources") or {}).items()
            if isinstance(meta, dict) and meta.get("auth") == "proxy"}


def preflight(root: Path, cfg: dict) -> list[str]:
    """Report readiness without ever printing a secret value."""
    report = []
    proxied = proxied_sources(cfg)
    for name in SECRET_NAMES:
        if name == "RAPIDAPI_KEY" and "jsearch" in proxied and not secret(name):
            report.append(f"  {name}: added by the credential proxy (not checked here)")
        else:
            report.append(f"  {name}: {'ok' if secret(name) else 'missing'}")
    for profile in cfg["profiles"]:
        criteria = root / profile["criteria"]
        report.append(f"  criteria[{profile['id']}]: {'ok' if criteria.is_file() else 'MISSING'}")
    (root / "state").mkdir(exist_ok=True)
    return report


def queries_for(profile: dict, today: date) -> list[dict]:
    qs = list(profile.get("daily_queries") or [])
    if today.weekday() == profile.get("weekly_day", 0):
        qs += list(profile.get("weekly_queries") or [])
    return qs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Collect and dedupe job candidates.")
    ap.add_argument("--data", help="path to the private data repo")
    ap.add_argument("--out", default="candidates.json")
    ap.add_argument("--preflight-only", action="store_true")
    args = ap.parse_args(argv)

    try:
        root = data_root(args.data)
        cfg = load_config(root)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    print("preflight:")
    for line in preflight(root, cfg):
        print(line)
    if args.preflight_only:
        return 0

    secrets = {name: secret(name) for name in SECRET_NAMES}
    secrets["_proxy"] = proxied_sources(cfg)
    seen = Seen(root)
    budget = Budget(root, cfg.get("budgets", {}))
    today = date.today()

    collected, skipped_seen, errors = {}, 0, []
    blocked: dict[str, int] = {}
    for profile in cfg["profiles"]:
        blacklist = Blacklist.from_config(cfg, profile["id"])
        for query in queries_for(profile, today):
            source = query["source"]
            fetch = REGISTRY.get(source)
            if not fetch:
                errors.append(f"unknown source: {source}")
                continue
            if budget.remaining(source) <= 0:
                errors.append(f"{source}: monthly budget exhausted, skipped")
                continue
            try:
                results = fetch(query, profile["id"], secrets)
            except Exception as exc:  # a broken source degrades, never aborts
                errors.append(f"{source}: {type(exc).__name__}")
                continue
            budget.spend(source)
            for cand in results:
                if cand.candidate_key in seen:
                    skipped_seen += 1
                    continue
                if not is_http_url(cand.url):
                    continue
                hit = blacklist.match(cand.to_dict())
                if hit:  # not added to seen: removing the entry later brings the job back
                    blocked[hit] = blocked.get(hit, 0) + 1
                    continue
                collected.setdefault(cand.candidate_key, cand)  # cross-source dedupe

    payload = {
        "generated_on": today.isoformat(),
        "counts": {"new": len(collected), "already_seen": skipped_seen,
                   "blacklisted": sum(blocked.values())},
        "blocked_by": blocked,
        "errors": errors,
        "candidates": [c.to_dict() for c in collected.values()],
        # CV variants per profile: the AI picks one per match from profiles/<id>/cv/<variant>.md
        "cv_variants": {p["id"]: sorted(catalog(root, p)) for p in cfg["profiles"]},
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    budget.save()

    print(f"\nnew: {len(collected)}  already seen: {skipped_seen}  "
          f"blacklisted: {sum(blocked.values())}  errors: {len(errors)}")
    for name, n in sorted(blocked.items()):
        print(f"  - blocked {n} from {name}")
    for err in errors:
        print(f"  ! {err}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
