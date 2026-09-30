"""De onde as tools tiram o apartamento: sempre da sessão, nunca do modelo."""

from google.adk.tools.tool_context import ToolContext

CHAVE_APARTAMENTO = "apartamento"


def apartamento_da_sessao(tool_context: ToolContext) -> str:
    """Apartamento do morador autenticado, gravado no state na criação da sessão.

    Nenhuma tool recebe apartamento como parâmetro, e nenhuma tool grava esta
    chave: o modelo não tem como trocar o apartamento usado nas operações.
    """
    apartamento = tool_context.state.get(CHAVE_APARTAMENTO)
    if not apartamento:
        raise RuntimeError("Sessão sem apartamento definido.")
    return str(apartamento)
