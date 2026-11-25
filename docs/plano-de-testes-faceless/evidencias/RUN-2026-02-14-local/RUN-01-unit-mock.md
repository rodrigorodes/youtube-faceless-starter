# RUN-01 — camada unit/mock (sem E2E)

- Data: 2026-11-24 (o nome do diretório preserva o rótulo original)

Comando:
```
python3 -m pytest tests -q --ignore=tests/e2e_full --ignore=tests/e2e_ux -p no:cacheprovider
```

Resultado real (exit code 1):
- 21 failed
- 3129 passed
- 945 skipped
- 82.56 s

Nenhum cenário do plano foi promovido a PASS por este resultado: a suíte existente
não é o plano. Este registro é evidência de execução real da camada unit/mock.
