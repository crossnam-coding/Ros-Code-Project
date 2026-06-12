"""스템의 악기 종류 판별.

1차: 파일명 키워드 매칭 (영어/한국어/약어)
2차: 파일명으로 알 수 없으면 스펙트럼 휴리스틱으로 추정
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

# 분류 가능한 악기군. chains.py의 프로파일 키와 1:1 대응한다.
ROLES = (
    "kick",
    "snare",
    "hihat",
    "drums",      # 드럼 버스/오버헤드/룸 등 통드럼
    "percussion",
    "bass",
    "guitar",
    "piano",
    "keys",
    "synth",
    "pad",
    "strings",
    "brass",
    "vocal",
    "backing_vocal",
    "fx",
    "other",
)

# 키워드 → 악기군. 위에서부터 순서대로 검사하므로 구체적인 것을 먼저 둔다.
_KEYWORD_RULES: list[tuple[str, str]] = [
    (r"back(ing)?[ _-]?vo|bgv|chorus[ _-]?vo|harmony|코러스|백보컬", "backing_vocal"),
    (r"vo(x|cal|ice)?\b|vocal|lead[ _-]?vo|acapella|보컬|목소리|노래", "vocal"),
    (r"kick|bd\b|bass[ _-]?drum|킥", "kick"),
    (r"snare|sd\b|rim|clap|스네어|클랩", "snare"),
    (r"hi[ _-]?hat|hat|hh\b|하이햇|햇", "hihat"),
    (r"overhead|oh\b|cymbal|ride|crash|room|tom|drum|드럼|탐|심벌", "drums"),
    (r"perc|shaker|tamb|conga|bongo|cajon|퍼커션|쉐이커", "percussion"),
    (r"(?<![a-z])bass|sub\b|808|베이스", "bass"),
    (r"guitar|gtr|gt\b|akg\b|elec[ _-]?g|acoustic[ _-]?g|기타", "guitar"),
    (r"piano|pno|grand|rhodes|epiano|e\.p|피아노", "piano"),
    (r"organ|keys|key\b|clav|건반|키즈", "keys"),
    (r"pad|패드", "pad"),
    (r"synth|saw|pluck|arp|lead(?![ _-]?vo)|신스|리드", "synth"),
    (r"string|violin|viola|cello|orch|스트링|현악", "strings"),
    (r"brass|horn|trumpet|sax|trombone|브라스|혼|색소폰", "brass"),
    (r"fx|riser|sweep|impact|whoosh|noise|효과", "fx"),
]


@dataclass
class StemFeatures:
    """스펙트럼 휴리스틱에 쓰는 간단한 특징값."""

    spectral_centroid_hz: float   # 밝기
    low_energy_ratio: float       # 200Hz 이하 에너지 비율
    percussiveness: float         # 크레스트 팩터 기반 타악기성 (0~1 근사)


def classify_by_name(filename: str) -> str | None:
    """파일명 키워드로 악기군을 판별한다. 못 찾으면 None."""
    name = filename.lower()
    # "01_Kick.wav" 같은 트랙 번호 접두사는 무시
    name = re.sub(r"^\d+[ _.-]*", "", name)
    for pattern, role in _KEYWORD_RULES:
        if re.search(pattern, name):
            return role
    return None


def compute_features(audio: np.ndarray, sr: int) -> StemFeatures:
    """모노 합산 신호에서 분류용 특징을 뽑는다."""
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    # 너무 길면 가운데 60초만 분석 (속도)
    max_samples = sr * 60
    if mono.shape[0] > max_samples:
        start = (mono.shape[0] - max_samples) // 2
        mono = mono[start : start + max_samples]

    spectrum = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(mono.shape[0], d=1.0 / sr)
    power = spectrum**2
    total = power.sum() + 1e-12

    centroid = float((freqs * power).sum() / total)
    low_ratio = float(power[freqs <= 200].sum() / total)

    # 크레스트 팩터(피크/RMS)가 클수록 타악기적
    rms = float(np.sqrt((mono**2).mean()) + 1e-12)
    crest = float(np.abs(mono).max() / rms)
    percussiveness = min(crest / 20.0, 1.0)

    return StemFeatures(centroid, low_ratio, percussiveness)


def classify_by_features(f: StemFeatures) -> str:
    """파일명으로 못 알아낸 스템을 스펙트럼으로 대충 분류한다."""
    if f.low_energy_ratio > 0.75:
        # 저음 위주: 짧고 타격감 있으면 킥, 길게 유지되면 베이스
        return "kick" if f.percussiveness > 0.55 else "bass"
    if f.spectral_centroid_hz > 4000 and f.percussiveness > 0.5:
        return "hihat"
    if f.percussiveness > 0.6:
        return "percussion"
    if f.spectral_centroid_hz < 800:
        return "keys"
    return "other"


def classify(filename: str, audio: np.ndarray, sr: int) -> tuple[str, str]:
    """악기군과 판별 근거('name' 또는 'spectrum')를 반환한다."""
    role = classify_by_name(filename)
    if role is not None:
        return role, "name"
    return classify_by_features(compute_features(audio, sr)), "spectrum"
