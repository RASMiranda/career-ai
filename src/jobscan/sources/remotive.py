"""Remotive: remote-first board, public JSON API, no key."""

from ..models import Candidate
from ..normalize import candidate_key, truncate
from ._http import get_json

API = "https://remotive.com/api/remote-jobs"


def fetch(query: dict, profile: str, _secrets=None) -> list[Candidate]:
    payload = get_json(API, {"search": query["query"], "limit": query.get("limit", 40)})
    if not payload:
        return []
    out = []
    for job in payload.get("jobs", []):
        title, company = job.get("title", ""), job.get("company_name", "")
        if not title or not company:
            continue
        out.append(Candidate(
            candidate_key=candidate_key("remotive", str(job.get("id", "")), title, company),
            profile=profile, source="remotive", title=title, company=company,
            location=job.get("candidate_required_location", ""), remote=True,
            contract_type=job.get("job_type", ""), salary=job.get("salary", ""),
            description=truncate(job.get("description", "")),
            url=job.get("url", ""), posted_at=job.get("publication_date", ""),
            source_id=str(job.get("id", "")),
        ))
    return out
