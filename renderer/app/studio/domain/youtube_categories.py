"""Heurística: de um pilar/nicho (texto livre) para a categoria do YouTube (`videoCategoryId`).

O Em Alta (`chart=mostPopular`) sem categoria é a plataforma inteira, não o nicho do canal. Com
`videoCategoryId` ele passa a ser o Em Alta da categoria do pilar, e custa o mesmo (1 unidade).
É uma heurística por palavra-chave: sem casamento devolve `None` e quem chama NÃO coleta Em Alta
(melhor sem ideia do que com ideia fora do nicho). Os ids são os da lista pública do YouTube.
"""
from __future__ import annotations

import re
import unicodedata

# Ordem importa: o primeiro grupo que casar vence. Palavras já sem acento e em minúsculas.
_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("20", ("game", "games", "gamer", "gameplay", "jogo", "jogos", "gta", "minecraft", "fortnite", "esports", "speedrun")),
    ("10", ("musica", "music", "dj", "djs", "edm", "rap", "funk", "sertanejo", "rock", "pop", "trap", "festival", "festivais",
            "show", "shows", "lineup", "clipe", "album", "cantor", "banda", "eletronica", "house", "techno", "trance")),
    ("17", ("esporte", "esportes", "futebol", "basquete", "nba", "volei", "tenis", "mma", "ufc", "corrida", "sports")),
    ("15", ("pet", "pets", "cachorro", "cachorros", "cao", "caes", "gato", "gatos", "canil", "kennel", "animal", "animais")),
    ("2", ("carro", "carros", "moto", "motos", "automovel", "automoveis", "autos", "veiculo", "veiculos")),
    ("19", ("viagem", "viagens", "turismo", "travel", "destino", "destinos")),
    ("25", ("noticia", "noticias", "politica", "news", "eleicao", "eleicoes", "governo")),
    ("28", ("ciencia", "tecnologia", "tech", "ia", "inteligencia", "artificial", "gadget", "gadgets", "espaco", "astronomia", "software")),
    ("27", ("educacao", "historia", "aprender", "aula", "aulas", "curso", "cursos", "estudo", "estudos", "geografia", "filosofia",
            "biologia", "fisica", "quimica", "matematica", "documentario")),
    ("26", ("receita", "receitas", "culinaria", "cozinha", "moda", "beleza", "maquiagem", "diy", "tutorial", "decoracao",
            "jardinagem", "churrasco", "carne", "carnes", "corte", "cortes")),
    ("23", ("comedia", "humor", "piada", "piadas", "stand", "meme", "memes")),
    ("1", ("filme", "filmes", "cinema", "trailer", "serie", "series", "anime", "animacao")),
    ("22", ("vlog", "vlogs", "rotina", "lifestyle")),
)

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return set(_WORD.findall(folded))


def youtube_category_for(*texts: str) -> str | None:
    """`videoCategoryId` do primeiro grupo cujas palavras aparecem nos textos (nome do pilar, termos, nicho)."""
    tokens: set[str] = set()
    for text in texts:
        tokens |= _tokens(text)
    if not tokens:
        return None
    for category_id, words in _GROUPS:
        if tokens.intersection(words):
            return category_id
    return None
