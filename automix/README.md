# automix — 멀티트랙 자동 믹싱 엔진 (프로토타입)

스템(멀티트랙) 폴더를 넣으면 자동으로 믹스된 스테레오 WAV를 출력합니다.
표준 믹싱 가이드(악기별 EQ 포인트, 컴프 세팅, 패닝, 리버브 공간감)를
규칙으로 코딩한 룰 베이스 엔진입니다.

## 설치

```bash
pip install -r requirements.txt
# 레퍼런스 곡 기반 마스터링까지 쓰려면 (선택):
pip install matchering
```

## 사용법

```bash
# 기본: 스템 폴더 → 믹스 WAV (-14 LUFS, 스트리밍 기준)
python3 -m automix ./내곡_스템폴더 -o 내곡_mix.wav

# 라우드니스 바꾸기 (CD 마스터 느낌이면 -9 ~ -10 정도)
python3 -m automix ./스템폴더 -o mix.wav --target-lufs -12

# 레퍼런스 곡처럼 마스터링까지 (matchering 필요)
python3 -m automix ./스템폴더 -o mix.wav --reference 레퍼런스곡.wav
```

출력 파일 옆에 `*.report.md` 리포트가 같이 생성됩니다 — 트랙별로 어떤
악기로 인식했고, 어떤 EQ/컴프를 걸었고, 팬과 리버브를 얼마나 줬는지
전부 기록됩니다.

## 스템 파일 준비 팁

- **파일명에 악기 이름을 넣어주세요.** `Kick.wav`, `Bass.wav`, `LeadVocal.wav`,
  `Guitar_L.wav`처럼요. 한국어(`보컬.wav`, `드럼.wav`)도 인식합니다.
  이름으로 알 수 없으면 스펙트럼 분석으로 추정하지만 정확도가 떨어집니다.
- 지원 포맷: WAV / FLAC / AIFF / OGG / MP3 (샘플레이트 달라도 자동 통일)
- 스템은 이펙트를 걸지 않은 **드라이 상태**가 제일 좋습니다 (이미 컴프/리버브가
  걸려 있으면 이중 처리가 됩니다).

## 파이프라인 구조 (트랙 → 그룹 버스 → 믹스 버스)

아이돌 곡처럼 보컬 트랙이 많은 세션을 위해 실제 스튜디오 워크플로우와 같은
3단 버스 구조를 사용합니다.

```
[트랙 레벨]
  악기 분류 (보컬은 리드/더블/하모니/애드립/떼창까지 세분화)
  → 게인 스테이징(-20 LUFS) → 공진 감지 EQ → 정석 체인(HPF→EQ→컴프)
  → 디에서(보컬류) → LUFS 밸런스 → 마스킹 카빙(킥↔베이스, 보컬↔미드 악기)
  → 등파워 패닝 → 트랙 덕킹(킥→베이스, 리드→패드/스트링)

[그룹 버스 레벨]  ※ 리드/더블/하모니/애드립/떼창/드럼/베이스/뮤직 8버스
  버스별 캐릭터 EQ + 글루 컴프
  → 리드 보컬 사이드체인 덕킹: 리드가 나오면 더블/하모니/애드립/떼창 버스가
    자동으로 살짝 물러남 ("리드가 왕" 원칙)

[공간]
  가까운 플레이트(리드/더블/스네어...) + 먼 홀(하모니/떼창/패드/스트링)
  2개 리버브 버스 → 원근감

[믹스 버스]
  글루 컴프 2:1 → 에어 쉘프 → 목표 LUFS → 리미터 -1dBFS
  → (선택) matchering 레퍼런스 마스터링
```

악기별 레시피는 `chains.py`의 `PROFILES`, 버스 정의는 같은 파일의 `BUSES`에 있습니다.
수치를 바꾸면 바로 믹스 성향이 바뀝니다 (예: 보컬 리버브 양, 하모니 버스 덕킹 깊이).
소스를 분석해서 반응하는 처리(공진/카빙/디에서/덕킹)는 `analysis.py`, `dynamics.py`에 있습니다.

### 보컬 트랙 파일명 규칙 (많을수록 정확)

| 인식 | 파일명 예시 |
|---|---|
| 리드 보컬 | `V1_Lead.wav`, `MainVo.wav`, `보컬.wav`, `Vox.wav` |
| 더블 | `Vox_DBL_L.wav`, `Double_01.wav`, `더블L.wav` |
| 하모니/스택 | `Harmony_Hi.wav`, `BGV_stack.wav`, `하모니3도.wav`, `화음.wav` |
| 애드립 | `Adlib.wav`, `애드립.wav` |
| 떼창/군중 | `chant.wav`, `crowd.wav`, `떼창.wav` |

악기 이름이 같이 있으면 악기가 우선입니다 (`GTR_DBL.wav`는 기타로 인식).

## 웹 UI (브라우저 버전)

`mixer/index.html`을 브라우저로 열면 드래그&드롭으로 쓸 수 있는 웹 버전이 있습니다.
같은 엔진을 JavaScript로 포팅한 것으로, 업로드 없이 전부 브라우저 안에서 처리됩니다.
GitHub Pages 배포 시 `https://crossnam-coding.github.io/Ros-Code-Project/mixer/`로 접속.

파이썬 버전과의 차이: 공진 감지 EQ와 matchering 레퍼런스 마스터링은 파이썬 전용,
출력이 16bit WAV(파이썬은 24bit)입니다. LUFS 측정은 양쪽 다 ITU-R BS.1770 기준이며
pyloudnorm과 0.1dB 이내로 교차 검증되어 있습니다.

## 참고한 믹싱 지식

레시피와 처리 순서는 업계 표준 자료들의 공통 내용을 규칙으로 옮긴 것입니다:

- Mike Senior, *Mixing Secrets for the Small Studio* — 악기별 EQ 출발점, 머드 컷, 보컬 체인
- Bobby Owsinski, *The Mixing Engineer's Handbook* — 밸런스/패닝/공간 배치 원칙
- ITU-R BS.1770 — 라우드니스(LUFS) 측정 표준
- Intelligent music production 연구 (Reiss 등, AES/[dl4am 튜토리얼](https://dl4am.github.io/tutorial/)) — 마스킹 카빙, 자동 밸런스 등 자동 믹싱 연구

## 테스트

실제 멀티트랙이 없을 때 합성 데모 스템으로 검증:

```bash
python3 scripts/make_demo_stems.py   # demo_stems/ 생성
python3 -m automix demo_stems -o output/demo_mix.wav
```

## 한계 (프로토타입)

- 룰 베이스라 곡 장르/분위기를 듣고 판단하지는 않습니다 — 정석적인 출발점 믹스를 만들어 줍니다.
- 디에서, 사이드체인 덕킹, 오토메이션은 아직 없습니다.
- 마스킹(킥-베이스 충돌 등)은 고정 EQ 규칙으로만 처리합니다.
