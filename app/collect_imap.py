"""IMAP 읽기 전용 수집 (SPEC 13장).

절대 지킬 것 (SPEC 9장 안전장치 1)
  - 메일함을 readonly=True 로 연다
  - 본문은 BODY.PEEK 으로 가져온다 -> 읽음 표시가 붙지 않는다
  - 삭제·이동·플래그 변경 코드를 두지 않는다
  - 본문과 개인정보를 로그·콘솔에 출력하지 않는다 (제목 일부와 id 정도만)
"""

from __future__ import annotations

import email
import imaplib
import re
from datetime import date, datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

from app import config


class ImapError(Exception):
    """사용자에게 보여줄 한국어 안내를 담는다."""

    def __init__(self, message: str, hints: list[str]):
        super().__init__(message)
        self.message = message
        self.hints = hints


def _decode(raw: str | None) -> str:
    """=?UTF-8?B?...?= 같은 헤더를 사람이 읽을 수 있게 푼다."""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except (UnicodeDecodeError, LookupError, ValueError):
        return raw


def connect() -> imaplib.IMAP4_SSL:
    """로그인까지 한다. 실패하면 한국어 안내를 담아 던진다."""
    missing = [n for n, v in (("IMAP_USER", config.IMAP_USER),
                              ("IMAP_APP_PASSWORD", config.IMAP_APP_PASSWORD))
               if not v]
    if missing:
        # 무엇이 비었는지 정확히 짚어준다. 둘 다 비었다고 뭉뚱그리면
        # 이미 채운 쪽을 계속 다시 보게 된다.
        raise ImapError(
            f".env 의 {' 와 '.join(missing)} 가 비어 있습니다.",
            [f"`.env` 파일 안에서 `{missing[0]}=` 로 시작하는 줄을 찾아 "
             f"등호 뒤에 값을 넣고 저장하세요.",
             "앱 비밀번호는 띄어쓰기를 빼고 16자만 붙여넣습니다.",
             "파일 위치: " + str(config.ROOT / ".env")])
    if len(config.IMAP_APP_PASSWORD) != 16:
        raise ImapError(
            f"앱 비밀번호가 16자가 아닙니다. (지금 {len(config.IMAP_APP_PASSWORD)}자)",
            ["구글이 준 16자리를 띄어쓰기 없이 붙여넣었는지 확인하세요.",
             "평소 쓰는 비밀번호가 아니라 앱 비밀번호여야 합니다."])
    try:
        conn = imaplib.IMAP4_SSL(config.IMAP_HOST, 993, timeout=20)
    except OSError as e:
        raise ImapError(
            f"{config.IMAP_HOST} 에 연결하지 못했습니다.",
            ["인터넷 연결을 확인하세요.",
             "학교 관리자가 IMAP 접속을 막아 두었을 수 있습니다.",
             f"기술적 내용: {type(e).__name__}"]) from e

    try:
        conn.login(config.IMAP_USER, config.IMAP_APP_PASSWORD)
    except imaplib.IMAP4.error as e:
        detail = str(e)
        hints = [
            "앱 비밀번호를 썼는지 확인하세요. 평소 쓰는 비밀번호로는 안 됩니다.",
            "띄어쓰기가 섞여 들어가지 않았는지 보세요. 16자여야 합니다.",
            "2단계 인증이 켜져 있어야 앱 비밀번호가 동작합니다.",
        ]
        if "Application-specific password required" in detail:
            hints.insert(0, "일반 비밀번호를 넣으신 것 같습니다. 앱 비밀번호가 필요합니다.")
        elif "Invalid credentials" in detail:
            hints.insert(0, "아이디나 앱 비밀번호가 틀렸습니다.")
        else:
            hints.append("학교 정책이 앱 비밀번호를 막았을 수 있습니다 → 경희대 IT Desk 문의")
        try:
            conn.logout()
        except Exception:
            pass
        raise ImapError("메일 서버 로그인에 실패했습니다.", hints) from e

    return conn


def _body_text(msg: email.message.Message) -> tuple[str, list[str]]:
    """본문 글자와 첨부 파일 '이름만' 꺼낸다. 첨부 내용은 읽지 않는다."""
    attachments: list[str] = []
    plain, html = "", ""

    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        disp = str(part.get("Content-Disposition") or "")
        fname = part.get_filename()
        if fname or "attachment" in disp:
            if fname:
                attachments.append(_decode(fname))
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except LookupError:
            text = payload.decode("utf-8", errors="replace")
        if ctype == "text/plain":
            plain += text
        else:
            html += text

    return (plain or html), attachments


def fetch_recent(days: int | None = None, limit: int | None = None,
                 account_name: str = "학교") -> list[dict]:
    """최근 메일을 읽어 샘플과 같은 모양으로 돌려준다.

    읽음 표시를 건드리지 않는다.
    """
    days = days if days is not None else config.IMAP_RECENT_DAYS
    limit = limit if limit is not None else config.IMAP_MAX_MESSAGES

    conn = connect()
    out: list[dict] = []
    try:
        # readonly=True : 이 연결로는 어떤 변경도 일어나지 않는다
        typ, _ = conn.select("INBOX", readonly=True)
        if typ != "OK":
            raise ImapError("받은편지함을 열지 못했습니다.",
                            ["메일함 이름이 다를 수 있습니다."])

        if days and days > 0:
            since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
            criteria = f'(SINCE "{since}")'
        else:
            criteria = "ALL"   # days=0 이면 받은편지함 전체
        typ, data = conn.search(None, criteria)
        if typ != "OK":
            raise ImapError("메일 검색에 실패했습니다.", ["잠시 후 다시 시도해 보세요."])

        ids = data[0].split()
        ids = ids[-limit:] if limit else ids

        for num in ids:
            # BODY.PEEK : 읽음 표시(\Seen)를 붙이지 않고 가져온다
            typ, raw = conn.fetch(num, "(BODY.PEEK[])")
            if typ != "OK" or not raw or not isinstance(raw[0], tuple):
                continue
            msg = email.message_from_bytes(raw[0][1])
            body, attach = _body_text(msg)

            try:
                received = parsedate_to_datetime(msg.get("Date")).astimezone()
            except (TypeError, ValueError):
                received = datetime.now().astimezone()

            mid = _decode(msg.get("Message-ID")) or f"<no-id-{num.decode()}>"
            out.append({
                "id": f"k{num.decode()}",
                "account": account_name,
                "source": "imap",
                "message_id": mid,
                "received_at": received.isoformat(timespec="seconds"),
                "sender": _decode(msg.get("From")),
                "subject": _decode(msg.get("Subject")) or "(제목 없음)",
                "body_text": body,
                "attachment_names": attach,
            })
    finally:
        try:
            conn.close()
            conn.logout()
        except Exception:
            pass

    out.sort(key=lambda e: e["received_at"])
    return out


def flag_report(days: int, limit: int) -> list[dict]:
    """읽음/안읽음 상태만 확인한다. 본문을 가져오지 않는다.

    BODY.PEEK 이 정말로 읽음 표시를 건드리지 않았는지 대조하는 용도다.
    """
    conn = connect()
    rows: list[dict] = []
    try:
        conn.select("INBOX", readonly=True)
        since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = conn.search(None, f'(SINCE "{since}")')
        ids = data[0].split()[-limit:] if typ == "OK" else []
        for num in ids:
            typ, d = conn.fetch(num, "(FLAGS)")
            flags = d[0].decode(errors="replace") if typ == "OK" and d and d[0] else ""
            rows.append({"id": num.decode(),
                         "읽음": "\\Seen" in flags})
    finally:
        try:
            conn.close()
            conn.logout()
        except Exception:
            pass
    return rows


# ── 증분 수집 (UID 기준) ──────────────────────────────────────────
# 받은편지함을 매번 통째로 읽으면 메일이 쌓일수록 느려진다.
# IMAP 의 UID 는 메일함 안에서 증가만 하므로, 마지막으로 본 UID 뒤쪽만
# 가져오면 된다. 단 UIDVALIDITY 가 바뀌면 UID 가 전부 무효가 되므로
# 그때는 전체를 다시 읽는다.

def _state_path():
    return config.DATA_DIR / "imap_state.json"


def load_state() -> dict:
    import json
    p = _state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(uidvalidity: int, last_uid: int) -> None:
    import json
    config.DATA_DIR.mkdir(exist_ok=True)
    _state_path().write_text(
        json.dumps({"uidvalidity": uidvalidity, "last_uid": last_uid}),
        encoding="utf-8")


def _msg_to_dict(num: bytes, msg, account_name: str) -> dict:
    body, attach = _body_text(msg)
    try:
        received = parsedate_to_datetime(msg.get("Date")).astimezone()
    except (TypeError, ValueError):
        received = datetime.now().astimezone()
    mid = _decode(msg.get("Message-ID")) or f"<no-id-{num.decode()}>"
    return {
        "id": f"k{num.decode()}",
        "account": account_name,
        "source": "imap",
        "message_id": mid,
        "received_at": received.isoformat(timespec="seconds"),
        "sender": _decode(msg.get("From")),
        "subject": _decode(msg.get("Subject")) or "(제목 없음)",
        "body_text": body,
        "attachment_names": attach,
    }


def fetch_incremental(account_name: str = "학교") -> tuple[list[dict], bool]:
    """마지막으로 읽은 뒤에 온 메일만 가져온다.

    돌려주는 값: (메일 목록, 전체를 다시 읽었는가)
    읽음 표시는 건드리지 않는다.
    """
    conn = connect()
    out: list[dict] = []
    try:
        conn.select("INBOX", readonly=True)
        raw = conn.response("UIDVALIDITY")[1]
        uidvalidity = int(raw[0]) if raw and raw[0] else 0

        state = load_state()
        last_uid = int(state.get("last_uid", 0))
        # UIDVALIDITY 가 달라졌다면 예전 UID 는 못 믿는다 -> 전부 다시
        full = state.get("uidvalidity") != uidvalidity or last_uid <= 0

        if full:
            typ, data = conn.uid("search", None, "ALL")
        else:
            typ, data = conn.uid("search", None, f"UID {last_uid + 1}:*")
        if typ != "OK":
            raise ImapError("메일 검색에 실패했습니다.", ["잠시 후 다시 시도해 보세요."])

        uids = [u for u in data[0].split() if int(u) > last_uid or full]
        for uid in uids:
            typ, raw2 = conn.uid("fetch", uid, "(BODY.PEEK[])")
            if typ != "OK" or not raw2 or not isinstance(raw2[0], tuple):
                continue
            out.append(_msg_to_dict(uid, email.message_from_bytes(raw2[0][1]),
                                    account_name))

        if uids:
            save_state(uidvalidity, max(int(u) for u in uids))
        elif full:
            save_state(uidvalidity, last_uid)
    finally:
        try:
            conn.close()
            conn.logout()
        except Exception:
            pass

    out.sort(key=lambda e: e["received_at"])
    return out, full
