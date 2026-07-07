"""Testes de geometria da zona (rodáveis com ``pytest``)."""

from __future__ import annotations

import numpy as np
import pytest

from baia_vision.zones import (
    Zone,
    frac_polygon_to_pixels,
    point_in_polygon,
)

# Quadrado 100x100 usado em vários testes.
SQUARE = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.int32)


def test_point_inside_square():
    assert point_in_polygon((50, 50), SQUARE) is True


def test_point_outside_square():
    assert point_in_polygon((150, 50), SQUARE) is False
    assert point_in_polygon((-10, 50), SQUARE) is False
    assert point_in_polygon((50, 200), SQUARE) is False


def test_point_inside_concave_polygon():
    # Polígono em "L" — testa que a concavidade é respeitada.
    l_shape = np.array(
        [[0, 0], [100, 0], [100, 40], [40, 40], [40, 100], [0, 100]],
        dtype=np.int32,
    )
    assert point_in_polygon((20, 80), l_shape) is True   # braço vertical do L
    assert point_in_polygon((80, 80), l_shape) is False  # canto recortado


def test_frac_polygon_to_pixels_basic():
    frac = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    px = frac_polygon_to_pixels(frac, width=640, height=480)
    expected = np.array([[0, 0], [640, 0], [640, 480], [0, 480]], dtype=np.int32)
    assert np.array_equal(px, expected)


def test_frac_polygon_to_pixels_fractional_values():
    frac = [[0.25, 0.5], [0.75, 0.5], [0.5, 1.0]]
    px = frac_polygon_to_pixels(frac, width=200, height=100)
    expected = np.array([[50, 50], [150, 50], [100, 100]], dtype=np.int32)
    assert np.array_equal(px, expected)


def test_frac_polygon_rejects_degenerate():
    with pytest.raises(ValueError):
        frac_polygon_to_pixels([[0.0, 0.0], [1.0, 1.0]], 100, 100)


def test_zone_from_config_and_contains():
    zone_cfg = {
        "name": "BAIA 01",
        "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    }
    zone = Zone.from_config(zone_cfg, width=100, height=100)
    assert zone.name == "BAIA 01"
    assert zone.contains((50, 50)) is True
    assert zone.contains((250, 250)) is False


def test_zone_contains_matches_fractional_region():
    # Zona ocupando o quadrante inferior-central; ponto na base de uma caixa.
    zone_cfg = {
        "name": "BAIA 01",
        "polygon": [[0.25, 0.45], [0.75, 0.45], [0.85, 0.95], [0.15, 0.95]],
    }
    zone = Zone.from_config(zone_cfg, width=1000, height=1000)
    assert zone.contains((500, 700)) is True    # centro da baia
    assert zone.contains((500, 100)) is False   # topo do frame, fora
    assert zone.contains((50, 500)) is False     # canto esquerdo, fora
