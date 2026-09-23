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


def _load(model: str | None = None,
          source: str = "sample") -> tuple[list[dict], dict, str]:
    model = model or config.ANTHROPIC_MODEL
    suffix = "" if source == "sample" else f"_{source}"
    path = config.DATA_DIR / f"extract{suffix}_{model}.json"
    if not path.exists():
        return [], {}, model
    data = json.loads(path.read_text(encoding="utf-8"))
    if source == "imap":
        cached = config.DATA_DIR / "emails_imap.json"
        if not cached.exists():
            return [], {}, model
        emails = {m["id"]: m for m in
                  json.loads(cached.read_text(encoding="utf-8"))["emails"]}
    else:
        emails = {e["id"]: e for e in json.loads(
            (config.SAMPLES_DIR / "emails.json").read_text(encoding="utf-8"))["emails"]}
    return data["outputs"], emails, data["model"]


def build_view(model: str | None = None, source: str = "sample") -> dict:
    outs, emails, model = _load(model, source)
    if not outs:
        return {"ready": False, "model": model}

    today = config.today_for(source)
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

    # 마감이 있는 일 / 언제든 하면 되는 일을 나눈다.
    # 기한이 없는 것이 정상인 할 일(진료확인서 제출 등)을 "확인 필요"에
    # 쌓아두면 그 섹션이 무의미해진다.
    anytime = [m for m in normal if not m.get("deadline_iso")]
    dated = [m for m in normal if m.get("deadline_iso")]
    overdue = [m for m in dated if m.get("is_overdue")]
    upcoming = [m for m in dated if not m.get("is_overdue")]
    upcoming.sort(key=lambda m: (m["deadline_iso"] or "9999", m["title"]))
    overdue.sort(key=lambda m: m["deadline_iso"] or "")
    anytime.sort(key=lambda m: m["received_at"], reverse=True)

    # 인증 / 참고용 / 정리 실패
    verification, reference, failed = [], [], []
    for o in outs:
        em = emails.get(o["email_id"], {})
        base = {"email_id": o["email_id"], "account": em.get("account", ""),
                "subject": em.get("subject", ""),
                "received_at": em.get("received_at", "")[:10]}
        if o["status"] != "success":
            failed.append({**base, "fail_kind": o.get("fail_kind"),
                           "error_message": o.get("error_message")})
            continue
        cat = o["result"]["category"]
        entry = {**base, "category": cat, "summary": o["result"]["summary"],
                 "injection": o["result"].get("contains_instruction_to_ai", False)}
        if cat == "인증·보안":
            # 인증 메일은 받는 즉시 쓰는 것이라 할 일 목록에 두지 않는다.
            # 대신 "필요할 때 찾아보는" 별도 목록으로 모은다. 최신이 위로.
            verification.append(entry)
        elif not o["result"]["action_required"]:
            reference.append(entry)
    verification.sort(key=lambda v: v["received_at"], reverse=True)

    return {
        "ready": True,
        "model": model,
        "source": source,
        "today": str(today),
        "today_top": today_top(merged, today),
        "needs_review": review,
        "upcoming": upcoming,
        "anytime": anytime,
        "overdue": overdue,
        "verification": verification,
        "reference": reference,
        "failed": failed,
        "counts": {
            "메일": len(outs),
            "마감 있는 할 일": len(upcoming),
            "언제든 하는 일": len(anytime),
            "확인 필요": len(review),
            "지남": len(overdue),
            "인증": len(verification),
            "참고용": len(reference),
            "정리 실패": len(failed),
            "중복 묶음": sum(1 for m in merged if m["is_merged"]),
        },
    }


def email_detail(email_id: str, source: str = "sample") -> dict | None:
    """원문 보기. 마스킹본도 함께 준다 (SPEC 10장 8번 미리보기)."""
    from app.normalize import normalize

    if source == "imap":
        cached = config.DATA_DIR / "emails_imap.json"
        if not cached.exists():
            return None
        emails = json.loads(cached.read_text(encoding="utf-8"))["emails"]
    else:
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
