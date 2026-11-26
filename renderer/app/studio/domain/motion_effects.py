"""Efeitos visuais, motion graphics e presets cinematográficos (V4-05).

Fornece:
1. Parâmetros e keyframes para movimento de câmera Ken Burns e Zoom/Pan suave.
2. Camadas gráficas e lower thirds declarativos para legendagem contextual.
3. Tratamento de cor (color grading / LUT), vinheta, granulação (grain) e desfoque (blur).
4. Presets consolidados para Whiteboard, Documentary, Cinematic e Tech Explainer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from .render_plan import Motion


class ColorGrading(str, Enum):
    """Estilos tonais de color grading para pós-processamento."""

    NONE = "none"
    DOCUMENTARY = "documentary"      # Contraste factual e tons de pele naturais
    WARM = "warm"                    # Tons âmbar/dourados e atmosfera acolhedora
    COOL = "cool"                    # Tons azulados e atmosfera técnica/analítica
    NOIR = "noir"                    # Monocromático de alto contraste e sombras profundas
    VIBRANT = "vibrant"              # Saturação viva para vídeos de curiosidades


@dataclass(frozen=True)
class MotionKeyframe:
    """Keyframe de transformação geométrica para animações de câmera."""

    time_progress: float            # 0.0 (início) a 1.0 (fim do shot)
    scale: float = 1.0              # Fator de escala/zoom
    center_x: float = 0.5           # Ponto focal horizontal (0.0 a 1.0)
    center_y: float = 0.5           # Ponto focal vertical (0.0 a 1.0)


@dataclass(frozen=True)
class MotionCurve:
    """Curva calculada de movimento de câmera Ken Burns."""

    motion: Motion
    start: MotionKeyframe
    end: MotionKeyframe
    easing: Literal["linear", "ease_in_out", "smooth"] = "smooth"


def calculate_motion_curve(motion: Motion, zoom_factor: float = 1.15) -> MotionCurve:
    """Calcula os keyframes inicial e final para o movimento de câmera solicitado."""
    z = max(1.0, zoom_factor)
    if motion == "zoom_in":
        start = MotionKeyframe(0.0, scale=1.0, center_x=0.5, center_y=0.5)
        end = MotionKeyframe(1.0, scale=z, center_x=0.5, center_y=0.5)
    elif motion == "zoom_out":
        start = MotionKeyframe(0.0, scale=z, center_x=0.5, center_y=0.5)
        end = MotionKeyframe(1.0, scale=1.0, center_x=0.5, center_y=0.5)
    elif motion == "pan_left":
        start = MotionKeyframe(0.0, scale=z, center_x=0.6, center_y=0.5)
        end = MotionKeyframe(1.0, scale=z, center_x=0.4, center_y=0.5)
    elif motion == "pan_right":
        start = MotionKeyframe(0.0, scale=z, center_x=0.4, center_y=0.5)
        end = MotionKeyframe(1.0, scale=z, center_x=0.6, center_y=0.5)
    else:  # "none"
        start = MotionKeyframe(0.0, scale=1.0, center_x=0.5, center_y=0.5)
        end = MotionKeyframe(1.0, scale=1.0, center_x=0.5, center_y=0.5)

    return MotionCurve(motion=motion, start=start, end=end)


@dataclass(frozen=True)
class PostProcessingEffects:
    """Efeitos óticos e texturas aplicados sobre o plano visual."""

    color_grading: ColorGrading = ColorGrading.NONE
    vignette_strength: float = 0.0     # 0.0 a 1.0 (escurecimento suave das bordas)
    grain_strength: float = 0.0        # 0.0 a 1.0 (granulação de película analógica)
    blur_background: bool = False      # Se True, desfoca fundo em caso de letterbox

    def __post_init__(self) -> None:
        if not (0.0 <= self.vignette_strength <= 1.0):
            raise ValueError("vignette_strength must be between 0.0 and 1.0")
        if not (0.0 <= self.grain_strength <= 1.0):
            raise ValueError("grain_strength must be between 0.0 and 1.0")


@dataclass(frozen=True)
class LowerThirdGraphic:
    """Elemento visual de identificação (lower third) para locutores ou tópicos."""

    title: str
    subtitle: str = ""
    start_s: float = 0.0
    duration_s: float = 3.5
    position: Literal["bottom_left", "bottom_center", "bottom_right"] = "bottom_left"
    accent_color: str = "#D4AF37"      # Dourado padrão documental

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("lower third title cannot be empty")
        if self.duration_s <= 0:
            raise ValueError("duration_s must be positive")


@dataclass(frozen=True)
class InfographicOverlay:
    """Gráfico ou infográfico animado sobreposto ao vídeo."""

    graphic_type: Literal["bar_chart", "timeline", "stat_card", "map"]
    title: str
    data_points: tuple[tuple[str, float], ...] = ()
    start_s: float = 0.0
    duration_s: float = 4.0
    position_x: float = 0.5
    position_y: float = 0.5
    scale: float = 0.8
