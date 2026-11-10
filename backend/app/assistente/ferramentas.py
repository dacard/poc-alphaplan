"""Ferramentas (consultas) que o assistente de IA pode chamar.

Cada ferramenta recebe parâmetros simples e devolve um dicionário pequeno, já agregado,
para o modelo responder sem precisar ver o banco inteiro.
"""
from collections import defaultdict
from datetime import date, datetime, timezone

from rapidfuzz import fuzz, process
from sqlmodel import Session, select

from .. import conciliacao as conc
from ..dashboard import dados_dashboard
from ..models import (Administradora, Cliente, Colaborador, Contrato, LinhaRelatorio, Operadora,
                      Produto, Relatorio)
from ..parsers.comum import normalizar_nome

PERCENTUAL_AGENCIAMENTO = 50  # parcelas com % >= isto são agenciamento (não recorrente)


# ---------- contexto compartilhado (carregado uma vez por pergunta) ----------

class Contexto:
    def __init__(self, session: Session):
        self.session = session
        self.hoje = date.today().strftime("%Y-%m")
        a, m = map(int, self.hoje.split("-"))
        self.ultimo_mes = f"{a:04d}-{m - 1:02d}" if m > 1 else f"{a - 1:04d}-12"
        self.mes_anterior = conc.meses_entre("2000-01", self.ultimo_mes)[-2]
        self.clientes = {c.id: c for c in session.exec(select(Cliente))}
        self.produtos = {p.id: p for p in session.exec(select(Produto))}
        self.operadoras = {o.id: o for o in session.exec(select(Operadora))}
        self.adms = {a.id: a for a in session.exec(select(Administradora))}
        self.contratos = list(session.exec(select(Contrato)))
        refs = {}
        for c in self.contratos:
            fonte = conc.fonte_do_contrato(session, c)
            if fonte:
                refs[(fonte, c.identificador_relatorio)] = c.id
        self.linhas = defaultdict(list)  # contrato_id -> linhas
        for l in session.exec(select(LinhaRelatorio)):
            cid = refs.get((l.fonte, l.contrato_ref))
            if cid:
                self.linhas[cid].append(l)
        self._conciliacao = {}

    def conciliacao(self, c: Contrato) -> dict:
        if c.id not in self._conciliacao:
            self._conciliacao[c.id] = conc.conciliar_contrato(self.session, c)
        return self._conciliacao[c.id]

    def contratos_de(self, cliente_id: int | None = None, contrato_id: int | None = None) -> list[Contrato]:
        return [c for c in self.contratos
                if (cliente_id is None or c.cliente_id == cliente_id)
                and (contrato_id is None or c.id == contrato_id)]

    def receita_mes(self, c: Contrato, mes: str, recorrente: bool = False) -> float:
        total = 0.0
        for l in self.linhas[c.id]:
            if l.competencia != mes:
                continue
            if recorrente and l.valor_comissao > 0 and (l.percentual or 0) >= PERCENTUAL_AGENCIAMENTO:
                continue
            total += l.valor_comissao
        return round(total, 2)

    def pessoas_mes(self, c: Contrato, mes: str) -> set[str]:
        return {normalizar_nome(l.nome) for l in self.linhas[c.id] if l.competencia == mes and l.valor_comissao > 0}

    def descrever(self, c: Contrato) -> dict:
        p = self.produtos[c.produto_id]
        return {
            "contrato_id": c.id,
            "cliente_id": c.cliente_id,
            "cliente": self.clientes[c.cliente_id].nome,
            "produto": p.nome,
            "operadora": self.operadoras[p.operadora_id].nome,
            "administradora": self.adms[c.administradora_id].nome if c.administradora_id else None,
            "identificador_relatorio": c.identificador_relatorio,
        }

    def metricas(self, c: Contrato) -> dict:
        r = self.conciliacao(c)
        colabs = self.session.exec(select(Colaborador).where(Colaborador.contrato_id == c.id)).all()
        ultimo = next((m for m in r["meses"] if m["competencia"] == self.ultimo_mes), None)
        return {
            **self.descrever(c),
            "colaboradores_ativos_cadastro": sum(1 for x in colabs if conc.ativo_no_mes(x, self.hoje)),
            "receita_total": round(sum(l.valor_comissao for l in self.linhas[c.id]), 2),
            "receita_ultimo_mes": self.receita_mes(c, self.ultimo_mes),
            "receita_mes_anterior": self.receita_mes(c, self.mes_anterior),
            "vidas_ultimo_mes": len(self.pessoas_mes(c, self.ultimo_mes)),
            "vidas_mes_anterior": len(self.pessoas_mes(c, self.mes_anterior)),
            "impacto_acumulado": r["totais"]["impacto"],
            "meses_com_divergencia": r["totais"]["meses_divergentes"],
            "meses_analisados": r["totais"]["meses"],
            "situacao_ultimo_mes": ultimo["status"] if ultimo else "sem relatório",
        }


# ---------- ferramentas ----------

def buscar_clientes(ctx: Contexto, texto: str | None = None) -> dict:
    clientes = list(ctx.clientes.values())
    if texto:
        alvo = normalizar_nome(texto)
        nomes = {c.id: normalizar_nome(c.nome) for c in clientes}
        diretos = [c for c in clientes if alvo in nomes[c.id]]
        if diretos:
            clientes = diretos
        else:
            achados = process.extract(alvo, nomes, scorer=fuzz.partial_ratio, limit=5, score_cutoff=70)
            clientes = [ctx.clientes[k] for _, _, k in achados]
    saida = []
    for cli in sorted(clientes, key=lambda c: c.nome)[:20]:
        contratos = ctx.contratos_de(cliente_id=cli.id)
        m = [ctx.metricas(c) for c in contratos]
        saida.append({
            "cliente_id": cli.id, "nome": cli.nome, "contratos": len(contratos),
            "colaboradores_ativos_cadastro": sum(x["colaboradores_ativos_cadastro"] for x in m),
            "receita_total": round(sum(x["receita_total"] for x in m), 2),
            "receita_ultimo_mes": round(sum(x["receita_ultimo_mes"] for x in m), 2),
            "impacto_acumulado": round(sum(x["impacto_acumulado"] for x in m), 2),
        })
    return {"encontrados": len(saida), "clientes": saida}


def listar_contratos(ctx: Contexto, cliente_id: int | None = None) -> dict:
    contratos = ctx.contratos_de(cliente_id=cliente_id)
    return {"ultimo_mes_completo": ctx.ultimo_mes, "mes_anterior": ctx.mes_anterior,
            "total_contratos": len(contratos), "contratos": [ctx.metricas(c) for c in contratos]}


CRITERIOS = {
    "receita_total": ("Receita de comissão acumulada (todos os meses)", True),
    "receita_ultimo_mes": ("Receita do último mês completo", True),
    "queda_ultimo_mes": ("Variação de receita: último mês completo x mês anterior (mais negativa primeiro)", False),
    "queda_trimestre": ("Variação da receita recorrente (sem agenciamento): média dos últimos 3 meses x 3 anteriores", False),
    "impacto_negativo": ("Diferença acumulada recebido − esperado pelo cadastro (mais negativa primeiro)", False),
    "impacto_positivo": ("Diferença acumulada recebido − esperado pelo cadastro (mais positiva primeiro)", True),
    "colaboradores": ("Colaboradores ativos no cadastro", True),
    "saida_colaboradores": ("Variação de vidas com comissão: último mês x anterior (mais negativa primeiro)", False),
}


def ranking(ctx: Contexto, criterio: str, agrupar_por: str = "contrato", limite: int = 10,
            cliente_id: int | None = None) -> dict:
    if criterio not in CRITERIOS:
        raise ValueError(f"criterio inválido; use um de: {', '.join(CRITERIOS)}")
    descricao, maior_primeiro = CRITERIOS[criterio]
    meses = conc.meses_entre("2000-01", ctx.ultimo_mes)
    recentes, anteriores = meses[-3:], meses[-6:-3]

    itens = []
    for c in ctx.contratos_de(cliente_id=cliente_id):
        m = ctx.metricas(c)
        if criterio == "queda_ultimo_mes":
            valor = round(m["receita_ultimo_mes"] - m["receita_mes_anterior"], 2)
        elif criterio == "queda_trimestre":
            antes = sum(ctx.receita_mes(c, x, recorrente=True) for x in anteriores) / 3
            depois = sum(ctx.receita_mes(c, x, recorrente=True) for x in recentes) / 3
            m["receita_media_antes"], m["receita_media_depois"] = round(antes, 2), round(depois, 2)
            valor = round(depois - antes, 2)
        elif criterio == "saida_colaboradores":
            valor = m["vidas_ultimo_mes"] - m["vidas_mes_anterior"]
        else:
            valor = {"receita_total": m["receita_total"], "receita_ultimo_mes": m["receita_ultimo_mes"],
                     "impacto_negativo": m["impacto_acumulado"], "impacto_positivo": m["impacto_acumulado"],
                     "colaboradores": m["colaboradores_ativos_cadastro"]}[criterio]
        itens.append({**m, "valor": valor})

    if agrupar_por != "contrato":
        chave = {"cliente": lambda x: x["cliente"],
                 "administradora": lambda x: x["administradora"] or "(direto com a operadora)",
                 "operadora": lambda x: x["operadora"]}[agrupar_por]
        grupos = defaultdict(lambda: {"valor": 0.0, "contratos": 0, "receita_total": 0.0,
                                      "receita_ultimo_mes": 0.0, "receita_mes_anterior": 0.0,
                                      "impacto_acumulado": 0.0})
        for x in itens:
            g = grupos[chave(x)]
            g["contratos"] += 1
            for k in ("valor", "receita_total", "receita_ultimo_mes", "receita_mes_anterior", "impacto_acumulado"):
                g[k] = round(g[k] + x[k], 2)
        if criterio == "saida_colaboradores" and agrupar_por == "cliente":
            # pessoas distintas por cliente (quem tem médico e odonto conta uma vez)
            for x_cli in {x["cliente_id"]: x["cliente"] for x in itens}.items():
                cs = ctx.contratos_de(cliente_id=x_cli[0])
                antes = set().union(*(ctx.pessoas_mes(c, ctx.mes_anterior) for c in cs))
                depois = set().union(*(ctx.pessoas_mes(c, ctx.ultimo_mes) for c in cs))
                grupos[x_cli[1]]["valor"] = len(depois) - len(antes)
        itens = [{agrupar_por: nome, **g} for nome, g in grupos.items()]

    if criterio in ("queda_ultimo_mes", "queda_trimestre", "impacto_negativo", "saida_colaboradores"):
        itens = [x for x in itens if x["valor"] < 0]
    elif criterio == "impacto_positivo":
        itens = [x for x in itens if x["valor"] > 0]
    itens.sort(key=lambda x: x["valor"], reverse=maior_primeiro)
    return {
        "criterio": descricao,
        "periodo": {"ultimo_mes_completo": ctx.ultimo_mes, "mes_anterior": ctx.mes_anterior,
                    "trimestre_recente": f"{recentes[0]} a {recentes[-1]}",
                    "trimestre_anterior": f"{anteriores[0]} a {anteriores[-1]}"},
        "total_que_atendem": len(itens),
        "itens": itens[:max(1, min(limite, 30))],
    }


def movimentacao_colaboradores(ctx: Contexto, cliente_id: int | None = None, contrato_id: int | None = None,
                               meses: int = 6) -> dict:
    """Entradas e saídas mês a mês, pelas pessoas com comissão nos relatórios."""
    contratos = ctx.contratos_de(cliente_id=cliente_id, contrato_id=contrato_id)
    if not contratos:
        raise ValueError("Nenhum contrato encontrado para o filtro informado.")
    todos = conc.meses_entre("2000-01", ctx.ultimo_mes)
    janela = todos[-(meses + 1):]
    pessoas = {m: set() for m in janela}  # pessoas distintas (médico + odonto da mesma pessoa contam uma vez)
    for c in contratos:
        for m in janela:
            pessoas[m] |= ctx.pessoas_mes(c, m)
    linhas, total_e, total_s = [], 0, 0
    for anterior, atual in zip(janela, janela[1:]):
        entradas = pessoas[atual] - pessoas[anterior]
        saidas = pessoas[anterior] - pessoas[atual]
        total_e += len(entradas)
        total_s += len(saidas)
        linhas.append({
            "competencia": atual, "vidas": len(pessoas[atual]),
            "entradas": len(entradas), "saidas": len(saidas),
            "nomes_entradas": sorted(entradas)[:8],
            "nomes_saidas": sorted(saidas)[:8],
        })
    colabs = [x for c in contratos for x in ctx.session.exec(select(Colaborador).where(Colaborador.contrato_id == c.id))]
    return {
        "escopo": [ctx.descrever(c) for c in contratos][:10],
        "metodo": "Entrada = pessoa com comissão no mês que não tinha no mês anterior; saída = o contrário.",
        "periodo": f"{janela[1]} a {janela[-1]}",
        "total_entradas": total_e, "total_saidas": total_s,
        "vidas_inicio": len(pessoas[janela[0]]), "vidas_fim": len(pessoas[janela[-1]]),
        "meses": linhas,
        "cadastro": {"colaboradores": len(colabs),
                     "ativos": sum(1 for x in colabs if conc.ativo_no_mes(x, ctx.hoje)),
                     "com_data_de_exclusao": sum(1 for x in colabs if x.data_exclusao)},
    }


def conciliacao_contrato(ctx: Contexto, contrato_id: int, competencia: str | None = None) -> dict:
    c = next((x for x in ctx.contratos if x.id == contrato_id), None)
    if not c:
        raise ValueError(f"Contrato {contrato_id} não encontrado.")
    r = ctx.conciliacao(c)
    meses = [{k: m[k] for k in ("competencia", "status", "impacto", "contagem")} |
             {"esperado": m["esperado"]["comissao"], "recebido": m["processado"]["comissao"],
              "vidas_esperadas": m["esperado"]["vidas"], "vidas_processadas": m["processado"]["vidas"]}
             for m in r["meses"]]
    detalhe = None
    alvo = competencia or (r["meses"][0]["competencia"] if r["meses"] else None)
    mes = next((m for m in r["meses"] if m["competencia"] == alvo), None)
    if mes:
        detalhe = {"competencia": alvo, "divergencias": [
            {"tipos": d["tipos"], "nome": d["nome"], "impacto": d["impacto"],
             "esperado": d["esperado"] and {k: d["esperado"][k] for k in ("mensalidade", "percentual", "comissao")},
             "recebido": d["processado"] and {k: d["processado"][k] for k in ("mensalidade", "percentuais", "comissao", "parcelas")}}
            for d in mes["divergencias"][:15]], "total_divergencias": len(mes["divergencias"])}
    return {**ctx.descrever(c), "regras_comissao": c.regras_comissao, "totais": r["totais"],
            "tipos_de_divergencia": r["tipos"], "meses": meses, "detalhe_do_mes": detalhe}


def ultimos_relatorios(ctx: Contexto, fonte: str | None = None, cliente_id: int | None = None,
                       limite: int = 5) -> dict:
    relatorios = {r.id: r for r in ctx.session.exec(select(Relatorio))}
    linhas_por_rel = defaultdict(int)
    if cliente_id is not None:
        for c in ctx.contratos_de(cliente_id=cliente_id):
            for l in ctx.linhas[c.id]:
                linhas_por_rel[l.relatorio_id] += 1
        candidatos = [relatorios[i] for i in linhas_por_rel]
    else:
        candidatos = list(relatorios.values())
    if fonte:
        candidatos = [r for r in candidatos if r.fonte == fonte.lower()]
    candidatos.sort(key=lambda r: (r.data_referencia, r.importado_em), reverse=True)

    def local(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%d/%m/%Y %H:%M")

    por_fonte = defaultdict(lambda: {"total": 0, "portal": 0, "upload_manual": 0, "mais_recente": None})
    for r in candidatos:
        g = por_fonte[r.fonte]
        g["total"] += 1
        g["upload_manual" if "/manual-" in "/" + r.caminho else "portal"] += 1
        g["mais_recente"] = max(g["mais_recente"] or "", r.data_referencia.isoformat())
    return {"total": len(candidatos), "totais_por_fonte": dict(por_fonte), "relatorios": [{
        "relatorio_id": r.id, "fonte": r.fonte, "referencia": r.referencia,
        "data_do_relatorio": r.data_referencia.strftime("%d/%m/%Y"),
        "importado_em": local(r.importado_em),
        "arquivo": r.caminho.split("/")[-1], "pasta": r.caminho,
        "origem": "upload manual" if "/manual-" in "/" + r.caminho else "portal",
        "status": r.status, "linhas": r.qtd_linhas,
        **({"linhas_do_cliente": linhas_por_rel[r.id]} if cliente_id is not None else {}),
    } for r in candidatos[:max(1, min(limite, 20))]]}


def serie_mensal(ctx: Contexto, cliente_id: int | None = None, contrato_id: int | None = None,
                 meses: int = 12) -> dict:
    contratos = ctx.contratos_de(cliente_id=cliente_id, contrato_id=contrato_id)
    janela = conc.meses_entre("2000-01", ctx.ultimo_mes)[-meses:]
    esperado = defaultdict(float)
    for c in contratos:
        for m in ctx.conciliacao(c)["meses"]:
            esperado[m["competencia"]] += m["esperado"]["comissao"]
    serie = []
    for m in janela:  # vidas = pessoas distintas no mês
        bruta = sum(l.valor_comissao for c in contratos for l in ctx.linhas[c.id] if l.competencia == m and l.valor_comissao > 0)
        estornos = sum(l.valor_estorno for c in contratos for l in ctx.linhas[c.id] if l.competencia == m)
        vidas = len(set().union(*(ctx.pessoas_mes(c, m) for c in contratos))) if contratos else 0
        serie.append({"competencia": m, "receita_liquida": round(bruta - estornos, 2), "estornos": round(estornos, 2),
                      "esperado": round(esperado[m], 2), "vidas": vidas})
    return {"contratos": len(contratos), "serie": serie}


def resumo_geral(ctx: Contexto, cliente_ids: list[int] | None = None) -> dict:
    d = dados_dashboard(ctx.session, cliente_ids)
    ind = dict(d["indicadores"])
    ind["relatorios_com_dados_de_contratos"] = ind.pop("relatorios")  # relatórios sem linhas de contrato não entram
    ind["pagamentos_de_comissao"] = ind.pop("pagamentos")
    return {
        "indicadores": ind,
        "ultimos_meses": d["serie"][-6:],
        "projecao": d["projecao"]["resumo"],
        "projecao_meses": [{k: p[k] for k in ("competencia", "receita", "vidas")} for p in d["projecao"]["meses"]],
        "alertas_queda_receita": {k: d["alertas"][k] for k in ("total", "perda_mensal", "periodo_recente", "periodo_anterior")},
    }


# ---------- definições para a API ----------

def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


INT_OPC = {"type": "integer"}
DEFINICOES = [
    {"name": "buscar_clientes",
     "description": "Procura clientes (empresas) pelo nome, com tolerância a grafia, e devolve id, nº de contratos, "
                    "colaboradores ativos, receita total e do último mês e impacto acumulado. Use para descobrir o "
                    "cliente_id antes de outras consultas. Sem 'texto', lista todos.",
     "input_schema": _obj({"texto": {"type": "string", "description": "Parte do nome do cliente"}})},
    {"name": "listar_contratos",
     "description": "Lista os contratos (de um cliente ou de todos) com produto, operadora, administradora, "
                    "colaboradores ativos, receita total, receita do último mês completo e do anterior, vidas e "
                    "impacto acumulado (recebido − esperado).",
     "input_schema": _obj({"cliente_id": INT_OPC})},
    {"name": "ranking",
     "description": "Ordena contratos ou clientes por um critério. Use para 'mais lucrativo' (receita_total ou "
                    "receita_ultimo_mes), 'redução/queda no último mês' (queda_ultimo_mes), 'queda de receita "
                    "recorrente' (queda_trimestre), 'resultado negativo / recebendo menos que o esperado' "
                    "(impacto_negativo), 'recebendo a mais' (impacto_positivo), 'maiores em colaboradores' "
                    "(colaboradores) e 'perda de colaboradores' (saida_colaboradores). Para empresas, use agrupar_por='cliente'; "
                    "para comparar administradoras ou operadoras, agrupar_por='administradora' ou 'operadora'.",
     "input_schema": _obj({
         "criterio": {"type": "string", "enum": list(CRITERIOS)},
         "agrupar_por": {"type": "string", "enum": ["contrato", "cliente", "administradora", "operadora"]},
         "limite": {"type": "integer", "description": "Quantos itens devolver (padrão 10)"},
         "cliente_id": INT_OPC,
     }, ["criterio"])},
    {"name": "movimentacao_colaboradores",
     "description": "Entradas e saídas de colaboradores mês a mês (pessoas com comissão nos relatórios), "
                    "de um cliente, de um contrato ou de toda a carteira, nos últimos N meses completos.",
     "input_schema": _obj({"cliente_id": INT_OPC, "contrato_id": INT_OPC,
                           "meses": {"type": "integer", "description": "Meses completos a analisar (padrão 6)"}})},
    {"name": "conciliacao_contrato",
     "description": "Conciliação de um contrato: regras de comissão, totais, situação e impacto de cada mês e as "
                    "divergências de um mês (padrão: o mais recente) com esperado x recebido por colaborador.",
     "input_schema": _obj({"contrato_id": {"type": "integer"},
                           "competencia": {"type": "string", "description": "AAAA-MM"}}, ["contrato_id"])},
    {"name": "ultimos_relatorios",
     "description": "Relatórios processados: totais por fonte (quantos vieram do portal e quantos por upload manual) "
                    "e os mais recentes (geral, de uma fonte ou que trazem dados de um cliente), com data do relatório, "
                    "data/hora da importação, nome do arquivo, origem e status. "
                    "Fontes: samp, easyplan, uphealth, quali, mediatorie.",
     "input_schema": _obj({"fonte": {"type": "string"}, "cliente_id": INT_OPC,
                           "limite": {"type": "integer", "description": "Padrão 5"}})},
    {"name": "serie_mensal",
     "description": "Receita líquida, estornos, esperado pelo cadastro e vidas mês a mês (últimos N meses completos), "
                    "de toda a carteira, de um cliente ou de um contrato. Use para tendências e comparações entre meses.",
     "input_schema": _obj({"cliente_id": INT_OPC, "contrato_id": INT_OPC,
                           "meses": {"type": "integer", "description": "Padrão 12"}})},
    {"name": "resumo_geral",
     "description": "Indicadores gerais (clientes, operadoras, administradoras, contratos, colaboradores, relatórios, "
                    "pagamentos, receita total e estornos), últimos 6 meses, projeção dos próximos meses e total de "
                    "contratos com queda de receita. Opcionalmente filtrado por uma lista de clientes.",
     "input_schema": _obj({"cliente_ids": {"type": "array", "items": {"type": "integer"}}})},
]

FUNCOES = {
    "buscar_clientes": buscar_clientes,
    "listar_contratos": listar_contratos,
    "ranking": ranking,
    "movimentacao_colaboradores": movimentacao_colaboradores,
    "conciliacao_contrato": conciliacao_contrato,
    "ultimos_relatorios": ultimos_relatorios,
    "serie_mensal": serie_mensal,
    "resumo_geral": resumo_geral,
}
