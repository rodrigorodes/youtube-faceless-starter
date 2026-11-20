"""Erros compartilhados da camada de aplicação (sem dependências, para evitar importação circular)."""


class ServiceUnavailable(RuntimeError):
    """Persistência/fila indisponível (traduzida pelos adaptadores; a API responde 503)."""
