# Google AI Pro e integração audiovisual — complemento V4.1

Status: proposta documental, não implementada. Código de referência: main 182ec75 (25/11/2026). Objetivo: aproveitar a assinatura pessoal e APIs oficiais, melhorar qualidade e reduzir custo de produção sem acoplar o Core a Google. Não criar terceiro MVP; preservar Foundation, 14 fases e 227 atividades originais (GAI-01–09 são complementos de aceite vinculados, não nova contagem do plano original).

## Decisão de produto
Priorizar **External Asset Import + Assisted Generation**, genéricos e úteis também a outros fornecedores. Após Foundation/V4-00 e contratos mínimos de V4-04/11, produzir vertical slice real com mídia externa. API automática e Drive são evoluções opcionais, somente após comprovar benefício, direitos, custo e disponibilidade. Não exigir novo serviço, broker, CI/CD, autenticação de assinatura não autorizada ou automação de navegador.

| Capacidade | Assinatura / ferramenta oficial (assistida) | Automatização (API separada) |
|---|---|---|
| Texto e direção criativa | Gemini, copiar/colar ou importar texto revisado | Gemini Text / OpenCode Bridge |
| Pesquisa | Deep Research, importar fontes/brief revisado | ResearchPort existente + fonte/API autorizada |
| Imagem | Nano Banana no Gemini/Flow, exportar arquivo | API de imagem oficial compatível |
| Vídeo | Flow/Veo, exportar clipes | Veo API assíncrona |
| Música | Ferramenta oficial disponível no plano, exportar se permitido | Provider autorizado opcional, não requisito |
| Voz | Importar áudio autorizado se exportável | Gemini TTS opcional; Piper local padrão |
| QA | Avaliação humana/assistida | Gemini multimodal opcional |
| Storage | Drive, quota pessoal compartilhada | Drive API com OAuth próprio e escopo mínimo |

A assinatura do operador foi informada como R$ 484,90 no primeiro ano, renovação R$ 969,90/ano, 5 TB compartilhados. Não é tarifa fixa do produto. Créditos Cloud de US$ 10/mês são benefício potencial sujeito à ativação, elegibilidade, faturamento e serviços cobertos; conferir no projeto. Flow, Gemini, Antigravity e Cloud têm franquias distintas; nenhuma quota transferível presumida. Não prometer tokens/clipes, saldo, gratuidade, monetização ou direitos comerciais. Conferir documentação vigente, região, modelo, preços e termos por capacidade antes de homologar. Links de referência: https://one.google.com/intl/pt_br/about/google-ai-plans/ ; https://ai.google.dev/gemini-api/docs ; https://ai.google.dev/gemini-api/docs/pricing ; https://developers.google.com/drive/api/guides/about-sdk ; https://antigravity.google/docs/faq ; https://labs.google/fx/tools/flow .

## AS-IS — pontos concretos consultados
| Código atual (renderer/app/studio/) | Achado | Delta mínimo |
|---|---|---|
| composition/providers.py, composition/wiring.py | Registry, OpenCode text/image, stock, Piper, FFmpeg, Pexels/Pixabay; Veo registrado em IMAGE | Reusar registry; não anunciar provider como disponível se não implementado; capability de vídeo explícita |
| adapters/image_veo.py | VeoImage estima custo e lança ModelUnavailable | Não chamar até contrato e adapter reais; não fingir suporte |
| application/media.py | SwapSceneMedia aceita asset existente ou MediaCandidate; CAS/versão/licença. _materialize aceita MIME de imagem e grava AssetKind.image | Importar local e corrigir suporte vídeo no caminho aplicável; não mascarar vídeo como imagem |
| adapters/storage.py | FileAssetStore.put valida imagem, dimensão e tamanho; FileRenderStorage resolve paths locais | Manter comportamento de imagem; estender via storage tipado/streaming |
| api/routes.py | /videos/{video_id}/scenes/{scene_id}/media; assets vinculáveis; preview /asset | Novo upload autorizado, reutilizar vínculo; verificar autoria/escopo de recurso e contrato HTTP |
| api/panel_video_storyboard_js.py | Escolher/trocar mídia, preview por img, busca e reuse | Entrada importar, prompt, preview por tipo, revisão/undo |
| adapters/asset_resolver.py | LocalAssetResolver, metadados por tipo, paths confinados | Reutilizar resolver; verificar arquivo e ffprobe antes de confiar em metadados |
| adapters/google_oauth.py | OAuth existente voltado ao YouTube | Não reutilizar grant/token YouTube para Drive |
| adapters/text_opencode.py | Bridge gera texto | Preservar; Google direto opcional, não requisito para modo assistido |

RenderPlan e FFmpeg continuam canônicos; candidato de vídeo no catálogo não comprova materialização/render de vídeo ponta a ponta. Validar compatibilidade de schema/asset kind, durações, paths e preview antes de implementar. Reusar migrações e contratos existentes, adicionar somente campos estritamente necessários.

## Modo assistido (P0 funcional do complemento)
Operador seleciona cena, imagem/vídeo/áudio, vê prompt com duração, formato, identidade de canal e intenção visual. Copia prompt, abre ferramenta oficial, gera e baixa conteúdo, importa arquivo e informa origem/termos/licença. Studio valida, registra proveniência e apresenta preview; operador aplica asset à cena com revisão esperada. Importação não executa LLM, não consome API, não abre browser automaticamente, não acessa cookies, não salva credencial de assinatura e não reivindica saldo remoto. Texto/research importado segue revisão editorial e SourceSnapshot/ClaimEvidence; não virar Asset audiovisual nem fonte verificada automaticamente. Música entra em track de áudio; voz externa entra no contrato de narração e sincronização, não no slot de imagem.

Estados conceituais, reconciliar com modelos reais: requested -> awaiting_external -> imported -> validated -> attached, com refused/stale/cancelled. Não precisa criar novo workflow persistente se revisão e asset já bastam; não bloquear worker esperando humano; gerar faltantes não sobrescreve asset aprovado. Não publicar automaticamente. Retomar estado do Studio após importação, sem regeneração ampla.

## Importação segura e integração de mídia
- Proposta de endpoint multipart autenticado e com proteção CSRF/origem de browser, por vídeo/cena ou biblioteca conforme contratos reais. Validar ownership/escopo, versão atual, bloqueio de produção e tamanho antes de gravar. Separar ingestão de associação: asset registrado -> seleção/revisão via SwapSceneMedia ou comando tipado equivalente (CAS), sem perder referência anterior se falhar.
- MVP imagem PNG/JPEG/WebP e vídeo MP4 codecs homologados; áudio WAV/MP3 na etapa de voz/música após suporte de tracks. Detectar conteúdo real, não confiar em extensão, MIME do cliente nem metadados declarados. Limites configuráveis de bytes, pixels, duração, frames, codecs, timeout/probe e espaço; streaming para temporário próprio, hash SHA-256 e finalização atômica; path seguro, sem URL arbitrária, traversal ou symlink. Não executar arquivo como código. Cleanup apenas temporários próprios e reconciliação de órfãos.
- Metadados: hash, kind, mime/codec, dimensions, duration_ticks, source/provider/model (quando conhecido), origem externa/AI ou stock, prompt/ref opcional, licença/termos/evidência, data, projeto/canal, estado. Não inventar licença nem permitir compartilhamento entre escopos não autorizados. Direitos desconhecidos: política de rascunho explícita, bloquear uso publicável; preservar gates existentes. Não aceitar declaração como comprovação automática de direito de terceiro.
- Reaproveitar AssetRepository/AssetStore/LocalAssetResolver, RenderPlan e cache. Imagem não muda contrato anterior; vídeo conserva tipo e duração, usar política explícita de trim/loop/freeze/crop, áudio original mute por padrão no B-roll; sem alterar duração da narração silenciosamente. Preview img/video/audio por tipo. Reutilizar asset por hash conforme escopo/licença; duas importações concorrentes não duplicam vínculo/custo; stale retorna conflito.
- Alteração de asset invalida somente dependências necessárias (shot/cena/final e aprovação correspondente), não roteiro/voz que não dependam da mídia; undo/redo conforme revisões existentes; no-op não invalida. Render em arquivos locais, sem rede durante compilação.

## API automática (P1, opt-in)
Novo adapter Google via portas existentes, preferir SDK/API oficial com versionamento, deadline, erros tipados e client mockável. Nomes de arquivos conceituais: adapters/google/client.py, text_gemini.py, image_gemini.py, video_veo.py, voice_gemini.py, quality_gemini.py, usage.py. Não criar todos antecipadamente. Texto retorna schema validado e usage; TTS entrega arquivo/duração e alinhamento existente; vision retorna achados estruturados/evidência, not_verified quando indisponível. Para Veo: capability video.generate, operation id persistido, polling com prazo, cancel/reconcile quando suportado, validar output e licenças; nunca repetir submit pago após timeout ambíguo. Provider Registry congela seleção por run; fallback só para capacidade compatível e orçamento aprovado. Segredos server-side, BYOK, não expor token/API key. Sem chamada paga em teste padrão, dublês e fixture local.

## Drive (P2)
Aproveitar espaço compartilhado, não 5 TB garantidos livres. OAuth separado com consentimento e escopos mínimos (preferir drive.file se suficiente), token no cofre, revogação e reconciliação. Biblioteca/backup complementar: copiar arquivos selecionados e metadados/hash, retry idempotente, verificar upload e download, staging local para render. Não tratar Drive como filesystem de trabalho, não substituir backup SQL/storage/cofre, não sincronizar segredos nem aplicar deleção remota automática. Antes de backup real, ensaio de recuperação isolado e autorização.

## Contabilidade
Ver [GAI-EXECUTION-PLAN](GAI-EXECUTION-PLAN.md). BillingMode conceitual: LOCAL_FREE (sem API, não sem custo de máquina), SUBSCRIPTION_ASSISTED (mensalidade alocada opcional, créditos anotados pelo operador, saldo unknown quando não disponível), API_METERED (estimativa, reserva, uso efetivo, crédito/subsídio e custo líquido separados). Não deduzir valor estimado da mensalidade duas vezes. Budget Guard opera custo bruto estimado e reserva antes de chamada paga, mesmo com créditos Cloud; reconciliar custo real, erro ambíguo e eventual cobrança. Nunca considerar paid API grátis com base na assinatura; sem fallback pago automático. Evidenciar origem do preço/versão/data e unidade (tokens/cache, imagens, segundos, áudio). Medir custo/minuto final e taxa de descarte, não presumir créditos equivalentes à duração publicável.

## Não escopo
OAuth de Antigravity/Flow no servidor, scraping/automação não autorizada, replicar Google Flow, render distribuído, integração automática com todas ferramentas, quotas inventadas, serviços de terceiros sem direitos, geração de vídeo inteira em IA obrigatória, refatoração ampla. Foundation continua primeiro.
