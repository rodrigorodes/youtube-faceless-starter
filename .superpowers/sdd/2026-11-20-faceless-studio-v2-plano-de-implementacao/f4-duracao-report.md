# F4 — base de estimativa de duração

## Escopo e contrato

- Regra pura em `renderer/app/studio/domain/narration_duration.py`, usando
  `Scene.narration` do contrato existente. Não altera `Scene.duration_s` nem
  conecta a estimativa ao fluxo short ou a um fluxo long-form.
- A taxa de palavras por minuto é obrigatória, numérica, positiva e finita;
  valores booleanos e resultados não finitos são recusados. Retorna segundos
  por cena, na ordem de entrada, e a soma, sem arredondamento explícito.
- Contagem por sequências Unicode de letras e números; hífens e apóstrofos
  internos unem palavras. Pontuação isolada não conta. É uma convenção de
  estimativa, não tokenização linguística nem expansão de números.
- F4-03 também pede validação contra velocidade real do TTS: **não realizada**.
  Não há evidência de precisão, pausas, prosódia ou integração long-form.

## Evidências

- Python 3.12.16, imagem local `faceless-v2-hygiene-test-local:latest`,
  rede desabilitada e workspace montado somente para leitura.
- TDD: execução inicial de
  `docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider tests/test_narration_duration.py`
  falhou na coleta com `ModuleNotFoundError` para o módulo novo; após a
  implementação, a execução com `tests/test_narration_duration.py tests/test_architecture.py`
  passou: 17 testes.
- Domínio, contrato e arquitetura:
  `docker run --rm --network none -v "$PWD:/workspace:ro" -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider tests/test_narration_duration.py tests/test_contracts.py tests/test_render_domain.py tests/test_architecture.py`
  — 54 passaram.
- Suíte completa:
  `docker run --rm --network none -v "$PWD:/workspace:ro" -v /Users/rodrigomendes/youtube-faceless-starter/.git:/Users/rodrigomendes/youtube-faceless-starter/.git:ro -w /workspace -e PYTHONPATH=/workspace/renderer --entrypoint python faceless-v2-hygiene-test-local:latest -m pytest -q -p no:cacheprovider`
  — 668 passaram, 310 ignorados, um aviso de depreciação Starlette/AnyIO.
  Sem o segundo volume, a suíte teve 2 falhas nos testes de empacotamento
  `test_real_starter_archive_is_safe_and_keeps_scripts_executable` e
  `test_extracted_starter_runs_contract_snapshot_and_backup_import`, pois o
  caminho Git externo do worktree não estava acessível no contêiner.
  A execução não configurou banco descartável; testes dependentes de serviços
  foram ignorados, não validados.
- A imagem `faceless-v2-local-test:latest` não tinha `pytest`; foi usada a
  imagem de testes citada acima, sem instalar dependências ou acessar rede.
