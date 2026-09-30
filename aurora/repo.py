"""Operações de domínio sobre o banco do condomínio.

Toda função que lê ou grava dados de um apartamento recebe o apartamento como
parâmetro e filtra por ele no SQL. Quem chama (as tools) passa sempre o
apartamento da sessão, nunca um valor vindo do modelo.
"""

import re
import secrets
import sqlite3
from datetime import date

from aurora import db

_DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ErroDeValidacao(ValueError):
    """Entrada inválida vinda da conversa (área inexistente, data mal formada...)."""


def validar_data(data: str) -> str:
    data = (data or "").strip()
    if not _DATA_RE.match(data):
        raise ErroDeValidacao("A data precisa estar no formato AAAA-MM-DD.")
    try:
        date.fromisoformat(data)
    except ValueError as exc:
        raise ErroDeValidacao(f"A data {data} não existe no calendário.") from exc
    return data


# ---------------------------------------------------------------- consultas


def apartamento_existe(numero: str) -> bool:
    with db.conexao() as conn:
        return conn.execute("SELECT 1 FROM apartamentos WHERE numero = ?", (numero,)).fetchone() is not None


def listar_areas() -> list[dict]:
    with db.conexao() as conn:
        rows = conn.execute("SELECT id, nome, taxa FROM areas ORDER BY nome").fetchall()
    return [dict(r) for r in rows]


def obter_area(area_id: str) -> dict:
    with db.conexao() as conn:
        row = conn.execute("SELECT id, nome, taxa FROM areas WHERE id = ?", ((area_id or "").strip(),)).fetchone()
    if row is None:
        ids = ", ".join(a["id"] for a in listar_areas())
        raise ErroDeValidacao(f"Área '{area_id}' não existe. Áreas válidas: {ids}.")
    return dict(row)


def data_ocupada(area_id: str, data: str) -> bool:
    """Diz só se a data está ocupada — nunca de quem é a reserva."""
    with db.conexao() as conn:
        row = conn.execute(
            "SELECT 1 FROM reservas WHERE area = ? AND data = ? AND status = 'ativa'",
            (area_id, data),
        ).fetchone()
    return row is not None


def reservas_do_apartamento(apartamento: str) -> list[dict]:
    with db.conexao() as conn:
        rows = conn.execute(
            "SELECT codigo, area, data FROM reservas"
            " WHERE apartamento = ? AND status = 'ativa' ORDER BY data, area",
            (apartamento,),
        ).fetchall()
    return [dict(r) for r in rows]


def visitantes_do_apartamento(apartamento: str) -> list[dict]:
    with db.conexao() as conn:
        rows = conn.execute(
            "SELECT nome, data FROM visitantes WHERE apartamento = ? ORDER BY data, id",
            (apartamento,),
        ).fetchall()
    return [dict(r) for r in rows]


# ----------------------------------------------------------------- gravações


def _novo_codigo() -> str:
    return f"RSV-{secrets.token_hex(3).upper()}"


def criar_reserva(apartamento: str, area_id: str, data: str) -> dict | None:
    """Grava a reserva. Devolve None se a área já estiver ocupada na data.

    A exclusividade é garantida pelo índice único parcial
    ux_reserva_ativa_por_area_data (ver db.py): se outra reserva ativa para a
    mesma área e data entrar antes, o INSERT falha com IntegrityError, mesmo
    que a conferência anterior tenha dito que a data estava livre.
    """
    for _ in range(10):
        codigo = _novo_codigo()
        try:
            with db.transacao() as conn:
                conn.execute(
                    "INSERT INTO reservas (codigo, apartamento, area, data, status)"
                    " VALUES (?, ?, ?, ?, 'ativa')",
                    (codigo, apartamento, area_id, data),
                )
            return {"codigo": codigo, "area": area_id, "data": data}
        except sqlite3.IntegrityError as exc:
            mensagem = str(exc)
            if "reservas.codigo" in mensagem:
                continue  # colisão de código (inclusive de reserva cancelada): tenta outro
            if "reservas.area" in mensagem or "reservas.data" in mensagem:
                return None  # área já reservada nesta data
            raise
    raise RuntimeError("Não foi possível gerar um código de reserva único.")


def cancelar_reserva(apartamento: str, area_id: str, data: str) -> dict | None:
    """Cancela a reserva ativa DO APARTAMENTO na área/data. None se ele não tiver."""
    with db.transacao() as conn:
        row = conn.execute(
            "SELECT codigo, area, data FROM reservas"
            " WHERE apartamento = ? AND area = ? AND data = ? AND status = 'ativa'",
            (apartamento, area_id, data),
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE reservas SET status = 'cancelada' WHERE codigo = ?", (row["codigo"],))
    return dict(row)


def autorizar_visitante(apartamento: str, nome: str, data: str) -> dict:
    with db.transacao() as conn:
        conn.execute(
            "INSERT INTO visitantes (apartamento, nome, data) VALUES (?, ?, ?)",
            (apartamento, nome, data),
        )
    return {"nome": nome, "data": data}


# ------------------------------------------------------------------ sessões


def registrar_sessao(session_id: str, apartamento: str) -> None:
    with db.transacao() as conn:
        conn.execute("INSERT INTO sessoes (session_id, apartamento) VALUES (?, ?)", (session_id, apartamento))


def apartamento_da_sessao(session_id: str) -> str | None:
    with db.conexao() as conn:
        row = conn.execute("SELECT apartamento FROM sessoes WHERE session_id = ?", (session_id,)).fetchone()
    return row["apartamento"] if row else None
