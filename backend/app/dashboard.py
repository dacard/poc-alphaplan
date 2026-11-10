"""Dados do dashboard: indicadores, receita mês a mês e projeção.

Receita = comissão líquida recebida (pagamentos − estornos), por competência.
Esperado = comissão calculada pelo cadastro (mesma conta da conciliação).
Projeção: tendência linear das vidas com comissão nos últimos meses completos ×
receita média por vida no mesmo período. A faixa de incerteza usa a variação
mensal da receita por vida.
"""
from collections import defaultdict
from datetime import date
from statistics import mean, pstdev

from sqlmodel import Session, select

from . import conciliacao as conc
from .models import Cliente, Colaborador, Contrato, LinhaRelatorio, Produto
from .parsers.comum import normalizar_nome

MESES_BASE_PROJECAO = 6
JANELA_ALERTA = 3          # meses recentes x meses anteriores
PERCENTUAL_AGENCIAMENTO = 50  # parcelas com % >= isto são agenciamento (não recorrente)
TOP_ALERTAS = 10
HORIZONTE_PROJECAO = 6
AMORTECIMENTO = 0.8  # a cada mês a tendência da receita por vida pesa 80% do mês anterior


def _proximos_meses(ultimo: str, n: int) -> list[str]:
    a, m = map(int, ultimo.split("-"))
    saida = []
    for _ in range(n):
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
        saida.append(f"{a:04d}-{m:02d}")
    return saida


def _tendencia(valores: list[float]) -> tuple[float, float]:
    """Regressão linear simples (y = a + b·x). Devolve (a, b)."""
    n = len(valores)
    if n < 2:
        return (valores[0] if valores else 0.0), 0.0
    xs = range(n)
    mx, my = (n - 1) / 2, mean(valores)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, valores)) / sum((x - mx) ** 2 for x in xs)
    return my - b * mx, b


def dados_dashboard(session: Session, cliente_ids: list[int] | None) -> dict:
    hoje = date.today().strftime("%Y-%m")
    q = select(Contrato)
    if cliente_ids is not None:
        q = q.where(Contrato.cliente_id.in_(cliente_ids or [-1]))
    contratos = list(session.exec(q))

    # Linhas de relatório dos contratos selecionados
    refs = {}
    for c in contratos:
        fonte = conc.fonte_do_contrato(session, c)
        if fonte:
            refs[(fonte, c.identificador_relatorio)] = c.id
    linhas = [l for l in session.exec(select(LinhaRelatorio)) if (l.fonte, l.contrato_ref) in refs]

    # ---------- indicadores ----------
    produtos = {p.id: p for p in session.exec(select(Produto))}
    colaboradores = list(session.exec(select(Colaborador).where(
        Colaborador.contrato_id.in_([c.id for c in contratos] or [-1]))))
    total_clientes = len(cliente_ids) if cliente_ids is not None else len(session.exec(select(Cliente)).all())
    indicadores = {
        "clientes": total_clientes,
        "operadoras": len({produtos[c.produto_id].operadora_id for c in contratos}),
        "administradoras": len({c.administradora_id for c in contratos if c.administradora_id}),
        "contratos": len(contratos),
        "colaboradores": sum(1 for x in colaboradores if conc.ativo_no_mes(x, hoje)),
        "relatorios": len({l.relatorio_id for l in linhas}),
        "pagamentos": sum(1 for l in linhas if l.valor_comissao > 0),
        "receita": round(sum(l.valor_comissao for l in linhas), 2),
        "estornos": round(sum(l.valor_estorno for l in linhas), 2),
    }

    # ---------- série mensal (até o mês atual; parcelas antecipadas ficam de fora do gráfico) ----------
    por_mes = defaultdict(lambda: {"bruta": 0.0, "estornos": 0.0, "pessoas": set()})
    for l in linhas:
        if l.competencia > hoje:
            continue
        m = por_mes[l.competencia]
        if l.valor_comissao > 0:
            m["bruta"] += l.valor_comissao
            m["pessoas"].add((l.fonte, l.contrato_ref, normalizar_nome(l.nome)))
        m["estornos"] += l.valor_estorno

    esperado = defaultdict(float)
    for c in contratos:
        for m in conc.conciliar_contrato(session, c)["meses"]:
            if m["competencia"] <= hoje:
                esperado[m["competencia"]] += m["esperado"]["comissao"]

    meses = conc.meses_entre(min(por_mes), max(por_mes)) if por_mes else []
    serie = []
    for comp in meses:
        m = por_mes.get(comp, {"bruta": 0.0, "estornos": 0.0, "pessoas": set()})
        serie.append({
            "competencia": comp,
            "receita": round(m["bruta"] - m["estornos"], 2),
            "bruta": round(m["bruta"], 2),
            "estornos": round(m["estornos"], 2),
            "esperado": round(esperado[comp], 2) if comp in esperado else None,
            "vidas": len(m["pessoas"]),
            "parcial": comp == hoje,
        })

    por_contrato = defaultdict(list)
    for l in linhas:
        por_contrato[refs[(l.fonte, l.contrato_ref)]].append(l)
    return {"indicadores": indicadores, "serie": serie, "projecao": _projetar(serie),
            "alertas": _alertas(session, contratos, por_contrato, hoje)}


def _alertas(session: Session, contratos: list[Contrato], por_contrato: dict, hoje: str) -> dict:
    """Contratos com maior queda de receita recorrente: média dos últimos meses completos
    contra a média dos meses anteriores. Agenciamento fica de fora, porque o fim dele
    derruba a receita de todo contrato novo e não indica problema."""
    a, m = map(int, hoje.split("-"))
    ultimo = f"{a:04d}-{m - 1:02d}" if m > 1 else f"{a - 1:04d}-12"  # último mês completo
    inicio = conc.meses_entre("2000-01", ultimo)[-2 * JANELA_ALERTA]
    janela = conc.meses_entre(inicio, ultimo)
    anteriores, recentes = janela[:JANELA_ALERTA], janela[JANELA_ALERTA:]

    clientes = {c.id: c.nome for c in session.exec(select(Cliente))}
    produtos = {p.id: p.nome for p in session.exec(select(Produto))}
    itens = []
    for c in contratos:
        receita = defaultdict(float)
        pessoas = defaultdict(set)
        for l in por_contrato.get(c.id, []):
            if l.competencia not in janela:
                continue
            if l.percentual is not None and l.percentual >= PERCENTUAL_AGENCIAMENTO and l.valor_comissao > 0:
                continue
            receita[l.competencia] += l.valor_comissao
            if l.valor_comissao > 0:
                pessoas[l.competencia].add(normalizar_nome(l.nome))
        antes = sum(receita[x] for x in anteriores) / JANELA_ALERTA
        depois = sum(receita[x] for x in recentes) / JANELA_ALERTA
        if antes <= 0 or depois >= antes:
            continue
        vidas_antes = round(sum(len(pessoas[x]) for x in anteriores) / JANELA_ALERTA, 1)
        vidas_depois = round(sum(len(pessoas[x]) for x in recentes) / JANELA_ALERTA, 1)
        num = lambda v: f"{v:g}".replace(".", ",")
        if depois <= 0:
            causa, tipo = f"nenhuma comissão em {recentes[0][5:]}–{recentes[-1][5:]}/{recentes[-1][:4]}", "sem_pagamento"
        else:
            # A causa é a que mais explica a queda: menos vidas ou menos receita por vida
            va, vd = antes / vidas_antes, depois / vidas_depois
            if (vidas_depois - vidas_antes) / vidas_antes <= (vd - va) / va:
                causa, tipo = f"{num(vidas_antes)} → {num(vidas_depois)} vidas/mês", "vidas"
            else:
                causa, tipo = f"R$ {va:.2f} → R$ {vd:.2f} por vida".replace(".", ","), "valor"
        itens.append({
            "contrato_id": c.id,
            "cliente": clientes[c.cliente_id],
            "produto": produtos[c.produto_id],
            "identificador": c.identificador_relatorio,
            "receita_antes": round(antes, 2),
            "receita_depois": round(depois, 2),
            "variacao": round(depois - antes, 2),
            "variacao_pct": round((depois - antes) / antes * 100, 1),
            "vidas_antes": vidas_antes,
            "vidas_depois": vidas_depois,
            "causa": causa,
            "tipo": tipo,
        })
    itens.sort(key=lambda x: x["variacao"])
    return {
        "periodo_anterior": [anteriores[0], anteriores[-1]],
        "periodo_recente": [recentes[0], recentes[-1]],
        "total": len(itens),
        "perda_mensal": round(sum(x["variacao"] for x in itens), 2),
        "itens": itens[:TOP_ALERTAS],
    }


def _projetar(serie: list[dict]) -> dict:
    """Receita projetada = vidas projetadas × receita por vida projetada.

    As duas tendências vêm dos últimos meses completos. Assim a projeção capta tanto
    entrada/saída de colaboradores quanto mudanças de valor (reajustes, fim de
    agenciamento, estornos). Vidas seguem a tendência linear; a receita por vida usa
    tendência amortecida (Holt), porque quedas como o fim do agenciamento se estabilizam.
    Faixa = ± desvio dos resíduos da receita por vida.
    """
    completos = [s for s in serie if not s["parcial"] and s["vidas"]][-MESES_BASE_PROJECAO:]
    if len(completos) < 3:
        return {"meses": [], "base": [], "resumo": None}

    vidas = [s["vidas"] for s in completos]
    por_vida = [s["receita"] / s["vidas"] for s in completos]
    av, bv = _tendencia(vidas)
    ap, bp = _tendencia(por_vida)
    residuos = [y - (ap + bp * x) for x, y in enumerate(por_vida)]
    desvio = pstdev(residuos)

    n = len(completos)
    # O mês em andamento (parcial) também é projetado, além dos próximos meses
    extra = 1 if serie[-1]["parcial"] else 0
    pontos = []
    for i, comp in enumerate(_proximos_meses(completos[-1]["competencia"], HORIZONTE_PROJECAO + extra)):
        x = n + i
        v = max(0.0, av + bv * x)
        passos = x - (n - 1)
        pv = max(0.0, ap + bp * (n - 1) + bp * sum(AMORTECIMENTO ** k for k in range(1, passos + 1)))
        pontos.append({
            "competencia": comp,
            "vidas": round(v, 1),
            "receita": round(v * pv, 2),
            "receita_min": round(v * max(0.0, pv - desvio), 2),
            "receita_max": round(v * (pv + desvio), 2),
        })

    ultimo = completos[-1]
    return {
        "meses": pontos,
        "base": [s["competencia"] for s in completos],
        "resumo": {
            "vidas_por_mes": round(bv, 1),
            "receita_por_vida": round(por_vida[-1], 2),
            "receita_por_vida_por_mes": round(bp, 3),
            "estornos_medios": round(mean(s["estornos"] for s in completos), 2),
            "vidas_atual": ultimo["vidas"],
            "receita_atual": ultimo["receita"],
            "vidas_fim": pontos[-1]["vidas"],
            "receita_fim": pontos[-1]["receita"],
            "receita_total_projetada": round(sum(p["receita"] for p in pontos), 2),
        },
    }
