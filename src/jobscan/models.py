"""Shared data shapes. Kept as plain dicts at the boundaries so the JSON the
AI step writes is the same shape the validator reads."""

from dataclasses import dataclass, asdict, field
from typing import Optional

CONFIDENCE = ("high", "medium", "low")
DISPOSITION = ("email", "low-confidence", "discarded")


@dataclass
class Candidate:
    candidate_key: str
    profile: str
    source: str
    title: str
    company: str
    location: str = ""
    remote: Optional[bool] = None
    contract_type: str = ""
    salary: str = ""
    description: str = ""
    url: str = ""
    posted_at: str = ""
    source_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Decision:
    """One decision per candidate. Produced by the AI step."""
    candidate_key: str
    fit: int
    tier: str
    confidence: str
    disposition: str
    why: str
    caution: str = ""
    next_action: str = ""
    cv: str = ""            # CV variant id from the profile's catalog (see jobscan.cv)

    @staticmethod
    def required_fields() -> tuple:
        return ("candidate_key", "fit", "tier", "confidence", "disposition", "why")
