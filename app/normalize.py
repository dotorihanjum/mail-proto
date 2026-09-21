"""본문 정리와 개인정보 마스킹 (SPEC 6장).

  원문 → HTML 제거 → 길이 자르기 → 마스킹 → AI 전송

중요: AI 는 마스킹된 본문을 보므로, 근거 문장 검증도 마스킹된 본문을 기준으로
해야 한다. 원문과 대조하면 마스킹된 자리 때문에 반드시 불일치가 난다.
"""

import re
from html.parser import HTMLParser

MAX_BODY_CHARS = 4000  # TUNE: AI 에 보낼 본문 최대 길이


class _Stripper(HTMLParser):
    """태그를 떼고 글자만 남긴다. 블록 태그는 줄바꿈으로 바꾼다."""

    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "ul", "ol", "table"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in self.BLOCK:
            self._out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self._out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._out.append(data)

    def text(self) -> str:
        return "".join(self._out)


def looks_like_html(body: str) -> bool:
    return bool(re.search(r"<(html|body|div|p|br|table|ul)\b", body, re.I))


def strip_html(body: str) -> str:
    p = _Stripper()
    p.feed(body)
    text = p.text()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── 개인정보 마스킹 ───────────────────────────────────────────────
# 주의: 날짜를 건드리면 안 된다.
#   - 전화번호는 0으로 시작하므로 "2026-09-30" 과 겹치지 않는다.
#   - 학번은 10자리이므로 8자리 날짜 "20260921" 과 겹치지 않는다.
_PII = [
    (re.compile(r"\d{6}\s*-\s*[1-4]\d{6}"), "[주민번호]"),
    (re.compile(r"\b01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}\b"), "[휴대폰번호]"),
    (re.compile(r"\b0\d{1,2}[-.\s]\d{3,4}[-.\s]\d{4}\b"), "[전화번호]"),
    (re.compile(r"\b(19|20)\d{8}\b"), "[학번]"),
]


def mask_pii(text: str) -> tuple[str, list[str]]:
    """가린 텍스트와, 무엇을 가렸는지 목록을 돌려준다."""
    found: list[str] = []
    for pat, label in _PII:
        if pat.search(text):
            found.append(label)
            text = pat.sub(label, text)
    return text, found


def normalize(body: str, mask: bool = True) -> dict:
    """본문 1건을 처리해 각 단계 결과를 함께 돌려준다."""
    was_html = looks_like_html(body)
    text = strip_html(body) if was_html else body.strip()

    was_truncated = len(text) > MAX_BODY_CHARS
    if was_truncated:
        text = text[:MAX_BODY_CHARS] + "\n\n[본문이 길어 이후는 잘렸습니다]"

    masked, found = (mask_pii(text) if mask else (text, []))
    return {
        "normalized": text,
        "masked": masked,
        "was_html": was_html,
        "was_truncated": was_truncated,
        "masked_kinds": found,
    }
