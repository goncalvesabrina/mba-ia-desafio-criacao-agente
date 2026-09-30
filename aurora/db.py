"""Banco SQLite com o estado do condomínio (reservas, visitantes, sessões).

Os arquivos de dados/ são só o estado inicial: são lidos na restauração e
nunca são alterados. Tudo o que o assistente muda fica em var/condominio.db.
"""

import json
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from aurora import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS apartamentos (
    numero  TEXT PRIMARY KEY,
    morador TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS areas (
    id   TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    taxa REAL NOT NULL
);

-- Reservas canceladas nunca são apagadas: o codigo continua ocupando a
-- PRIMARY KEY e por isso nunca é reutilizado por uma reserva nova.
CREATE TABLE IF NOT EXISTS reservas (
    codigo      TEXT PRIMARY KEY,
    apartamento TEXT NOT NULL REFERENCES apartamentos(numero),
    area        TEXT NOT NULL REFERENCES areas(id),
    data        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'cancelada'))
);

-- Garantia 5: no máximo uma reserva ATIVA por área e data. O SQLite confere
-- o índice no próprio INSERT, então duas gravações simultâneas não passam.
CREATE UNIQUE INDEX IF NOT EXISTS ux_reserva_ativa_por_area_data
    ON reservas (area, data) WHERE status = 'ativa';

CREATE TABLE IF NOT EXISTS visitantes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    apartamento TEXT NOT NULL REFERENCES apartamentos(numero),
    nome        TEXT NOT NULL,
    data        TEXT NOT NULL
);

-- Dono de cada sessão: definido uma única vez, na criação.
CREATE TABLE IF NOT EXISTS sessoes (
    session_id  TEXT PRIMARY KEY,
    apartamento TEXT NOT NULL REFERENCES apartamentos(numero)
);
"""


def _connect() -> sqlite3.Connection:
    config.VAR_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.CONDOMINIO_DB, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def conexao() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transacao() -> Iterator[sqlite3.Connection]:
    """Transação de escrita: BEGIN IMMEDIATE pega o lock de escrita já no início."""
    with conexao() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")


def _ler_json(nome: str) -> list[dict]:
    return json.loads((config.DADOS_DIR / nome).read_text(encoding="utf-8"))


def restaurar() -> None:
    """Recria o banco do condomínio a partir dos arquivos de dados/."""
    config.VAR_DIR.mkdir(parents=True, exist_ok=True)
    for sufixo in ("", "-wal", "-shm"):
        caminho = config.CONDOMINIO_DB.with_name(config.CONDOMINIO_DB.name + sufixo)
        caminho.unlink(missing_ok=True)

    with conexao() as conn:
        conn.executescript(SCHEMA)
        conn.execute("BEGIN")
        conn.executemany(
            "INSERT INTO apartamentos (numero, morador) VALUES (:numero, :morador)",
            _ler_json("apartamentos.json"),
        )
        conn.executemany(
            "INSERT INTO areas (id, nome, taxa) VALUES (:id, :nome, :taxa)",
            _ler_json("areas.json"),
        )
        conn.executemany(
            "INSERT INTO reservas (codigo, apartamento, area, data)"
            " VALUES (:codigo, :apartamento, :area, :data)",
            _ler_json("reservas.json"),
        )
        conn.executemany(
            "INSERT INTO visitantes (apartamento, nome, data)"
            " VALUES (:apartamento, :nome, :data)",
            _ler_json("visitantes.json"),
        )
        conn.execute("COMMIT")


def inicializar() -> None:
    """Na subida da API: cria o banco a partir de dados/ só se ele não existir."""
    if not config.CONDOMINIO_DB.exists():
        restaurar()
    else:
        with conexao() as conn:
            conn.executescript(SCHEMA)
