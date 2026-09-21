# 메일 → 할 일·마감 정리 프로토타입

여러 메일함에 흩어진 메일을 읽어서 "해야 할 일과 마감"으로 바꿔 한 화면에 보여준다.
메일은 **삭제·숨김·이동하지 않고**, 정렬해서 보여주기만 한다.

- 전체 명세: [SPEC.md](SPEC.md)
- 작업 규칙과 확정 사항: [CLAUDE.md](CLAUDE.md)

---

## 처음 한 번만 하면 되는 것

### 1. API 키 넣기

`.env` 파일을 텍스트 편집기로 열어서, `ANTHROPIC_API_KEY=` 뒤에 키를 붙여넣고 저장합니다.

```
ANTHROPIC_API_KEY=sk-ant-여기에본인키
```

따옴표를 붙이지 말고, 등호 뒤에 바로 붙여넣으세요.

> `.env` 파일은 git에 올라가지 않습니다. 절대 다른 곳에 복사하거나 공유하지 마세요.

터미널에서 파일을 열려면:

```bash
open -a TextEdit /Users/lwj/Desktop/claude/mail_proto/.env
```

### 2. 설정이 잘 됐는지 확인

```bash
cd /Users/lwj/Desktop/claude/mail_proto && ./.venv/bin/python check_setup.py
```

"모든 확인을 통과했습니다"가 나오면 준비 끝입니다.
실패하면 화면에 **무엇을 고쳐야 하는지 한국어로** 나옵니다.

---

## 자주 쓰는 명령어

모든 명령어는 이 폴더에서 실행합니다. `./.venv/bin/python`을 쓰는 이유는
이 프로젝트 전용 파이썬을 쓰기 위해서입니다. (컴퓨터 전체 설정을 건드리지 않습니다)

**설정 확인** (API 1회 호출, 1원 미만)

```bash
cd /Users/lwj/Desktop/claude/mail_proto && ./.venv/bin/python check_setup.py
```

**패키지 다시 설치** (뭔가 꼬였을 때)

```bash
cd /Users/lwj/Desktop/claude/mail_proto && ./.venv/bin/pip install -r requirements.txt
```

아래는 해당 마일스톤을 마친 뒤부터 쓸 수 있습니다.

| 명령어 | 언제 |
|---|---|
| `./.venv/bin/python -m app.extract` | M3 — 샘플 30통을 AI로 처리 (캐시 있으면 공짜) |
| `./.venv/bin/python -m app.extract --no-cache` | M3 — 캐시 무시하고 다시 호출 (약 180원) |
| `./.venv/bin/python -m app.evaluate` | M6 — 3회 반복 평가 리포트 생성 (캐시 있으면 0원) |
| `./.venv/bin/python -m app.evaluate --model claude-sonnet-5` | M6 — 다른 모델로 비교 |
| `./.venv/bin/python -m pytest` | M4 — 규칙 엔진 테스트 (56개, AI 안 씀, 0원) |
| `./.venv/bin/uvicorn app.main:app --port 8000` | M5 — 웹 화면. 브라우저에서 http://127.0.0.1:8000 열기 (끌 때는 Ctrl+C) |

---

## 지금까지 만든 것

| 단계 | 내용 | 상태 |
|---|---|---|
| M1 | 환경·뼈대 | 완료 |
| M2 | 샘플 메일 30통 + 정답 | 예정 |
| M3 | AI 추출 + 검증 | 완료 |
| M4 | 규칙 엔진 + 테스트 | 완료 |
| M5 | 웹 화면 | 완료 |
| M6 | 평가 리포트 | 완료 (haiku) |
| M7 | 경희대 메일 연동 | 예정 |

---

## 폴더 설명

```
mail_proto/
├─ check_setup.py    설정 확인
├─ .env              내 API 키·비밀번호 (git에 안 올라감, 공유 금지)
├─ .env.example      설정 항목 예시 (값은 비어 있음)
├─ app/              프로그램 본체
│  └─ config.py      조정할 숫자는 전부 여기에 모음
├─ web/              화면 (M5)
├─ samples/          가짜 샘플 메일과 정답 (M2)
├─ tests/            테스트 (M4)
├─ reports/          평가 리포트 (M6)
└─ data/             내 메일이 담긴 로컬 DB (git에 안 올라감)
```

---

## 안전 원칙

이 프로그램은 **메일을 읽기만 합니다.** 삭제·이동·읽음 처리·답장을 하지 않습니다.
읽지 않은 메일은 읽지 않은 상태 그대로 남습니다.
