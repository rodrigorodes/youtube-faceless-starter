# Higiene de segredos e pacote starter

Execute na raiz do repositório, com Git, Bash e Python 3 disponíveis:

```sh
scripts/check-secrets.sh
scripts/package-starter.sh /caminho/novo/starter.zip
```

Os comandos retornam zero em caso de sucesso e um em caso de detecção ou
erro; não mostram os valores detectados. O pacote não sobrescreve um arquivo
existente. A checagem consulta tanto o índice Git quanto os arquivos
rastreados na árvore de trabalho, inclusive alterações ainda não confirmadas.
Arquivos não rastreados, como credenciais e backups locais legítimos, não são
inspecionados, removidos nem incluídos. Links simbólicos em caminhos rastreados
fazem a operação falhar.

O pacote usa uma allowlist de caminhos e formatos: arquivos de configuração
especificados no script; código Python do renderer; migrações SQL numeradas
em `renderer/app/studio/adapters/postgres/migrations/`; schemas em
`contracts/v1/`; scripts e testes de código; documentação Markdown; e uma
lista explícita de exemplos e workflows JSON. Nomes contendo `backup`,
`archive`, `export` ou `dump` e formatos fora da allowlist, incluindo CSV,
ZIP e SQL fora das migrações, não entram no pacote. Para distribuir um novo
formato ou exemplo, revise e atualize explicitamente a política e seus testes.
As únicas exceções ao filtro de nome são os caminhos de código
`scripts/backup.py`, `scripts/export_contracts.py` e `tests/test_backup.py`;
elas não autorizam backups ou exportações de dados.

O scanner procura formatos conhecidos de chaves, cabeçalhos Bearer, valores
atribuídos a `client_secret` e `refresh_token`, e cabeçalhos de chave privada.
Usa limites mínimos de comprimento e exceções exatas para alguns marcadores
seguros; pode ter falsos positivos e negativos. Não examina o histórico Git,
imagens ou arquivos compactados de forma recursiva, nem garante detectar dados
pessoais ou todos os segredos. A allowlist também não garante que conteúdo
permitido não contenha dados sensíveis: **revise o conteúdo e a origem do ZIP
antes de distribuí-lo**, especialmente documentação, exemplos e workflows.
Ao detectar uma credencial exposta, siga o processo de resposta e rotação
apropriado; esses comandos não a invalidam.
