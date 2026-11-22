# Suíte completa após F02 — comparação com o baseline

Mesmo comando, mesmo PostgreSQL descartável e mesmas variáveis do baseline da F00.

| Rodada | Resultado | Observação |
|---|---|---|
| Baseline (F00, HEAD `e254b61`) | **2625 passed, 63 failed, 58 skipped** (400 s) | falhas pré-existentes classificadas em [pre-existing-failures](pre-existing-failures.md) |
| Após F02, 1ª rodada | 2675 passed, **67 failed** | 63 pré-existentes + **4 regressões próprias** do canal ativo |
| Após F02, 2ª rodada (final) | **2679 passed, 63 failed, 58 skipped** (380 s) | `diff` dos nomes contra o baseline: **idêntico** |

## Regressões próprias (corrigidas)

1. `tests/test_panel.py` (3): asserção exata `href="/studio/panel"` não previa `?project_id=`
   que a F02.T01 passou a propagar. A expectativa foi atualizada para aceitar o parâmetro —
   o comportamento novo é o que o contrato pede ("canal B permanece em todas as áreas").
2. `tests/test_channels_page.py::test_channel_appearance_selects_the_current_style`: o link
   para a biblioteca de estilos passou a levar o canal; a asserção foi atualizada na mesma linha.

Nenhuma correção de produção foi necessária; nenhum teste pré-existente foi enfraquecido — as
asserções continuam verificando rota, item ativo e alvo existente.

## falhas remanescentes

As mesmas 63 do baseline (42 telas desatualizadas após o port V3, 17 por FFmpeg ausente no host,
2 por contrato gerado com pydantic divergente, 2 sensíveis à ordem). Ver
[pre-existing-failures](pre-existing-failures.md).

## Testes acrescentados pela F02 (todos verdes)

| Arquivo | Testes | Cobre |
|---|---|---|
| `tests/test_active_channel.py` (novo) | 25 | regra do canal ativo, redirects, vídeo intacto, documento renderizado |
| `tests/test_advanced_page.py` (novo) | 5 | tela Avançado: saúde, providers reais, config efetiva, sem segredo, sem controle |
| `tests/test_new_video_v3.py` | 13 (6 novos) | estilos reais, herança com nome, sem opções fictícias, payload, predefinição real |
| `tests/test_video_style_api.py` | 24 (5 novos) | criação com estilo (persistência, arquivado, desconhecido), canal ativo validado, tela Avançado |
| `tests/test_ports.py` | 7 (2 novos) | caso de uso `CreateVideo` com estilo (puro, sem banco) |
| `tests/test_settings_area.py` | 10 (4 novos) | sete grupos de Configurações |

## Comando

```sh
T=/private/var/folders/3c/qgm1b33j2vq0yb_2pp_9zz7r0000gn/T/f00-disposable
PYTHONPATH=renderer PYTHONDONTWRITEBYTECODE=1 \
  STUDIO_TEST_DSN="postgresql://postgres:test@127.0.0.1:55433/postgres" \
  STUDIO_BUDGET_DISPOSABLE_DSN="postgresql://postgres:test@127.0.0.1:55433/postgres" \
  STUDIO_BUDGET_TEST_PROOF_FILE="$T/proof/proof" \
  python3 -m pytest -p no:cacheprovider tests -q
```