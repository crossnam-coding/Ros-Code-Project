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

# 🚀 Space Shooter

누구나 즐길 수 있는 단일 파일 2D 슈팅 게임. 설치 없이 브라우저로 바로 플레이.

## 실행 방법
`index.html` 파일을 브라우저로 열면 끝.

## 조작
- 이동: 방향키 또는 `WASD`
- 발사: `Space`
- 일시정지: `P`

## 규칙
- 적 격추: 일반 +10점, 빨간 슈터 +30점
- 200점마다 레벨 업 → 적 등장이 빨라지고, 레벨 3부터 3방향 발사
- 생명 3개. 적과 충돌하거나 적탄에 맞으면 생명 1 감소
