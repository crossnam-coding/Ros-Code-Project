"""자동 믹싱 파이프라인 본체.

구조: 트랙 → 그룹 버스 → 믹스 버스 (실제 세션 워크플로우와 동일)

트랙 레벨 (소스 반응형 처리 포함):
  - 공진 감지 EQ, 정석 체인(HPF→EQ→컴프), 디에서(보컬류), LUFS 밸런스,
    마스킹 카빙(킥 기음↔베이스, 보컬↔미드 악기), 등파워 패닝
버스 레벨:
  - 그룹별 글루 컴프/캐릭터 EQ (리드/더블/하모니/애드립/떼창/드럼/베이스/뮤직)
  - 리드 보컬이 나올 때 백킹 보컬 버스들을 사이드체인 덕킹 ("리드가 왕")
공간:
  - 가까운 플레이트(리드/더블/스네어 등) + 먼 홀(하모니/떼창/패드/스트링) 2개 리버브 버스

메모리: 트랙을 한 번에 다 들고 있지 않고 버스 순서대로 로드→처리→합산→해제.
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
from .chains import (
    BUSES,
    PROFILES,
    ROLE_TO_BUS,
    RoleProfile,
    build_bus_chain,
    build_chain,
    describe_bus,
    describe_chain,
)
from .classify import classify_by_name, classify_by_features, compute_features
from .dynamics import apply_ducking, deess, ducking_gain

AUDIO_EXTENSIONS = {".wav", ".flac", ".aif", ".aiff", ".ogg", ".mp3"}

# 게인 스테이징: 모든 스템을 체인에 넣기 전 이 라우드니스로 정렬한다.
PRE_CHAIN_LUFS = -20.0

# 믹스 안에서 리드 보컬(offset 0.0)이 갖는 기준 라우드니스. 다른 악기는 상대 오프셋.
BALANCE_REF_LUFS = -18.0

# 공진 감지 EQ를 적용할 악기군 (트랜지언트 위주 악기는 오탐이 많아 제외)
RESONANCE_ROLES = {"vocal", "backing_vocal", "vocal_double", "vocal_harmony", "vocal_adlib",
                   "vocal_chant", "guitar", "piano", "keys", "synth", "bass", "strings",
                   "brass", "snare", "other"}

# 디에서를 적용할 보컬류
DEESS_ROLES = {"vocal", "backing_vocal", "vocal_double", "vocal_harmony", "vocal_adlib", "vocal_chant"}

# 보컬이 있을 때 3kHz 자리를 양보하는 악기군
VOCAL_CARVE_ROLES = {"guitar", "piano", "keys", "synth", "pad", "strings", "brass"}

# 리드 보컬 덕킹을 받는 악기 (트랙 레벨 — 버스 레벨 덕킹은 BUSES 정의 참고)
VOCAL_DUCK_ROLES = {"pad", "strings"}


@dataclass
class StemResult:
    """리포트용: 스템 하나가 어떻게 처리됐는지 기록."""

    filename: str
    role: str
    role_label: str
    bus_label: str
    classified_by: str
    input_lufs: float
    target_lufs: float
    pan: float
    reverb_send: float
    space: str
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
    if stems_in_role == 1 or profile.pan_spread <= 0:
        return [profile.pan] * stems_in_role
    positions = np.linspace(-profile.pan_spread / 2.0, profile.pan_spread / 2.0, stems_in_role)
    return [float(np.clip(p + profile.pan * 0.2, -1.0, 1.0)) for p in positions]


def _load_audio(path: Path, target_sr: int | None) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(str(path), always_2d=True, dtype="float32")
    if target_sr is not None and sr != target_sr:
        g = math.gcd(sr, target_sr)
        audio = resample_poly(audio, target_sr // g, sr // g, axis=0).astype(np.float32)
        sr = target_sr
    return _to_stereo(audio)


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
    role: str
    classified_by: str
    est_length: int      # 리샘플 반영한 예상 샘플 수
    pan: float = 0.0
    result: StemResult | None = None


def mix_directory(
    stems_dir: str | Path,
    output_path: str | Path,
    target_lufs: float = -14.0,
    reference: str | Path | None = None,
    verbose: bool = True,
) -> list[StemResult]:
    """스템 폴더를 읽어 자동 믹스한 스테레오 파일을 출력한다."""
    stems_dir = Path(stems_dir)
    output_path = Path(output_path)
    files = find_stems(stems_dir)

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    # ── 1. 메타데이터 수집 + 분류 (오디오는 필요할 때만 로드) ──────────
    infos = {p: sf.info(str(p)) for p in files}
    sr = max(i.samplerate for i in infos.values())
    stems: list[_Stem] = []
    for path in files:
        info = infos[path]
        est_length = int(info.frames * sr / info.samplerate)
        role = classify_by_name(path.name)
        how = "파일명"
        if role is None:
            audio = _load_audio(path, None)  # 원본 샘플레이트로 빠르게
            role = classify_by_features(compute_features(audio, info.samplerate))
            how = "스펙트럼 분석"
            del audio
        stems.append(_Stem(path, role, how, est_length))
    length = max(s.est_length for s in stems)
    log(f"스템 {len(stems)}개 / 샘플레이트 {sr}Hz 통일 / 버스 {len({ROLE_TO_BUS[s.role] for s in stems})}개 구성")

    # 같은 악기군 개수를 세서 팬 위치 배정
    role_counts: dict[str, int] = {}
    for s in stems:
        role_counts[s.role] = role_counts.get(s.role, 0) + 1
    role_pan_queue = {role: _assign_pans(n, PROFILES[role]) for role, n in role_counts.items()}
    for s in stems:
        s.pan = role_pan_queue[s.role].pop(0)

    has_vocal = any(s.role == "vocal" for s in stems)

    # ── 2. 버스 순서대로 처리 (리드 먼저 → 덕킹 트리거 확보) ───────────
    mix_bus = np.zeros((length, 2), dtype=np.float64)
    send_close = np.zeros((length, 2), dtype=np.float64)
    send_far = np.zeros((length, 2), dtype=np.float64)
    kick_f0: float | None = None
    kick_trigger: np.ndarray | None = None   # 모노
    lead_trigger: np.ndarray | None = None
    kick_duck = lead_duck = None
    used_buses: list[str] = []

    for bus_name, bus in BUSES.items():
        bus_stems = [s for s in stems if ROLE_TO_BUS[s.role] == bus_name]
        if not bus_stems:
            continue
        used_buses.append(bus_name)
        log(f"[{bus.label}] 트랙 {len(bus_stems)}개")
        bus_sum = np.zeros((length, 2), dtype=np.float64)

        for s in bus_stems:
            profile = PROFILES[s.role]
            target = BALANCE_REF_LUFS + profile.target_lufs_offset
            notes: list[str] = []

            audio = _load_audio(s.path, sr)
            input_lufs = _measure_lufs(audio, sr)
            if not math.isfinite(input_lufs):
                log(f"  [건너뜀] {s.path.name}: 무음이거나 너무 짧음")
                continue

            if s.role == "kick" and kick_f0 is None:
                kick_f0 = find_low_fundamental(audio, sr)
                if kick_f0:
                    notes.append(f"킥 기음 감지: {kick_f0:.0f}Hz")

            audio, _ = _gain_to_lufs(audio, sr, PRE_CHAIN_LUFS)

            if s.role in RESONANCE_ROLES:
                cuts = find_resonances(audio, sr)
                if cuts:
                    eq = Pedalboard([PeakFilter(cutoff_frequency_hz=c.freq, gain_db=c.gain_db, q=c.q) for c in cuts])
                    audio = eq(audio.T, sr).T
                    notes.append("공진 컷: " + ", ".join(c.describe() for c in cuts))

            audio = build_chain(profile)(audio.T, sr).T

            if s.role in DEESS_ROLES:
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

            audio = _apply_pan(audio, s.pan)

            # 트랙 레벨 덕킹: 킥→베이스, 리드→패드/스트링
            if s.role == "bass" and kick_duck is not None:
                audio = apply_ducking(audio, kick_duck)
                notes.append("킥이 칠 때 최대 -3dB 덕킹")
            if s.role in VOCAL_DUCK_ROLES and lead_duck is not None:
                audio = apply_ducking(audio, lead_duck)
                notes.append("리드 보컬이 나올 때 최대 -2dB 덕킹")

            n = audio.shape[0]
            bus_sum[:n] += audio
            mono = audio.mean(axis=1)
            if s.role == "kick":
                if kick_trigger is None:
                    kick_trigger = np.zeros(length)
                kick_trigger[:n] += mono
            if s.role == "vocal":
                if lead_trigger is None:
                    lead_trigger = np.zeros(length)
                lead_trigger[:n] += mono

            send = send_far if profile.space == "far" else send_close
            send[:n] += audio * profile.reverb_send

            s.result = StemResult(
                filename=s.path.name, role=s.role, role_label=profile.label,
                bus_label=bus.label, classified_by=s.classified_by,
                input_lufs=input_lufs, target_lufs=target, pan=s.pan,
                reverb_send=profile.reverb_send, space=profile.space,
                chain_description=describe_chain(profile), notes=notes,
            )
            extra = f" | {' / '.join(notes)}" if notes else ""
            log(f"  [{profile.label}] {s.path.name} → {target:.1f}LUFS, 팬 {s.pan:+.2f}, "
                f"리버브 {profile.reverb_send:.0%}({profile.space}){extra}")
            del audio

        # 버스 체인 (글루 컴프/캐릭터 EQ)
        chain = build_bus_chain(bus)
        if chain is not None and len(chain) > 0:
            bus_sum = chain(bus_sum.T.astype(np.float32), sr).T.astype(np.float64)

        # 버스 레벨 덕킹: 리드 보컬이 나올 때 백킹 버스를 눌러줌
        if bus.duck_by_lead > 0 and lead_duck is not None:
            bus_sum = apply_ducking(bus_sum, lead_duck)
            log(f"  ↳ 리드 보컬 덕킹 적용 (최대 {20 * math.log10(1 - bus.duck_by_lead):.1f}dB)")

        mix_bus += bus_sum
        del bus_sum

        # 트리거 → 덕킹 게인 (이후 버스들이 사용)
        if kick_trigger is not None and kick_duck is None:
            kick_duck = ducking_gain(kick_trigger, sr, depth=0.3)
            kick_trigger = None
        if lead_trigger is not None and lead_duck is None:
            lead_duck = ducking_gain(lead_trigger, sr, depth=0.2, attack_ms=15, release_ms=250)
            lead_trigger = None

    if not used_buses:
        raise ValueError("처리 가능한 스템이 없습니다 (전부 무음/초단편).")

    # ── 3. 리버브 2공간: 가까운 플레이트 + 먼 홀 ────────────────────
    log("리버브 버스 처리 중 (close 플레이트 / far 홀)...")
    close_rv = Pedalboard([Reverb(room_size=0.45, damping=0.55, wet_level=1.0, dry_level=0.0, width=1.0)])
    far_rv = Pedalboard([Reverb(room_size=0.85, damping=0.4, wet_level=1.0, dry_level=0.0, width=1.0)])
    mix_bus += close_rv(send_close.T.astype(np.float32), sr).T.astype(np.float64)[:length]
    mix_bus += far_rv(send_far.T.astype(np.float32), sr).T.astype(np.float64)[:length]
    del send_close, send_far

    # ── 4. 믹스 버스: 글루 컴프 → 에어 → 라우드니스 정렬 → 리미터 ───────
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
    post_lufs = _measure_lufs(mix, sr)
    if math.isfinite(post_lufs) and post_lufs > target_lufs:
        mix *= 10.0 ** ((target_lufs - post_lufs) / 20.0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_path), mix.astype(np.float32), sr, subtype="PCM_24")
    final_lufs = _measure_lufs(mix, sr)
    log(f"믹스 완료 → {output_path} ({final_lufs:.1f} LUFS, {sr}Hz/24bit)")

    # ── 5. (선택) 레퍼런스 마스터링 ──────────────────────────────
    if reference is not None:
        _master_with_reference(output_path, Path(reference), log)

    results = [s.result for s in stems if s.result is not None]
    _write_report(output_path, results, used_buses, final_lufs, target_lufs)
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


def _write_report(
    output_path: Path,
    results: list[StemResult],
    used_buses: list[str],
    final_lufs: float,
    target_lufs: float,
) -> None:
    """믹스 결정 내역을 마크다운 리포트로 남긴다."""
    report_path = output_path.with_suffix(".report.md")
    lines = [
        "# 자동 믹스 리포트",
        "",
        f"- 출력: `{output_path.name}`",
        f"- 최종 라우드니스: {final_lufs:.1f} LUFS (목표 {target_lufs:.1f})",
        f"- 스템 수: {len(results)} / 버스 수: {len(used_buses)}",
        "",
        "| 파일 | 악기 판별 | 버스 | 근거 | 입력 LUFS | 목표 LUFS | 팬 | 리버브 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        pan_str = "C" if abs(r.pan) < 0.05 else (f"L{abs(r.pan) * 100:.0f}" if r.pan < 0 else f"R{r.pan * 100:.0f}")
        lines.append(
            f"| {r.filename} | {r.role_label} | {r.bus_label} | {r.classified_by} | "
            f"{r.input_lufs:.1f} | {r.target_lufs:.1f} | {pan_str} | {r.reverb_send:.0%} ({r.space}) |"
        )
    lines += ["", "## 그룹 버스 처리", ""]
    for name in used_buses:
        lines.append(f"- **{BUSES[name].label}**: {describe_bus(BUSES[name])}")
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
        "- 리버브: 가까운 플레이트(room 0.45) + 먼 홀(room 0.85), 트랙별 센드는 위 표 참고",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
