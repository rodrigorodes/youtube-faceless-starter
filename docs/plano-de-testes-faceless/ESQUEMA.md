# Esquema do plano de testes Faceless

Modelo: `.ai-analysis/GC_MVP/stg-teste/plano-de-testes-gc` do workspace CERC.
A estrutura foi adaptada ao domínio Faceless: não há HUs/cards Jira inventados, nem
pressuposto de ambiente STG. As regras derivam do código, dos contratos e da documentação.

## Fonte e organização

`dados/NN-*.yaml` contém os dados de cada capítulo. JSON formatado é aceito, por ser
subconjunto de YAML. Os capítulos Markdown são gerados por `gerar.py` a partir de `dados/`
(não editar à mão). `validar.py` confere que o `.md` é exatamente a saída do gerador e que
regras, cenários e contagens estão coerentes. Para mudar o plano, altere `dados/` e rode
`python3 gerar.py`.
`dados/funcionalidades.yaml` cataloga capítulos e `dados/regras.yaml` registra rastreabilidade.

| Campo | Contrato |
|---|---|
| id | Único no plano; `PREFIXO-nn` |
| titulo | O comportamento exercitado |
| tipo | feliz, borda, erro, concorrencia, volume, regressao |
| regras | Lista de IDs definidos no catálogo de regras |
| status | A_PROJETAR nesta elaboração; nunca PASS por inspeção |
| prioridade | alta, media, baixa |
| objetivo | O que o cenário prova |
| pre_condicoes | Estado, ambiente, fixtures e dependências |
| exemplo | Dados concretos e passos reproduzíveis |
| esperado | Resultado observável e efeitos que não devem ocorrer |
| limitacoes | O que a execução nessa camada não comprova |
| automacao | camada e referência de teste existente ou proposta |

## Camadas

- `unit`: regras puras; sem provar integração.
- `mock`: API/aplicação com substitutos; sem provar fornecedor.
- `local-integrado`: Postgres descartável, arquivos temporários e/ou FFmpeg/Piper reais.
- `browser`: comportamento no navegador; declarar backend real ou substituído.
- `live`: integração externa real, somente em campanha específica autorizada.
- `manual`: avaliação humana, como inteligibilidade e qualidade editorial.

## Evolução dos resultados

`A_PROJETAR` significa que o cenário está descrito, mas sua associação com um executor
completo ainda precisa ser confirmada. Um teste similar existente não justifica promoção.
Use `A_EXECUTAR` quando fixtures e executor estiverem prontos; `BLOQUEADO` com motivo
concreto; `PASS`, `FALHA`, `PARCIAL` ou `RETESTAR` apenas com histórico de execução.

Depois de executar, acrescentar `obtido`, `modo`, `data` e `evidencia` com caminhos
relativos a esta pasta. Resultado parcial ou skip não é aprovação. Evidências devem
identificar versão, alterações locais, camada, ambiente e IDs dos objetos sintéticos.
Não gravar tokens, cabeçalhos Authorization, cookies ou conteúdo de cofres.

Garantias desejadas não existentes devem estar identificadas como lacuna/expectativa
proposta; não são contratos implementados. Limites de desempenho propostos não são SLAs.
