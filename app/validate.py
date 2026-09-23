"""AI 출력 검증 (SPEC 6장 '검증' 단계, 9장 안전장치).

M3 에서 할 수 있는 검사:
  - 근거 문장이 AI 가 실제로 본 본문(마스킹본) 안에 있는가
  - action_required 가 true 인데 항목이 하나도 없는가
  - 신뢰도가 낮은가 / 마감이 없는가

M4 에서 추가될 검사 (규칙 코드의 날짜 파서가 필요):
  - AI 날짜와 코드 날짜가 다른가 (date_mismatch)
  - 연도 보정 상한을 넘었는가 (far_future)
"""

from __future__ import annotations

import re

from app import config

# 확인 필요 사유. items.review_reason 에 들어가는 값과 같아야 한다.
REASON_TEXT = {
    "low_confidence": "AI가 확신하지 못함",
    "no_deadline": "기한이 있어야 하는데 마감일을 찾지 못함",
    "no_evidence": "근거 문장이 본문에 없음",
    "date_mismatch": "AI와 규칙 코드의 날짜가 다름",
    "far_future": "연도 없는 날짜가 너무 먼 미래",
}


def _squash(s: str) -> str:
    """공백·줄바꿈 차이를 무시하고 비교하기 위해 눌러 편다."""
    return re.sub(r"\s+", "", s)


def evidence_in_body(evidence: str, body_masked: str) -> bool:
    """근거 문장이 AI 가 본 본문 안에 실제로 있는가.

    반드시 마스킹된 본문과 대조해야 한다. 원문과 대조하면
    가려진 자리(예: [전화번호]) 때문에 무조건 불일치가 난다.
    """
    if not evidence.strip():
        return False
    return _squash(evidence) in _squash(body_masked)


def validate_extraction(out: dict) -> dict:
    """extract_one 의 결과를 받아 검증 결과를 덧붙여 돌려준다."""
    if out["status"] != "success":
        return out  # 이미 실패한 건 그대로 둔다

    result = out["result"]
    body_masked = out["normalized"]["masked"]
    items = result["items"]

    # 할 일이 있다면서 하나도 못 뽑은 경우 — 조용히 넘기지 않는다
    if result["action_required"] and not items:
        out["status"] = "failed"
        out["fail_kind"] = "no_items"
        out["error_message"] = (
            "할 일이 있는 메일이라고 판단했는데 항목을 하나도 뽑지 못했습니다."
        )
        return out

    for it in items:
        reasons: list[str] = []

        it["evidence_verified"] = evidence_in_body(it["evidence"], body_masked)
        if not it["evidence_verified"]:
            reasons.append("no_evidence")

        if it["confidence"] <= config.CONFIDENCE_REVIEW_MAX:
            reasons.append("low_confidence")

        # 마감이 있어야 하는 종류인데 못 찾은 경우만 확인 필요
        if it["deadline_iso"] is None and it.get("deadline_expected", True):
            reasons.append("no_deadline")

        it["review_reason"] = reasons
        it["needs_review"] = bool(reasons)

    return out


def summarize(outs: list[dict]) -> dict:
    """여러 건의 검증 결과를 한눈에 보기 좋게 집계한다."""
    ok = [o for o in outs if o["status"] == "success"]
    failed = [o for o in outs if o["status"] != "success"]
    items = [it for o in ok for it in o["result"]["items"]]
    return {
        "메일": len(outs),
        "성공": len(ok),
        "정리 실패": len(failed),
        "실패 종류": {k: sum(1 for o in failed if o["fail_kind"] == k)
                   for k in {o["fail_kind"] for o in failed}},
        "항목": len(items),
        "확인 필요": sum(1 for it in items if it["needs_review"]),
        "근거 검증 실패": sum(1 for it in items if not it["evidence_verified"]),
        "지시문구 감지": sum(1 for o in ok if o["result"]["contains_instruction_to_ai"]),
        "입력 토큰": sum(o["input_tokens"] for o in outs),
        "출력 토큰": sum(o["output_tokens"] for o in outs),
    }
