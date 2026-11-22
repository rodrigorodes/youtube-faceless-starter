/* Prototype V3. No API calls, credentials, uploads or real publication. */
const V3={input:'idea',selected:null,undo:new Map(),redo:new Map(),mediaTab:'video',bypass:false};
const clone=o=>JSON.parse(JSON.stringify(o));
const prior={home:pgHome,new:pgNew,scenes:tabScenes,qa:tabQA,pub:tabPub,modal:renderModal,render,finish:finishPipeline};
STATE.scheduled=['Agendado','accent'];
function snapshot(v){return clone({scenes:v.scenes,comp:v.comp,style:v.style,voice:v.voice});}
function remember(v){
 if(!v||v.state==='generating')return;
 const stack=V3.undo.get(v.id)||[];stack.push(snapshot(v));V3.undo.set(v.id,stack.slice(-30));V3.redo.set(v.id,[]);
}
function travel(from,to){
 const v=vid(),stack=from.get(v.id)||[];if(!stack.length)return;
 const target=to.get(v.id)||[];target.push(snapshot(v));to.set(v.id,target);
 Object.assign(v,stack.pop());dirty(v);render();toast('Edição restaurada. Publicações e custos não são desfeitos.');
}
newDefaults=function(){const c=ch();return {topic:'',mode:c.mode,format:c.format,voice:c.voice,style:c.style,template:'tp1',dur:String(c.dur||45),music:'mu1',script:V3.input==='script'};};
pgHome=function(){
 const root=document.createElement('div');root.innerHTML=prior.home();
 const field=root.querySelector('#homeTopic');
 field.insertAdjacentHTML('beforebegin',`<div class="row" style="margin-bottom:12px">${seg([['idea','Tenho uma ideia'],['script','Já tenho roteiro']],V3.input,'input-kind')}</div>`);
 field.placeholder=V3.input==='script'?'Cole seu roteiro. Cada parágrafo será preservado como uma cena.':'Qual história você quer contar?';
 const action=root.querySelector('[data-a=quickv2]');
 action.textContent=ch().mode==='piloto'?'⚡ Gerar vídeo completo':'🎬 Abrir storyboard';
 action.insertAdjacentHTML('beforebegin',`<span class="sample">Padrões de ${esc(ch().name)} · ${ch().dur}s · ${esc(sty(ch().style).name)}</span>`);
 return root.innerHTML;
};
pgNew=function(){
 const root=document.createElement('div');root.innerHTML=prior.new();
 const select=root.querySelector('#ndur'),d=S.newDraft;
 if(select&&!Array.from(select.options).some(o=>o.value===d.dur))select.add(new Option(d.dur+' s · padrão do canal',d.dur,true,true));
 return root.innerHTML;
};
tabScenes=function(v){
 const selected=v.scenes.find(s=>s.id===V3.selected)||v.scenes[0];
 if(!selected)return prior.scenes(v);V3.selected=selected.id;
 return `<div class="between" style="margin-bottom:16px"><div><h2>Conte sua história, cena por cena</h2><p class="sub">Selecione uma cena para editar. As demais ficam preservadas.</p></div><div class="row">
 ${b('↶ Desfazer','undo-v3','small',(V3.undo.get(v.id)||[]).length?'':'disabled')}
 ${b('↷ Refazer','redo-v3','small',(V3.redo.get(v.id)||[]).length?'':'disabled')}
 ${b('+ Nova cena','addscene','small')}</div></div>
 <div class="row" style="margin-bottom:16px">${v.scenes.map((s,i)=>b(`${i+1} · ${esc(s.title)} ${s.audio==='stale'?' · atualizar voz':''}`,'select-scene',s===selected?'primary small':'small',`data-id="${s.id}" aria-pressed="${s===selected}"`)).join('')}</div>
 ${sceneCard(v,selected,v.scenes.indexOf(selected))}
 <div class="row" style="margin-top:12px">${b('Histórico da voz','audio-history','small',`data-id="${selected.id}"`)}${b('Gerar tudo o que falta','genmissing','ghost small')}</div>
 <details class="diag" style="margin-top:18px"><summary>Ver roteiro completo · ${v.scenes.length} cenas</summary>${v.scenes.map((s,i)=>`<p style="margin-top:12px"><b>${i+1}. ${esc(s.title)}</b><br>${esc(s.text)}</p>`).join('')}</details>`;
};
tabQA=function(v){
 const root=document.createElement('div');root.innerHTML=prior.qa(v);
 const stack=root.querySelector('.two > .stack');
 if(stack&&stack.children.length>1){
  const checks=stack.firstElementChild,preview=stack.lastElementChild;
  stack.prepend(preview);
  const detail=document.createElement('details');detail.className='diag';
  detail.innerHTML='<summary>Ver todas as verificações técnicas</summary>';
  checks.replaceWith(detail);detail.append(checks);
  const issues=gates(v).filter(g=>g.st!=='ok');
  preview.insertAdjacentHTML('afterend',`<div class="card"><h3>${issues.length?'Pontos para revisar':'Pronto para sua revisão'}</h3>${issues.map(g=>`<p class="sub" style="margin-top:8px">${esc(g.n)} · ${esc(g.d)}</p>`).join('')}${issues.length?b('Revisar cenas','tab','small','data-v="cenas"'):''}<p class="sample">Verificações ilustrativas. QA técnico não verifica fatos do roteiro.</p></div>`);
 }
 return root.innerHTML;
};
tabPub=function(v){
 const scheduled=v.state==='scheduled';if(scheduled)v.state='approved';
 const root=document.createElement('div');root.innerHTML=prior.pub(v);
 if(scheduled)v.state='scheduled';
 const date=root.querySelector('#pm5');
 date?.insertAdjacentHTML('afterend','<p class="sample">Horário de Brasília · UTC−03:00. Agendar não publica agora.</p>');
 if(scheduled){
  const btn=root.querySelector('[data-a=publish]');
  btn.textContent='Atualizar agendamento';
  btn.insertAdjacentHTML('beforebegin',`<div class="note info" style="margin-bottom:12px">Agendado para ${esc(v.meta.schedule.replace('T',' às '))} · Brasília. Ainda não publicado.</div>`);
 }
 return root.innerHTML;
};
function nativeModal(title,body){
 $('#overlay').innerHTML=`<dialog class="modal" aria-labelledby="v3-dialog-title"><h2 id="v3-dialog-title">${title}</h2>${body}<div style="margin-top:16px">${b('Voltar','close-v3','ghost small')}</div></dialog>`;
 const dialog=$('#overlay dialog');dialog.addEventListener('cancel',()=>{S.modal=null;S.contextReturn=false;});dialog.showModal();
}
renderModal=function(){
 const m=S.modal;if(!m)return prior.modal();
 if(m.t==='impact'){
  const v=vid(),n=v.scenes.filter(s=>!s.media||s.audio!=='ok').length;
  nativeModal('Atualizar esta versão',`<p style="margin:12px 0">${n} cena(s) precisam de mídia ou voz atualizadas. As demais serão preservadas; a montagem será atualizada.</p><p class="sub">Estimativa ilustrativa do vídeo completo: ${usd(estCost(v))}. Custo incremental ainda não calculado.</p><p class="sample">A publicação anterior não muda. Será necessária nova aprovação.</p>${b('Confirmar atualização','confirm-render','primary')}`);return;
 }
 if(m.t==='audio-history'){
  const s=vid().scenes.find(s=>s.id===m.id),hist=s.generations||[];
  nativeModal('Versões da voz desta cena',`<p class="sample">Pré-escuta e áudio simulados. Restaurar não altera o texto atual.</p>${hist.map((g,i)=>`<div class="card flat" style="margin-top:10px"><b>Geração ${i+1}</b><p class="sub">${esc(g.text)}</p><div class="row">${b('▶ Ouvir versão','listen-history','small')}${b('Restaurar','restore-audio','small',`data-id="${s.id}" data-index="${i}"`)}</div></div>`).join('')||'<p>Nenhuma geração guardada ainda.</p>'}`);return;
 }
 if(m.t==='media'){
  const v=vid();const tab=V3.mediaTab;
  const media=tab==='video'?v.scenes:tab==='channel'?S.videos.filter(x=>x.ch===v.ch).flatMap(x=>x.scenes):[];
  const options=tab==='video'||tab==='channel'?media.filter(s=>s.media).map(s=>s.media):EMOJIS.slice(0,6).map(e=>({kind:tab==='stock'?'stock':'ia',emoji:e}));
  nativeModal('Mídia para esta cena',`<div class="row" style="margin:12px 0">${[['video','Deste vídeo'],['channel','Do canal'],['files','Meus arquivos'],['stock','Stock'],['generate','Gerar']].map(([k,l])=>b(l,'media-tab',tab===k?'primary small':'small',`data-v="${k}"`)).join('')}</div>${tab==='files'?'<p class="sub">Nenhum arquivo enviado. Importação real depende do backend.</p><label class="field">Escolher arquivo para demonstrar seleção<input id="demo-file" type="file" accept="image/*,video/*"></label><p id="file-result" role="status"></p>':`<p class="sample">Prévia ilustrativa. Sem busca, geração ou custo real.</p><div class="grid3">${options.map(x=>b(x.emoji,'pickmedia','',`data-k="${x.kind}" data-e="${x.emoji}"`)).join('')||'<p>Nenhuma mídia disponível neste escopo.</p>'}</div>`}`);return;
 }
 if(m.t==='contextproviders'){
  const c=S.route==='wizard'?S.wiz.d:ch(),missing=readiness(c).missing;
  const kinds=missing.map(x=>x.k);
  nativeModal('Preparar apenas o que falta',`<p class="sub">Seu rascunho permanece aberto.</p>${missing.length?missing.map(x=>`<div class="note" style="margin-top:12px">${esc(x.err)}</div>`).join(''):'<p class="note okn">Todos os serviços necessários estão prontos na simulação.</p>'}<div class="stack" style="margin-top:12px">${S.providers.filter(p=>kinds.includes(p.kind)).map(provCard).join('')}</div><details class="diag" style="margin-top:12px"><summary>Todos os serviços e detalhes avançados</summary>${S.providers.map(provCard).join('')}</details>${b('Concluir e voltar','closecontext','primary')}`);return;
 }
 prior.modal();
};
finishPipeline=function(v){
 prior.finish(v);
 v.scenes.forEach(s=>{s.generations??=[];if(!s.generations.some(g=>g.text===s.text&&g.voice===v.voice))s.generations.push({text:s.text,voice:v.voice});});
};
S.videos.forEach(v=>v.scenes.forEach(s=>{s.generations=s.audio==='ok'?[{text:s.text,voice:v.voice}]:[];}));
const mutationActions=new Set(['delscene','mv','broll','regen','genmissing','pickmedia','addscene','comp','compchk','vstyle']);
document.addEventListener('focusin',e=>{
 if(S.route==='video'&&e.target.matches('textarea[data-sid],input[data-sid],select[data-a=comp],input[data-a=comp]'))remember(vid());
});
/* Capture replaces old actions where their semantics no longer match V3. */
document.addEventListener('click',e=>{
 const el=e.target.closest('[data-a]');if(!el||el.disabled)return;
 const a=el.dataset.a,v=vid();
 if(mutationActions.has(a)&&S.route==='video'){remember(v);if(v.state==='scheduled')v.state='review';}
 if(a==='regen'){
  const s=v.scenes.find(s=>s.id===el.dataset.sid);s.generations??=[];s.generations.push({text:s.text,voice:v.voice});
 }
 const handled=['input-kind','quickv2','quick','undo-v3','redo-v3','select-scene','audio-history','restore-audio','listen-history','media-tab','close-v3','publish','confirm-render'];
 if(a==='render'&&!V3.bypass){
  e.stopImmediatePropagation();e.preventDefault();S.modal={t:'impact'};render();return;
 }
 if(!handled.includes(a))return;
 e.stopImmediatePropagation();e.preventDefault();
 if(a==='input-kind'){V3.input=el.dataset.v;render();}
 if(a==='quick'||a==='quickv2'){
  const content=S.homeTopic.trim();if(!content){toast('Escreva sua ideia ou cole um roteiro.');return;}
  S.newDraft={...newDefaults(),topic:V3.input==='script'?'Vídeo a partir do meu roteiro':content,script:V3.input==='script',scriptText:V3.input==='script'?content:''};
  if(a==='quick'||!readiness(ch(),ch().mode==='piloto'?undefined:['text']).ok){go('#/new');return;}
  const created=createVideo(ch().mode,S.newDraft.topic);S.homeTopic='';S.vid=created.id;S.route='video';S.tab='cenas';
  history.pushState(null,'','#/video/'+created.id+'/cenas');
  if(created.mode==='piloto')runPipeline(created,1);render();
 }
 if(a==='undo-v3')travel(V3.undo,V3.redo);
 if(a==='redo-v3')travel(V3.redo,V3.undo);
 if(a==='select-scene'){V3.selected=el.dataset.id;render();}
 if(a==='audio-history'){S.modal={t:'audio-history',id:el.dataset.id};render();}
 if(a==='listen-history')toast('Pré-escuta da versão selecionada · simulação sem áudio real.');
 if(a==='restore-audio'){
  remember(v);const s=v.scenes.find(s=>s.id===el.dataset.id),g=s.generations[Number(el.dataset.index)];
  s.restoredGeneration=Number(el.dataset.index);s.audio=g.text===s.text&&g.voice===v.voice?'ok':'stale';
  dirty(v);S.modal=null;render();toast(s.audio==='ok'?'Voz restaurada.':'Versão restaurada, mas não corresponde ao texto/voz atual.');
 }
 if(a==='media-tab'){V3.mediaTab=el.dataset.v;render();}
 if(a==='close-v3'){S.modal=null;S.contextReturn=false;render();}
 if(a==='confirm-render'){
  S.modal=null;render();V3.bypass=true;
  document.querySelector('[data-a=render]')?.click();V3.bypass=false;
 }
 if(a==='publish'){
  if(!ytOn()||!['approved','scheduled'].includes(v.state)||v.dirty){toast('Aprove uma versão atual e conecte o canal de destino.');return;}
  if(v.meta.schedule){
   const date=new Date(v.meta.schedule+':00-03:00');
   if(!Number.isFinite(date.getTime())||date.getTime()<=Date.now()){toast('Escolha uma data futura no horário de Brasília.');return;}
   v.state='scheduled';v.pub=null;toast('Agendado na simulação. O vídeo ainda não foi publicado.');
  }else{v.state='published';v.pub={url:'https://youtube.com/'+(v.format==='short'?'shorts/':'watch?v=')+uid('demo'),at:'agora'};toast('Publicação simulada. Nada foi enviado ao YouTube.');}
  render();
 }
},true);
document.addEventListener('change',e=>{
 if(e.target.id==='demo-file'){
  const f=e.target.files[0];$('#file-result').textContent=f?'Selecionado: '+f.name+'. Nada foi enviado ou armazenado.':'Nenhum arquivo selecionado.';
 }
 if(e.target.dataset.a==='meta'&&e.target.dataset.k==='schedule')render();
});
document.addEventListener('input',e=>{
 if(S.route==='video'&&vid()?.state==='scheduled'&&['text','prompt','brollnote','comp'].includes(e.target.dataset.a)){
  vid().state='review';toast('Agendamento precisa ser revisado após estas alterações.');
 }
});
document.title='Faceless Studio · V3 · Criar com confiança';
render();
