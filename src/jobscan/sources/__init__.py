"""Job sources. Each returns a list of Candidate objects and never raises past
the collector: one dead source must not kill the whole run."""

from .adzuna import fetch as adzuna_fetch
from .arbeitnow import fetch as arbeitnow_fetch
from .jsearch import fetch as jsearch_fetch
from .remotive import fetch as remotive_fetch

REGISTRY = {
    "remotive": remotive_fetch,
    "arbeitnow": arbeitnow_fetch,
    "adzuna": adzuna_fetch,
    "jsearch": jsearch_fetch,
}
