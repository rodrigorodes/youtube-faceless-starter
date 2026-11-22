# Projeto consolidado — Canal como contexto, vídeo como espaço de trabalho

## 1. Problema e resultado
A VE-07 anterior expunha dez etapas internas como telas principais. O criador precisava navegar entre roteiro, narração, storyboard, mídia e qualidade para corrigir uma única cena. Preservar a identidade violeta e os componentes visuais; reorganizar a experiência em torno do conteúdo.

Resultado esperado: escolher canal, informar tema/roteiro, gerar com padrões conhecidos, revisar e ajustar cenas e publicar uma versão aprovada. O usuário pode sair durante a execução e voltar ao mesmo vídeo.

## 2. Hierarquia
Conta/equipe tem membros e canais. Canal contém vídeos. Vídeo mantém cenas, revisões, execuções e publicação. Conta Google é uma integração; não equivale a usuário do produto ou canal editorial. Uma conta pessoal deve ser criada automaticamente, sem wizard de organização para usuário solo.

Não introduzir um nível visível “projeto” entre canal e vídeo. No código atual, `projects` e `channel_profiles` têm relação 1:1 por FK UNIQUE: mapear os identificadores antes de criar/renomear entidades. `workspaces` já existe, mas a vinculação completa não foi validada; não tornar sua adoção um pré-requisito visual.

## 3. Experiência
Menu global: Início, Canais, Biblioteca, Configurações. Canal: Vídeos, Ideias, Identidade, Configurações. Vídeo: Conteúdo, Edição, Publicação. Histórico e detalhes de execução ficam em painel secundário do vídeo. Início reúne trabalhos e ações pendentes com identificação do canal.

Novo vídeo pede tema OU roteiro, formato e duração aproximada. Canal fornece idioma, voz, estilo e política de qualidade/custo. Mostrar resumo e opção “alterar somente neste vídeo”. Preferência “Revisar roteiro antes de gerar cenas” substitui a bifurcação Automático/Assistido; ambos usam o mesmo coordenador, com pausa persistida quando configurada.

Editor: cenas à esquerda, prévia no centro, propriedades da cena à direita, sequência e duração abaixo. No mobile, lista de cenas e propriedades colapsam. Roteiro, voz e imagem são acessíveis sem trocar de vídeo. Prévia antiga permanece identificada como desatualizada até o novo artefato ficar pronto.

Publicação reúne prévia final, achados, título, descrição, thumbnail, destino, privacidade e agendamento quando suportado. Aprovar e publicar continuam comandos distintos. Exportar não exige OAuth, mas exige artefato válido e a política de QA aplicável.

## 4. Reuso identificado no ZIP
| Base observada | Uso proposto | Limitação/evidência |
|---|---|---|
| `api/shell_v3.py` | Shell, canal ativo e navegação | Adaptar hierarquia, sem SPA obrigatória |
| `api/panel_videos.py` | Listagem por canal e entrada no vídeo | `_situacao_key` inclui APPROVED em publicados: corrigir |
| `api/panel_production.py` | Progresso e workspace | Confirmar endpoints e comandos existentes por fase |
| `domain/production_run.py` | Runs, checkpoints e lifecycle | Retry/resume congelam config; regeneração cria nova execução |
| `application/production.py` | Coordenação e gate | Não duplicar pipeline |
| `domain/provider.py` | ECONOMY/BALANCED/PREMIUM e capabilities | Preferência não garante capacidade nem custo conhecido |
| `channel_profiles` e revisões | Identidade do canal | Snapshots existentes devem continuar respeitados |
| `organizations/users/memberships/byok_keys` | Fundamentos de conta e equipe | Tabelas não provam isolamento completo |
| `visual_styles` | Estilo reutilizável | Schema ainda menciona biblioteca compartilhada single-tenant |
| `domain/render_plan.py` + compiler + renderer | Evolução VE-01–06 | Validar suporte real no baseline, não pela demo |

Caminhos Python relativos a `renderer/app/studio/`. A inspeção foi estática; não é auditoria completa nem certificação SaaS.

## 5. Providers e custo
Credenciais por conta/equipe, política padrão por canal, override por vídeo, exceção por cena quando suportada. Não duplicar segredos em snapshots. Resolver capacidades antes de habilitar controles. Permitir ver provider/modelo em detalhes avançados e registrar a escolha real por operação.

O usuário escolhe econômico/equilibrado/maior qualidade, voz e origem da mídia. O router escolhe implementação elegível conforme capacidades, disponibilidade, licença e limite. Voz de identidade não troca silenciosamente. Fallback com mudança perceptível ou custo além do autorizado requer decisão. Custo desconhecido não é zero; não permitir gasto ilimitado por interpretação de “maior qualidade”.

Salvar rascunho é gratuito e não inicia geração. Gerar usa estimativa, limite, reserva e idempotência. Operação com resultado financeiro ambíguo permanece pendente de reconciliação; retry cego não é seguro.

## 6. Fronteiras do MVP
Inclui histórico simples recuperável e comparação de alternativa selecionada, sem undo/redo ilimitado. Mantém timeline de leitura e reordenação de cenas por botões; não implementar tracks livres/keyframes. Importação de narração/SRT pode entrar depois, com contrato de sincronização próprio. Analytics e Finder/Intelligence são evoluções separadas: ideias aprovadas entram como briefing no mesmo vídeo.

## 7. Sucesso
Metas de validação (não resultados medidos): criar rascunho em até 60 segundos com canal configurado; localizar e substituir mídia de cena em até três ações após abrir o vídeo; retomar produção em até duas ações desde o Início. Medir tempo até primeira prévia separando espera do motor e interação humana. Custos e falhas devem ser compreensíveis sem abrir logs técnicos.

## 8. Referências
- https://join.elevenlabs.io/ — integração de criação e edição no Studio.
- https://fstudio.digital/ — edição centrada em cenas e associação de fontes de mídia.
Consulta pública em 22/11/2026; não houve teste dos produtos autenticados/instalados. São referências de interação, não contratos de API ou evidências de capacidade do nosso aplicativo. Nenhum asset/branding foi copiado.
