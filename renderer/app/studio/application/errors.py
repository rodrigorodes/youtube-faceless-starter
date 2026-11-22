"""Erros compartilhados da camada de aplicação (sem dependências, para evitar importação circular)."""


class ServiceUnavailable(RuntimeError):
    """Persistência/fila indisponível (traduzida pelos adaptadores; a API responde 503)."""


class InvalidInput(ValueError):
    """Dado recusado pela persistência (ex.: byte NUL em texto)."""


class ScriptEditIdempotencyConflict(ValueError):
    """A chave de idempotência já foi usada com outro payload (replay inseguro é recusado)."""


class ScriptRevisionUnavailable(ValueError):
    """A revisão pedida não existe ou não tem snapshot recuperável (versão legada)."""


class ProjectNotFound(LookupError):
    pass


class VisualStyleNotFound(LookupError):
    """O estilo visual referenciado não existe (VS-02b: override de vídeo, VS-02: canal)."""


