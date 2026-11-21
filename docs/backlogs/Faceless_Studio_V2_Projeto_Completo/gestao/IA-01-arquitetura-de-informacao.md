# IA-01 — Início, Produção e Tendências como telas separadas

Insumo da fatia IA-01. Escrito enquanto PROD-01 roda (não toca em `panel.py`).

## 1. O problema (relato do dono)

> "Tendências, produção e Início podiam ser em páginas diferentes, estão carregando juntas e só
> mudando a posição."

Confirmado no código. `render_panel` (`renderer/app/studio/api/panel.py:1757`, arquivo com 3548
linhas) emite **uma única** página com **cinco** seções, e a navegação aponta para **âncoras** dela:

| Item da nav (hoje) | `href` atual | Seção | Linha |
| --- | --- | --- | --- |
| Início | `#inicio-section` | hero + "precisa de atenção" | `panel.py:2386` |
| Produção | `#producao-section` | Produção | `:2452` |
| (sem item próprio) | — | `#precisa-section` (atenção humana) | `:2460` |
| Tendências | `#trending-section` | Tendências | `:2465` |
| Vídeos | `#videos-section` | Vídeos | `:2475` |

Há ainda `#new-video-section` (formulário do Início). Consequência: **todo** o conteúdo é renderizado
junto e navegar apenas rola a tela — exatamente o sintoma relatado.

## 2. O desenho aprovado manda o contrário

`produto/prototipo.html` (1373 linhas) já resolve isso com **telas de verdade**:
`<section class="view" id="…" hidden>` dentro de `<main class="views">`, com roteador por hash e
View Transitions (com fallback).

Telas (12): `inicio · tendencias · novo · producao · pesquisa · roteiro · editor · preview ·
publicacao · analytics · canais · equipe`.

Nav agrupada:

- **Operação** — Início, Tendências, Novo vídeo, Produção, Vídeos, Pesquisa, Roteiro, Editor,
  Preview e QA, Publicação
- **Aprendizado e gestão** — Analytics, Canais, Equipe, Configurações *em breve*

**Correção de uma suposição minha:** no protótipo, **"Vídeos" não é tela própria** — é um bloco
`#videos` dentro do **Início**, com alias de rota. O próprio protótipo comenta:

> "Vídeos" não tem tela própria: a lista vive no Início, na âncora `#videos`. A rota `#videos` abre o
> Início e leva o foco para a lista — destino real, sem link morto.

`JORNADA-E-TELAS.md` confirma: Home, Tendências, Novo vídeo e Produção são telas distintas, com ação
primária e informações essenciais próprias.

## 3. Decisão de implementação (escolhida por mim, com o motivo)

O protótipo é um mockup de documento único; o **app real já usa rotas de servidor por tela**
(`/panel/analytics`, `/panel/estilos`, `/panel/conexoes`, `/panel/canais`, `/panel/equipe`,
`/panel/novo-video`, `/panel/videos/{id}`). Logo:

1. **Rotas de servidor reais**, não roteador de hash: `/studio/panel` (Início),
   `/studio/panel/producao`, `/studio/panel/tendencias`. Cada rota renderiza **só** o seu conteúdo —
   é isso que mata o "carregando juntas" na raiz, porque deixa de existir HTML de cinco telas.
2. **Vídeos segue o protótipo**: continua sendo bloco dentro do Início. Publica-se
   `/studio/panel/videos` como **302** para `/studio/panel#videos` com foco no bloco — assim não
   existe link morto nem tela nova que o desenho não previu.
3. **Sem padrão ARIA de `tablist`** para a navegação (o protótipo registra que a guidance proíbe abas
   para navegação de página). A nav continua sendo `nav` com `aria-current="page"` no item ativo.
4. `#precisa-section` (atenção humana) é conteúdo do **Início**, junto do hero.
5. A tela de Produção **já existe** em `panel_production.py` (`render_execution`, `STAGE_LABELS`,
   `render_new_video`); "novo vídeo" já é `/panel/novo-video`. Reaproveitar, não reescrever.
6. Escopo desta fatia: **Início · Produção · Tendências · Vídeos**. Pesquisa, Roteiro, Editor,
   Preview e QA, Publicação, Analytics, Canais e Equipe ficam como estão (a nav mantém os destinos
   reais já entregues).

## 4. Custo real (o que quebra e precisa de correção deliberada)

Testes que **fixam as âncoras atuais** (verificado por `grep`, não suposto):

| Arquivo | Linhas |
| --- | --- |
| `tests/test_panel.py` | 624, 628, 631–634, 648, 649, 677 |
| `tests/test_panel_page.py` | 627, 749–750, 805 |
| `tests/test_publishing.py` | 430, 431, 436, 438 |
| `tests/test_ux_contract.py` | 107, 109 |

E os que verificam "exatamente um `aria-current=page`", que devem continuar valendo por tela:
`test_script_page.py:183–185`, `test_styles_page.py:135–139`, `test_connections_page.py:190–194`.

**Regra:** corrigir cada assert para a nova expectativa **de forma deliberada** — o teste passa a
documentar a mudança de IA (ex.: "Produção agora é `/studio/panel/producao`, não a âncora
`#producao-section`"). Nunca mascarar nem afrouxar o assert.

## 5. Sequência

IA-01 **depende de PROD-01**: os dois mexem em `panel.py` (PROD-01 no form do Início e na página do
vídeo). Ordem: mesclar PROD-01 no `main` → criar o worktree de IA-01 a partir do `main` já com ele →
implementar → Postgres dedicado → mesclar.

## 6. Critérios de aceite

1. `/studio/panel` (Início) renderiza hero + precisa de atenção + produção em andamento + próximos +
   tendências (resumo) + bloco Vídeos — e **não** contém o HTML completo de Produção nem de
   Tendências.
2. `/studio/panel/producao` e `/studio/panel/tendencias` renderizam suas telas isoladas, cada uma com
   `aria-current="page"` no próprio item da nav (exatamente um).
3. `/studio/panel/videos` → **302** → `/studio/panel#videos`; a nav de "Vídeos" aponta para esse
   destino real.
4. Verificação no container reconstruído: as três rotas respondem **200 logado** e cada página contém
   só as suas seções.
5. Suíte alvo verde com as correções deliberadas; `tests/test_architecture.py` intacto (nada de
   lógica nas views, wiring só em `composition.py`); sem `git add -A`.
