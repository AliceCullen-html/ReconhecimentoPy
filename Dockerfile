# =====================================================================
# Imagem para deploy do front de teste no Hugging Face Spaces (Docker SDK).
# HF Spaces free: 2 vCPU / 16 GB — roda o pipeline com folga.
# Também serve para qualquer host que rode contêiner (Cloud Run, Fly, etc.).
# =====================================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg habilita o preview H.264 inline; sem libs de GUI (usamos opencv headless).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces executa como uid 1000; criamos o usuário e trabalhamos no HOME dele.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR /app

# Instala as dependências (torch CPU, ultralytics, opencv headless, flask, gunicorn).
COPY --chown=user deploy/requirements-render.txt ./requirements.txt
RUN pip install --user -r requirements.txt

# Pré-baixa os pesos YOLO na imagem → primeiro processamento não espera download.
RUN python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"

# Copia o código do projeto.
COPY --chown=user . /app

# Hardware do HF aguenta mais que o Render free: qualidade quase cheia.
# (Ajuste PROC_MAX_WIDTH/PROC_FRAME_STRIDE se quiser mais velocidade.)
ENV MAX_UPLOAD_MB=200 \
    PROC_MAX_WIDTH=1280 \
    PROC_FRAME_STRIDE=1 \
    OMP_NUM_THREADS=2

EXPOSE 7860

# HF Spaces (Docker) espera a app na porta 7860.
CMD ["gunicorn", "webapp.app:app", \
     "--bind", "0.0.0.0:7860", \
     "--workers", "1", "--worker-class", "gthread", "--threads", "4", \
     "--timeout", "1200"]
