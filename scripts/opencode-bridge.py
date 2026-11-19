#!/usr/bin/env python3
"""Bridge local: expõe geração de texto do OpenCode (login OAuth) ao renderer em Docker.

- Roda NO HOST (não no container), escuta só em 127.0.0.1.
- Usa endpoints stateless do OpenCode (generate/text e generate/image): sem agente, sem ferramentas, sem acesso a arquivos.
- Imagens: só modelos gratuitos (id terminado em ":free"), para nunca gerar custo, salvo OPENCODE_ALLOW_PAID_IMAGES=1.
- Os tokens OAuth ficam no OpenCode; este script nunca os lê.
- Exige Authorization: Bearer <OPENCODE_BRIDGE_TOKEN>.
Somente biblioteca padrão (Python 3.9+).
"""
import hmac
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_PROMPT = 4000
MAX_IMAGE_PROMPT = 800
DEFAULT_IMAGE_MODEL = "openrouter/recraft/recraft-v4.1-flash-v2:free"
TIMEOUT_SECONDS = 90
LOCK = threading.Semaphore(1)  # uma geração por vez (assinatura pessoal, sem fila)


def load_env():
    """Lê só as chaves OPENCODE_* do .env do projeto, sem sobrescrever o ambiente."""
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.startswith("OPENCODE_"):
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_model(ref):
    """'provider/model#variant' -> dict da API do OpenCode."""
    variant = None
    if "#" in ref:
        ref, variant = ref.split("#", 1)
    provider, _, model = ref.partition("/")
    if not provider or not model:
        raise ValueError("OPENCODE_MODEL deve ser provider/model[#variant]")
    out = {"providerID": provider, "id": model}
    if variant:
        out["variant"] = variant
    return out


def generate(prompt, model_ref, binary):
    body = json.dumps({"prompt": prompt, "model": parse_model(model_ref)})
    proc = subprocess.run([binary, "api", "post", "/api/experimental/generate/text", "-d", body],
                          capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    if proc.returncode != 0:
        raise RuntimeError("opencode api failed")
    return json.loads(proc.stdout)["data"]["text"]


def check_image_model(ref):
    """Recusa modelos de imagem que possam cobrar, a menos que liberado explicitamente."""
    parse_model(ref)
    if not ref.split("#", 1)[0].endswith(":free") and os.environ.get("OPENCODE_ALLOW_PAID_IMAGES") != "1":
        raise ValueError("OPENCODE_IMAGE_MODEL must be a ':free' model (set OPENCODE_ALLOW_PAID_IMAGES=1 to allow paid ones)")


def generate_image(prompt, model_ref, binary):
    body = json.dumps({"model": parse_model(model_ref), "prompt": prompt, "aspect": "9:16"})
    proc = subprocess.run([binary, "api", "post", "/api/experimental/generate/image", "-d", body],
                          capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    if proc.returncode != 0:
        raise RuntimeError("opencode api failed")
    image = json.loads(proc.stdout)["data"]["images"][0]
    return {"mime": image.get("mime", "image/png"), "data": image["data"]}


def make_handler(token, model_ref, binary, generate_fn=generate, image_model=DEFAULT_IMAGE_MODEL, image_fn=generate_image):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # sem log de prompt/cabeçalhos
            pass

        def reply(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            given = self.headers.get("Authorization", "")
            return hmac.compare_digest(given.encode(), f"Bearer {token}".encode())

        def do_GET(self):
            if self.path == "/health":
                return self.reply(200, {"status": "ok", "model": model_ref, "image_model": image_model})
            self.reply(404, {"detail": "not found"})

        def do_POST(self):
            if self.path not in ("/generate", "/image"):
                return self.reply(404, {"detail": "not found"})
            if not self.authorized():
                return self.reply(401, {"detail": "unauthorized"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 16384:
                    raise ValueError
                prompt = json.loads(self.rfile.read(length))["prompt"]
                limit = MAX_IMAGE_PROMPT if self.path == "/image" else MAX_PROMPT
                if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > limit:
                    raise ValueError
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                return self.reply(400, {"detail": "body must be JSON with 'prompt' (1-%d chars)" % (MAX_IMAGE_PROMPT if self.path == "/image" else MAX_PROMPT)})
            if not LOCK.acquire(blocking=False):
                return self.reply(429, {"detail": "busy: one generation at a time"})
            try:
                if self.path == "/image":
                    self.reply(200, image_fn(prompt, image_model, binary))
                else:
                    self.reply(200, {"text": generate_fn(prompt, model_ref, binary)})
            except subprocess.TimeoutExpired:
                self.reply(504, {"detail": "opencode timed out"})
            except Exception as exc:
                self.reply(502, {"detail": f"generation failed: {type(exc).__name__}"})
            finally:
                LOCK.release()

    return Handler


def main():
    load_env()
    token = os.environ.get("OPENCODE_BRIDGE_TOKEN", "").strip()
    if len(token) < 16:
        sys.exit("Defina OPENCODE_BRIDGE_TOKEN (>= 16 caracteres) no .env ou no ambiente.")
    model_ref = os.environ.get("OPENCODE_MODEL", "openai/gpt-6-luna")
    parse_model(model_ref)
    binary = shutil.which("opencode")
    if not binary:
        sys.exit("Comando 'opencode' não encontrado no PATH.")
    image_model = os.environ.get("OPENCODE_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)
    try:
        check_image_model(image_model)
    except ValueError as exc:
        sys.exit(str(exc))
    port = int(os.environ.get("OPENCODE_BRIDGE_PORT", "8787"))
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, model_ref, binary, image_model=image_model))
    print(f"opencode-bridge em http://127.0.0.1:{port} (texto: {model_ref}; imagem: {image_model}). Ctrl+C para parar.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
