"""소스를 '듣고' 판단하기 위한 스펙트럼 분석 도구.

실제 엔지니어가 귀로 하는 일의 근사:
  - 트랙에서 실제로 튀는 공진 대역 찾기 (find_resonances)
  - 킥/베이스의 기음 위치 찾기 → 마스킹 카빙에 사용 (find_low_fundamental)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks, welch


@dataclass
class ResonanceCut:
    freq: float
    gain_db: float  # 음수 (컷)
    q: float
    excess_db: float  # 주변 대비 얼마나 튀었는지

    def describe(self) -> str:
        return f"{self.freq:.0f}Hz {self.gain_db:.1f}dB (Q{self.q:.1f}, 공진 +{self.excess_db:.1f}dB)"


def _mono(audio: np.ndarray) -> np.ndarray:
    return audio.mean(axis=1) if audio.ndim == 2 else audio


def average_spectrum_db(audio: np.ndarray, sr: int, nfft: int = 8192) -> tuple[np.ndarray, np.ndarray]:
    """Welch 평균 파워 스펙트럼 (freqs, dB)."""
    mono = _mono(audio)
    max_samples = sr * 60
    if mono.shape[0] > max_samples:
        start = (mono.shape[0] - max_samples) // 2
        mono = mono[start : start + max_samples]
    freqs, psd = welch(mono, fs=sr, nperseg=min(nfft, mono.shape[0]))
    return freqs, 10.0 * np.log10(psd + 1e-20)


def find_resonances(
    audio: np.ndarray,
    sr: int,
    fmin: float = 250.0,   # 그 아래는 악기 기음일 가능성이 높아 건드리지 않는다
    fmax: float = 8000.0,
    min_excess_db: float = 12.0,
    max_cuts: int = 2,
) -> list[ResonanceCut]:
    """주변(±1/2 옥타브 추세) 대비 min_excess_db 이상 튀는 좁은 공진을 찾는다.

    엔지니어가 좁은 Q로 스윕하면서 '울리는 데'를 찾아 깎는 작업의 자동화.
    찾은 공진은 좁은 Q(4.0)로, 튀어나온 만큼의 60%를 (최대 6dB) 깎는다.
    """
    freqs, spec_db = average_spectrum_db(audio, sr)

    # 로그 주파수 격자로 옮겨서 1/2 옥타브 스케일로 추세선을 만든다
    valid = freqs > 20
    freqs, spec_db = freqs[valid], spec_db[valid]
    if freqs.shape[0] < 32:
        return []
    log_grid = np.linspace(np.log2(freqs[0]), np.log2(freqs[-1]), 1024)
    spec_log = np.interp(log_grid, np.log2(freqs), spec_db)
    octaves_per_bin = (log_grid[-1] - log_grid[0]) / 1024
    trend = gaussian_filter1d(spec_log, sigma=0.5 / octaves_per_bin)
    excess = spec_log - trend

    grid_hz = 2.0**log_grid
    in_range = (grid_hz >= fmin) & (grid_hz <= fmax)
    peaks, props = find_peaks(np.where(in_range, excess, -np.inf), height=min_excess_db)
    if peaks.shape[0] == 0:
        return []

    # 가장 심한 것부터 max_cuts개
    order = np.argsort(props["peak_heights"])[::-1][:max_cuts]
    cuts = []
    for idx in order:
        p = peaks[idx]
        excess_db = float(excess[p])
        cuts.append(ResonanceCut(
            freq=float(grid_hz[p]),
            gain_db=-min(excess_db * 0.6, 6.0),
            q=4.0,
            excess_db=excess_db,
        ))
    return sorted(cuts, key=lambda c: c.freq)


def find_low_fundamental(audio: np.ndarray, sr: int, fmin: float = 30.0, fmax: float = 120.0) -> float | None:
    """저음 악기(킥/베이스)의 기음 주파수를 찾는다. 마스킹 카빙의 기준점."""
    freqs, spec_db = average_spectrum_db(audio, sr)
    mask = (freqs >= fmin) & (freqs <= fmax)
    if not mask.any():
        return None
    band_freqs, band_db = freqs[mask], spec_db[mask]
    return float(band_freqs[int(np.argmax(band_db))])
