"""Tools do especialista de regulamento.

Rodam dentro do AgentTool do especialista, numa sessão própria em memória:
o texto dos capítulos fica nessa sessão interna e só a resposta final do
especialista volta para a sessão do morador (Garantia 4).
"""

from aurora import regulamento


def listar_capitulos() -> dict:
    """Lista o número e o título de cada capítulo do regulamento interno."""
    return {"capitulos": regulamento.sumario()}


def ler_capitulo(numero: int) -> dict:
    """Devolve o texto completo de UM capítulo do regulamento interno.

    Args:
        numero: número do capítulo em algarismos arábicos (ex.: 4 para o Capítulo IV).
    """
    cap = regulamento.capitulo(numero)
    if cap is None:
        return {"status": "erro", "mensagem": f"Capítulo {numero} não existe.", "capitulos": regulamento.sumario()}
    return {"capitulo": cap.romano, "titulo": cap.titulo, "texto": cap.texto}
