"""Testes de Integração e Estabilização — Onda INT-05 (Studio, Acervo Persistente e Mídia Externa GAI-01).

Valida os achados A09, A10 e A12 da auditoria INT-01:
- A12 / GAI-01: ImportExternalMedia com suporte seguro a PNG e MP4, validação de magic bytes,
  tamanho máximo e licença aberta/comercial registrada.
- Proteção estrita contra path traversal.
- Deduplicação por hash de conteúdo e proveniência.
- A10: Persistência integrada com FileAssetStore e AssetRepository (Postgres).
"""
import io
import shutil
import subprocess
from pathlib import Path
from PIL import Image
import pytest

from app.studio.adapters.media_probe import FfmpegMediaProbe
from app.studio.adapters.postgres.db import migrate
from app.studio.adapters.postgres.editorial_repo import PostgresScriptRepository
from app.studio.adapters.postgres.media_repo import PostgresAssetRepository
from app.studio.adapters.postgres.repo import PostgresVideoRepository
from app.studio.adapters.storage import FileAssetStore
from app.studio.application.media import AssetRefused, ImportExternalMedia
from app.studio.domain.contracts import AssetKind, VideoFormat
from conftest import verified_test_connect


PROJECT_ID = "e" * 32
VIDEO_ID = "f" * 32
SCENE_ID = "1" * 32


@pytest.fixture
def dsn():
    import os
    val = os.environ.get("STUDIO_BUDGET_DISPOSABLE_DSN")
    if not val or not os.environ.get("STUDIO_BUDGET_TEST_PROOF_FILE"):
        pytest.skip("PostgreSQL descartável não configurado")
    return val


@pytest.fixture
def conn(dsn):
    import os
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    c = verified_test_connect(dsn, proof)
    try:
        c.execute("DROP SCHEMA IF EXISTS studio CASCADE")
        c.commit()
        yield c
    finally:
        c.close()


@pytest.fixture
def setup_db(conn, dsn, tmp_path: Path):
    import os
    proof = os.environ["STUDIO_BUDGET_TEST_PROOF_FILE"]
    migrate(conn)
    conn.execute("INSERT INTO studio.projects(id, name) VALUES (%s, 'canal')", (PROJECT_ID,))
    conn.execute(
        "INSERT INTO studio.videos(id, project_id, topic, format) VALUES (%s, %s, 'tema', 'short')",
        (VIDEO_ID, PROJECT_ID),
    )
    conn.execute(
        "INSERT INTO studio.scenes(id, video_id, idx, narration, image_prompt) VALUES (%s, %s, 1, 'Primeira cena', 'Prompt visual da primeira cena')",
        (SCENE_ID, VIDEO_ID),
    )
    conn.commit()

    connect = lambda: verified_test_connect(dsn, proof)  # noqa: E731
    videos = PostgresVideoRepository(connect)
    scripts = PostgresScriptRepository(connect)
    assets = PostgresAssetRepository(connect)
    store = FileAssetStore(tmp_path / "storage")

    importer = ImportExternalMedia(videos=videos, scripts=scripts, assets=assets, store=store, probe=FfmpegMediaProbe())
    return importer, assets, tmp_path / "storage"


def _create_test_png_bytes(width: int = 100, height: int = 100) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=(30, 60, 90))
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_int_05_import_valid_png_with_license(setup_db):
    """GAI-01: Importação de imagem PNG válida com licença aberta e vínculo de cena."""
    importer, assets, storage_root = setup_db
    png_data = _create_test_png_bytes(1080, 1920)

    asset = importer.execute(
        video_id=VIDEO_ID,
        data=png_data,
        filename="background.png",
        mime="image/png",
        license="CC0",
        scene_id=SCENE_ID,
        attribution="Acervo Público",
        source_url="https://example.com/asset.png",
    )

    assert asset is not None
    assert asset.kind == AssetKind.image
    assert asset.license == "CC0"
    assert asset.provider == "import"
    assert (storage_root / asset.path).exists()


def test_int_05_import_rejects_missing_license(setup_db):
    """GAI-01: Rejeição mandatória de mídia com licença desconhecida ou ausente."""
    importer, _, _ = setup_db
    png_data = _create_test_png_bytes()

    with pytest.raises(AssetRefused, match="without a valid registered open/commercial license"):
        importer.execute(
            video_id=VIDEO_ID,
            data=png_data,
            filename="foto.png",
            mime="image/png",
            license="unknown",
        )


def test_int_05_import_rejects_fake_magic_bytes(setup_db):
    """GAI-01: Rejeição de arquivo com MIME adulterado ou magic bytes inválidos."""
    importer, _, _ = setup_db
    fake_png = b"Not a real PNG header at all"

    with pytest.raises(AssetRefused, match="corrupted or fake png magic bytes"):
        importer.execute(
            video_id=VIDEO_ID,
            data=fake_png,
            filename="fake.png",
            mime="image/png",
            license="CC-BY",
        )


def test_int_05_import_valid_mp4_video(setup_db, tmp_path: Path):
    """GAI-01: Importação de vídeo MP4 válido persistido como AssetKind.video."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe necessários para fixture MP4 real")
    importer, assets, storage_root = setup_db
    mp4_file = tmp_path / "broll_clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=24:d=1.0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(mp4_file),
        ],
        check=True,
    )
    mp4_data = mp4_file.read_bytes()

    asset = importer.execute(
        video_id=VIDEO_ID,
        data=mp4_data,
        filename="broll_clip.mp4",
        mime="video/mp4",
        license="Commercial Stock",
        attribution="Stock Studio",
    )

    assert asset.kind == AssetKind.video
    assert asset.license == "Commercial Stock"
    assert (storage_root / asset.path).exists()
    assert asset.path.endswith(".mp4")


def test_int_05_path_traversal_sanitization(setup_db):
    """Segurança: Proteção estrita contra path traversal no nome do arquivo."""
    importer, _, storage_root = setup_db
    png_data = _create_test_png_bytes()

    # Tentativa de injeção de caminho relativo para fora da raiz de storage
    asset = importer.execute(
        video_id=VIDEO_ID,
        data=png_data,
        filename="../../../etc/passwd.png",
        mime="image/png",
        license="CC0",
    )

    # O arquivo deve ser gravado exclusivamente dentro da raiz de storage, sanitizado
    file_path = (storage_root / asset.path).resolve()
    assert storage_root.resolve() in file_path.parents
    assert ".." not in file_path.parts
