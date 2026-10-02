"""Step 3: validate the AI's decisions. Fails closed.

Nothing is delivered unless every check here passes.
"""

import argparse
import json
import sys
from pathlib import Path

from .blacklist import Blacklist
from .cv import catalog
from .config import ConfigError, data_root, load_authorization, load_config, recipient_problems
from .models import CONFIDENCE, DISPOSITION, Decision
from .normalize import is_http_url


def validate(candidates: dict, decisions: list, auth: dict,
             blacklist: Blacklist | None = None, cfg: dict | None = None,
             cvs: dict[str, set] | None = None) -> tuple[list, list]:
    """``cvs`` maps profile id -> CV variant ids the AI may choose from."""
    problems, ok = [], []
    cand_by_key = {c["candidate_key"]: c for c in candidates["candidates"]}
    seen_keys = set()

    for raw in decisions:
        key = raw.get("candidate_key")
        if key not in cand_by_key:
            problems.append(f"decision for unknown candidate: {key}")
            continue
        if key in seen_keys:
            problems.append(f"duplicate decision for {key}")
            continue
        seen_keys.add(key)

        missing = [f for f in Decision.required_fields() if raw.get(f) in (None, "")]
        if missing:
            problems.append(f"{key}: missing fields {missing}")
            continue
        if not isinstance(raw["fit"], int) or not 0 <= raw["fit"] <= 100:
            problems.append(f"{key}: fit must be an int 0-100, got {raw['fit']!r}")
            continue
        if raw["confidence"] not in CONFIDENCE:
            problems.append(f"{key}: bad confidence {raw['confidence']!r}")
            continue
        if raw["disposition"] not in DISPOSITION:
            problems.append(f"{key}: bad disposition {raw['disposition']!r}")
            continue
        if raw["disposition"] == "email":
            if raw["confidence"] == "low":
                problems.append(f"{key}: low confidence cannot be dispositioned 'email'")
                continue
            if not is_http_url(cand_by_key[key].get("url", "")):
                problems.append(f"{key}: emailable match has no valid http(s) link")
                continue
        if cvs is not None:
            options = cvs.get(cand_by_key[key].get("profile"), set())
            chosen = raw.get("cv") or ""
            if chosen and chosen not in options:
                problems.append(f"{key}: unknown cv {chosen!r} (choose from {sorted(options) or 'none'})")
                continue
            if raw["disposition"] == "email" and options and not chosen:
                problems.append(f"{key}: emailable match has no cv chosen")
                continue
        if blacklist and raw["disposition"] != "discarded":
            hit = blacklist.match(cand_by_key[key])
            if hit:
                problems.append(f"{key}: company is blacklisted ({hit}) but was not discarded")
                continue
        ok.append(raw)

    undecided = set(cand_by_key) - seen_keys
    if undecided:
        problems.append(f"{len(undecided)} candidate(s) received no decision")

    if not auth.get("active"):
        problems.append("authorization.yaml: active is not true")
    if cfg is not None:
        problems += recipient_problems(cfg)

    return ok, problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate AI decisions (dry run gate).")
    ap.add_argument("--data")
    ap.add_argument("--candidates", default="candidates.json")
    ap.add_argument("--decisions", default="decisions.json")
    args = ap.parse_args(argv)

    try:
        root = data_root(args.data)
        auth = load_authorization(root)
        cfg = load_config(root)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    candidates = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    decisions = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
    if isinstance(decisions, dict):
        decisions = decisions.get("decisions", [])

    cvs = {p["id"]: set(catalog(root, p)) for p in cfg["profiles"]}
    ok, problems = validate(candidates, decisions, auth, Blacklist.from_config(cfg), cfg, cvs)
    if problems:
        print("VALIDATION FAILED — nothing will be delivered:", file=sys.stderr)
        for p in problems:
            print(f"  ! {p}", file=sys.stderr)
        return 1

    emailed = sum(1 for d in ok if d["disposition"] == "email")
    pending = sum(1 for d in ok if d["disposition"] == "low-confidence")
    print(f"validation ok — {len(ok)} decisions, {emailed} to email, {pending} to verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
