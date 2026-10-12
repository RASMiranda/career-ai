"""Deterministic triage: spend model tokens only on candidates that need judgement.

Per profile (``prefilter:`` in profile.yaml):

    prefilter:
      min_description_chars: 300   # shorter text (e.g. alert emails) always goes to the model
      require_any: [java, angular] # a described job must mention one of these (whole words)
      reject_title: ['\\bjunior\\b'] # regexes; a matching title is discarded
      max_to_score: 40             # more than this per run waits for the next run

Rejected candidates get a ``discarded`` decision written by code ("prefilter: ...");
the model never sees them. Candidates over the cap are left out of the run
entirely and are not marked seen, so they come back next time.
"""

import html
import re

from .config import ConfigError
from .cv import catalog

DEFAULT_MAX_TO_SCORE = 40
DEFAULT_MIN_DESCRIPTION = 300
EXCERPT_CHARS = 500

LEVELS = {"a1": 1, "basic": 2, "a2": 2, "b1": 3, "intermediate": 3, "b2": 4,
          "professional": 5, "c1": 5, "fluent": 5, "c2": 6, "native": 7}
DEFAULT_WORKING_LEVEL = "professional"

# Language -> names a posting may use for it, and common function words (offline
# detection: a text is "in" a language when these are a clear share of its words).
LANGS = {
    "en": ("english|englisch|anglais|inglés|inglês|inglese", "the and of to in is for with on you we are our will be as".split()),
    "de": ("german|deutsch\\w*|allemand|alemán|alemão|tedesco|duits", "der die das und ist nicht mit für auf werden wir sie ein eine den dem von zu im als auch bei oder sich wird sind nach über".split()),
    "fr": ("french|französisch\\w*|français|francais|francés|francês|francese|frans|francophone", "le la les des est une pour dans avec sur nous vous pas qui que du au aux et ou votre notre sont par".split()),
    "nl": ("dutch|niederländisch\\w*|nederlands\\w*|néerlandais|holandés|holandês|olandese", "de het een en van is voor met op te niet wij je zijn aan ook bij als naar door of onze".split()),
    "es": ("spanish|spanisch|español|espagnol|espanhol|spagnolo", "el la los las de un una es para con por que en y nuestro tu se del al como más o son".split()),
    "it": ("italian|italienisch|italiano|italien|italiana", "il lo la le di un una è per con che in e nostro sono del della al come più non o gli".split()),
    "pt": ("portuguese|portugiesisch|português|portugais|portugués|portoghese", "o a os as de um uma é para com por que em e nosso você se do da no na como mais ou são".split()),
}
LANG_SHARE = 0.06   # min share of function words
LANG_LEAD = 2       # and at least this many times the runner-up's count
MIN_LANG_WORDS = 40
_TAG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
_DEMAND = (r"c1|c2|b2|fluent|fluency|native|mother tongue|business|proficien\w*|very good|excellent|strong|"
           r"required|mandatory|must|knowledge of|skills? in|sehr gute?|verhandlungssicher\w*|fließend\w*|"
           r"muttersprach\w*|erforderlich|vorausgesetzt|obligatoire|courant|indispensable|"
           r"communicat\w*|speak\w*|spoken|written|ability to|able to|working knowledge|language proficiency|"
           r"bilingual|bilingue|maîtrise|vloeiend|tweetalig|gute\w*|kenntnisse")
_SOFT = re.compile(r"\b(plus|asset|advantage|bonus|nice to have|desirable|preferred|von vorteil|wünschenswert|idéalement)\b", re.I)

# A thin text (Adzuna cuts it at ~500 chars, the language line sits further down the page; alert emails
# carry none) cannot show the language, but an on-site place still says what the job is worked in.
# Place -> languages spoken there at work. Brussels is deliberately absent (English is common there, so
# only the text can say), as is Germany (English-first tech scene). A bare "Belgium" means nl, fr or de.
REGION_LANGUAGES = {
    "fr": re.compile(r"(?<!\w)(?:wallonie|wallonia|wallonië|namur|namen|nivelles|nijvel|tubize|tubeke|li[eè]ge|luik|charleroi|"
                     r"hainaut|henegouwen|brabant wallon|waals-brabant|louvain-la-neuve|wavre|waver|arlon|aarlen|verviers|"
                     r"tournai|doornik|paris|lyon|marseille|toulouse|lille|nantes|bordeaux|strasbourg|france|frankrijk)(?!\w)", re.I),
    "nl": re.compile(r"(?<!\w)(?:vlaanderen|flanders|antwerpen|antwerp|gent|ghent|brugge|bruges|leuven|mechelen|hasselt|"
                     r"kortrijk|oost-vlaanderen|west-vlaanderen|vlaams-brabant)(?!\w)", re.I),
}
_BELGIUM = re.compile(r"(?<!\w)(?:belgi[eëum]\w*|belgique|belgien)(?!\w)", re.I)
_BRUSSELS = re.compile(r"(?<!\w)(?:brussels?|bruxelles|brussel)(?!\w)", re.I)
BELGIUM_LANGUAGES = {"fr", "nl", "de"}
SNIPPET_SOURCES = {"adzuna"}   # APIs that return an excerpt, not the posting

_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def clean(text: str) -> str:
    """Plain text: tags dropped, entities decoded, whitespace collapsed."""
    return _SPACE.sub(" ", html.unescape(_TAGS.sub(" ", text or ""))).strip()


def _spoken(profile: dict, raw: dict) -> set[str] | None:
    """Languages below working level (a posting needing one is out); None = nothing declared."""
    declared = profile.get("languages") or {}
    if not declared:
        return None
    pid = profile.get("id")
    best = {}
    for tag, level in declared.items():
        if not _TAG.match(str(tag).lower()) or str(level).lower() not in LEVELS:
            raise ConfigError(f"profile {pid!r}: languages: {tag!r}: {level!r} must be a BCP 47 tag "
                              f"(pt-PT) and one of {sorted(LEVELS)}")
        lang = str(tag).lower().split("-")[0]
        best[lang] = max(best.get(lang, 0), LEVELS[str(level).lower()])
    wl = str(raw.get("working_level", DEFAULT_WORKING_LEVEL)).lower()
    if wl not in LEVELS:
        raise ConfigError(f"profile {pid!r}: prefilter.working_level {wl!r} must be one of {sorted(LEVELS)}")
    return {lang for lang in LANGS if best.get(lang, 0) < LEVELS[wl]}


def detect_language(text: str) -> str | None:
    """Best-matching language in LANGS, or None if the text is short or unclear."""
    words = re.findall(r"[^\W\d_]+", text.lower())
    if len(words) < MIN_LANG_WORDS:
        return None
    hits = {lang: sum(w in set(stop) for w in words) for lang, (_, stop) in LANGS.items()}
    best, runner_up = sorted(hits, key=hits.get, reverse=True)[:2]
    clear = hits[best] >= LANG_LEAD * hits[runner_up]
    return best if clear and hits[best] / len(words) >= LANG_SHARE else None


def demanded_language(text: str, lacking: set[str]) -> str | None:
    """A lacking language the text demands, e.g. 'fluent German' or 'Deutsch C1'; 'a plus' is not a demand."""
    for lang in sorted(lacking):
        names = LANGS[lang][0]
        rx = re.compile(rf"\b(?:{_DEMAND})\b[^.\n;]{{0,40}}\b(?:{names})\b|\b(?:{names})\b[^.\n;]{{0,40}}\b(?:{_DEMAND})\b", re.I)
        for m in rx.finditer(text):
            if not _SOFT.search(text[max(0, m.start() - 40):m.end() + 40]):
                return lang
    return None


_NEGATED = re.compile(r"\b(no|not|without|nor|neither|zonder|sans|ohne)\b[^.;]{0,25}$", re.I)


def language_worry(text: str, lacking: set[str]) -> str | None:
    """A lacking language the model's own words raise as a risk ('French likely'); 'a plus' and 'no French' don't count."""
    for lang in sorted(lacking):
        for m in re.finditer(rf"\b(?:{LANGS[lang][0]})\b", text, re.I):
            if not _SOFT.search(text[max(0, m.start() - 40):m.end() + 40]) and not _NEGATED.search(text[:m.start()]):
                return lang
    return None


def is_snippet(candidate: dict, min_chars: int = DEFAULT_MIN_DESCRIPTION) -> bool:
    """The text is a cut-off excerpt or an alert line, not the whole posting."""
    text = clean(candidate.get("description"))
    return len(text) < min_chars or candidate.get("source") in SNIPPET_SOURCES or text.endswith(("...", "…"))


def local_languages(candidate: dict) -> set[str]:
    """Languages an on-site job is worked in, from its place alone; empty when remote or unclear."""
    place = candidate.get("location") or ""
    if candidate.get("remote") is True or not place or _BRUSSELS.search(place):
        return set()
    found = {lang for lang, rx in REGION_LANGUAGES.items() if rx.search(place)}
    if not found and _BELGIUM.search(place):
        return set(BELGIUM_LANGUAGES)
    return found


def rules_for(profile: dict) -> dict:
    raw = profile.get("prefilter") or {}
    try:
        reject = [re.compile(p, re.I) for p in raw.get("reject_title") or []]
    except re.error as exc:
        raise ConfigError(f"profile {profile.get('id')!r}: bad prefilter.reject_title regex: {exc}")
    spoken = _spoken(profile, raw)
    terms = [t for t in raw.get("require_any") or [] if str(t).strip()]
    require = re.compile("|".join(rf"(?<!\w){re.escape(str(t).strip())}(?!\w)" for t in terms), re.I) if terms else None
    return {"reject_title": reject, "spoken": spoken, "require_any": require,
            "min_description_chars": int(raw.get("min_description_chars", DEFAULT_MIN_DESCRIPTION)),
            "max_to_score": int(raw.get("max_to_score", DEFAULT_MAX_TO_SCORE))}


def reject_reason(candidate: dict, rules: dict) -> str | None:
    title = candidate.get("title") or ""
    for rx in rules["reject_title"]:
        if rx.search(title):
            return f"title matches {rx.pattern}"
    description = clean(candidate.get("description"))
    lacking = rules["spoken"]
    if lacking:
        if len(description) >= rules["min_description_chars"]:
            written = detect_language(description)
            if written in lacking:
                return f"posting is written in {written}, not spoken at working level"
        demanded = demanded_language(f"{title} {description}", lacking)   # a short text can still say it
        if demanded:
            return f"posting demands {demanded}, not spoken at working level"
        local = local_languages(candidate)
        if local and local <= lacking and is_snippet(candidate, rules["min_description_chars"]):
            return (f"text is only a snippet, so the language is unverified, and the job is on site in {candidate.get('location')!r} "
                    f"where it is worked in {'/'.join(sorted(local))}, not spoken at working level")
    if (rules["require_any"] and len(description) >= rules["min_description_chars"]
            and not rules["require_any"].search(f"{title} {description}")):
        return "none of the required terms appear"
    return None


def auto_decision(candidate: dict, reason: str) -> dict:
    return {"candidate_key": candidate["candidate_key"], "fit": 0, "tier": "radar",
            "confidence": "high", "disposition": "discarded",
            "why": f"prefilter: {reason}", "caution": "", "next_action": "None"}


def triage(payload: dict, cfg: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (auto decisions, candidates for the model, candidates deferred by the cap)."""
    rules = {p["id"]: rules_for(p) for p in cfg["profiles"]}
    default = rules_for({})
    auto, to_score, deferred, scored = [], [], [], {}
    for c in payload["candidates"]:
        pid = c.get("profile")
        r = rules.get(pid, default)
        reason = reject_reason(c, r)
        if reason:
            auto.append(auto_decision(c, reason))
        elif scored.get(pid, 0) >= r["max_to_score"]:
            deferred.append(c)
        else:
            scored[pid] = scored.get(pid, 0) + 1
            to_score.append(c)
    return auto, to_score, deferred


def render_brief(to_score: list[dict], cfg: dict, root, excerpt: int = EXCERPT_CHARS) -> str:
    """What the model reads instead of candidates.json: one short block per candidate."""
    profiles = {p["id"]: p for p in cfg["profiles"]}
    out = []
    for pid in dict.fromkeys(c.get("profile") for c in to_score):
        p = profiles.get(pid, {"id": pid})
        cvs = ", ".join(sorted(catalog(root, p))) or "none"
        out += [f"# Profile {pid}: criteria {p.get('criteria', '?')} · CV variants: {cvs}", ""]
        for c in (c for c in to_score if c.get("profile") == pid):
            text = clean(c.get("description"))
            remote = {True: "remote", False: "not remote"}.get(c.get("remote"), "remote?")
            facts = " | ".join(filter(None, [c.get("location"), remote, c.get("contract_type"),
                                             c.get("salary"), c.get("source")]))
            snippet = (" [SNIPPET: the posting is longer; language, on-site and rate are unverified. If the place "
                       "or wording makes a language the profile lacks likely, discard it]") if is_snippet(c) else ""
            more = f" […+{len(text) - excerpt} chars: pipeline show {c['candidate_key']}]" if len(text) > excerpt else ""
            out += [f"## {c['candidate_key']} | {c['title']} | {c['company']}",
                    facts, ((text[:excerpt] + more + snippet) if text else "(no description)"), ""]
    return "\n".join(out).rstrip() + "\n"
