"""Orquestração da POC: lê vídeo -> detecta -> regras -> anota -> escreve.

Fluxo por frame (ver docs/ARQUITETURA.md):
    1. Ler frame do vídeo.
    2. Detectar (YOLO + tracking) -> lista de :class:`Detection`.
    3. Resolver a zona em pixels (uma vez, no 1º frame).
    4. Calcular flags do frame (person/truck na zona, contagem).
    5. Atualizar a máquina de estados da operação (com debounce).
    6. Avaliar regras de alerta.
    7. Anotar o frame e escrever no vídeo de saída.
    8. Acumular eventos e escrever ``events.json`` ao final.

A pipeline é a única camada que conhece TODAS as outras — as demais são
isoladas e testáveis. Nenhum parâmetro de negócio é hardcoded: tudo vem do
``config`` recebido.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2

from . import annotator as ann
from .alerts import AlertEngine, FiredAlert
from .detector import Detection, Detector
from .operation import Event, OperationStateMachine
from .zones import Zone

# Índices COCO usados para classificar detecções nas flags de zona.
_PERSON_CLS = 0
_TRUCK_CLS = 7


@dataclass
class PipelineResult:
    """Resultado da execução da pipeline.

    Attributes:
        events: Eventos de operação registrados (INICIO/FIM).
        video_path: Caminho do vídeo anotado (``None`` se desabilitado).
        events_json_path: Caminho do ``events.json`` (``None`` se desabilitado).
        frames_processed: Total de frames processados.
        fps: FPS do vídeo de entrada.
    """

    events: list[Event] = field(default_factory=list)
    video_path: Path | None = None
    events_json_path: Path | None = None
    frames_processed: int = 0
    fps: float = 0.0


def _compute_zone_flags(
    detections: list[Detection], zone: Zone
) -> dict[str, object]:
    """Calcula as flags de zona a partir das detecções do frame.

    Usa o ``foot_point`` (base da caixa) para decidir presença na zona.

    Returns:
        Dicionário com ``person_in_zone``, ``truck_in_zone``,
        ``truck_absent`` e ``person_count``.
    """
    person_count = 0
    truck_in_zone = False

    for det in detections:
        if not zone.contains(det.foot_point):
            continue
        if det.cls_id == _PERSON_CLS:
            person_count += 1
        elif det.cls_id == _TRUCK_CLS:
            truck_in_zone = True

    person_in_zone = person_count > 0
    return {
        "person_in_zone": person_in_zone,
        "truck_in_zone": truck_in_zone,
        "truck_absent": not truck_in_zone,
        "person_count": person_count,
    }


def run_pipeline(
    input_path: str | Path,
    output_dir: str | Path,
    config: dict,
    progress_cb: Callable[[int, int], None] | None = None,
) -> PipelineResult:
    """Executa a pipeline completa sobre um vídeo.

    Args:
        input_path: Caminho do vídeo de entrada (.mp4).
        output_dir: Diretório onde salvar saídas.
        config: Configuração já carregada (ver :func:`baia_vision.load_config`).
        progress_cb: Callback opcional ``(frame_atual, total)`` para progresso.

    Returns:
        :class:`PipelineResult` com eventos e caminhos das saídas.

    Raises:
        FileNotFoundError: Se o vídeo de entrada não existir.
        RuntimeError: Se o vídeo não puder ser aberto pelo OpenCV.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    if not input_path.exists():
        raise FileNotFoundError(f"Vídeo de entrada não encontrado: {input_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Não foi possível abrir o vídeo: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    src_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    # --- Otimizações de custo (essenciais em hosts pequenos) ---
    # max_width: redimensiona o frame antes de detectar/anotar → corta RAM e CPU.
    # frame_stride: roda a detecção só a cada N frames e reaproveita as caixas
    #   nos frames intermediários (o vídeo/estado seguem quadro a quadro). O
    #   debounce continua em frames REAIS, então os tempos não mudam.
    proc_cfg = config.get("processing", {}) or {}
    max_width = int(proc_cfg.get("max_width", 0) or 0)
    frame_stride = max(1, int(proc_cfg.get("frame_stride", 1) or 1))

    if max_width and src_width > max_width:
        scale = max_width / src_width
        width = max_width
        height = int(round(src_height * scale))
    else:
        width, height = src_width, src_height

    # --- Instancia as camadas a partir da config ---
    model_cfg = config["model"]
    detector = Detector(
        weights=model_cfg.get("weights", "yolo11n.pt"),
        conf=model_cfg.get("conf", 0.35),
        classes=model_cfg.get("classes"),
    )
    zone = Zone.from_config(config["zone"], width, height)
    op_machine = OperationStateMachine.from_config(config["operation"])
    alert_engine = AlertEngine.from_config(config.get("alerts", []))

    out_cfg = config.get("output", {})
    write_video = bool(out_cfg.get("annotated_video", True))
    write_json = bool(out_cfg.get("events_json", True))

    writer = None
    video_path: Path | None = None
    if write_video:
        video_path = output_dir / "annotated.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))

    result = PipelineResult(video_path=video_path, fps=fps)

    frame_idx = 0
    last_detections: list[Detection] = []
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            # Redimensiona (uma vez) para a resolução de processamento.
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))

            timestamp_s = frame_idx / fps if fps else 0.0

            # Detecta só a cada `frame_stride` frames; reaproveita as últimas
            # caixas nos intermediários (economiza inferência/CPU).
            if frame_idx % frame_stride == 0:
                last_detections = detector.detect(frame)
            detections = last_detections

            zone_flags = _compute_zone_flags(detections, zone)
            op_machine.update(zone_flags, frame_idx, timestamp_s)

            # Flags para o motor de alertas (inclui operation_active).
            alert_flags: dict[str, object] = {
                **zone_flags,
                "operation_active": op_machine.is_active,
            }
            fired: list[FiredAlert] = alert_engine.evaluate(alert_flags)

            if writer is not None:
                ann.annotate(
                    frame,
                    detections,
                    zone,
                    op_machine.state,
                    op_machine.elapsed_s(timestamp_s),
                    fired,
                )
                writer.write(frame)

            frame_idx += 1
            if progress_cb is not None:
                progress_cb(frame_idx, total_frames)
    finally:
        cap.release()
        if writer is not None:
            writer.release()

    result.events = op_machine.events
    result.frames_processed = frame_idx

    if write_json:
        events_json_path = output_dir / "events.json"
        payload = {
            "video": input_path.name,
            "fps": round(fps, 3),
            "frames": frame_idx,
            "zone": config["zone"].get("name", "ZONA"),
            "events": [e.to_dict() for e in op_machine.events],
        }
        with events_json_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        result.events_json_path = events_json_path

    return result
