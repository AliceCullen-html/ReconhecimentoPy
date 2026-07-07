#!/usr/bin/env python3
"""Entrypoint CLI da POC baia-vision-poc.

Exemplo::

    python scripts/run.py --input data/input/video.mp4 \\
                          --output data/output/ \\
                          --config config/config.yaml

Valida a entrada, roda a pipeline com barra de progresso simples e imprime,
ao final, uma tabela legível dos eventos + os caminhos das saídas geradas.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite rodar o script diretamente sem instalar o pacote: adiciona src/.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from baia_vision import load_config  # noqa: E402
from baia_vision.operation import Event  # noqa: E402
from baia_vision.pipeline import PipelineResult, run_pipeline  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Define e faz o parse dos argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        prog="baia-vision-poc",
        description=(
            "POC de visão computacional para baia de carga: detecta caminhão "
            "e pessoas, cronometra a operação e emite alertas."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Caminho do vídeo de entrada (.mp4).",
    )
    parser.add_argument(
        "--output", "-o", default="data/output/",
        help="Diretório para as saídas (vídeo anotado + events.json).",
    )
    parser.add_argument(
        "--config", "-c", default="config/config.yaml",
        help="Caminho do arquivo de configuração YAML.",
    )
    return parser.parse_args(argv)


def _progress_bar(current: int, total: int, width: int = 30) -> None:
    """Imprime uma barra de progresso simples in-place no stderr."""
    if total > 0:
        frac = min(1.0, current / total)
        filled = int(frac * width)
        bar = "#" * filled + "-" * (width - filled)
        msg = f"\r[{bar}] {current}/{total} frames ({frac * 100:5.1f}%)"
    else:
        msg = f"\rProcessando frame {current}..."
    print(msg, end="", file=sys.stderr, flush=True)


def _print_events_table(events: list[Event]) -> None:
    """Imprime uma tabela legível dos eventos de operação no console."""
    print("\n=== LOG DE EVENTOS ===")
    if not events:
        print("(nenhuma operação detectada)")
        return

    header = f"{'TEMPO(s)':>9}  {'TIPO':<7}  {'DURACAO(s)':>10}  DESCRICAO"
    print(header)
    print("-" * len(header))
    for ev in events:
        dur = f"{ev.duracao_s:.2f}" if ev.duracao_s is not None else "-"
        print(
            f"{ev.timestamp_s:>9.2f}  {ev.tipo:<7}  {dur:>10}  {ev.descricao}"
        )


def _print_summary(result: PipelineResult) -> None:
    """Imprime o resumo final: eventos + caminhos das saídas."""
    _print_events_table(result.events)

    print("\n=== SAÍDAS ===")
    print(f"Frames processados : {result.frames_processed}")
    print(f"FPS do vídeo       : {result.fps:.2f}")
    if result.video_path is not None:
        print(f"Vídeo anotado      : {result.video_path}")
    if result.events_json_path is not None:
        print(f"Log de eventos     : {result.events_json_path}")


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da CLI.

    Returns:
        Código de saída (0 = sucesso; 1 = erro tratado e amigável).
    """
    args = _parse_args(argv)

    input_path = Path(args.input)
    config_path = Path(args.config)

    # Validações amigáveis antes de carregar modelos pesados.
    if not input_path.exists():
        print(f"[erro] Vídeo de entrada não encontrado: {input_path}", file=sys.stderr)
        print("       Coloque um vídeo royalty-free em data/input/ (ver README).",
              file=sys.stderr)
        return 1
    if not config_path.exists():
        print(f"[erro] Config não encontrado: {config_path}", file=sys.stderr)
        return 1

    try:
        config = load_config(config_path)
    except (ValueError, OSError) as exc:
        print(f"[erro] Falha ao carregar config: {exc}", file=sys.stderr)
        return 1

    print(f"Processando '{input_path}' com config '{config_path}'...",
          file=sys.stderr)
    try:
        result = run_pipeline(
            input_path=input_path,
            output_dir=args.output,
            config=config,
            progress_cb=_progress_bar,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"\n[erro] {exc}", file=sys.stderr)
        return 1

    print(file=sys.stderr)  # quebra de linha após a barra de progresso
    _print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
