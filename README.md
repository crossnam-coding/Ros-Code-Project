# Ros Code Project

## 🎚️ automix — 멀티트랙 자동 믹싱 엔진

스템을 넣으면 자동으로 믹스해주는 엔진. 악기별 정석 EQ/컴프 체인에 더해
공진 감지 EQ, 마스킹 카빙, 사이드체인 덕킹, 디에서 등 소스 반응형 처리 포함.
자세한 사용법은 [automix/README.md](automix/README.md) 참고.

- **웹 UI**: [mixer/index.html](mixer/index.html) — 브라우저에 스템을 드래그&드롭하면 끝
  (GitHub Pages 배포 시 `https://crossnam-coding.github.io/Ros-Code-Project/mixer/`)
- **CLI (파이썬)**:

```bash
pip install -r requirements.txt
python3 -m automix ./스템폴더 -o mix.wav
```

---

# 🍑 BOOTY BUMP 3D · 맨해튼 엉덩이 헌터

루트 `index.html` 에 배포되는 **Three.js 1인칭 3D** 코믹 캐주얼 게임. 황혼의 맨해튼을 걷다 앞의 **꽃미남 카툰 캐릭터**를 손으로 직접 잡고 콤보 점수를 쌓아요.

> 등장인물은 전부 100% 만화 캐릭터입니다. 가볍게 웃으며 즐기는 코믹 게임이에요 😎

## 실행 방법
GitHub Pages 주소로 접속: `https://crossnam-coding.github.io/Ros-Code-Project/`
(Three.js를 CDN으로 불러오므로 인터넷 연결이 필요해요.)

## 모드
- 🗽 **맨해튼 거리 (3D)** — 1인칭으로 맨해튼을 걸으며 앞의 꽃미남 엉덩이를 *팡!* (60초)
- 📸 **AR 모드** — 카메라 영상 위에 내 손 + 꽃미남이 합성돼요. 탭해서 잡기! (권한 거부 시 만화 배경, 45초)

## 규칙
- 남자가 **안 볼 때** 탭하면 성공 (일반 +50, 👑 황금 +120)
- 남자가 **뒤돌아볼 때(👀)** 잡으면 *딱 걸림!* — 콤보 끊기고 -40점
- 4콤보마다 점수 배수 증가 🔥 / 점수 랭크: 🐣 → ✨ → 💖 → 👑 → 💎

## 특징
- **Three.js 진짜 3D** — 절차적 머티리얼, 황혼 조명, 블룸·비네팅·필름그레인, ACES 톤매핑
- 캐릭터·도시·손 모두 코드로 생성(외부 모델/텍스처 없음), 단일 `index.html`(CDN ES 모듈)
