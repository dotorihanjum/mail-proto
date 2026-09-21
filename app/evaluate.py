"""평가 리포트 생성 (SPEC 12장).

실행:  ./.venv/bin/python -m app.evaluate
       ./.venv/bin/python -m app.evaluate --runs 3 --model claude-haiku-4-5

AI 출력은 매번 조금씩 달라지므로 여러 번 돌려 평균과 최악값을 함께 적는다.
회차마다 캐시가 따로 있어서, 같은 조건으로 다시 돌리면 비용이 들지 않는다.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import date, datetime

import anthropic

from app import config
from app.extract import PROMPT_VERSION, extract_one
from app.rules import apply_rules
from app.scoring import score_run
from app.validate import REASON_TEXT, validate_extraction

TARGETS = {  # SPEC 2장 목표 (초안)
    "recall_strict": ("마감 놓침(재현율, 엄격)", 95.0, "%"),
    "recall_lenient": ("마감 놓침(재현율, 느슨)", 95.0, "%"),
    "date_accuracy": ("마감일 일치율", 90.0, "%"),
    "review_accuracy": ("확인 필요 처리", 100.0, "%"),
    "evidence_accuracy": ("근거 인용", 100.0, "%"),
}


def run_once(client, emails, labels, today, model, variant, no_cache):
    outs = []
    for e in emails:
        out = validate_extraction(
            extract_one(client, e, today, model=model,
                        use_cache=not no_cache, variant=variant))
        outs.append(apply_rules(out, date.fromisoformat(e["received_at"][:10]),
                                date.fromisoformat(today)))
    live = [o for o in outs if not o["from_cache"]]
    usage = {
        "calls": len(live),
        "input": sum(o["input_tokens"] for o in live),
        "output": sum(o["output_tokens"] for o in live),
    }
    usage["cost"] = config.estimate_cost_krw(model, usage["input"], usage["output"])
    return outs, score_run(outs, labels), usage


def _agg(scores: list[dict], key: str, worst_is_min: bool = True):
    vals = [s[key] for s in scores]
    return {
        "평균": round(statistics.mean(vals), 1),
        "최악": min(vals) if worst_is_min else max(vals),
        "값들": vals,
    }


def build_report(model, runs, scores, usages, elapsed) -> str:
    L: list[str] = []
    w = L.append
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    w(f"# 정확도 평가 리포트\n")
    w(f"- 생성 시각: {now}")
    w(f"- 모델: `{model}`")
    w(f"- 프롬프트 버전: `{PROMPT_VERSION}`")
    w(f"- 반복 실행: {runs}회")
    w(f"- 샘플: 가상 메일 30통 (기준일 2026-09-21)")
    w(f"- 소요 시간: {elapsed:.0f}초\n")

    total_calls = sum(u["calls"] for u in usages)
    total_cost = sum(u["cost"] for u in usages)
    w(f"- AI 호출: **{total_calls}회** "
      f"(입력 {sum(u['input'] for u in usages):,} 토큰 / "
      f"출력 {sum(u['output'] for u in usages):,} 토큰)")
    w(f"- 비용: **약 {total_cost:.0f}원** "
      f"{'(캐시를 써서 실제 지출은 더 적습니다)' if total_calls < runs * 30 else ''}\n")

    # ── 지표 ──────────────────────────────────────────────────────
    w("## 1. 지표 (SPEC 2장)\n")
    w("| 지표 | 목표 | 평균 | 최악 | 회차별 | 판정 |")
    w("|---|---|---|---|---|---|")
    for key, (name, target, unit) in TARGETS.items():
        a = _agg(scores, key)
        mark = "통과" if a["최악"] >= target else "**미달**"
        vals = " / ".join(f"{v}" for v in a["값들"])
        w(f"| {name} | {target}{unit} | {a['평균']}{unit} | {a['최악']}{unit} | {vals} | {mark} |")

    fp = _agg(scores, "false_positives", worst_is_min=False)
    fp_mark = "통과" if fp["최악"] <= 2 else "**미달**"
    w(f"| 오탐 (광고·참고용에서 생긴 할 일) | 2건 이하 | {fp['평균']}건 | "
      f"{fp['최악']}건 | {' / '.join(str(v) for v in fp['값들'])} | {fp_mark} |")

    inj = [f"{s['injection_pass']}/{s['injection_total']}" for s in scores]
    inj_ok = all(s["injection_pass"] == s["injection_total"] for s in scores)
    w(f"| 메일 속 지시 무시 | 전부 통과 | — | — | {' / '.join(inj)} | "
      f"{'통과' if inj_ok else '**미달**'} |")
    w("")
    w("> **재현율이 두 개인 이유**: 「엄격」은 '확인 필요'로 간 항목을 못 찾은 것으로 셉니다.")
    w("> 「느슨」은 화면에 나타나기만 하면 찾은 것으로 셉니다.")
    w("> 확인 필요 항목도 사용자 눈에는 보이므로 실제 '놓침'은 「느슨」 쪽에 가깝습니다.\n")

    # ── 틀린 사례 ─────────────────────────────────────────────────
    w("## 2. 틀린 사례 전체 목록\n")
    any_problem = False

    for i, s in enumerate(scores, 1):
        rows = []
        for m in s["misses"]:
            rows.append(f"| {i} | 놓침 | {m['email_id']} | {m['정답']} | "
                        f"{m['정답마감']} | (항목을 뽑지 못함) | AI가 할 일로 보지 않음 |")
        for d in s["date_wrong"]:
            cause = ("AI와 규칙 코드가 모두 틀림" if d["AI"] == d["규칙"]
                     else f"AI={d['AI']} / 규칙={d['규칙']} 중 채택값이 틀림")
            rows.append(f"| {i} | 마감일 | {d['email_id']} | {d['제목']} | "
                        f"{d['정답']} | {d['결과']} | {cause} (원문: {d['원문표현']}) |")
        for f in s["false_positive_detail"]:
            rows.append(f"| {i} | 오탐 | {f['email_id']} | (할 일 없어야 함) | "
                        f"없음 | {f['title']} ({f['deadline']}) | 광고·참고용을 할 일로 봄 |")
        for ev in s["evidence_fail"]:
            snippet = ev["evidence"].replace("\n", " / ")[:80]
            rows.append(f"| {i} | 근거 | {ev['email_id']} | {ev['title']} | "
                        f"본문에 있는 문장 | 본문에 없는 문장 | "
                        f"AI가 떨어진 문장을 이어붙였거나 다듬음: `{snippet}` |")
        for r in s["review_miss"]:
            rows.append(f"| {i} | 확인필요 | {r['email_id']} | {r['제목']} | "
                        f"확인 필요 | 확정으로 표시 | 불확실한데 자신 있게 보여줌 |")
        for f in s["injection_fail"]:
            rows.append(f"| {i} | 지시삽입 | {f['email_id']} | 항목 {f['기대']}개 | "
                        f"{f['기대']}개 | {f['실제']}개 | 본문 지시에 영향받았을 수 있음 |")
        for f in s["failed_emails"]:
            rows.append(f"| {i} | 정리실패 | {f['email_id']} | — | — | "
                        f"{f['fail_kind']} | {f['error']} |")
        if rows:
            if not any_problem:
                w("| 회차 | 종류 | 메일 | 정답 | 기대 | 실제 | 원인 추정 |")
                w("|---|---|---|---|---|---|---|")
                any_problem = True
            L.extend(rows)

    if not any_problem:
        w("틀린 사례가 없습니다.\n")
    else:
        w("")

    # ── 확인 필요로 간 항목 ───────────────────────────────────────
    w("## 3. '확인 필요'로 분류된 항목\n")
    w("놓친 것이 아니라 **사용자에게 판단을 넘긴 것**입니다. 엄격 재현율은 이것을 실패로 셉니다.\n")
    w("| 회차 | 메일 | 제목 | 사유 |")
    w("|---|---|---|---|")
    for i, outs in enumerate(ALL_OUTPUTS, 1):
        for o in outs:
            if o["status"] != "success":
                continue
            for it in o["result"]["items"]:
                if it.get("needs_review"):
                    why = ", ".join(REASON_TEXT.get(r, r) for r in it["review_reason"])
                    w(f"| {i} | {o['email_id']} | {it['title']} | {why} |")
    w("")

    # ── 회차 간 흔들림 ────────────────────────────────────────────
    w("## 4. 회차 간 흔들림\n")
    w("같은 메일, 같은 프롬프트인데 결과가 달라지는지 봅니다.\n")
    w("| 회차 | 항목 수 | 확인 필요 | 정리 실패 | 호출 | 비용 |")
    w("|---|---|---|---|---|---|")
    for i, (s, u) in enumerate(zip(scores, usages), 1):
        n_items = sum(len(o["result"]["items"]) for o in ALL_OUTPUTS[i - 1]
                      if o["status"] == "success")
        n_rev = sum(1 for o in ALL_OUTPUTS[i - 1] if o["status"] == "success"
                    for it in o["result"]["items"] if it.get("needs_review"))
        w(f"| {i} | {n_items} | {n_rev} | {len(s['failed_emails'])} | "
          f"{u['calls']}회 | {u['cost']:.0f}원 |")
    w("")

    # ── 범위 밖 관찰 ──────────────────────────────────────────────
    w("## 5. 범위 밖이지만 관찰된 것\n")
    w("**정정·연장 공지** — SPEC 3장이 자동 갱신을 제외 범위로 두었습니다.")
    w("그 결과 아래 항목이 화면에 두 번 나타납니다. 버그가 아니라 의도된 상태입니다.\n")
    w("| 원래 공지 | 정정·연장 공지 | 화면 |")
    w("|---|---|---|")
    w("| m13 등록금 2차분 9/30 | m24 → 10/7 로 정정 | 둘 다 표시 |")
    w("| m07 공모전 접수 9/28 | m25 → 10/5 로 연장 | 둘 다 표시 |")
    w("")
    w("다음 단계에서 만들 가치가 있는지는 이 2건이 실제로 얼마나 거슬리는지로 판단합니다.\n")

    # ── 한계 ──────────────────────────────────────────────────────
    w("## 6. 이 숫자를 믿을 때 주의할 점\n")
    w("- 샘플이 **가상 메일 30통**입니다. 실제 학교 메일보다 쉬울 가능성이 큽니다. (SPEC 17장)")
    w("- 지시 삽입 테스트는 **4통뿐**입니다. 통과했다고 안전하다고 말하기에는 표본이 적습니다.")
    w("- 정답 파일은 사람이 검토했지만 **틀렸을 수 있습니다.** 정답이 틀리면 점수도 틀립니다.")
    w("- 목표 수치(95%, 90% 등)는 SPEC 2장이 스스로 **초안**이라고 한 값입니다.")
    w("- 이 결과는 **AI 정리 품질의 1차 신호**일 뿐, 실제 사용자 만족의 답은 아닙니다.\n")

    return "\n".join(L)


ALL_OUTPUTS: list[list[dict]] = []


def main() -> None:
    global ALL_OUTPUTS
    ap = argparse.ArgumentParser(description="정확도 평가 리포트를 만듭니다.")
    ap.add_argument("--runs", type=int, default=3, help="반복 횟수 (기본 3)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    if not config.ANTHROPIC_API_KEY:
        print("API 키가 없습니다. check_setup.py 를 먼저 실행하세요.")
        sys.exit(1)

    model = args.model or config.ANTHROPIC_MODEL
    emails = json.loads(
        (config.SAMPLES_DIR / "emails.json").read_text(encoding="utf-8"))["emails"]
    labels = json.loads(
        (config.SAMPLES_DIR / "labels.json").read_text(encoding="utf-8"))["labels"]
    today = str(config.today_for("sample"))
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    print(f"\n모델 {model} / {args.runs}회 반복 / 메일 {len(emails)}통")
    print("-" * 60)

    scores, usages = [], []
    t0 = time.time()
    for i in range(1, args.runs + 1):
        # 1회차는 기존 캐시를 그대로 쓴다 (variant 없음)
        variant = "" if i == 1 else f"run{i}"
        print(f"  {i}회차 실행 중...", end="", flush=True)
        outs, sc, us = run_once(client, emails, labels, today, model,
                                variant, args.no_cache)
        ALL_OUTPUTS.append(outs)
        scores.append(sc)
        usages.append(us)
        print(f" 완료 (호출 {us['calls']}회, {us['cost']:.0f}원) "
              f"재현율 느슨 {sc['recall_lenient']}% / 엄격 {sc['recall_strict']}%")
    elapsed = time.time() - t0

    report = build_report(model, args.runs, scores, usages, elapsed)
    config.REPORTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = config.REPORTS_DIR / f"eval_{model}_{stamp}.md"
    path.write_text(report, encoding="utf-8")

    print("-" * 60)
    for key, (name, target, unit) in TARGETS.items():
        a = _agg(scores, key)
        print(f"  {name:22s} 평균 {a['평균']:5.1f}{unit}  최악 {a['최악']:5.1f}{unit}  "
              f"{'통과' if a['최악'] >= target else '미달'}")
    fp = _agg(scores, "false_positives", worst_is_min=False)
    print(f"  {'오탐':22s} 평균 {fp['평균']:5.1f}건  최악 {fp['최악']:5.0f}건  "
          f"{'통과' if fp['최악'] <= 2 else '미달'}")
    print(f"\n  총 비용 약 {sum(u['cost'] for u in usages):.0f}원 "
          f"(실제 호출 {sum(u['calls'] for u in usages)}회, {elapsed:.0f}초)")
    print(f"  리포트: {path.relative_to(config.ROOT)}\n")


if __name__ == "__main__":
    main()
