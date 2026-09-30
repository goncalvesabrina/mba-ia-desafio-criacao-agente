"""Índice do regulamento por capítulo, lido de dados/regulamento.md."""

import re
from dataclasses import dataclass
from functools import cache

from aurora import config

_CAPITULO_RE = re.compile(r"^## Capítulo ([IVXLC]+): (.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Capitulo:
    numero: int
    romano: str
    titulo: str
    texto: str


def _romano_para_int(romano: str) -> int:
    valores = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    for atual, proximo in zip(romano, romano[1:] + " "):
        v = valores[atual]
        total += -v if valores.get(proximo, 0) > v else v
    return total


@cache
def capitulos() -> tuple[Capitulo, ...]:
    texto = (config.DADOS_DIR / "regulamento.md").read_text(encoding="utf-8")
    marcas = list(_CAPITULO_RE.finditer(texto))
    resultado = []
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        resultado.append(
            Capitulo(
                numero=_romano_para_int(m.group(1)),
                romano=m.group(1),
                titulo=m.group(2).strip(),
                texto=texto[m.start():fim].strip(),
            )
        )
    return tuple(resultado)


def sumario() -> list[dict]:
    return [{"numero": c.numero, "capitulo": c.romano, "titulo": c.titulo} for c in capitulos()]


def capitulo(numero: int) -> Capitulo | None:
    return next((c for c in capitulos() if c.numero == numero), None)
