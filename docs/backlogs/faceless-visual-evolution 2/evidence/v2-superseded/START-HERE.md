# Comece aqui

1. Abra `prototype/index.html` em um navegador. Não precisa de servidor nem instalação.
2. Selecione um canal, abra um vídeo e alterne entre Conteúdo, Edição e Publicação.
3. Em Edição, selecione uma cena, altere o texto ou a mídia e use “Simular atualização”.
4. Simule revisão e publicação; são operações locais fictícias. Nenhuma API, cobrança, áudio ou MP4 real.
5. Teste o outro canal, crie um vídeo, configure a identidade e simule uma falha/retomada.
6. Leia [PROJECT-V2](PROJECT-V2.md), [decisões](DECISIONS.md) e [backlog](phases/BACKLOG-V2.md).
7. Para implementar, use [prompt mestre](prompts/00-master.md) no repositório real e delimite a fase desejada.

## Incorporar no seu checkout
A pasta atualizada permanece em `docs/backlogs/faceless-visual-evolution 2/`. Não é necessário renomeá-la. Todos os links da proposta usam caminhos relativos. Preserve arquivos locais mais recentes: extraia o ZIP em outra pasta e compare antes de copiar.

## Estado da entrega
- Documentação e protótipo: atualizados.
- Aplicação Python, SQL, n8n e integrações: preservadas.
- Testes do produto e render real: não executados nesta atualização documental.
- O protótipo usa armazenamento local do navegador; botão “Reiniciar demo” limpa somente seus dados de demonstração. Se o navegador bloquear esse armazenamento, funciona em memória até fechar.
