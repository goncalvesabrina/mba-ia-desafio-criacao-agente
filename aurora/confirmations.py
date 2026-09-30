"""Confirmações pendentes, lidas dos eventos persistidos da sessão.

Quando uma tool chama tool_context.request_confirmation, o ADK grava na sessão
uma chamada de função especial, adk_request_confirmation, e pausa a execução.
Uma confirmação está pendente enquanto não existir na sessão uma resposta
(FunctionResponse) com o mesmo id. Como tudo vem dos eventos persistidos, a
lista sobrevive ao reinício da API.
"""

from typing import Any

from google.adk.events import Event
from google.adk.flows.llm_flows.functions import REQUEST_CONFIRMATION_FUNCTION_CALL_NAME
from google.genai import types


def pendentes(events: list[Event]) -> list[dict[str, Any]]:
    respondidas = {fr.id for ev in events for fr in ev.get_function_responses() if fr.id}
    resultado = []
    for ev in events:
        for fc in ev.get_function_calls():
            if fc.name != REQUEST_CONFIRMATION_FUNCTION_CALL_NAME or not fc.id or fc.id in respondidas:
                continue
            args = fc.args or {}
            original = args.get("originalFunctionCall") or {}
            confirmacao = args.get("toolConfirmation") or {}
            detalhes = confirmacao.get("payload") or original.get("args") or {}
            resultado.append(
                {
                    "id": fc.id,
                    "acao": original.get("name", ""),
                    "descricao": confirmacao.get("hint", ""),
                    "detalhes": detalhes,
                }
            )
    return resultado


def resposta_do_morador(confirmation_id: str, confirmado: bool) -> types.Content:
    """Mensagem que devolve ao ADK a decisão do morador sobre uma confirmação."""
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=confirmation_id,
                    name=REQUEST_CONFIRMATION_FUNCTION_CALL_NAME,
                    response={"confirmed": confirmado},
                )
            )
        ],
    )
