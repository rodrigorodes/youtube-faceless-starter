"""Contratos das portas de provider: o outro lado da fronteira de ``test_architecture.py``.

``test_architecture.py`` prova que o núcleo (``domain``/``application``) **não importa**
mídia nem SDK de provedor (pureza de imports). Falta a outra metade da fronteira:

* **Registro ⇒ porta:** toda implementação que a composição registra **satisfaz
  estruturalmente** o Protocol da sua porta (``TextModel``/``ImageModel``/``Voice``/
  ``Renderer``), checado com ``isinstance`` sobre Protocols ``@runtime_checkable``.
* **Registro ⇔ catálogo:** toda implementação do catálogo do painel (``F10-03``) tem um
  ``register(...)`` correspondente **e vice-versa**. Trava a forma estrutural do bug
  "config/painel mentindo": um provider que o painel anuncia (ou esconde) sem implementação
  correspondente. O defeito do ``PiperVoice`` — ``self.model`` decorativo, o painel prometia
  uma voz configurável que a síntese não honrava (corrigido em ``b067d4a``) — é o exemplar
  **semântico** da mesma classe: por isso o teste de extensibilidade abaixo também exige que
  a identidade ``name:model`` da porta chegue ao render.
* **Extensibilidade sem tocar o núcleo:** um provider novo entra pelo **mesmo**
  ``register()`` de produção, é resolvido pelo **mesmo** ``ProjectConfig.resolve`` +
  ``build`` e é consumido pela porta pelo fluxo real (``RunRender``), sem nenhuma
  alteração em ``domain/``/``application/``.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.studio.application.config import _REGISTRY, ProjectConfig, build, register  # noqa: E402
from app.studio.application.ports import (  # noqa: E402
    ImageModel,
    MediaSearch,
    OverlayVerifier,
    Renderer,
    SemanticChecker,
    TenantContext,
    TextModel,
    Voice,
)
from app.studio.domain.provider import ProviderStanding, capability_gaps  # noqa: E402
from app.studio.domain.quality import SemanticResult  # noqa: E402

pytest.importorskip("psycopg")
from app.studio.composition import Settings, Studio, _provider_implementations  # noqa: E402

# Porta de cada ``kind`` de provider. É o contrato que o registro precisa satisfazer.
PORTS = {"text": TextModel, "image": ImageModel, "voice": Voice, "renderer": Renderer,
         "search": MediaSearch}
DUMMY_MODEL = "dummy-model"
# Baseline explícito do produto: se o código e a expectativa divergirem juntos, o teste
# ainda pega — o catálogo não pode mudar por acidente, só por decisão documentada.
EXPECTED_CATALOG = {
    ("text", "opencode"), ("text", "demo"),
    ("image", "opencode"), ("image", "placeholder"), ("image", "stock"), ("image", "veo"),
    ("voice", "piper"),
    ("voice", "kokoro"),
    ("voice", "elevenlabs"),
    ("renderer", "ffmpeg"),
    ("search", "pexels"),
    ("search", "pixabay"),
}


@pytest.fixture(scope="module", autouse=True)
def registered_providers():
    """Executa os ``register(...)`` de produção (``Studio.__init__``), sem banco.

    A conexão do ``Studio`` é tardia: construir a raiz de composição com tokens dummy
    registra as implementações reais sem abrir Postgres. É a **mesma** chamada que a
    produção faz — o teste não duplica a lista de providers.
    """
    studio = Studio(Settings(bridge_token="test-bridge-token", pexels_key="test-pexels-key",
                             pixabay_key="test-pixabay-key",
                             storage_root=Path("/tmp/studio-port-contracts")))
    yield studio
    studio.shutdown()


# -- Registro ⇒ porta ---------------------------------------------------------


def test_every_registered_provider_satisfies_its_port(registered_providers):
    """Constrói cada ``(kind, name)`` registrado e checa o Protocol da porta estruturalmente.

    Sem isto, um ``register`` poderia apontar para uma classe que não implementa a porta
    (faltando ``speak``/``generate``/``complete``/``qa_inputs``) e o erro só apareceria em
    tempo de execução, no meio de um render/produção.
    """
    assert _REGISTRY, "a composição deveria registrar providers ao subir o Studio"
    for kind, name in sorted(_REGISTRY):
        impl = build(kind, f"{name}:{DUMMY_MODEL}")
        port = PORTS[kind]
        assert isinstance(impl, port), (
            f"{kind}:{name} → {type(impl).__name__} não satisfaz {port.__name__}")
        # A identidade que o catálogo/roteamento usam é a mesma do objeto construído.
        assert impl.name == name, f"{kind}:{name} construiu com name={impl.name!r}"


# -- Registro ⇔ catálogo (o invariante que pega "painel mentindo") -------------


def _drift(catalog: set, registry: set) -> tuple[set, set]:
    """Diferença nos **dois** sentidos: (anunciado sem implementação, implementado sem anúncio)."""
    return catalog - registry, registry - catalog


def test_catalog_and_registry_have_no_drift(registered_providers):
    """Toda implementação do catálogo está registrada, e todo registro está no catálogo.

    Trava a forma estrutural de "config/painel mentindo": um provider anunciado como
    AVAILABLE sem ``register`` correspondente (o painel promete o que não dá para construir) ou
    um ``register`` fora do catálogo (o provider existe mas é invisível na configuração).
    ``EXPECTED_CATALOG`` fixa o baseline do produto: mexer na lista de voz (por exemplo) passa
    a exigir a atualização deliberada do teste e do guia ``docs/21-extensao.md``.

    O defeito do ``PiperVoice`` (``self.model`` ignorado, ``b067d4a``) é o exemplar
    **semântico** desta classe — catálogo e registro existiam, mas o adaptador não honrava o
    modelo anunciado. Esta comparação **não** pega esse caso: quem o cobre é o teste de
    extensibilidade, ao afirmar que a identidade ``name:model`` da porta chega ao render
    (``voice_id == "fake:pt_BR-x"``), junto dos testes de comportamento do adaptador.
    """
    catalog = {(impl.kind.value, impl.name) for impl in _provider_implementations(Settings())}
    registry = set(_REGISTRY)

    announced_without_implementation, implemented_without_announcement = _drift(catalog, registry)
    assert announced_without_implementation == set(), (
        f"anunciado no catálogo mas não registrado: {sorted(announced_without_implementation)}")
    assert implemented_without_announcement == set(), (
        f"registrado mas ausente do catálogo: {sorted(implemented_without_announcement)}")
    assert catalog == EXPECTED_CATALOG, (
        f"o catálogo mudou; atualize a baseline e o guia docs/21-extensao.md: {sorted(catalog)}")


def test_the_drift_check_catches_both_directions():
    """Prova que a comparação é *load-bearing*: drift fabricado é detectado nos dois sentidos."""
    catalog = {("voice", "piper"), ("text", "demo")}
    registry = {("voice", "piper"), ("voice", "ghost")}
    announced_without, implemented_without = _drift(catalog, registry)
    assert announced_without == {("text", "demo")}  # no catálogo, sem register → painel mentiria
    assert implemented_without == {("voice", "ghost")}  # registrado, fora do catálogo → invisível


# -- Capabilities e origem declaradas no catálogo real (F06.T01) --------------


def test_every_registered_provider_declares_the_capability_of_its_port(registered_providers):
    """O catálogo real declara a capability que a porta exige (F06.T01).

    A política de roteamento só aceita cartão cuja capability declarada inclui a da porta;
    um adaptador novo que declare um conjunto divergente seria barrado em execução. Este teste
    pega isso no catálogo, antes do painel prometer o provider.
    """
    implementations = _provider_implementations(Settings())
    assert capability_gaps(implementations) == ()
    assert {impl.kind.value for impl in implementations} == set(PORTS)


def test_the_product_catalog_has_exactly_two_stand_ins(registered_providers):
    """Só ``text:demo`` e ``image:placeholder`` são stand-ins; o resto é produção.

    Baseline deliberada (como ``EXPECTED_CATALOG``): se um adaptador real for classificado
    como demo/placeholder — ou um novo stand-in entrar sem revisão — a política de produção
    mudaria em silêncio. Atualizar este teste é a decisão explícita.
    """
    stand_ins = {(impl.kind.value, impl.name)
                 for impl in _provider_implementations(Settings())
                 if impl.standing is not ProviderStanding.PRODUCTION}
    assert stand_ins == {("text", "demo"), ("image", "placeholder")}


# -- A fronteira continua barrando SDK no núcleo ------------------------------


def test_architecture_guard_still_bars_provider_sdks_from_the_core():
    """O núcleo pode ganhar providers novos, mas nunca um import de SDK de provedor.

    Cita ``elevenlabs`` (o SDK da voz de nuvem do exemplo do guia) em ``PROVIDER_SDKS`` e
    confirma que ``domain``/``application`` continuam limpos. É o que permite trocar a porta
    de voz por um provider de nuvem **sem** contaminar o núcleo puro do Render Plan.
    """
    from test_architecture import PROVIDER_SDKS, imports_of, violates

    assert "elevenlabs" in PROVIDER_SDKS
    for layer in ("domain", "application"):
        assert violates(imports_of(layer), tuple(PROVIDER_SDKS)) == set(), layer


# -- Extensibilidade sem tocar o núcleo ---------------------------------------


class _FakeVoice:
    """Adaptador de voz de teste: satisfaz a porta ``Voice`` pelo mesmo Protocol da produção."""

    name = "fake"

    def __init__(self, model: str):
        self.model = model
        self.spoken: list[tuple[str, str]] = []

    def speak(self, text: str, out_path: Path) -> float:
        self.spoken.append((text, str(out_path)))
        return 1.0


class _FakeJobs:
    def __init__(self, job):
        self.job, self.completed = job, False

    def get(self, job_id):
        return self.job

    def start(self, job_id):
        return True

    def alive(self, job_id):
        return True

    def complete(self, job_id, asset, qa):
        self.completed = True
        return True

    def fail(self, job_id, error):
        raise AssertionError(f"o render recusou o provider fake: {error}")


class _FakeFiles:
    def __init__(self, work):
        self.work = work

    def image_path(self, relative):
        return Path("/tmp") / relative

    def work_dir(self, project_id, video_id, job_id):
        return self.work

    def publish(self, project_id, video_id, job_id, mp4, srt):
        return "final-1.mp4"

    def prune(self, project_id, video_id, keep):
        pass

    def cleanup(self, work):
        pass


class _FakeAssets:
    def __init__(self, asset):
        self.asset, self.added = asset, []

    def get(self, asset_id):
        return self.asset

    def add(self, asset):
        self.added.append(asset)
        return asset


class _FakeScripts:
    def __init__(self, scenes):
        self._scenes = scenes

    def scenes(self, video_id):
        return self._scenes


class _FakeVideos:
    def __init__(self, video):
        self.video = video

    def get_video(self, video_id):
        return self.video


class _FakeRenderer:
    name = "ffmpeg"

    def __init__(self):
        self.spec = None

    def render(self, spec, out_path):
        self.spec = spec
        return out_path

    def qa_inputs(self, spec):
        return SimpleNamespace(plan=None, descriptors=())


class _FakeQuality:
    def evaluate(self, plan, *, media_path, narration_path=None, descriptors=(), render_id, checksum):
        return object()


def test_a_new_provider_enters_through_the_same_seams_without_touching_the_core(tmp_path):
    """Um provider novo entra pelo ``register`` de produção e o fluxo real o consome.

    Prova de que a fronteira é **extensível**: nenhuma alteração em ``domain/`` ou
    ``application/`` — o adaptador é registrado pelo mesmo ``register()`` que a composição
    usa, resolvido pelo mesmo ``ProjectConfig.resolve`` + ``build`` do ``Studio``, e o
    ``RunRender`` (núcleo) o consome pela porta ``Voice``. O ``voice_id`` que chega ao
    renderer é ``fake:pt_BR-x``: é a identidade ``name:model`` que o ``RunRender`` deriva do
    objeto da porta (a mesma que o ``PiperVoice`` ignorava ao não honrar ``self.model``).
    """
    from app.studio.application.render import RunRender
    from app.studio.domain.contracts import (Asset, AssetKind, RenderJob, Scene, Video,
                                             VideoFormat, VideoStatus)

    register("voice", "fake", _FakeVoice)
    try:
        config = ProjectConfig.resolve(overrides={"voice": "fake:pt_BR-x"}, env={})
        voice = build("voice", config.voice)
        assert isinstance(voice, Voice), "o provider fake satisfaz a porta Voice"

        video = Video(id="v" * 32, project_id="p" * 32, topic="tema de teste",
                      format=VideoFormat.short, status=VideoStatus.ASSETS_READY)
        asset = Asset(id="a" * 32, kind=AssetKind.image, cache_key="img" * 8,
                      path="images/x.png", provider="placeholder", model="m", license="CC0-1.0")
        scene = Scene(id="s" * 32, video_id="v" * 32, idx=0, narration="Uma frase falada de teste.",
                      caption="c", label="FATO", image_prompt="abstract colorful light trails",
                      asset_id="a" * 32)
        jobs = _FakeJobs(RenderJob(id="job-1", video_id="v" * 32, input_hash="h" * 8))
        renderer = _FakeRenderer()
        run = RunRender(_FakeVideos(video), _FakeScripts([scene]), _FakeAssets(asset), jobs,
                        _FakeFiles(tmp_path), voice_for=lambda project_id: voice,
                        renderer_for=lambda project_id: renderer, quality=_FakeQuality())

        run.execute("job-1")

        assert voice.spoken == [("Uma frase falada de teste.", str(tmp_path / "speech_000.wav"))]
        assert jobs.completed, "o fluxo real (RunRender) não recusou o provider registrado"
        assert renderer.spec.voice_id == "fake:pt_BR-x", "a identidade da porta não chegou ao render"
    finally:
        _REGISTRY.pop(("voice", "fake"), None)  # não polui o teste de drift nem o resto da suíte


# -- Limite honesto da checagem estrutural ------------------------------------


def test_runtime_checkable_proves_member_presence_not_signatures():
    """O que ``isinstance`` **não** prova: a assinatura dos métodos.

    ``@runtime_checkable`` checa só a presença dos membros (``hasattr``), não a aridade nem
    os tipos. É o suficiente para pegar "faltou implementar a porta"; não substitui o
    consumidor que de fato chama a porta (o ``RunRender`` acima) nem os testes de
    comportamento de cada adaptador.
    """

    class WrongArity:
        name = "fake"

        def speak(self):  # a porta exige (text, out_path) -> float
            return 0.0

    assert isinstance(WrongArity(), Voice)  # presença basta: a assinatura não é checada aqui


# -- Portas S6 declaradas antes do adaptador (VE-05/ISO) ----------------------


class _FakeSemanticChecker:
    """Satisfaz ``SemanticChecker`` sem provedor: declara ``not_verified`` honestamente."""

    name = "fake"

    def check(self, plan, *, media_path, narration_path=None, descriptors=()):
        return SemanticResult(verdict="not_verified", reason="fake provider absent")


class _FakeOverlayVerifier:
    """Satisfaz ``OverlayVerifier`` sem tocar mídia (o adaptador real usa ffprobe/ffmpeg)."""

    name = "fake"

    def verify(self, plan, *, media_path, descriptors=()):
        return ()


class _FakeTenantContext:
    """Satisfaz ``TenantContext`` com o mínimo de identidade de tenant."""

    tenant_id = "tenant-test"
    organization_id = "org-test"

    def require_organization_id(self):
        return self.organization_id


def test_s6_semantic_checker_port_is_declared_and_satisfiable():
    from app.studio.adapters.quality_semantic import NotVerifiedSemanticChecker

    assert isinstance(_FakeSemanticChecker(), SemanticChecker)
    assert isinstance(NotVerifiedSemanticChecker(), SemanticChecker)
    result = NotVerifiedSemanticChecker().check(
        _fake_plan(), media_path=Path("/tmp/none.mp4"))
    assert result.verdict == "not_verified" and result.reason


def test_s6_overlay_verifier_port_is_declared_and_satisfiable():
    assert isinstance(_FakeOverlayVerifier(), OverlayVerifier)


def test_s6_tenant_context_port_is_declared_and_satisfiable():
    assert isinstance(_FakeTenantContext(), TenantContext)
    assert _FakeTenantContext().require_organization_id() == "org-test"

    class _NoScope:
        tenant_id = "tenant-test"
        organization_id = "org-test"

    assert not isinstance(_NoScope(), TenantContext)  # falta o escopo canônico


def _fake_plan():
    """Plano mínimo só para exercitar as portas S6 (sem persistência nem render)."""
    from app.studio.domain.contracts import VideoFormat
    from app.studio.domain.render_plan import AssetReference, StyleSnapshot
    from app.studio.domain.render_plan_builder import StoryboardScene, build_render_plan

    sha = "a" * 64
    return build_render_plan(
        plan_id="plan:port", revision=1, project_id="p", video_id="v", format=VideoFormat.short,
        scenes=[StoryboardScene(scene_id="scene0", asset_id="asset0",
                                narration="Narração do teste automatizado.", speech_seconds=2.2,
                                label="SELO")],
        assets=[AssetReference(asset_id="asset0", asset_version=1, uri="assets/0.png",
                               content_sha256=sha, media_type="image", license="CC0")],
        style_snapshot=StyleSnapshot(style_id="s", version=1),
    )
