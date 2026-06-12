"""시간에 따라 변하는 처리 — 디에서, 사이드체인 덕킹.

고정 EQ/컴프와 달리 신호를 따라가며 그때그때 게인을 움직이는,
엔지니어의 '손 타는' 작업에 해당하는 부분.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt


_ENV_BLOCK = 32  # 엔벨로프는 느리게 변하므로 블록 피크로 다운샘플해서 계산 (속도 ~32배)


def envelope_follower(signal: np.ndarray, sr: int, attack_ms: float, release_ms: float) -> np.ndarray:
    """절댓값 신호를 어택/릴리즈 원폴 스무딩한 엔벨로프."""
    rect = np.abs(signal)
    n = rect.shape[0]
    pad = (-n) % _ENV_BLOCK
    if pad:
        rect = np.concatenate([rect, np.zeros(pad)])
    blocks = rect.reshape(-1, _ENV_BLOCK).max(axis=1)  # 블록 피크 (트랜지언트 보존)

    block_sr = sr / _ENV_BLOCK
    atk = np.exp(-1.0 / max(block_sr * attack_ms / 1000.0, 1e-3))
    rel = np.exp(-1.0 / max(block_sr * release_ms / 1000.0, 1e-3))
    env = np.empty_like(blocks)
    prev = 0.0
    for i in range(blocks.shape[0]):
        x = blocks[i]
        coeff = atk if x > prev else rel
        prev = coeff * prev + (1.0 - coeff) * x
        env[i] = prev
    return np.repeat(env, _ENV_BLOCK)[:n]


def deess(
    audio: np.ndarray,
    sr: int,
    band: tuple[float, float] = (4500.0, 9000.0),
    threshold_above_rms_db: float = 8.0,
    ratio: float = 3.0,
    max_reduction_db: float = 8.0,
) -> tuple[np.ndarray, float]:
    """치찰음 대역만 눌러주는 디에서. (결과, 최대 감쇠량 dB)을 반환.

    원리: 4.5~9kHz 대역을 분리해 그 대역의 평균보다 일정 이상 커지는
    순간에만 비율 압축으로 깎고 다시 합친다.
    """
    nyq = sr / 2.0
    hi = min(band[1], nyq * 0.95)
    sos = butter(4, [band[0] / nyq, hi / nyq], btype="band", output="sos")
    sib = sosfilt(sos, audio, axis=0)

    env = envelope_follower(sib.mean(axis=1) if sib.ndim == 2 else sib, sr, attack_ms=1.5, release_ms=60.0)
    env_db = 20.0 * np.log10(env + 1e-12)
    band_rms_db = 20.0 * np.log10(float(np.sqrt((sib**2).mean())) + 1e-12)
    threshold_db = band_rms_db + threshold_above_rms_db

    over = np.maximum(env_db - threshold_db, 0.0)
    reduction_db = np.minimum(over * (1.0 - 1.0 / ratio), max_reduction_db)
    gain = (10.0 ** (-reduction_db / 20.0))[:, None] if audio.ndim == 2 else 10.0 ** (-reduction_db / 20.0)

    out = (audio - sib) + sib * gain
    return out, float(reduction_db.max())


def ducking_gain(trigger: np.ndarray, sr: int, depth: float, attack_ms: float = 5.0, release_ms: float = 120.0) -> np.ndarray:
    """트리거 신호(예: 킥)가 칠 때 깎을 게인 곡선을 만든다.

    depth=0.3이면 트리거 피크 순간 약 -3dB. 반환값 shape는 (samples,).
    """
    mono = trigger.mean(axis=1) if trigger.ndim == 2 else trigger
    env = envelope_follower(mono, sr, attack_ms, release_ms)
    peak = float(np.percentile(env, 99.5)) + 1e-12
    env = np.clip(env / peak, 0.0, 1.0)
    return 1.0 - depth * env


def apply_ducking(audio: np.ndarray, gain: np.ndarray) -> np.ndarray:
    n = min(audio.shape[0], gain.shape[0])
    out = audio.copy()
    out[:n] *= gain[:n, None] if audio.ndim == 2 else gain[:n]
    return out
