"""악기별 정석 믹싱 체인 프로파일.

인터넷/교과서의 표준 믹싱 가이드를 규칙으로 옮긴 것:
  - HPF로 불필요한 저역 정리 (low-end cleanup)
  - 머드 존(200~400Hz) 정리, 악기별 캐릭터 대역 부스트
  - 악기 특성에 맞는 컴프레서 비율/어택/릴리즈
  - 악기별 목표 라우드니스(밸런스), 팬 위치, 리버브 센드 양
"""

from __future__ import annotations

import math

from dataclasses import dataclass, field

from pedalboard import (
    Compressor,
    HighpassFilter,
    HighShelfFilter,
    LowShelfFilter,
    NoiseGate,
    PeakFilter,
    Pedalboard,
)


@dataclass
class EQMove:
    freq: float
    gain_db: float
    q: float = 0.9

    def describe(self) -> str:
        sign = "+" if self.gain_db >= 0 else ""
        return f"{self.freq:.0f}Hz {sign}{self.gain_db:.1f}dB"


@dataclass
class RoleProfile:
    """한 악기군의 믹싱 레시피."""

    label: str                      # 리포트용 한국어 이름
    highpass_hz: float
    eq_moves: list[EQMove] = field(default_factory=list)
    low_shelf: EQMove | None = None
    high_shelf: EQMove | None = None
    comp_threshold_db: float = -18.0
    comp_ratio: float = 3.0
    comp_attack_ms: float = 10.0
    comp_release_ms: float = 120.0
    gate_threshold_db: float | None = None  # 드럼 등 새는 소리 정리용
    target_lufs_offset: float = -6.0        # 보컬(0.0) 기준 상대 라우드니스
    pan: float = 0.0                        # -1(L) ~ +1(R), 같은 군이 여러 개면 좌우로 벌림
    pan_spread: float = 0.0                 # 같은 군 2개 이상일 때 벌리는 폭
    reverb_send: float = 0.0                # 0~1, 리버브 버스로 보내는 양
    space: str = "close"                    # 리버브 공간: close(가까운 플레이트) / far(먼 홀)


# 악기별 표준 레시피. 수치는 일반적인 믹싱 가이드 기준의 보수적인 출발점.
PROFILES: dict[str, RoleProfile] = {
    "kick": RoleProfile(
        label="킥",
        highpass_hz=30,
        eq_moves=[EQMove(65, 2.0, 1.0), EQMove(350, -3.0, 1.2), EQMove(3500, 2.0, 1.0)],
        comp_threshold_db=-14, comp_ratio=4.0, comp_attack_ms=15, comp_release_ms=80,
        target_lufs_offset=-1.0, pan=0.0, reverb_send=0.0,
    ),
    "snare": RoleProfile(
        label="스네어",
        highpass_hz=80,
        eq_moves=[EQMove(200, 1.5, 1.2), EQMove(450, -2.0, 1.2), EQMove(5000, 2.0, 0.9)],
        comp_threshold_db=-15, comp_ratio=4.0, comp_attack_ms=8, comp_release_ms=100,
        target_lufs_offset=-3.0, pan=0.0, reverb_send=0.18,
    ),
    "hihat": RoleProfile(
        label="하이햇",
        highpass_hz=300,
        eq_moves=[EQMove(7000, 1.0, 0.8)],
        comp_threshold_db=-20, comp_ratio=2.0, comp_attack_ms=5, comp_release_ms=80,
        target_lufs_offset=-10.0, pan=0.25, reverb_send=0.05,
    ),
    "drums": RoleProfile(
        label="드럼(버스/오버헤드)",
        highpass_hz=40,
        eq_moves=[EQMove(400, -1.5, 1.0)],
        high_shelf=EQMove(9000, 1.5),
        comp_threshold_db=-16, comp_ratio=3.0, comp_attack_ms=12, comp_release_ms=120,
        target_lufs_offset=-2.5, pan=0.0, pan_spread=0.5, reverb_send=0.10,
    ),
    "percussion": RoleProfile(
        label="퍼커션",
        highpass_hz=120,
        eq_moves=[EQMove(350, -1.5, 1.1)],
        comp_threshold_db=-18, comp_ratio=2.5, comp_attack_ms=8, comp_release_ms=100,
        target_lufs_offset=-9.0, pan=0.4, pan_spread=0.6, reverb_send=0.12,
    ),
    "bass": RoleProfile(
        label="베이스",
        highpass_hz=35,
        eq_moves=[EQMove(80, 1.5, 0.9), EQMove(250, -2.0, 1.1), EQMove(800, 1.0, 1.0)],
        comp_threshold_db=-16, comp_ratio=4.0, comp_attack_ms=20, comp_release_ms=150,
        target_lufs_offset=-2.0, pan=0.0, reverb_send=0.0,
    ),
    "guitar": RoleProfile(
        label="기타",
        highpass_hz=90,
        eq_moves=[EQMove(300, -2.0, 1.1), EQMove(2500, 1.5, 0.9)],
        comp_threshold_db=-18, comp_ratio=2.5, comp_attack_ms=12, comp_release_ms=120,
        target_lufs_offset=-6.0, pan=0.5, pan_spread=1.0, reverb_send=0.15,
    ),
    "piano": RoleProfile(
        label="피아노",
        highpass_hz=70,
        eq_moves=[EQMove(280, -1.5, 1.0)],
        high_shelf=EQMove(8000, 1.0),
        comp_threshold_db=-19, comp_ratio=2.0, comp_attack_ms=20, comp_release_ms=150,
        target_lufs_offset=-6.0, pan=-0.2, pan_spread=0.4, reverb_send=0.18,
    ),
    "keys": RoleProfile(
        label="건반",
        highpass_hz=90,
        eq_moves=[EQMove(300, -1.5, 1.0)],
        comp_threshold_db=-19, comp_ratio=2.0, comp_attack_ms=15, comp_release_ms=140,
        target_lufs_offset=-7.0, pan=0.3, pan_spread=0.6, reverb_send=0.15,
    ),
    "synth": RoleProfile(
        label="신스",
        highpass_hz=100,
        eq_moves=[EQMove(350, -1.5, 1.0)],
        comp_threshold_db=-18, comp_ratio=2.0, comp_attack_ms=10, comp_release_ms=120,
        target_lufs_offset=-7.0, pan=0.35, pan_spread=0.7, reverb_send=0.12,
    ),
    "pad": RoleProfile(
        label="패드",
        highpass_hz=150,
        eq_moves=[EQMove(400, -2.0, 0.9)],
        high_shelf=EQMove(8000, 1.0),
        comp_threshold_db=-20, comp_ratio=1.8, comp_attack_ms=30, comp_release_ms=250,
        target_lufs_offset=-11.0, pan=0.0, pan_spread=0.8, reverb_send=0.30, space="far",
    ),
    "strings": RoleProfile(
        label="스트링",
        highpass_hz=120,
        eq_moves=[EQMove(350, -1.5, 1.0)],
        high_shelf=EQMove(9000, 1.0),
        comp_threshold_db=-20, comp_ratio=2.0, comp_attack_ms=25, comp_release_ms=200,
        target_lufs_offset=-8.0, pan=0.0, pan_spread=0.7, reverb_send=0.25, space="far",
    ),
    "brass": RoleProfile(
        label="브라스",
        highpass_hz=100,
        eq_moves=[EQMove(300, -1.5, 1.0), EQMove(2000, 1.0, 0.9)],
        comp_threshold_db=-17, comp_ratio=3.0, comp_attack_ms=15, comp_release_ms=130,
        target_lufs_offset=-7.0, pan=0.3, pan_spread=0.6, reverb_send=0.15,
    ),
    "vocal": RoleProfile(
        label="보컬",
        highpass_hz=90,
        eq_moves=[EQMove(250, -2.0, 1.1), EQMove(3000, 2.0, 0.9)],
        high_shelf=EQMove(10000, 1.5),
        comp_threshold_db=-16, comp_ratio=3.0, comp_attack_ms=8, comp_release_ms=120,
        target_lufs_offset=0.0, pan=0.0, reverb_send=0.20,
    ),
    "backing_vocal": RoleProfile(
        label="백보컬",
        highpass_hz=120,
        eq_moves=[EQMove(250, -2.5, 1.1), EQMove(3000, 1.0, 0.9)],
        comp_threshold_db=-18, comp_ratio=3.5, comp_attack_ms=8, comp_release_ms=120,
        target_lufs_offset=-7.0, pan=0.45, pan_spread=0.9, reverb_send=0.28, space="far",
    ),
    "vocal_double": RoleProfile(
        label="보컬 더블",
        highpass_hz=120,
        eq_moves=[EQMove(250, -2.5, 1.1)],
        high_shelf=EQMove(8000, -1.5),  # 리드보다 어둡게 → 리드 뒤에 붙음
        comp_threshold_db=-17, comp_ratio=4.0, comp_attack_ms=5, comp_release_ms=100,
        target_lufs_offset=-8.0, pan=0.0, pan_spread=1.2, reverb_send=0.15,
    ),
    "vocal_harmony": RoleProfile(
        label="하모니/스택",
        highpass_hz=150,
        eq_moves=[EQMove(250, -3.0, 1.1), EQMove(3000, -1.0, 0.9)],  # 리드 자리 비움
        comp_threshold_db=-17, comp_ratio=4.0, comp_attack_ms=8, comp_release_ms=130,
        target_lufs_offset=-9.0, pan=0.0, pan_spread=1.4, reverb_send=0.30, space="far",
    ),
    "vocal_adlib": RoleProfile(
        label="애드립",
        highpass_hz=130,
        eq_moves=[EQMove(250, -2.0, 1.1), EQMove(3000, 1.5, 0.9)],
        high_shelf=EQMove(10000, 1.0),
        comp_threshold_db=-17, comp_ratio=3.0, comp_attack_ms=8, comp_release_ms=120,
        target_lufs_offset=-6.0, pan=0.35, pan_spread=1.0, reverb_send=0.35,
    ),
    "vocal_chant": RoleProfile(
        label="코러스(떼창)",
        highpass_hz=180,
        eq_moves=[EQMove(300, -2.0, 1.0)],
        comp_threshold_db=-18, comp_ratio=5.0, comp_attack_ms=10, comp_release_ms=150,
        target_lufs_offset=-10.0, pan=0.0, pan_spread=1.6, reverb_send=0.35, space="far",
    ),
    "fx": RoleProfile(
        label="이펙트",
        highpass_hz=150,
        comp_threshold_db=-20, comp_ratio=2.0, comp_attack_ms=10, comp_release_ms=150,
        target_lufs_offset=-12.0, pan=0.0, pan_spread=1.0, reverb_send=0.25, space="far",
    ),
    "other": RoleProfile(
        label="기타악기(미분류)",
        highpass_hz=80,
        eq_moves=[EQMove(300, -1.5, 1.0)],
        comp_threshold_db=-18, comp_ratio=2.5, comp_attack_ms=12, comp_release_ms=130,
        target_lufs_offset=-7.0, pan=0.2, pan_spread=0.6, reverb_send=0.12,
    ),
}


def build_chain(profile: RoleProfile) -> Pedalboard:
    """프로파일을 pedalboard 이펙트 체인으로 변환한다."""
    plugins = []
    if profile.gate_threshold_db is not None:
        plugins.append(NoiseGate(threshold_db=profile.gate_threshold_db, ratio=4, release_ms=150))
    plugins.append(HighpassFilter(cutoff_frequency_hz=profile.highpass_hz))
    if profile.low_shelf:
        plugins.append(
            LowShelfFilter(cutoff_frequency_hz=profile.low_shelf.freq, gain_db=profile.low_shelf.gain_db)
        )
    for move in profile.eq_moves:
        plugins.append(PeakFilter(cutoff_frequency_hz=move.freq, gain_db=move.gain_db, q=move.q))
    if profile.high_shelf:
        plugins.append(
            HighShelfFilter(cutoff_frequency_hz=profile.high_shelf.freq, gain_db=profile.high_shelf.gain_db)
        )
    plugins.append(
        Compressor(
            threshold_db=profile.comp_threshold_db,
            ratio=profile.comp_ratio,
            attack_ms=profile.comp_attack_ms,
            release_ms=profile.comp_release_ms,
        )
    )
    return Pedalboard(plugins)


def describe_chain(profile: RoleProfile) -> str:
    """리포트용 체인 설명 문자열."""
    parts = [f"HPF {profile.highpass_hz:.0f}Hz"]
    if profile.low_shelf:
        parts.append(f"LowShelf {profile.low_shelf.describe()}")
    parts.extend(f"EQ {m.describe()}" for m in profile.eq_moves)
    if profile.high_shelf:
        parts.append(f"HighShelf {profile.high_shelf.describe()}")
    parts.append(
        f"Comp {profile.comp_ratio:.1f}:1 "
        f"(thr {profile.comp_threshold_db:.0f}dB, atk {profile.comp_attack_ms:.0f}ms, rel {profile.comp_release_ms:.0f}ms)"
    )
    return " → ".join(parts)


# ──────────────────────── 그룹 버스 ────────────────────────
# 실제 세션 워크플로우: 트랙 → 그룹 버스(글루/캐릭터) → 믹스 버스.
# duck_by_lead: 리드 보컬이 나올 때 이 버스를 눌러주는 깊이 (0이면 안 누름)


@dataclass
class BusProfile:
    label: str
    roles: tuple[str, ...]
    comp: tuple[float, float, float, float] | None = None  # (thr_db, ratio, atk_ms, rel_ms)
    eq_moves: list[EQMove] = field(default_factory=list)
    high_shelf: EQMove | None = None
    duck_by_lead: float = 0.0


# 처리 순서 중요: vocal_lead가 가장 먼저(덕킹 트리거), drums가 bass보다 먼저(킥 트리거)
BUSES: dict[str, BusProfile] = {
    "vocal_lead": BusProfile(
        label="리드 보컬 버스", roles=("vocal",),
        comp=(-16, 2.0, 15, 150), high_shelf=EQMove(12000, 1.0),
    ),
    "drums": BusProfile(
        label="드럼 버스", roles=("kick", "snare", "hihat", "drums", "percussion"),
        comp=(-12, 2.0, 30, 180),
    ),
    "bass_bus": BusProfile(
        label="베이스 버스", roles=("bass",),
    ),
    "vocal_double": BusProfile(
        label="더블 버스", roles=("vocal_double",),
        comp=(-17, 3.0, 10, 120), high_shelf=EQMove(8000, -1.0), duck_by_lead=0.15,
    ),
    "vocal_harmony": BusProfile(
        label="하모니 버스", roles=("vocal_harmony", "backing_vocal"),
        comp=(-17, 3.0, 10, 150), eq_moves=[EQMove(3000, -1.0, 0.9)], duck_by_lead=0.20,
    ),
    "vocal_adlib": BusProfile(
        label="애드립 버스", roles=("vocal_adlib",),
        comp=(-18, 2.5, 10, 140), duck_by_lead=0.25,
    ),
    "vocal_chant": BusProfile(
        label="떼창 버스", roles=("vocal_chant",),
        comp=(-18, 4.0, 15, 180), eq_moves=[EQMove(300, -1.5, 1.0)], duck_by_lead=0.20,
    ),
    "music": BusProfile(
        label="뮤직 버스", roles=("guitar", "piano", "keys", "synth", "pad", "strings", "brass", "fx", "other"),
        comp=(-15, 1.5, 30, 250),
    ),
}

ROLE_TO_BUS: dict[str, str] = {
    role: name for name, bus in BUSES.items() for role in bus.roles
}


def build_bus_chain(bus: BusProfile) -> Pedalboard | None:
    plugins = []
    for move in bus.eq_moves:
        plugins.append(PeakFilter(cutoff_frequency_hz=move.freq, gain_db=move.gain_db, q=move.q))
    if bus.high_shelf:
        plugins.append(
            HighShelfFilter(cutoff_frequency_hz=bus.high_shelf.freq, gain_db=bus.high_shelf.gain_db)
        )
    if bus.comp:
        thr, ratio, atk, rel = bus.comp
        plugins.append(Compressor(threshold_db=thr, ratio=ratio, attack_ms=atk, release_ms=rel))
    return Pedalboard(plugins) if plugins else None


def describe_bus(bus: BusProfile) -> str:
    parts = [f"EQ {m.describe()}" for m in bus.eq_moves]
    if bus.high_shelf:
        parts.append(f"HighShelf {bus.high_shelf.describe()}")
    if bus.comp:
        thr, ratio, atk, rel = bus.comp
        parts.append(f"글루 컴프 {ratio:.1f}:1 (thr {thr:.0f}dB, atk {atk:.0f}ms, rel {rel:.0f}ms)")
    if bus.duck_by_lead > 0:
        duck_db = 20 * math.log10(1 - bus.duck_by_lead)
        parts.append(f"리드 보컬 덕킹 최대 {duck_db:.1f}dB")
    return " → ".join(parts) if parts else "(패스스루)"
