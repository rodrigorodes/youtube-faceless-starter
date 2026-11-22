import sys
from playwright.sync_api import sync_playwright
import pathlib
P=(pathlib.Path(__file__).parent/"index.html").resolve().as_uri()
import os
OUT="/tmp/mockup-v4-shots/"; os.makedirs(OUT,exist_ok=True)
errs=[]
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1360,'height':860})
    pg.on('pageerror',lambda e:errs.append('PAGEERR '+str(e)))
    pg.on('console',lambda m:errs.append('CONSOLE '+m.text) if m.type=='error' else None)
    pg.goto(P)
    # all routes
    for h in ['home','new','videos','ideas','analytics','library','settings','video/v1/cenas','video/v1/composicao','video/v1/qualidade','video/v1/publicacao','video/v1/fontes','video/v1/producao','video/v4/producao']:
        pg.goto(P+'#/'+h); pg.wait_for_timeout(150)
        pg.screenshot(path=OUT+h.replace('/','_')+'.png')
    # QUICK journey
    pg.goto(P+'#/new'); pg.fill('#ntopic','A cidade perdida de Z')
    pg.click('[data-a=nmode][data-v=piloto]'); pg.click('[data-a=create]')
    pg.wait_for_selector('text=Piloto automático trabalhando'); pg.screenshot(path=OUT+'quick_progress.png')
    pg.wait_for_selector('text=Aprovar esta versão',timeout=15000)
    assert 'qualidade' in pg.url, pg.url
    pg.screenshot(path=OUT+'quick_qa.png')
    pg.click('[data-a=approve]'); pg.click('text=Ir para publicação →')
    pg.click('[data-a=publish]'); pg.wait_for_selector('text=Publicado agora')
    pg.screenshot(path=OUT+'quick_published.png')
    # DIRECTOR journey
    pg.goto(P+'#/new'); pg.fill('#ntopic','Os faróis esquecidos'); pg.click('[data-a=nmode][data-v=diretor]'); pg.click('[data-a=create]')
    pg.wait_for_selector('.scene'); n=pg.locator('.scene').count(); print('scenes',n)
    pg.fill('.scene >> nth=0 >> textarea','Texto editado pelo diretor para a primeira cena do vídeo.')
    pg.click('.scene >> nth=0 >> [data-a=broll]')
    pg.click('.scene >> nth=1 >> [data-a=media]'); pg.click('[data-a=pickmedia] >> nth=2')
    pg.screenshot(path=OUT+'dir_scenes.png')
    pg.click('text=Gerar o que falta e renderizar'); pg.wait_for_selector('text=Aprovar esta versão',timeout=15000)
    pg.screenshot(path=OUT+'dir_qa.png')
    # edit after render => blocks approval
    pg.click('text=Cenas & Storyboard'); pg.fill('.scene >> nth=0 >> textarea','Outra edição.')
    pg.click('button.tab:has-text("Qualidade")'); assert pg.locator('[data-a=approve]').is_disabled()
    # mobile
    pg.set_viewport_size({'width':390,'height':800}); pg.goto(P+'#/home'); pg.screenshot(path=OUT+'mobile_home.png')
    ov=pg.evaluate('document.documentElement.scrollWidth>innerWidth'); print('mobile overflow',ov)
    b.close()
print('ERRORS',errs)
