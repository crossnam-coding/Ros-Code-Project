"""자동 믹싱 파이프라인 본체.

룰 베이스 정석 체인에 더해, 소스를 분석해서 반응하는 처리(엔지니어 방식)를 수행한다:
  - 공진 감지 EQ: 트랙에서 실제로 튀는 좁은 대역을 찾아서 깎음
  - 마스킹 카빙: 킥 기음 주파수를 찾아 베이스에서 그 자리를 비켜줌,
    보컬이 있으면 미드 악기들의 3kHz를 살짝 양보
  - 디에서: 보컬 치찰음 대역만 동적으로 억제
  - 사이드체인 덕킹: 킥이 칠 때 베이스를, 보컬이 나올 때 패드/스트링을 살짝 눌러줌
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile as sf
from pedalboard import Compressor, HighShelfFilter, Limiter, PeakFilter, Pedalboard, Reverb
from scipy.signal import resample_poly

from .analysis import find_low_fundamental, find_resonances
from .chains import PROFILES, RoleProfile, build_chain, describe_chain
from .classify import classify
from .dynamics import apply_ducking, deess, ducking_gain

AUDIO_EXTENSIONS = {".wav", ".flac", ".aif", ".aiff", ".ogg", ".mp3"}

# 게인 스테이징: 모든 스템을 체인에 넣기 전 이 라우드니스로 정렬한다.
# 컴프레서 스레숄드가 예측 가능하게 동작하게 하기 위한 작업 레벨.
PRE_CHAIN_LUFS = -20.0

# 믹스 안에서 보컬(offset 0.0)이 갖는 기준 라우드니스. 다른 악기는 상대 오프셋.
BALANCE_REF_LUFS = -18.0

# 공진 감지 EQ를 적용할 악기군 (트랜지언트 위주 악기는 오탐이 많아 제외)
RESONANCE_ROLES = {"vocal", "backing_vocal", "guitar", "piano", "keys", "synth",
                   "bass", "strings", "brass", "snare", "other"}

# 보컬이 있을 때 3kHz 자리를 양보하는 악기군
VOCAL_CARVE_ROLES = {"guitar", "piano", "keys", "synth", "pad", "strings", "brass"}

# 보컬 덕킹을 받는 악기군 (보컬이 나올 때 살짝 물러나는 배경 악기)
VOCAL_DUCK_ROLES = {"pad", "strings"}


@dataclass
class StemResult:
    """리포트용: 스템 하나가 어떻게 처리됐는지 기록."""

    filename: str
    role: str
    role_label: str
    classified_by: str
    input_lufs: float
    target_lufs: float
    pan: float
    reverb_send: float
    chain_description: str
    notes: list[str] = field(default_factory=list)  # 소스 반응형 처리 내역


def _to_stereo(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return np.stack([audio, audio], axis=1)
    if audio.shape[1] == 1:
        return np.repeat(audio, 2, axis=1)
    if audio.shape[1] > 2:
        return audio[:, :2]
    return audio


def _measure_lufs(audio: np.ndarray, sr: int) -> float:
    """무음/초단편 파일에서도 죽지 않는 LUFS 측정."""
    if audio.shape[0] < int(sr * 0.5):
        return float("-inf")
    try:
        loudness = pyloudnorm.Meter(sr).integrated_loudness(audio)
    except ValueError:
        return float("-inf")
    return float(loudness)


def _gain_to_lufs(audio: np.ndarray, sr: int, target_lufs: float) -> tuple[np.ndarray, float]:
    """target_lufs가 되도록 게인을 걸고 (결과, 적용 게인 dB)을 반환."""
    current = _measure_lufs(audio, sr)
    if not math.isfinite(current):
        return audio, 0.0
    gain_db = target_lufs - current
    gain_db = float(np.clip(gain_db, -40.0, 40.0))
    return audio * (10.0 ** (gain_db / 20.0)), gain_db


def _apply_pan(audio: np.ndarray, pan: float) -> np.ndarray:
    """등파워 패닝. pan: -1(L) ~ +1(R). 스테레오 입력에는 밸런스로 적용."""
    theta = (np.clip(pan, -1.0, 1.0) + 1.0) * (math.pi / 4.0)
    left_gain = math.cos(theta) * math.sqrt(2.0)   # sqrt(2) 보정: 센터에서 0dB
    right_gain = math.sin(theta) * math.sqrt(2.0)
    out = audio.copy()
    out[:, 0] *= left_gain
    out[:, 1] *= right_gain
    return out


def _assign_pans(stems_in_role: int, profile: RoleProfile) -> list[float]:
    """같은 악기군 스템들의 팬 위치를 정한다. 1개면 기본 위치, 여러 개면 좌우로 벌림."""
    # pan_spread가 0인 악기(킥/베이스/보컬 등)는 여러 개여도 전부 기본 위치 유지
    if stems_in_role == 1 or profile.pan_spread <= 0:
        return [profile.pan] * stems_in_role
    # -spread/2 ~ +spread/2 사이에 균등 배치 (예: 기타 2개 → L/R 대칭)
    positions = np.linspace(-profile.pan_spread / 2.0, profile.pan_spread / 2.0, stems_in_role)
    return [float(np.clip(p + profile.pan * 0.2, -1.0, 1.0)) for p in positions]


def _load_audio(path: Path, target_sr: int | None) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(str(path), always_2d=True, dtype="float32")
    if target_sr is not None and sr != target_sr:
        g = math.gcd(sr, target_sr)
        audio = resample_poly(audio, target_sr // g, sr // g, axis=0).astype(np.float32)
        sr = target_sr
    return audio, sr


def find_stems(stems_dir: Path) -> list[Path]:
    files = sorted(
        p for p in stems_dir.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )
    if not files:
        raise FileNotFoundError(f"{stems_dir} 안에 오디오 파일이 없습니다 ({'/'.join(sorted(AUDIO_EXTENSIONS))})")
    return files


@dataclass
class _Stem:
    path: Path
    audio: np.ndarray          # 처리 단계에 따라 갱신됨
    role: str
    classified_by: str
    input_lufs: float
    pan: float = 0.0
    result: StemResult | None = None


def mix_directory(
    stems_dir: str | Path,
    output_path: str | Path,
    target_lufs: float = -14.0,
    reference: str | Path | None = None,
    verbose: bool = True,
) -> list[StemResult]:
    """스템 폴더를 읽어 자동 믹스한 스테레오 파일을 출력한다.

    reference를 주면 matchering으로 레퍼런스 곡에 맞춰 마스터링까지 수행한다
    (matchering 미설치 시 안내 후 일반 리미팅으로 마무리).
    """
    stems_dir = Path(stems_dir)
    output_path = Path(output_path)
    files = find_stems(stems_dir)

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    # ── 1. 로드: 샘플레이트 통일(최고값), 스테레오 변환 ──────────────
    rates = [sf.info(str(p)).samplerate for p in files]
    sr = max(rates)
    log(f"스템 {len(files)}개 로드 (샘플레이트 {sr}Hz로 통일)")

    stems: list[_Stem] = []
    for path in files:
        audio, _ = _load_audio(path, sr)
        audio = _to_stereo(audio)
        input_lufs = _measure_lufs(audio, sr)
        if not math.isfinite(input_lufs):
            log(f"  [건너뜀] {path.name}: 무음이거나 너무 짧음")
            continue
        role, how = classify(path.name, audio, sr)
        stems.append(_Stem(path, audio, role, how, input_lufs))

    if not stems:
        raise ValueError("처리 가능한 스템이 없습니다 (전부 무음/초단편).")
    length = max(s.audio.shape[0] for s in stems)

    # ── 2. 곡 전체 컨텍스트 분석 (마스킹 카빙/덕킹의 기준) ─────────────
    kick_stems = [s for s in stems if s.role == "kick"]
    has_vocal = any(s.role == "vocal" for s in stems)
    kick_f0 = None
    if kick_stems:
        kick_f0 = find_low_fundamental(kick_stems[0].audio, sr)
        if kick_f0:
            log(f"킥 기음 감지: {kick_f0:.0f}Hz → 베이스가 이 대역을 비켜줍니다")

    # 같은 악기군 개수를 세서 팬 위치 배정
    role_counts: dict[str, int] = {}
    for s in stems:
        role_counts[s.role] = role_counts.get(s.role, 0) + 1
    role_pan_queue: dict[str, list[float]] = {
        role: _assign_pans(count, PROFILES[role]) for role, count in role_counts.items()
    }

    # ── 3. 트랙별 처리 ─────────────────────────────────────────
    #    게인 스테이징 → 공진 감지 EQ → 정석 체인 → 디에서 → 밸런스 → 카빙 → 팬
    for s in stems:
        profile = PROFILES[s.role]
        target = BALANCE_REF_LUFS + profile.target_lufs_offset
        s.pan = role_pan_queue[s.role].pop(0)
        notes: list[str] = []

        audio, _ = _gain_to_lufs(s.audio, sr, PRE_CHAIN_LUFS)

        if s.role in RESONANCE_ROLES:
            cuts = find_resonances(audio, sr)
            if cuts:
                eq = Pedalboard([PeakFilter(cutoff_frequency_hz=c.freq, gain_db=c.gain_db, q=c.q) for c in cuts])
                audio = eq(audio.T, sr).T
                notes.append("공진 컷: " + ", ".join(c.describe() for c in cuts))

        audio = build_chain(profile)(audio.T, sr).T  # pedalboard는 (ch, samples)

        if s.role in ("vocal", "backing_vocal"):
            audio, max_red = deess(audio, sr)
            if max_red > 0.5:
                notes.append(f"디에서: 최대 -{max_red:.1f}dB (4.5~9kHz)")

        audio, _ = _gain_to_lufs(audio, sr, target)

        carve = []
        if s.role == "bass" and kick_f0:
            carve.append(PeakFilter(cutoff_frequency_hz=kick_f0, gain_db=-2.5, q=1.4))
            notes.append(f"마스킹 카빙: 킥 기음 {kick_f0:.0f}Hz -2.5dB")
        if s.role in VOCAL_CARVE_ROLES and has_vocal:
            carve.append(PeakFilter(cutoff_frequency_hz=3000, gain_db=-1.5, q=0.8))
            notes.append("보컬 자리 양보: 3kHz -1.5dB")
        if carve:
            audio = Pedalboard(carve)(audio.T, sr).T

        s.audio = _apply_pan(audio, s.pan)
        s.result = StemResult(
            filename=s.path.name,
            role=s.role,
            role_label=profile.label,
            classified_by="파일명" if s.classified_by == "name" else "스펙트럼 분석",
            input_lufs=s.input_lufs,
            target_lufs=target,
            pan=s.pan,
            reverb_send=profile.reverb_send,
            chain_description=describe_chain(profile),
            notes=notes,
        )
        extra = f" | {' / '.join(notes)}" if notes else ""
        log(f"  [{profile.label}] {s.path.name} → 목표 {target:.1f}LUFS, "
            f"팬 {s.pan:+.2f}, 리버브 {profile.reverb_send:.0%}{extra}")

    # ── 4. 사이드체인 덕킹: 킥→베이스, 보컬→패드/스트링 ────────────────
    def _trigger(roles: tuple[str, ...]) -> np.ndarray | None:
        sources = [s.audio for s in stems if s.role in roles]
        if not sources:
            return None
        out = np.zeros(length)
        for src in sources:
            out[: src.shape[0]] += src.mean(axis=1)
        return out

    kick_trigger = _trigger(("kick",))
    if kick_trigger is not None and any(s.role == "bass" for s in stems):
        gain = ducking_gain(kick_trigger, sr, depth=0.3)
        for s in stems:
            if s.role == "bass":
                s.audio = apply_ducking(s.audio, gain)
                s.result.notes.append("사이드체인 덕킹: 킥이 칠 때 최대 -3dB")
        log("덕킹: 킥 → 베이스 (최대 -3dB)")

    vocal_trigger = _trigger(("vocal",))
    duck_targets = [s for s in stems if s.role in VOCAL_DUCK_ROLES]
    if vocal_trigger is not None and duck_targets:
        gain = ducking_gain(vocal_trigger, sr, depth=0.2, attack_ms=15, release_ms=250)
        for s in duck_targets:
            s.audio = apply_ducking(s.audio, gain)
            s.result.notes.append("사이드체인 덕킹: 보컬이 나올 때 최대 -2dB")
        log("덕킹: 보컬 → 패드/스트링 (최대 -2dB)")

    # ── 5. 합산 + 공용 리버브 버스 (공간감) ─────────────────────────
    mix_bus = np.zeros((length, 2), dtype=np.float64)
    reverb_send_bus = np.zeros((length, 2), dtype=np.float64)
    for s in stems:
        mix_bus[: s.audio.shape[0]] += s.audio
        reverb_send_bus[: s.audio.shape[0]] += s.audio * PROFILES[s.role].reverb_send

    log("리버브 버스 처리 중...")
    reverb = Pedalboard([Reverb(room_size=0.55, damping=0.5, wet_level=1.0, dry_level=0.0, width=1.0)])
    reverb_return = reverb(reverb_send_bus.T.astype(np.float32), sr).T.astype(np.float64)
    mix_bus += reverb_return[:length]

    # ── 6. 믹스 버스: 글루 컴프 → 에어 → 라우드니스 정렬 → 리미터 ───────
    log("믹스 버스 처리 중...")
    bus_chain = Pedalboard([
        Compressor(threshold_db=-14, ratio=2.0, attack_ms=30, release_ms=200),
        HighShelfFilter(cutoff_frequency_hz=11000, gain_db=1.0),
    ])
    mix = bus_chain(mix_bus.T.astype(np.float32), sr).T.astype(np.float64)
    mix, _ = _gain_to_lufs(mix, sr, target_lufs)
    mix = Pedalboard([Limiter(threshold_db=-1.0, release_ms=100)])(
        mix.T.astype(np.float32), sr
    ).T.astype(np.float64)
    # pedalboard 리미터는 메이크업 게인이 붙으므로 목표보다 커지면 깎아서 맞춘다
    # (낮추는 방향은 피크를 다시 만들지 않아 안전)
    post_lufs = _measure_lufs(mix, sr)
    if math.isfinite(post_lufs) and post_lufs > target_lufs:
        mix *= 10.0 ** ((target_lufs - post_lufs) / 20.0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), mix.astype(np.float32), sr, subtype="PCM_24")
    final_lufs = _measure_lufs(mix, sr)
    log(f"믹스 완료 → {output_path} ({final_lufs:.1f} LUFS, {sr}Hz/24bit)")

    # ── 7. (선택) 레퍼런스 마스터링 ──────────────────────────────
    if reference is not None:
        _master_with_reference(output_path, Path(reference), log)

    results = [s.result for s in stems]
    _write_report(output_path, results, final_lufs, target_lufs)
    return results


def _master_with_reference(mix_path: Path, reference: Path, log) -> None:
    try:
        import matchering as mg
    except ImportError:
        log("matchering이 설치돼 있지 않아 레퍼런스 마스터링을 건너뜁니다. "
            "(pip install matchering)")
        return
    mastered = mix_path.with_name(mix_path.stem + "_mastered.wav")
    log(f"레퍼런스({reference.name}) 기준 마스터링 중...")
    mg.process(
        target=str(mix_path),
        reference=str(reference),
        results=[mg.pcm24(str(mastered))],
    )
    log(f"마스터링 완료 → {mastered}")


def _write_report(output_path: Path, results: list[StemResult], final_lufs: float, target_lufs: float) -> None:
    """믹스 결정 내역을 마크다운 리포트로 남긴다."""
    report_path = output_path.with_suffix(".report.md")
    lines = [
        "# 자동 믹스 리포트",
        "",
        f"- 출력: `{output_path.name}`",
        f"- 최종 라우드니스: {final_lufs:.1f} LUFS (목표 {target_lufs:.1f})",
        f"- 스템 수: {len(results)}",
        "",
        "| 파일 | 악기 판별 | 근거 | 입력 LUFS | 목표 LUFS | 팬 | 리버브 센드 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        pan_str = "C" if abs(r.pan) < 0.05 else (f"L{abs(r.pan) * 100:.0f}" if r.pan < 0 else f"R{r.pan * 100:.0f}")
        lines.append(
            f"| {r.filename} | {r.role_label} | {r.classified_by} | "
            f"{r.input_lufs:.1f} | {r.target_lufs:.1f} | {pan_str} | {r.reverb_send:.0%} |"
        )
    lines += ["", "## 트랙별 이펙트 체인", ""]
    for r in results:
        lines.append(f"- **{r.filename}** ({r.role_label}): {r.chain_description}")
    lines += ["", "## 소스 반응형 처리 (분석 기반)", ""]
    any_notes = False
    for r in results:
        for note in r.notes:
            lines.append(f"- **{r.filename}**: {note}")
            any_notes = True
    if not any_notes:
        lines.append("- (해당 없음)")
    lines += [
        "",
        "## 믹스 버스",
        "",
        "- 글루 컴프 2:1 (thr -14dB, atk 30ms, rel 200ms)",
        "- 에어 쉘프 11kHz +1dB",
        f"- 라우드니스 정렬 {target_lufs:.1f} LUFS → 리미터 -1dBFS",
        "- 공용 리버브 버스: room 0.55, 트랙별 센드 양은 위 표 참고",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
