"""Domínio de categorias (pilares de conteúdo)."""
from dataclasses import dataclass, field
from datetime import datetime

from .ids import check_id


class CategoryError(Exception):
    """Erro base para categorias."""


class CategoryNameInvalid(CategoryError, ValueError):
    """Nome da categoria vazio, muito longo ou inválido."""


class DuplicateCategoryName(CategoryError, ValueError):
    """Nome de categoria duplicado dentro do mesmo projeto."""


def validate_category_name(name: str) -> str:
    if not isinstance(name, str):
        raise CategoryNameInvalid("Category name must be a string")
    cleaned = name.strip()
    if not (1 <= len(cleaned) <= 100):
        raise CategoryNameInvalid("Category name must be between 1 and 100 characters")
    return cleaned


MAX_QUERIES_PER_CATEGORY = 10


def clean_queries(queries: list[str] | None) -> list[str]:
    if not queries:
        return []
    cleaned: list[str] = []
    for q in queries:
        if isinstance(q, str):
            s = q.strip()
            if s and s not in cleaned:
                cleaned.append(s)
    return cleaned[:MAX_QUERIES_PER_CATEGORY]


@dataclass(frozen=True)
class ProjectCategory:
    id: str
    project_id: str
    name: str
    queries: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        check_id(self.id)
        check_id(self.project_id)
        validate_category_name(self.name)
        object.__setattr__(self, "queries", clean_queries(self.queries))
