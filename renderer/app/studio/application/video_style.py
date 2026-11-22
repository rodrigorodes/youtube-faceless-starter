"""Estilo por vídeo (VS-05b) — a leitura que a tela do vídeo precisa para o override.

O canal herda o estilo da biblioteca; o vídeo pode **sobrepor** ou voltar a herdar
(`Video.style_id` nulo). Aqui vive o wiring da leitura: a tela não consulta o banco — recebe
uma projeção com **quem** o vídeo herda hoje (o estilo do canal, ou nenhum) e as opções reais
disponíveis. Nada é inventado: sem parâmetros de estilo, só a chave e o nome que a tela mostra.

`SetVideoStyle` grava (ou limpa) o override via `VideoRepository.set_video_style`, que recusa
estilo inexistente com `VisualStyleNotFound` (nunca fica um vínculo quebrado).

`SetVideoStylePatch` (F05.T02) é o override **tipado** do vídeo sobre o estilo selecionado:
precedência sobre o patch do canal, revisão própria para o controle otimista e reset que
**remove** o patch (volta a herdar), nunca um `{}` sem semântica. A resolução efetiva é
recalculada na leitura (`effective_config.resolve_effective_config`), então quando a base de
estilo muda o patch continua aplicado sobre a base nova — o resultado não é congelado aqui.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.contracts import Video
from ..domain.ids import check_id
from ..domain.visual_style import StylePatch, VisualStyle, effective_style_id
from .ports import ChannelProfileRepository, VideoRepository, VisualStyleRepository

__all__ = ["VideoStyleView", "BuildVideoStyleView", "SetVideoStyle", "VideoStylePatch",
           "SetVideoStylePatch", "VideoStylePatchConflict"]


class VideoStylePatchConflict(ValueError):
    """A revisão informada do patch do vídeo não é a atual: outra escrita venceu a corrida.

    Equivalente ao ``ChannelVersionConflict`` para o agregado vídeo (que não tem `version`): o
    repositório recusa a escrita perdedora antes de gravar qualquer coisa.
    """


def validate_style_patch_revision(value: object) -> int:
    """Revisão do patch: inteiro >= 0 (0 = nunca personalizado). Booleano não é inteiro aqui."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("style patch revision must be an integer >= 0")
    return value


@dataclass(frozen=True)
class VideoStylePatch:
    """Estado persistido do patch do vídeo: a revisão e o override tipado (``None`` = herda).

    ``patch`` ausente/vazio é ausência de override: o vídeo herda do canal. A normalização é a
    canônica de ``domain.visual_style.StylePatch`` — a allowlist vale também para quem lê o banco.
    """

    revision: int = 0
    patch: StylePatch | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "revision", validate_style_patch_revision(self.revision))
        if self.patch is not None:
            typed = (self.patch if isinstance(self.patch, StylePatch)
                     else StylePatch.from_mapping(self.patch, where="video style patch"))
            object.__setattr__(self, "patch", None if typed.is_empty else typed)

    @property
    def inherits(self) -> bool:
        return self.patch is None


@dataclass(frozen=True)
class VideoStyleView:
    """O que a tela do vídeo mostra sobre o estilo: opções reais + de quem ele herda."""

    video_id: str
    project_id: str
    # O override do vídeo (None = herda) e o estilo do canal do projeto (None = nenhum).
    override_style_id: str | None = None
    channel_style_id: str | None = None
    # Nome do estilo do canal — "de quem" o vídeo herda quando não sobrepõe (None = nenhum).
    inherited_style_name: str | None = None
    # Estilos reais disponíveis para escolher (ativos; inclui o override atual, se fora da lista).
    styles: tuple[VisualStyle, ...] = field(default_factory=tuple)

    @property
    def inherits_from_channel(self) -> bool:
        return self.override_style_id is None

    @property
    def effective_style_id(self) -> str | None:
        return effective_style_id(self.channel_style_id, self.override_style_id)


class BuildVideoStyleView:
    """Monta a projeção do override a partir do vídeo, do canal do projeto e da biblioteca."""

    def __init__(self, videos: VideoRepository, channels: ChannelProfileRepository,
                 styles: VisualStyleRepository):
        self.videos = videos
        self.channels = channels
        self.styles = styles

    def execute(self, video_id: str) -> VideoStyleView | None:
        video = self.videos.get_video(check_id(video_id))
        if video is None:
            return None
        profile = self.channels.get_by_project(video.project_id)
        channel_style_id = profile.style_id if profile is not None else None
        inherited_name = None
        if channel_style_id is not None:
            style = self.styles.get(channel_style_id)
            inherited_name = style.name if style is not None else None
        styles = list(self.styles.list())
        # Um canal/vídeo pode apontar para um estilo fora da lista ativa (ex.: arquivado depois):
        # a opção atual continua representável com o nome real, nunca some para virar "nenhum".
        for current in (channel_style_id, video.style_id):
            if current is not None and all(s.id != current for s in styles):
                extra = self.styles.get(current)
                if extra is not None:
                    styles.append(extra)
        return VideoStyleView(
            video_id=video.id,
            project_id=video.project_id,
            override_style_id=video.style_id,
            channel_style_id=channel_style_id,
            inherited_style_name=inherited_name,
            styles=tuple(styles),
        )


class SetVideoStyle:
    """Fixa (ou limpa, com None) o estilo que sobrepõe o do canal neste vídeo.

    Devolve ``None`` se o vídeo não existe; propaga ``VisualStyleNotFound`` se o estilo não
    existe — a API traduz para 404/422 sem stack trace.
    """

    def __init__(self, videos: VideoRepository):
        self.videos = videos

    def execute(self, video_id: str, style_id: str | None) -> Video | None:
        v_id = check_id(video_id)
        sid = check_id(style_id) if style_id is not None else None
        return self.videos.set_video_style(v_id, sid)


class SetVideoStylePatch:
    """Grava (ou remove, com None) o override tipado de estilo deste vídeo (F05.T02).

    Devolve o estado persistido (revisão + patch) ou ``None`` se o vídeo não existe. Um patch
    inválido sobe como ``StylePatchInvalid`` (antes de qualquer escrita) e uma revisão velha como
    ``VideoStylePatchConflict`` — nada é gravado pela escrita perdedora.
    """

    def __init__(self, videos: VideoRepository):
        self.videos = videos

    def execute(self, video_id: str, expected_revision: int,
                patch: StylePatch | dict | None) -> VideoStylePatch | None:
        v_id = check_id(video_id)
        revision = validate_style_patch_revision(expected_revision)
        return self.videos.set_video_style_patch(v_id, revision, patch)
