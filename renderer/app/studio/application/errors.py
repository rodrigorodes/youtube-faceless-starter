"""Erros compartilhados da camada de aplicação (sem dependências, para evitar importação circular)."""


class ServiceUnavailable(RuntimeError):
    """Persistência/fila indisponível (traduzida pelos adaptadores; a API responde 503)."""


class InvalidInput(ValueError):
    """Dado recusado pela persistência (ex.: byte NUL em texto)."""


class ProjectNotFound(LookupError):
    pass


