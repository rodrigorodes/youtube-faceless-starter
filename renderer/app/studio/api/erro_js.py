"""Mensagem de erro amigável no navegador: traduz o `detail` da API e nunca despeja JSON cru.

A API devolve `detail` em inglês (contrato estável, consumido por workers e testes). Esta camada fica
só na tela: reconhece os erros conhecidos e os diz em português com o próximo passo; o que não
reconhece vira a frase de fallback da própria tela + o detalhe técnico, curto, entre parênteses.
`detail` como lista (validação 422) vira "Revise os campos: …", sem `JSON.stringify`.

Uso nas telas: `window.StudioErro.texto(dados, 'verifique os campos.', status)`.
"""

ERRO_JS = r"""
(function () {
  // [padrão, mensagem, anexarDetalheTecnico] — do mais específico para o mais genérico.
  var TRADUCOES = [
    [/did not expose an email/i, 'O Google não informou o e-mail da conta. Conecte de novo e permita o acesso ao e-mail.', false],
    [/has no YouTube channel/i, 'Esta conta Google não tem um canal do YouTube. Crie o canal no YouTube e conecte de novo.', false],
    [/(oauth state|consent state|pkce verifier).*(match|expired|lost|invalid)|state (does not match|expired)|lost its pkce verifier/i,
      'A autorização expirou ou não confere. Clique em Conectar e refaça o consentimento.', false],
    [/oauth callback has no code/i, 'O Google não devolveu o código de autorização. Refaça a conexão.', false],
    [/reconnect required/i, 'Esta conexão com o YouTube precisa ser refeita. Conecte a conta Google de novo.', true],
    [/temporarily unavailable/i, 'O Google/YouTube está indisponível agora. Tente de novo em instantes.', true],
    [/OAuth is not configured/i, 'A conexão com o Google não está configurada neste ambiente (credenciais OAuth).', true],
    [/OAuth failed/i, 'O Google recusou a autorização. Tente conectar de novo.', true],
    [/publication executor is not configured/i, 'A publicação ainda não está configurada neste ambiente. Nada foi enviado ao YouTube.', false],
    [/publication not found/i, 'Publicação não encontrada. Atualize a página.', false],
    [/database unavailable/i, 'O banco de dados está indisponível. Tente de novo em instantes.', false],
    [/services? unavailable|not configured/i, 'Este recurso não está disponível neste ambiente.', true],
    [/model output rejected/i, 'O modelo devolveu uma resposta que o Studio recusou. Tente gerar de novo.', false],
    [/asset refused/i, 'Um material (imagem ou áudio) foi recusado. Troque o material ou tente de novo.', true],
    [/not found/i, 'Não encontrado. Atualize a página e tente de novo.', false],
    [/already exists|duplicate/i, 'Já existe um item com esse nome ou identificação.', true],
    [/version conflict|stale|expected_version/i, 'Outra pessoa alterou isto antes de você. Atualize a página e refaça a mudança.', false],
    [/budget|spend cap|cost cap/i, 'O teto de custo foi atingido. Ajuste o limite em Configurações para continuar.', true],
    [/api key/i, 'Falta a chave de acesso deste serviço. Cadastre em Configurações.', false]
  ];
  var PADRAO = {
    400: 'A solicitação não foi aceita. Confira os dados e tente de novo.',
    401: 'Sua sessão não é válida. Entre de novo.',
    403: 'Você não tem permissão para esta ação.',
    404: 'Não encontrado. Atualize a página e tente de novo.',
    409: 'O estado atual não permite esta ação. Atualize a página e confira.',
    413: 'O conteúdo enviado é grande demais.',
    422: 'Revise os campos informados.',
    429: 'Muitas tentativas seguidas. Aguarde um pouco e tente de novo.',
    500: 'O servidor falhou ao processar. Tente de novo; se repetir, veja os logs.',
    502: 'Um serviço externo falhou. Tente de novo em instantes.',
    503: 'Este recurso está indisponível agora. Tente de novo em instantes.',
    504: 'O servidor demorou demais para responder. Tente de novo.'
  };
  function curto(texto) {
    texto = String(texto).replace(/\s+/g, ' ').trim();
    return texto.length > 160 ? texto.slice(0, 157) + '…' : texto;
  }
  // Texto que já está em português (acentos ou palavras comuns): é mostrado como veio.
  function jaEmPortugues(texto) {
    return /[À-ÿ]/.test(texto) || /\b(não|nao|precisa|adicione|informe|escolha|selecione|falha|erro|inválid|aguard|indispon)/i.test(texto);
  }
  function campos(lista) {
    var nomes = [];
    lista.forEach(function (item) {
      var loc = item && Array.isArray(item.loc) ? item.loc : [];
      var nome = loc.filter(function (p) { return typeof p === 'string' && p !== 'body' && p !== 'query'; }).pop();
      if (nome && nomes.indexOf(nome) < 0) nomes.push(nome);
    });
    return nomes.length ? 'Revise os campos: ' + nomes.join(', ') + '.' : PADRAO[422];
  }
  function texto(dados, fallback, status) {
    var detalhe = dados && typeof dados === 'object' ? dados.detail : undefined;
    var base = fallback || 'tente novamente.';
    if (Array.isArray(detalhe)) return campos(detalhe);
    if (typeof detalhe === 'string' && detalhe.trim()) {
      for (var i = 0; i < TRADUCOES.length; i++) {
        if (TRADUCOES[i][0].test(detalhe)) {
          return TRADUCOES[i][1] + (TRADUCOES[i][2] ? ' (Detalhe técnico: ' + curto(detalhe) + ')' : '');
        }
      }
      if (jaEmPortugues(detalhe)) return detalhe;
      return base + ' (Detalhe técnico: ' + curto(detalhe) + ')';
    }
    if (status && PADRAO[status]) return PADRAO[status];
    return base;
  }
  window.StudioErro = { texto: texto };
})();
"""
