"""CLI: python3 -m automix <스템 폴더> [-o 출력.wav] [--target-lufs -14] [--reference 레퍼런스.wav]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .mixer import mix_directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="automix",
        description="멀티트랙(스템) 폴더를 넣으면 자동으로 믹스해주는 룰 베이스 자동 믹싱 엔진",
    )
    parser.add_argument("stems_dir", help="스템 오디오 파일들이 들어있는 폴더")
    parser.add_argument("-o", "--output", default=None, help="출력 파일 경로 (기본: <폴더명>_mix.wav)")
    parser.add_argument("--target-lufs", type=float, default=-14.0,
                        help="최종 믹스 목표 라우드니스 (기본 -14, 스트리밍 기준)")
    parser.add_argument("--reference", default=None,
                        help="레퍼런스 곡 파일. 주면 matchering으로 그 곡처럼 마스터링까지 수행")
    args = parser.parse_args(argv)

    stems_dir = Path(args.stems_dir)
    if not stems_dir.is_dir():
        parser.error(f"폴더가 아닙니다: {stems_dir}")
    output = Path(args.output) if args.output else stems_dir.parent / f"{stems_dir.name}_mix.wav"

    try:
        mix_directory(stems_dir, output, target_lufs=args.target_lufs, reference=args.reference)
    except (FileNotFoundError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
