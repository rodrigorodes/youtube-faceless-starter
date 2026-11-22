"""Helpers para validação de DOM vivo, acessibilidade e responsividade."""
from __future__ import annotations

from playwright.sync_api import Page


def assert_no_duplicate_ids(page: Page, *, context_desc: str = "") -> None:
    """Verifica se há IDs duplicados no DOM ativo (inclusive dentro de diálogos/modais abertos).

    Essa verificação previne bugs como B2 (onde getElementById retornava o primeiro
    elemento duplicado em vez do campo do formulário de modal).
    """
    duplicates = page.evaluate("""
        () => {
            const elements = document.querySelectorAll('[id]');
            const counts = {};
            for (const el of elements) {
                const id = (el.id || '').trim();
                if (!id) continue;
                counts[id] = (counts[id] || 0) + 1;
            }
            return Object.entries(counts)
                .filter(([id, count]) => count > 1)
                .map(([id, count]) => ({ id, count }));
        }
    """)
    if duplicates:
        details = ", ".join(f"#{item['id']} ({item['count']}x)" for item in duplicates)
        prefix = f"[{context_desc}] " if context_desc else ""
        raise AssertionError(f"{prefix}IDs duplicados detectados no DOM de {page.url}: {details}")


def assert_no_horizontal_overflow(page: Page, *, context_desc: str = "") -> None:
    """Verifica se a página ou seus containers geraram scroll horizontal indesejado no viewport."""
    res = page.evaluate("""
        () => {
            const doc = document.documentElement;
            const scrollW = doc.scrollWidth;
            const innerW = window.innerWidth;
            return {
                scrollWidth: scrollW,
                innerWidth: innerW,
                overflows: scrollW > innerW
            };
        }
    """)
    if res["overflows"]:
        prefix = f"[{context_desc}] " if context_desc else ""
        raise AssertionError(
            f"{prefix}Overflow horizontal detectado: scrollWidth ({res['scrollWidth']}px) > innerWidth ({res['innerWidth']}px) em {page.url}"
        )
