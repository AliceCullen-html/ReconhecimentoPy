"""Wrapper do YOLO (ultralytics).

Responsabilidades:
    * Carregar o modelo (pesos configuráveis).
    * Rodar inferência com tracking frame a frame.
    * Devolver detecções normalizadas (:class:`Detection`) para as camadas
      seguintes, isolando o resto do código da API do ultralytics.

Decisão (mais simples): o ``import ultralytics`` é feito de forma preguiçosa
(dentro do ``__init__``) para que o restante do pacote — e os testes de
geometria — possam ser importados sem torch/ultralytics instalados.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

# Nomes das classes COCO relevantes para a POC (index -> rótulo).
COCO_LABELS: dict[int, str] = {0: "person", 7: "truck"}


@dataclass
class Detection:
    """Uma detecção em um frame, já normalizada.

    Attributes:
        cls_id: Índice da classe COCO (0=person, 7=truck).
        label: Rótulo textual da classe.
        conf: Confiança da detecção (0..1).
        xyxy: Caixa ``(x1, y1, x2, y2)`` em pixels.
        track_id: ID de tracking (``None`` se o tracker não atribuiu).
    """

    cls_id: int
    label: str
    conf: float
    xyxy: tuple[float, float, float, float]
    track_id: int | None = None

    @property
    def foot_point(self) -> tuple[float, float]:
        """Ponto de contato com o solo: centro-x, base-y da caixa.

        Usado para decidir se o objeto está *dentro* da zona da baia (o pé da
        pessoa / base do caminhão é mais representativo que o centro da caixa).
        """
        x1, y1, x2, y2 = self.xyxy
        return ((x1 + x2) / 2.0, y2)


class Detector:
    """Carrega o modelo YOLO e roda detecção + tracking por frame."""

    def __init__(
        self,
        weights: str = "yolo11n.pt",
        conf: float = 0.35,
        classes: Iterable[int] | None = None,
    ) -> None:
        """Inicializa o detector.

        Args:
            weights: Caminho/nome dos pesos (baixados automaticamente pelo
                ultralytics se ausentes). Ex.: ``"yolo11n.pt"``.
            conf: Confiança mínima para manter uma detecção.
            classes: Índices COCO a manter (ex.: ``[0, 7]``). ``None`` = todas.
        """
        # Import preguiçoso: mantém o pacote importável sem ultralytics.
        from ultralytics import YOLO

        self.model = YOLO(weights)
        self.conf = conf
        self.classes = list(classes) if classes is not None else None

    def detect(self, frame: Any) -> list[Detection]:
        """Roda inferência + tracking em um frame BGR (numpy array).

        Usa ``model.track(persist=True)`` para manter IDs estáveis entre frames
        (tracker padrão do ultralytics, ByteTrack). Detecções abaixo de ``conf``
        ou fora de ``classes`` são descartadas pela própria chamada.

        Args:
            frame: Frame BGR (``numpy.ndarray``) como o OpenCV entrega.

        Returns:
            Lista de :class:`Detection` para o frame.
        """
        results = self.model.track(
            frame,
            persist=True,
            conf=self.conf,
            classes=self.classes,
            verbose=False,
        )

        detections: list[Detection] = []
        if not results:
            return detections

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or boxes.xyxy is None:
            return detections

        # Nomes do próprio modelo (fallback para COCO_LABELS).
        names = getattr(result, "names", None) or COCO_LABELS

        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        cls_ids = boxes.cls.cpu().numpy().astype(int)
        track_ids = (
            boxes.id.cpu().numpy().astype(int) if boxes.id is not None else None
        )

        for i in range(len(xyxy)):
            cls_id = int(cls_ids[i])
            label = names.get(cls_id, str(cls_id)) if isinstance(names, dict) else str(names[cls_id])
            detections.append(
                Detection(
                    cls_id=cls_id,
                    label=label,
                    conf=float(confs[i]),
                    xyxy=tuple(float(v) for v in xyxy[i]),
                    track_id=int(track_ids[i]) if track_ids is not None else None,
                )
            )

        return detections
