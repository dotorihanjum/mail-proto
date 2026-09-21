"""로컬 저장 (SQLite).

지금은 ERD 중 item_states 만 만든다. 완료 체크가 화면에서 바꿀 수 있는
유일한 값이고, AI 를 다시 돌려도 살아남아야 하기 때문이다.
나머지 테이블은 실제로 필요해질 때(M6 모델 비교, M7 실제 메일) 만든다.

DB 파일은 data/ 안에 있고 data/ 는 .gitignore 에 들어 있다.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from app import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS item_states (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id       TEXT NOT NULL,
    item_key       TEXT NOT NULL,
    title_snapshot TEXT,
    deadline_date  TEXT,
    status         TEXT NOT NULL DEFAULT 'open',
    updated_at     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_item_states
    ON item_states(email_id, item_key);
"""


def item_key(title: str) -> str:
    """제목에서 띄어쓰기·문장부호를 걷어낸 값.

    AI 가 같은 항목을 조금 다르게 부르면 키가 달라져 완료 체크가 풀린다.
    완전히 막을 수는 없다. 풀리는 쪽이 안전한 실패이므로 그대로 둔다.
    """
    return re.sub(r"[\s·,.\-()\[\]/]+", "", title).lower()


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def get_states() -> dict[tuple[str, str], str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT email_id, item_key, status FROM item_states").fetchall()
    return {(r["email_id"], r["item_key"]): r["status"] for r in rows}


def set_state(email_id: str, key: str, status: str,
              title: str = "", deadline_date: str | None = None) -> None:
    if status not in ("open", "done"):
        raise ValueError(f"status 는 open 또는 done 이어야 합니다: {status!r}")
    with connect() as conn:
        conn.execute(
            """INSERT INTO item_states
                   (email_id, item_key, title_snapshot, deadline_date, status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(email_id, item_key) DO UPDATE SET
                   status = excluded.status,
                   title_snapshot = excluded.title_snapshot,
                   deadline_date = excluded.deadline_date,
                   updated_at = excluded.updated_at""",
            (email_id, key, title, deadline_date, status,
             datetime.now().isoformat(timespec="seconds")))
