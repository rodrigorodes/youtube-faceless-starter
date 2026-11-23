"""Resultado da publicação em português para a aba Publicação.

`POST /studio/videos/{id}/publication/publish` devolve `result` (UPLOADED, IDLE, RETRY, RECONCILE,
DEAD_LETTER, BLOCKED) e um `detail` técnico em inglês. A tela mostra primeiro o que aconteceu e o
que fazer, e mantém o motivo técnico no fim — nada é escondido, e só `UPLOADED` conta como sucesso.

Uso: `window.StudioPublicacao.explicar(dadosDaApi)` devolve `{ok, texto}`.
"""

PUBLICACAO_JS = r"""
(function () {
  // [padrão do detalhe técnico, explicação com o próximo passo], do mais específico ao mais genérico.
  var MOTIVOS = [
    [/no YouTube destination is configured|no channel profile is configured|invalid project identifier/i,
      'Este canal ainda não tem um destino do YouTube conectado. Conecte o canal em Conexões e tente de novo.'],
    [/no connected authorization/i,
      'Não há autorização vigente para o canal do YouTube de destino. Refaça a conexão em Conexões.'],
    [/access token belongs to/i,
      'A conta Google conectada não é a do canal de destino. Conecte a conta certa em Conexões.'],
    [/needs to be reconnected|credentials are unusable/i,
      'A conexão com o YouTube precisa ser refeita. Conecte a conta Google de novo em Conexões.'],
    [/OAuth refresh failed/i,
      'Não foi possível renovar o acesso ao Google agora. Tente de novo em instantes.'],
    [/intent is missing|metadata changed|destination changed|render revision changed|checksum changed|not the current render|no longer matches/i,
      'A aprovação ficou desatualizada (o vídeo ou os dados mudaram depois dela). Aprove a versão de novo.'],
    [/QA did not pass/i,
      'O QA não passou. Corrija os problemas ou aprove com o motivo do override.'],
    [/no successful render/i,
      'Ainda não há um vídeo renderizado para publicar.'],
    [/rendered file is missing/i,
      'O arquivo do vídeo renderizado não foi encontrado. Renderize de novo.'],
    [/schedule has expired|too close/i,
      'O horário agendado já passou ou está perto demais (mínimo de 15 minutos). Escolha outro horário.'],
    [/disabled by configuration/i,
      'A publicação está desligada neste ambiente. Nada foi enviado ao YouTube.'],
    [/remote state is unknown|reported success without a video id|could not be recorded|disappeared while recording/i,
      'Não dá para saber se o YouTube recebeu o vídeo. Não reenvie: a publicação precisa ser reconciliada.'],
    [/already has another YouTube id/i,
      'Este vídeo já tem outro identificador do YouTube registrado. É preciso revisar manualmente.']
  ];

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
