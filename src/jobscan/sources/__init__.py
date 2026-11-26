"""Job sources. Each returns a list of Candidate objects and never raises past
the collector: one dead source must not kill the whole run."""

from .adzuna import fetch as adzuna_fetch
from .arbeitnow import fetch as arbeitnow_fetch
from .jsearch import fetch as jsearch_fetch
from .remotive import fetch as remotive_fetch
from .workingnomads import fetch as workingnomads_fetch

REGISTRY = {
    "remotive": remotive_fetch,
    "workingnomads": workingnomads_fetch,
    "arbeitnow": arbeitnow_fetch,
    "adzuna": adzuna_fetch,
    "jsearch": jsearch_fetch,
}

# Manifests (ARCHITECTURE §2b, ADR-008, ADR-080). Declared for the sources listed here only;
# arbeitnow, adzuna and jsearch have none yet, so the gate below does not cover them.
# ``terms_reviewed`` is "<date> <link>" once the owner's terms review is recorded. A manifest
# with it unset is registered but never run.
MANIFEST_FIELDS = ("access_method", "terms_reviewed", "rate_limit", "redistribution_allowed", "params")
MANIFESTS = {
    "remotive": {
        "access_method": "public_api",
        "terms_reviewed": "2026-11-26 https://remotive.com/remote-jobs/api",
        "rate_limit": "not stated in the API terms; one request per query per run, no key",
        # The terms ask that listings are not put on third-party sites and that the source is named
        # and linked. The owner's email is the only place a listing goes.
        "redistribution_allowed": False,
        "params": {"query": "string, sent as search", "limit": "integer, default 40"},
    },
    "workingnomads": {
        "access_method": "public_api",
        "terms_reviewed": None,  # owner to paste the terms; see ADR-080
        "rate_limit": "one fetch of the whole feed per run, filtered locally",
        "redistribution_allowed": False,  # conservative until the terms are read
        "params": {"query": "string, case-insensitive substring of title, tags and description"},
    },
}


def manifest_gaps(name: str) -> list[str]:
    """Manifest fields missing for a declared source (an undeclared source has no manifest to check)."""
    manifest = MANIFESTS.get(name)
    if manifest is None:
        return []
    return [f for f in MANIFEST_FIELDS if f not in manifest]


def blocked_reason(name: str) -> str | None:
    """Why the collector must not run this source, or None. A declared source whose terms are not
    reviewed is blocked (ADR-080); an undeclared one is not checked here."""
    manifest = MANIFESTS.get(name)
    if manifest is not None and not manifest.get("terms_reviewed"):
        return "terms not reviewed (ADR-080): not run"
    return None
