"""받은편지함 전체를 훑어 목록을 만든다 (AI 전송 없음).

실행:  ./.venv/bin/python scan_imap.py

  - 메일은 읽기 전용으로만 열고 읽음 표시를 건드리지 않습니다
  - 제목·발신자 목록은 `data/메일목록.txt` 에 저장합니다 (내 컴퓨터에만)
  - 화면에는 통계만 찍습니다. 제목을 화면에 찍으면 이 대화를 통해
    Anthropic 으로 전송되기 때문입니다
  - AI 호출은 하지 않습니다
"""

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.collect_imap import ImapError, fetch_recent  # noqa: E402
from app.normalize import normalize  # noqa: E402

# 샘플에서 잰 값 (한국어 기준)
FIXED_TOKENS_PER_MAIL = 3400   # 시스템 프롬프트 등 고정분
TOKENS_PER_CHAR = 0.62
OUTPUT_TOKENS_PER_MAIL = 171

print()
print("=" * 64)
print("  받은편지함 전체 훑기 (AI 전송 없음)")
print("=" * 64)
print()

try:
    mails = fetch_recent(days=0, limit=0)
except ImapError as e:
    print(f"  [실패] {e.message}")
    for h in e.hints:
        print(f"   - {h}")
    sys.exit(1)

if not mails:
    print("  받은편지함이 비어 있습니다.")
    sys.exit(0)

# ── 통계만 화면에 ─────────────────────────────────────────────────
print(f"  메일 {len(mails)}통")
print(f"  기간: {mails[0]['received_at'][:10]} ~ {mails[-1]['received_at'][:10]}")
print()

years = Counter(m["received_at"][:4] for m in mails)
print("  연도별")
for y, n in sorted(years.items()):
    print(f"    {y}년  {n:3d}통  {'#' * min(n, 40)}")
print()

total_chars = 0
html_n = 0
for m in mails:
    norm = normalize(m["body_text"], mask=config.MASK_PII)
    total_chars += len(norm["masked"])
    html_n += 1 if norm["was_html"] else 0

est_in = len(mails) * FIXED_TOKENS_PER_MAIL + int(total_chars * TOKENS_PER_CHAR)
est_out = len(mails) * OUTPUT_TOKENS_PER_MAIL
cost = config.estimate_cost_krw(config.ANTHROPIC_MODEL, est_in, est_out)

print(f"  본문 합계 {total_chars:,}자 (HTML 메일 {html_n}통)")
print(f"  첨부 있는 메일 {sum(1 for m in mails if m['attachment_names'])}통")
print()
print(f"  AI로 보낼 경우 예상")
print(f"    모델   {config.ANTHROPIC_MODEL}")
print(f"    토큰   입력 약 {est_in:,} / 출력 약 {est_out:,}")
print(f"    비용   약 {cost:.0f}원")
print()

# ── 목록은 파일로만 ───────────────────────────────────────────────
out = config.DATA_DIR / "메일목록.txt"
lines = [
    "받은편지함 목록 (이 파일은 내 컴퓨터에만 있고 git 에 올라가지 않습니다)",
    f"총 {len(mails)}통",
    "",
    f"{'번호':<6}{'수신일':<12}{'본문자수':>8}  제목",
    "-" * 90,
]
for i, m in enumerate(mails, 1):
    lines.append(f"{i:<6}{m['received_at'][:10]:<12}{len(m['body_text']):>8}  {m['subject'][:60]}")
out.write_text("\n".join(lines), encoding="utf-8")

print(f"  제목 목록을 저장했습니다: {out.relative_to(ROOT)}")
print()
print("  다음 명령으로 직접 열어보세요 (제 화면에는 안 보입니다):")
print(f"    open -a TextEdit '{out}'")
print()
print("  학사 공지가 들어 있는 번호를 알려주시면 그 메일만 AI로 보낼 수 있습니다.")
print()
