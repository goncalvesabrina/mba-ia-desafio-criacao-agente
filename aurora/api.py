"""API HTTP do assistente (contrato do enunciado) — `uv run aurora-api`."""

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService, Session
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from aurora import config, confirmations, db, repo
from aurora.agents import app as adk_app
from aurora.tools.sessao import CHAVE_APARTAMENTO

logger = logging.getLogger("aurora.api")


class NovaSessao(BaseModel):
    apartamento: str


class NovaMensagem(BaseModel):
    texto: str


class RespostaConfirmacao(BaseModel):
    id: str
    confirmado: bool


class Estado:
    session_service: DatabaseSessionService
    runner: Runner
    # Uma execução por vez em cada sessão (sessões diferentes rodam em paralelo).
    travas: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


estado = Estado()


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.inicializar()
    config.VAR_DIR.mkdir(parents=True, exist_ok=True)
    # Garantia 3: sessões e eventos persistidos em SQLite (var/sessions.db).
    estado.session_service = DatabaseSessionService(
        db_url=config.SESSOES_DB_URL, connect_args={"timeout": 30}
    )
    estado.runner = Runner(app=adk_app, session_service=estado.session_service)
    yield
    await estado.runner.close()


api = FastAPI(title="Residencial Aurora — assistente", lifespan=lifespan)


@api.exception_handler(genai_errors.APIError)
async def modelo_indisponivel(_: Request, exc: genai_errors.APIError) -> JSONResponse:
    logger.error("Falha ao chamar o modelo: %s", exc)
    return JSONResponse(status_code=503, content={"detail": "O assistente está indisponível no momento. Tente de novo."})


async def _carregar_sessao(session_id: str) -> Session:
    apartamento = repo.apartamento_da_sessao(session_id)
    session = None
    if apartamento is not None:
        session = await estado.session_service.get_session(
            app_name=config.APP_NAME, user_id=apartamento, session_id=session_id
        )
    if session is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    return session


def _texto(eventos: list[Event]) -> str:
    partes = []
    for ev in eventos:
        if ev.author == "user" or ev.partial or not ev.content or not ev.content.parts:
            continue
        partes.extend(p.text for p in ev.content.parts if p.text and not p.thought)
    return "\n".join(t.strip() for t in partes if t.strip())


async def _executar(session: Session, mensagem: types.Content) -> dict:
    eventos = []
    async for ev in estado.runner.run_async(
        user_id=session.user_id, session_id=session.id, new_message=mensagem
    ):
        eventos.append(ev)
    atualizada = await _carregar_sessao(session.id)
    return {
        "resposta": _texto(eventos),
        "confirmacoes_pendentes": confirmations.pendentes(atualizada.events),
    }


@api.post("/sessoes", status_code=201)
async def criar_sessao(body: NovaSessao) -> dict:
    apartamento = body.apartamento.strip()
    if not repo.apartamento_existe(apartamento):
        raise HTTPException(status_code=404, detail="Apartamento não encontrado.")
    # Garantia 2: o apartamento entra no state uma única vez, aqui. As tools o
    # leem do state e nenhuma tool o altera.
    session = await estado.session_service.create_session(
        app_name=config.APP_NAME,
        user_id=apartamento,
        state={CHAVE_APARTAMENTO: apartamento},
    )
    repo.registrar_sessao(session.id, apartamento)
    return {"session_id": session.id}


@api.post("/sessoes/{session_id}/mensagens")
async def enviar_mensagem(session_id: str, body: NovaMensagem) -> dict:
    session = await _carregar_sessao(session_id)
    async with estado.travas[session_id]:
        mensagem = types.Content(role="user", parts=[types.Part(text=body.texto)])
        return await _executar(session, mensagem)


@api.post("/sessoes/{session_id}/confirmacoes")
async def responder_confirmacao(session_id: str, body: RespostaConfirmacao) -> dict:
    await _carregar_sessao(session_id)
    async with estado.travas[session_id]:
        # Garantia 1: só aceita um id que esteja pendente nesta sessão, conferido
        # nos eventos persistidos. Id respondido, inexistente ou de outra sessão -> 409.
        session = await _carregar_sessao(session_id)
        ids_pendentes = {p["id"] for p in confirmations.pendentes(session.events)}
        if body.id not in ids_pendentes:
            raise HTTPException(status_code=409, detail="Não existe confirmação pendente com esse id nesta sessão.")
        return await _executar(session, confirmations.resposta_do_morador(body.id, body.confirmado))


@api.get("/sessoes/{session_id}/eventos")
async def listar_eventos(session_id: str) -> list[dict]:
    session = await _carregar_sessao(session_id)
    return [ev.model_dump(mode="json", by_alias=True, exclude_none=True) for ev in session.events]


@api.get("/apartamentos/{numero}/reservas")
async def reservas_do_apartamento(numero: str) -> list[dict]:
    return repo.reservas_do_apartamento(numero)


@api.get("/apartamentos/{numero}/visitantes")
async def visitantes_do_apartamento(numero: str) -> list[dict]:
    return repo.visitantes_do_apartamento(numero)


def main() -> None:
    uvicorn.run("aurora.api:api", host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
