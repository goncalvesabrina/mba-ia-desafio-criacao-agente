"""Tools do especialista de reservas."""

from google.adk.tools.tool_context import ToolContext

from aurora import repo
from aurora.tools.sessao import apartamento_da_sessao


def listar_areas() -> dict:
    """Lista as áreas comuns que podem ser reservadas, com id, nome e taxa em reais.

    Taxa 0 significa que a área não gera cobrança.
    """
    return {"areas": repo.listar_areas()}


def consultar_disponibilidade(area: str, data: str) -> dict:
    """Diz se uma área comum está livre ou ocupada em uma data.

    Args:
        area: id da área (ex.: "salao-de-festas", "churrasqueira", "quadra").
        data: data no formato AAAA-MM-DD.
    """
    try:
        area_info = repo.obter_area(area)
        data = repo.validar_data(data)
    except repo.ErroDeValidacao as exc:
        return {"status": "erro", "mensagem": str(exc)}
    ocupada = repo.data_ocupada(area_info["id"], data)
    # Só livre/ocupada: nunca de quem é a reserva que ocupa a data.
    return {"area": area_info["id"], "data": data, "disponibilidade": "ocupada" if ocupada else "livre"}


def listar_minhas_reservas(tool_context: ToolContext) -> dict:
    """Lista as reservas ativas do apartamento do morador desta conversa."""
    apartamento = apartamento_da_sessao(tool_context)
    return {"apartamento": apartamento, "reservas": repo.reservas_do_apartamento(apartamento)}


def cancelar_minha_reserva(area: str, data: str, tool_context: ToolContext) -> dict:
    """Cancela uma reserva do apartamento do morador desta conversa. Não pede confirmação.

    Só encontra reservas do próprio apartamento; reservas de outros apartamentos
    não podem ser canceladas.

    Args:
        area: id da área reservada (ex.: "quadra").
        data: data da reserva no formato AAAA-MM-DD.
    """
    apartamento = apartamento_da_sessao(tool_context)
    try:
        area_info = repo.obter_area(area)
        data = repo.validar_data(data)
    except repo.ErroDeValidacao as exc:
        return {"status": "erro", "mensagem": str(exc)}
    cancelada = repo.cancelar_reserva(apartamento, area_info["id"], data)
    if cancelada is None:
        return {
            "status": "nao_encontrada",
            "mensagem": f"O apartamento {apartamento} não tem reserva de {area_info['nome']} em {data}.",
        }
    return {"status": "cancelada", "reserva": cancelada}


def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
    """Reserva uma área comum para o apartamento do morador desta conversa.

    Se a área tiver taxa, a reserva gera cobrança e fica pendente até o morador
    aprovar pelo sistema de confirmações do aplicativo. Áreas sem taxa são
    reservadas na hora.

    Args:
        area: id da área (ex.: "salao-de-festas", "churrasqueira", "quadra").
        data: data no formato AAAA-MM-DD.
    """
    apartamento = apartamento_da_sessao(tool_context)
    try:
        area_info = repo.obter_area(area)
        data = repo.validar_data(data)
    except repo.ErroDeValidacao as exc:
        return {"status": "erro", "mensagem": str(exc)}

    indisponivel = {
        "status": "indisponivel",
        "mensagem": f"{area_info['nome']} já está reservado(a) em {data}. Escolha outra data.",
    }
    if repo.data_ocupada(area_info["id"], data):
        return indisponivel

    # Garantia 1: área com taxa gera cobrança, então só grava depois que o
    # morador aprovar pela rota de confirmações. tool_confirmation só é
    # preenchido pelo ADK quando chega a resposta do sistema (FunctionResponse
    # de adk_request_confirmation); texto na conversa não preenche.
    if area_info["taxa"] > 0:
        confirmacao = tool_context.tool_confirmation
        if confirmacao is None:
            tool_context.request_confirmation(
                hint=f"Confirmar reserva de {area_info['nome']} em {data} com taxa de R$ {area_info['taxa']:.2f}?",
                payload={
                    "area": area_info["id"],
                    "nome_area": area_info["nome"],
                    "data": data,
                    "taxa": area_info["taxa"],
                },
            )
            return {
                "status": "aguardando_confirmacao",
                "mensagem": "A reserva gera cobrança e aguarda a aprovação do morador no aplicativo.",
            }
        if not confirmacao.confirmed:
            return {"status": "nao_confirmada", "mensagem": "O morador recusou a cobrança. Nada foi reservado."}

    # Garantia 5: a exclusividade é conferida no INSERT (índice único parcial).
    reserva = repo.criar_reserva(apartamento, area_info["id"], data)
    if reserva is None:
        return indisponivel
    return {
        "status": "reservada",
        "mensagem": f"Reserva gravada com o código {reserva['codigo']}. Nada mais está pendente.",
        "reserva": reserva,
        "taxa": area_info["taxa"],
    }
