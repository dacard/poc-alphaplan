"""API da POC. Rodar a partir de backend/:  ../.venv/bin/uvicorn app.main:app --reload"""
import subprocess
import sys
from collections import defaultdict
from datetime import date

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, func, select

from . import conciliacao as conc
from .db import RAIZ, criar_tabelas, get_session
from .dashboard import dados_dashboard
from .importador import importar
from .models import (Administradora, Cliente, Colaborador, Contrato, LinhaRelatorio, Operadora,
                     Produto, Relatorio)
from .parsers import PARSERS

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
    contagem = dict(session.exec(select(Relatorio.fonte, func.count()).group_by(Relatorio.fonte)).all())
    return [{"codigo": c, "relatorios": contagem.get(c, 0)} for c in PARSERS]


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


@app.post("/api/importar", tags=["relatorios"])
def importar_relatorios(fonte: str | None = None, session: Session = SessionDep):
    return importar(session, fonte)


@app.post("/api/coletar/{fonte}", tags=["relatorios"])
def coletar(fonte: str, session: Session = SessionDep):
    """Roda o robô de coleta da fonte (Playwright) e importa o que foi baixado."""
    script = RAIZ / "playwright-scripts" / f"{fonte}.py"
    if fonte not in PARSERS or not script.exists():
        raise HTTPException(404, f"Fonte '{fonte}' sem script de coleta")
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        raise HTTPException(500, f"Falha na coleta: {proc.stderr[-1500:]}")
    return {"saida": proc.stdout[-3000:], "importacao": importar(session, fonte)}
