# Residencial Aurora — assistente virtual

API em Python (FastAPI + Google ADK 2.10.0) com o assistente dos moradores do
Residencial Aurora. Pelo chat, o morador reserva o salão de festas, a
churrasqueira e a quadra, cancela as próprias reservas, autoriza visitantes e
tira dúvidas sobre o regulamento.

O modelo decide o caminho da conversa; o código decide o que é permitido. As
cinco garantias abaixo ficam nas tools, no banco e na API, e continuam valendo
independentemente do que o morador escreva.

## Arquitetura

```
cliente ── FastAPI (aurora/api.py) ── Runner + App do ADK ── DatabaseSessionService (var/sessions.db)
                                            │
                                   aurora (agente principal)
                     ┌──────────────────────┼─────────────────────────┐
             transferência           transferência                AgentTool
                     │                      │                          │
                 reservas              visitantes                 regulamento
                     │                      │                          │
          tools ─ aurora/repo.py ─ var/condominio.db (SQLite)   dados/regulamento.md
```

| Agente | Responsabilidade | Como é acionado | Por quê |
|---|---|---|---|
| `aurora` (principal) | Conversa com o morador, identifica a intenção e distribui o trabalho. Não tem tools de dados e não recebe o regulamento nas instruções. | É o `root_agent` do `App`. | Um único ponto de entrada; as instruções ficam curtas e baratas. |
| `reservas` | Listar áreas, consultar disponibilidade, reservar, listar e cancelar as reservas do morador. | `sub_agent` do principal, por **transferência** (`transfer_to_agent`). | Reservar pode pausar a execução esperando confirmação. Com transferência, a pausa fica gravada na sessão persistida em nome do próprio especialista, e o Runner devolve a aprovação a ele (ver Garantia 1). |
| `visitantes` | Autorizar a entrada de visitantes e listar os visitantes do morador. | `sub_agent` do principal, por **transferência**. | Mesmo motivo: a autorização sempre pausa esperando confirmação. |
| `regulamento` | Responder dúvidas lendo **um** capítulo do regulamento. | **`AgentTool`** do principal. | O `AgentTool` roda o especialista numa sessão própria, em memória, e devolve só a resposta final. O texto dos capítulos nunca entra na sessão do morador (ver Garantia 4). |

Os especialistas de reservas e visitantes têm `disallow_transfer_to_peers=True`:
quando o assunto muda, eles devolvem a conversa ao agente principal em vez de
se chamarem entre si.

**Tools.** Reservas e visitantes são sempre lidos e gravados por tools
([aurora/tools/reservas.py](aurora/tools/reservas.py) e
[aurora/tools/visitantes.py](aurora/tools/visitantes.py)), que chamam
[aurora/repo.py](aurora/repo.py). Nada vem da memória do modelo.

**Armazenamento.** Dois arquivos SQLite em `var/`, que fica fora do Git:
- `var/condominio.db`: apartamentos, áreas, reservas, visitantes e o dono de
  cada sessão ([aurora/db.py](aurora/db.py)). É criado a partir de `dados/`,
  e os arquivos de `dados/` nunca são alterados.
- `var/sessions.db`: sessões e eventos do ADK (`DatabaseSessionService`).

**Modelos.** Cada agente tem o próprio modelo Gemini
([aurora/config.py](aurora/config.py)), porque na cota gratuita do AI Studio o
limite diário é contado por modelo. [aurora/modelos.py](aurora/modelos.py)
repete a chamada com espera crescente. Se o modelo continuar sem cota (429),
sobrecarregado (5xx) ou sem resposta, a mesma requisição passa para o próximo
modelo de `AURORA_MODELS_ALTERNATIVOS`.

## Garantias

### Garantia 1: cobrança ou acesso só com confirmação

- **Pedido de confirmação.** [aurora/tools/reservas.py:94-111](aurora/tools/reservas.py#L94-L111)
  cobre a área com taxa, e [aurora/tools/visitantes.py:34-46](aurora/tools/visitantes.py#L34-L46)
  cobre a autorização de visitante.
  - Se `tool_context.tool_confirmation` é `None`, a tool chama
    `tool_context.request_confirmation(...)` e retorna sem gravar. O ADK grava
    então na sessão uma chamada `adk_request_confirmation` e pausa a execução.
  - A gravação só acontece quando `tool_confirmation.confirmed` é verdadeiro.
  - A quadra, com taxa 0, é gravada direto, sem confirmação.
- **Confirmações pendentes.**
  - [aurora/confirmations.py](aurora/confirmations.py) (`pendentes`) lê os
    eventos persistidos. Pendente é uma chamada `adk_request_confirmation`
    sem `FunctionResponse` com o mesmo id.
  - `detalhes` é o payload da tool: `area`/`data` para reservas e `nome`/`data`
    para visitantes.
- **A rota de confirmações.** Fica em [aurora/api.py:128-138](aurora/api.py#L128-L138).
  - Com a trava da sessão, ela recarrega os eventos e aceita o id somente se
    ele estiver pendente naquela sessão. Qualquer outro id recebe **409**,
    inclusive um já respondido.
  - Se o id estiver pendente, ela envia ao Runner o `FunctionResponse`
    `{"confirmed": true|false}` montado por `resposta_do_morador`.
  - Depois de respondida, a confirmação deixa de estar pendente. Um reenvio
    recebe 409 e não executa de novo.
- **Por que não depende do modelo.**
  - `tool_confirmation` só é preenchido pelo ADK a partir de um
    `FunctionResponse` de `adk_request_confirmation`, e só a rota de
    confirmações envia esse tipo de mensagem. A rota de mensagens envia
    apenas texto.
  - Escrever "já estou confirmando" não muda nada.
- **Retomada no agente certo.**
  - O `App` usa `ResumabilityConfig(is_resumable=True)`
    ([aurora/agents.py:115-121](aurora/agents.py#L115-L121)). Com isso, o
    Runner encaminha o `FunctionResponse` ao agente que fez a chamada de
    confirmação: `reservas` ou `visitantes`.
  - Testado com a sessão em SQLite e com a API reiniciada entre o pedido e a
    aprovação.

### Garantia 2: cada sessão pertence a um apartamento

- **Criação da sessão.** [aurora/api.py:104-117](aurora/api.py#L104-L117) grava
  o apartamento no `state` da sessão uma única vez e registra o dono da sessão
  na tabela `sessoes`.
- **Tools.**
  - Nenhuma tool recebe apartamento como parâmetro. Todas usam
    `apartamento_da_sessao(tool_context)`
    ([aurora/tools/sessao.py](aurora/tools/sessao.py)), que lê o `state`.
  - Nenhuma tool grava essa chave.
- **Consultas.**
  - Em [aurora/repo.py](aurora/repo.py), `reservas_do_apartamento`,
    `visitantes_do_apartamento` e `cancelar_reserva` filtram
    `WHERE apartamento = ?`.
  - Cancelar a reserva de outro apartamento resulta em "não encontrada", sem
    revelar o código.
- **Datas ocupadas.** `consultar_disponibilidade` e `reservar_area` usam
  `repo.data_ocupada` e devolvem só `livre`/`ocupada` ou `indisponivel`. O
  código e o apartamento de quem reservou nunca saem do banco.
- **Por que não depende do modelo.** Mesmo que o morador diga ser de outro
  apartamento, o modelo não tem nenhum parâmetro pelo qual trocar o
  apartamento das operações.

### Garantia 3: nada se perde no reinício

- **Sessões e eventos.** São gravados em `var/sessions.db` pelo
  `DatabaseSessionService` ([aurora/api.py:48-58](aurora/api.py#L48-L58)).
- **Dados do condomínio.** Reservas e visitantes ficam em `var/condominio.db`.
  - Na subida, `db.inicializar()` ([aurora/db.py:124-130](aurora/db.py#L124-L130))
    só cria o banco a partir de `dados/` se ele ainda não existir.
  - Reiniciar a API não restaura nada.
- **Confirmações pendentes.** São recalculadas a partir dos eventos
  persistidos, então sobrevivem ao reinício. Não existe estado relevante em
  memória.
- **Códigos que não se repetem.**
  - Cancelar só muda `status` para `cancelada`
    ([aurora/repo.py:120-131](aurora/repo.py#L120-L131)). A linha continua
    ocupando a `PRIMARY KEY` `codigo`.
  - Um código novo aleatório que colida com qualquer código existente, ativo
    ou cancelado, é descartado e gerado de novo
    ([aurora/repo.py:92-117](aurora/repo.py#L92-L117)).

### Garantia 4: o regulamento é consultado, não carregado

- **O agente principal.** Suas instruções
  ([aurora/agents.py](aurora/agents.py), `root_agent`) não contêm o
  regulamento. Ele só pode chamar a tool `regulamento`.
- **O especialista `regulamento`.**
  - É acionado como `AgentTool` ([aurora/agents.py:113](aurora/agents.py#L113)).
  - O `AgentTool` do ADK cria um `Runner` com `InMemorySessionService` só para
    ele. Os eventos internos (o sumário e o texto do capítulo lido) ficam
    nessa sessão descartável.
  - Na sessão do morador entram apenas a chamada da tool e a resposta final
    do especialista.
- **As tools do especialista.** Ficam em [aurora/tools/regulamento.py](aurora/tools/regulamento.py).
  - `listar_capitulos` devolve só os títulos.
  - `ler_capitulo` devolve **um** capítulo, recortado por
    [aurora/regulamento.py](aurora/regulamento.py).
- **Por que não depende do modelo.** Mesmo que o especialista leia um capítulo
  a mais, esse texto não chega à sessão do morador.

### Garantia 5: dois moradores, uma reserva

- **Índice único parcial.** Fica em [aurora/db.py:36-39](aurora/db.py#L36-L39):
  ```sql
  CREATE UNIQUE INDEX ux_reserva_ativa_por_area_data ON reservas (area, data) WHERE status = 'ativa';
  ```
- **Gravação.** `repo.criar_reserva` ([aurora/repo.py:92-117](aurora/repo.py#L92-L117))
  faz o `INSERT` numa transação `BEGIN IMMEDIATE`.
  - Se outra reserva ativa para a mesma área e data já tiver entrado, o
    SQLite rejeita o `INSERT` com `IntegrityError` no instante da gravação,
    mesmo que a conferência anterior tenha dito que a data estava livre.
  - A tool transforma isso em uma resposta normal (`indisponivel`). A
    aprovação perdedora responde 200, sem erro de servidor.
- **Por que não depende do modelo.** A regra vale para qualquer escrita no
  banco, venha de onde vier.

## Como rodar

**Pré-requisitos**
- Python 3.12 ou superior e [uv](https://docs.astral.sh/uv/).
- Uma chave do [Google AI Studio](https://aistudio.google.com/apikey).
- Nenhum serviço externo: o armazenamento é SQLite local.

**Variáveis do `.env`**

```bash
cp .env.example .env
```

| Variável | Obrigatória | Descrição |
|---|---|---|
| `GOOGLE_API_KEY` | sim | Chave do Google AI Studio. |
| `GOOGLE_GENAI_USE_VERTEXAI` | sim | `FALSE`, para usar o AI Studio. |
| `AURORA_MODEL_PRINCIPAL` | não | Modelo do agente principal (padrão `gemini-3.7-flash`). |
| `AURORA_MODEL_RESERVAS` | não | Modelo do especialista de reservas (padrão `gemini-3.5-flash`). |
| `AURORA_MODEL_VISITANTES` | não | Modelo do especialista de visitantes (padrão `gemini-3.5-flash-lite`). |
| `AURORA_MODEL_REGULAMENTO` | não | Modelo do especialista de regulamento (padrão `gemini-3.1-flash-lite`). |
| `AURORA_MODELS_ALTERNATIVOS` | não | Modelos tentados em ordem quando o do agente está sem cota ou indisponível, separados por vírgula. |

**Instalar**

```bash
uv sync
```

**Restaurar os dados iniciais.** Rode com a API parada. O comando recria
`var/condominio.db` a partir de `dados/` e apaga as sessões.

```bash
uv run aurora-restore
```

**Subir a API** em http://localhost:8000:

```bash
uv run aurora-api
```

**Conferir o fluxo do avaliador (opcional).** Com a API no ar e os dados
recém-restaurados:

```bash
uv run python scripts/fluxo_avaliador.py antes    # passos 1 a 12
# Ctrl+C na API e `uv run aurora-api` de novo, sem restaurar
uv run python scripts/fluxo_avaliador.py depois   # passos 13 e 14
```

### Contrato da API

| Rota | Resposta |
|---|---|
| `POST /sessoes` `{"apartamento": "101"}` | `201 {"session_id": "..."}` |
| `POST /sessoes/{id}/mensagens` `{"texto": "..."}` | `200 {"resposta": "...", "confirmacoes_pendentes": [{"id", "acao", "descricao", "detalhes"}]}` |
| `POST /sessoes/{id}/confirmacoes` `{"id": "...", "confirmado": true}` | `200`, no mesmo formato da rota de mensagens; `409` se o id não está pendente nesta sessão |
| `GET /sessoes/{id}/eventos` | `200`, com a lista de eventos completos, em ordem |
| `GET /apartamentos/{n}/reservas` | `200 [{"codigo", "area", "data"}]` |
| `GET /apartamentos/{n}/visitantes` | `200 [{"nome", "data"}]` |

As rotas com `{id}` respondem `404` quando a sessão não existe.
