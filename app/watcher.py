"""새 메일 실시간 감시 (IMAP IDLE).

메일 서버가 "새 메일 왔다"고 알려줄 때까지 연결을 열어 두고 기다린다.
주기적으로 물어보는 것보다 빠르고 서버에도 부담이 적다.

  - 연결은 읽기 전용이다. 아무것도 바꾸지 않는다.
  - 알림만 받고 본문은 가져오지 않는다. 가져오기는 사용자가 누를 때 한다.
  - 서버가 보통 30분이면 IDLE 을 끊으므로 29분마다 다시 건다.
  - 앱(웹서버)이 켜져 있는 동안만 동작한다.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

from app import config
from app.collect_imap import ImapError, connect

IDLE_SECONDS = 29 * 60     # 서버가 끊기 전에 먼저 다시 건다
RETRY_SECONDS = 30         # 연결이 끊겼을 때 다시 시도하기까지


class MailWatcher(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True, name="mail-watcher")
        self.events = 0                 # 새 메일 신호를 받은 횟수
        self.last_event_at: str | None = None
        self.status = "아직 시작하지 않음"
        self.error: str | None = None
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> dict:
        return {
            "켜짐": self.is_alive(),
            "상태": self.status,
            "새 메일 신호": self.events,
            "마지막 신호": self.last_event_at,
            "오류": self.error,
        }

    def run(self) -> None:
        while not self._stop.is_set():
            conn = None
            try:
                self.status = "연결 중"
                conn = connect()
                conn.select("INBOX", readonly=True)
                self.error = None
                self.status = "감시 중"

                with conn.idle(duration=IDLE_SECONDS) as idler:
                    for typ, _data in idler:
                        if self._stop.is_set():
                            break
                        # EXISTS = 메일함에 메일이 늘었다는 신호
                        if typ in ("EXISTS", "RECENT"):
                            self.events += 1
                            self.last_event_at = datetime.now().isoformat(
                                timespec="seconds")
                            self.status = "새 메일 감지"
            except ImapError as e:
                self.error = e.message
                self.status = "연결 실패 — 다시 시도 대기"
            except Exception as e:  # 끊김, 타임아웃 등
                self.error = f"{type(e).__name__}: {str(e)[:120]}"
                self.status = "끊김 — 다시 연결 대기"
            finally:
                try:
                    if conn is not None:
                        conn.close()
                        conn.logout()
                except Exception:
                    pass

            if self._stop.is_set():
                break
            if self.error:
                self._stop.wait(RETRY_SECONDS)

        self.status = "멈춤"


_watcher: MailWatcher | None = None


def start() -> dict:
    global _watcher
    if not config.IMAP_USER or not config.IMAP_APP_PASSWORD:
        return {"켜짐": False, "상태": ".env 에 메일 설정이 없습니다"}
    if _watcher is None or not _watcher.is_alive():
        _watcher = MailWatcher()
        _watcher.start()
        time.sleep(0.3)
    return _watcher.snapshot()


def status() -> dict:
    if _watcher is None:
        return {"켜짐": False, "상태": "꺼져 있음", "새 메일 신호": 0,
                "마지막 신호": None, "오류": None}
    return _watcher.snapshot()


def acknowledge() -> None:
    """새 메일을 실제로 가져왔으니 신호를 지운다."""
    if _watcher is not None:
        _watcher.events = 0
        if _watcher.is_alive():
            _watcher.status = "감시 중"


def stop() -> dict:
    global _watcher
    if _watcher is not None:
        _watcher.stop()
    return {"켜짐": False, "상태": "멈추는 중"}
