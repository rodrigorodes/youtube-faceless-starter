"""Timeline e plano multitrack de áudio audiovisual (V4-03 / Professional Audio).

Orquestra a montagem de 4 camadas sonoras simultâneas:
1. Voz (diálogo / narração do locutor)
2. Música de fundo (com suporte a crossfade entre múltiplas faixas)
3. Ambiência contínua (textura de sala / atmosfera)
4. Efeitos sonoros pontuais (SFX de transição, destaques, impactos)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .audio_catalog import AudioCatalog, AudioCategory, AudioTrack


@dataclass(frozen=True)
class AudioEvent:
    """Instância de áudio posicionada na timeline do vídeo."""

    id: str
    track_id: str
    category: AudioCategory
    start_s: float
    duration_s: float
    gain_db: float = 0.0
    fade_in_s: float = 0.0
    fade_out_s: float = 0.0
    ducked: bool = False             # Se True, sofre atenuação dinâmica sob a presença da voz

    def __post_init__(self) -> None:
        if self.start_s < 0.0:
            raise ValueError(f"start_s must be non-negative: {self.start_s}")
        if self.duration_s <= 0.0:
            raise ValueError(f"duration_s must be positive: {self.duration_s}")
        if self.fade_in_s < 0.0 or self.fade_out_s < 0.0:
            raise ValueError("fades must be non-negative")
        if (self.fade_in_s + self.fade_out_s) > self.duration_s:
            raise ValueError("sum of fades cannot exceed event duration")

    @property
    def end_s(self) -> float:
        return self.start_s + self.duration_s


@dataclass(frozen=True)
class MultitrackAudioPlan:
    """Especificação completa da mixagem multitrack para o renderizador."""

    total_duration_s: float
    voice_events: tuple[AudioEvent, ...] = ()
    music_events: tuple[AudioEvent, ...] = ()
    ambience_events: tuple[AudioEvent, ...] = ()
    sfx_events: tuple[AudioEvent, ...] = ()
    ducking_attenuation_db: float = -14.0   # Nível de atenuação da música durante fala (-12dB a -18dB)
    target_lufs: float = -14.0              # Padrão YouTube (-14.0 LUFS integrado)
    target_true_peak_dbtp: float = -1.0     # Padrão de segurança contra distorção em AAC (-1.0 dBTP)
    highpass_voice_hz: float = 80.0         # Filtro rumble anti-pop na voz

    def __post_init__(self) -> None:
        if self.total_duration_s <= 0.0:
            raise ValueError("total_duration_s must be positive")

    @property
    def all_events(self) -> tuple[AudioEvent, ...]:
        return (
            *self.voice_events,
            *self.music_events,
            *self.ambience_events,
            *self.sfx_events,
        )

    def is_voice_active_at(self, time_s: float) -> bool:
        """Determina se a faixa de locução/voz está ativa no instante time_s."""
        for ev in self.voice_events:
            if ev.start_s <= time_s < ev.end_s:
                return True
        return False


def verify_audio_licenses(plan: MultitrackAudioPlan, catalog: AudioCatalog) -> list[str]:
    """Verifica se todas as faixas utilizadas no plano multitrack possuem licença comprovada.

    Retorna lista de erros de violação de licença encontrados.
    """
    violations: list[str] = []
    checked_tracks: set[str] = set()

    for event in plan.all_events:
        if event.track_id in checked_tracks:
            continue
        checked_tracks.add(event.track_id)

        # Voz gerada internamente não precisa de catalog id se for synthesized
        if event.category == AudioCategory.VOICE or event.track_id == "voice":
            continue

        if event.category in (AudioCategory.MUSIC, AudioCategory.SFX, AudioCategory.AMBIENCE):
            track = catalog.get_track(event.track_id)
            if track is None:
                violations.append(f"track '{event.track_id}' not found in registered audio catalog")
            elif not track.license or track.license.strip().lower() in ("unlicensed", "unknown", "proprietary"):
                violations.append(f"track '{event.track_id}' lacks a compliant open license: '{track.license}'")

    return violations


def build_multitrack_plan(
    total_duration_s: float,
    voice_events: Sequence[AudioEvent] = (),
    music_tracks: Sequence[tuple[str, float, float]] = (),  # (track_id, start_s, duration_s)
    ambience_track_id: str | None = None,
    sfx_cues: Sequence[tuple[str, float]] = (),             # (track_id, timestamp_s)
    catalog: AudioCatalog | None = None,
) -> MultitrackAudioPlan:
    """Gera um plano multitrack estruturado e coerente com tempos e transições suaves."""
    music_events: list[AudioEvent] = []
    for i, (m_id, m_start, m_dur) in enumerate(music_tracks):
        # Crossfade de 1.0s entre faixas consecutivas
        fade_in = 1.0 if i > 0 else 0.5
        fade_out = 1.0 if i < (len(music_tracks) - 1) else 1.5
        music_events.append(
            AudioEvent(
                id=f"music_{i+1}",
                track_id=m_id,
                category=AudioCategory.MUSIC,
                start_s=m_start,
                duration_s=m_dur,
                gain_db=-6.0,
                fade_in_s=min(fade_in, m_dur / 2.0),
                fade_out_s=min(fade_out, m_dur / 2.0),
                ducked=True,
            )
        )

    ambience_events: list[AudioEvent] = []
    if ambience_track_id:
        ambience_events.append(
            AudioEvent(
                id="ambience_bed",
                track_id=ambience_track_id,
                category=AudioCategory.AMBIENCE,
                start_s=0.0,
                duration_s=total_duration_s,
                gain_db=-18.0,
                fade_in_s=0.5,
                fade_out_s=1.0,
                ducked=True,
            )
        )

    sfx_events: list[AudioEvent] = []
    for j, (sfx_id, cue_s) in enumerate(sfx_cues):
        sfx_dur = 0.8  # duração estimada do efeito se não houver catálogo
        if catalog:
            t = catalog.get_track(sfx_id)
            if t and t.duration_s > 0:
                sfx_dur = t.duration_s

        sfx_events.append(
            AudioEvent(
                id=f"sfx_{j+1}",
                track_id=sfx_id,
                category=AudioCategory.SFX,
                start_s=cue_s,
                duration_s=sfx_dur,
                gain_db=-3.0,
                fade_in_s=0.02,
                fade_out_s=0.05,
                ducked=False,  # SFX não sofrem ducking da voz
            )
        )

    return MultitrackAudioPlan(
        total_duration_s=total_duration_s,
        voice_events=tuple(voice_events),
        music_events=tuple(music_events),
        ambience_events=tuple(ambience_events),
        sfx_events=tuple(sfx_events),
        ducking_attenuation_db=-14.0,
        target_lufs=-14.0,
        target_true_peak_dbtp=-1.0,
    )
