"""JSearch via RapidAPI: broad aggregation, monthly quota. Budget-tracked."""

from ..models import Candidate
from ..normalize import candidate_key, truncate
from ._http import get_json

API = "https://jsearch.p.rapidapi.com/search"


def fetch(query: dict, profile: str, secrets: dict) -> list[Candidate]:
    key = secrets.get("RAPIDAPI_KEY")
    if not key:
        return []
    payload = get_json(
        API,
        {"query": query["query"], "page": "1",
         "num_pages": "1", "date_posted": query.get("date_posted", "week")},
        headers={"X-RapidAPI-Key": key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
    )
    if not payload:
        return []
    out = []
    for job in payload.get("data", []):
        title, company = job.get("job_title", ""), job.get("employer_name", "")
        loc = ", ".join(x for x in (job.get("job_city"), job.get("job_country")) if x)
        out.append(Candidate(
            candidate_key=candidate_key("jsearch", job.get("job_id", ""), title, company),
            profile=profile, source="jsearch", title=title, company=company,
            location=loc, remote=job.get("job_is_remote"),
            contract_type=job.get("job_employment_type", ""),
            description=truncate(job.get("job_description", "")),
            url=job.get("job_apply_link", ""),
            posted_at=str(job.get("job_posted_at_datetime_utc", "")),
            source_id=job.get("job_id", ""),
        ))
    return out
