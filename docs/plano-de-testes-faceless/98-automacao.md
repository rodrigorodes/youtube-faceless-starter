# Automação e limites da evidência

## Executores existentes — inspecionados, não executados

| Executor | O que oferece | Limites |
|---|---|---|
| `scripts/test-container.sh` | Imagem do renderer, verificação de hash/migrações, PostgreSQL efêmero com prova de descartabilidade, pytest | Não prova navegador nem YouTube real; revisar skips e dependências |
| `scripts/run-e2e-full.sh` | Stack `faceless-e2e`, porta 8100, Postgres/storage em tmpfs, jornadas Playwright | Reinicializa a stack E2E; usa texto demo, imagem placeholder, budget desabilitado e limite 60 s |
| `scripts/run-e2e-tests.sh` | Suíte de interface contra servidor existente | Padrão aponta para localhost:8000; **não usar sem conferir destino e isolamento** |
| `scripts/render_benchmark.py` | Base para medição de render | Conferir argumentos e fixtures antes da campanha; não representa capacidade de provedores externos |
| `scripts/publish_live_pilot.py` | Piloto de publicação real | Fora da campanha local; exige autorização específica e conta de teste |

Fontes: `scripts/test-container.sh:58-109`, `scripts/run-e2e-full.sh:18-35`,
`scripts/run-e2e-tests.sh:13-39`, `docker-compose.e2e.yml:25-43`.

## Ordem sugerida

1. Conferir requisitos, imagem, disponibilidade Docker e ausência de uso concorrente da stack E2E.
2. Rodar testes focados de contratos, segurança, publicação e orçamento.
3. Rodar suíte de backend no runner de contêiner.
4. Preparar dependências Playwright e navegador no ambiente isolado de testes.
5. Executar jornadas E2E locais, coletando vídeo, estado final, erros de JS e respostas 5xx.
6. Exercitar falhas/concorrência de forma controlada no mesmo isolamento.
7. Só depois planejar campanha `live`; não converter mocks em resultados live.

## Comandos candidatos da campanha futura

Executar a partir da raiz do repositório, **apenas após o preflight do piloto**:

```bash
bash scripts/test-container.sh tests/test_studio_auth.py tests/test_publication_policy.py tests/test_budget_guard.py -q -ra
bash scripts/test-container.sh tests -q -ra
bash scripts/run-e2e-full.sh
```

Não foram executados nesta entrega. Não usar `docker-compose.test.yml` isoladamente
como substituto equivalente: ele não monta a prova exigida por
`tests/conftest.py:10-46,96-105`. A fixture de banco remove o schema `studio`;
não apontar DSNs para bancos de uso. Não remover as guardas para “fazer passar”.

O runner monta o checkout **somente leitura** e remove seu contêiner ao sair
(`scripts/test-container.sh:102-109`). Portanto, não adicionar ingenuamente
`--junitxml=docs/...`: não será gravável. A exportação persistente de JUnit do runner
é uma lacuna de infraestrutura a planejar, não uma capacidade entregue aqui.
Guardar stdout/stderr sanitizados fora da montagem ou definir uma saída dedicada em
uma futura tarefa. Para pytest fora desse runner, `--junitxml=<caminho gravável>`
é suportado, mas só deve ser utilizado em ambiente cuja segurança foi conferida.

## Associação dos cenários

Cada cenário lista o teste relacionado, não uma promessa de que esse teste o cobre
inteiramente. Antes de executar, comparar fixtures/assertions com os passos e esperado;
registrar nodeid exato, parametrizações e partes não cobertas.
Não calcular cobertura por quantidade de arquivos ou nomes similares.

O conjunto `tests/` inclui testes de navegador: dependências e guardas podem fazer
coleta falhar ou testes serem pulados. Reportar separadamente coletados, passados,
falhos, erros e skips, com motivos. Exit 0 com skips não significa cobertura integral.

## Evidência por execução

Proposta de diretório: `evidencias/<RUN>/<ID>/`.

- `resultado.json`: ID, camada, versão/dirty, início/fim, veredicto, obtido e limitações.
- `envio.json` / `resposta.json`: somente dados sintéticos sanitizados.
- `estado-final.json`: estado persistido e invariantes negativas.
- `execucao.txt`: comando, exit code e resumo dos testes.
- Capturas de tela e amostra audiovisual quando o esperado depende de percepção.

Requests aceitos não provam conclusão assíncrona. Usar condição final com prazo
explícito; timeout é resultado inconclusivo/falha conforme contrato, nunca sucesso.
Falha incerta de upload exige reconciliação antes de repetição.

## Referência de ferramenta

Semântica de pytest consultada via Context7 (`/pytest-dev/pytest`, versão instalada
fixada em `requirements-dev.txt`: 8.3.5). A configuração real do repositório prevalece
para executores e isolamento; documentação de ferramenta não comprova execução local.
