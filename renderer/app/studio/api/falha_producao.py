"""Falha da produção em português: o que aconteceu, o que fazer e para onde ir.

O motivo real do estágio (`failure_reason`, `error_message`) é uma mensagem técnica em inglês, como
`SourceRefused: no sources with checkable claims: add sources first`. A tela mostra primeiro a
explicação e o próximo passo, com um botão para o lugar certo, e mantém o motivo técnico logo
abaixo — nada é escondido nem inventado. Motivo desconhecido não ganha explicação inventada.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import escape as e

from .panel_video_nav import area_href


@dataclass(frozen=True)
class Falha:
    texto: str
    destino: str | None = None  # área do vídeo ("fontes", "qualidade"…) ou caminho absoluto ("/studio/…")
    rotulo: str | None = None


_FONTE_ILEGIVEL = ("Não foi possível ler a fonte pela URL. Cole o texto da página no campo «Texto da fonte» "
                   "e tente novamente.")

_REGRAS: tuple[tuple[re.Pattern[str], Falha], ...] = tuple((re.compile(p, re.I), f) for p, f in (
    (r"no sources with checkable claims|add sources first",
     Falha("O roteiro só é escrito a partir de fatos das fontes, e este vídeo ainda não tem nenhuma fonte com "
           "afirmações que possam ser conferidas. Adicione uma fonte (a URL com o texto colado) e só então tente de novo "
           "— repetir antes disso falha de novo.", "fontes", "Adicionar fonte")),
    (r"url host is not in the allowlist",
     Falha("O endereço da fonte não está na lista de domínios permitidos. Cole o texto da página no campo "
           "«Texto da fonte»: o texto colado vale como fonte mesmo sem a URL liberada.", "fontes", "Abrir fontes")),
    (r"private address|unsupported content type|no readable text|too many redirects|downgrade https",
     Falha(_FONTE_ILEGIVEL, "fontes", "Abrir fontes")),
    (r"fact-check did not pass",
     Falha("O fact-check reprovou cenas: há afirmações sem apoio nas fontes. Revise as cenas sinalizadas ou "
           "acrescente fontes que as sustentem.", "cenas", "Revisar cenas")),
    (r"render did not finish",
     Falha("A renderização não terminou com sucesso. Abra a execução para ver o motivo e tente novamente.")),
    (r"qa gate refused|qa failed|no successful render to verify|no qa report|render and a qa report",
     Falha("A verificação de qualidade (QA) não passou ou não pôde rodar. Veja os apontamentos na aba "
           "Qualidade & Aprovação.", "qualidade", "Abrir qualidade")),
    (r"no approved publication",
     Falha("Não há publicação aprovada pendente. Aprove o vídeo em Qualidade & Aprovação antes de publicar.",
           "qualidade", "Abrir qualidade")),
    (r"reconnect required|oauth|youtube channel",
     Falha("A conexão com o YouTube precisa ser refeita. Reconecte a conta Google e tente novamente.",
           "/studio/panel/conexoes", "Abrir conexões")),
    (r"publication did not complete",
     Falha("A publicação no YouTube não concluiu. Nada foi enviado como sucesso. Confira a aba Publicação "
           "YouTube e a conexão do canal.", "publicacao", "Abrir publicação")),
    (r"video \S+ does not exist",
     Falha("O vídeo desta execução não existe mais.")),
))


def explicar_falha(motivo: str | None) -> Falha | None:
    """Explicação pt-BR de um motivo técnico, ou None se o motivo for vazio ou desconhecido."""
    if not motivo or not motivo.strip():
        return None
    for padrao, falha in _REGRAS:
        if padrao.search(motivo):
            return falha
    return None


def falha_html(motivo: str | None, video_id: str, *, estilo: str = "margin:0.5rem 0 0") -> str:
    """Bloco HTML: explicação + botão para o lugar certo + o motivo técnico, sempre visível."""
    if not motivo or not motivo.strip():
        return (f'<p class="sub" style="{estilo}">O motivo não foi registrado; abra a execução para ver '
                'o detalhe.</p>')
    falha = explicar_falha(motivo)
    tecnico = f'<p class="sample" style="margin:6px 0 0">Motivo técnico: <code>{e(motivo)}</code></p>'
    if falha is None:
        return (f'<p class="sub" style="{estilo}">A etapa falhou e o Studio não tem uma explicação '
                f'pronta para este motivo. Abra a execução para ver o detalhe.</p>{tecnico}')
    acao = ""
    if falha.destino and falha.rotulo:
        href = falha.destino if falha.destino.startswith("/") else area_href(video_id, falha.destino)
        acao = f'<p style="margin:10px 0 0"><a class="btn small" href="{href}">{e(falha.rotulo)}</a></p>'
    return f'<p class="sub" style="{estilo}"><strong>{e(falha.texto)}</strong></p>{acao}{tecnico}'


def _regras_js() -> str:
    """As mesmas regras, em JS, para o polling da execução (a fonte continua sendo `_REGRAS`)."""
    regras = [{"p": padrao.pattern, "t": f.texto} for padrao, f in _REGRAS]
    return json.dumps(regras, ensure_ascii=False)


# `window.StudioFalha.explicar(motivo)` devolve a explicação em português ou o próprio motivo.
FALHA_JS = (
    "(function () {\n"
    "  var REGRAS = " + _regras_js() + ".map(function (r) { return [new RegExp(r.p, 'i'), r.t]; });\n"
    "  window.StudioFalha = { explicar: function (motivo) {\n"
    "    if (!motivo) return motivo;\n"
    "    for (var i = 0; i < REGRAS.length; i++) { if (REGRAS[i][0].test(motivo)) return REGRAS[i][1]; }\n"
    "    return motivo;\n"
    "  } };\n"
    "})();\n"
)
