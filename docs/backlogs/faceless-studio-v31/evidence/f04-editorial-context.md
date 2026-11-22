# F04 — contexto editorial governa os geradores (stream L, sem commit)

Worktree `f04-editorial` (`/Users/rodrigomendes/youtube-faceless-starter.worktrees/f04-editorial 55443`),
baseline com F02, F01, F03.T01 e F06.T01 aplicados **sem commit**. Nenhum commit, push, deploy,
provider real ou chamada paga nesta fatia.

## F04.T01 — contexto tipado a partir da configuração efetiva

`EditorialContext` (`application/editorial.py`, dataclass imutável) é o **único** caminho de
derivação: `EditorialContext.from_effective_config(config)` lê `EffectiveConfig.editorial` e
preserva a proveniência por campo (`editorial.<campo>` → `channel` | `engine_default`). Não relê
`ChannelProfile`, não grava nada e não cria segunda persistência.

- `legacy` = todos os seis campos com proveniência `engine_default` (sem perfil). Só nesse caso
  idioma, duração de prompt e alvo longo continuam exatamente os de hoje.
- `declared_duration_s` = `None` no retrato legado; caso contrário a duração do perfil.
- `coerce()` aceita `EffectiveConfig` já resolvido ou `EditorialContext`; `None` = sem perfil.
- Defaults: `EDITORIAL_DEFAULTS` de `domain/effective_config` (pt-BR, "", (), "", 60, "") e
  `test_channel_domain.py` trava a igualdade entre o default do perfil e o do motor.

## F04.T02 — idioma e duração no curto e no longo

- `build_prompt`, `build_long_outline_prompt`, `build_long_scenes_prompt` e
  `build_prompt_for_format` recebem `context=` (keyword-only). Sem contexto o texto do prompt é
  **idêntico** ao anterior (`português do Brasil`, sem linha de duração) — teste de igualdade.
- `language_label`: `pt-BR` → "português do Brasil" (legado); outros códigos entram como o próprio
  código (`en-US`), então canal A e canal B produzem prompts diferentes (asserção do idioma).
- Público, narrativa, pilares e CTA entram como linhas de orientação **apenas** quando declarados,
  com corte explícito (300/600/300 caracteres) para o limite de 3900 do prompt sobrar para os fatos.
  A instrução "Use SOMENTE os fatos" e a exigência de `claim_ids` não mudaram; fonte insuficiente
  continua bloqueando (`SourceRefused` antes da chamada) e cena sem citação continua `ScriptRejected`.
- Duração curta: linha `Duração alvo ~Ns.` quando o perfil declara a duração.
- Duração longa: precedência chamada > construtor > duração declarada **acima do default curto
  (60 s)** > 480 s. O perfil grava 60 s por default, valor indistinguível de "não configurado para
  longo"; ele não pode encolher o formato. `words_per_minute` continua o medido (172), nunca campo
  do canal.
- `GenerateScript` e `GenerateLongScript` recebem `editorial_for(video)` opcional; sem ele o
  comportamento é o legado (teste explícito).

## F04.T03 — matriz campo → consumidor (o que existe de fato)

| Campo de `ChannelProfile` | Entra em `EffectiveConfig.editorial` | Consumidor **antes** desta fatia | Consumidor **depois** | Contrato/teste |
|---|---|---|---|---|
| `language` | sim | tela/JSON do canal, página Novo vídeo (exibição), `effective_config` | prompts curto e longo | `test_editorial.py`, `test_longform_editorial.py` |
| `audience` | sim | tela/JSON, `effective_config` | prompts curto e longo | idem |
| `narrative` | sim | tela/JSON, `effective_config` | prompts curto e longo | idem |
| `pillars` | sim | tela/JSON, `effective_config` | prompts curto e longo | idem |
| `cta` | sim | tela/JSON, `effective_config` | prompts curto e longo | idem |
| `target_duration_s` | sim | tela/JSON, `effective_config` | prompt curto; alvo do longo (> 60 s) | idem |
| `strategy` | **não** (schema 1 não tem o campo) | tela/JSON apenas | — | sem contrato: não suportado |
| `visual_identity` | **não** | tela/JSON apenas | — | sem contrato: não suportado |
| `voice` | **não** (voz do render vem do estilo/projeto) | tela/JSON e rótulo "voz" na página Novo vídeo | — | sem contrato: não suportado |
| `audio` | **não** | tela/JSON apenas | — | sem contrato: não suportado |
| `thumbnail` | **não** | tela/JSON apenas | — | **thumbnail avançada não suportada** |
| `style_id` / `youtube_channel_id` | referências fora do `editorial` | render (F03/VS) e gate de publicação (F01) | inalterado | — |

Consumidores verificados que **não** foram alterados, por falta de contrato:

- **Metadados** (`domain/metadata.build_metadata`): título/descrição/tags vêm do tema, narrações e
  fontes; não recebe canal. Sem contrato para idioma/CTA do perfil.
- **Thumbnail** (`adapters/thumbnail.PillowThumbnail`, `publishing.GetThumbnail`): JPEG 1280x720 da
  imagem da primeira cena. `channel.thumbnail` é texto livre **sem consumidor**; não há thumbnail
  avançada (texto sobreposto, variações A/B) e esta fatia não a promete.
- **Ideias** (`application/ideas.ScoreIdeas`): rubrica fixa em português, sem entrada de canal.
- **Categorias** (`application/categories.py`, `domain/categories`): são **queries de coleta** de
  tendências (`ProjectCategory.queries`), não pilares editoriais. `channel.pillars` não é lido ali;
  a distinção permanece e nada foi acoplado.

## Fiação que falta (fora do escopo desta fatia)

`composition.py` é de outra onda. O bloco abaixo é o que falta para ligar o contexto ao fluxo real;
até lá, API/UI continuam no caminho legado (pt-BR) porque `editorial_for` fica `None`:

```python
from .domain.effective_config import resolve_effective_config

def editorial_for(video):
    try:
        channel = channel_repo.get_by_project(video.project_id)
    except InvalidId:
        return None
    if channel is None:
        return None  # sem perfil: defaults legados
    # F03.T02 deve congelar este documento antes do primeiro efeito; aqui ele é só derivado.
    return resolve_effective_config(video=video, channel=channel, lookup_style=style_repo.get)

GenerateScript(..., editorial_for=editorial_for)
GenerateLongScript(..., editorial_for=editorial_for)
```

Risco a decidir antes de fiar: um perfil existente hoje carrega `target_duration_s=60` (default do
formulário). Com a fiação, `GenerateScript` passa a receber "Duração alvo ~60s"; o formato longo
continua em 480 s por causa da guarda `> 60`. Um canal de vídeos longos precisa declarar a duração
real; não há hoje marca de "campo editado pelo humano" no perfil.

## Testes (PostgreSQL descartável 55443)

Comando (arquivos tocados, nunca a suíte inteira):

```
PYTHONPATH=renderer PYTHONDONTWRITEBYTECODE=1 \
STUDIO_TEST_DSN=postgresql://postgres:test@127.0.0.1:55443/postgres \
STUDIO_BUDGET_DISPOSABLE_DSN=postgresql://postgres:test@127.0.0.1:55443/postgres \
STUDIO_BUDGET_TEST_PROOF_FILE=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/fs31-f04-editorial/proof/proof \
python -m pytest -q tests/test_channel_domain.py tests/test_editorial.py \
  tests/test_longform_editorial.py tests/test_longform_480s.py tests/test_editorial_api.py \
  tests/test_claims_metadata.py tests/test_ideas.py
```

- Antes: **160 passed**, 0 failed, 0 skipped.
- Depois: **175 passed**, 0 failed, 0 skipped (15 testes novos: 9 em `test_editorial.py`, 5 em
  `test_longform_editorial.py`, 1 em `test_channel_domain.py`). Nenhum teste existente foi afrouxado.

## Limites e achados

- `strategy`, `visual_identity`, `voice`, `audio` e `thumbnail` não entram na configuração efetiva
  (schema 1): governá-los exigiria ampliar o contrato da F03, o que esta fatia não faz.
- `EffectiveConfig` não tem marca de campo "explícito": a duração do perfil é sempre `channel`.
- Metadados, thumbnail, ideias e categorias seguem sem contrato de consumo; nada foi prometido.
- `editorial_for` recebe o `Video` porque `resolve_effective_config` congela `video_id` e estilo do
  vídeo; a composição já tem `channel_repo` e `style_repo` para montar isso sem I/O extra.