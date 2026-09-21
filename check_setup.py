"""
설정이 제대로 됐는지 확인하는 스크립트.

실행:  ./.venv/bin/python check_setup.py

API를 딱 1번 호출합니다. 비용은 1원 미만입니다.
이 스크립트는 API 키 값을 화면이나 파일에 출력하지 않습니다.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

OK = "  [OK] "
NG = "  [실패] "


def fail(message: str, how_to_fix: str) -> None:
    print(NG + message)
    print()
    print("  ── 해결 방법 ──")
    for line in how_to_fix.strip().split("\n"):
        print("  " + line)
    print()
    sys.exit(1)


print()
print("=" * 60)
print("  설정 확인을 시작합니다")
print("=" * 60)
print()

# ── 1. 파이썬 버전 ────────────────────────────────────────────────
print("1) 파이썬 버전")
major, minor = sys.version_info[:2]
if (major, minor) < (3, 11):
    fail(
        f"파이썬 {major}.{minor} 입니다. 3.11 이상이 필요합니다.",
        "가상환경이 잘못 잡혔을 수 있습니다. 아래 명령으로 다시 실행해 보세요.\n"
        "  ./.venv/bin/python check_setup.py",
    )
print(OK + f"파이썬 {major}.{minor}")

# ── 2. 패키지 ─────────────────────────────────────────────────────
print()
print("2) 필요한 패키지")
try:
    import anthropic  # noqa: F401
    import pydantic  # noqa: F401
    import dotenv  # noqa: F401
except ImportError as e:
    fail(
        f"패키지를 찾을 수 없습니다: {e.name}",
        "아래 명령을 실행하세요.\n"
        "  ./.venv/bin/pip install -r requirements.txt",
    )
print(OK + f"anthropic {anthropic.__version__}, pydantic {pydantic.__version__}")

# ── 3. .env 파일 ──────────────────────────────────────────────────
print()
print("3) .env 설정 파일")
if not (ROOT / ".env").exists():
    fail(
        ".env 파일이 없습니다.",
        "아래 명령으로 예시 파일을 복사한 뒤, 열어서 API 키를 넣으세요.\n"
        "  cp .env.example .env",
    )

from app import config  # noqa: E402

if not config.ANTHROPIC_API_KEY:
    fail(
        "ANTHROPIC_API_KEY 가 비어 있습니다.",
        ".env 파일을 열어서 ANTHROPIC_API_KEY= 뒤에 키를 붙여넣고 저장하세요.\n"
        "키는 console.anthropic.com → API Keys 에서 발급합니다.\n"
        "따옴표 없이, 등호 뒤에 바로 붙여넣으면 됩니다.",
    )
if not config.ANTHROPIC_API_KEY.startswith("sk-ant-"):
    fail(
        "ANTHROPIC_API_KEY 모양이 이상합니다. (sk-ant- 로 시작해야 합니다)",
        ".env 파일을 다시 확인하세요. 따옴표가 섞여 들어가지 않았는지,\n"
        "앞뒤에 공백이 붙지 않았는지 보세요.",
    )
# 키 값 자체는 절대 출력하지 않는다. 길이만 알려준다.
print(OK + f".env 읽음 (API 키 {len(config.ANTHROPIC_API_KEY)}자 확인)")
print(OK + f"사용할 모델: {config.ANTHROPIC_MODEL}")

# ── 4. API 호출 1회 ───────────────────────────────────────────────
print()
print("4) Claude API 호출 (1회, 1원 미만)")

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

try:
    resp = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=64,
        messages=[{"role": "user", "content": "연결 확인 중입니다. '준비 완료'라고만 답하세요."}],
    )
except anthropic.AuthenticationError:
    fail(
        "API 키가 거부되었습니다.",
        "키가 틀렸거나 삭제되었을 수 있습니다.\n"
        "console.anthropic.com → API Keys 에서 키를 새로 만들어\n"
        ".env 의 ANTHROPIC_API_KEY 값을 교체하세요.",
    )
except anthropic.NotFoundError:
    fail(
        f"'{config.ANTHROPIC_MODEL}' 모델을 찾을 수 없습니다.",
        ".env 의 ANTHROPIC_MODEL 값을 확인하세요. 철자가 정확해야 합니다.\n"
        "  ANTHROPIC_MODEL=claude-haiku-4-5",
    )
except anthropic.RateLimitError:
    fail(
        "요청이 너무 잦습니다. (rate limit)",
        "1분 정도 기다렸다가 다시 실행하세요.",
    )
except anthropic.APIStatusError as e:
    detail = str(e)
    if "credit balance" in detail.lower() or "billing" in detail.lower():
        fail(
            "API 잔액이 부족합니다.",
            "console.anthropic.com → Billing 에서 결제 수단을 등록하고\n"
            "최소 $5 를 충전한 뒤 다시 실행하세요.\n"
            "(Claude 구독료와는 별개로 청구됩니다)",
        )
    fail(
        f"API가 오류를 돌려줬습니다. (HTTP {e.status_code})",
        f"오류 내용: {detail[:300]}\n"
        "잠시 후 다시 시도해 보고, 계속 같으면 이 메시지를 알려주세요.",
    )
except anthropic.APIConnectionError:
    fail(
        "인터넷 연결에 실패했습니다.",
        "네트워크 연결을 확인하세요.\n"
        "회사·학교 와이파이라면 방화벽이 막고 있을 수 있습니다.",
    )

answer = "".join(b.text for b in resp.content if b.type == "text").strip()
print(OK + f"응답 받음: \"{answer}\"")

usage = resp.usage
cost = config.estimate_cost_krw(config.ANTHROPIC_MODEL, usage.input_tokens, usage.output_tokens)
print(OK + f"토큰: 입력 {usage.input_tokens} / 출력 {usage.output_tokens}  (약 {cost:.2f}원)")

# ── 5. 폴더 ───────────────────────────────────────────────────────
print()
print("5) 폴더")
config.DATA_DIR.mkdir(exist_ok=True)
config.LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
print(OK + "data/ 준비됨 (git에 올라가지 않음)")

print()
print("=" * 60)
print("  모든 확인을 통과했습니다. M2로 넘어갈 수 있습니다.")
print("=" * 60)
print()
