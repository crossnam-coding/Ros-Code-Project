#!/usr/bin/env bash
# automix 셋업 — 파이썬 의존성 설치 후 데모 믹스로 동작 검증.
# 사용법:  bash setup.sh        (가상환경 .venv 생성 + 설치 + 데모 믹스)
#          bash setup.sh --no-demo   (데모 믹스 건너뛰기)
set -euo pipefail

cd "$(dirname "$0")"
echo "▶ automix 셋업 시작 ($(pwd))"

# 1. 파이썬 확인 (3.9+ 권장)
if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ python3 가 필요합니다. https://www.python.org/downloads/ 에서 설치하세요." >&2
  exit 1
fi
echo "  파이썬: $(python3 --version)"

# 2. 가상환경 (.venv) — 시스템 파이썬을 건드리지 않음
if [ ! -d .venv ]; then
  echo "▶ 가상환경 생성 (.venv)"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 3. 의존성 설치
echo "▶ 의존성 설치 중..."
python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r requirements.txt
echo "  설치 완료: pedalboard, soundfile, numpy, scipy, pyloudnorm"
echo "  (레퍼런스 마스터링까지 쓰려면:  pip install matchering )"

# 4. 동작 검증: 합성 데모 스템으로 한 곡 믹스
if [ "${1:-}" != "--no-demo" ]; then
  echo "▶ 데모 믹스로 동작 검증 중..."
  python3 scripts/make_demo_stems.py demo_stems >/dev/null
  python3 -m automix demo_stems -o output/demo_mix.wav
  echo ""
  echo "✓ 셋업 완료. 데모 결과: output/demo_mix.wav  (리포트: output/demo_mix.report.md)"
fi

cat <<'EOF'

──────────────────────────────────────────────
다음부터는 이렇게 쓰면 됩니다:

  source .venv/bin/activate           # 가상환경 켜기 (터미널 새로 열 때마다)
  python3 -m automix "스템폴더" -o "내곡_mix.wav"

  # 레퍼런스 곡에 맞춰 마스터링까지:
  python3 -m automix "스템폴더" -o "내곡_mix.wav" --reference "레퍼런스.wav"
──────────────────────────────────────────────
EOF
