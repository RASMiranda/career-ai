"""Greenhouse job references: the board slug, the job id and which host (US or EU) carries the posting.

Greenhouse runs two job-board hosts. A posting's form lives on the host it was published on, so a
reference keeps the host and rebuilds the form URL from it. Only https URLs of the form
``/<slug>/jobs/<id>`` on those two hosts are accepted; anything else raises ValueError.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

HOSTS = {"us": "job-boards.greenhouse.io", "eu": "job-boards.eu.greenhouse.io"}
_BY_NETLOC = {host: name for name, host in HOSTS.items()}
_SLUG = re.compile(r"[A-Za-z0-9_-]+")
_PATH = re.compile(r"/(?P<slug>[^/]+)/jobs/(?P<job_id>[0-9]+)/?")


@dataclass(frozen=True)
class GreenhouseRef:
    slug: str
    job_id: str
    host: str                      # "us" | "eu"

    def __post_init__(self):
        if not self.slug or not _SLUG.fullmatch(self.slug):
            raise ValueError(f"bad Greenhouse board slug: {self.slug!r}")
        if self.host not in HOSTS:
            raise ValueError(f"Greenhouse host must be one of {sorted(HOSTS)}, got {self.host!r}")
        if not re.fullmatch(r"[0-9]+", self.job_id or ""):
            raise ValueError(f"bad Greenhouse job id: {self.job_id!r}")

    def form_url(self) -> str:
        """The application page for this posting, on the host it was published on."""
        return f"https://{HOSTS[self.host]}/{self.slug}/jobs/{self.job_id}"


def parse(url: str) -> GreenhouseRef:
    """Read a Greenhouse job URL. Raises ValueError for anything that is not one."""
    try:
        parts = urlparse(url or "")
    except ValueError as exc:
        raise ValueError(f"not a Greenhouse job URL: {url!r}") from exc
    if parts.scheme != "https" or parts.netloc.lower() not in _BY_NETLOC:   # no port, no userinfo
        raise ValueError(f"not a Greenhouse job URL: {url!r}")
    match = _PATH.fullmatch(parts.path)
    if match is None:
        raise ValueError(f"not a Greenhouse job URL: {url!r}")
    return GreenhouseRef(match["slug"], match["job_id"], _BY_NETLOC[parts.netloc.lower()])
