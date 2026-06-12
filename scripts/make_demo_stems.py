"""테스트용 합성 스템 생성기.

실제 멀티트랙이 없을 때 파이프라인을 검증하기 위한 8초짜리 간단한 곡
(킥/스네어/하이햇/베이스/피아노/패드/가짜 보컬)을 demo_stems/에 만든다.

사용법: python3 scripts/make_demo_stems.py [출력폴더]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
BPM = 100
BEATS = 16  # 8초 분량 (4/4 × 4마디)
BEAT_SEC = 60.0 / BPM
TOTAL = int(SR * BEAT_SEC * BEATS)
T = np.arange(TOTAL) / SR


def env(decay: float, length: int) -> np.ndarray:
    return np.exp(-np.arange(length) / (SR * decay))


def place(track: np.ndarray, hit: np.ndarray, beat: float) -> None:
    start = int(beat * BEAT_SEC * SR)
    end = min(start + hit.shape[0], TOTAL)
    track[start:end] += hit[: end - start]


def kick() -> np.ndarray:
    out = np.zeros(TOTAL)
    n = int(SR * 0.35)
    t = np.arange(n) / SR
    freq = 110 * np.exp(-t * 18) + 45            # 피치 떨어지는 킥
    hit = np.sin(2 * np.pi * np.cumsum(freq) / SR) * env(0.12, n)
    hit[: int(SR * 0.004)] += np.random.randn(int(SR * 0.004)) * 0.4  # 어택 클릭
    for b in range(0, BEATS):
        place(out, hit * 0.9, b)
    return out


def snare() -> np.ndarray:
    out = np.zeros(TOTAL)
    n = int(SR * 0.22)
    hit = (np.random.randn(n) * 0.5 + np.sin(2 * np.pi * 190 * np.arange(n) / SR) * 0.5) * env(0.05, n)
    for b in range(1, BEATS, 2):
        place(out, hit * 0.8, b)
    return out


def hihat() -> np.ndarray:
    out = np.zeros(TOTAL)
    n = int(SR * 0.06)
    for i in range(BEATS * 2):
        hit = np.random.randn(n) * env(0.012, n) * (0.5 if i % 2 else 0.3)
        place(out, hit, i * 0.5)
    return out


NOTES = {"C2": 65.41, "G2": 98.0, "A2": 110.0, "F2": 87.31,
         "C4": 261.63, "E4": 329.63, "G4": 392.0, "A4": 440.0, "F4": 349.23}
PROGRESSION = ["C2", "G2", "A2", "F2"]  # 마디당 한 코드


def bass() -> np.ndarray:
    out = np.zeros(TOTAL)
    n = int(SR * BEAT_SEC * 0.9)
    for bar in range(4):
        f = NOTES[PROGRESSION[bar]]
        t = np.arange(n) / SR
        note = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)) * env(0.4, n)
        for b in range(4):
            place(out, note * 0.6, bar * 4 + b)
    return out


def piano() -> np.ndarray:
    out = np.zeros(TOTAL)
    chords = [["C4", "E4", "G4"], ["G4", "C4", "E4"], ["A4", "C4", "E4"], ["F4", "A4", "C4"]]
    n = int(SR * BEAT_SEC * 1.8)
    t = np.arange(n) / SR
    for bar in range(4):
        chord = sum(
            np.sin(2 * np.pi * NOTES[name] * t) + 0.2 * np.sin(2 * np.pi * 3 * NOTES[name] * t)
            for name in chords[bar]
        ) * env(0.7, n)
        place(out, chord * 0.25, bar * 4)
        place(out, chord * 0.2, bar * 4 + 2)
    return out


def pad() -> np.ndarray:
    out = np.zeros(TOTAL)
    n = int(SR * BEAT_SEC * 4)
    t = np.arange(n) / SR
    fade = np.minimum(1.0, np.minimum(t / 0.8, (n / SR - t) / 0.8))
    for bar in range(4):
        f = NOTES[PROGRESSION[bar]] * 4
        tone = sum(np.sin(2 * np.pi * f * r * t + r) for r in (1.0, 1.5, 2.0, 3.01)) * fade
        place(out, tone * 0.12, bar * 4)
    return out


def vocal() -> np.ndarray:
    """비브라토 걸린 사인 멜로디로 보컬 흉내."""
    out = np.zeros(TOTAL)
    melody = ["G4", "E4", "A4", "G4", "E4", "C4", "F4", "G4"]
    n = int(SR * BEAT_SEC * 1.6)
    t = np.arange(n) / SR
    fade = np.minimum(1.0, np.minimum(t / 0.05, (n / SR - t) / 0.3))
    for i, name in enumerate(melody):
        f = NOTES[name]
        vibrato = 1 + 0.012 * np.sin(2 * np.pi * 5.5 * t) * np.minimum(t / 0.4, 1)
        tone = (np.sin(2 * np.pi * f * vibrato * t)
                + 0.35 * np.sin(2 * np.pi * 2 * f * vibrato * t)
                + 0.15 * np.sin(2 * np.pi * 3 * f * vibrato * t)) * fade
        place(out, tone * 0.5, i * 2)
    return out


def vocal_shift(ratio: float, detune: float = 1.0) -> np.ndarray:
    """vocal()과 같은 멜로디를 음정 비율만 바꿔 하모니/더블 흉내."""
    out = np.zeros(TOTAL)
    melody = ["G4", "E4", "A4", "G4", "E4", "C4", "F4", "G4"]
    n = int(SR * BEAT_SEC * 1.6)
    t = np.arange(n) / SR
    fade = np.minimum(1.0, np.minimum(t / 0.05, (n / SR - t) / 0.3))
    for i, name in enumerate(melody):
        f = NOTES[name] * ratio * detune
        vib = 1 + 0.012 * np.sin(2 * np.pi * 5.2 * t) * np.minimum(t / 0.4, 1)
        tone = (np.sin(2 * np.pi * f * vib * t) + 0.3 * np.sin(2 * np.pi * 2 * f * vib * t)) * fade
        place(out, tone * 0.45, i * 2)
    return out


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo_stems")
    out_dir.mkdir(parents=True, exist_ok=True)
    stems = {
        "01_Kick.wav": kick(),
        "02_Snare.wav": snare(),
        "03_HiHat.wav": hihat(),
        "04_Bass.wav": bass(),
        "05_Piano.wav": piano(),
        "06_Pad.wav": pad(),
        "07_LeadVocal.wav": vocal(),
        "08_Vox_DBL.wav": vocal_shift(1.0, detune=1.004),   # 더블 (미세 디튠)
        "09_Harmony_Hi.wav": vocal_shift(1.25),             # 장3도 위 하모니
        "10_Adlib.wav": vocal_shift(1.5),                   # 5도 위 애드립 흉내
    }
    for name, audio in stems.items():
        peak = np.abs(audio).max()
        if peak > 0:
            audio = audio / peak * 0.7
        sf.write(str(out_dir / name), audio.astype(np.float32), SR)
        print(f"  {out_dir / name}")
    print(f"데모 스템 {len(stems)}개 생성 완료 → {out_dir}/")


if __name__ == "__main__":
    main()
