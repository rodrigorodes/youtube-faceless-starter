# Benchmark UX — evolução das jornadas do Faceless Studio v2

Data da consulta: 2026-11-22.
Escopo: pesquisa de referências e inspeção do mockup `prototype-v4-v2/index.html`.
Não modifica o mockup nem o backend. Recomendações são hipóteses de melhoria, não resultados de testes com usuários.

## Método e limites

Foram consultadas páginas públicas oficiais de Descript, ElevenLabs, InVideo e YouTube. Não houve teste autenticado dessas plataformas nem comparação de performance.
Canva foi localizado por pesquisa, mas a página completa retornou bloqueio de navegador: usar somente como referência preliminar.
As capacidades dos concorrentes não demonstram que nosso backend as suporta.
Não copiar identidade visual: preservar tokens, cores e organização do Studio.

## Referências verificadas

1. **Descript — Selection toolbar**
   https://help.descript.com/descript-tour/selection-toolbar
   Ao selecionar texto, oferece ações contextuais: regenerar, adicionar camada, cena, comentários e correções.
   Aplicação proposta: ferramentas da cena selecionada, em vez de todas as ferramentas abertas em todas as cenas.
   Cuidado: corrigir transcrição sem alterar áudio, no Descript, não equivale a editar roteiro TTS no nosso produto.

2. **ElevenCreative Studio**
   https://elevenlabs.io/docs/eleven-creative/products/studio
   Documenta entrada por prompt, inspirações e upload; edição manual; biblioteca por projeto/workspace.
   Nos projetos de áudio: histórico de gerações por parágrafo, restauração, bloqueio, invalidação após mudar texto/voz.
   Documenta aviso de quantos parágrafos serão afetados ao substituir voz.
   Aplicação proposta: escopo explícito da mudança, histórico por cena e reutilização.
   Não importar promessas de regeneração gratuita, limites ou suporte de modelos.

3. **InVideo — Undo / redo**
   https://help.invideo.io/invideo-ai/how-can-i-undo-or-redo-my-edits
   Documenta desfazer/refazer na barra inferior após entrar na edição.
   Aplicação proposta: edição reversível e restauração de cenas, sem confundir desfazer edição com desfazer publicação.

4. **YouTube — Schedule video publish time**
   https://support.google.com/youtube/answer/1270709?hl=en
   Distingue privado/agendado/público; permite escolher data, horário e fuso, alterar agendamento e publicar imediatamente.
   Aplicação proposta: estados explícitos, fuso visível e confirmação do destino.

5. **Canva — Brand Kits / Templates (evidência parcial)**
   https://www.canva.com/help/using-brand-templates/
   https://www.canva.com/business/features/brand/
   Resultados oficiais de busca descrevem kits de marca e modelos reutilizáveis. A leitura completa da ajuda foi bloqueada.
   Aplicação proposta: identidade reutilizável do canal; não atribuir à Canva detalhes de interação não verificados.

## Princípio

Menos fricção não significa menos controle: ações frequentes devem ser diretas, ações caras devem ser previsíveis e edições devem ser reversíveis.
Piloto e Diretor são duas entradas para o mesmo vídeo, não dois produtos ou projetos separados.

## P0 — corrigir antes de expandir

### 1. Tema e roteiro devem ser entradas distintas
- Evidência local: Home oferece “tema ou roteiro”; `quickv2` trata tudo como `topic`. `quick` classifica pela quantidade de caracteres.
- Risco: roteiro colado vira assunto para gerar outro roteiro, perdendo a intenção.
- Proposta: “Ideia” / “Já tenho roteiro” como seletor curto; sem inferir pelo tamanho.
- Aceite: roteiro permanece literal nas cenas e registrado como fonte; ideia permite geração.

### 2. Honrar os padrões prometidos pelo canal
- Evidência: `newDefaults()` fixa `dur:'45'`, apesar de existir duração configurável no canal.
- Proposta: resumo “Usando padrões de [canal]”, com formato, voz, estilo e duração; alterações marcadas “Somente neste vídeo”.
- Aceite: vídeo novo herda a duração configurada; mudar canal não altera vídeos existentes.

### 3. Agendar não é publicar
- Evidência: o handler `publish` grava `state='published'` e `at:'agora'`, mesmo com agendamento.
- Proposta: opções “Publicar agora” / “Agendar”; data, horário e fuso; cartão final com canal, versão e visibilidade.
- Aceite: agendamento futuro mostra “Agendado”; envio/processamento não é apresentado como publicação concluída.

### 4. Dar segurança para experimentar
- Evidência: `delscene` exclui imediatamente, sem desfazer; regeneração substitui estado sem seleção de versões.
- Referências: InVideo e ElevenLabs.
- Proposta: desfazer/refazer para edição; “Cena removida · Desfazer”; histórico de áudio com ouvir/restaurar.
- Limite: desfazer não promete reembolso nem remoção de vídeo já publicado.
- Dependência: histórico de assets e revisões no backend precisa ser validado.

## P1 — próximo refinamento das jornadas

### 5. Storyboard focado, não um formulário repetido
- Hoje cada cena exibe simultaneamente prompt, player, regeneração, mídia, B-roll, reordenação e exclusão.
- Proposta: cenas compactas com miniatura, texto e estado. Seleção abre detalhes da cena; áudio e troca de mídia permanecem a um clique.
- Desktop: prévia ao lado da cena. Mobile: painel expansível, sem ações apenas por hover.
- Manter edição completa, atalhos e reordenação por botões, além de eventual arraste.
- Referência: Descript, ações contextuais.

### 6. Explicar o impacto antes de regenerar
- Exemplo de mensagem: “Você alterou 2 cenas. Vamos atualizar suas vozes e remontar o vídeo; as outras cenas serão preservadas.”
- Mostrar custo estimado ou “Estimativa indisponível”; nunca inventar preço zero.
- Troca de voz global informa número de cenas afetadas.
- “Ouvir” deve reproduzir áudio existente, não iniciar cobrança oculta.
- Referência: ElevenLabs, invalidação e escopo de alteração.
- Dependência: cálculo real de dependências, cache e custo; não basta trocar o rótulo do botão.

### 7. Aprovação centrada no vídeo
- Prévia como elemento principal; ao lado, resumo: “Pronto para revisar” ou “2 itens precisam de atenção”.
- Problemas apontam para a cena/campo exato; verificações aprovadas ficam em “Ver detalhes”.
- “Aprovar e preparar publicação” permanece; não confundir QA técnico com verificação factual.
- Esta é recomendação para nosso produto, não comportamento atribuído aos concorrentes.

### 8. Biblioteca como recurso de criação
- Ao trocar mídia: “Deste vídeo”, “Do canal”, “Meus arquivos”, “Stock”, “Gerar”.
- Ao trocar voz: ouvir, favoritos e recentes, antes de filtros técnicos.
- Ao vincular estilo: diferenciar “Padrão do canal” de “Aplicar somente ao vídeo”.
- Referência: ElevenLabs, separação Project / Workspace.
- Dependência: escopo de propriedade, uploads, licenças e busca; não pressupor biblioteca persistida.

### 9. Criar canal com confiança visual
- Manter criação curta. Nome + nicho + predefinição bastam para começar.
- Mostrar uma amostra visual e de voz, não outra sequência de formulários.
- Após criar: “Criar primeiro vídeo”; YouTube é necessário na publicação, não no onboarding.
- Na edição de identidade, explicitar “Afeta novos vídeos” e oferecer retorno ao padrão.
- Inspiração preliminar: Canva Brand Kit; padrões de herança são proposta nossa.

### 10. Resolver somente a conexão necessária
- Hoje o diálogo contextual pode mostrar todo o catálogo de providers.
- Proposta: “Precisamos conectar a voz escolhida”, seguido das opções válidas para essa tarefa.
- Nome/modelo/custo/rate limit continuam em “Detalhes avançados”.
- Distinguir “Referência cadastrada”, “Credencial disponível”, “Conexão testada” e “Selecionado para este canal”.
- Não declarar pronto apenas porque o usuário preencheu um apelido.
- Tarefas de roteamento automático sem candidato devem permitir mudar perfil ou escolher alternativa elegível, não apenas cadastrar chave.

## P2 — ganhar velocidade com uso recorrente

### 11. Reutilizar escolhas bem-sucedidas
- “Criar outro com este estilo”, duplicar configuração de vídeo sem copiar publicação, favoritos de voz e mídia.
- Ideias recomendadas explicam por que combinam com o nicho e deixam o tema editável.
- Referências: inspirações e assets reutilizáveis no ElevenLabs.
- Não substituir “Tendências” por dados inventados: sinalizar origem, janela e ausência de evidência.

### 12. Retomar sem procurar
- Home: “Continuar editando”, “Revisar vídeo pronto”, “Corrigir uma falha”.
- Persistência real de rascunho com estados “Salvando”, “Salvo”, “Falha ao salvar”.
- Progresso pode ser acompanhado fora do workspace; conclusão volta para aprovação quando solicitado.
- Retomar apenas etapa falha, preservando outputs válidos e a revisão congelada.
- É proposta nossa; depende de contratos assíncronos e persistência, não apenas animação de progresso.

## O que não copiar

- Timeline complexa como porta obrigatória do fluxo Rápido.
- Chat de IA obrigatório para ações simples.
- Termos “capability”, “fallback” e “rate limit” na criação cotidiana.
- Regeneração paga escondida em um botão “Ouvir”.
- Publicação automática como efeito da aprovação.
- Checkout, onboarding longo ou funcionalidades extras só porque concorrentes têm.

## Ordem recomendada para a próxima versão

1. Entradas explícitas + herança correta + agendamento honesto.
2. Desfazer/restaurar + aviso do impacto de uma edição.
3. Storyboard compacto + aprovação orientada à prévia.
4. Biblioteca contextual + resolução de conexões por tarefa.
5. Persistência e retomada reais, respeitando disponibilidade do backend.

Não retirar controles ainda sem suporte: identificar claramente como proposta e mapear dependências de implementação.

## Validação proposta com usuários (não executada)

Tarefas: criar canal e primeiro vídeo; gerar a partir de roteiro próprio; trocar voz de uma cena; restaurar áudio anterior; corrigir erro de QA; agendar em canal específico.
Medir: conclusão sem ajuda, erros, retornos desnecessários, perda de trabalho e tempo de interação (separado do tempo de geração).
Critérios funcionais: nenhuma perda de roteiro; nenhuma publicação no canal errado; nenhum “Publicado” para vídeo apenas agendado; alterações não destroem versões sem restauração.
Só depois comparar métricas da v2 com a próxima versão. Não prometer percentuais de melhoria sem esse teste.
