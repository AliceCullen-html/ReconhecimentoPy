"""Geometria da zona da baia.

Responsabilidades:
    * Converter o polígono de coordenadas fracionárias (0..1) para pixels.
    * Testar se um ponto (ex.: base de uma caixa de detecção) está dentro
      do polígono da zona.
    * Fornecer o polígono em pixels para o anotador desenhar.

Nada aqui depende de YOLO/OpenCV além de numpy — geometria pura e testável.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Point = tuple[float, float]


def frac_polygon_to_pixels(
    polygon_frac: list[Point], width: int, height: int
) -> np.ndarray:
    """Converte polígono fracionário (0..1) para coordenadas em pixels.

    Args:
        polygon_frac: Lista de vértices ``[x, y]`` em fração da largura/altura.
        width: Largura do frame em pixels.
        height: Altura do frame em pixels.

    Returns:
        Array ``(N, 2)`` de inteiros com os vértices em pixels.

    Raises:
        ValueError: Se o polígono tiver menos de 3 vértices.
    """
    if len(polygon_frac) < 3:
        raise ValueError("Um polígono precisa de ao menos 3 vértices.")

    pts = np.array(
        [[fx * width, fy * height] for fx, fy in polygon_frac],
        dtype=np.float64,
    )
    return np.round(pts).astype(np.int32)


def point_in_polygon(point: Point, polygon: np.ndarray) -> bool:
    """Testa se ``point`` está dentro de ``polygon`` (ray casting).

    Implementação própria (algoritmo par-ímpar / crossing number) para manter
    a geometria testável sem depender do OpenCV. Pontos exatamente sobre a
    aresta podem cair para qualquer lado — comportamento aceitável para a POC.

    Args:
        point: Ponto ``(x, y)`` em pixels.
        polygon: Array ``(N, 2)`` com os vértices do polígono em pixels.

    Returns:
        ``True`` se o ponto estiver dentro do polígono, senão ``False``.
    """
    x, y = point
    poly = np.asarray(polygon, dtype=np.float64)
    n = len(poly)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        # A aresta (i, j) cruza a horizontal em y?
        intersects = (yi > y) != (yj > y)
        if intersects:
            # x da interseção da aresta com a linha horizontal em y.
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i

    return inside


@dataclass
class Zone:
    """Zona da baia: nome + polígono, com o polígono já resolvido em pixels.

    Use :meth:`from_config` para construir a partir do bloco ``zone`` do YAML
    e das dimensões do vídeo.

    Attributes:
        name: Rótulo exibido no HUD (ex.: ``"BAIA 01"``).
        polygon_px: Vértices em pixels, array ``(N, 2)``.
    """

    name: str
    polygon_px: np.ndarray

    @classmethod
    def from_config(
        cls, zone_cfg: dict, width: int, height: int
    ) -> "Zone":
        """Cria uma :class:`Zone` a partir da config e do tamanho do frame.

        Args:
            zone_cfg: Bloco ``zone`` do config (``name`` e ``polygon``).
            width: Largura do frame em pixels.
            height: Altura do frame em pixels.

        Returns:
            Instância de :class:`Zone` com polígono em pixels.
        """
        name = zone_cfg.get("name", "ZONA")
        polygon_frac = zone_cfg["polygon"]
        polygon_px = frac_polygon_to_pixels(polygon_frac, width, height)
        return cls(name=name, polygon_px=polygon_px)

    def contains(self, point: Point) -> bool:
        """Retorna ``True`` se ``point`` (em pixels) estiver dentro da zona."""
        return point_in_polygon(point, self.polygon_px)
