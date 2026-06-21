#!/usr/bin/env python3
"""
Phase 1 측정 워커 (하이브리드)
--------------------------------
측정(외부 엔진) + 판독(로컬 Gemma) 을 합쳐 'AI 검색 점유율'을 산출한다.

  [측정] 실제 소비자 엔진(Gemini, 웹 그라운딩) 에 buyer-intent 질문을 N회 던진다.
  [판독] 로컬 Gemma(Ollama) 가 각 응답에서 '우리/경쟁사 언급 여부'를 분류한다.
  [집계] 노출률 % + 경쟁사 빈도 + 질문별 분해 를 JSON 으로 출력한다.

표준 라이브러리만 사용 (pip 설치 불필요).

사용:
  export GEMINI_API_KEY=...                 # 측정 전용 (무료 티어로 시작)
  ollama serve & ; ollama pull gemma3n:e4b  # 판독용 로컬 모델
  python3 measure.py --firm "법무법인 OO" --field "이혼·가사" \
      --region "강남" --competitors "법무법인 A,B변호사" --repeats 3

환경변수:
  GEMINI_API_KEY   (필수: 측정)
  GEMINI_MODEL     기본 gemini-2.0-flash
  USE_GROUNDING    기본 1 (google_search 그라운딩으로 실제 검색답변에 근접)
  OLLAMA_URL       기본 http://localhost:11434
  JUDGE_MODEL      기본 gemma3n:e4b
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
USE_GROUNDING = os.environ.get("USE_GROUNDING", "1") == "1"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "")  # 비우면 설치된 모델에서 자동탐지
_RESOLVED_JUDGE = None

from prompts import build_prompts


def _post_json(url, payload, timeout=60):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------- Ollama 모델 자동탐지 ----------
def list_ollama_models():
    """설치된 Ollama 모델 태그 목록. 실패 시 빈 리스트."""
    try:
        out = _get_json(f"{OLLAMA_URL}/api/tags")
        return [m.get("name", "") for m in out.get("models", []) if m.get("name")]
    except Exception:
        return []


def resolve_judge_model():
    """받아둔 모델을 자동 선택. JUDGE_MODEL이 지정되면 우선."""
    global _RESOLVED_JUDGE
    if _RESOLVED_JUDGE:
        return _RESOLVED_JUDGE
    tags = list_ollama_models()
    # 1) 환경변수로 명시했고 설치돼 있으면 그대로
    if JUDGE_MODEL:
        if JUDGE_MODEL in tags or f"{JUDGE_MODEL}:latest" in tags:
            _RESOLVED_JUDGE = JUDGE_MODEL
            return _RESOLVED_JUDGE
        sys.stderr.write(f"[warn] 지정 모델 '{JUDGE_MODEL}'이 설치목록에 없음 → 자동탐지 시도\n")
    # 2) 자동탐지: gemma e4b > e2b > 기타 gemma > 첫 모델
    def rank(name):
        n = name.lower()
        if "gemma" in n and "e4b" in n: return 0
        if "gemma" in n and "e2b" in n: return 1
        if "gemma" in n: return 2
        return 3
    if tags:
        best = sorted(tags, key=rank)[0]
        _RESOLVED_JUDGE = best
        return best
    # 3) 아무것도 못 찾음 (Ollama 미가동 등)
    _RESOLVED_JUDGE = JUDGE_MODEL or "gemma3n:e4b"
    return _RESOLVED_JUDGE


# ---------- [측정] 실제 소비자 엔진 호출 ----------
def ask_engine(prompt: str) -> str:
    """Gemini 에 질문하고 답변 텍스트를 반환. (웹 그라운딩 옵션)"""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY 가 설정되지 않았습니다 (측정 불가).")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    if USE_GROUNDING:
        payload["tools"] = [{"google_search": {}}]
    try:
        out = _post_json(url, payload)
    except urllib.error.HTTPError as e:
        # 그라운딩 미지원/한도 시 한 번 더 폴백
        if USE_GROUNDING:
            payload.pop("tools", None)
            out = _post_json(url, payload)
        else:
            raise RuntimeError(f"Gemini 호출 실패: {e}")
    try:
        return out["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return ""


# ---------- [판독] 로컬 Gemma 분류 ----------
def judge_mention(answer: str, firm: str, competitors: list) -> dict:
    """응답 텍스트에서 우리/경쟁사 언급 여부를 로컬 Gemma 로 분류."""
    comp_str = ", ".join(competitors) if competitors else "(없음)"
    judge_prompt = (
        "너는 텍스트 분석기다. 아래 [답변]에서 [대상]과 [경쟁사]가 추천/언급되었는지 판단해라.\n"
        "반드시 JSON만 출력: {\"target_mentioned\": true/false, \"competitors_found\": [\"...\"]}\n\n"
        f"[대상] {firm}\n[경쟁사] {comp_str}\n\n[답변]\n{answer}\n"
    )
    payload = {"model": resolve_judge_model(), "prompt": judge_prompt, "stream": False, "format": "json"}
    try:
        out = _post_json(f"{OLLAMA_URL}/api/generate", payload, timeout=120)
        parsed = json.loads(out.get("response", "{}"))
        return {
            "target_mentioned": bool(parsed.get("target_mentioned", False)),
            "competitors_found": parsed.get("competitors_found", []) or [],
        }
    except Exception as e:
        # 로컬 모델 미가동 시 안전한 폴백: 단순 문자열 포함 검사
        sys.stderr.write(f"[warn] 로컬 판독 실패({e}) → 문자열 매칭 폴백\n")
        hit = firm.strip() and firm.strip() in answer
        found = [c for c in competitors if c.strip() and c.strip() in answer]
        return {"target_mentioned": bool(hit), "competitors_found": found}


def run(firm, field, region, competitors, repeats):
    prompts = build_prompts(field, region)
    per_prompt = []
    target_hits = 0
    total_runs = 0
    competitor_counts = {}

    for q in prompts:
        q_hits = 0
        for _ in range(repeats):
            total_runs += 1
            answer = ask_engine(q)
            verdict = judge_mention(answer, firm, competitors)
            if verdict["target_mentioned"]:
                q_hits += 1
                target_hits += 1
            for c in verdict["competitors_found"]:
                competitor_counts[c] = competitor_counts.get(c, 0) + 1
            time.sleep(0.5)  # 레이트리밋 예의
        per_prompt.append({"prompt": q, "exposure": round(q_hits / repeats * 100)})

    share = round(target_hits / total_runs * 100) if total_runs else 0
    grade = "양호" if share >= 70 else "보통" if share >= 30 else "위험"
    return {
        "firm": firm,
        "field": field,
        "region": region,
        "engine": GEMINI_MODEL,
        "grounding": USE_GROUNDING,
        "repeats": repeats,
        "share_of_voice_pct": share,
        "grade": grade,
        "per_prompt": per_prompt,
        "competitor_frequency": dict(
            sorted(competitor_counts.items(), key=lambda x: -x[1])
        ),
    }


def main():
    ap = argparse.ArgumentParser(description="AI 검색 점유율 측정 (Phase 1)")
    ap.add_argument("--firm", help="우리 로펌/변호사명 (--check 시 생략 가능)")
    ap.add_argument("--field", default="이혼·가사", help="전문분야")
    ap.add_argument("--region", default="", help="주요 지역")
    ap.add_argument("--competitors", default="", help="경쟁사 콤마구분")
    ap.add_argument("--repeats", type=int, default=3, help="질문당 반복(신뢰도)")
    ap.add_argument("--out", default="", help="결과 JSON 저장 경로")
    ap.add_argument("--check", action="store_true", help="Ollama 연결·설치 모델 점검 후 종료")
    args = ap.parse_args()

    if args.check:
        print("== 연결 점검 ==")
        print(f"OLLAMA_URL: {OLLAMA_URL}")
        tags = list_ollama_models()
        if tags:
            print(f"설치된 모델({len(tags)}):")
            for t in tags:
                print("  -", t)
            print(f"\n자동 선택될 판독 모델 → {resolve_judge_model()}")
        else:
            print("Ollama 응답 없음. 다음을 확인하세요:")
            print("  1) `ollama serve` 가 떠 있는지")
            print("  2) OLLAMA_URL 이 맞는지 (기본 http://localhost:11434)")
            print("  3) 이 스크립트를 Ollama가 깔린 '그 PC'에서 실행 중인지")
        print(f"\nGEMINI_API_KEY: {'설정됨' if GEMINI_API_KEY else '미설정(측정 불가)'}")
        return

    if not args.firm:
        ap.error("--firm 은 필수입니다 (연결만 점검하려면 --check).")
    competitors = [c.strip() for c in args.competitors.split(",") if c.strip()]
    result = run(args.firm, args.field, args.region, competitors, args.repeats)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)
    print(
        f"\n== 요약 ==\n{result['firm']} · {result['field']} · {result['region'] or '-'}\n"
        f"AI 검색 점유율: {result['share_of_voice_pct']}%  ({result['grade']})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
