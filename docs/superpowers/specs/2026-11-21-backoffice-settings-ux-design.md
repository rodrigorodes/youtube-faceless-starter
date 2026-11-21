# UX das configurações do estúdio (canal · estilo · conta do YouTube)

**Projeto:** Faceless Studio V2
**Versão:** 1.0
**Status:** Desenhado
**Data:** 2026-11-21
**Base:** `main` @ `473492c`

---

## 1. Objetivo

O usuário precisa **configurar** três coisas novas — o **estilo** do canal, o **destino no
YouTube** e a própria **identidade do canal** — sem que a interface fique pesada. O critério
do dono do produto: *"não pesada e fácil para o usuário"*.

## 2. Diagnóstico: de onde viria o peso

A tela **Canais (F10)** já é um canivete: nome, estratégia, público, pilares, identidade
visual, voz, áudio, thumbnail, CTA **+** providers **+** budget **+** canal do YouTube **+**
OAuth. Empilhar ali também **Estilos** e **conta → N canais** faz o usuário ter de entender,
numa tela só: projeto, canal, provider, budget, escopo OAuth, estilo e conta.

O peso **não** vem do número de campos — vem de **conceitos misturados numa decisão só**.

## 3. Princípios (com referência)

| Princípio | Fonte |
| --- | --- |
| **Divulgação progressiva**: mostrar o essencial primeiro, revelar o avançado sob demanda; **no máximo 2 níveis** (mais que isso perde o usuário) | Nielsen Norman Group, *Progressive Disclosure* |
| **Uma tarefa primária por tela**; a arquitetura de informação é 80% da qualidade | sanjaydey.com, *SaaS Dashboard Design* |
| **Abas para 2–6 seções irmãs** (pares), não para passos sequenciais nem opções raras | setproduct.com, *Tabs UI design rules* |
| **Menu lateral com 3–7 destinos de topo** | NN/g, *Menu-Design Checklist* |
| **Configurações em seções categorizadas**, uma decisão por vez | uxuiprinciples.com |
| **Seleção em vez de formulário**; padrões que funcionam sem tocar em nada | (padrão do próprio painel: nada é obrigatório) |
| **O que não tem medição não aparece** | regra já vigente no painel |

## 4. Arquitetura de informação

A navegação ganha **dois destinos** — e para isso reaproveita um slot que **já existe e está
morto**: o item "Configurações — em breve" (`_NAV_UNAVAILABLE`, `api/panel.py:78`). Nada de
menu novo inchado: o placeholder vira item real.

```
Operação                         Gestão
 ├─ Início                        ├─ Estilos      ← NOVO (a biblioteca compartilhada)
 ├─ Produção                      ├─ Conexões     ← NOVO (contas Google → canais do YouTube)
 ├─ Tendências                    └─ Equipe
 ├─ Vídeos
 ├─ Analytics
 └─ Canais            ← continua sendo a unidade operacional; fica LEVE (ver §5.2)
```

**Por que separar "Estilos" do canal** (e não embutir em Canais): estilo é **compartilhado
entre canais**. Se ele mora dentro do canal, o usuário entende que é daquele canal só e volta
a copiar à mão — que é exatamente o problema que a biblioteca veio resolver. Separar **ensina
o modelo certo sem manual**.

## 5. Telas

### 5.1 Canais — lista (vira um índice)

Hoje "Canais" é um formulário gigante de um canal por projeto. Vira uma **lista de cards**:
cada card mostra o que decide a vida do canal, sem abrir nada.

```
┌───────────────────────────────────────────────┐
│ Música Eletrônica Brasil                      │
│ Estilo: Documentário Cinemático               │
│ Publica em: ADE Brasil (YouTube) · CONECTADO  │
│ 12 vídeos                                     │
└───────────────────────────────────────────────┘
```
Quando houver **um canal só** (o caso de hoje), a lista é dispensável: cai direto na tela do
canal. A lista só aparece quando **existe mais de um** — assim não criamos uma tela que hoje
seria inútil.

### 5.2 Canal — o detalhe (abas, não um formulário)

Quatro abas irmãs (2–6 = exatamente o caso de abas):

```
┌ Canal: Música Eletrônica Brasil ──────────────────────────────┐
│ [ Identidade ] [ Aparência ] [ Publicação ] [ Custos ]        │
├───────────────────────────────────────────────────────────────┤
│ Aparência                                                     │
│   Segue o estilo:   ( Documentário Cinemático ▾ )  + criar    │
│   ▸ Avançado  (ajustes deste canal, recolhido)                │
└───────────────────────────────────────────────────────────────┘
```

- **Identidade** — estratégia, público, pilares, idioma (o que *descreve* o canal).
- **Aparência** — **seletor** de estilo + "criar novo" (leva à biblioteca). Avançado
  recolhido. Um *preview* só aparece se for **real**; sem medição, sem preview.
- **Publicação** — **seletor** "publica em: (canal do YouTube ▾)" + status da conexão. Sem
  conta conectada → estado vazio que leva a **Conexões**.
- **Custos** — budget e providers (hoje misturados com a identidade).

### 5.3 Estilos — a biblioteca

Lista dos estilos do estúdio; cada linha: nome + resumo curto dos parâmetros + **quantos
canais usam**. Editar agrupa por nível de decisão (progressiva):

```
Básico      motion (ritmo de câmera) · music (bpm)
Avançado ▸  caption · palette · voice · extra
```
Arquivar em vez de apagar (o nome é liberado; os canais que usavam voltam ao padrão).

### 5.4 Conexões — conta Google → canais do YouTube

O fluxo real (validado contra como um produto do mercado faz o mesmo):

```
1. [+ Conectar conta Google]        → OAuth (Google)
2. Lista os canais da conta         → escolher UM
3. Confirmar o canal escolhido       → nome + id, para não errar de canal
4. Vinculado                         → aparece em "Publicação" do canal
```

- A tela mostra a hierarquia **conta → canais**, com status por canal (conectado / expirado /
  revogado) e **qual canal do estúdio publica ali**.
- **Reconexão isolada**: reconectar um canal não toca nos outros.
- **Confirmação explícita do canal** (nome + id): a própria referência de mercado diz que
  errar de canal custa segundos para evitar e horas para consertar — e é a nossa regra do
  YT-03 vista pelo usuário.

## 6. Estados vazios (parte do "fácil")

Toda tela nova tem estado vazio que **ensina o próximo passo**, não um vazio mudo:

| Tela | Vazio | O que ensina |
| --- | --- | --- |
| Estilos | "Nenhum estilo ainda" | criar o primeiro (ou "usar o padrão do estúdio") |
| Conexões | "Nenhuma conta conectada" | conectar (1 botão) + o que será pedido |
| Canal › Publicação | "Publica onde?" | link direto para Conexões |
| Canal › Aparência | sem estilo escolhido | "segue o padrão do estúdio" (e não é erro) |

## 7. O que mantém leve (checklist de aceite)

1. **1 seletor por escolha** — estilo e destino são seleções, não formulários.
2. **Nenhum campo obrigatório novo** — o canal nasce com padrão e sem destino.
3. **Avançado recolhido** — cores, `extra`, detalhes raros fechados por padrão.
4. **No máximo 2 níveis** de divulgação em qualquer tela.
5. **Menu não cresce além de 7 destinos** de topo.
6. **Nada inventado** — sem preview falso, sem percentual sem medição.
7. **Teclado e leitor de tela** — `aria-current`, `aria-disabled`, foco visível (o painel já
   faz isso; manter).

## 8. Referências

- Nielsen Norman Group — *Progressive Disclosure* (`nngroup.com/articles/progressive-disclosure/`).
- setproduct.com — *Tabs UI design rules* (abas para 2–6 seções irmãs).
- NN/g — *Menu-Design Checklist* (3–7 destinos de topo).
- uxuiprinciples.com — *Progressive Disclosure* (configurações em seções categorizadas).
- sanjaydey.com — *SaaS Dashboard Design* (uma tarefa primária por tela; IA é 80%).
- SocialKit — *How to Connect a YouTube Channel to a Scheduler* (fluxo conta → escolher canal
  → **confirmar o canal**; aviso do erro de canal; conexão de mais de um canal).

## 9. Decisões abertas

- **Onde vive "Custos"**: dentro do canal (recomendado) ou em Configurações do estúdio. Hoje
  está em Canais; mover para o canal é a leitura mais simples.
- **Preview de estilo**: só quando houver um preview **real** (render de amostra). Sem ele, a
  aba Aparência é só o seletor — e está ótimo.
- **Promover Estilos/Conexões a topo** se o uso mostrar que são visitados com frequência
  (hoje ficam sob "Gestão" para o menu não inchar).
