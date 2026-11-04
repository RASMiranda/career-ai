"""What the owner has switched on for submission, read from authorization.yaml (ADR-042).

Every rule here fails closed: a missing key, a non-date, or a value that is not exactly what the rule asks
for means "off". The model never reads this file's decisions; code does.

    application_submission:
      master_switch: false          # must be true, with acknowledged_on, before any auto submit
      acknowledged_on: "YYYY-MM-DD"
      site_allow_list: [...]        # optional; narrows the adapters the config allows
      adapters:
        linkedin_easy_apply:
          mode: manual              # manual | assisted | auto
          enabled: false            # must be true for auto
          cooldown_days: 7
          caps: {per_day: 2, per_week: 5, per_company_days: 30}
    linkedin_tos_acknowledgement:
      acknowledged_on: "YYYY-MM-DD" # the owner's own dated statement; code never writes it
"""

from datetime import date

from ..config import ConfigError

MODES = ("manual", "assisted", "auto")
LINKEDIN = "linkedin_easy_apply"
LINKEDIN_CAPS = {"per_day": 2, "per_week": 5, "per_company_days": 30}   # conservative defaults (ADR-042)
LINKEDIN_COOLDOWN_DAYS = 7


def _dated(value) -> bool:
    try:
        date.fromisoformat(str(value or ""))
        return True
    except ValueError:
        return False


def submission(auth: dict) -> dict:
    return dict(auth.get("application_submission") or {})


def master_switch_on(auth: dict) -> bool:
    sub = submission(auth)
    return sub.get("master_switch") is True and _dated(sub.get("acknowledged_on"))


def adapter_cfg(auth: dict, name: str) -> dict:
    return dict((submission(auth).get("adapters") or {}).get(name) or {})


def adapter_mode(auth: dict, name: str) -> str:
    mode = adapter_cfg(auth, name).get("mode", "manual")
    if mode not in MODES:
        raise ConfigError(f"authorization.yaml: adapters.{name}.mode must be manual, assisted or auto")
    return mode


def linkedin_may_auto(auth: dict) -> tuple[bool, list[str]]:
    """Auto submit on LinkedIn Easy Apply needs all four: master switch, the adapter's enabled flag and
    mode auto, and a dated owner acknowledgement. Returns the reasons it may not, for the run log."""
    reasons = []
    if not master_switch_on(auth):
        reasons.append("master_switch is off or acknowledged_on is missing")
    if adapter_cfg(auth, LINKEDIN).get("enabled") is not True:
        reasons.append("adapters.linkedin_easy_apply.enabled is not true")
    if adapter_mode(auth, LINKEDIN) != "auto":
        reasons.append("adapters.linkedin_easy_apply.mode is not auto")
    ack = auth.get("linkedin_tos_acknowledgement") or {}
    if not _dated(ack.get("acknowledged_on")):
        reasons.append("no dated linkedin_tos_acknowledgement")
    return (not reasons, reasons)


def linkedin_caps(auth: dict) -> dict:
    """LinkedIn's own caps, in the same key names the general caps use."""
    raw = {**LINKEDIN_CAPS, **(adapter_cfg(auth, LINKEDIN).get("caps") or {})}
    return {"max_per_day": int(raw["per_day"]), "max_per_week": int(raw["per_week"]),
            "one_per_company_days": int(raw["per_company_days"])}


def linkedin_cooldown_days(auth: dict) -> int:
    return int(adapter_cfg(auth, LINKEDIN).get("cooldown_days", LINKEDIN_COOLDOWN_DAYS))


def allowed_adapters(base: list[str], auth: dict) -> list[str]:
    """Adapters a run may use: the config's list, plus LinkedIn only when it may auto, narrowed by the
    owner's site allow-list when one is written."""
    allowed = list(base)
    if linkedin_may_auto(auth)[0]:
        if LINKEDIN not in allowed:
            allowed.append(LINKEDIN)
    else:
        allowed = [a for a in allowed if a != LINKEDIN]
    site_list = submission(auth).get("site_allow_list")
    if site_list is not None:
        allowed = [a for a in allowed if a in site_list]
    return allowed
