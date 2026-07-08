#!/usr/bin/env python3
"""Front de teste (opcional) da POC baia-vision-poc.

NÃO faz parte do núcleo da POC — o pipeline continua rodável por CLI
(``scripts/run.py``). Esta é uma camada web mínima (Flask) para *testar* o
sistema pelo navegador: sobe-se um vídeo, roda-se o pipeline e veem-se os
resultados (tabela de eventos + vídeo anotado + events.json).

Decisões (mais simples):
    * Processamento **assíncrono** em uma thread de fundo, com página de
      progresso que consulta ``/status``. Isso evita que um request HTTP fique
      pendurado minutos (proxies/hosts derrubam com 502) — importante em hosts
      pequenos/lentos como o Render free.
    * Estado dos jobs vive em memória do processo (dict). Como o deploy usa 1
      worker, isso basta para a POC; reiniciou, perdeu os jobs (aceitável).
    * Reaproveita ``config/config.yaml`` do repo; parâmetros de custo podem ser
      sobrescritos por env (``PROC_MAX_WIDTH``, ``PROC_FRAME_STRIDE``).
    * Se ``ffmpeg`` existir, transcodifica o vídeo para H.264 (toca inline).

Uso::

    pip install -r webapp/requirements.txt
    python webapp/app.py            # abre em http://127.0.0.1:5000
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
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

# Registro de jobs em memória: job_id -> dict(status, progress, result/error...).
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _load_config_with_overrides() -> dict:
    """Carrega o config e aplica overrides de custo vindos de env.

    ``PROC_MAX_WIDTH`` e ``PROC_FRAME_STRIDE`` permitem apertar o custo no
    deploy (ex.: Render free) sem alterar o ``config.yaml`` versionado.
    """
    cfg = load_config(CONFIG_PATH)
    proc = dict(cfg.get("processing", {}) or {})
    if os.environ.get("PROC_MAX_WIDTH"):
        proc["max_width"] = int(os.environ["PROC_MAX_WIDTH"])
    if os.environ.get("PROC_FRAME_STRIDE"):
        proc["frame_stride"] = int(os.environ["PROC_FRAME_STRIDE"])
    cfg["processing"] = proc

    # Modelo/confiança também sobrescrevíveis por env — permite usar um modelo
    # mais forte (ex.: yolo11s.pt) no deploy sem mexer no config versionado.
    model = dict(cfg.get("model", {}))
    if os.environ.get("MODEL_WEIGHTS"):
        model["weights"] = os.environ["MODEL_WEIGHTS"]
    if os.environ.get("MODEL_CONF"):
        model["conf"] = float(os.environ["MODEL_CONF"])
    cfg["model"] = model
    return cfg


def _config_summary() -> dict:
    """Resumo do config ativo para exibir na página inicial."""
    cfg = _load_config_with_overrides()
    proc = cfg.get("processing", {})
    return {
        "model": cfg["model"].get("weights", "yolo11n.pt"),
        "conf": cfg["model"].get("conf", 0.35),
        "zone": cfg["zone"].get("name", "ZONA"),
        "alerts": [a.get("name") for a in cfg.get("alerts", [])],
        "max_width": proc.get("max_width", 0),
        "stride": proc.get("frame_stride", 1),
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


def _run_job(job_id: str, input_path: Path, out_dir: Path, config: dict) -> None:
    """Executa o pipeline em background e atualiza o estado do job.

    Roda em uma thread separada; comunica progresso e resultado via ``_JOBS``.
    Guarda apenas nomes de arquivo (as URLs são montadas na rota ``/result``,
    onde há contexto de request).
    """
    def progress_cb(current: int, total: int) -> None:
        with _JOBS_LOCK:
            _JOBS[job_id]["progress"] = {"current": current, "total": total}

    try:
        result = run_pipeline(input_path, out_dir, config, progress_cb=progress_cb)

        playable_name = None
        video_name = None
        if result.video_path is not None:
            video_name = result.video_path.name
            h264 = _maybe_transcode_h264(result.video_path)
            playable_name = (h264 or result.video_path).name

        payload = {
            "run_id": out_dir.name,
            "events": [e.to_dict() for e in result.events],
            "frames": result.frames_processed,
            "fps": round(result.fps, 2),
            "video_name": video_name,
            "playable_name": playable_name,
            "json_name": (
                result.events_json_path.name
                if result.events_json_path is not None
                else None
            ),
        }
        with _JOBS_LOCK:
            _JOBS[job_id].update(status="done", result=payload)
    except Exception as exc:  # noqa: BLE001 — reporta qualquer falha ao usuário
        with _JOBS_LOCK:
            _JOBS[job_id].update(status="error", error=str(exc))


@app.route("/", methods=["GET"])
def index():
    """Página inicial com o formulário de upload."""
    return render_template("index.html", cfg=_config_summary(), max_mb=_max_mb)


@app.route("/process", methods=["POST"])
def process():
    """Recebe o vídeo, dispara o job em background e redireciona ao progresso."""
    file = request.files.get("video")
    if file is None or file.filename == "":
        abort(400, "Nenhum arquivo enviado.")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        abort(400, f"Extensão não suportada: {ext}. Use {sorted(ALLOWED_EXT)}.")

    run_id = uuid.uuid4().hex[:12]
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = secure_filename(file.filename) or f"upload{ext}"
    input_path = UPLOAD_DIR / f"{run_id}_{safe_name}"
    file.save(str(input_path))

    out_dir = OUTPUT_DIR / run_id
    config = _load_config_with_overrides()

    job_id = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "status": "processing",
            "progress": {"current": 0, "total": 0},
            "original_name": file.filename,
        }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, input_path, out_dir, config),
        daemon=True,
    )
    thread.start()

    return redirect(url_for("job_page", job_id=job_id))


@app.route("/job/<job_id>", methods=["GET"])
def job_page(job_id: str):
    """Página de progresso; consulta ``/status`` até o job terminar."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        abort(404, "Job não encontrado (pode ter expirado após um restart).")
    return render_template(
        "job.html", job_id=job_id, original_name=job.get("original_name", "")
    )


@app.route("/status/<job_id>", methods=["GET"])
def job_status(job_id: str):
    """Estado do job em JSON, consumido pela página de progresso."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return jsonify({"status": "not_found"}), 404
        data = {"status": job["status"], "progress": job.get("progress", {})}
        if job["status"] == "done":
            data["result_url"] = url_for("result_page", job_id=job_id)
        elif job["status"] == "error":
            data["error"] = job.get("error", "erro desconhecido")
    return jsonify(data)


@app.route("/result/<job_id>", methods=["GET"])
def result_page(job_id: str):
    """Renderiza os resultados de um job concluído."""
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        abort(404, "Job não encontrado.")
    if job["status"] != "done":
        return redirect(url_for("job_page", job_id=job_id))

    res = job["result"]
    run_id = res["run_id"]
    inline_video = download_video = None
    if res["video_name"] is not None:
        inline_video = url_for(
            "output_file", run_id=run_id, filename=res["playable_name"]
        )
        download_video = url_for(
            "output_file", run_id=run_id, filename=res["video_name"]
        )
    json_url = (
        url_for("output_file", run_id=run_id, filename=res["json_name"])
        if res["json_name"] is not None
        else None
    )

    return render_template(
        "result.html",
        run_id=run_id,
        original_name=job.get("original_name", ""),
        events=res["events"],
        inline_video=inline_video,
        download_video=download_video,
        json_url=json_url,
        frames=res["frames"],
        fps=res["fps"],
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
    # use_reloader=False para não rodar o job em um processo que será reiniciado.
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
