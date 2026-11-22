# UX revisada — fluxo completo e configurações disponíveis

## Princípio
Preservar a cobertura da V3/V3.1 e VE-07 anterior, reorganizando-a por canal e vídeo. Progressive disclosure significa expor detalhes na área adequada, não remover capacidades. FEATURE-COVERAGE-V3.md é gate obrigatório.

## Navegação global
Início, Criar vídeo, Vídeos, Tendências e ideias, Desempenho, Biblioteca, Configurações. Canal ativo consistente em todas as áreas. Selecionar outro canal abre seus vídeos; não muda a propriedade de vídeo aberto. Conta/equipe e usuário são contextos separados, com conta pessoal padrão para usuário solo.

## Navegação do vídeo
Visão geral, Fontes e roteiro, Narração, Cenas e mídias, Composição, Qualidade, Publicação, Produção. Acessível por lista de vídeos ou criação. Navegar não conclui etapa; status real e próxima ação são projetados pelo backend. Produção oferece mapa de dependências e ações, sem repetir formulários.

### Visão geral
Prévia, estado, próximo passo, voz/estilo/formato/custo e opções avançadas do vídeo. Histórico e identidade sempre acessíveis. Render anterior é identificado como desatualizado; nunca atribuir resultado antigo a revisão nova.

### Criar
Tema/roteiro, formato, duração e padrão do canal visível. Opções avançadas opcionais: estilo, voz, providers, mídia, qualidade e limite. Criar rascunho não inicia gasto. Seguir para fontes/roteiro; pesquisa automática não é pressuposta.

### Fontes e roteiro
Cadastrar fontes de texto/URL; distinguir registrada, extraída e verificada. Fact-check com evidências e falhas acionáveis quando disponível. Roteiro completo e por cena. Alterações preservam IDs não afetados; redivisão exige comparação quando ambígua. Salvar não dispara IA.

### Narração
Voz/provider, velocidade e controles suportados. Ouvir trecho real, regenerar cena ou todos os trechos impactados; mostrar duração-alvo e medida. Se não existe áudio, não oferecer reprodução falsa. Alinhamento por palavra só com capacidade comprovada.

### Cenas e mídias
Lista/grade numerada + prévia + propriedades: texto, intenção, voz e mídia. Adicionar/remover/reordenar. Trocar mídia mostra candidatos, origem, licença, custo e alternativa anterior. Busca stock/IA/upload são entradas do mesmo contrato. Regeneração seletiva apresenta impacto antes de pagar. ID de cena não é índice.

### Composição
Tracks de leitura para base, B-roll, títulos, legendas, narração e música. Presets de tipografia, transições/movimento, resolução/FPS, volume e área segura. Core valida opções. Sem editor NLE livre no MVP. Render explicitamente solicitado e com estado real.

### Qualidade e aprovação
Checklist com evidências e links à cena. Técnico bloqueante; semântico ausente = not_verified. Aprovar requer render/checksum atual e permissão no servidor. Mutação invalida aprovação para nova revisão sem apagar histórico publicado.

### Publicação
Prévia aprovada, título/descrição/tags quando suportados, thumbnail, privacidade, canal autorizado e agendamento com timezone explícito no produto. Confirmação final distinta de aprovação. Alterações de metadados/destino invalidam intenção pendente. Publicação concluída é imutável como histórico; edição local não substitui o arquivo no YouTube.

### Produção e avançado do vídeo
Etapas, pause/resume/retry/cancel, cache e custos quando medidos; erro acionável e retomada após fechar navegador. Run atual e snapshot em detalhes. Retry/resume congelam configuração; regeneração cria execução nova. Resultado de job antigo não promove revisão atual.

## Settings completo
1. Canais: criar/editar/selecionar, YouTube/destino e estado.
2. Estratégia editorial: idioma, público, pilares, narrativa, duração, CTA.
3. Marca e estilo: biblioteca, voz, legenda/fonte, música/volume, motion/transição, cor, thumbnail.
4. Produção e orçamento: perfil, limites soft/hard, resolução/FPS, mídia, providers por tarefa, revisão e fallback.
5. Conexões e providers: catálogo real por capacidade, modelos, disponibilidade, teste, credencial/BYOK, conta Google/canais/autorização.
6. Conta e equipe: membros/papéis, organização, uso/preferências/aparência.
7. Avançado: render/RenderPlan, QA, saúde, configuração efetiva sanitizada, logs/eventos/API/n8n.

## Herança e validação
Padrão de canal só para novos vídeos; adotar padrão atual em vídeo existente é explícito. Preservar precedência efetiva V3.1. Configuração não consumida pelo core não deve ser apresentada como aplicada. Catálogo demo não equivale a suporte de SDK. Controle de permissão, CAS, custo e destino no backend.

## Feedback e acessibilidade
Salvo/salvando/erro explícitos; produção separada de rascunho. Confirmação para exclusão/efeitos externos. Nenhuma porcentagem fabricada. Conflito preserva edição local. Layout 390/768/1280 px; foco visível, labels, modal com Escape/foco e contraste 4.5:1 como meta a verificar. Sem depender de cor. Sidebar colapsável/rolável no mobile; tabs do vídeo com overflow controlado.

## Escopo da demo
Formulários de Settings salvam localmente ao alterar campo. Texto/roteiro usam Salvar; gerenciamento completo de drafts não salvos e conflitos pertence ao produto. QA/render/voz/publicação/conexão são simulações; gráficos fixos. Sem API, OAuth ou coleta de segredos. O CSS V3 original foi incorporado, com extensões de componentes para novas áreas. Não há validação visual real aprovada nesta entrega.
