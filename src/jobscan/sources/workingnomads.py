"""Working Nomads: remote-job board with a public JSON feed, no key (ADR-080).

The feed is one JSON array of exposed jobs. It is fetched once per process and
filtered locally, so several queries in one run cost one request. The terms are
not reviewed yet: the manifest in ``sources/__init__.py`` leaves ``terms_reviewed``
unset, so ``collect`` does not run this adapter until the owner records the review.
"""

from ..models import Candidate
from ..normalize import candidate_key, truncate
from ._http import get_json

API = "https://www.workingnomads.com/api/exposed_jobs/"

_UNFETCHED = object()
_feed_cache = _UNFETCHED  # the parsed feed, or None when the fetch failed


def reset_cache() -> None:
    """Forget the feed so the next query fetches it again (tests, and a new run in one process)."""
    global _feed_cache
    _feed_cache = _UNFETCHED


def _feed() -> list:
    global _feed_cache
    if _feed_cache is _UNFETCHED:
        payload = get_json(API)
        _feed_cache = payload if isinstance(payload, list) else None
    if _feed_cache is None:
        raise ConnectionError("no usable response from the Working Nomads feed")
    return _feed_cache


def fetch(query: dict, profile: str, _secrets=None) -> list[Candidate]:
    """Jobs whose title, tags or description contain the query text (case-insensitive substring)."""
    needle = (query.get("query") or "").casefold().strip()
    out = []
    for job in _feed():
        if not isinstance(job, dict):
            continue
        title, company = job.get("title") or "", job.get("company_name") or ""
        description, tags = job.get("description") or "", job.get("tags") or ""
        if not title or not company:
            continue
        haystack = f"{title}\n{tags}\n{description}".casefold()
        if needle and needle not in haystack:
            continue
        url = job.get("url") or ""
        out.append(Candidate(
            candidate_key=candidate_key("workingnomads", url, title, company),
            profile=profile, source="workingnomads", title=title, company=company,
            location=job.get("location") or "", remote=True,
            description=truncate(description), url=url,
            posted_at=job.get("pub_date") or "", source_id=url,
        ))
    return out
