"""Conciliação mês a mês: cadastro (esperado) x relatórios (processado).

Para cada competência (AAAA-MM) de um contrato:
  1. Esperado  = colaboradores ativos no mês, com mensalidade e comissão calculadas pela regra.
  2. Processado = linhas dos relatórios do contrato no mês, agrupadas por pessoa.
  3. Casa as pessoas: CPF (se a chave do contrato for CPF) -> nome exato -> nome aproximado.
  4. Classifica as diferenças e calcula o impacto financeiro (recebido - esperado).
"""
from collections import defaultdict
from datetime import date

from rapidfuzz import fuzz, process
from sqlmodel import Session, select

from .models import Administradora, Colaborador, Contrato, LinhaRelatorio, Operadora, Produto
from .parsers.comum import normalizar_nome

SIMILARIDADE_MINIMA = 90  # 0-100, para casar nomes escritos de forma diferente

FAIXAS_ANS = [(0, 18), (19, 23), (24, 28), (29, 33), (34, 38), (39, 43), (44, 48), (49, 53), (54, 58), (59, 200)]

TIPOS = {
    "ausente": "Esperado, sem comissão no relatório",
    "nao_cadastrado": "No relatório, sem cadastro",
    "mensalidade": "Mensalidade diferente",
    "percentual": "Percentual de comissão diferente",
    "duplicidade": "Mesma parcela paga mais de uma vez",
    "estorno": "Estorno de comissão",
}


# ---------- utilidades ----------

def mes(d: date) -> str:
    return d.strftime("%Y-%m")


def meses_entre(inicio: str, fim: str) -> list[str]:
    a, m = map(int, inicio.split("-"))
    saida = []
    while f"{a:04d}-{m:02d}" <= fim:
        saida.append(f"{a:04d}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return saida


def diferenca_meses(inicio: str, fim: str) -> int:
    a1, m1 = map(int, inicio.split("-"))
    a2, m2 = map(int, fim.split("-"))
    return (a2 - a1) * 12 + (m2 - m1)


def percentual_da_regra(regras: list[dict], parcela: int | None) -> float | None:
    if parcela is None:
        return None
    for r in regras or []:
        ate = r.get("parcela_ate")
        if r["parcela_de"] <= parcela and (ate is None or parcela <= ate):
            return float(r["percentual"])
    return None


def mensalidade_esperada(colab: Colaborador, produto: Produto, competencia: str) -> float:
    if produto.tabela_faixas and colab.data_nascimento:
        ano, m = map(int, competencia.split("-"))
        n = colab.data_nascimento
        idade = ano - n.year - ((m, 1) < (n.month, n.day))
        for i, (de, ate) in enumerate(FAIXAS_ANS):
            if de <= idade <= ate and i < len(produto.tabela_faixas):
                return float(produto.tabela_faixas[i])
    return colab.valor_mensalidade


def ativo_no_mes(colab: Colaborador, competencia: str) -> bool:
    """data_exclusao = mês a partir do qual não deve mais haver cobrança."""
    if mes(colab.data_inclusao) > competencia:
        return False
    return colab.data_exclusao is None or mes(colab.data_exclusao) > competencia


def fonte_do_contrato(session: Session, contrato: Contrato) -> str | None:
    if contrato.administradora_id:
        adm = session.get(Administradora, contrato.administradora_id)
        if adm and adm.codigo_fonte:
            return adm.codigo_fonte
    produto = session.get(Produto, contrato.produto_id)
    operadora = session.get(Operadora, produto.operadora_id)
    return operadora.codigo_fonte


def linhas_do_contrato(session: Session, contrato: Contrato) -> list[LinhaRelatorio]:
    fonte = fonte_do_contrato(session, contrato)
    if not fonte:
        return []
    return list(session.exec(select(LinhaRelatorio).where(
        LinhaRelatorio.fonte == fonte,
        LinhaRelatorio.contrato_ref == contrato.identificador_relatorio)))


# ---------- conciliação ----------

def _eh_estorno(l: LinhaRelatorio) -> bool:
    return l.valor_estorno > 0 and l.valor_comissao <= 0


def _agrupar_processado(linhas: list[LinhaRelatorio]) -> dict[str, dict]:
    pessoas: dict[str, dict] = {}
    for l in linhas:
        chave = normalizar_nome(l.nome)
        p = pessoas.setdefault(chave, {"nome": l.nome, "cpf": None, "linhas": []})
        p["cpf"] = p["cpf"] or l.cpf
        p["linhas"].append(l)
    for p in pessoas.values():
        # Linhas de estorno não contam como pagamento da mensalidade
        ls = [l for l in p["linhas"] if not _eh_estorno(l)] or p["linhas"]
        p["pagamentos"] = [l for l in p["linhas"] if not _eh_estorno(l)]
        p["mensalidade"] = round(sum(l.valor_base for l in ls) / len(ls), 2)
        p["mensalidade_total"] = round(sum(l.valor_base for l in p["pagamentos"]), 2)
        ls = p["linhas"]
        p["comissao"] = round(sum(l.valor_comissao for l in ls), 2)
        p["estorno"] = round(sum(l.valor_estorno for l in ls), 2)
        p["parcelas"] = sorted({l.parcela for l in ls if l.parcela is not None})
        p["percentuais"] = sorted({l.percentual for l in ls if l.percentual is not None and not _eh_estorno(l)})
        p["relatorios"] = sorted({l.relatorio_id for l in ls})
    return pessoas


def _casar(esperados: list[dict], processados: dict[str, dict], chave_cpf: bool):
    """Devolve (pares, esperados_sem_par, processados_sem_par)."""
    pares, livres_e = [], list(esperados)
    livres_p = dict(processados)

    def casar_por(funcao_chave, confianca):
        nonlocal livres_e
        indice = {}
        for k, p in livres_p.items():
            ch = funcao_chave(p)
            if ch:
                indice.setdefault(ch, k)
        restantes = []
        for e in livres_e:
            ch = funcao_chave(e)
            if ch and ch in indice and indice[ch] in livres_p:
                pares.append((e, livres_p.pop(indice[ch]), confianca))
            else:
                restantes.append(e)
        livres_e = restantes

    if chave_cpf:
        casar_por(lambda x: x.get("cpf"), "cpf")
    casar_por(lambda x: normalizar_nome(x["nome"]), "nome")

    restantes = []
    for e in livres_e:
        achado = process.extractOne(normalizar_nome(e["nome"]), list(livres_p.keys()),
                                    scorer=fuzz.token_sort_ratio, score_cutoff=SIMILARIDADE_MINIMA)
        if achado:
            pares.append((e, livres_p.pop(achado[0]), f"nome aproximado ({achado[1]:.0f}%)"))
        else:
            restantes.append(e)
    return pares, restantes, livres_p


def conciliar_mes(contrato, produto, colaboradores, linhas_mes, competencia) -> dict:
    esperados = []
    for c in colaboradores:
        if not ativo_no_mes(c, competencia):
            continue
        mens = mensalidade_esperada(c, produto, competencia)
        parcela = diferenca_meses(mes(c.data_inclusao), competencia) + 1
        esperados.append({"colaborador_id": c.id, "nome": c.nome, "cpf": c.cpf,
                          "mensalidade": mens, "parcela_estimada": parcela})

    processados = _agrupar_processado(linhas_mes)
    pares, ausentes, novos = _casar(esperados, processados, contrato.chave_conciliacao == "cpf")

    divergencias = []
    tot_esp_comissao = tot_esp_mens = 0.0

    for e, p, confianca in pares:
        # Comissão esperada parcela a parcela: um mês pode trazer parcelas atrasadas/antecipadas.
        pagamentos = p["pagamentos"]
        parcelas = [l.parcela if l.parcela is not None else e["parcela_estimada"] for l in pagamentos]
        pcts = [percentual_da_regra(contrato.regras_comissao, n) for n in parcelas]
        if pagamentos and all(x is not None for x in pcts):
            com_esp = round(sum(e["mensalidade"] * x / 100 for x in pcts), 2)
        elif pagamentos:
            com_esp = p["comissao"] + p["estorno"]  # sem regra para a parcela: não há como esperar
        else:
            com_esp = 0.0  # só estorno no mês
        pct = pcts[0] if pcts else None
        tot_esp_comissao += com_esp
        tot_esp_mens += e["mensalidade"] * max(len(pagamentos), 1)

        tipos = []
        if pagamentos and abs(p["mensalidade"] - e["mensalidade"]) > contrato.tolerancia:
            tipos.append("mensalidade")
        if any(x is not None and abs(l.percentual - x) > 0.001
               for l, x in zip(pagamentos, pcts) if l.percentual is not None):
            tipos.append("percentual")
        if len(parcelas) != len(set(parcelas)):
            tipos.append("duplicidade")
        if p["estorno"] > 0:
            tipos.append("estorno")
        impacto = round(p["comissao"] - com_esp, 2)
        if tipos:
            divergencias.append(_item(tipos, e, p, confianca, pct, com_esp, impacto))

    for e in ausentes:
        pct = percentual_da_regra(contrato.regras_comissao, e["parcela_estimada"])
        com_esp = round(e["mensalidade"] * (pct or 0) / 100, 2)
        tot_esp_comissao += com_esp
        tot_esp_mens += e["mensalidade"]
        divergencias.append(_item(["ausente"], e, None, None, pct, com_esp, -com_esp))

    for p in novos.values():
        divergencias.append(_item(["nao_cadastrado"], None, p, None, None, 0.0, p["comissao"]))

    proc_comissao = round(sum(p["comissao"] for p in processados.values()), 2)
    proc_mens = round(sum(p["mensalidade_total"] for p in processados.values()), 2)
    contagem = defaultdict(int)
    for d in divergencias:
        for t in d["tipos"]:
            contagem[t] += 1
    divergencias.sort(key=lambda d: (-abs(d["impacto"]), d["nome"]))

    return {
        "competencia": competencia,
        "status": "divergente" if divergencias else "ok",
        "esperado": {"vidas": len(esperados), "mensalidades": round(tot_esp_mens, 2),
                     "comissao": round(tot_esp_comissao, 2)},
        "processado": {"vidas": len(processados), "mensalidades": proc_mens, "comissao": proc_comissao,
                       "linhas": len(linhas_mes)},
        "casados": len(pares),
        "impacto": round(proc_comissao - tot_esp_comissao, 2),
        "contagem": dict(contagem),
        "divergencias": divergencias,
    }


def _item(tipos, e, p, confianca, pct, com_esp, impacto) -> dict:
    return {
        "tipos": tipos,
        "nome": (e or p)["nome"],
        "colaborador_id": e["colaborador_id"] if e else None,
        "confianca": confianca,
        "esperado": None if e is None else {
            "mensalidade": e["mensalidade"], "percentual": pct, "comissao": com_esp,
            "parcela": e["parcela_estimada"], "cpf": e["cpf"]},
        "processado": None if p is None else {
            "mensalidade": p["mensalidade"], "percentuais": p["percentuais"], "comissao": p["comissao"],
            "estorno": p["estorno"], "parcelas": p["parcelas"], "linhas": len(p["linhas"]),
            "cpf": p["cpf"], "relatorios": p["relatorios"]},
        "impacto": round(impacto, 2),
    }


def conciliar_contrato(session: Session, contrato: Contrato) -> dict:
    produto = session.get(Produto, contrato.produto_id)
    colaboradores = list(session.exec(select(Colaborador).where(Colaborador.contrato_id == contrato.id)))
    linhas = linhas_do_contrato(session, contrato)

    por_mes = defaultdict(list)
    for l in linhas:
        por_mes[l.competencia].append(l)

    meses = []
    if por_mes:
        hoje = mes(date.today())
        # Do início do contrato (ou 1º relatório) até o último relatório (limitado a hoje),
        # mais meses futuros pagos antecipadamente.
        inicio = max(min(por_mes), mes(contrato.data_inicio))
        fim = max(inicio, min(max(por_mes), hoje))
        meses = sorted(set(meses_entre(inicio, fim)) | {m for m in por_mes if m >= inicio})

    resultado = [conciliar_mes(contrato, produto, colaboradores, por_mes.get(m, []), m)
                 for m in reversed(meses)]
    return {
        "contrato_id": contrato.id,
        "tipos": TIPOS,
        "meses": resultado,
        "totais": {
            "meses": len(resultado),
            "meses_divergentes": sum(1 for m in resultado if m["status"] == "divergente"),
            "esperado": round(sum(m["esperado"]["comissao"] for m in resultado), 2),
            "processado": round(sum(m["processado"]["comissao"] for m in resultado), 2),
            "impacto": round(sum(m["impacto"] for m in resultado), 2),
        },
    }
