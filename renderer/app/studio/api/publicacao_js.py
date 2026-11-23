"""Resultado da publicação em português para a aba Publicação.

`POST /studio/videos/{id}/publication/publish` devolve `result` (UPLOADED, IDLE, RETRY, RECONCILE,
DEAD_LETTER, BLOCKED) e um `detail` técnico em inglês. A tela mostra primeiro o que aconteceu e o
que fazer, e mantém o motivo técnico no fim — nada é escondido, e só `UPLOADED` conta como sucesso.

As regras (`MOTIVOS`) são a única fonte: o servidor as usa para a falha já registrada e o navegador as
recebe em JSON para o resultado do clique. Uso no navegador:
`window.StudioPublicacao.explicar(dadosDaApi)` devolve `{ok, texto}`.
"""
from __future__ import annotations

import json
import re

# [padrão do detalhe técnico, explicação com o próximo passo], do mais específico ao mais genérico.
# Só construções comuns a Python e a JavaScript (sem lookbehind nem grupos nomeados).
MOTIVOS: tuple[tuple[str, str], ...] = (
    (r"no YouTube destination is configured|no channel profile is configured|invalid project identifier",
     "Este canal ainda não tem um destino do YouTube conectado. Conecte o canal em Conexões e tente de novo."),
    (r"no connected authorization",
     "Não há autorização vigente para o canal do YouTube de destino. Refaça a conexão em Conexões."),
    (r"access token belongs to",
     "A conta Google conectada não é a do canal de destino. Conecte a conta certa em Conexões."),
    (r"needs to be reconnected|credentials are unusable",
     "A conexão com o YouTube precisa ser refeita. Conecte a conta Google de novo em Conexões."),
    (r"OAuth refresh failed",
     "Não foi possível renovar o acesso ao Google agora. Tente de novo em instantes."),
    (r"intent is missing|metadata changed|destination changed|render revision changed|checksum changed"
     r"|not the current render|no longer matches",
     "A aprovação ficou desatualizada (o vídeo ou os dados mudaram depois dela). Aprove a versão de novo."),
    (r"QA did not pass",
     "O QA não passou. Corrija os problemas ou aprove com o motivo do override."),
    (r"no successful render",
     "Ainda não há um vídeo renderizado para publicar."),
    (r"rendered file is missing",
     "O arquivo do vídeo renderizado não foi encontrado. Renderize de novo."),
    (r"schedule has expired|too close",
     "O horário agendado já passou ou está perto demais (mínimo de 15 minutos). Escolha outro horário."),
    (r"disabled by configuration",
     "A publicação está desligada neste ambiente. Nada foi enviado ao YouTube."),
    (r"remote state is unknown|reported success without a video id|could not be recorded|disappeared while recording",
     "Não dá para saber se o YouTube recebeu o vídeo. Não reenvie: a publicação precisa ser reconciliada."),
    (r"already has another YouTube id",
     "Este vídeo já tem outro identificador do YouTube registrado. É preciso revisar manualmente."),
)
_COMPILADAS = tuple((re.compile(padrao, re.I), texto) for padrao, texto in MOTIVOS)


def explicar_motivo(detalhe: str | None) -> str | None:
    """Explicação em português do motivo técnico registrado; `None` quando não há regra (nada é inventado)."""
    for padrao, texto in _COMPILADAS:
        if detalhe and padrao.search(detalhe):
            return texto
    return None


_TEMPLATE = r"""
(function () {
  var MOTIVOS = __MOTIVOS__.map(function (m) { return [new RegExp(m[0], 'i'), m[1]]; });

  function motivo(detalhe) {
    if (!detalhe) return '';
    for (var i = 0; i < MOTIVOS.length; i++) { if (MOTIVOS[i][0].test(detalhe)) return MOTIVOS[i][1]; }
    return '';
  }

  function explicar(dados) {
    dados = dados || {};
    var detalhe = dados.detail ? String(dados.detail).slice(0, 300) : '';
    var tecnico = detalhe ? ' (Detalhe técnico: ' + detalhe + ')' : '';
    var explicado = motivo(detalhe);
    switch (dados.result) {
      case 'UPLOADED':
        return { ok: true, texto: 'Publicado no YouTube' + (dados.youtube_video_id ? ' (id ' + dados.youtube_video_id + ')' : '') + '.' };
      case 'IDLE':
        return { ok: false, texto: 'Nada para publicar: aprove uma versão primeiro, ou ela já foi enviada. Nada foi enviado agora.' };
      case 'RETRY':
        return { ok: false, texto: 'O envio falhou por um problema temporário. Uma nova tentativa foi agendada.' + (explicado ? ' ' + explicado : '') + tecnico };
      case 'RECONCILE':
        return { ok: false, texto: (explicado || 'Não dá para saber se o YouTube recebeu o vídeo. Não reenvie: a publicação precisa ser reconciliada.') + tecnico };
      case 'DEAD_LETTER':
      case 'BLOCKED':
        return { ok: false, texto: 'A publicação foi bloqueada. ' + (explicado || 'O envio não foi concluído.') + tecnico };
      default:
        return { ok: false, texto: 'Resposta inesperada do servidor; não é possível confirmar a publicação.' + tecnico };
    }
  }
  window.StudioPublicacao = { explicar: explicar };
})();
"""


PUBLICACAO_JS = _TEMPLATE.replace("__MOTIVOS__", json.dumps(MOTIVOS, ensure_ascii=False))
