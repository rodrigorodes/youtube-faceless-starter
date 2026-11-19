"""Regras de mídia (domínio puro): estilo do prompt de imagem, aspecto por formato e tamanhos finais."""
from .contracts import VideoFormat

_COMMON = ", cinematic photography, {orientation} {aspect} composition, rich colors, no text, no logos, no recognizable real people"
IMAGE_STYLE = {
    "9:16": _COMMON.format(orientation="vertical", aspect="9:16"),
    "16:9": _COMMON.format(orientation="horizontal", aspect="16:9"),
}
ASPECT_FOR = {VideoFormat.short: "9:16", VideoFormat.long: "16:9"}
SIZE_FOR = {"9:16": (1080, 1920), "16:9": (1920, 1080)}


def build_image_prompt(prompt: str, aspect: str) -> str:
    return prompt.strip() + IMAGE_STYLE[aspect]


def strip_style(prompt: str) -> str:
    """Prompt original, sem o sufixo de estilo (provedores de busca, como o stock, usam só o tema)."""
    for suffix in IMAGE_STYLE.values():
        if prompt.endswith(suffix):
            return prompt[: -len(suffix)]
    return prompt
