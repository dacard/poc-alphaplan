"""Avaliação do assistente de IA com 20 perguntas de gestor.

Para cada pergunta, a resposta certa é calculada direto do banco (sem passar pelas ferramentas do
assistente) e o script confere:
  - compreensão: o assistente consultou as ferramentas que respondem a pergunta;
  - resposta: os fatos esperados (nomes, números, datas) aparecem no texto.

Rodar a partir de backend/:  ../.venv/bin/python -m avaliacao.avaliar_assistente [--so 3,7]
Grava o relatório em dados/avaliacao_assistente.md (dados reais: fica fora do git).
"""
import argparse
import re
import time
import unicodedata
from collections import defaultdict
from datetime import date

from sqlmodel import Session, select

from app import conciliacao as conc
from app.assistente.agente import perguntar
from app.db import PASTA_DADOS, engine
from app.models import Administradora, Cliente, Colaborador, Contrato, LinhaRelatorio, Produto, Relatorio
from app.parsers.comum import normalizar_nome


# ---------- utilidades ----------

def sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def brl(v: float) -> str:
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s  # sem "R$" e sem sinal: casa com "R$ 1.234,56" e "-R$ 1.234,56"


def nome_curto(nome: str, palavras: int = 2) -> str:
    """Primeiras palavras significativas do nome (o assistente pode abreviar razões sociais)."""
    ignorar = {"de", "da", "do", "e", "ltda", "s.a", "me"}
    return " ".join([p for p in nome.split() if p.lower() not in ignorar][:palavras])


def contem(texto: str, alvo: str) -> bool:
    t = sem_acento(texto).replace(" ", " ")
    return sem_acento(alvo) in t


# ---------- verdade calculada do banco ----------

class Verdade:
    def __init__(self, s: Session):
        self.s = s
        hoje = date.today()
        self.hoje = hoje.strftime("%Y-%m")
        self.ultimo = f"{hoje.year}-{hoje.month - 1:02d}" if hoje.month > 1 else f"{hoje.year - 1}-12"
        self.anterior = conc.meses_entre("2000-01", self.ultimo)[-2]
        self.clientes = {c.id: c for c in s.exec(select(Cliente))}
        self.contratos = list(s.exec(select(Contrato)))
        self.produtos = {p.id: p for p in s.exec(select(Produto))}
        self.adms = {a.id: a for a in s.exec(select(Administradora))}
        self.linhas = {c.id: conc.linhas_do_contrato(s, c) for c in self.contratos}
        self.conc = {c.id: conc.conciliar_contrato(s, c) for c in self.contratos}

    def cliente(self, trecho: str) -> Cliente:
        return next(c for c in self.clientes.values() if sem_acento(trecho) in sem_acento(c.nome))

    def receita(self, contratos, mes=None) -> float:
        return round(sum(l.valor_comissao for c in contratos for l in self.linhas[c.id]
                         if mes is None or l.competencia == mes), 2)

    def de(self, cliente_id):
        return [c for c in self.contratos if c.cliente_id == cliente_id]

    def pessoas(self, contratos, mes):
        """Pessoas distintas com comissão no mês (médico + odonto da mesma pessoa contam uma vez)."""
        return {normalizar_nome(l.nome) for c in contratos for l in self.linhas[c.id]
                if l.competencia == mes and l.valor_comissao > 0}


def montar_casos(v: Verdade) -> list[dict]:
    casos = []

    def caso(pergunta, ferramentas, fatos, algum=None, proibido=None):
        casos.append({"pergunta": pergunta, "ferramentas": ferramentas, "fatos": fatos,
                      "algum": algum or [], "proibido": proibido or []})

    ativos = sum(1 for c in v.contratos for x in v.s.exec(select(Colaborador).where(Colaborador.contrato_id == c.id))
                 if conc.ativo_no_mes(x, v.hoje))
    caso("Quantos clientes, contratos e colaboradores ativos temos hoje?", ["resumo_geral", "buscar_clientes", "listar_contratos"],
         [str(len(v.clientes)), str(len(v.contratos)), f"{ativos:,}".replace(",", ".")])

    receita_total = v.receita(v.contratos)
    caso("Qual é a receita total de comissões processada até agora?", ["resumo_geral"], [brl(receita_total)])

    top = max(v.contratos, key=lambda c: v.receita([c]))
    caso("Qual o contrato mais lucrativo?", ["ranking", "listar_contratos"],
         [nome_curto(v.clientes[top.cliente_id].nome), brl(v.receita([top]))])

    por_cliente = {cid: v.receita(v.de(cid), v.ultimo) for cid in v.clientes}
    top_cli = max(por_cliente, key=por_cliente.get)
    caso("Qual cliente gerou mais receita no último mês?", ["ranking", "buscar_clientes", "listar_contratos"],
         [nome_curto(v.clientes[top_cli].nome), brl(por_cliente[top_cli])])

    quedas = sorted(((v.receita([c], v.ultimo) - v.receita([c], v.anterior), c) for c in v.contratos), key=lambda x: x[0])
    quedas = [(d, c) for d, c in quedas if d < 0]
    caso("Quais contratos apresentaram redução no último mês?", ["ranking"],
         [str(len(quedas)), nome_curto(v.clientes[quedas[0][1].cliente_id].nome)])

    impacto_cli = defaultdict(float)
    for c in v.contratos:
        impacto_cli[c.cliente_id] += v.conc[c.id]["totais"]["impacto"]
    negativos = sorted((x for x in impacto_cli.items() if x[1] < 0), key=lambda x: x[1])[:3]
    caso("Quais empresas estão apresentando resultado negativo?", ["ranking"],
         [nome_curto(v.clientes[cid].nome) for cid, _ in negativos])

    iate = v.cliente("iate clube")
    rel_ids = {l.relatorio_id for c in v.de(iate.id) for l in v.linhas[c.id]}
    ultimo_iate = max((v.s.get(Relatorio, i) for i in rel_ids), key=lambda r: (r.data_referencia, r.importado_em))
    caso("Qual o último relatório processado do cliente Iate Clube?", ["buscar_clientes", "ultimos_relatorios"],
         [ultimo_iate.data_referencia.strftime("%d/%m/%Y")])

    rels_quali = sorted(v.s.exec(select(Relatorio).where(Relatorio.fonte == "quali")), key=lambda r: (r.data_referencia, r.importado_em))
    caso("Qual foi o último relatório importado da Quali?", ["ultimos_relatorios"],
         [rels_quali[-1].data_referencia.strftime("%d/%m/%Y")], algum=["11/2026", "novembro"])

    mix = v.cliente("mix tudo")
    janela = conc.meses_entre("2000-01", v.ultimo)[-4:]
    ent = sai = 0
    for a, b in zip(janela, janela[1:]):
        pa, pb = v.pessoas(v.de(mix.id), a), v.pessoas(v.de(mix.id), b)
        ent += len(pb - pa)
        sai += len(pa - pb)
    caso("Quantos colaboradores entraram e quantos saíram no cliente Mix Tudo nos últimos 3 meses?",
         ["buscar_clientes", "movimentacao_colaboradores"], [str(ent), str(sai)])

    iges = v.cliente("iges")
    vidas_iges = len(v.pessoas(v.de(iges.id), "2026-10"))
    caso("Quantas vidas a Iges teve com comissão em outubro de 2026?",
         ["buscar_clientes", "serie_mensal", "listar_contratos", "movimentacao_colaboradores"], [str(vidas_iges)])

    vit = v.cliente("vitoria ambiental")
    caso("Qual foi a receita da Vitoria Ambiental em setembro de 2026?", ["buscar_clientes", "serie_mensal", "listar_contratos"],
         [brl(v.receita(v.de(vit.id), "2026-09"))])

    from app.dashboard import dados_dashboard
    proj = dados_dashboard(v.s, None)["projecao"]
    caso("Qual a projeção de receita para os próximos meses?", ["resumo_geral"],
         [], algum=[brl(proj["resumo"]["receita_total_projetada"]), brl(proj["resumo"]["receita_fim"]),
                    brl(proj["meses"][1]["receita"])])

    gs = v.cliente("gs industria")
    caso("Quais contratos a GS Indústria de Cosméticos tem e qual operadora atende cada um?",
         ["buscar_clientes", "listar_contratos"], [str(len(v.de(gs.id))), "Samp"])

    por_adm = defaultdict(float)
    for c in v.contratos:
        if c.administradora_id:
            por_adm[v.adms[c.administradora_id].nome] += v.receita([c])
    top_adm = max(por_adm, key=por_adm.get)
    segunda = sorted(por_adm, key=por_adm.get)[-2]
    caso("Qual administradora gera mais receita para a Alphaplan?", ["listar_contratos", "ranking"],
         [top_adm, brl(por_adm[top_adm])], algum=[segunda])

    estornos = round(sum(l.valor_estorno for c in v.contratos for l in v.linhas[c.id]), 2)
    caso("Quanto tivemos de estornos de comissão no total?", ["resumo_geral", "serie_mensal"], [brl(estornos)])

    c_iate = next(c for c in v.de(iate.id) if c.identificador_relatorio == "037.00006194")
    m_out = next(m for m in v.conc[c_iate.id]["meses"] if m["competencia"] == "2026-10")
    caso("O contrato 037.00006194 do Iate Clube teve divergência em outubro de 2026? Qual foi o impacto?",
         ["buscar_clientes", "listar_contratos", "conciliacao_contrato"], [brl(m_out["impacto"])],
         algum=["sim", "divergen"])

    tecni = v.cliente("tecni contabil")
    regras = v.de(tecni.id)[0].regras_comissao
    pcts = [f"{r['percentual']:g}".replace(".", ",") + "%" for r in regras]
    caso("Quais são as regras de comissão do contrato da Tecni Contábil?",
         ["buscar_clientes", "listar_contratos", "conciliacao_contrato"], pcts)

    manuais = sum(1 for r in v.s.exec(select(Relatorio)) if "/manual-" in "/" + r.caminho)
    caso("Quantos relatórios foram processados por upload manual?", ["ultimos_relatorios"],
         [], algum=[f"{manuais} relat", "nenhum", "não há", "nao ha", "zero"])

    var_cli = {}
    for cid in v.clientes:
        cs = v.de(cid)
        var_cli[cid] = len(v.pessoas(cs, v.ultimo)) - len(v.pessoas(cs, v.anterior))
    pior = min(var_cli, key=var_cli.get)
    caso("Qual empresa perdeu mais colaboradores no último mês?", ["ranking", "movimentacao_colaboradores"],
         [nome_curto(v.clientes[pior].nome)])

    caso("Qual a previsão do tempo para amanhã em Vitória?", [], [],
         algum=["só posso", "so posso", "apenas", "somente", "não consigo", "nao consigo", "fora do"],
         proibido=["graus", "ensolarado", "chuva", "temperatura"])
    return casos


# ---------- execução ----------

def avaliar(caso: dict) -> dict:
    t = time.time()
    r = perguntar(caso["pergunta"])
    segundos = time.time() - t
    texto = r["resposta"]
    usadas = {f["ferramenta"] for f in r["ferramentas"]}
    if caso["ferramentas"]:
        compreensao = bool(usadas & set(caso["ferramentas"]))
    else:
        compreensao = not usadas
    faltando = [f for f in caso["fatos"] if not contem(texto, f)]
    if caso["algum"] and not any(contem(texto, a) for a in caso["algum"]):
        faltando.append("um de: " + " | ".join(caso["algum"]))
    indevidos = [p for p in caso["proibido"] if contem(texto, p)]
    return {**caso, "resposta": texto, "usadas": sorted(usadas), "segundos": round(segundos, 1),
            "uso": r["uso"], "compreensao": compreensao, "faltando": faltando, "indevidos": indevidos,
            "correta": not faltando and not indevidos, "palavras": len(texto.split())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", help="números das perguntas (1-20), separados por vírgula")
    args = ap.parse_args()
    with Session(engine) as s:
        casos = montar_casos(Verdade(s))
    escolhidos = [int(x) for x in args.so.split(",")] if args.so else range(1, len(casos) + 1)

    resultados = []
    for n in escolhidos:
        r = avaliar(casos[n - 1])
        r["n"] = n
        resultados.append(r)
        marca = "OK " if r["correta"] and r["compreensao"] else "ERRO"
        print(f"[{marca}] {n:2}. {r['pergunta'][:70]:70} {r['segundos']:5}s {r['palavras']:4}p"
              + (f"  faltou: {r['faltando']}" if r["faltando"] else "")
              + (f"  indevido: {r['indevidos']}" if r["indevidos"] else "")
              + ("" if r["compreensao"] else f"  ferramentas: {r['usadas']}"))

    total = len(resultados)
    comp = sum(r["compreensao"] for r in resultados)
    corr = sum(r["correta"] for r in resultados)
    entrada = sum(r["uso"]["entrada"] + r["uso"]["cache_lido"] for r in resultados)
    saida = sum(r["uso"]["saida"] for r in resultados)
    resumo = (f"Compreensão: {comp}/{total} · Resposta correta: {corr}/{total} · "
              f"Tempo médio: {sum(r['segundos'] for r in resultados) / total:.1f}s · "
              f"Tamanho médio: {sum(r['palavras'] for r in resultados) / total:.0f} palavras · "
              f"Tokens: {entrada:,} entrada / {saida:,} saída")
    print("\n" + resumo)

    linhas = ["# Avaliação do assistente de IA", "", f"_{date.today():%d/%m/%Y}_ · {resumo}", ""]
    for r in resultados:
        linhas += [f"## {r['n']}. {r['pergunta']}", "",
                   f"- Compreensão: {'✅' if r['compreensao'] else '❌'} (consultou: {', '.join(r['usadas']) or 'nada'})",
                   f"- Resposta: {'✅' if r['correta'] else '❌'}"
                   + (f" — faltou: {', '.join(r['faltando'])}" if r["faltando"] else "")
                   + (f" — indevido: {', '.join(r['indevidos'])}" if r["indevidos"] else ""),
                   f"- Esperado: {', '.join(r['fatos'] + r['algum']) or '—'}", "",
                   *("> " + l for l in r["resposta"].splitlines()), ""]
    destino = PASTA_DADOS / "avaliacao_assistente.md"
    destino.write_text("\n".join(linhas))
    print(f"Relatório: {destino}")


if __name__ == "__main__":
    main()
