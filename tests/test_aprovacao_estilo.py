"""O formulário "Decisão de aprovação" (prévia e aba Publicação) usa só estilos que o design system define.

Bug: `<input>` sem `type` não casa com `input[type=text]` do CSS (ficava cinza do navegador), os controles
levavam a classe `.campo` (que é o contêiner do rótulo) e "Rejeitar" usava `btn-danger`, que o CSS v3 não tem.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "renderer"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_video_workspace import _preview  # noqa: E402

from app.studio.api import approval_form  # noqa: E402
from app.studio.api.shell_v3_css import V3_CSS  # noqa: E402


def _form() -> str:
    return approval_form.render_approval_decision(_preview(), bare=True)


def test_every_text_input_declares_its_type_so_the_theme_styles_it():
    inputs = re.findall(r"<input\b[^>]*>", _form())
    assert inputs and all(re.search(r'\btype="(text|datetime-local)"', tag) for tag in inputs), inputs


def test_controls_do_not_reuse_the_field_wrapper_class():
    controls = re.findall(r"<(?:input|textarea)\b[^>]*>", _form())
    assert controls and not [tag for tag in controls if 'class="campo"' in tag]


def test_every_button_class_used_by_the_form_exists_in_the_v3_theme():
    for tag in re.findall(r"<button\b[^>]*>", _form()):
        classes = re.search(r'class="([^"]+)"', tag).group(1).split()
        assert any(f".{name}" in V3_CSS for name in classes if name != "btn"), tag
    assert ".btn-danger" in V3_CSS and ".acoes" in V3_CSS
