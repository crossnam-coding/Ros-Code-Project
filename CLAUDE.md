# CLAUDE.md — automix 프로젝트 가이드

로컬 Claude Code가 이 폴더를 열었을 때 프로젝트를 바로 이해하도록 정리한 문서.

## 이 레포에 뭐가 있나

이 레포(`Ros-Code-Project`)는 **두 개의 독립 프로젝트**를 한 폴더에 담고 있다.

1. **automix** — 멀티트랙(스템) 자동 믹싱 엔진. **← 지금 작업 대상**
   - `automix/` 파이썬 패키지, `mixer/` 브라우저 웹 믹서, `scripts/`, `setup.sh`, `requirements.txt`
2. **BOOTY BUMP 3D** — 루트 `index.html` 에 있는 Three.js 게임. **automix와 무관.**
   - 별도 세션에서 만든 것. **automix 작업 중에는 건드리지 말 것** (사용자가 명시적으로 요청할 때만).

> 폴더를 열거나 GitHub Pages 주소로 들어가면 루트 `index.html`(게임)이 먼저 보이는데,
> 믹싱 작업과는 상관없다. 믹서 엔진은 전부 `automix/`(파이썬)와 `mixer/`(브라우저)에 있다.

## automix가 하는 일

스템 폴더를 넣으면 자동으로 믹스된 스테레오 WAV를 출력한다. **머신러닝이 아니라
룰 베이스(규칙 기반) DSP 엔진**이다 — 표준 믹싱 가이드의 정석 세팅을 코드로 옮긴 것에,
소스를 분석해 반응하는 처리(공진 감지·마스킹 카빙·디에서·덕킹)를 얹었다.

파이프라인: **트랙 → 그룹 버스 → 믹스 버스** (실제 스튜디오 워크플로우)

```
[트랙]  분류 → 게인스테이징(-20 LUFS) → 공진 감지 EQ → 정석 체인(HPF→EQ→컴프)
        → 디에서(보컬류) → LUFS 밸런스 → 마스킹 카빙 → 등파워 패닝 → 트랙 덕킹
[버스]  8개 그룹 버스(리드/더블/하모니/애드립/떼창/드럼/베이스/뮤직)
        버스별 캐릭터 EQ + 글루 컴프 → 리드 보컬 우선 덕킹
[공간]  가까운 플레이트 + 먼 홀, 2개 리버브 버스 → 원근감
[믹스]  글루 컴프 → 에어 쉘프 → 목표 LUFS 정렬 → 리미터 -1dBFS → (선택)레퍼런스 마스터링
```

## 파일 구조

| 경로 | 역할 |
|---|---|
| `automix/classify.py` | 악기 분류 (파일명 키워드 + 스펙트럼 휴리스틱). 보컬은 리드/더블/하모니/애드립/떼창 세분화 |
| `automix/chains.py` | **레시피의 핵심.** `PROFILES`(악기별 EQ/컴프) + `BUSES`(그룹 버스 정의). 여기 숫자를 바꾸면 믹스 성향이 바뀐다 |
| `automix/analysis.py` | 스펙트럼 분석 — 공진 감지, 킥 기음 찾기 |
| `automix/dynamics.py` | 시변 처리 — 디에서, 사이드체인 덕킹, 엔벨로프 팔로워 |
| `automix/mixer.py` | 파이프라인 본체 (`mix_directory`) + 리포트 생성 |
| `automix/__main__.py` | CLI 진입점 (`python3 -m automix`) |
| `mixer/index.html` | 브라우저 웹 믹서 — 위 엔진을 **순수 JS로 포팅**한 것 |
| `scripts/make_demo_stems.py` | 합성 데모 스템 생성기 (실제 멀티 없이 테스트용) |
| `setup.sh` | 가상환경 + 의존성 설치 + 데모 믹스 검증 |

## 실행 / 테스트

```bash
# 최초 1회: 환경 세팅 (.venv 생성 + 설치 + 데모 믹스 검증)
bash setup.sh

# 이후 매번: 가상환경 켜고 믹스
source .venv/bin/activate
python3 -m automix "스템폴더" -o "내곡_mix.wav"
python3 -m automix "스템폴더" -o "mix.wav" --target-lufs -12      # 라우드니스 조절
python3 -m automix "스템폴더" -o "mix.wav" --reference "레퍼런스.wav"  # 레퍼런스 마스터링(matchering 필요)

# 변경 후 동작 검증: 데모 스템으로 한 곡 돌려보기
python3 scripts/make_demo_stems.py demo_stems
python3 -m automix demo_stems -o output/demo_mix.wav
```

출력 옆에 `*.report.md`가 같이 생긴다 — 트랙별로 어떤 악기로 인식했고 무슨 처리를 했는지 전부 기록.

## 개발 규칙 (중요)

- **파이썬과 JS는 같은 엔진의 두 구현이다.** `automix/`(파이썬)와 `mixer/index.html`(JS)는
  동일한 알고리즘/레시피를 구현한다. **레시피나 알고리즘을 바꾸면 양쪽을 함께 고쳐 동기 상태를 유지할 것.**
  (LUFS 측정은 ITU-R BS.1770 기준이며 pyloudnorm과 0.1dB 이내로 교차 검증돼 있다.)
- **룰 베이스가 기본 설계다** (의도된 것). 수치는 표준 믹싱 가이드 기준의 보수적 출발점.
  머신러닝을 붙이는 건 별개 결정 — 사용자와 합의 후 진행.
- **변경은 데모 믹스로 검증한다.** `scripts/make_demo_stems.py`로 만든 스템을 돌려서
  에러 없이 완료되고 최종 LUFS가 목표값에 맞는지 확인.
- 웹 믹서의 JS는 `mixer/index.html` 안 `<script>` 한 곳에 모여 있다. node로 문법 체크 가능:
  `python3 -c "import re; open('/tmp/a.js','w').write(re.search(r'<script>\n(.*)</script>', open('mixer/index.html').read(), re.S).group(1))" && node --check /tmp/a.js`
- **루트 `index.html`(게임)은 automix 작업과 무관하니 수정하지 말 것.**

## 배포 (선택 — 웹 믹서를 공유하고 싶을 때)

GitHub Pages(`main` 루트)로 배포한다. 웹 믹서 주소: `https://crossnam-coding.github.io/Ros-Code-Project/mixer/`
(루트 주소는 게임이다.) 활성화: **Settings → Pages → Source: Deploy from a branch → Branch: `main` / `/ (root)`**.

## 브랜칭

- 기능은 작업 브랜치에서 개발하고, 사용자가 배포/공유를 요청하면 `main`에 머지.
