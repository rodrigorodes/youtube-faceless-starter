# Backlog incremental — Google AI Pro / External Media
Status PENDING, nenhuma execução autorizada por este documento. Integração com V4.1: IDs auxiliares GAI, não renumerar 14 fases/227 tarefas declaradas. Reconciliar com contratos existentes e evidências da Foundation. Implementação estimada sequencial 7–14 dias assistidos por IA para escopo completo candidato, sem homologação medida; primeiros dois itens 1,5–3 dias estimados para imagem e vídeo mínimos, áudio/import editorial ampliados em fases próprias; APIs e Drive opcionais, estimativas sobrepostas à V4 e não somar duas vezes.

| ID | Fase consumidora | Prioridade | Entrega | Estimativa |
|---|---|---|---|---|
| GAI-01 | V4-04/11 | P0 complemento | External Asset Import | 1–2d |
| GAI-02 | V4-10 (UX incremental) | P0 complemento | Assisted Generation | 0,5–1d |
| GAI-03 | V4-01/06 | P1 | Gemini Text nativo | 0,5–1d |
| GAI-04 | V4-01/05 | P1 | Image/Nano Banana | 0,5–1d |
| GAI-05 | V4-02/07 | P1 | Gemini TTS | 1–2d |
| GAI-06 | V4-05/08/12 | P1 | Veo Video | 1–2d |
| GAI-07 | V4-11 | P2 | Drive Storage | 1–2d |
| GAI-08 | V4-09 | P1 | Gemini Quality Evaluator | 1–2d |
| GAI-09 | V4-01/12 | P1 transversal | Cost Accounting | 0,5–1d |

Total aritmético dos intervalos 7–14 dias. Candidatos P1/P2 não bloqueiam o MVP assistido; autorização e guard obrigatório antes de qualquer API paga, portanto parte mínima GAI-09 precede GAI-03–06/08. Não aguardar conclusão de V4-10/11 para vertical slice: fundações e UX mínimo incremental. FS-08 extrações apenas quando necessárias, não novo refactor.

## GAI-01 — importação
- 01a: inventariar schema Asset/AssetKind, storage, MediaFetcher, materialização, preview, resolver, RenderPlan/FFmpeg e testes. Registrar gaps e contratos, especialmente vídeo MIME/kind atual.
- 01b: ingestão imagem/vídeo tipada, limites e probing, hash/escopo/licença e atomicidade. Preservar storage atual; áudio em track própria quando disponível.
- 01c: vincular asset via comando existente com CAS/revisão e invalidação; preview correto, guardar anterior em falha; não regenerar áudio.
- Gate: fixture PNG e MP4 originais offline importadas e renderizadas; arquivo corrupto, MIME falso, excesso, traversal, licença desconhecida, stale/concurrency e retry recusados ou tratados conforme política, sem dano a cena/arquivo existente. Provar MP4 de ponta a ponta (não basta busca de vídeo).

## GAI-02 — modo assistido
- 02a: painel por cena com origem externa genérica, prompt editável/copiável, duração/aspecto/identidade, link oficial opcional. Fluxo sem login no app de assinatura e sem automação da interface.
- 02b: importar/preview/aplicar e voltar ao storyboard, persistência e undo/redo conforme contrato; estado aguardando humano não ocupa worker.
- 02c: import editorial via revisão existente; voz e música pela track adequada em fase consumidora, sem declarar suporte antes de validar.
- Gate: browser em ambiente isolado, gerar prompt -> importar fixture -> trocar mídia -> reabrir -> render; nenhuma chamada externa paga/LLM em importação/edição determinística, sem alteração de cenas não relacionadas. UX não exibe saldo não verificado.

## GAI-03 — texto Gemini
Validar modelos disponíveis e termos atuais; cliente oficial, JSON schema, erros 429/503, retries limitados e fallback autorizado, usage/tokens/cache, BYOK e gate editorial. Gate: mocks de sucesso, schema inválido, timeout, quota, budget insuficiente e fallback; integração live só com teto/consentimento. Bridge permanece disponível.

## GAI-04 — imagem
Capacidade image.generate, modelo configurável, tamanho/aspecto, validação e licença/proveniência. Gate: fixture/double, recusa arquivo inválido, custo e cache medidos; não usar assinatura como credencial API.

## GAI-05 — voz
Contrato Voice existente, formato WAV normalizado, idioma/voz, duração medida, sincronização, cancel e fallback Piper explícito. Gate: narração PT-BR, fixture de áudio, transcrição/sync e falha, sem voz clonada sem autorização; autorização de custo.

## GAI-06 — vídeo Veo
Separar video.generate de image.generate; desabilitado até homologação. Submit/poll/reconcile por operation id, retry limitado, reserva e custo por segundo/modelo; trim/crop e áudio original controlados; usar pipeline GAI-01. Gate: mock async, restart, timeout ambíguo sem segundo submit, cancel quando suportado, output inválido e orçamento; piloto live opcional e autorizado, nunca required para render assistido.

## GAI-07 — Drive
OAuth separado/escopo mínimo, upload/download/referências/hash, sync opt-in, staging e restauração isolada. Gate: fake API, expiração/revogação, arquivo remoto indisponível e integridade; nenhum upload real sem autorização, nenhuma deleção remota automática, render sem depender de rede.

## GAI-08 — QA multimodal
Reusar SemanticChecker/QA report; imagens/frames/trecho áudio conforme capacidade e permissão, prompts e resposta estruturados, evidência temporal e estado not_verified; revisão humana calibrada. Gate: fixture com mismatch conhecido, indisponibilidade não vira pass, sem envio de conteúdo privado não autorizado, custo guardado.

## GAI-09 — finops mínimo
Mapear UsageRepository/CostGuard/reservas e preços. Distinguir local, assistido, API; registrar unidade, provider/model, run/video/channel, estimado/efetivo/unknown e crédito/subsídio separado. Assinatura pessoal não implica direito a API; quota manual com timestamp/fonte ou unknown. Gate: teto zero sem chamada paga; saldo API não presumido; retry/timeout/restart sem cobrança duplicada simulada; relatório de custo/minuto com denominador válido e sem dupla contagem de assinatura/credit. Não criar FinOps service separado.

## Sequência e DoD
Foundation P0 -> V4-00 -> contratos mínimos V4-01/04/11 e gate custo -> GAI-01 + GAI-02 vertical slice -> revisão humana -> APIs opcionais em fases consumidoras -> Drive quando necessário. Usar golden fixture 60–90s, imagem e clipe externo original autorizado, sincronização e render real; depois ampliar piloto V4-13 com custo/minuto, tempo humano, proporção de assets descartados, direitos e qualidade comparativa. Sem publicação, upload remoto ou gasto não autorizado. Testes locais: fixtures/doubles, arquitetura, contratos, DB descartável, browser, FFmpeg; registrar SHA/comandos/saídas/hash/limitações e GO/NO-GO. Não criar CI/CD. Sem alteração de core não justificada e sem duplicar Registry, AssetRepository, RenderPlan ou pipeline.
