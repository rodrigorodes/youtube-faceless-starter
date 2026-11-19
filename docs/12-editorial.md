# Fluxo editorial: fontes, roteiro e checagem factual (P02)

Do tema ao roteiro verificado, tudo pela API do estúdio (`/studio`, porta 8000, só local). O estado do vídeo segue
`IDEA → SCRIPTED → FACT_CHECKED`; nada avança para mídia, vídeo ou upload sem passar pela checagem.

## Passo a passo

```bash
B=http://localhost:8000/studio; H='Content-Type: application/json'
PID=$(curl -s -X POST $B/projects -H "$H" -d '{"name":"canal"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
VID=$(curl -s -X POST $B/videos -H "$H" -d "{\"project_id\":\"$PID\",\"topic\":\"ADE 2026\",\"format\":\"short\"}" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 1. fonte: URL da allowlist OU texto colado (use o texto quando o site bloquear raspagem)
curl -s -X POST $B/videos/$VID/sources -H "$H" -d '{"url":"https://www.amsterdam-dance-event.nl/en/"}'
curl -s -X POST $B/videos/$VID/sources -H "$H" -d '{"url":"https://www.amsterdam-dance-event.nl/en/about","text":"…texto copiado da página oficial…"}'

# 2. roteiro (2 a 20 cenas); regerar enquanto SCRIPTED cria a versão seguinte
curl -s -X POST $B/videos/$VID/script -H "$H" -d '{"scene_count":6}'
curl -s $B/videos/$VID/script

# 3. checagem factual: aprova e move para FACT_CHECKED, ou reprova e lista o que não tem fonte
curl -s -X POST $B/videos/$VID/fact-check -H "$H" -d '{}'
# só com motivo, e fica registrado: curl … -d '{"override_reason":"número conferido na fonte impressa"}'

# opcional: ranquear ideias antes de escolher o tema (1 a 20 ideias)
curl -s -X POST $B/ideas/score -H "$H" -d '{"topics":["ADE 2026: destaques","Bastidores do festival"]}'
```

Erros: `404` vídeo inexistente · `409` estado errado · `422` entrada recusada (URL fora da allowlist, texto vazio ou
maior que 200 mil caracteres, override sem motivo) · `403` teto de custo · `502` fonte ou modelo indisponível, ou
resposta do modelo fora do formato (nada é gravado) · `503` banco indisponível.

## Como a checagem factual funciona

O gate é **determinístico**, sem LLM. Cada cena cita `claim_ids`: frases verificáveis (com número ou nome próprio)
extraídas do texto da fonte. Para cada cena, **todo número e todo nome próprio da narração e da legenda precisa
aparecer nas claims citadas** (ou em todas as fontes, se a cena não citar nenhuma). Reprova o que não aparecer.

- Números equivalentes casam: `3.600`, `3,600`, `3600`, `três mil e seiscentos`, `1,5 mil`, `vinte e um`.
- Acentos são ignorados (`Oxygène` = `oxygene`); hífen separa nomes (`Jean-Michel` → `jean`, `michel`).
- Exônimos em português não existem na fonte em inglês (`Amsterdã`): entram em `STUDIO_ALLOW_NAMES` (padrão `amsterda`).
- **Override humano**: exige motivo não vazio; o relatório mantém a lista de itens sem fonte e `overridden: true`.
- O prompt do roteiro só oferece as claims; se a resposta cita um `claim_id` que não existe, é recusada.

### Limites conhecidos
- Uma palavra capitalizada **sozinha no início da frase** não é checada como nome próprio (não há léxico para
  separá-la de uma palavra comum). Se vier seguida de outra capitalizada, as duas são checadas.
- A checagem prova que número e nome existem na fonte citada, **não** que a frase os usa corretamente (ex.: trocar
  `3.600 artistas` por `3.600 eventos`). Leia o roteiro antes de aprovar; a aprovação humana é a P05.
- O prompt cabe em ~3.900 caracteres (limite do bridge): só as primeiras claims entram quando a fonte é longa.

## Fontes e segurança (SSRF)
- Allowlist por sufixo de domínio em `STUDIO_SOURCE_ALLOWLIST` (padrão `amsterdam-dance-event.nl`); `evil-…` e
  `….evil.com` não passam. Só `http(s)`, sem credenciais na URL.
- Antes de conectar, todo endereço resolvido precisa ser público (recusa loopback, rede privada, link-local, `100.64/10`).
- Até 3 redirects, cada um revalidado. Só `text/html`, `text/plain`, `application/xhtml+xml`; leitura cortada em 2 MB.
- Limite: o `httpx` resolve o nome de novo ao conectar (janela de DNS rebinding). A allowlist estreita é a defesa principal.
- Sites com Cloudflare ou captcha podem recusar: cole o texto oficial (`text`).

## Modelo e custo
- `STUDIO_TEXT` (`<provedor>:<modelo>`) define o provedor; o `config` do projeto sobrescreve. Provedores: `opencode`
  (bridge local, assinatura OAuth do OpenCode, sem custo por chamada) e `demo` (monta o roteiro com as próprias claims, offline).
- O bridge escolhe o modelo que ele mesmo carrega (`OPENCODE_MODEL`); o nome após `opencode:` só identifica a chamada no ledger.
- Toda chamada passa pelo `CostGuard` **antes**: teto por vídeo `MAX_COST_USD_PER_VIDEO` (padrão 0) e mensal
  `MAX_COST_USD_PER_MONTH` (padrão 15). Uso gravado em `studio.usage_ledger`, mesmo quando a resposta é recusada.

## Dados
Tabelas `source_snapshots` (texto + sha256 + data; mesma página com o mesmo conteúdo não duplica), `scripts` (versões),
`scenes` (substituídas a cada novo roteiro), `fact_checks` (todo relatório, inclusive os reprovados e os overrides).
Gerações concorrentes no mesmo vídeo são serializadas pelo bloqueio da linha: uma vence, a outra recebe `409`.

## Verificado (stack real)
URL real da ADE buscada com redirect; fora da allowlist, `127.0.0.1` e `file://` recusados (422); roteiro por LLM
real (bridge) aprovado na checagem; número trocado (`3,600` → `4,600`) reprovado, override vazio recusado (422),
override com motivo aceito e gravado.
