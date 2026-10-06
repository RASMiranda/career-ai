"""JSearch via RapidAPI: broad aggregation, monthly quota. Budget-tracked."""

from ..models import Candidate
from ..normalize import candidate_key, truncate
from ._http import get_json

HOST = "jsearch.p.rapidapi.com"
ENDPOINTS = tuple(f"https://{HOST}{p}" for p in ("/search-v2", "/search"))


def jobs_of(payload: dict) -> list:
    """/search-v2 nests the list as data.jobs; the older /search returned data as a list."""
    data = payload.get("data")
    if isinstance(data, dict):
        data = data.get("jobs")
    return data if isinstance(data, list) else []


def fetch(query: dict, profile: str, secrets: dict) -> list[Candidate]:
    key = secrets.get("RAPIDAPI_KEY")
    if not key and "jsearch" not in secrets.get("_proxy", ()):
        return []
    # With `auth: proxy` the environment adds X-RapidAPI-Key itself; never send our own.
    headers = {"X-RapidAPI-Host": HOST, **({"X-RapidAPI-Key": key} if key else {})}
    params = {"query": query["query"], "page": "1",
              "num_pages": "1", "date_posted": query.get("date_posted", "week")}
    payload = None
    for api in ENDPOINTS:
        payload = get_json(api, params, headers=headers)
        if payload is not None:
            break
    if payload is None:   # collect records the error and spends no budget
        raise ConnectionError("no usable response (key rejected, quota, or host blocked)")
    out = []
    for job in jobs_of(payload):
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
