#!/usr/bin/env python3
"""Front de teste (opcional) da POC baia-vision-poc.

NÃO faz parte do núcleo da POC — o pipeline continua rodável por CLI
(``scripts/run.py``). Esta é apenas uma camada web mínima (Flask) para
*testar* o sistema pelo navegador: sobe-se um vídeo, roda-se o pipeline e
veem-se os resultados (tabela de eventos + vídeo anotado + events.json).

Decisões (mais simples):
    * Flask puro, síncrono (o request espera o processamento) — suficiente
      para uma POC/demonstração; não é um serviço de produção.
    * Reaproveita ``config/config.yaml`` do repo; nada de config duplicada.
    * Se ``ffmpeg`` estiver disponível, transcodifica o vídeo anotado para
      H.264 (avc1) para tocar inline no navegador; senão, oferece download.

Uso::

    pip install -r webapp/requirements.txt
    python webapp/app.py            # abre em http://127.0.0.1:5000
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from flask import (
    Flask,
    abort,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

# Expõe src/ para importar o pacote sem instalar (mesma abordagem do CLI).
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from baia_vision import load_config  # noqa: E402
from baia_vision.pipeline import run_pipeline  # noqa: E402

CONFIG_PATH = ROOT / "config" / "config.yaml"
UPLOAD_DIR = ROOT / "data" / "input"
OUTPUT_DIR = ROOT / "data" / "output"
ALLOWED_EXT = {".mp4", ".avi", ".mov", ".mkv"}

app = Flask(__name__)
# Limite de upload configurável por env (MAX_UPLOAD_MB). Em deploys com pouca
# RAM (ex.: Render free, 512 MB) convém baixar isso para evitar OOM.
_max_mb = int(os.environ.get("MAX_UPLOAD_MB", "300"))
app.config["MAX_CONTENT_LENGTH"] = _max_mb * 1024 * 1024


def _config_summary() -> dict:
    """Resumo do config ativo para exibir na página inicial."""
    cfg = load_config(CONFIG_PATH)
    return {
        "model": cfg["model"].get("weights", "yolo11n.pt"),
        "conf": cfg["model"].get("conf", 0.35),
        "zone": cfg["zone"].get("name", "ZONA"),
        "alerts": [a.get("name") for a in cfg.get("alerts", [])],
    }


def _maybe_transcode_h264(src: Path) -> Path | None:
    """Transcodifica para H.264 (tocável inline) se ``ffmpeg`` existir.

    Args:
        src: Vídeo anotado gerado pelo pipeline (codec mp4v).

    Returns:
        Caminho do vídeo H.264, ou ``None`` se ffmpeg indisponível/falhar.
    """
    if shutil.which("ffmpeg") is None:
        return None
    dst = src.with_name("annotated_web.mp4")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(src),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", "-an", str(dst),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return dst
    except (subprocess.CalledProcessError, OSError):
        return None


@app.route("/", methods=["GET"])
def index():
    """Página inicial com o formulário de upload."""
    return render_template("index.html", cfg=_config_summary())


@app.route("/process", methods=["POST"])
def process():
    """Recebe o vídeo, roda o pipeline e renderiza os resultados."""
    file = request.files.get("video")
    if file is None or file.filename == "":
        abort(400, "Nenhum arquivo enviado.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        abort(400, f"Extensão não suportada: {ext}. Use {sorted(ALLOWED_EXT)}.")

    # ID de execução isola upload e saídas de cada teste.
    run_id = uuid.uuid4().hex[:12]
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = secure_filename(file.filename) or f"upload{ext}"
    input_path = UPLOAD_DIR / f"{run_id}_{safe_name}"
    file.save(str(input_path))

    out_dir = OUTPUT_DIR / run_id
    config = load_config(CONFIG_PATH)

    try:
        result = run_pipeline(input_path, out_dir, config)
    except (RuntimeError, FileNotFoundError) as exc:
        abort(400, f"Falha ao processar o vídeo: {exc}")

    # Vídeo para tocar inline: H.264 se possível, senão o mp4v original.
    inline_video = None
    download_video = None
    if result.video_path is not None:
        h264 = _maybe_transcode_h264(result.video_path)
        playable = h264 if h264 is not None else result.video_path
        inline_video = url_for("output_file", run_id=run_id, filename=playable.name)
        download_video = url_for(
            "output_file", run_id=run_id, filename=result.video_path.name
        )

    events = [e.to_dict() for e in result.events]
    json_url = (
        url_for("output_file", run_id=run_id, filename=result.events_json_path.name)
        if result.events_json_path is not None
        else None
    )

    return render_template(
        "result.html",
        run_id=run_id,
        original_name=file.filename,
        events=events,
        inline_video=inline_video,
        download_video=download_video,
        json_url=json_url,
        frames=result.frames_processed,
        fps=round(result.fps, 2),
    )


@app.route("/output/<run_id>/<path:filename>")
def output_file(run_id: str, filename: str):
    """Serve arquivos gerados (vídeo anotado, events.json) por execução."""
    directory = (OUTPUT_DIR / run_id).resolve()
    # Trava de segurança: impede path traversal para fora de data/output/.
    if not str(directory).startswith(str(OUTPUT_DIR.resolve())):
        abort(404)
    return send_from_directory(directory, filename)


if __name__ == "__main__":
    # host/port fixos e simples; debug ligado para uso local de teste.
    app.run(host="127.0.0.1", port=5000, debug=True)
