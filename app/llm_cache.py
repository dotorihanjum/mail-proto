"""AI 응답 캐시.

SPEC 12장이 3회 반복 실행과 모델 비교를 요구한다. 캐시가 없으면
화면을 고칠 때마다 30통을 다시 호출하게 된다. 비용보다 시간이 이유다.

키: 모델 + 프롬프트 버전 + 실제로 보낸 본문. 하나라도 바뀌면 새로 호출한다.
"""

import hashlib
import json
from pathlib import Path

from app import config


def _key(model: str, prompt_version: str, payload: str) -> str:
    raw = f"{model}\x00{prompt_version}\x00{payload}".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def get(model: str, prompt_version: str, payload: str) -> dict | None:
    f = config.LLM_CACHE_DIR / f"{_key(model, prompt_version, payload)}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def put(model: str, prompt_version: str, payload: str, value: dict) -> None:
    config.LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    f = config.LLM_CACHE_DIR / f"{_key(model, prompt_version, payload)}.json"
    f.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def clear() -> int:
    n = 0
    for f in Path(config.LLM_CACHE_DIR).glob("*.json"):
        f.unlink()
        n += 1
    return n
