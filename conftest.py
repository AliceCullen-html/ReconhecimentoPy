"""Configuração de teste: expõe ``src/`` no ``sys.path`` para os imports.

Decisão (mais simples): em vez de empacotar/instalar o projeto, adicionamos
``src/`` ao path para que ``import baia_vision`` funcione com ``pytest`` direto.
"""

import sys
from pathlib import Path

SRC = Path(__file__).parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
