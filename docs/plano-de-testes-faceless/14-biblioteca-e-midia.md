# Biblioteca e mídia compartilhada

**Prefixo dos cenários:** `BIB`

> Arquivo gerado por `gerar.py` a partir de `dados/`. Não editar à mão; altere os dados e gere de novo.

## Como funciona

A Biblioteca (pgLibrary) tem cinco abas: Estilos visuais, Vozes, Músicas, Mídias & Stock (Pixabay) e Modelos de roteiro. Estilos são a biblioteca compartilhada com criação, edição versionada, arquivamento com limpeza de vínculos e contagem de uso. Vozes e modelos são catálogos locais exibidos sem síntese. Músicas vêm do manifest CC0 em storage/music-candidates e são servidas por rota dedicada. Mídias & Stock consulta a API Pixabay quando há chave configurada.

## Regras desta funcionalidade

| Regra | O que exige | Fontes | Cenários |
|---|---|---|---|
| `BIB.R01` | A Biblioteca renderiza cinco abas na ordem Estilos visuais, Vozes, Músicas, Mídias & Stock (Pixabay) e Modelos de roteiro; a aba ativa usa aria-selected; a lista de estilos mostra estilos reais e um vazio honesto quando não há catálogo; nenhum item de mockup é inventado. | `renderer/app/studio/api/panel_styles.py:881-935` | [BIB-01](#bib-01), [BIB-02](#bib-02) |
| `BIB.R02` | Estilos: criar valida nome e params; nome ativo duplicado é recusado; editar exige expected_version e campos da allowlist; arquivar mantém histórico, libera o nome e devolve links_cleared; a contagem de uso é medida. | `renderer/app/studio/application/styles.py:1-120`, `renderer/app/studio/api/routes.py:2834-2878` | [BIB-03](#bib-03), [BIB-04](#bib-04), [BIB-05](#bib-05), [BIB-06](#bib-06) |
| `BIB.R03` | Músicas: o manifest é lido de storage/music-candidates/manifest.json; a rota /studio/music/{file} serve apenas .mp3 de candidatos e devolve 404 fora; basename bloqueia path traversal; Accept-Ranges e cache são anunciados. | `renderer/app/studio/api/panel_styles.py:808-830`, `renderer/app/studio/api/routes.py:2880-2893` | [BIB-08](#bib-08) |
| `BIB.R04` | Mídias & Stock: GET /studio/media/search exige PIXABAY_API_KEY; sem chave devolve ok=false com erro legível e lista vazia; com chave delega ao adapter PixabayMediaSearch pela camada de composição, sem import de adapters na API. | `renderer/app/studio/api/routes.py:2895-2925`, `renderer/app/studio/composition/providers.py:1-40` | [BIB-09](#bib-09) |
| `BIB.R05` | Vozes: a página exibe o catálogo local (Piper Faber pt-BR como padrão do estúdio, Jeff) e a voz herdada do canal; não sintetiza áudio nem promete voz de provider não configurado. | `renderer/app/studio/api/panel_styles.py:644-700` | [BIB-07](#bib-07) |
| `BIB.R06` | Modelos de roteiro: três arquétipos são exibidos como referência; não há persistência, seleção por vídeo nem geração a partir do modelo. | `renderer/app/studio/api/panel_styles.py:700-810` | [BIB-10](#bib-10) |

## Resumo dos cenários

Total: 10 cenário(s), todos documentais nesta elaboração.

| ID | Cenário | Tipo | Regras | Status |
|---|---|---|---|---|
| [BIB-01](#bib-01) | Abas da Biblioteca e aba ativa | feliz | BIB.R01 | `A_PROJETAR` |
| [BIB-02](#bib-02) | Vazio honesto da biblioteca | borda | BIB.R01 | `A_PROJETAR` |
| [BIB-03](#bib-03) | Criar estilo válido e duplicado | feliz/erro | BIB.R02 | `A_PROJETAR` |
| [BIB-04](#bib-04) | Editar estilo com controle de versão | erro/concorrencia | BIB.R02 | `A_PROJETAR` |
| [BIB-05](#bib-05) | Arquivar estilo e limpar vínculos | feliz | BIB.R02 | `A_PROJETAR` |
| [BIB-06](#bib-06) | Uso por estilo medido | feliz | BIB.R02 | `A_PROJETAR` |
| [BIB-07](#bib-07) | Catálogo de vozes herdado do canal | feliz | BIB.R05 | `A_PROJETAR` |
| [BIB-08](#bib-08) | Manifest de músicas e rota de áudio | feliz/erro | BIB.R03 | `A_PROJETAR` |
| [BIB-09](#bib-09) | Busca Pixabay sem chave e com chave | erro/feliz | BIB.R04 | `A_PROJETAR` |
| [BIB-10](#bib-10) | Modelos de roteiro como referência | feliz | BIB.R06 | `A_PROJETAR` |

## Cenários

### BIB-01 — Abas da Biblioteca e aba ativa

- **Tipo:** feliz
- **Regras:** BIB.R01
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Confirmar a estrutura de cinco abas e o estado ativo.
- **Pré-condições:** render_styles com canal ativo e sem estilos.
- **Dados:** StylesPageView vazio; channel_name 'Canal H'; channel_voice 'Rodrigo'.
- **Passos:**
  1. Renderizar a página.
  2. Coletar os botões de aba.
  3. Conferir aria-selected e aria-current.
- **Esperado:** Cinco abas na ordem esperada; Estilos visuais é a aba ativa; o menu e a aba ativa usam aria-current; o cabeçalho diz 'Canal ativo: Canal H'.
- **Limitações:** O teste verifica HTML de servidor; o comportamento de troca de aba depende do JavaScript da página.
- **Automação:** camada `unit`; referência `Existente: tests/test_library_v3.py:27-40.`

### BIB-02 — Vazio honesto da biblioteca

- **Tipo:** borda
- **Regras:** BIB.R01
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Confirmar que a ausência de estilos não vira mockup.
- **Pré-condições:** StylesPageView sem itens.
- **Dados:** Sem estilos; com um estilo ativo depois.
- **Passos:**
  1. Renderizar sem estilos.
  2. Renderizar com um estilo.
  3. Procurar nomes fictícios.
- **Esperado:** Sem estilos, a página informa o vazio e não cria cards; com estilo, o card real aparece; nenhum nome fictício do protótipo é usado.
- **Limitações:** Nomes fictícios do protótipo podem existir em outros pontos da UI; este cenário cobre a Biblioteca.
- **Automação:** camada `unit`; referência `Existente: tests/test_library_v3.py:41-60.`

### BIB-03 — Criar estilo válido e duplicado

- **Tipo:** feliz/erro
- **Regras:** BIB.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Validar criação e recusa de nome ativo duplicado.
- **Pré-condições:** Repositório de estilos com um estilo 'Cinemático'.
- **Dados:** POST /styles com name 'Documentário' e params válidos; repetir com 'Cinemático'.
- **Passos:**
  1. Criar o estilo novo.
  2. Tentar criar o duplicado.
  3. Criar com params inválidos.
- **Esperado:** O estilo novo é criado com versão 1; o duplicado devolve erro de domínio; params inválidos devolvem 422.
- **Limitações:** O erro de duplicado é mapeado pelo guard global; a mensagem exata depende do handler.
- **Automação:** camada `local-integrado`; referência `Proposto: tests/test_styles_api.py.`

### BIB-04 — Editar estilo com controle de versão

- **Tipo:** erro/concorrencia
- **Regras:** BIB.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Recusar edição perdedora e campo fora da allowlist.
- **Pré-condições:** Estilo com versão 2.
- **Dados:** PATCH com expected_version 1; PATCH com campo 'organization_id'; PATCH válido com expected_version 2.
- **Passos:**
  1. Enviar a versão defasada.
  2. Enviar campo desconhecido.
  3. Enviar a versão correta.
- **Esperado:** Versão defasada devolve conflito; campo desconhecido devolve 422; a versão correta atualiza e incrementa a versão.
- **Limitações:** A concorrência real depende do repositório; o cenário descreve o contrato de versão.
- **Automação:** camada `local-integrado`; referência `Proposto: tests/test_styles_api.py.`

### BIB-05 — Arquivar estilo e limpar vínculos

- **Tipo:** feliz
- **Regras:** BIB.R02
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Confirmar soft delete com limpeza de vínculos e contagem.
- **Pré-condições:** Estilo usado por um canal e um vídeo.
- **Dados:** POST /styles/{id}/archive; depois listar com e sem include_archived.
- **Passos:**
  1. Arquivar o estilo.
  2. Conferir links_cleared.
  3. Listar com e sem arquivados.
- **Esperado:** O estilo sai da lista padrão; links_cleared reflete os vínculos limpos; o canal volta ao padrão e o vídeo herda do canal; include_archived mostra o estilo arquivado.
- **Limitações:** A limpeza de vínculos é transacional no repositório; o teste precisa de banco descartável.
- **Automação:** camada `local-integrado`; referência `Proposto: tests/test_styles_archive.py.`

### BIB-06 — Uso por estilo medido

- **Tipo:** feliz
- **Regras:** BIB.R02
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Confirmar que a contagem de uso vem do repositório.
- **Pré-condições:** Dois canais usando o mesmo estilo.
- **Dados:** GET /styles e leitura de usage_counts.
- **Passos:**
  1. Criar dois canais com o estilo.
  2. Listar estilos.
  3. Comparar a contagem.
- **Esperado:** A contagem é 2, sem estimativa; estilo sem uso mostra 0.
- **Limitações:** A contagem é por canal; uso por vídeo não é contabilizado nesta leitura.
- **Automação:** camada `local-integrado`; referência `Proposto: tests/test_styles_usage.py.`

### BIB-07 — Catálogo de vozes herdado do canal

- **Tipo:** feliz
- **Regras:** BIB.R05
- **Status:** A_PROJETAR
- **Prioridade:** media
- **Objetivo:** Confirmar que a voz do canal aparece e não há síntese.
- **Pré-condições:** channel_voice 'Rodrigo' e depois vazio.
- **Dados:** render_styles com channel_voice 'Rodrigo' e com ''.
- **Passos:**
  1. Renderizar com voz definida.
  2. Renderizar sem voz.
  3. Procurar indicadores de síntese.
- **Esperado:** Com voz definida, o card correspondente é destacado como ativo; sem voz, o padrão do estúdio é indicado; nenhum áudio é gerado na página.
- **Limitações:** A voz é herdada do canal; a página não valida se o provider de voz está disponível.
- **Automação:** camada `unit`; referência `Existente: tests/test_styles_page.py (parcial).`

### BIB-08 — Manifest de músicas e rota de áudio

- **Tipo:** feliz/erro
- **Regras:** BIB.R03
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Confirmar a leitura do manifest e a proteção da rota de áudio.
- **Pré-condições:** storage/music-candidates/manifest.json com 6 trilhas; um MP3 presente.
- **Dados:** GET /studio/music/<arquivo>.mp3; GET com ../; GET com .wav; GET de arquivo ausente.
- **Passos:**
  1. Baixar um MP3 do manifest.
  2. Tentar path traversal.
  3. Tentar extensão inválida.
  4. Tentar arquivo ausente.
- **Esperado:** O MP3 é servido com Accept-Ranges e cache; path traversal e extensão inválida devolvem 400; arquivo ausente devolve 404; a página mostra as 6 trilhas.
- **Limitações:** O manifest é lido do disco local; em container o caminho /data/music-candidates tem precedência.
- **Automação:** camada `mock`; referência `Proposto: tests/test_music_route.py.`

### BIB-09 — Busca Pixabay sem chave e com chave

- **Tipo:** erro/feliz
- **Regras:** BIB.R04
- **Status:** A_PROJETAR
- **Prioridade:** alta
- **Objetivo:** Confirmar a resposta honesta sem chave e o caminho com chave.
- **Pré-condições:** Ambiente sem PIXABAY_API_KEY; depois com chave de teste e adapter dublê.
- **Dados:** GET /studio/media/search?q=tecnologia&type=image.
- **Passos:**
  1. Chamar sem chave.
  2. Chamar com chave e adapter dublê.
  3. Conferir o import do adapter na API.
- **Esperado:** Sem chave: ok=false, erro 'PIXABAY_API_KEY não configurada no servidor' e candidates vazio; com chave: adapter devolve candidatos; a API não importa adapters diretamente (guard de arquitetura).
- **Limitações:** Nenhuma chamada real à Pixabay é feita; o adapter dublê substitui a rede.
- **Automação:** camada `mock`; referência `Existente: tests/test_architecture.py:45; rota proposta em tests/test_media_search_api.py.`

### BIB-10 — Modelos de roteiro como referência

- **Tipo:** feliz
- **Regras:** BIB.R06
- **Status:** A_PROJETAR
- **Prioridade:** baixa
- **Objetivo:** Confirmar que os três modelos são exibidos sem persistência.
- **Pré-condições:** render_styles padrão.
- **Dados:** Aba Modelos de roteiro.
- **Passos:**
  1. Renderizar a página.
  2. Coletar os cards de modelo.
  3. Procurar ação de salvar ou aplicar.
- **Esperado:** Três modelos são exibidos; não há ação de persistir ou aplicar modelo; o texto descreve o arquétipo sem prometer geração.
- **Limitações:** Modelos são conteúdo estático da página; não há API de modelos.
- **Automação:** camada `unit`; referência `Proposto: tests/test_library_models.py.`

## Resumo do capítulo

10 cenários documentais, todos A_PROJETAR. Execução direta, sem workflow. Os testes citados são referências existentes, não comprovação de aprovação. Nenhuma chamada paga à Pixabay é executada nesta rodada.
