"""경희대 메일 연결 시험 (SPEC 13장 체크리스트 1~3).

실행:  ./.venv/bin/python check_imap.py

이 스크립트는
  - 메일을 읽기 전용으로만 엽니다
  - 읽음 표시를 건드리지 않습니다
  - 본문을 화면에 찍지 않습니다 (제목과 글자 수만)
  - 어떤 내용도 외부(AI 서비스)로 보내지 않습니다
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.collect_imap import ImapError, fetch_recent, flag_report  # noqa: E402

DAYS = 3      # 첫 시험이니 작게 잡는다
LIMIT = 5

print()
print("=" * 64)
print("  경희대 메일 연결 시험 (읽기 전용, 외부 전송 없음)")
print("=" * 64)
print()
print(f"  서버   : {config.IMAP_HOST}:993 (SSL)")
print(f"  범위   : 최근 {DAYS}일, 최대 {LIMIT}통")
print()

try:
    # ── 1) 가져오기 전 읽음 상태 ──────────────────────────────────
    print("1) 가져오기 전 읽음 상태 확인")
    before = flag_report(DAYS, LIMIT)
    if not before:
        print("   최근 메일이 없습니다. DAYS 값을 늘려 다시 시도해 보세요.")
        sys.exit(0)
    unread_before = [r["id"] for r in before if not r["읽음"]]
    print(f"   메일 {len(before)}통 중 읽지 않음 {len(unread_before)}통")
    print()

    # ── 2) 본문 가져오기 ─────────────────────────────────────────
    print("2) 메일 가져오기 (BODY.PEEK)")
    mails = fetch_recent(days=DAYS, limit=LIMIT)
    print(f"   {len(mails)}통 가져옴")
    print()

    # ── 3) 제목이 한글로 정상 표시되는가 ─────────────────────────
    print("3) 제목 확인 (본문은 찍지 않습니다)")
    for m in mails:
        sender = m["sender"].split("<")[0].strip()[:18] or "(발신자 미상)"
        print(f"   [{m['received_at'][:10]}] {m['subject'][:40]}")
        print(f"       보낸이 {sender} · 본문 {len(m['body_text'])}자"
              + (f" · 첨부 {len(m['attachment_names'])}개" if m["attachment_names"] else ""))
    print()

    # ── 4) 읽음 상태가 그대로인가 ────────────────────────────────
    print("4) 가져온 뒤 읽음 상태 재확인")
    after = flag_report(DAYS, LIMIT)
    unread_after = [r["id"] for r in after if not r["읽음"]]
    changed = sorted(set(unread_before) - set(unread_after))
    print(f"   메일 {len(after)}통 중 읽지 않음 {len(unread_after)}통")
    if changed:
        print(f"   [실패] 읽지 않음이던 메일 {len(changed)}통이 읽음으로 바뀌었습니다: {changed}")
        print("          BODY.PEEK 가 제대로 동작하지 않았습니다. 코드를 고쳐야 합니다.")
    else:
        print("   [OK] 읽지 않음 상태가 그대로입니다.")
    print()

    print("=" * 64)
    print("  체크리스트")
    print("=" * 64)
    print("   1. 연결 성공                 [OK]")
    print(f"   2. 제목이 한글로 정상 표시     {'[OK]' if any(m['subject'] != '(제목 없음)' for m in mails) else '[확인 필요]'}")
    print(f"   3. 읽지 않음 상태 유지        {'[OK]' if not changed else '[실패]'}")
    print("   4. 같은 처리 과정 동작         (아직 — AI 전송 단계, 따로 결정)")
    print("   5. 사람이 원문과 대조          (아직)")
    print()
    print("  여기까지 외부로 나간 정보는 없습니다.")
    print("  웹메일에서 직접 열어 읽지 않음 표시가 그대로인지 확인해 보세요.")
    print()

except ImapError as e:
    print()
    print(f"  [실패] {e.message}")
    print()
    print("  ── 해볼 것 ──")
    for h in e.hints:
        print(f"   - {h}")
    print()
    print("  막히면 M7 을 보류하고 M1~M6 결과로 마무리해도 됩니다.")
    print("  경희대 정책은 우리가 바꿀 수 없습니다. (SPEC 13장)")
    print()
    sys.exit(1)
