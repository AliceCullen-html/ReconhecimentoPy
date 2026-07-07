"""Máquina de estados da operação de carga/descarga.

Estados: ``IDLE`` e ``ACTIVE``.

Transições (com histerese / debounce — requisito, não extra):
    * ``IDLE -> ACTIVE``: quando as condições de ``start_requires`` são
      verdadeiras por ``debounce_frames_start`` frames CONSECUTIVOS.
      Registra evento ``INICIO``.
    * ``ACTIVE -> IDLE``: quando ``end_when`` é verdadeiro por
      ``debounce_frames_end`` frames CONSECUTIVOS. Registra evento ``FIM``
      com a duração calculada.

O debounce evita que a detecção "pisque" e gere eventos falsos.

As condições são expressas como flags booleanas por frame, calculadas na
pipeline: ``truck_in_zone``, ``person_in_zone``, ``truck_absent``. A máquina
apenas consome essas flags — não sabe nada sobre YOLO ou geometria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class State(str, Enum):
    """Estados possíveis da operação."""

    IDLE = "IDLE"
    ACTIVE = "ACTIVE"


@dataclass
class Event:
    """Evento registrado pela máquina de estados.

    Attributes:
        timestamp_s: Momento no vídeo, em segundos.
        tipo: ``"INICIO"`` ou ``"FIM"``.
        descricao: Texto legível do evento.
        duracao_s: Duração da operação (apenas em eventos ``FIM``).
    """

    timestamp_s: float
    tipo: str
    descricao: str
    duracao_s: float | None = None

    def to_dict(self) -> dict:
        """Serializa o evento para JSON (omite ``duracao_s`` quando ausente)."""
        data: dict = {
            "timestamp_s": round(self.timestamp_s, 2),
            "tipo": self.tipo,
            "descricao": self.descricao,
        }
        if self.duracao_s is not None:
            data["duracao_s"] = round(self.duracao_s, 2)
        return data


# Flags que a pipeline calcula por frame e a máquina sabe interpretar.
# 'truck_absent' é derivada (NOT truck_in_zone) mas mantida nomeada para
# espelhar o vocabulário do config (end_when: "truck_absent").
_KNOWN_FLAGS = {"truck_in_zone", "person_in_zone", "truck_absent"}


@dataclass
class OperationStateMachine:
    """Máquina de estados IDLE/ACTIVE com debounce configurável.

    Attributes:
        start_requires: Flags que precisam ser todas verdadeiras para iniciar.
        end_when: Flag única que, sustentada, encerra a operação.
        debounce_frames_start: Frames consecutivos para confirmar início.
        debounce_frames_end: Frames consecutivos para confirmar fim.
    """

    start_requires: list[str]
    end_when: str
    debounce_frames_start: int
    debounce_frames_end: int

    state: State = State.IDLE
    events: list[Event] = field(default_factory=list)

    # --- estado interno de debounce/cronômetro ---
    _start_counter: int = 0
    _end_counter: int = 0
    _frame_inicio: int | None = None
    _ts_inicio: float | None = None

    @classmethod
    def from_config(cls, op_cfg: dict) -> "OperationStateMachine":
        """Constrói a máquina a partir do bloco ``operation`` do config."""
        return cls(
            start_requires=list(op_cfg.get("start_requires", [])),
            end_when=op_cfg.get("end_when", "truck_absent"),
            debounce_frames_start=int(op_cfg.get("debounce_frames_start", 15)),
            debounce_frames_end=int(op_cfg.get("debounce_frames_end", 30)),
        )

    @property
    def is_active(self) -> bool:
        """``True`` se a operação está em curso (estado ``ACTIVE``)."""
        return self.state is State.ACTIVE

    def elapsed_s(self, timestamp_s: float) -> float | None:
        """Cronômetro da operação em curso, ou ``None`` se ociosa.

        Args:
            timestamp_s: Timestamp atual do vídeo em segundos.

        Returns:
            Segundos decorridos desde o início, ou ``None`` se ``IDLE``.
        """
        if self._ts_inicio is None:
            return None
        return max(0.0, timestamp_s - self._ts_inicio)

    def update(
        self, flags: dict[str, bool], frame_idx: int, timestamp_s: float
    ) -> Event | None:
        """Avança a máquina um frame e devolve o evento gerado, se houver.

        Args:
            flags: Flags booleanas do frame (ver ``_KNOWN_FLAGS``).
            frame_idx: Índice do frame atual (0-based).
            timestamp_s: Timestamp do frame em segundos de vídeo.

        Returns:
            :class:`Event` recém-registrado (``INICIO``/``FIM``) ou ``None``.
        """
        if self.state is State.IDLE:
            return self._update_idle(flags, frame_idx, timestamp_s)
        return self._update_active(flags, timestamp_s)

    # ------------------------------------------------------------------ #
    # Transições internas
    # ------------------------------------------------------------------ #
    def _update_idle(
        self, flags: dict[str, bool], frame_idx: int, timestamp_s: float
    ) -> Event | None:
        start_ok = all(flags.get(name, False) for name in self.start_requires)

        if start_ok:
            self._start_counter += 1
        else:
            self._start_counter = 0  # histerese: exige consecutivos

        if self._start_counter >= self.debounce_frames_start:
            self.state = State.ACTIVE
            self._frame_inicio = frame_idx
            self._ts_inicio = timestamp_s
            self._start_counter = 0
            self._end_counter = 0
            event = Event(
                timestamp_s=timestamp_s,
                tipo="INICIO",
                descricao="Operação de carregamento iniciada",
            )
            self.events.append(event)
            return event
        return None

    def _update_active(
        self, flags: dict[str, bool], timestamp_s: float
    ) -> Event | None:
        end_ok = flags.get(self.end_when, False)

        if end_ok:
            self._end_counter += 1
        else:
            self._end_counter = 0  # histerese: exige consecutivos

        if self._end_counter >= self.debounce_frames_end:
            duracao = (
                timestamp_s - self._ts_inicio
                if self._ts_inicio is not None
                else 0.0
            )
            self.state = State.IDLE
            self._end_counter = 0
            self._start_counter = 0
            self._frame_inicio = None
            self._ts_inicio = None
            event = Event(
                timestamp_s=timestamp_s,
                tipo="FIM",
                descricao="Operação de carregamento finalizada",
                duracao_s=max(0.0, duracao),
            )
            self.events.append(event)
            return event
        return None
