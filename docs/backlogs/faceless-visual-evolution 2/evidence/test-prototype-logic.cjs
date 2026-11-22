const fs=require('fs'),vm=require('vm'),path=require('path');
const src=process.argv[2]||path.join(__dirname,'../prototype/index.html');
const html=fs.readFileSync(src,'utf8');const els={},events={},storage={};
function elem(id){return els[id]||(els[id]={id,value:'',innerHTML:'',textContent:'',checked:false,dataset:{},type:'text',style:{},open:false,hasAttribute(){return false},addEventListener(type,fn){(events[id+':'+type]??=[]).push(fn)},showModal(){this.open=true},close(){this.open=false}})}
const context=vm.createContext({document:{getElementById:elem,documentElement:{style:{}},addEventListener:(k,f)=>(events[k]??=[]).push(f)},localStorage:{getItem:k=>storage[k],setItem:(k,v)=>storage[k]=v,removeItem:k=>delete storage[k]},location:{reload(){}},setTimeout:()=>0,clearTimeout(){},console,Date});
const run=s=>vm.runInContext(s,context);run(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
const checks=[];function ok(s,label){if(!run(s))throw new Error(label);checks.push(label)}
function action(a,data={}){context.dat=data;run(`handle(${JSON.stringify(a)},{dataset:dat})`)}
function submit(id){for(const f of events.submit||[])f({preventDefault(){},target:{id}})}
function change(scope,key,value,type='text'){const e={dataset:{scope,bind:key},type,value,checked:value,hasAttribute(){return false}};for(const f of events.change||[])f({target:e})}
for(const route of ['home','videos','new','ideas','analytics','library','settings']){run(`S.route='${route}';render()`);ok('document.getElementById("app").innerHTML.length>100','Render de área: '+route)}
for(const tab of ['channels','strategy','brand','production','connections','team','advanced']){action('setting',{tab});ok('document.getElementById("app").innerHTML.length>600','Configuração disponível: '+tab)}
run("openVideo('rome')");for(const tab of ['overview','content','voice','edit','composition','quality','publish','production']){action('videoTab',{tab});ok('document.getElementById("app").innerHTML.length>600','Funcionalidade do vídeo: '+tab)}
action('setting',{tab:'strategy'});change('channel','strategy','Estratégia alterada');ok('channel().settings.strategy==="Estratégia alterada"','Estratégia editável e persistida');
run('var old=video().config.musicVolume');change('channel','musicVolume',25,'number');ok('channel().settings.musicVolume===25&&video().config.musicVolume===old','Configuração do canal preserva snapshot do vídeo');
action('addProvider');elem('providerName').value='Provider personalizado';elem('providerCapability').value='Roteiro';elem('providerModel').value='modelo-exemplo';elem('confirmModal').onclick();ok('providersFor("Roteiro").includes("Provider personalizado")','N providers aparecem na seleção por tarefa');
action('testProvider',{index:'4'});ok('S.account.providers[4].state.includes("simulado")','Teste de conexão explicitamente simulado');
action('addKey');elem('keyAlias').value='alias-teste';elem('keyProvider').value='Provider personalizado';elem('confirmModal').onclick();ok('S.account.keys[0].alias==="alias-teste"','BYOK com referência fictícia, sem segredo');action('revokeKey',{index:'0'});ok('S.account.keys[0].state.includes("Revogada")','Revogar referência BYOK');
action('addMember');elem('memberName').value='Pessoa';elem('memberEmail').value='pessoa@exemplo.test';elem('memberRole').value='Reviewer';elem('confirmModal').onclick();ok('S.account.members.length===2&&S.account.members[1].role==="Reviewer"','Adicionar membro e papel local');
action('connectYoutube');elem('confirmModal').onclick();ok('channel().demoConnected===true','Vínculo YouTube fictício separado do canal');
run("openVideo('rome')");action('videoTab',{tab:'content'});action('addSource');elem('sourceTitle').value='Fonte local';elem('sourceType').value='Texto';elem('sourceText').value='Trecho para revisão';elem('confirmModal').onclick();ok('video().sources.length===2','Adicionar fonte ao vídeo');action('removeSource',{index:'1'});ok('video().sources.length===1','Remover fonte');
change('video','resolution','720p');ok('video().config.resolution==="720p"&&channel().settings.resolution==="1080p"','Override do vídeo não altera canal');ok('video().revision===2&&video().renderRevision===1','Override invalida render sem gerar');
action('videoTab',{tab:'edit'});elem('sceneText').value='Uma edição de cena';submit('sceneForm');ok('scene().text==="Uma edição de cena"&&video().approvedRevision===null','Edição de cena preservada');
action('voiceGenerate');elem('confirmModal').onclick();ok('video().voiceVersion===video().revision','Narração simulada por revisão');
action('generate');elem('genConsent').checked=true;elem('confirmModal').onclick();ok('video().renderRevision===video().revision','Composição simulada da revisão atual');
action('approve');ok('video().approvedRevision===null','QA pendente bloqueia aprovação');action('qaCheck');action('approve');ok('video().approvedRevision===video().revision&&!video().published','QA e aprovação distintos da publicação');
elem('pubTitle').value='Título final';elem('description').value='Texto';elem('privacy').value='Privado';action('publish');elem('confirmModal').onclick();run('var pubVersion=video().published.revision');ok('video().published.title==="Título final"','Publicação simulada guarda metadados');
action('media');elem('mediaChoice').value='Meus arquivos';elem('confirmModal').onclick();ok('video().published.revision===pubVersion&&video().revision>pubVersion','Edição não altera publicação histórica');
action('pause');ok('video().localStatus.includes("Pausado")','Pausar produção demo');action('resume');ok('video().localStatus.includes("Retomado")','Retomar produção demo');action('cancel');elem('confirmModal').onclick();ok('video().localStatus.includes("Cancelado")&&video().scenes.length===3','Cancelar mantém cenas');
action('setting',{tab:'channels'});action('selectConfigChannel',{id:'space'});action('nav',{route:'videos'});ok('!document.getElementById("app").innerHTML.includes("Por que Roma caiu?")','Isolamento visual de canais');
action('useIdea',{title:'Ideia demonstrativa'});ok('S.route==="new"&&S.idea==="Ideia demonstrativa"','Ideia preenche criação');
elem('topic').value='Meu roteiro';elem('script').value='Texto fornecido.\n\nSegundo trecho.';elem('format').value='short';elem('duration').value='60';elem('reviewScript').checked=true;submit('newForm');ok('video().sources.length===0&&video().scenes[0].text==="Texto fornecido."&&video().channel==="space"','Novo vídeo preserva roteiro e exige fontes próprias');
action('generate');ok('document.getElementById("message").textContent.includes("fontes")','Geração sem fonte bloqueada na demo');
action('addChannel');elem('newChannelName').value='Terceiro canal';elem('confirmModal').onclick();ok('channel().settings.resolution==="1080p"','Novo canal recebe configurações completas');
change('account','theme','Claro');ok('document.documentElement.style.colorScheme==="light"','Tema claro aplica preferência');
action('libraryTab',{tab:'styles'});action('applyStyle',{style:'Minimalista'});ok('channel().style==="Minimalista"','Biblioteca aplica estilo ao canal');
ok('JSON.parse(localStorage.getItem(KEY)).account.members.length===2','Persistência local inclui equipe e configurações');
const result={method:'Node VM com DOM mínimo; não valida layout/navegador',passed:checks.length,checks};console.log(JSON.stringify(result,null,2));fs.writeFileSync(path.join(__dirname,'prototype-test-results.json'),JSON.stringify(result,null,2));
