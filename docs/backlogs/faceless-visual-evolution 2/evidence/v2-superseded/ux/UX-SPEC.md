# UX — Criar e editar dentro do vídeo

## Navegação
- Global: Início, Canais, Biblioteca, Configurações.
- Canal: Vídeos, Ideias, Identidade, Configurações.
- Vídeo: Conteúdo, Edição, Publicação; histórico e execução em detalhes secundários.
- Breadcrumb com canal e vídeo; seleção de canal persiste na navegação. Ao trocar de canal durante edição, salvar rascunho ou informar falha; abrir listagem do novo canal, sem reatribuir o vídeo aberto.
- Contexto “Todos os canais” só para agregação. Criar vídeo nesse contexto exige canal explícito.

## Primeira utilização
Conta pessoal criada sem questionário de equipe. Criar canal: nome, idioma e sugestão de identidade com padrões editáveis. Conexão YouTube pode ser feita depois, mas publicação exige autorização válida. Não bloquear a primeira criação por configuração avançada de providers; quando não houver capacidade disponível, informar qual conexão falta.

## Novo vídeo
Tema OU roteiro. Formato e duração aproximada. Defaults do canal visíveis: voz, estilo, idioma, qualidade/custo. Opção “Revisar roteiro antes de gerar cenas”. CTA inicial “Criar rascunho”; ação paga separada “Gerar”, com estimativa/limite. Se já há roteiro, preservar texto do usuário e não substituir silenciosamente.

## Conteúdo
Briefing, roteiro completo e resumo do canal. Alteração de roteiro deve reconciliar cenas mantendo IDs dos trechos não afetados; quando não houver correspondência segura, mostrar proposta de redivisão antes de aplicar. Texto editável por cena em Edição. Autosave com estados salvando/salvo/falhou; bloqueio de geração sobre alterações não salvas.

## Edição
Desktop: lista de cenas, prévia central, propriedades contextuais (Texto e voz / Mídia / Aparência). Seleção não inicia geração. Sequência inferior é leitura; mover cena por botões acessíveis. Preview de cena e vídeo distinguem artefato real, storyboard e prévia desatualizada.

Ações: salvar texto; ouvir áudio disponível; escolher voz compatível; comparar/trocar mídia; adicionar/remover/reordenar cena; atualizar somente afetadas; restaurar revisão anterior como NOVA revisão. Confirmar exclusão de cena. Não prometer custo zero por restaurar: artefatos ausentes podem exigir geração.

Ao alterar texto: narração e timings afetados, composição e QA ficam pendentes. Trocar mídia preserva narração, mas invalida visual/final. Mudança global de estilo apresenta impacto e custo antes de geração. Cache pode evitar trabalho, mas não prometer reutilização antes da análise.

## Revisão e publicação
Checklist ao lado da prévia final. Cada problema leva à cena correspondente, quando possível. Técnico bloqueante; semântico ausente mostra “Não verificado”. Separar aviso editorial de bloqueio técnico e permitir política explícita de revisão humana.

Aprovar esta versão é distinto de confirmar envio. Destino traz nome/avatar/ID do canal YouTube e conexão válida. Título/descrição/privacidade/thumbnail/agendamento entram no resumo final. Se mudar depois da confirmação, exigir nova intenção de publicação. Mostrar status real: enviando/processando/publicado/erro, conforme suportado pela integração.

## Estados de produto (projeções, não novos enums obrigatórios)
| Dimensão | Rótulos |
|---|---|
| Conteúdo | Rascunho, Alterações salvas |
| Produção | Na fila, Gerando, Pausado, Precisa de atenção, Falhou, Pronto para revisão |
| Revisão | Pendente, Aprovado, Aprovação desatualizada |
| Publicação | Não publicado, Agendado, Enviando, Publicado, Falhou |

“Publicado” depende de publicação confirmada; APPROVED não pertence ao filtro. Um vídeo publicado com nova edição mostra “Publicado · alterações locais”. Nenhuma porcentagem fictícia: usar etapas reais ou contagem conhecida.

## Erros e recuperação
| Situação | Experiência |
|---|---|
| Provider indisponível | Preservar rascunho e prévia; tentar novamente ou escolher alternativa elegível |
| Orçamento insuficiente | Mostrar saldo/limite e custo; não chamar provider |
| Custo desconhecido | Explicar falta de estimativa e pedir limite/política; não tratar como gratuito |
| Duas abas editam | Rejeitar revisão obsoleta; comparar/recarregar, preservar texto local |
| Falha parcial | Manter cenas prontas; mostrar etapa afetada e retentativa idempotente |
| OAuth expirado | Reconectar destino sem perder vídeo |
| Cancelar geração | Encerrar trabalho possível, informar custos já incorridos; manter rascunho |
| Navegador fechado | Job continua no servidor; retomar pelo vídeo |

## Identidade e providers
Alterações de canal valem para novos vídeos; botão explícito adota novos padrões em vídeo existente com preview de impacto. Providers globais em Configurações; override por vídeo em Avançado. Segredos nunca renderizados. Controles desabilitados explicam capacidade faltante. Voz diferente por cena é exceção explícita, não fallback automático.

## Acessibilidade e responsividade
390/768/1280 px sem rolagem horizontal da página. Controles com labels; foco visível; status em aria-live; navegação por teclado; confirmação com foco gerenciado e Escape. Não depender de cor. Meta de contraste 4.5:1 para texto normal. Erro junto do campo e resumo quando necessário. Preview possui descrição; áudio/vídeo reais exigem controles acessíveis.

## Protótipo entregue
Demonstra canais, vídeos separados, criação, identidade herdada por snapshot, cenas editáveis, troca de mídia, histórico simples, falha/retomada e gates simulados. Dados ficam localmente no navegador quando disponível. Não implementa login, isolamento real, pesquisa de mídia, TTS, áudio, render, custo medido, OAuth, QA real, agendamento ou upload. Biblioteca e configurações são demonstrativas. Não oferece edição NLE.
