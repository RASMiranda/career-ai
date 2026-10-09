"""Make a saved web page safe to share: keep the structure, drop everything personal.

    python -m jobscan.redact page.html --term "Ana" --term "Silva" --term "Lisbon" [--out safe.html]

Why: to build or fix a site adapter from your own saved pages, the page has to be
uploaded. A page saved while you were logged in carries session tokens, your name, your
contact details and tracking ids. This keeps what an adapter needs (tags, classes, roles,
labels, ``data-test*`` hooks, option lists, the ``JobPosting`` JSON-LD) and removes the rest:

- scripts (except JSON-LD), styles, SVG, iframes, comments, ``<noscript>``, most ``<meta>``
- the ``value`` of every text-like input, the content of every ``<textarea>``
- inline styles, event handlers, nonces, and ``data-*`` attributes other than test hooks
- query strings and fragments in links, ``/in/<handle>`` paths, ``urn:li:`` ids
- email addresses, phone numbers, and every ``--term`` you name (case-insensitive)

It is conservative, not a guarantee: names, employers and cities you do not pass as
``--term`` stay. Read the result before you share it.
"""

import argparse
import html
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

MAX_BYTES = 30_000_000
DROP_CONTENT = {"style", "noscript", "svg", "iframe", "template", "object", "embed", "canvas"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}   # no end tag
KEEP_META = {"viewport", "description", "og:title", "og:url", "og:description", "og:site_name", "og:type"}
KEEP_DATA = re.compile(r"^data-(test|testid|cy|qa|automation|control-name|field|name|type|purpose|ui|e2e)", re.I)
VALUE_KEPT = {"radio", "checkbox", "submit", "button", "reset", "image"}
URL_ATTRS = {"href", "src", "action", "content", "poster", "data-href"}
STRUCTURAL = {"class", "id", "for", "name", "type", "role", "rel", "lang", "charset"}   # no phone scrub

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<![\w])\+?\d[\d\s().-]{7,}\d(?![\w])")
_IN_PATH = re.compile(r"(/in/|/pub/|/profile/view\?id=)[^/\"'?#\s&]+", re.I)
_URN = re.compile(r"urn:li:[A-Za-z_]+:[A-Za-z0-9_,()-]+")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class Redactor(HTMLParser):
    def __init__(self, terms: list[str]):
        super().__init__(convert_charrefs=False)
        self.terms = [re.compile(re.escape(t), re.I) for t in terms if t.strip()]
        self.out: list[str] = []
        self.counts: dict[str, int] = {}
        self._drop_tag = ""        # element whose content is being dropped
        self._drop_depth = 0
        self._in_textarea = False
        self._textarea_typed = False
        self._in_ld = False

    # ----------------------------------------------------------------- helpers
    def _count(self, what: str, n: int = 1) -> None:
        self.counts[what] = self.counts.get(what, 0) + n

    def _scrub(self, text: str, phones: bool = True) -> str:
        def phone(m: re.Match) -> str:
            digits = sum(c.isdigit() for c in m.group())
            if digits < 9 or _ISO_DATE.fullmatch(m.group().strip()):
                return m.group()
            self._count("phones")
            return "[phone]"

        text, n = _EMAIL.subn("[email]", text)
        self._count("emails", n)
        if phones:
            text = _PHONE.sub(phone, text)
        for rx in self.terms:
            text, n = rx.subn("REDACTED", text)
            self._count("terms", n)
        text, n = _URN.subn("urn:li:REDACTED", text)
        self._count("ids", n)
        return text

    def _url(self, value: str) -> str:
        if re.match(r"^(https?:)?//|^/", value):
            trimmed = re.split(r"[?#]", value, maxsplit=1)[0]
            if trimmed != value:
                self._count("urls_trimmed")
            value = trimmed
        value, n = _IN_PATH.subn(lambda m: m.group(1) + "REDACTED", value)
        self._count("ids", n)
        return value

    def _attrs(self, tag: str, attrs: list) -> list[tuple[str, str | None]]:
        kind = dict((k.lower(), v) for k, v in attrs).get("type", "") or ""
        out = []
        for key, value in attrs:
            k = key.lower()
            if k.startswith("on") or k in {"nonce", "integrity", "style", "srcset"} or (
                    k == "src" and tag in {"img", "source"}):
                self._count("attributes_dropped")
                continue
            if k.startswith("data-") and not KEEP_DATA.match(k):
                self._count("attributes_dropped")
                continue
            if value is None:
                out.append((key, None))
                continue
            if tag == "input" and k == "value" and kind.lower() not in VALUE_KEPT:
                if value:
                    self._count("inputs_blanked")
                out.append((key, ""))
                continue
            value = html.unescape(value)
            if k in URL_ATTRS:
                value = self._url(value)
            out.append((key, self._scrub(value, phones=k not in STRUCTURAL and not k.startswith("data-"))))
        return out

    @staticmethod
    def _tag(tag: str, attrs: list, closed: bool) -> str:
        parts = [tag]
        for key, value in attrs:
            parts.append(key if value is None else f'{key}="{html.escape(value, quote=True)}"')
        return "<" + " ".join(parts) + (" />" if closed else ">")

    def _keep_meta(self, attrs: list) -> bool:
        d = {k.lower(): (v or "") for k, v in attrs}
        return "charset" in d or (d.get("name") or d.get("property") or "").lower() in KEEP_META

    # ------------------------------------------------------------------- parser
    def _start(self, tag: str, attrs: list, closed: bool) -> None:
        tag = tag.lower()
        if self._drop_tag:
            if tag == self._drop_tag and not closed:
                self._drop_depth += 1
            return
        if tag == "script":
            if "ld+json" in dict((k.lower(), (v or "").lower()) for k, v in attrs).get("type", ""):
                self._in_ld = True
                self.out.append(self._tag(tag, self._attrs(tag, attrs), False))
            else:
                self._count("scripts_removed")
                self._drop_tag, self._drop_depth = "script", 1
            return
        if tag in DROP_CONTENT:
            self._count(f"{tag}_removed")
            if not closed:
                self._drop_tag, self._drop_depth = tag, 1
            return
        if tag == "meta" and not self._keep_meta(attrs):
            self._count("meta_dropped")
            return
        if tag == "link" and "canonical" not in dict((k.lower(), (v or "").lower()) for k, v in attrs).get("rel", ""):
            return
        if tag == "textarea":
            self._in_textarea = True
        self.out.append(self._tag(tag, self._attrs(tag, attrs), closed))

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, True)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._drop_tag:
            if tag == self._drop_tag:
                self._drop_depth -= 1
                if self._drop_depth <= 0:
                    self._drop_tag = ""
            return
        if tag in VOID:
            return
        if tag == "textarea":
            self._in_textarea = False
            if self._textarea_typed:
                self._count("textareas_blanked")
            self._textarea_typed = False
        if tag == "script":
            self._in_ld = False
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self._drop_tag:
            return
        if self._in_textarea:
            self._textarea_typed = self._textarea_typed or bool(data.strip())
            return
        self.out.append(self._scrub(data, phones=not self._in_ld))

    def handle_entityref(self, name):
        if not self._drop_tag and not self._in_textarea:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self._drop_tag and not self._in_textarea:
            self.out.append(f"&#{name};")

    def handle_comment(self, data):
        self._count("comments_removed")

    def handle_decl(self, decl):
        if decl.lower().startswith("doctype"):
            self.out.append(f"<!{decl}>")

    def handle_pi(self, data):
        pass

    def unknown_decl(self, data):
        pass


def redact(page: str, terms: list[str] | None = None) -> tuple[str, dict[str, int]]:
    parser = Redactor(terms or [])
    parser.feed(page)
    parser.close()
    return "".join(parser.out), parser.counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jobscan.redact", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="an HTML page you saved (not .mhtml)")
    ap.add_argument("--term", action="append", default=[], metavar="TEXT",
                    help="text to remove wherever it appears: your names, city, employer, school (repeatable)")
    ap.add_argument("--out", help="default: <file>.redacted.html next to the original")
    args = ap.parse_args(argv)

    src = Path(args.file)
    if not src.is_file() or src.stat().st_size > MAX_BYTES:
        print(f"error: {src} is not a file, or is larger than {MAX_BYTES // 1_000_000} MB", file=sys.stderr)
        return 2
    page = src.read_text(encoding="utf-8", errors="replace")
    head = page[:600].lower()
    if "mime-version" in head or "content-type: multipart" in head:
        print("error: this is an .mhtml bundle. Save the page as 'Webpage, HTML only' or "
              "'Webpage, Complete' instead.", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else src.with_name(src.stem + ".redacted.html")
    if out.resolve() == src.resolve():
        print("error: refusing to overwrite the original", file=sys.stderr)
        return 2
    safe, counts = redact(page, args.term)
    out.write_text(safe, encoding="utf-8")
    print(f"wrote {out} ({len(page):,} -> {len(safe):,} bytes)")
    for what, n in sorted(counts.items()):
        print(f"  {what.replace('_', ' ')}: {n}")
    if not args.term:
        print("  ! no --term given: your name, city and employer are still in the file")
    print("Open the file and read it before you share it; only what is listed above was removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
