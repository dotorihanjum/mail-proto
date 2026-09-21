"""
설정과 튜닝 상수를 모으는 곳.

규칙: 나중에 조정할 가능성이 있는 숫자는 코드 여기저기에 흩뿌리지 말고
      전부 이 파일에 `# TUNE:` 주석과 함께 둔다.
"""

import os
from pathlib import Path
from datetime import date

from dotenv import load_dotenv

# ── 경로 ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SAMPLES_DIR = ROOT / "samples"
REPORTS_DIR = ROOT / "reports"
DB_PATH = DATA_DIR / "mail.db"
LLM_CACHE_DIR = DATA_DIR / "llm_cache"

load_dotenv(ROOT / ".env")

# ── .env 값 ───────────────────────────────────────────────────────
# 주의: 이 값들을 print 하거나 로그에 남기지 않는다. (CLAUDE.md 규칙 3)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5").strip()
MASK_PII = os.getenv("MASK_PII", "true").strip().lower() == "true"

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com").strip()
IMAP_USER = os.getenv("IMAP_USER", "").strip()
IMAP_APP_PASSWORD = os.getenv("IMAP_APP_PASSWORD", "").replace(" ", "")

_today_override = os.getenv("TODAY_OVERRIDE", "").strip()


def today_for(source: str) -> date:
    """기준일을 돌려준다.

    TODAY_OVERRIDE는 샘플 모드에서만 적용한다.
    실제 메일(source="imap")에는 언제나 진짜 오늘을 쓴다.
    — 이걸 구분하지 않으면 실제 메일의 D-day가 전부 틀어진다.
    """
    if source == "sample" and _today_override:
        return date.fromisoformat(_today_override)
    return date.today()


# ── 판정 임계값 ───────────────────────────────────────────────────
# TUNE: 확인 필요로 보낼 신뢰도 경계. SPEC 9장의 "상한 0.7"과 짝이 맞아야
#       하므로 '미만'이 아니라 '이하'다. (0.7이 통과되면 코드가 해석 못 한
#       날짜가 확정된 것처럼 보이는 버그가 생긴다)
CONFIDENCE_REVIEW_MAX = 0.7

# TUNE: 코드가 날짜 표현을 해석하지 못했을 때 AI 신뢰도에 씌우는 상한.
UNPARSED_DATE_CONFIDENCE_CAP = 0.7

# TUNE: 연도가 없는 날짜("10/5까지")를 미래로 해석할 최대 범위(개월).
#       넘으면 확인 필요로 보낸다. 회고성 메일의 "1/5"가 D-106이 되는 것을 막는다.
YEAR_INFERENCE_MAX_MONTHS = 6

# TUNE: 중복으로 묶을 제목 유사도 (difflib ratio)
DUPLICATE_TITLE_SIMILARITY = 0.8

# TUNE: 시각이 안 적힌 마감을 몇 시로 볼지. 화면에는 "시각 미기재"를 표시한다.
DEFAULT_DEADLINE_HOUR = 23
DEFAULT_DEADLINE_MINUTE = 59

# 우선순위 경계 (D-day 기준)
PRIORITY_URGENT_DAYS = 1
PRIORITY_HIGH_DAYS = 3
PRIORITY_NORMAL_DAYS = 7

TODAY_TOP_N = 3

# ── IMAP 수집 범위 (M7) ───────────────────────────────────────────
IMAP_RECENT_DAYS = 14
IMAP_MAX_MESSAGES = 50

# ── 요금 (2026-06 기준, 100만 토큰당 USD) ─────────────────────────
MODEL_PRICING = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
}
USD_TO_KRW = 1400


def estimate_cost_krw(model: str, input_tokens: int, output_tokens: int) -> float:
    """대략의 원화 비용. 리포트에 표시할 용도."""
    if model not in MODEL_PRICING:
        return 0.0
    in_price, out_price = MODEL_PRICING[model]
    usd = (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price
    return usd * USD_TO_KRW
