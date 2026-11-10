"""API da POC. Rodar a partir de backend/:  ../.venv/bin/uvicorn app.main:app --reload"""
from collections import defaultdict
from datetime import date

from fastapi import Body, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, func, select

import anthropic

from . import coletas
from . import conciliacao as conc
from .db import RAIZ, criar_tabelas, get_session
from .assistente import agente
from .dashboard import dados_dashboard
from .importador import importar, remover_relatorio
from .models import (Administradora, Cliente, Colaborador, Contrato, LinhaRelatorio, Operadora,
                     Produto, Relatorio)
from .parsers import PARSERS
from .parsers.comum import ArquivoInvalido

app = FastAPI(title="POC Alphaplan - Conciliação de comissões")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
criar_tabelas()


@app.exception_handler(ValidationError)
def erro_validacao(_, exc: ValidationError):
    campos = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
    return JSONResponse(status_code=422, content={"detail": f"Dados inválidos - {campos}"})

SessionDep = Depends(get_session)


# ---------- CRUD genérico ----------

def crud(prefixo: str, modelo: type[SQLModel], dependentes: list[tuple[type[SQLModel], str]] = ()):
    @app.get(f"/api/{prefixo}", tags=[prefixo])
    def listar(session: Session = SessionDep):
        return session.exec(select(modelo)).all()

    @app.get(f"/api/{prefixo}/{{item_id}}", tags=[prefixo])
    def obter(item_id: int, session: Session = SessionDep):
        return _obter(session, modelo, item_id)

    @app.post(f"/api/{prefixo}", tags=[prefixo])
    def criar(dados: dict = Body(...), session: Session = SessionDep):
        dados.pop("id", None)
        item = modelo.model_validate(dados)
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    @app.put(f"/api/{prefixo}/{{item_id}}", tags=[prefixo])
    def atualizar(item_id: int, dados: dict = Body(...), session: Session = SessionDep):
        item = _obter(session, modelo, item_id)
        dados.pop("id", None)
        validado = modelo.model_validate({**item.model_dump(), **dados})
        for campo, valor in validado.model_dump(exclude={"id"}).items():
            setattr(item, campo, valor)
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    @app.delete(f"/api/{prefixo}/{{item_id}}", tags=[prefixo])
    def remover(item_id: int, session: Session = SessionDep):
        item = _obter(session, modelo, item_id)
        for dep, campo in dependentes:
            if session.exec(select(dep).where(getattr(dep, campo) == item_id)).first():
                raise HTTPException(409, f"Existem registros em '{dep.__name__}' ligados a este item")
        session.delete(item)
        session.commit()
        return {"ok": True}


def _obter(session, modelo, item_id):
    item = session.get(modelo, item_id)
    if not item:
        raise HTTPException(404, f"{modelo.__name__} {item_id} não encontrado")
    return item


crud("operadoras", Operadora, [(Produto, "operadora_id")])
crud("administradoras", Administradora, [(Contrato, "administradora_id")])
crud("produtos", Produto, [(Contrato, "produto_id")])
crud("clientes", Cliente, [(Contrato, "cliente_id")])
crud("contratos", Contrato, [(Colaborador, "contrato_id")])
crud("colaboradores", Colaborador)


# ---------- Assistente de IA ----------

@app.post("/api/assistente", tags=["assistente"])
def assistente(dados: dict = Body(...)):
    """{"mensagem": "...", "conversa_id": "..."} -> resposta do assistente."""
    mensagem = (dados.get("mensagem") or "").strip()
    if not mensagem:
        raise HTTPException(422, "Mensagem vazia")
    try:
        return agente.perguntar(mensagem[:2000], dados.get("conversa_id"))
    except anthropic.AuthenticationError:
        raise HTTPException(503, "Assistente indisponível: verifique ANTHROPIC_API_KEY no .env")
    except anthropic.RateLimitError:
        raise HTTPException(429, "Muitas perguntas seguidas. Aguarde alguns segundos e tente de novo.")
    except anthropic.APIStatusError as erro:
        raise HTTPException(502, f"Erro na API de IA ({erro.status_code}). Tente novamente.")
    except anthropic.APIConnectionError:
        raise HTTPException(503, "Sem conexão com a API de IA.")


@app.delete("/api/assistente/{conversa_id}", tags=["assistente"])
def limpar_conversa(conversa_id: str):
    agente.nova_conversa(conversa_id)
    return {"ok": True}


# ---------- Dashboard ----------

@app.get("/api/dashboard", tags=["telas"])
def dashboard(clientes: str | None = None, session: Session = SessionDep):
    """clientes: ids separados por vírgula; ausente = todos."""
    ids = None if clientes is None else [int(x) for x in clientes.split(",") if x.strip()]
    return dados_dashboard(session, ids)


# ---------- Visões enriquecidas para as telas ----------

def _resumo_contrato(session: Session, c: Contrato, com_conciliacao: bool = True) -> dict:
    produto = session.get(Produto, c.produto_id)
    operadora = session.get(Operadora, produto.operadora_id)
    adm = session.get(Administradora, c.administradora_id) if c.administradora_id else None
    hoje = date.today().strftime("%Y-%m")
    colabs = session.exec(select(Colaborador).where(Colaborador.contrato_id == c.id)).all()
    resumo = {
        **c.model_dump(),
        "cliente": session.get(Cliente, c.cliente_id).nome,
        "produto": produto.nome,
        "operadora": operadora.nome,
        "administradora": adm.nome if adm else None,
        "fonte": conc.fonte_do_contrato(session, c),
        "colaboradores_ativos": sum(1 for x in colabs if conc.ativo_no_mes(x, hoje)),
        "colaboradores_total": len(colabs),
    }
    if com_conciliacao:
        r = conc.conciliar_contrato(session, c)
        ultimo = r["meses"][0] if r["meses"] else None
        resumo["conciliacao"] = {**r["totais"], "ultimo_mes": ultimo and {
            k: ultimo[k] for k in ("competencia", "status", "impacto")}}
    return resumo


@app.get("/api/clientes-resumo", tags=["telas"])
def clientes_resumo(session: Session = SessionDep):
    saida = []
    for cli in session.exec(select(Cliente).order_by(Cliente.nome)).all():
        contratos = session.exec(select(Contrato).where(Contrato.cliente_id == cli.id)).all()
        resumos = [_resumo_contrato(session, c) for c in contratos]
        saida.append({
            **cli.model_dump(),
            "contratos": len(contratos),
            "colaboradores_ativos": sum(r["colaboradores_ativos"] for r in resumos),
            "meses_divergentes": sum(r["conciliacao"]["meses_divergentes"] for r in resumos),
            "impacto": round(sum(r["conciliacao"]["impacto"] for r in resumos), 2),
        })
    return saida


@app.get("/api/clientes/{cliente_id}/contratos", tags=["telas"])
def contratos_do_cliente(cliente_id: int, session: Session = SessionDep):
    contratos = session.exec(select(Contrato).where(Contrato.cliente_id == cliente_id)).all()
    return [_resumo_contrato(session, c) for c in contratos]


@app.get("/api/contratos/{contrato_id}/resumo", tags=["telas"])
def contrato_resumo(contrato_id: int, session: Session = SessionDep):
    return _resumo_contrato(session, _obter(session, Contrato, contrato_id), com_conciliacao=False)


@app.get("/api/contratos/{contrato_id}/colaboradores", tags=["telas"])
def colaboradores_do_contrato(contrato_id: int, session: Session = SessionDep):
    return session.exec(select(Colaborador).where(Colaborador.contrato_id == contrato_id)
                        .order_by(Colaborador.nome)).all()


@app.get("/api/contratos/{contrato_id}/relatorios", tags=["telas"])
def relatorios_do_contrato(contrato_id: int, session: Session = SessionDep):
    contrato = _obter(session, Contrato, contrato_id)
    agrupado = defaultdict(lambda: {"linhas": 0, "comissao": 0.0, "pessoas": set(), "competencias": set()})
    for l in conc.linhas_do_contrato(session, contrato):
        g = agrupado[l.relatorio_id]
        g["linhas"] += 1
        g["comissao"] += l.valor_comissao
        g["pessoas"].add(l.nome)
        g["competencias"].add(l.competencia)
    saida = []
    for rel_id, g in agrupado.items():
        rel = session.get(Relatorio, rel_id)
        saida.append({**rel.model_dump(), "linhas_contrato": g["linhas"], "pessoas": len(g["pessoas"]),
                      "comissao": round(g["comissao"], 2), "competencias": sorted(g["competencias"])})
    return sorted(saida, key=lambda r: r["data_referencia"] or date.min, reverse=True)


@app.get("/api/contratos/{contrato_id}/conciliacao", tags=["telas"])
def conciliacao_do_contrato(contrato_id: int, session: Session = SessionDep):
    return conc.conciliar_contrato(session, _obter(session, Contrato, contrato_id))


@app.post("/api/contratos/{contrato_id}/acoes", tags=["telas"])
def acao_divergencia(contrato_id: int, dados: dict = Body(...), session: Session = SessionDep):
    """Resolve uma divergência atualizando o cadastro.

    {"acao": "incluir", "nome", "cpf", "valor_mensalidade", "competencia"}  -> novo colaborador
    {"acao": "desligar", "colaborador_id", "competencia"}                    -> data de exclusão
    {"acao": "reajustar", "itens": [{"colaborador_id", "valor"}], "competencia"} -> nova mensalidade
    """
    _obter(session, Contrato, contrato_id)
    inicio_mes = date.fromisoformat(dados["competencia"] + "-01")
    if dados["acao"] == "incluir":
        item = Colaborador(contrato_id=contrato_id, nome=dados["nome"], cpf=dados.get("cpf"),
                           data_inclusao=inicio_mes, valor_mensalidade=dados["valor_mensalidade"])
    elif dados["acao"] == "reajustar":
        for it in dados["itens"]:
            colab = _obter(session, Colaborador, it["colaborador_id"])
            historico = [h for h in (colab.historico_mensalidade or []) if h["a_partir"] != dados["competencia"]]
            historico.append({"a_partir": dados["competencia"], "valor": float(it["valor"])})
            colab.historico_mensalidade = sorted(historico, key=lambda h: h["a_partir"])
            session.add(colab)
        session.commit()
        return {"ok": True, "reajustados": len(dados["itens"])}
    elif dados["acao"] == "desligar":
        item = _obter(session, Colaborador, dados["colaborador_id"])
        item.data_exclusao = inicio_mes
    else:
        raise HTTPException(400, "Ação desconhecida")
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


# ---------- Relatórios, coleta e importação ----------

@app.get("/api/fontes", tags=["relatorios"])
def fontes(session: Session = SessionDep):
    """Uma linha por fonte: nome, relatórios importados, último relatório, coleta e upload."""
    nomes = {o.codigo_fonte: o.nome for o in session.exec(select(Operadora)) if o.codigo_fonte}
    nomes |= {a.codigo_fonte: a.nome for a in session.exec(select(Administradora)) if a.codigo_fonte}
    resumo = {f: (n, ultimo, importado) for f, n, ultimo, importado in session.exec(
        select(Relatorio.fonte, func.count(), func.max(Relatorio.data_referencia), func.max(Relatorio.importado_em))
        .group_by(Relatorio.fonte)).all()}
    saida = []
    for codigo, parser in PARSERS.items():
        n, ultimo, importado = resumo.get(codigo, (0, None, None))
        saida.append({
            "codigo": codigo,
            "nome": nomes.get(codigo, codigo),
            "relatorios": n,
            "ultimo_relatorio": ultimo,
            "ultima_importacao": importado,
            "tem_robo": (RAIZ / "playwright-scripts" / f"{codigo}.py").exists(),
            "aceita": getattr(parser, "ACEITA", None),
            "instrucoes": getattr(parser, "INSTRUCOES", None),
            "coleta": coletas.estado(codigo),
        })
    return saida


@app.get("/api/relatorios", tags=["relatorios"])
def relatorios(fonte: str | None = None, session: Session = SessionDep):
    q = select(Relatorio).order_by(Relatorio.data_referencia.desc())
    if fonte:
        q = q.where(Relatorio.fonte == fonte)
    return session.exec(q).all()


@app.get("/api/relatorios/{relatorio_id}/linhas", tags=["relatorios"])
def linhas_do_relatorio(relatorio_id: int, contrato_ref: str | None = None, session: Session = SessionDep):
    q = select(LinhaRelatorio).where(LinhaRelatorio.relatorio_id == relatorio_id)
    if contrato_ref:
        q = q.where(LinhaRelatorio.contrato_ref == contrato_ref)
    return session.exec(q.order_by(LinhaRelatorio.nome)).all()


@app.delete("/api/relatorios/{relatorio_id}", tags=["relatorios"])
def excluir_relatorio(relatorio_id: int, session: Session = SessionDep):
    """Remove o relatório e suas linhas. Se veio de upload manual, apaga também os arquivos
    (os baixados pelo robô ficam em disco e voltariam numa próxima importação)."""
    manual = remover_relatorio(session, _obter(session, Relatorio, relatorio_id))
    session.commit()
    return {"ok": True, "arquivos_removidos": manual}


@app.post("/api/importar", tags=["relatorios"])
def importar_relatorios(fonte: str | None = None, session: Session = SessionDep):
    return importar(session, fonte)


@app.post("/api/coletar/{fonte}", tags=["relatorios"])
def coletar(fonte: str):
    """Inicia o robô de coleta da fonte em segundo plano; acompanhe em /api/fontes."""
    try:
        return coletas.iniciar_coleta(fonte)
    except KeyError as erro:
        raise HTTPException(404, str(erro))


@app.post("/api/upload/{fonte}", tags=["relatorios"])
async def upload(fonte: str, arquivos: list[UploadFile] = File(...)):
    """Upload manual (ex.: relatório recebido por e-mail quando o portal está fora do ar)."""
    recebidos = [(a.filename or "arquivo", await a.read()) for a in arquivos]
    try:
        return coletas.receber_upload(fonte, recebidos)
    except KeyError as erro:
        raise HTTPException(404, str(erro))
    except ArquivoInvalido as erro:
        raise HTTPException(422, str(erro))
