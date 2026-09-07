"""Localize presentation of a frozen summary; preserve original records and codes."""

import re
from html import escape
from html.parser import HTMLParser

from oceanpilot.web_i18n import CLIENT_TRANSLATIONS

_PHRASES = sorted(CLIENT_TRANSLATIONS, key=len, reverse=True)
_PATTERN = re.compile(
    "|".join(re.escape(key) for key in _PHRASES if re.search(r"[\u3400-\u9fff]", key))
)


def translate_display(text: str) -> str:
    return _PATTERN.sub(lambda match: CLIENT_TRANSLATIONS[match[0]], text)


class _SummaryTranslator(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool]] = []

    def handle_starttag(self, tag, attrs):
        skip = (
            bool(self.stack and self.stack[-1][1])
            or tag in ("style", "script")
            or any(key == "data-no-i18n" for key, _ in attrs)
        )
        self.parts.append(
            self.get_starttag_text().replace('lang="zh-CN"', 'lang="en"')
            if tag == "html"
            else self.get_starttag_text()
        )
        if tag not in ("meta", "br", "hr", "img", "input", "link", "wbr"):
            self.stack.append((tag, skip))

    def handle_endtag(self, tag):
        self.parts.append(f"</{tag}>")
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_data(self, data):
        self.parts.append(
            data
            if self.stack and self.stack[-1][1]
            else escape(translate_display(data), quote=False)
        )

    def handle_entityref(self, name):
        self.parts.append(f"&{name};")

    def handle_charref(self, name):
        self.parts.append(f"&#{name};")

    def handle_decl(self, decl):
        self.parts.append(f"<!{decl}>")


def localize_summary_html(html: str, locale: str) -> str:
    if locale != "en":
        return html
    parser = _SummaryTranslator()
    parser.feed(html)
    return "".join(parser.parts)
