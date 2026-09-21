"""화면에 보낼 데이터를 조립한다 (SPEC 10장).

섹션
  1. 오늘 할 일 3가지
  2. 확인 필요
  3. 마감 목록 (중복은 한 줄로 묶고 출처를 모두 표시)
  4. 지난 마감
  5. 정리 실패 / 참고용 메일
"""

from __future__ import annotations

import json
from datetime import date

from app import config, db
from app.rules import (PRIORITY_TEXT, days_until, merge_duplicates,
                       priority_of, today_top)
from app.validate import REASON_TEXT


def _load(model: str | None = None) -> tuple[list[dict], dict, str]:
    model = model or config.ANTHROPIC_MODEL
    path = config.DATA_DIR / f"extract_{model}.json"
    if not path.exists():
        return [], {}, model
    data = json.loads(path.read_text(encoding="utf-8"))
    emails = {e["id"]: e for e in json.loads(
        (config.SAMPLES_DIR / "emails.json").read_text(encoding="utf-8"))["emails"]}
    return data["outputs"], emails, data["model"]


def build_view(model: str | None = None) -> dict:
    outs, emails, model = _load(model)
    if not outs:
        return {"ready": False, "model": model}

    today = config.today_for("sample")
    states = db.get_states()

    # 항목을 한 줄로 펴면서 출처 메일 정보를 붙인다
    items: list[dict] = []
    for o in outs:
        if o["status"] != "success":
            continue
        em = emails.get(o["email_id"], {})
        for it in o["result"]["items"]:
            key = db.item_key(it["title"])
            items.append({
                **it,
                "email_id": o["email_id"],
                "item_key": key,
                "account": em.get("account", ""),
                "subject": em.get("subject", ""),
                "sender": em.get("sender", ""),
                "received_at": em.get("received_at", "")[:10],
                "category": o["result"]["category"],
                "status": states.get((o["email_id"], key), "open"),
                "priority_text": PRIORITY_TEXT[it.get("priority", 3)],
                "review_text": [REASON_TEXT.get(r, r) for r in it.get("review_reason", [])],
            })

    # 중복 병합 — 한 줄로 묶고 출처는 전부 남긴다
    groups = merge_duplicates(items)
    merged: list[dict] = []
    for g in groups:
        head = dict(items[g[0]])
        head["sources"] = [{
            "email_id": items[i]["email_id"],
            "account": items[i]["account"],
            "subject": items[i]["subject"],
            "evidence": items[i]["evidence"],
        } for i in g]
        head["is_merged"] = len(g) > 1
        # 묶인 항목 중 하나라도 완료면 완료로 본다
        head["status"] = "done" if any(items[i]["status"] == "done" for i in g) else "open"
        head["member_keys"] = [
            {"email_id": items[i]["email_id"], "item_key": items[i]["item_key"]} for i in g]
        merged.append(head)

    review = [m for m in merged if m.get("needs_review")]
    normal = [m for m in merged if not m.get("needs_review")]
    overdue = [m for m in normal if m.get("is_overdue")]
    upcoming = [m for m in normal if not m.get("is_overdue")]
    upcoming.sort(key=lambda m: (m["deadline_iso"] or "9999", m["title"]))
    overdue.sort(key=lambda m: m["deadline_iso"] or "")

    # 참고용 / 정리 실패
    reference, failed = [], []
    for o in outs:
        em = emails.get(o["email_id"], {})
        base = {"email_id": o["email_id"], "account": em.get("account", ""),
                "subject": em.get("subject", ""), "received_at": em.get("received_at", "")[:10]}
        if o["status"] != "success":
            failed.append({**base, "fail_kind": o.get("fail_kind"),
                           "error_message": o.get("error_message")})
        elif not o["result"]["action_required"]:
            reference.append({**base, "category": o["result"]["category"],
                              "summary": o["result"]["summary"],
                              "injection": o["result"].get("contains_instruction_to_ai", False)})

    return {
        "ready": True,
        "model": model,
        "today": str(today),
        "today_top": today_top(merged, today),
        "needs_review": review,
        "upcoming": upcoming,
        "overdue": overdue,
        "reference": reference,
        "failed": failed,
        "counts": {
            "메일": len(outs),
            "할 일": len(merged),
            "확인 필요": len(review),
            "지남": len(overdue),
            "참고용": len(reference),
            "정리 실패": len(failed),
            "중복 묶음": sum(1 for m in merged if m["is_merged"]),
        },
    }


def email_detail(email_id: str) -> dict | None:
    """원문 보기. 마스킹본도 함께 준다 (SPEC 10장 8번 미리보기)."""
    from app.normalize import normalize

    emails = json.loads(
        (config.SAMPLES_DIR / "emails.json").read_text(encoding="utf-8"))["emails"]
    em = next((e for e in emails if e["id"] == email_id), None)
    if em is None:
        return None
    norm = normalize(em["body_text"], mask=config.MASK_PII)
    return {
        "email_id": em["id"], "account": em["account"], "sender": em["sender"],
        "subject": em["subject"], "received_at": em["received_at"],
        "attachment_names": em["attachment_names"],
        "body_raw": em["body_text"],
        "body_masked": norm["masked"],
        "was_html": norm["was_html"],
        "masked_kinds": norm["masked_kinds"],
    }
