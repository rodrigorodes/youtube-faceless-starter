# F5 — fatia de contrato VisualBeat

## Escopo

- `renderer/app/studio/domain/visual_beat.py` define contrato versionado,
  imutável e sem I/O para intervalo em segundos relativos à cena. Os tipos
  seguem F5-02: `stock`, `ai_image`, `ai_clip`, `diagram`, `screen_capture`
  e `text_animation`. Referência, cena e textos opcionais fornecidos devem
  ser não vazios; transição é opcional e não identifica efeitos suportados.
- Tempos são numéricos, finitos e não negativos, com início estritamente
  anterior ao fim. Beats de mídia exigem proveniência e licença não vazias;
  animação de texto local pode omiti-las. A presença desses metadados não
  constitui verificação jurídica nem auditoria dos direitos.
- Nenhuma integração com renderer, alteração de `Scene`, persistência,
  storyboard ou múltiplos beats por cena foi feita. Esta fatia não conclui F5.

## Evidências

- TDD: teste novo executado antes da implementação falhou na coleta por
  `ModuleNotFoundError: app.studio.domain.visual_beat`; após implementação,
  testes de fronteiras, contrato, arquitetura e domínio render passaram.
- Python 3.12.16, imagem local `faceless-v2-hygiene-test-local:latest`,
  execução sem rede e workspace somente leitura:
  `docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider tests/test_visual_beat.py tests/test_architecture.py tests/test_contracts.py tests/test_render_domain.py`
  — 102 passaram. O teste de arquitetura verifica imports de toda a camada
  de domínio, inclusive o novo módulo.
- Suíte completa com montagem adicional somente leitura do Git externo do
  worktree, necessária para os testes de empacotamento:
  `docker run --rm --network none -v "$PWD:/workspace:ro" -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git:ro -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider`
  — 733 passaram, 310 ignorados, um aviso de depreciação Starlette/AnyIO.
  Banco e serviços externos não foram configurados; testes ignorados não
  foram validados. A suíte também incluiu arquivos não rastreados preexistentes.
