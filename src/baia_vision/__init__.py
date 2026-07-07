"""baia_vision — POC de visão computacional para monitoramento de baia de carga.

Camadas (ver docs/ARQUITETURA.md):
    vídeo -> detector -> zonas -> máquina de estados -> alertas -> anotador -> saída

Toda a parametrização vive em ``config/config.yaml``; nada é hardcoded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

__all__ = ["load_config", "__version__"]

__version__ = "0.1.0"


def load_config(path: str | Path) -> dict[str, Any]:
    """Carrega e valida minimamente o arquivo de configuração YAML.

    Args:
        path: Caminho para o ``config.yaml``.

    Returns:
        Dicionário com as chaves de configuração (``model``, ``zone``,
        ``operation``, ``alerts``, ``output``).

    Raises:
        FileNotFoundError: Se o arquivo não existir.
        ValueError: Se faltar alguma seção obrigatória.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {path}")

    with path.open("r", encoding="utf-8") as fh:
        cfg: dict[str, Any] = yaml.safe_load(fh) or {}

    # Validação mínima: garantir presença das seções obrigatórias.
    # Decisão (mais simples): não usamos schema externo; apenas checagem de chaves.
    required = ("model", "zone", "operation", "output")
    missing = [key for key in required if key not in cfg]
    if missing:
        raise ValueError(
            f"Seções ausentes no config: {', '.join(missing)}. "
            "Veja config/config.yaml de exemplo."
        )

    # 'alerts' é opcional; normaliza para lista vazia se ausente.
    cfg.setdefault("alerts", [])
    return cfg
