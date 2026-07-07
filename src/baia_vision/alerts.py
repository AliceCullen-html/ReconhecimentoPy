"""Avaliação de regras de alerta configuráveis.

Cada regra do config tem a forma::

    - name: "pessoa_em_zona_sem_operacao"
      description: "..."
      when: "person_in_zone AND NOT operation_active"
      severity: "warning"

O avaliador de ``when`` é MÍNIMO de propósito (decisão: não construir um parser
de expressões completo). Ele entende apenas:

    * operandos: flags booleanas nomeadas (ver ``SUPPORTED_FLAGS``);
    * operadores: ``AND``, ``OR``, ``NOT`` (case-insensitive);
    * sem parênteses; precedência fixa: ``NOT`` > ``AND`` > ``OR``.

Isso cobre as regras da POC. Flags desconhecidas geram ``ValueError`` para
falhar cedo em vez de silenciar um erro de digitação no YAML.

Flags suportadas (calculadas pela pipeline por frame):
    * ``person_in_zone``    — há ao menos uma pessoa dentro da zona.
    * ``truck_in_zone``     — há um caminhão dentro da zona.
    * ``operation_active``  — a máquina de estados está em ``ACTIVE``.
    * ``person_count``      — nº de pessoas na zona; em contexto booleano,
      ``> 0`` conta como verdadeiro.
"""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_FLAGS = {
    "person_in_zone",
    "truck_in_zone",
    "operation_active",
    "person_count",
}


def _as_bool(value: object) -> bool:
    """Coerção para booleano (``person_count`` inteiro -> ``> 0``)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    return bool(value)


def evaluate_when(expr: str, flags: dict[str, object]) -> bool:
    """Avalia uma expressão booleana mínima sobre flags nomeadas.

    Gramática suportada (precedência ``NOT`` > ``AND`` > ``OR``)::

        expr   := or_term (OR or_term)*
        or_term:= and_term (AND and_term)*
        and_term := [NOT] flag

    Args:
        expr: Expressão como ``"person_in_zone AND NOT operation_active"``.
        flags: Valores das flags nomeadas para o frame atual.

    Returns:
        Resultado booleano da expressão.

    Raises:
        ValueError: Se aparecer uma flag não suportada ou a sintaxe for
            inválida (ex.: ``NOT`` sem operando).
    """
    tokens = expr.replace("(", " ").replace(")", " ").split()
    if not tokens:
        return False

    # Split por OR (menor precedência).
    or_groups: list[list[str]] = [[]]
    for tok in tokens:
        if tok.upper() == "OR":
            or_groups.append([])
        else:
            or_groups[-1].append(tok)

    return any(_eval_and_group(group, flags) for group in or_groups)


def _eval_and_group(tokens: list[str], flags: dict[str, object]) -> bool:
    """Avalia um grupo separado por ``AND`` (com ``NOT`` unário opcional)."""
    # Split por AND.
    and_terms: list[list[str]] = [[]]
    for tok in tokens:
        if tok.upper() == "AND":
            and_terms.append([])
        else:
            and_terms[-1].append(tok)

    return all(_eval_term(term, flags) for term in and_terms)


def _eval_term(term_tokens: list[str], flags: dict[str, object]) -> bool:
    """Avalia um termo: ``[NOT] flag``."""
    negate = False
    idx = 0
    while idx < len(term_tokens) and term_tokens[idx].upper() == "NOT":
        negate = not negate
        idx += 1

    if idx >= len(term_tokens):
        raise ValueError(f"Termo inválido em expressão de alerta: {term_tokens!r}")

    flag_name = term_tokens[idx]
    if flag_name not in SUPPORTED_FLAGS:
        raise ValueError(
            f"Flag não suportada em regra de alerta: {flag_name!r}. "
            f"Suportadas: {sorted(SUPPORTED_FLAGS)}"
        )

    value = _as_bool(flags.get(flag_name, False))
    return (not value) if negate else value


@dataclass
class AlertRule:
    """Uma regra de alerta carregada do config.

    Attributes:
        name: Identificador curto da regra.
        description: Texto exibido quando o alerta dispara.
        when: Expressão booleana sobre flags nomeadas.
        severity: Nível (ex.: ``"warning"``, ``"critical"``).
    """

    name: str
    description: str
    when: str
    severity: str = "warning"

    @classmethod
    def from_config(cls, rule_cfg: dict) -> "AlertRule":
        """Cria uma :class:`AlertRule` a partir de um item da lista ``alerts``."""
        return cls(
            name=rule_cfg["name"],
            description=rule_cfg.get("description", rule_cfg["name"]),
            when=rule_cfg["when"],
            severity=rule_cfg.get("severity", "warning"),
        )

    def evaluate(self, flags: dict[str, object]) -> bool:
        """Retorna ``True`` se a regra dispara para as ``flags`` do frame."""
        return evaluate_when(self.when, flags)


@dataclass
class FiredAlert:
    """Alerta disparado em um frame (para HUD e/ou log)."""

    name: str
    description: str
    severity: str


class AlertEngine:
    """Avalia todas as regras configuradas contra as flags de cada frame."""

    def __init__(self, rules: list[AlertRule]) -> None:
        """Args: rules: Regras já parseadas do config."""
        self.rules = rules

    @classmethod
    def from_config(cls, alerts_cfg: list[dict]) -> "AlertEngine":
        """Cria o motor a partir da lista ``alerts`` do config."""
        return cls([AlertRule.from_config(r) for r in (alerts_cfg or [])])

    def evaluate(self, flags: dict[str, object]) -> list[FiredAlert]:
        """Devolve a lista de alertas que dispararam para o frame.

        Args:
            flags: Flags booleanas/numéricas do frame.

        Returns:
            Lista (possivelmente vazia) de :class:`FiredAlert`.
        """
        fired: list[FiredAlert] = []
        for rule in self.rules:
            if rule.evaluate(flags):
                fired.append(
                    FiredAlert(
                        name=rule.name,
                        description=rule.description,
                        severity=rule.severity,
                    )
                )
        return fired
