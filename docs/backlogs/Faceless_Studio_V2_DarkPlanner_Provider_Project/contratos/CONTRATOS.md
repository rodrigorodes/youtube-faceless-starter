# Contratos internos propostos (não são endpoints DarkPlanner)

## Contrato existente, que deve permanecer compatível
```python
class Voice(Protocol):
    name: str
    def speak(self, text: str, out_path: Path) -> float: ...
```

## DTOs de aplicação opcionais (sem nome de fornecedor)
```python
from dataclasses import dataclass
from enum import Enum

class AudioErrorCode(str, Enum):
    UNAVAILABLE = 'unavailable'
    RATE_LIMITED = 'rate_limited'
    INVALID_INPUT = 'invalid_input'
    AUTH_REQUIRED = 'auth_required'
    BUDGET_EXCEEDED = 'budget_exceeded'
    TEMPORARY_FAILURE = 'temporary_failure'
    UNSUPPORTED = 'unsupported'
    NEEDS_RECONCILIATION = 'needs_reconciliation'

@dataclass(frozen=True)
class AudioCapabilities:
    supports_srt: bool
    supports_multivoice: bool
    supports_async_jobs: bool
    supports_idempotency_key: bool
    accepted_languages: tuple[str, ...] = ()

@dataclass(frozen=True)
class AudioGenerationRequest:
    scene_id: str
    text: str
    voice_id: str
    language: str
    speed: float
    content_hash: str

@dataclass(frozen=True)
class AudioArtifact:
    scene_id: str
    wav_uri: str
    duration_seconds: float
    audio_sha256: str
    provider_name: str
    external_reference: str | None = None
    subtitles_uri: str | None = None
```

**Observação:** `wav_uri` e `external_reference` não incluem credenciais nem URL assinada exposta em APIs públicas. Para o MVP `AudioArtifact` pode permanecer interno ao adapter e retornar apenas duração conforme a porta existente.

## Máquina de estados opcional para provider assíncrono
`CREATED → SUBMITTING → SUBMITTED → PROCESSING → DOWNLOADING → READY` / `FAILED` / `NEEDS_RECONCILIATION`. `READY` só depois de validar WAV local. Regras: `retry` pode retornar ao ponto seguro; `SUBMITTING` com crash sem idempotência do provedor não reenvia automaticamente.

## Configuração
```yaml
# PÚBLICO — nunca guardar segredo aqui
voice: darkplanner:pt-br-voice-id # exemplo de spec interna; ID real a confirmar
voice_policy:
  fallback: disabled
  cost_limit_usd_per_video: 0.50
```

**Secret resolver (fora do domínio):** `secret_ref` ligado ao escopo organization/channel; o adapter recebe credenciais em runtime via factory. Jamais armazenar tokens em `ProjectConfig` ou `AudioArtifact`.

## Contrato HTTP para a UI (proposta, não existente)
- `GET /studio/providers/voice` → providers habilitados, status, capabilities.
- `GET /studio/providers/voice/{name}/voices` → vozes, se suportado/documentado.
- `POST /studio/channels/{id}/voice/test` → job para prévia curta com budget e rate limit.
- `PATCH /studio/channels/{id}/audio-settings` → voice spec e preferências; somente perfil autorizado.

## Testes de substituição
- `PiperVoice` e `DarkPlannerVoiceAdapter` passam pelo mesmo harness: valid text → WAV reproduzível + duração positiva; texto vazio → erro normalizado; falha externa → erro categorizado; sem vazamento de secrets.
- Trocar `voice` via config não altera `domain/`, `application/render.py` nem as transições de produção.
