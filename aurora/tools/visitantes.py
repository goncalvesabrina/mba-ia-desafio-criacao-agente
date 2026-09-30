"""Tools do especialista de visitantes."""

from google.adk.tools.tool_context import ToolContext

from aurora import repo
from aurora.tools.sessao import apartamento_da_sessao


def listar_meus_visitantes(tool_context: ToolContext) -> dict:
    """Lista os visitantes autorizados do apartamento do morador desta conversa."""
    apartamento = apartamento_da_sessao(tool_context)
    return {"apartamento": apartamento, "visitantes": repo.visitantes_do_apartamento(apartamento)}


def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict:
    """Autoriza a entrada de um visitante no prédio para o apartamento do morador.

    Liberar acesso sempre fica pendente até o morador aprovar pelo sistema de
    confirmações do aplicativo; dizer na conversa que já confirmou não basta.

    Args:
        nome: nome completo do visitante.
        data: data da visita no formato AAAA-MM-DD.
    """
    apartamento = apartamento_da_sessao(tool_context)
    nome = " ".join((nome or "").split())
    if not nome:
        return {"status": "erro", "mensagem": "Informe o nome do visitante."}
    try:
        data = repo.validar_data(data)
    except repo.ErroDeValidacao as exc:
        return {"status": "erro", "mensagem": str(exc)}

    # Garantia 1: liberar acesso só com a aprovação vinda da rota de confirmações.
    confirmacao = tool_context.tool_confirmation
    if confirmacao is None:
        tool_context.request_confirmation(
            hint=f"Confirmar a entrada de {nome} em {data}?",
            payload={"nome": nome, "data": data},
        )
        return {
            "status": "aguardando_confirmacao",
            "mensagem": "A autorização libera acesso ao prédio e aguarda a aprovação do morador no aplicativo.",
        }
    if not confirmacao.confirmed:
        return {"status": "nao_confirmada", "mensagem": "O morador recusou a autorização. Nada foi gravado."}

    visitante = repo.autorizar_visitante(apartamento, nome, data)
    return {
        "status": "autorizado",
        "mensagem": f"Entrada de {nome} autorizada para {data}. Nada mais está pendente.",
        "visitante": visitante,
    }
