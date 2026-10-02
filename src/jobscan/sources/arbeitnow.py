"""Arbeitnow: EU-heavy board, public JSON API, no key."""

from ..models import Candidate
from ..normalize import candidate_key, norm_text, truncate
from ._http import get_json

API = "https://www.arbeitnow.com/api/job-board-api"


def fetch(query: dict, profile: str, _secrets=None) -> list[Candidate]:
    payload = get_json(API)
    if not payload:
        return []
    terms = [t for t in norm_text(query["query"]).split() if len(t) > 2]
    out = []
    for job in payload.get("data", []):
        title, company = job.get("title", ""), job.get("company_name", "")
        haystack = norm_text(f"{title} {company} {' '.join(job.get('tags') or [])}")
        if terms and not any(t in haystack for t in terms):
            continue
        out.append(Candidate(
            candidate_key=candidate_key("arbeitnow", job.get("slug", ""), title, company),
            profile=profile, source="arbeitnow", title=title, company=company,
            location=job.get("location", ""), remote=bool(job.get("remote")),
            description=truncate(job.get("description", "")),
            url=job.get("url", ""), posted_at=str(job.get("created_at", "")),
            source_id=job.get("slug", ""),
        ))
    return out
