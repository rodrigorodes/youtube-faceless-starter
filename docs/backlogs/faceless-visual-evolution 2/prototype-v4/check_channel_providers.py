import os, pathlib
from playwright.sync_api import sync_playwright
P=(pathlib.Path(__file__).parent/"index.html").resolve().as_uri()
OUT2="/tmp/mockup-v4-shots/"; os.makedirs(OUT2,exist_ok=True)
errs=[]
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1360,'height':900})
    pg.on('pageerror',lambda e:errs.append('PAGEERR '+str(e)))
    pg.on('console',lambda m:errs.append('CONSOLE '+m.text) if m.type=='error' else None)
    pg.goto(P+'#/settings')
    for t in ['Canais','Marca & Editorial','Produção & Orçamento','Conexões & Equipe']:
        pg.click(f'button.tab:has-text("{t}")'); pg.wait_for_timeout(100); pg.screenshot(path=OUT2+'set_'+t[:4]+'.png',full_page=True)
    # providers: testar / configurar voz externa
    pg.click('[data-a=editprov][data-id=vc2]'); pg.fill('#mf4','voz-prod'); pg.click('[data-a=saveprov]')
    assert pg.locator('[data-a=testprov][data-id=vc2]').is_enabled()
    pg.click('[data-a=testprov][data-id=vc2]'); pg.wait_for_selector('text=Teste simulado: ok')
    # premium -> piloto bloqueado? (voz externa agora ok q88) 
    # wizard
    pg.select_option('#chsel','__new'); pg.wait_for_selector('text=Criar canal')
    pg.click('[data-a=wnext]'); assert 'Dê um nome' in pg.inner_text('#toast')
    pg.fill('#w1','Canal de Teste'); pg.fill('#w2','Finanças pessoais')
    pg.click('[data-a=wnext]'); pg.click('[data-a=wsuggest]'); pg.screenshot(path=OUT2+'wiz2.png')
    pg.click('[data-a=wnext]'); pg.click('[data-a=wset][data-k=style][data-v=st3]'); pg.screenshot(path=OUT2+'wiz3.png')
    pg.click('[data-a=wnext]'); pg.click('[data-a=wset][data-k=profile][data-v=premium]')
    pg.click('[data-a=wnext]'); pg.screenshot(path=OUT2+'wiz5.png',full_page=True)
    pg.click('[data-a=yt]'); pg.click('[data-a=ytauth]')
    pg.click('[data-a=wnext]'); pg.screenshot(path=OUT2+'wiz6.png')
    pg.click('[data-a=wcreate]'); pg.wait_for_selector('text=Primeiros passos do canal Canal de Teste')
    pg.screenshot(path=OUT2+'home_newch.png',full_page=True)
    assert pg.locator('#chsel option:checked').inner_text()=='Canal de Teste'
    # novo canal premium + provider ok => criar video piloto
    pg.click('nav >> text=Criar vídeo'); pg.fill('#ntopic','Teste de juros'); 
    print('create disabled?',pg.locator('[data-a=create]').is_disabled())
    b.close()
print('ERRORS',errs)
