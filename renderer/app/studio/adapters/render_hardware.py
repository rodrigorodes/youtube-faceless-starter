"""Adaptadores de infraestrutura e hardware para Render Engine (V4-08).

Contém:
- Detecção de aceleração de hardware (Apple VideoToolbox, NVENC, VAAPI ou CPU puro).
- Consulta de espaço real em disco (check_disk_space_mb).
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

from ..domain.render_engine import RendererCapabilities

__all__ = [
    "detect_system_hardware",
    "check_disk_space_mb",
]


def detect_system_hardware(ffmpeg_binary: str = "ffmpeg") -> RendererCapabilities:
    """Detecta capacidades de hardware da máquina hospedeira de forma segura e resiliente."""
    system_name = platform.system().lower()
    machine = platform.machine().lower()

    # Verifica se ffmpeg está acessível
    ffmpeg_available = shutil.which(ffmpeg_binary) is not None
    if not ffmpeg_available:
        return RendererCapabilities(
            name="ffmpeg-not-found",
            supported_codecs=("h264", "aac"),
            hardware_acceleration=None,
            max_resolution=(1920, 1080),
        )

    # Detecção baseada na plataforma
    hw_accel: str | None = None
    if system_name == "darwin":
        # macOS / Apple Silicon
        hw_accel = "videotoolbox"
    elif system_name == "linux":
        # Verifica se há suporte a nvenc ou vaapi
        try:
            res = subprocess.run(
                [ffmpeg_binary, "-encoders"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
            )
            out = res.stdout.lower()
            if "h264_nvenc" in out:
                hw_accel = "nvenc"
            elif "h264_vaapi" in out:
                hw_accel = "vaapi"
        except Exception:
            hw_accel = None

    return RendererCapabilities(
        name="ffmpeg",
        supported_codecs=("h264", "hevc", "aac", "pcm_s16le"),
        hardware_acceleration=hw_accel,
        max_resolution=(3840, 2160) if hw_accel else (1920, 1080),
        supports_segmented_render=True,
        supports_cancellation=True,
        supports_lossless_concat=True,
    )


def check_disk_space_mb(path: str | Path) -> float:
    """Retorna o espaço livre em Megabytes para o diretório alvo."""
    try:
        target = Path(path).resolve()
        if not target.exists():
            target = target.parent
        usage = shutil.disk_usage(target)
        return usage.free / (1024 * 1024)
    except Exception:
        return 1024.0  # Fallback seguro de 1GB se não conseguir inspecionar
