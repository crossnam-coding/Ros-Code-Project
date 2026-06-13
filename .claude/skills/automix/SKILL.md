---
name: automix
description: >-
  멀티트랙(스템) 자동 믹싱 엔진 automix를 실행하거나 개발할 때 사용한다.
  스템 폴더를 믹스하기, 믹스 결과를 듣고 레시피(EQ/컴프/패닝/리버브/덕킹)를 튜닝하기,
  악기 분류나 버스 구조를 고치기, 웹 믹서(mixer/index.html)를 수정하기 등.
  "믹스해줘", "이 스템 믹싱", "보컬이 너무 작아/커", "공간감 더", "레시피 바꿔",
  "automix 고쳐" 같은 요청에서 발동.
---

# automix — 멀티트랙 자동 믹싱

룰 베이스 DSP 자동 믹싱 엔진. 파이프라인은 **트랙 → 그룹 버스 → 믹스 버스**.
전체 구조와 파일 역할은 루트 `CLAUDE.md` 참고.

## 스템을 믹스할 때

```bash
source .venv/bin/activate                              # 없으면 먼저 bash setup.sh
python3 -m automix "스템폴더" -o "내곡_mix.wav"
```

옵션:
- `--target-lufs -12` : 최종 라우드니스 (스트리밍 -14 기본 / CD·클럽 느낌 -9~-10)
- `--reference "곡.wav"` : 레퍼런스 곡처럼 마스터링 (matchering 필요: `pip install matchering`)

출력 옆 `*.report.md`에 트랙별 처리 내역이 남는다. 믹스가 이상하면 **먼저 리포트를 읽고**
어떤 악기로 분류됐는지, 어떤 EQ/컴프/팬/덕킹이 걸렸는지 확인한 뒤 원인을 짚는다.

## 결과를 튜닝할 때 — 어디를 만지나

레시피는 전부 `automix/chains.py`에 있다.

- **악기별 EQ/컴프/팬/리버브** → `PROFILES` 딕셔너리. 예: 보컬이 작으면 `vocal`의
  `target_lufs_offset`를 올리고(0.0이 기준, 다른 악기는 음수), 공간감이 부족하면 `reverb_send`를 키운다.
- **그룹 버스(글루 컴프, 리드 우선 덕킹)** → `BUSES` 딕셔너리. 예: 하모니가 리드를 가리면
  `vocal_harmony` 버스의 `duck_by_lead`를 키운다.
- **악기 분류가 틀리면** → `automix/classify.py`의 `_KEYWORD_RULES` / `_VOCAL_SUBTYPE_RULES`에
  파일명 패턴 추가.
- **공진 감지·디에서·덕킹 동작** → `automix/analysis.py`, `automix/dynamics.py`.

## 반드시 지킬 것

1. **파이썬과 JS를 함께 고친다.** `automix/`(파이썬)와 `mixer/index.html`(브라우저 JS)는
   같은 엔진의 두 구현이다. `PROFILES`/`BUSES`/분류 규칙/알고리즘을 바꾸면 **양쪽 다** 수정해
   동기 상태를 유지한다. (JS 쪽 대응물: `mixer/index.html`의 `PROFILES`, `BUSES`, `NAME_RULES`,
   `SUBTYPE_RULES`, DSP 함수들.)
2. **변경 후 데모 믹스로 검증한다.**
   ```bash
   python3 scripts/make_demo_stems.py demo_stems
   python3 -m automix demo_stems -o output/demo_mix.wav   # 에러 없이 완료 + 최종 LUFS가 목표에 맞는지
   ```
3. **웹 믹서 JS 문법 체크:**
   ```bash
   python3 -c "import re;open('/tmp/a.js','w').write(re.search(r'<script>\n(.*)</script>',open('mixer/index.html').read(),re.S).group(1))" && node --check /tmp/a.js
   ```
4. 수치 출처는 표준 믹싱 가이드(Mike Senior, Bobby Owsinski 등)다. 임의로 과격한 값을 넣지 말고
   보수적 출발점에서 조금씩 움직인다.
5. 루트 `index.html`(게임)은 건드리지 않는다.

## 머신러닝(진짜 AI)로 확장하려면

현재는 룰 베이스다. 신경망 믹싱이 필요하면 소니 `music_mixing_style_transfer`(레퍼런스 기반
스타일 트랜스퍼)가 현실적 후보지만 PyTorch·모델 다운로드·무거운 추론이 따라온다. 큰 방향 전환이라
착수 전 사용자와 합의한다.
