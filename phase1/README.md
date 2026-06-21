# Phase 1 — AI 검색 점유율 측정 워커 (하이브리드)

`lawgeo.html`의 **수동 붙여넣기**를 자동화한 백엔드 골격.
**측정 = 실제 엔진(Gemini 무료 티어)** / **판독 = 로컬 Gemma(Ollama)**.

## 동작
1. 분야·지역으로 buyer-intent 질문 세트 생성 (`prompts.py`)
2. 각 질문을 Gemini(웹 그라운딩)에 `--repeats`회 호출 → 실제 검색답변 수집
3. 각 답변을 로컬 Gemma가 "우리/경쟁사 언급?"으로 분류
4. **노출률 % + 등급 + 질문별 분해 + 경쟁사 빈도**를 JSON 출력

> 핵심 원칙: 측정은 반드시 실제 소비자 엔진. 로컬 Gemma는 *판독·생성*에만.

## 준비
```bash
# 1) 측정용 키 (무료 티어로 시작) — https://aistudio.google.com/apikey
export GEMINI_API_KEY="발급키"

# 2) 판독용 로컬 모델
#   - 설치: https://ollama.com
ollama pull gemma3n:e4b      # 가벼우면 gemma3n:e2b
ollama serve                 # 백그라운드 구동
```

## 먼저 연결 점검 (받아둔 모델 자동탐지)
> ⚠️ 이 스크립트는 **Ollama가 깔린 그 PC에서** 실행해야 합니다. (원격/다른 PC면 로컬 Ollama에 못 붙음)
```bash
cd phase1
python3 measure.py --check
```
설치된 모델 목록과 **자동 선택될 판독 모델**을 보여줍니다.
`JUDGE_MODEL`을 따로 안 줘도 `gemma e4b → e2b → 기타 gemma` 순으로 알아서 잡습니다.

## 실행
```bash
cd phase1
python3 measure.py \
  --firm "법무법인 OO" \
  --field "이혼·가사" \
  --region "강남" \
  --competitors "법무법인 A, B변호사" \
  --repeats 3 \
  --out result.json
```

## 환경변수
| 변수 | 기본 | 용도 |
|---|---|---|
| `GEMINI_API_KEY` | (필수) | 측정 |
| `GEMINI_MODEL` | `gemini-2.0-flash` | 측정 모델 |
| `USE_GROUNDING` | `1` | google_search 그라운딩(실제 검색답변 근접) |
| `OLLAMA_URL` | `http://localhost:11434` | 로컬 판독 |
| `JUDGE_MODEL` | `gemma3n:e4b` | 판독 모델 |

## 폴백 동작
- `GEMINI_API_KEY` 없으면 측정 불가(에러). **측정은 대체 불가.**
- Ollama 미가동 시 판독은 **문자열 포함 매칭으로 자동 폴백**(정확도 낮음, 개발용).

## 신뢰도 메모
LLM 응답은 비결정적 → `--repeats`를 늘리고 다엔진(추가 예정)으로 평균낼수록 신뢰도 ↑.
`gemini-2.0-flash` 외 Perplexity/OpenAI 어댑터는 다음 커밋에서 확장.

## 다음 (Phase 1 확장)
- [ ] 엔진 어댑터 추가(Perplexity, OpenAI) → 다엔진 평균
- [ ] 사전등록/리드 적재(Supabase)
- [ ] `lawgeo.html` 결과를 이 워커 출력으로 자동 채우기
- [ ] 콘텐츠 처방 생성(로컬 Gemma E4B)
