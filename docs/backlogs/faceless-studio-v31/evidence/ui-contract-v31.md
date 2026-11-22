# Telas afetadas pelo pacote V3.1 (contrato de UI)

Levantamento em 21/11/2026, a partir das tarefas F03–F06 e do que já está integrado.
Serve para não haver dois donos no mesmo arquivo nem promessa de tela sem backend.

| Tela / rota | Mudança necessária | Origem | Arquivos | Estado |
|---|---|---|---|---|
| `/studio/panel/tendencias` | filtro e **scroll infinito** (24 por lote, botão acessível + observer, fragmento `…/cartoes`) | pedido do operador | `api/panel_trends.py`, `api/routes.py`, `api/shell_v3_css.py` | **feito** (14 testes) |
| `/studio/panel/estilos` | separar **editar biblioteca** de **personalizar canal**; expor só parâmetro que o render usa; sem preview/percentual inventado | F05.T04 | `api/panel_styles.py`, `application/styles_page.py` | **feito** (`c77dbd5`) |
| `/studio/panel/canais` | **personalizar estilo do canal**: origem do valor (canal/estilo/padrão), valor efetivo e **reset**; revisão otimista (409 visível) | F05.T04 | `api/panel_channels.py`, `api/routes.py`, novo `panel_channel_style.py` | **feito** (`c77dbd5`) |
| `/studio/panel/canais` (Configurações) | **preferências de produção**: perfil econômico, limites vigentes, indisponibilidade, custo desconhecido, BYOK cadastrada × usada | F06.T03 | `api/panel_channels.py`, `application/channel_budget.py` | **feito** (`832dc9f`) |
| `/studio/panel/producao` | ações de **lifecycle** do run: pausar, retomar, tentar de novo, regenerar (rotuladas como execução nova) | F03.T04 | `api/panel_production.py`, `api/routes.py` | backend **feito** (`a77f661`); UI de produção pendente |
| `/studio/panel/avancado` | mostrar a **configuração efetiva persistida** e a proveniência do último run (read-only, sem edição) | F03.T02/T03 | `application/advanced_page.py`, `api/panel_advanced.py` | **feito** — agora dentro da casca de Configurações |
| `/studio/panel/producao` (casca) | casca **V3** com quadro de produção real (`id="pagina-producao"`), sem sidebar V2/API Docs/n8n | F07.T01 / FS31-A3 | `api/panel_production.py`, `api/routes.py` | **feito** |
| `/studio/canais` (Configurações) | **paridade visual** com a proposta: canal ativo no topo com `ATIVO`/`Trocar`, identidade em `item-config`, estilo em galeria de cartões; menu de 6 áreas na ordem do protótipo | pedido do operador | `api/panel_channels.py`, `api/shell_v3.py`, `api/shell_v3_css.py` | **feito** |

## Regras que valem para qualquer stream de UI

1. Nada de controle sem backend/teste: se não há caso de uso, a tela mostra estado ou não mostra.
2. Ausência de dado **nunca** é zero; custo real × estimado com rótulo.
3. Um único `aria-current="page"` por página (o item de navegação); filtro ativo usa `aria-current="true"`.
4. Sem `on*=` inline; JS no bloco com nonce; CSP preservada.
5. Escape de todo texto vindo de dados (o teste de XSS por tela é obrigatório).
6. Ação destrutiva (arquivar, reset, regenerar) tem confirmação explícita e diz o que acontece.

## Donos por arquivo nesta onda (evita conflito)

- `api/panel_channels.py` + `api/routes.py`: stream R (F06.T03) — depois passa para a fiação de F05.T04.
- `api/panel_styles.py` + `application/styles_page.py` + novos `panel_channel_style.py`/`channel_style_page.py`: stream S (F05.T04).
- `api/panel_production.py`: reservado para F03.T04 (P) após o backend fechar.