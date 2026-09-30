"""Comando `uv run aurora-restore`: volta reservas e visitantes ao estado de dados/.

Também apaga as sessões, para o fluxo recomeçar de um estado limpo.
"""

from aurora import config, db


def main() -> None:
    db.restaurar()
    for sufixo in ("", "-wal", "-shm", "-journal"):
        config.SESSOES_DB.with_name(config.SESSOES_DB.name + sufixo).unlink(missing_ok=True)
    print(f"Dados restaurados a partir de {config.DADOS_DIR} e sessões apagadas.")


if __name__ == "__main__":
    main()
