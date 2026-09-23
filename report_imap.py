"""실제 메일 처리 결과를 내가 직접 대조할 수 있게 파일로 뽑는다.

실행:  ./.venv/bin/python report_imap.py

결과는 data/ 안에만 저장된다. 화면에는 통계만 찍는다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.validate import REASON_TEXT  # noqa: E402

path = config.DATA_DIR / f"extract_imap_{config.ANTHROPIC_MODEL}.json"
if not path.exists():
    print("먼저 ./.venv/bin/python -m app.extract --source imap 를 실행하세요.")
    sys.exit(1)

outs = json.loads(path.read_text(encoding="utf-8"))["outputs"]
# 저장해 둔 메일을 쓴다. 메일 서버를 다시 부르지 않는다.
cached = config.DATA_DIR / "emails_imap.json"
if not cached.exists():
    print("먼저 메일을 가져와야 합니다: python -m app.extract --source imap")
    sys.exit(1)
mails = {m["id"]: m for m in
         json.loads(cached.read_text(encoding="utf-8"))["emails"]}

L = []
w = L.append
w("# 실제 메일 처리 결과 — 직접 대조용\n")
w("이 파일은 내 컴퓨터에만 있습니다. git 에 올라가지 않습니다.\n")
w("AI가 뽑은 할 일이 **맞는지 틀린지** 원문과 대조해 주세요.\n")
w("---\n")

w("## AI가 찾은 할 일\n")
found = False
for o in outs:
    if o["status"] != "success" or not o["result"]["items"]:
        continue
    found = True
    m = mails.get(o["email_id"], {})
    w(f"### {o['email_id']} · {m.get('received_at','')[:10]}")
    w(f"**{m.get('subject','(제목 없음)')}**\n")
    w(f"- 보낸이: {m.get('sender','')}")
    w(f"- 분류: {o['result']['category']}")
    w(f"- 요약: {o['result']['summary']}\n")
    for it in o["result"]["items"]:
        w(f"| | |")
        w(f"|---|---|")
        w(f"| 할 일 | {it['title']} |")
        w(f"| 마감일 | {it['deadline_iso'] or '못 찾음'} |")
        w(f"| 원문 표현 | {it['deadline_text'] or '—'} |")
        w(f"| AI 계산 / 규칙 계산 | {it.get('deadline_ai')} / {it.get('deadline_rule')} |")
        w(f"| 기한이 있는 종류인가 | {'예' if it.get('deadline_expected') else '아니오 (언제든 하면 되는 일)'} |")
        w(f"| 신뢰도 | {it['confidence']} |")
        w(f"| D-day | {it.get('dday')} |")
        w(f"| 확인 필요 사유 | {', '.join(REASON_TEXT.get(r, r) for r in it.get('review_reason', []))} |")
        w(f"| 근거가 본문에 실제로 있었나 | {'예' if it.get('evidence_verified') else '**아니오 — 확인 필요**'} |")
        w("")
        w(f"> 근거로 든 문장: {it['evidence']}\n")
    w("---\n")
if not found:
    w("없습니다.\n")

w("## 인증·보안으로 분류된 메일\n")
w("할 일 목록에서 빼고 별도 목록으로 모은 것들입니다. **아닌 것이 섞여 있는지** 봐주세요.\n")
w("| 메일 | 수신일 | 제목 |")
w("|---|---|---|")
for o in outs:
    if o["status"] != "success" or o["result"]["category"] != "인증·보안":
        continue
    m = mails.get(o["email_id"], {})
    w(f"| {o['email_id']} | {m.get('received_at','')[:10]} | {m.get('subject','')[:55]} |")
w("")

w("## 할 일 없음으로 분류된 메일 (오탐이 없는지 훑어보세요)\n")
w("여기에 **진짜 마감이 있는 메일이 섞여 있으면 '놓침'** 입니다.\n")
w("| 메일 | 수신일 | 분류 | 제목 |")
w("|---|---|---|---|")
for o in outs:
    if o["status"] != "success" or o["result"]["items"]:
        continue
    if o["result"]["category"] == "인증·보안":
        continue   # 위에 따로 적었다
    m = mails.get(o["email_id"], {})
    w(f"| {o['email_id']} | {m.get('received_at','')[:10]} | "
      f"{o['result']['category']} | {m.get('subject','')[:55]} |")
w("")

fails = [o for o in outs if o["status"] != "success"]
w(f"## 정리 실패 {len(fails)}건\n")
for o in fails:
    m = mails.get(o["email_id"], {})
    w(f"- {o['email_id']} {m.get('subject','')[:50]} — {o.get('fail_kind')}: {o.get('error_message')}")
if not fails:
    w("없습니다.\n")

out = config.DATA_DIR / "실제메일_결과.md"
out.write_text("\n".join(L), encoding="utf-8")
print()
print(f"  저장 완료: {out}")
print()
print("  열어보기:")
print(f"    open -a TextEdit '{out}'")
print()
print("  봐주실 것")
print("   1. '찾은 할 일'이 실제로 맞는 마감인가")
print("   2. '할 일 없음' 목록에 진짜 마감이 섞여 있지 않은가  <- 가장 중요")
print("   3. 근거 문장이 원문에 실제로 있는가 (실패한 것은 표에 표시됨)")
print("   4. 인증·보안 목록에 아닌 것이 섞여 있지 않은가")
print()
