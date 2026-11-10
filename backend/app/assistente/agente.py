"""Assistente de IA da POC: responde perguntas sobre clientes, contratos, comissões e relatórios.

Loop de ferramentas com a API da Anthropic: o modelo decide quais consultas fazer (ferramentas.py),
recebe os resultados e escreve a resposta. A conversa fica em memória no servidor, com os blocos
originais da resposta (incluindo os de raciocínio), como a API exige.
"""
import json
import threading
import uuid
from datetime import date

import anthropic
from dotenv import load_dotenv
from sqlmodel import Session

from ..db import RAIZ, engine
from .ferramentas import DEFINICOES, FUNCOES, Contexto

load_dotenv(RAIZ / ".env")

MODELO = "claude-opus-5-5"
ESFORCO = "medium"
MAX_RODADAS = 8  # chamadas de ferramenta por pergunta
BETAS = ["server-side-fallback-2026-07-01"]

SISTEMA = """Você é o assistente de IA da Alphaplan, uma corretora de benefícios que vende planos de saúde de \
operadoras (Samp, Unimed, Bluzz Saúde...) diretamente ou por administradoras (Easyplan, Up Health, Quali, \
Mediatorie). A Alphaplan recebe comissão sobre cada mensalidade paga pelos colaboradores das empresas clientes. \
Você apoia os operadores e gestores na validação desta POC, que baixa os relatórios de comissão dos portais, \
compara mês a mês com o cadastro dos contratos e aponta divergências.

Responda só sobre esse contexto: clientes, contratos, colaboradores, comissões, receitas, divergências, \
relatórios processados, projeções. Para qualquer outro assunto, diga em uma frase que só pode ajudar com os \
dados da POC.

## Como trabalhar
- Use as ferramentas para todo número, nome ou data. Nunca invente nem estime de cabeça.
- Quando a pergunta citar um cliente pelo nome, use buscar_clientes para achar o cliente_id. Se houver mais de \
um candidato plausível, responda com as opções e pergunte qual é.
- Faça quantas consultas precisar, de preferência em paralelo quando forem independentes.

## Glossário
- Receita: comissão líquida recebida (pagamentos menos estornos), por mês de competência.
- Esperado: comissão calculada pelo cadastro do contrato (mensalidade × % da regra da parcela).
- Impacto: recebido − esperado. Negativo = a Alphaplan recebeu menos do que deveria.
- "Mais lucrativo": maior receita de comissão. Use a receita acumulada, salvo se a pergunta falar de um período \
(ex.: "no último mês").
- "Resultado negativo": interprete como impacto acumulado negativo (recebendo menos que o esperado). Se a \
pergunta for sobre perda de receita ao longo do tempo, use as quedas. Diga em meia frase qual critério usou.
- "Redução no último mês": último mês completo comparado ao mês anterior.
- Agenciamento: parcelas iniciais pagas com % alto (50–100%). O fim delas derruba a receita de todo contrato \
novo e é esperado; para tendência use a queda de receita recorrente (queda_trimestre).
- Vidas: pessoas com pagamento de comissão no mês.

## Como responder
Clara e objetiva: responda exatamente o que foi perguntado, em poucas frases. Quem pergunta é um gestor \
ocupado; ele pede mais detalhes se quiser.
- A primeira frase já é a resposta. Em geral, 1 a 3 frases bastam.
- Liste só quando a pergunta pedir vários itens: até 5 (diga quantos são no total se houver mais). Tabela em \
markdown só para comparar 3 ou mais itens em 2 ou mais números.
- Não acrescente análises, alertas ou recomendações que não foram pedidos. Se houver algo realmente importante \
para a decisão (ex.: dado incompleto), diga em uma frase curta no final.
- Valores no formato R$ 1.234,56; datas dd/mm/aaaa; meses como "outubro/2026". Cite o período quando a \
resposta depender dele.
- Não exponha ids internos, nomes de ferramentas nem detalhes técnicos, a menos que perguntem.

Exemplos do tom esperado:
- "Qual o último relatório processado do cliente X?" -> "O último relatório processado foi o de 10/10/2026, \
importado às 15h30: relatorio-outubro.pdf."
- "Quais empresas estão apresentando resultado negativo?" -> "As empresas mais negativas são X (−R$ 1.200,00), \
Y (−R$ 800,00) e Z (−R$ 450,00), considerando o recebido menos o esperado pelo cadastro."
"""


_cliente = None
_conversas: dict[str, list] = {}
_trava = threading.Lock()


def cliente_api() -> anthropic.Anthropic:
    global _cliente
    if _cliente is None:
        _cliente = anthropic.Anthropic()
    return _cliente


def _executar(ctx: Contexto, nome: str, entrada: dict) -> tuple[str, bool]:
    funcao = FUNCOES.get(nome)
    if not funcao:
        return f"Ferramenta desconhecida: {nome}", True
    try:
        resultado = funcao(ctx, **entrada)
        return json.dumps(resultado, ensure_ascii=False, default=str), False
    except (TypeError, ValueError) as erro:
        return f"Erro: {erro}", True


def perguntar(mensagem: str, conversa_id: str | None = None) -> dict:
    conversa_id = conversa_id if conversa_id in _conversas else str(uuid.uuid4())
    with _trava:
        historico = _conversas.setdefault(conversa_id, [])
        mensagens = historico + [{"role": "user", "content": mensagem}]

    hoje = date.today()
    sistema = [
        {"type": "text", "text": SISTEMA},
        {"type": "text", "text": f"Hoje é {hoje.strftime('%d/%m/%Y')}. O mês atual está em andamento; "
                                 "o último mês completo é o anterior."},
    ]
    usadas, uso = [], {"entrada": 0, "saida": 0, "cache_lido": 0}

    with Session(engine) as session:
        ctx = Contexto(session)
        for _ in range(MAX_RODADAS + 1):
            resposta = cliente_api().beta.messages.create(
                model=MODELO,
                max_tokens=16000,
                betas=BETAS,
                fallbacks="default",
                output_config={"effort": ESFORCO},
                cache_control={"type": "ephemeral"},
                system=sistema,
                tools=DEFINICOES,
                messages=mensagens,
            )
            uso["entrada"] += resposta.usage.input_tokens
            uso["saida"] += resposta.usage.output_tokens
            uso["cache_lido"] += resposta.usage.cache_read_input_tokens or 0

            if resposta.stop_reason == "refusal":
                texto = "Não consigo responder a essa pergunta. Posso ajudar com os dados de comissões da POC."
                break
            mensagens.append({"role": "assistant", "content": resposta.content})
            chamadas = [b for b in resposta.content if b.type == "tool_use"]
            if resposta.stop_reason != "tool_use" or not chamadas:
                texto = "\n".join(b.text for b in resposta.content if b.type == "text").strip()
                if resposta.stop_reason == "max_tokens":
                    texto += "\n\n_(resposta interrompida por tamanho)_"
                break
            resultados = []
            for chamada in chamadas:
                conteudo, erro = _executar(ctx, chamada.name, chamada.input)
                usadas.append({"ferramenta": chamada.name, "entrada": chamada.input, "erro": erro})
                resultados.append({"type": "tool_result", "tool_use_id": chamada.id,
                                   "content": conteudo, **({"is_error": True} if erro else {})})
            mensagens.append({"role": "user", "content": resultados})
        else:
            texto = "Não consegui concluir a consulta. Tente reformular a pergunta de forma mais específica."

    with _trava:
        _conversas[conversa_id] = mensagens
    return {"conversa_id": conversa_id, "resposta": texto or "(sem resposta)", "ferramentas": usadas, "uso": uso}


def nova_conversa(conversa_id: str | None):
    with _trava:
        _conversas.pop(conversa_id, None)
