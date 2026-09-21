"""웹 서버 (SPEC 10장).

내 컴퓨터에서만 돈다(127.0.0.1). 외부에서 접속할 수 없다.
메일 본문은 브라우저로만 보내고 로그에는 남기지 않는다.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import config, db, service

app = FastAPI(title="메일 → 할 일 정리 (프로토타입)")
WEB = config.ROOT / "web"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/view")
def api_view(model: str | None = None) -> dict:
    return service.build_view(model)


@app.get("/api/email/{email_id}")
def api_email(email_id: str) -> dict:
    d = service.email_detail(email_id)
    if d is None:
        raise HTTPException(404, f"메일을 찾을 수 없습니다: {email_id}")
    return d


class StatusIn(BaseModel):
    targets: list[dict]   # [{email_id, item_key}, ...] 묶인 항목은 여러 개
    status: str
    title: str = ""
    deadline_date: str | None = None


@app.post("/api/status")
def api_status(body: StatusIn) -> dict:
    if body.status not in ("open", "done"):
        raise HTTPException(400, "status 는 open 또는 done 이어야 합니다.")
    for t in body.targets:
        db.set_state(t["email_id"], t["item_key"], body.status,
                     body.title, body.deadline_date)
    return {"ok": True, "status": body.status, "count": len(body.targets)}


@app.post("/api/extract")
def api_extract(no_cache: bool = False) -> dict:
    """AI로 정리. 캐시가 있으면 즉시 끝난다."""
    import json
    from datetime import date as _date

    import anthropic

    from app.extract import extract_one
    from app.rules import apply_rules
    from app.validate import summarize, validate_extraction

    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(400, "API 키가 없습니다. .env 를 확인하세요.")

    emails = json.loads(
        (config.SAMPLES_DIR / "emails.json").read_text(encoding="utf-8"))["emails"]
    today = str(config.today_for("sample"))
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    outs = []
    for e in emails:
        out = validate_extraction(
            extract_one(client, e, today, use_cache=not no_cache))
        outs.append(apply_rules(out, _date.fromisoformat(e["received_at"][:10]),
                                _date.fromisoformat(today)))

    live = [o for o in outs if not o["from_cache"]]
    cost = config.estimate_cost_krw(
        config.ANTHROPIC_MODEL,
        sum(o["input_tokens"] for o in live),
        sum(o["output_tokens"] for o in live))

    slim = [{k: v for k, v in o.items() if k != "normalized"} for o in outs]
    (config.DATA_DIR / f"extract_{config.ANTHROPIC_MODEL}.json").write_text(
        json.dumps({"model": config.ANTHROPIC_MODEL, "today": today, "outputs": slim},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    s = summarize(outs)
    return {"ok": True, "요약": {k: v for k, v in s.items() if k != "실패 종류"},
            "실제 호출": len(live), "비용원": round(cost)}


app.mount("/static", StaticFiles(directory=WEB), name="static")
