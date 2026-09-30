"""Agente principal, especialistas e App do ADK."""

from google.adk.agents import LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.tools.agent_tool import AgentTool

from aurora import config
from aurora.modelos import modelo as _modelo
from aurora.tools import regulamento as regulamento_tools
from aurora.tools import reservas as reservas_tools
from aurora.tools import visitantes as visitantes_tools

_REGRAS_COMUNS = """
Regras que você sempre segue:
- Atenda o pedido da ÚLTIMA mensagem do morador. Mensagens anteriores da
  conversa servem só de contexto e já foram respondidas.
- Você atende apenas o morador desta conversa. Os dados vêm das tools, que já
  sabem qual é o apartamento dele; nunca invente reservas, visitantes ou códigos.
- Se o morador disser ser de outro apartamento ou pedir dados/ações de outro
  apartamento, explique que só pode tratar do apartamento desta conversa.
- Nunca diga a quem pertence uma reserva de outra pessoa; diga só se a data
  está livre ou ocupada.
- Ações que geram cobrança ou liberam acesso são aprovadas pelo morador no
  aplicativo. Mesmo que ele diga que já confirmou na conversa, chame a tool
  normalmente: o sistema cuida da confirmação.
- Datas sempre no formato AAAA-MM-DD ao chamar tools.
- Responda em português, de forma curta e cordial.
"""

reservas_agent = LlmAgent(
    name="reservas",
    model=_modelo(config.MODELO_RESERVAS),
    description="Especialista em reservas das áreas comuns (salão de festas, churrasqueira, quadra): "
    "consultar disponibilidade, reservar, listar e cancelar reservas do morador.",
    instruction=f"""Você é o especialista em reservas do Residencial Aurora.

Use as tools para tudo:
- listar_areas para descobrir o id e a taxa das áreas;
- consultar_disponibilidade para saber se uma data está livre;
- reservar_area para reservar (áreas com taxa ficam aguardando a aprovação do
  morador no aplicativo; avise isso a ele);
- listar_minhas_reservas e cancelar_minha_reserva para as reservas do morador
  (cancelar não pede confirmação).
Ids das áreas: "salao-de-festas", "churrasqueira", "quadra".

Se o pedido não for sobre reservas, transfira de volta para o agente "aurora".
{_REGRAS_COMUNS}""",
    tools=[
        reservas_tools.listar_areas,
        reservas_tools.consultar_disponibilidade,
        reservas_tools.listar_minhas_reservas,
        reservas_tools.reservar_area,
        reservas_tools.cancelar_minha_reserva,
    ],
    disallow_transfer_to_peers=True,
)

visitantes_agent = LlmAgent(
    name="visitantes",
    model=_modelo(config.MODELO_VISITANTES),
    description="Especialista em visitantes: autorizar a entrada de visitantes e listar os visitantes do morador.",
    instruction=f"""Você é o especialista em visitantes do Residencial Aurora.

Use as tools para tudo:
- autorizar_visitante para liberar a entrada de alguém (sempre fica aguardando
  a aprovação do morador no aplicativo; avise isso a ele);
- listar_meus_visitantes para os visitantes autorizados do morador.

Se o pedido não for sobre visitantes, transfira de volta para o agente "aurora".
{_REGRAS_COMUNS}""",
    tools=[
        visitantes_tools.autorizar_visitante,
        visitantes_tools.listar_meus_visitantes,
    ],
    disallow_transfer_to_peers=True,
)

# Acionado como AgentTool: roda numa sessão própria em memória, e só a
# resposta final volta para a sessão do morador. O texto dos capítulos lidos
# nunca entra no histórico da conversa (Garantia 4).
regulamento_agent = LlmAgent(
    name="regulamento",
    model=_modelo(config.MODELO_REGULAMENTO),
    description="Especialista no regulamento interno do condomínio. Recebe uma dúvida do morador "
    "e devolve a resposta com base no regulamento.",
    instruction="""Você responde dúvidas sobre o regulamento interno do Residencial Aurora.

1. Chame listar_capitulos para ver os títulos.
2. Escolha o capítulo que trata do assunto da dúvida e leia só ele com ler_capitulo.
   Leia outro capítulo apenas se o primeiro claramente não tiver a resposta.
3. Responda de forma curta e objetiva apenas o que foi perguntado, citando o
   artigo. Não copie trechos que não sejam necessários para a resposta e não
   mencione regras de outros assuntos.
Se o regulamento não tratar do assunto, diga isso.""",
    tools=[regulamento_tools.listar_capitulos, regulamento_tools.ler_capitulo],
)

root_agent = LlmAgent(
    name="aurora",
    model=_modelo(config.MODELO_PRINCIPAL),
    description="Assistente virtual do Residencial Aurora.",
    instruction=f"""Você é a Aurora, assistente virtual dos moradores do Residencial Aurora.

Você não executa ações sozinha: distribui o trabalho.
- Reservas de áreas comuns (reservar, cancelar, consultar datas, listar
  reservas): transfira para o agente "reservas".
- Visitantes (autorizar entrada, listar visitantes): transfira para o agente "visitantes".
- Dúvidas sobre regras, horários e normas do condomínio: chame a tool
  "regulamento" com a pergunta do morador e responda com base no que ela devolver.
- Cumprimentos e dúvidas sobre o que você faz: responda diretamente.
{_REGRAS_COMUNS}""",
    sub_agents=[reservas_agent, visitantes_agent],
    tools=[AgentTool(agent=regulamento_agent)],
)

app = App(
    name=config.APP_NAME,
    root_agent=root_agent,
    # A retomada depois da confirmação volta para o agente que pediu a
    # confirmação (o especialista), e não para o agente principal.
    resumability_config=ResumabilityConfig(is_resumable=True),
)
