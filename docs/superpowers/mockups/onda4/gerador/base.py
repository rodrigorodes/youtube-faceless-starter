"""Renderiza as telas REAIS (sem JS) com dados de exemplo; base dos mockups fiéis."""
import re, sys
from types import SimpleNamespace
sys.path.insert(0, "/Users/rodrigomendes/youtube-faceless-starter.worktrees/ve-onda1-fundacao/renderer")
sys.path.insert(0, "/Users/rodrigomendes/youtube-faceless-starter.worktrees/ve-onda1-fundacao/tests")
from app.studio.api.panel_production import NewVideoView, PipelineStage
from app.studio.application.panel import CostBreakdown, MonthCost, VideoDetailView
from app.studio.domain.production_run import ProductionStage
from app.studio.api.panel_new_video import render_new_video_v3
from app.studio.api.panel_video_workspace import render_video_workspace
from app.studio.domain.contracts import Scene, Video, VideoFormat, VideoStatus
from app.studio.domain.panel import Stage

def strip(html):
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S)
    return html

def new_video():
    month = MonthCost(cap_usd=15.0, known_usd=2.4, unknown_calls=0, percent=16, text="US$ 2,40 de US$ 15,00",
                      breakdown=CostBreakdown())
    pipeline = tuple(PipelineStage(s, l, True) for s, l in [(ProductionStage.SCRIPT,"Roteiro"),(ProductionStage.RENDER,"Render")])
    v = NewVideoView(projects=[("p1","Mistérios do Mundo"),("p2","Tech News")], month=month, pipeline=pipeline,
        selected_project_id="p1", styles=(("s1","Documentário Sombrio"),("s2","Neon Tech")),
        inherited_style_name="Documentário Sombrio", channel_language="pt-BR", channel_voice="pt-BR · Fábio", has_profile=True)
    return strip(render_new_video_v3(v)[0])

def scenes():
    video = Video(id="v"*32, project_id="p"*32, topic="A cidade subterrânea de Derinkuyu", format=VideoFormat.short, status=VideoStatus.SCRIPTED)
    rows = [("Gancho","Sob o solo da Turquia existe um labirinto secreto capaz de abrigar vinte mil pessoas.","Túneis de pedra escuros iluminados por tochas.",6.5),
            ("Descoberta","Em 1963, um morador derrubou uma parede da casa e achou uma passagem que ninguém conhecia.","Parede de pedra desabando revelando uma passagem escura.",7.0),
            ("Engenharia","Poços de ventilação verticais desciam por dezoito andares e levavam ar fresco até o fundo.","Poço de ventilação vertical visto de cima.",6.0)]
    sc = [{"id":f"s{i+1}","idx":i,"narration":n,"caption":"c","label":l,"image_prompt":p,"duration_s":d,
           "asset_id":f"a{i}" if i<2 else None,"audio_state":"ok" if i<2 else "none"} for i,(l,n,p,d) in enumerate(rows)]
    return video, sc

class Script:
    version = 3
    scenes = ()

def workspace(area, status=VideoStatus.SCRIPTED):
    video, sc = scenes()
    video = video.model_copy(update={"status": status})
    html = render_video_workspace(video, area, script=Script(), scenes=sc, sources=[], projects=[("p1","Mistérios do Mundo")], project_id="p1",
                                  channel_name="Mistérios do Mundo", channel_voice="pt-BR · Fábio")[0]
    return strip(html)

if __name__ == "__main__":
    import pathlib
    out = pathlib.Path(__file__).parent
    (out/"nv.html").write_text(new_video())
    for a in ["cenas","composicao","qualidade"]:
        st = VideoStatus.RENDERED if a=="qualidade" else VideoStatus.SCRIPTED
        (out/f"ws_{a}.html").write_text(workspace(a, st))
    print("ok")
