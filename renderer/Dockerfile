FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core curl ca-certificates && rm -rf /var/lib/apt/lists/*
# Voz de narração pt-BR (Piper "faber", dataset CC0). Integridade conferida por SHA-256.
ARG VOICE_BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium
RUN mkdir -p /opt/voices && cd /opt/voices \
 && curl -fsSL -o pt_BR-faber-medium.onnx "$VOICE_BASE/pt_BR-faber-medium.onnx" \
 && curl -fsSL -o pt_BR-faber-medium.onnx.json "$VOICE_BASE/pt_BR-faber-medium.onnx.json" \
 && printf '%s  %s\n%s  %s\n' \
    75e913eb463db0b6ac7ddf68d3e4c9ac19ace36dc3b710a81039b448352b8ffc pt_BR-faber-medium.onnx \
    6b6801319e5a70aa4d75c63343515f55d1cd671ecd1ac511586bc16216812261 pt_BR-faber-medium.onnx.json | sha256sum -c -
ENV PIPER_VOICE=/opt/voices/pt_BR-faber-medium.onnx
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
