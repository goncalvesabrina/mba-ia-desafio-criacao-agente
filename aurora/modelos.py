"""Modelo Gemini com retentativas e troca de modelo quando o atual está indisponível.

Na cota gratuita do Google AI Studio cada modelo tem seu próprio limite diário,
e modelos diferentes ficam sobrecarregados (503) em momentos diferentes. Se o
modelo do agente falhar por cota (429) ou indisponibilidade (5xx), a mesma
requisição é repetida no próximo modelo da lista.
"""

import logging

import httpx
from typing import AsyncGenerator

from google.adk.models import Gemini, LlmRequest, LlmResponse
from google.genai import errors, types

from aurora import config

logger = logging.getLogger("aurora.modelos")

_CODIGOS_TRANSITORIOS = {429, 500, 502, 503, 504}

# Tempo máximo de cada chamada ao modelo antes de desistir dele (ms).
_TIMEOUT_MS = 60_000

_RETRY = types.HttpRetryOptions(
    attempts=3, initial_delay=2.0, max_delay=10.0, http_status_codes=sorted(_CODIGOS_TRANSITORIOS)
)


class GeminiComReserva(Gemini):
    """Gemini que tenta os modelos de `alternativos` quando o principal falha."""

    alternativos: list[str] = []

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        candidatos = [self.model] + [m for m in self.alternativos if m != self.model]
        ultimo_erro: Exception | None = None
        for nome in candidatos:
            llm_request.model = nome
            http_options = llm_request.config.http_options or types.HttpOptions()
            llm_request.config.http_options = http_options.model_copy(update={"timeout": _TIMEOUT_MS})
            try:
                async for resposta in super().generate_content_async(llm_request, stream=stream):
                    yield resposta
                return
            except errors.APIError as exc:
                if exc.code not in _CODIGOS_TRANSITORIOS:
                    raise
                logger.warning("Modelo %s indisponível (%s); tentando o próximo.", nome, exc.code)
                ultimo_erro = exc
            except httpx.TimeoutException as exc:
                logger.warning("Modelo %s não respondeu a tempo; tentando o próximo.", nome)
                ultimo_erro = exc
        assert ultimo_erro is not None
        raise ultimo_erro


def modelo(nome: str) -> GeminiComReserva:
    return GeminiComReserva(model=nome, alternativos=config.MODELOS_ALTERNATIVOS, retry_options=_RETRY)
