# -*- coding: utf-8 -*-
"""규칙 엔진 단위 테스트 (SPEC 9장).

AI 를 호출하지 않는다. 순수 계산만 검사하므로 빠르고 공짜다.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.rules import (  # noqa: E402
    parse_deadline, resolve_deadline, days_until, priority_of,
    merge_duplicates, today_top,
)

WED = date(2026, 9, 16)   # 수요일
THU = date(2026, 9, 17)   # 목요일
MON = date(2026, 9, 21)   # 월요일 = 기준일(오늘)


# ══ 날짜 표현 해석 ════════════════════════════════════════════════

@pytest.mark.parametrize("text,received,expected,time_spec", [
    # 연월일이 모두 적힌 경우
    ("2026년 9월 30일(수) 18:00까지", date(2026, 9, 15), "2026-09-30T18:00", True),
    ("2026. 9. 30.(수) 18:00",        date(2026, 9, 15), "2026-09-30T18:00", True),
    ("2026년 9월 24일(목) 17:00",      THU,               "2026-09-24T17:00", True),
    ("2026-10-02",                    date(2026, 9, 19), "2026-10-02",       False),
    # 연도 생략 — 수신일 이후 가장 가까운 날
    ("9월 25일(금)",                   WED,               "2026-09-25",       False),
    ("10/5까지",                      date(2026, 9, 19), "2026-10-05",       False),
    ("9/30 까지",                     date(2026, 9, 15), "2026-09-30",       False),
    ("1월 5일까지",                    date(2026, 9, 20), "2027-01-05",       False),
    # 기간은 끝나는 날이 마감
    ("10월 12일(월) ~ 10월 16일(금)",   WED,               "2026-10-16",       False),
    ("9월 15일 ~ 30일",                date(2026, 9, 10), "2026-09-30",       False),
    # 영어
    ("September 29, 2026 (5:00 PM KST)", date(2026, 9, 18), "2026-09-29T17:00", True),
    ("October 2, 2026",                  date(2026, 9, 19), "2026-10-02",       False),
])
def test_날짜표현_해석(text, received, expected, time_spec):
    p = parse_deadline(text, received)
    assert p.ok, f"{text!r} 를 해석하지 못함 ({p.note})"
    got = p.dt.strftime("%Y-%m-%dT%H:%M") if p.time_specified else p.dt.strftime("%Y-%m-%d")
    assert got == expected
    assert p.time_specified is time_spec


@pytest.mark.parametrize("text,received,expected", [
    # ★ 상대 표현의 기준은 '오늘'이 아니라 '수신일'이다
    ("내일까지",        MON, "2026-09-22"),
    ("모레까지",        MON, "2026-09-23"),
    ("오늘까지",        MON, "2026-09-21"),
    ("이번 주 금요일",   WED, "2026-09-18"),   # 수신 9/16(수) 기준 -> 이미 지난 날
    ("다음 주 월요일",   THU, "2026-09-21"),   # 수신 9/17(목) 기준 -> 오늘
    ("다음 주 수요일",   MON, "2026-09-30"),
])
def test_상대표현은_수신일_기준(text, received, expected):
    p = parse_deadline(text, received)
    assert p.ok, f"{text!r} 를 해석하지 못함"
    assert p.dt.strftime("%Y-%m-%d") == expected


def test_수신일이_과거면_마감도_과거로_나온다():
    """오늘로 당겨 계산하면 안 된다. 지난 마감은 지난 대로 둔다."""
    p = parse_deadline("이번 주 금요일", WED)
    assert p.dt.date() == date(2026, 9, 18)
    assert p.dt.date() < MON


@pytest.mark.parametrize("text", [
    "정원이 차는 대로 곧 마감", "추후 안내 예정", "이번 학기 중", "별도 공지", "",
])
def test_마감없음_표현은_날짜를_만들지_않는다(text):
    p = parse_deadline(text, MON)
    assert p.explicit_none
    assert p.dt is None


def test_해석불가는_실패로_표시된다():
    p = parse_deadline("가능한 한 빨리 부탁드립니다", MON)
    assert not p.ok and not p.explicit_none


# ══ 연도 보정 상한 ════════════════════════════════════════════════

def test_연도보정_상한_이내는_정상():
    """수신 9/16 의 '4월 15일' = 2027-04-15 = 7개월 뒤 (상한 9개월 이내)."""
    p = parse_deadline("4월 15일까지", WED)
    assert p.ok and p.year_inferred
    assert p.dt.date() == date(2027, 4, 15)
    assert not p.far_future


def test_연도보정_상한_초과는_확인필요로():
    """수신 9/16 의 '7월 1일' = 2027-07-01 = 10개월 뒤 (상한 초과)."""
    p = parse_deadline("7월 1일까지", WED)
    assert p.ok and p.far_future
    r = resolve_deadline(p.dt.strftime("%Y-%m-%d"), "7월 1일까지", WED)
    assert "far_future" in r["reasons"]


def test_상한_경계값():
    """딱 9개월이면 통과, 10개월이면 걸린다."""
    assert config.YEAR_INFERENCE_MAX_MONTHS == 9
    assert not parse_deadline("6월 16일", WED).far_future      # 9개월
    assert parse_deadline("7월 16일", WED).far_future          # 10개월


# ══ AI 와 코드의 대조 ═════════════════════════════════════════════

def test_둘이_같으면_확인필요_아님():
    r = resolve_deadline("2026-09-25", "9월 25일(금)", WED)
    assert r["deadline_iso"] == "2026-09-25"
    assert r["reasons"] == []


def test_둘이_다르면_확인필요_그리고_코드가_이긴다():
    """실제로 M3 에서 AI 가 틀렸던 m10 케이스."""
    r = resolve_deadline("2026-09-28", "다음 주 월요일", THU)
    assert "date_mismatch" in r["reasons"]
    assert r["deadline_ai"] == "2026-09-28"
    assert r["deadline_rule"] == "2026-09-21"
    assert r["deadline_iso"] == "2026-09-21"   # 코드가 이긴다


def test_m11_모레_케이스():
    r = resolve_deadline("2026-09-22", "모레까지", MON)
    assert "date_mismatch" in r["reasons"]
    assert r["deadline_iso"] == "2026-09-23"


def test_코드가_해석못하면_AI날짜를_쓰되_신뢰도에_상한():
    r = resolve_deadline("2026-10-01", "가능한 한 빨리", MON)
    assert r["deadline_iso"] == "2026-10-01"
    assert r["confidence_cap"] == config.UNPARSED_DATE_CONFIDENCE_CAP
    assert r["confidence_cap"] == 0.7


def test_본문은_마감없음인데_AI가_날짜를_만들면_확인필요():
    r = resolve_deadline("2026-10-31", "추후 안내 예정", MON)
    assert "date_mismatch" in r["reasons"]


# ══ D-day 와 우선순위 경계값 ══════════════════════════════════════

def test_dday():
    assert days_until("2026-09-21", MON) == 0
    assert days_until("2026-09-22", MON) == 1
    assert days_until("2026-09-18", MON) == -3     # 지남
    assert days_until("2026-09-30T18:00", MON) == 9
    assert days_until(None, MON) is None


@pytest.mark.parametrize("dday,expected", [
    (-5, 0), (0, 0), (1, 0),      # 긴급 (D <= 1)
    (2, 1), (3, 1),               # 높음 (D <= 3)
    (4, 2), (7, 2),               # 보통 (D <= 7)
    (8, 3), (100, 3),             # 여유
    (None, 3),                    # 마감 없음
])
def test_우선순위_경계값(dday, expected):
    assert priority_of(dday) == expected


# ══ 중복 병합 ═════════════════════════════════════════════════════

def _it(title, iso, **kw):
    return {"title": title, "deadline_iso": iso, **kw}


def test_같은공지_다른계정이면_묶인다():
    items = [_it("국가장학금 2차 신청", "2026-09-30T18:00"),
             _it("국가장학금 2차 신청", "2026-09-30T18:00")]
    assert merge_duplicates(items) == [[0, 1]]


def test_마감일이_다르면_제목이_같아도_안_묶인다():
    """정정 공지(m13/m24) 케이스. 이번 범위에서는 따로 남는 것이 정상이다."""
    items = [_it("등록금 분할납부 2차분 납부", "2026-09-30"),
             _it("등록금 분할납부 2차분 납부", "2026-10-07")]
    assert merge_duplicates(items) == [[0], [1]]


def test_제목이_덜_닮으면_안_묶인다():
    items = [_it("공모전 접수", "2026-10-05"),
             _it("장학금 신청 서류 제출", "2026-10-05")]
    assert merge_duplicates(items) == [[0], [1]]


def test_유사도_경계값():
    assert config.DUPLICATE_TITLE_SIMILARITY == 0.8


def test_마감없음끼리는_묶지_않는다():
    items = [_it("심리검사 신청", None), _it("심리검사 신청", None)]
    assert merge_duplicates(items) == [[0], [1]]


def test_셋이상도_한_묶음으로():
    items = [_it("동아리 등록 서류 제출", "2026-09-23"),
             _it("동아리 등록 서류 제출", "2026-09-23"),
             _it("동아리 등록 서류 제출", "2026-09-23")]
    assert merge_duplicates(items) == [[0, 1, 2]]


# ══ 오늘 할 일 3가지 ══════════════════════════════════════════════

def test_오늘할일은_우선순위_그다음_마감순():
    items = [_it("여유로운 일", "2026-10-30"),
             _it("오늘 마감", "2026-09-21"),
             _it("내일 마감", "2026-09-22"),
             _it("모레 마감", "2026-09-23")]
    got = [i["title"] for i in today_top(items, MON)]
    assert got == ["오늘 마감", "내일 마감", "모레 마감"]


def test_오늘할일에서_빠지는_것들():
    items = [_it("확인 필요한 일", "2026-09-22", needs_review=True),
             _it("마감 없는 일", None),
             _it("이미 지난 일", "2026-09-18"),
             _it("완료한 일", "2026-09-22", status="done"),
             _it("정상", "2026-09-25")]
    got = [i["title"] for i in today_top(items, MON)]
    assert got == ["정상"]


def test_최대_3개():
    assert config.TODAY_TOP_N == 3
    items = [_it(f"일{i}", "2026-09-22") for i in range(10)]
    assert len(today_top(items, MON)) == 3


# ══ 시각 미기재 처리 ══════════════════════════════════════════════

def test_시각이_없으면_23시59분으로_보되_표시는_남긴다():
    p = parse_deadline("9월 25일(금)까지", WED)
    assert p.time_specified is False           # 화면에 "시각 미기재"를 띄우는 근거
    assert (p.dt.hour, p.dt.minute) == (23, 59)
    assert config.DEFAULT_DEADLINE_HOUR == 23


def test_시각이_있으면_그대로():
    p = parse_deadline("9월 24일(목) 18:00 마감", WED)
    assert p.time_specified is True
    assert (p.dt.hour, p.dt.minute) == (18, 0)


def test_오후표기():
    p = parse_deadline("9월 24일 오후 5시까지", WED)
    assert p.time_specified is True
    assert p.dt.hour == 17
