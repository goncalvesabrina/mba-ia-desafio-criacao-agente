"""Configuração: caminhos, modelos e variáveis de ambiente."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DADOS_DIR = ROOT / "dados"
VAR_DIR = ROOT / "var"

CONDOMINIO_DB = VAR_DIR / "condominio.db"
SESSOES_DB = VAR_DIR / "sessions.db"
SESSOES_DB_URL = f"sqlite+aiosqlite:///{SESSOES_DB}"

APP_NAME = "aurora"

# Um modelo por agente: a cota gratuita do Gemini é contada por modelo, então
# espalhar os agentes entre modelos multiplica as chamadas disponíveis por dia.
MODELO_PRINCIPAL = os.getenv("AURORA_MODEL_PRINCIPAL", "gemini-3.7-flash")
MODELO_RESERVAS = os.getenv("AURORA_MODEL_RESERVAS", "gemini-3.5-flash")
MODELO_VISITANTES = os.getenv("AURORA_MODEL_VISITANTES", "gemini-3.5-flash-lite")
MODELO_REGULAMENTO = os.getenv("AURORA_MODEL_REGULAMENTO", "gemini-3.1-flash-lite")
# Tentados em ordem quando o modelo do agente está sem cota ou sobrecarregado.
MODELOS_ALTERNATIVOS = [
    m.strip()
    for m in os.getenv(
        "AURORA_MODELS_ALTERNATIVOS",
        "gemini-3.8-flash,gemini-3.7-flash,gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite",
    ).split(",")
    if m.strip()
]

HOST = os.getenv("AURORA_HOST", "127.0.0.1")
PORT = int(os.getenv("AURORA_PORT", "8000"))
