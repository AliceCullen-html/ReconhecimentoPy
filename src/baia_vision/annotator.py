"""Desenho das anotações sobre o frame (OpenCV).

Responsabilidades:
    * Caixas coloridas por classe (person vs truck).
    * Polígono da zona, com cor dependente do estado (cinza=IDLE, verde=ACTIVE).
    * HUD no topo: nome da baia + status + cronômetro da operação.
    * Faixa de alerta quando alguma regra dispara.

Todas as cores/estilos são constantes locais desta camada de apresentação —
não são parâmetros de negócio, então não vão para o YAML.
"""

from __future__ import annotations

import cv2
import numpy as np

from .alerts import FiredAlert
from .detector import Detection
from .operation import State
from .zones import Zone

# Cores BGR (OpenCV). Camada de apresentação, não configuração de negócio.
_COLOR_PERSON = (0, 200, 255)   # amarelo-alaranjado
_COLOR_TRUCK = (255, 160, 0)    # azul
_COLOR_ZONE_IDLE = (150, 150, 150)   # cinza
_COLOR_ZONE_ACTIVE = (0, 200, 0)     # verde
_COLOR_HUD_BG = (0, 0, 0)
_COLOR_HUD_TEXT = (255, 255, 255)
_COLOR_ALERT = (0, 0, 255)      # vermelho
_FONT = cv2.FONT_HERSHEY_SIMPLEX


def _class_color(label: str) -> tuple[int, int, int]:
    """Escolhe a cor da caixa a partir do rótulo da classe."""
    if label == "truck":
        return _COLOR_TRUCK
    return _COLOR_PERSON


def draw_zone(frame: np.ndarray, zone: Zone, state: State) -> None:
    """Desenha o polígono da zona; cor depende do estado da operação.

    Args:
        frame: Frame BGR (modificado in-place).
        zone: Zona com polígono em pixels.
        state: Estado atual (``IDLE`` -> cinza, ``ACTIVE`` -> verde).
    """
    color = _COLOR_ZONE_ACTIVE if state is State.ACTIVE else _COLOR_ZONE_IDLE
    pts = zone.polygon_px.reshape((-1, 1, 2))

    # Preenchimento translúcido para dar volume à zona.
    overlay = frame.copy()
    cv2.fillPoly(overlay, [pts], color)
    cv2.addWeighted(overlay, 0.20, frame, 0.80, 0, frame)

    cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)


def draw_detections(frame: np.ndarray, detections: list[Detection]) -> None:
    """Desenha as caixas das detecções com rótulo/confiança/ID.

    Args:
        frame: Frame BGR (modificado in-place).
        detections: Detecções do frame.
    """
    for det in detections:
        x1, y1, x2, y2 = (int(v) for v in det.xyxy)
        color = _class_color(det.label)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        tag = f"{det.label} {det.conf:.2f}"
        if det.track_id is not None:
            tag += f" #{det.track_id}"

        (tw, th), _ = cv2.getTextSize(tag, _FONT, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            frame, tag, (x1 + 2, y1 - 4), _FONT, 0.5, (0, 0, 0), 1, cv2.LINE_AA
        )


def _format_timer(seconds: float | None) -> str:
    """Formata o cronômetro como ``MM:SS`` (``--:--`` se ocioso)."""
    if seconds is None:
        return "--:--"
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def draw_hud(
    frame: np.ndarray,
    zone_name: str,
    state: State,
    elapsed_s: float | None,
) -> None:
    """Desenha a barra de HUD no topo com nome, status e cronômetro.

    Args:
        frame: Frame BGR (modificado in-place).
        zone_name: Nome da baia (ex.: ``"BAIA 01"``).
        state: Estado atual da operação.
        elapsed_s: Cronômetro em segundos, ou ``None`` se ocioso.
    """
    h, w = frame.shape[:2]
    bar_h = 40
    cv2.rectangle(frame, (0, 0), (w, bar_h), _COLOR_HUD_BG, -1)

    status_color = (
        _COLOR_ZONE_ACTIVE if state is State.ACTIVE else _COLOR_ZONE_IDLE
    )
    text = (
        f"{zone_name}  |  STATUS: {state.value}  "
        f"|  OPERACAO: {_format_timer(elapsed_s)}"
    )
    cv2.putText(
        frame, text, (10, 27), _FONT, 0.6, _COLOR_HUD_TEXT, 1, cv2.LINE_AA
    )
    # Indicador colorido do estado à direita.
    cv2.circle(frame, (w - 20, bar_h // 2), 8, status_color, -1)


def draw_alerts(frame: np.ndarray, alerts: list[FiredAlert]) -> None:
    """Desenha uma faixa de alerta logo abaixo do HUD, se houver alertas.

    Args:
        frame: Frame BGR (modificado in-place).
        alerts: Alertas disparados no frame.
    """
    if not alerts:
        return

    h, w = frame.shape[:2]
    top = 40
    band_h = 30
    cv2.rectangle(frame, (0, top), (w, top + band_h), _COLOR_ALERT, -1)

    # Mostra o primeiro alerta (mais relevante); indica quantos mais existem.
    first = alerts[0]
    text = f"⚠ ALERTA: {first.description}"
    if len(alerts) > 1:
        text += f"  (+{len(alerts) - 1})"
    cv2.putText(
        frame, text, (10, top + 21), _FONT, 0.55, (255, 255, 255), 1, cv2.LINE_AA
    )


def annotate(
    frame: np.ndarray,
    detections: list[Detection],
    zone: Zone,
    state: State,
    elapsed_s: float | None,
    alerts: list[FiredAlert],
) -> np.ndarray:
    """Aplica toda a anotação sobre o frame e o devolve.

    Ordem de desenho: zona (fundo) -> caixas -> HUD -> faixa de alerta.

    Args:
        frame: Frame BGR de entrada.
        detections: Detecções do frame.
        zone: Zona da baia.
        state: Estado da operação.
        elapsed_s: Cronômetro da operação (ou ``None``).
        alerts: Alertas disparados no frame.

    Returns:
        O mesmo frame, anotado in-place (retornado por conveniência).
    """
    draw_zone(frame, zone, state)
    draw_detections(frame, detections)
    draw_hud(frame, zone.name, state, elapsed_s)
    draw_alerts(frame, alerts)
    return frame
