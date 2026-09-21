"""규칙 코드 (SPEC 9장).

틀리면 안 되는 계산은 AI 에게 맡기지 않는다. 여기가 그 자리다.
  - 날짜 표현을 직접 해석하고, AI 날짜와 다르면 "확인 필요"로 보낸다
  - D-day, 우선순위, 중복 병합

조정할 숫자는 전부 config.py 에 있다.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app import config

WEEKDAYS = "월화수목금토일"
_EN_MONTHS = {
    m.lower(): i + 1 for i, m in enumerate([
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"])
}
_EN_MONTHS.update({m[:3]: i for m, i in list(_EN_MONTHS.items())})

# 마감이 아니라 "마감 없음"을 뜻하는 표현. 해석 실패와 구분한다.
_NO_DEADLINE = re.compile(
    r"곧\s*마감|추후\s*안내|추후\s*공지|미정|별도\s*공지|이번\s*학기\s*중|"
    r"정원이\s*차는\s*대로|상시|수시"
)


@dataclass
class Parsed:
    """날짜 해석 결과."""
    dt: datetime | None = None
    time_specified: bool = False
    ok: bool = False            # 코드가 해석에 성공했는가
    explicit_none: bool = False  # "추후 안내"처럼 마감이 없다고 적힌 경우
    year_inferred: bool = False  # 연도를 우리가 채워 넣었는가
    far_future: bool = False     # 연도 보정 상한을 넘었는가
    note: str = ""


def _with_time(d: date, hh: int | None, mm: int | None) -> tuple[datetime, bool]:
    if hh is None:
        return (datetime(d.year, d.month, d.day,
                         config.DEFAULT_DEADLINE_HOUR,
                         config.DEFAULT_DEADLINE_MINUTE), False)
    return (datetime(d.year, d.month, d.day, hh, mm or 0), True)


def _find_time(text: str) -> tuple[int | None, int | None]:
    """시각을 찾는다. 날짜 부분(2026. 9. 30.)을 시각으로 오인하면 안 된다."""
    m = re.search(r"(\d{1,2})\s*:\s*(\d{2})\s*(AM|PM|am|pm)?", text)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        ap = (m.group(3) or "").lower()
        if ap == "pm" and hh < 12:
            hh += 12
        elif ap == "am" and hh == 12:
            hh = 0
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    m = re.search(r"(오전|오후)\s*(\d{1,2})\s*시", text)
    if m:
        hh = int(m.group(2))
        if m.group(1) == "오후" and hh < 12:
            hh += 12
        return hh, 0
    return None, None


def _infer_year(month: int, day: int, received: date) -> tuple[date, bool, bool]:
    """연도가 없는 날짜를 수신일 이후 가장 가까운 날로 본다.

    상한(config.YEAR_INFERENCE_MAX_MONTHS)을 넘으면 far_future 로 표시해
    '확인 필요'로 보낸다. 회고성 메일의 날짜가 먼 미래로 둔갑하는 것을 막는다.
    """
    for y in (received.year, received.year + 1):
        try:
            cand = date(y, month, day)
        except ValueError:
            continue
        if cand >= received:
            months = (cand.year - received.year) * 12 + (cand.month - received.month)
            return cand, True, months > config.YEAR_INFERENCE_MAX_MONTHS
    return date(received.year + 1, month, day), True, True


def _take_range_end(text: str) -> str:
    """'A ~ B' 는 끝나는 날 B 가 마감이다. 월이 빠지면 앞에서 빌려온다."""
    # 주의: '-' 를 그냥 구분자로 쓰면 "2026-10-02" 같은 날짜까지 쪼개진다.
    #       앞뒤에 공백이 있을 때만 기간 구분자로 본다.
    parts = re.split(r"\s*[~∼]\s*|\s+-\s+|\s*부터\s*", text)
    if len(parts) < 2:
        return text
    head, tail = parts[0], parts[-1]
    if not re.search(r"\d{1,2}\s*월|\d{1,2}\s*/", tail):
        m = re.search(r"(\d{1,2})\s*월", head)
        if m:
            tail = f"{m.group(1)}월 " + tail
    return tail


def parse_deadline(text: str, received: date) -> Parsed:
    """마감 표현을 날짜로 해석한다. 해석 못 하면 ok=False 로 돌려준다."""
    if not text or not text.strip():
        return Parsed(explicit_none=True, note="마감 표현이 비어 있음")

    t = text.strip()
    if _NO_DEADLINE.search(t):
        return Parsed(explicit_none=True, note="마감이 정해지지 않았다고 적힘")

    t = _take_range_end(t)
    hh, mm = _find_time(t)

    # 1) 상대 표현 — 기준은 수신일이다
    for word, delta in (("오늘", 0), ("내일", 1), ("모레", 2), ("글피", 3)):
        if word in t:
            dt, ts = _with_time(received + timedelta(days=delta), hh, mm)
            return Parsed(dt, ts, ok=True, note=f"수신일 기준 {word}")

    m = re.search(r"(이번|금|다음|차)\s*주\s*([월화수목금토일])\s*요?일", t)
    if m:
        target = WEEKDAYS.index(m.group(2))
        if m.group(1) in ("다음", "차"):
            base = received + timedelta(days=7 - received.weekday())
            d = base + timedelta(days=target)
        else:
            d = received + timedelta(days=target - received.weekday())
        dt, ts = _with_time(d, hh, mm)
        return Parsed(dt, ts, ok=True, note=f"수신일 기준 {m.group(1)}주 {m.group(2)}요일")

    # 2) 연도가 있는 날짜
    m = re.search(r"(\d{4})\s*[년.\-/]\s*(\d{1,2})\s*[월.\-/]\s*(\d{1,2})", t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt, ts = _with_time(date(y, mo, d), hh, mm)
            return Parsed(dt, ts, ok=True, note="연월일이 모두 적힘")
        except ValueError:
            return Parsed(ok=False, note=f"날짜로 볼 수 없음: {y}-{mo}-{d}")

    # 3) 영어 (September 29, 2026 / Oct 2)
    m = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2})(?:\s*,\s*(\d{4}))?", t)
    if m and m.group(1).lower() in _EN_MONTHS:
        mo, d = _EN_MONTHS[m.group(1).lower()], int(m.group(2))
        if m.group(3):
            try:
                dt, ts = _with_time(date(int(m.group(3)), mo, d), hh, mm)
                return Parsed(dt, ts, ok=True, note="영어 표기, 연도 있음")
            except ValueError:
                return Parsed(ok=False, note="영어 표기를 날짜로 볼 수 없음")
        day, inferred, far = _infer_year(mo, d, received)
        dt, ts = _with_time(day, hh, mm)
        return Parsed(dt, ts, ok=True, year_inferred=inferred, far_future=far,
                      note="영어 표기, 연도 보정")

    # 4) 연도 없는 날짜 (9월 30일 / 9/30 / 9.30)
    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", t) or \
        re.search(r"(?<![\d:])(\d{1,2})\s*[/]\s*(\d{1,2})(?![\d:])", t)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            return Parsed(ok=False, note=f"달·일 범위를 벗어남: {mo}/{d}")
        try:
            day, inferred, far = _infer_year(mo, d, received)
        except ValueError:
            return Parsed(ok=False, note=f"날짜로 볼 수 없음: {mo}/{d}")
        dt, ts = _with_time(day, hh, mm)
        return Parsed(dt, ts, ok=True, year_inferred=inferred, far_future=far,
                      note="연도가 없어 수신일 이후 가장 가까운 날로 봄")

    return Parsed(ok=False, note="해석할 수 있는 날짜 표현을 찾지 못함")


# ── 날짜 확정 ─────────────────────────────────────────────────────
def _fmt(dt: datetime | None, time_specified: bool) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M") if time_specified else dt.strftime("%Y-%m-%d")


def resolve_deadline(ai_iso: str | None, deadline_text: str,
                     received: date) -> dict:
    """AI 날짜와 코드 날짜를 견줘 최종 마감일을 정한다.

    누가 이기는가: 코드가 해석에 성공하면 코드가 이긴다.
    SPEC 6장 "틀리면 안 되는 부분은 AI에게 맡기지 않는다" 에 따른 것이다.
    어느 쪽을 쓰든 둘이 다르면 반드시 '확인 필요'로 보낸다.
    """
    p = parse_deadline(deadline_text or "", received)
    rule_iso = _fmt(p.dt, p.time_specified)
    reasons: list[str] = []
    conf_cap: float | None = None

    if p.ok:
        final = rule_iso
        if ai_iso and rule_iso and ai_iso != rule_iso:
            reasons.append("date_mismatch")
        if p.far_future:
            reasons.append("far_future")
    elif p.explicit_none:
        final = ai_iso
        if ai_iso:
            # 본문은 "추후 안내"라는데 AI 가 날짜를 만들어낸 경우
            reasons.append("date_mismatch")
    else:
        # 코드가 해석하지 못한 표현 -> AI 날짜를 쓰되 신뢰도에 상한을 씌운다
        final = ai_iso
        conf_cap = config.UNPARSED_DATE_CONFIDENCE_CAP

    return {
        "deadline_ai": ai_iso,
        "deadline_rule": rule_iso,
        "deadline_iso": final,
        "time_specified": p.time_specified if p.ok else None,
        "reasons": reasons,
        "confidence_cap": conf_cap,
        "parse_note": p.note,
    }


# ── D-day 와 우선순위 ─────────────────────────────────────────────
def days_until(deadline_iso: str | None, today: date) -> int | None:
    if not deadline_iso:
        return None
    return (date.fromisoformat(deadline_iso[:10]) - today).days


def priority_of(dday: int | None) -> int:
    """0 긴급 / 1 높음 / 2 보통 / 3 여유. 마감이 없으면 3."""
    if dday is None:
        return 3
    if dday <= config.PRIORITY_URGENT_DAYS:
        return 0
    if dday <= config.PRIORITY_HIGH_DAYS:
        return 1
    if dday <= config.PRIORITY_NORMAL_DAYS:
        return 2
    return 3


PRIORITY_TEXT = {0: "긴급", 1: "높음", 2: "보통", 3: "여유"}


# ── 중복 병합 ─────────────────────────────────────────────────────
def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def merge_duplicates(items: list[dict]) -> list[list[int]]:
    """마감일(날짜까지)이 같고 제목이 닮은 항목끼리 묶는다.

    묶음은 인덱스 목록의 목록으로 돌려준다. 단독 항목도 1개짜리 묶음이 된다.
    """
    n = len(items)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for i in range(n):
        for j in range(i + 1, n):
            di = (items[i].get("deadline_iso") or "")[:10]
            dj = (items[j].get("deadline_iso") or "")[:10]
            if not di or di != dj:
                continue
            if _similar(items[i]["title"], items[j]["title"]) >= config.DUPLICATE_TITLE_SIMILARITY:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return [sorted(v) for _, v in sorted(groups.items())]


# ── 오늘 할 일 3가지 ──────────────────────────────────────────────
def today_top(items: list[dict], today: date, n: int | None = None) -> list[dict]:
    """우선순위 -> 마감 빠른 순으로 상위 N개.

    확인 필요, 마감 없음, 이미 지난 것, 완료한 것은 빼고 고른다.
    (SPEC 9장: 마감 없음 또는 확인 필요는 별도 목록)
    """
    n = n or config.TODAY_TOP_N
    pool = [
        it for it in items
        if it.get("deadline_iso")
        and not it.get("needs_review")
        and it.get("status", "open") != "done"
        and (days_until(it["deadline_iso"], today) or 0) >= 0
    ]
    pool.sort(key=lambda it: (priority_of(days_until(it["deadline_iso"], today)),
                              it["deadline_iso"]))
    return pool[:n]


# ── 파이프라인 연결 ───────────────────────────────────────────────
def apply_rules(out: dict, received: date, today: date) -> dict:
    """검증까지 끝난 결과에 규칙을 적용한다 (SPEC 6장 '규칙 처리' 단계).

    validate.py 가 붙여 둔 확인 필요 사유에 날짜 관련 사유를 더한다.
    """
    if out["status"] != "success":
        return out

    for it in out["result"]["items"]:
        r = resolve_deadline(it.get("deadline_iso"), it.get("deadline_text", ""), received)

        it["deadline_ai"] = r["deadline_ai"]
        it["deadline_rule"] = r["deadline_rule"]
        it["deadline_iso"] = r["deadline_iso"]
        it["parse_note"] = r["parse_note"]
        if r["time_specified"] is not None:
            it["time_specified"] = r["time_specified"]

        # 코드가 해석하지 못한 표현이면 신뢰도에 상한을 씌운다 (SPEC 9장)
        if r["confidence_cap"] is not None:
            it["confidence"] = min(it["confidence"], r["confidence_cap"])

        reasons = list(it.get("review_reason", []))
        for extra in r["reasons"]:
            if extra not in reasons:
                reasons.append(extra)

        # 상한을 씌운 뒤 신뢰도를 다시 본다
        if it["confidence"] <= config.CONFIDENCE_REVIEW_MAX and "low_confidence" not in reasons:
            reasons.append("low_confidence")
        # 마감이 확정됐으면 no_deadline 은 빼준다
        if it["deadline_iso"] and "no_deadline" in reasons:
            reasons.remove("no_deadline")
        elif not it["deadline_iso"] and "no_deadline" not in reasons:
            reasons.append("no_deadline")

        it["review_reason"] = reasons
        it["needs_review"] = bool(reasons)

        it["dday"] = days_until(it["deadline_iso"], today)
        it["priority"] = priority_of(it["dday"])
        it["is_overdue"] = it["dday"] is not None and it["dday"] < 0

    return out
