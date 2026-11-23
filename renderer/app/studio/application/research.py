"""Pesquisa automática (F3 mínimo): do tema do vídeo a fontes registradas com proveniência.

Só texto realmente lido de uma fonte de referência vira `SourceSnapshot`; nada é inventado nem resumido por
modelo. Sem fonte aproveitável a etapa falha com um motivo claro, e o humano adiciona a fonte manualmente.
Fontes já registradas (coladas ou buscadas) são respeitadas: a pesquisa não roda por cima delas.
"""
from dataclasses import dataclass

from ..domain.claims import extract_claims
from ..domain.contracts import SourceSnapshot
from .editorial import MAX_SOURCE_CHARS, SourceRefused, _require_video
from .ports import ResearchProvider, SnapshotRepository, VideoRepository

DEFAULT_LANGUAGE = "pt-BR"


@dataclass(frozen=True)
class ResearchResult:
    snapshots: tuple[SourceSnapshot, ...]
    reused: bool  # True: o vídeo já tinha fontes; nenhuma busca externa aconteceu


class AutoResearch:
    # Só o artigo mais relevante: os seguintes da busca costumam ser tangenciais (ex.: biografias que citam o tema).
    def __init__(self, provider: ResearchProvider, snaps: SnapshotRepository, videos: VideoRepository,
                 max_documents: int = 1):
        self.provider, self.snaps, self.videos, self.max_documents = provider, snaps, videos, max_documents

    def execute(self, video_id: str) -> ResearchResult:
        video = _require_video(self.videos, video_id)
        existing = self.snaps.list(video_id)
        if existing:
            return ResearchResult(tuple(existing), reused=True)
        project = self.videos.get_project(video.project_id)
        language = (getattr(project, "language", None) or DEFAULT_LANGUAGE)
        stored: list[SourceSnapshot] = []
        for doc in self.provider.search(video.topic, language):
            text = doc.text.strip()[:MAX_SOURCE_CHARS]
            if not extract_claims("probe", text):
                continue  # sem afirmações verificáveis (rascunho, lista, desambiguação): não vira fonte
            stored.append(self.snaps.add(video_id, doc.url, text))
            if len(stored) >= self.max_documents:
                break
        if not stored:
            raise SourceRefused(
                f"automatic research ({self.provider.name}) found no source with checkable claims "
                "for this topic: add a source manually")
        return ResearchResult(tuple(stored), reused=False)
