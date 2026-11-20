# F7 — Thumbnails, títulos, SEO e experimentos (P1)

**Prioridade:** P1  
**Dependências:** F4: roteiros; F6: preview/artefatos; pode começar em paralelo com F5.  
**Estado inicial:** A fazer (proposta, não implementação verificada)

**Objetivo:** melhorar apresentação e descoberta do vídeo sem alegar CTR garantido.

## Entregáveis e cards

| Card | Trabalho | Evidência de entrega |
|---|---|---|
| `F7-01` | Criar `PackagingAgent` (contrato com título, descrição, tags, capítulos, fontes e CTA). | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F7-02` | Gerar 3 conceitos de thumbnail e títulos correspondentes com justificativa editorial; sem clickbait enganoso. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F7-03` | Templates gráficos por canal; text overlays, safe areas, legibilidade mobile e exportação. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F7-04` | Review UI para comparar variantes, escolher e editar metadados. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F7-05` | Persistir versão escolhida junto a `publication_intent`. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F7-06` | Validar dimensões/formato/peso e regras vigentes da API do YouTube por integração. | PR com implementação, testes e documentação; demonstração do cenário descrito |
| `F7-07` | Testes de conteúdo enganoso, imagem sem licença e edição de metadados pós-aprovação. | PR com implementação, testes e documentação; demonstração do cenário descrito |

## Critérios de aceite

operador escolhe thumbnail/título antes de publicar; pacote completo é versionado e anexado à publicação.

## Provas de qualidade e cenários negativos

- Testes de contrato e casos felizes dos endpoints e handlers afetados.
- Simulação de falha parcial, retry, timeout e payload inválido quando aplicável.
- Garantia de permissões/autorização e ausência de credenciais em logs, respostas e artefatos.
- Observabilidade com `run_id`, `video_id`, `stage_id` e evidência reprodutível de diagnóstico.
- Sem regressão nos comportamentos existentes; compatibilidade documentada ou migração prevista.

## Métrica de saída / gate

Título, descrição, capítulos e thumbnail selecionados e versionados em publicação.

## Definition of Done

- [ ] Contratos públicos e eventos versionados.
- [ ] Migrations reversíveis ou rollout seguro.
- [ ] Testes unitários, integrados e falhas relevantes.
- [ ] UI com loading, vazio, sucesso, bloqueio e erro (quando houver UI).
- [ ] Custo e fallback registrados onde há consumo de API.
- [ ] Segurança e auditoria validadas.
- [ ] Docs, diagramas e runbook atualizados.
- [ ] Review técnica e demonstração do gate de aceite.
