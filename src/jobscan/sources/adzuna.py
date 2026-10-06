"""Adzuna: country-scoped job API. Free developer tier; needs app id + key."""

from ..models import Candidate
from ..normalize import candidate_key, truncate
from ._http import get_json


def fetch(query: dict, profile: str, secrets: dict) -> list[Candidate]:
    app_id, app_key = secrets.get("ADZUNA_APP_ID"), secrets.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []
    country = query.get("country", "gb")
    payload = get_json(
        f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
        {
            "app_id": app_id, "app_key": app_key,
            "what": query["query"], "results_per_page": query.get("limit", 30),
            "max_days_old": query.get("max_days_old", 7),
            "content-type": "application/json",
        },
    )
    if payload is None:   # collect records the error and spends no budget
        raise ConnectionError("no usable response (key rejected, quota, or host blocked)")
    out = []
    for job in payload.get("results", []):
        company = (job.get("company") or {}).get("display_name", "")
        title = job.get("title", "")
        salary = ""
        if job.get("salary_min"):
            salary = f"{job.get('salary_min')}-{job.get('salary_max')} {job.get('currency','')}".strip()
        out.append(Candidate(
            candidate_key=candidate_key("adzuna", str(job.get("id", "")), title, company),
            profile=profile, source="adzuna", title=title, company=company,
            location=(job.get("location") or {}).get("display_name", ""),
            contract_type=job.get("contract_type", ""), salary=salary,
            description=truncate(job.get("description", "")),
            url=job.get("redirect_url", ""), posted_at=job.get("created", ""),
            source_id=str(job.get("id", "")),
        ))
    return out
