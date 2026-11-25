# Plano de execução piloto — Faceless

**Estado: planejado, não executado.** Não há aprovação funcional do app nesta entrega.
Objetivo: validar um caminho completo local e suas barreiras de segurança antes de
ampliar a campanha. O produto é tratado como instalação local de um operador;
não presumir isolamento multitenant.

## G0 — Preparação e isolamento

- [ ] Registrar commit, arquivos modificados, versão da imagem e data da campanha.
- [ ] Reservar uso exclusivo do projeto Docker `faceless-e2e` e da porta 8100.
- [ ] Conferir que a stack E2E não contém dados de uso: o runner executa `down -v`.
- [ ] Garantir Postgres/storage descartáveis; nunca reutilizar `.env`, cofre ou DSN de uso.
- [ ] Conferir a prova de descartabilidade antes dos testes de banco.
- [ ] Confirmar providers demo/placeholder/Piper/FFmpeg e ausência de OAuth/bridge pagos.
- [ ] Preparar navegador/dependências Playwright no ambiente de testes.
- [ ] Definir pasta de evidências fora de montagens somente leitura.
- [ ] Registrar orçamento externo do piloto: **zero chamadas pagas e zero uploads reais**.

Falha em qualquer guarda bloqueia a fase dependente. Não modificar a guarda para continuar.

## G1 — Barreiras antes do caminho feliz

Executar cenários prioritários de acesso e publicação (capítulos 01 e 08):

1. Ausência de autenticação, credencial inválida e uso indevido de perfil worker/browser.
2. Tentativa de mutação browser sem proteção de origem/CSRF exigida.
3. Reivindicação/publicação sem aprovação ou com aprovação desatualizada.
4. Publicação pública sem confirmação explícita.
5. Recusa de fornecedor indisponível ou orçamento insuficiente sem efeito externo.

Conferir também ausência de efeitos persistidos e chamadas ao fake publisher.
Uma resposta 4xx sozinha não prova ausência de efeito. Casos de orçamento precisam
de fixtures dedicadas: o Compose E2E mantém `STUDIO_BUDGET_GUARD=0`.

## G2 — Jornada local mínima

Massa sintética: canal `QA-Historia-<RUN>`, vídeo sobre a queda de Constantinopla,
texto-fonte de `tests/e2e_full/conftest.py:25-33`, formato curto dentro de 60 segundos.
Usar IDs retornados, não valores fixos de ambiente.

1. Criar/selecionar canal e conferir configuração efetiva.
2. Criar vídeo com briefing e fonte fornecida.
3. Gerar/revisar roteiro e verificar checagem factual.
4. Gerar storyboard e conferir correspondência entre cenas e roteiro.
5. Produzir voz, mídia de teste, legendas e render.
6. Esperar estado terminal da produção, não apenas resposta de aceitação.
7. Abrir prévia, conferir artefato reproduzível e QA.
8. Aprovar a versão atual; confirmar que não houve publicação.
9. Editar uma entrada relevante e conferir invalidação de resultado/aprovação conforme contrato.
10. Regenerar e aprovar novamente; encerrar sem integração real com YouTube.

Evidências: estados antes/depois, IDs de versão/run, resumo QA, arquivo renderizado,
capturas e ausência de erros JS/5xx inesperados. Texto demo/imagem placeholder
não validam qualidade factual/estética de provedores reais.

## G3 — Falhas, concorrência e recuperação

Em fixtures controladas e objetos novos, separados da jornada feliz:

- Duas tentativas simultâneas de iniciar produção/publicação; observar uma posse válida.
- Timeout de fornecedor; verificar estado recuperável e tentativas limitadas.
- Expiração de lease e heartbeat concorrente; impedir commit do proprietário obsoleto.
- Falha depois do efeito externo simulado e antes da persistência; reconciliar antes de retry.
- Reserva de orçamento simultânea e liberação em falha; confirmar não duplicação de cobrança.
- Arquivo ausente/corrompido, mídia sem licença válida e QA reprovado.

Relógio/falhas simulados devem ser declarados como tal. Para testes reais de reinício,
usar exclusivamente processos/contêineres descartáveis e registrar o instante da falha.

## G4 — Expansão

Depois do piloto: demais configurações/providers, tendências, longform, diretores,
multishot, trocas de mídia, áudio/legendas, analytics, operação/backup, acessibilidade
e volume. O limite de 60 s da stack E2E não comprova longform de 480 s.
Criar campanha isolada própria para esses limites, sem alterar a stack de uso.

Campanha live é separada: exige autorização, conta/canal de teste, teto de custo,
visibilidade privada e confirmação de destino. Publicação pública não integra o piloto.

## Critérios de saída

- Todos os casos selecionados possuem evidência e camada identificadas.
- Nenhum bypass de autenticação/aprovação/orçamento, duplicação ou vazamento de segredo.
- Render local reproduzível, estado final coerente e aprovação vinculada à versão.
- Sem falhas críticas abertas; skips/bloqueios explicitamente listados.
- Zero uploads reais e zero chamadas pagas na campanha local.

Um piloto aprovado não aprova todos os cenários do plano.

## Critérios de parada e limpeza

Parar imediatamente se o destino não for descartável, aparecer segredo na evidência,
houver chamada externa inesperada, publicação indevida, duplicação de efeito ou
crescimento não limitado de tentativas/custo. Preservar evidência sanitizada.
Na saída, remover apenas recursos criados pelo executor da campanha, depois de
coletar evidências; nunca limpar storage, canais, bancos ou volumes de uso.
