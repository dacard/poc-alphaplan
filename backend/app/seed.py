"""Monta uma base de demonstração a partir dos relatórios reais já baixados.

ATENÇÃO: apaga dados/poc.db e recria do zero.

Como a POC não tem o cadastro real dos contratos, ele é simulado assim:
  - um cliente por empresa (Samp: EMPRESA/TITULAR; Easyplan: PRODUTOR; Up Health: Nome/Empresa Titular; Quali: Nome da Empresa);
  - um contrato por identificador de contrato no relatório;
  - regra de comissão = percentual mais comum na parcela 1 e nas demais;
  - colaboradores = quem aparece no "mês base" do contrato (1º mês com volume normal),
    com a mensalidade daquele mês. É o retrato do contrato no dia em que foi cadastrado.
A partir daí, entradas, saídas e mudanças de valor nos meses seguintes aparecem como divergências.

Rodar a partir de backend/:  ../.venv/bin/python -m app.seed
"""
from collections import Counter, defaultdict
from datetime import date
from statistics import median

from sqlmodel import Session, select

from .db import ARQUIVO_DB, engine
from .importador import importar
from .models import Administradora, Cliente, Colaborador, Contrato, LinhaRelatorio, Operadora, Produto
from .parsers.comum import normalizar_nome


def _mes_base(linhas_por_mes: dict[str, list]) -> str:
    """1º mês cujo volume chega a 80% da mediana mensal (evita meses de início parcial)."""
    meses = sorted(linhas_por_mes)
    alvo = 0.8 * median(len(v) for v in linhas_por_mes.values())
    return next(m for m in meses if len(linhas_por_mes[m]) >= alvo)


def _moda(valores, padrao):
    valores = [v for v in valores if v is not None]
    return Counter(valores).most_common(1)[0][0] if valores else padrao


def _regras(linhas, primeiras: int = 3) -> list[dict]:
    """Percentual mais comum em cada uma das primeiras parcelas e nas demais.

    Ex.: agenciamento dividido (parcelas 1-2 = 50%) e vitalício (3 em diante = 3%).
    Faixas vizinhas com o mesmo percentual são unidas.
    """
    pagos = [l for l in linhas if l.valor_comissao > 0]
    demais = _moda([l.percentual for l in pagos if (l.parcela or 0) > primeiras],
                   _moda([l.percentual for l in pagos if (l.parcela or 0) > 1], 100.0))
    faixas = []
    for n in range(1, primeiras + 1):
        faixas.append([n, n, _moda([l.percentual for l in pagos if l.parcela == n], demais)])
    faixas.append([primeiras + 1, None, demais])
    unidas = [faixas[0]]
    for f in faixas[1:]:
        if f[2] == unidas[-1][2]:
            unidas[-1][1] = f[1]
        else:
            unidas.append(f)
    return [{"parcela_de": de, "parcela_ate": ate, "percentual": pct} for de, ate, pct in unidas]


def criar_contrato(session, cliente, produto, adm, ref, linhas, chave):
    por_mes = defaultdict(list)
    for l in linhas:
        por_mes[l.competencia].append(l)
    base = _mes_base(por_mes)
    inicio = date.fromisoformat(base + "-01")

    contrato = Contrato(cliente_id=cliente.id, produto_id=produto.id,
                        administradora_id=adm.id if adm else None,
                        identificador_relatorio=ref, data_inicio=inicio,
                        regras_comissao=_regras(linhas), chave_conciliacao=chave,
                        observacoes=f"Gerado automaticamente a partir dos relatórios (mês base {base})")
    session.add(contrato)
    session.flush()

    vistos = {}
    for l in por_mes[base]:
        vistos.setdefault(normalizar_nome(l.nome), l)
    for l in vistos.values():
        session.add(Colaborador(contrato_id=contrato.id, nome=l.nome.title(), cpf=l.cpf,
                                data_inclusao=inicio, valor_mensalidade=l.valor_base))
    return contrato, len(vistos)


def main():
    ARQUIVO_DB.unlink(missing_ok=True)
    from .db import criar_tabelas
    criar_tabelas()

    with Session(engine) as s:
        samp = Operadora(nome="Samp", codigo_fonte="samp")
        bluzz = Operadora(nome="Bluzz Saúde")
        easyplan = Administradora(nome="Easyplan", codigo_fonte="easyplan")
        uphealth = Administradora(nome="Up Health", codigo_fonte="uphealth")
        quali = Administradora(nome="Quali", codigo_fonte="quali")
        s.add_all([samp, bluzz, easyplan, uphealth, quali, Operadora(nome="Unimed"), Operadora(nome="Amil"),
                   Administradora(nome="Benevix"), Administradora(nome="Mediatorie")])
        s.commit()

        print("Importando relatórios:", importar(s))

        prod_samp = Produto(nome="Samp Empresarial", operadora_id=samp.id)
        prod_bluzz = Produto(nome="Bluzz Saúde Adesão", operadora_id=bluzz.id)
        prod_samp_tipo = {t: Produto(nome=f"Samp {t}", operadora_id=samp.id) for t in ("Médico", "Dental")}
        # O relatório da Quali não informa a operadora
        op_indefinida = Operadora(nome="Operadora não informada")
        s.add(op_indefinida)
        s.flush()
        prod_quali = Produto(nome="Plano Quali", operadora_id=op_indefinida.id)
        s.add_all([prod_samp, prod_bluzz, prod_quali, *prod_samp_tipo.values()])
        s.flush()

        linhas = s.exec(select(LinhaRelatorio)).all()
        por_ref = defaultdict(list)
        for l in linhas:
            por_ref[(l.fonte, l.contrato_ref)].append(l)

        clientes: dict[str, Cliente] = {}

        def cliente(nome):
            if nome not in clientes:
                clientes[nome] = Cliente(nome=nome)
                s.add(clientes[nome])
                s.flush()
            return clientes[nome]

        for (fonte, ref), ls in sorted(por_ref.items()):
            cli = cliente(_moda([l.empresa for l in ls], ref).title())
            if fonte == "samp":
                c, n = criar_contrato(s, cli, prod_samp, None, ref, ls, "nome")
            elif fonte == "quali":
                c, n = criar_contrato(s, cli, prod_quali, quali, ref, ls, "nome")
            elif fonte == "uphealth":
                produto = prod_samp_tipo[ref.split(" / ")[-1]]
                c, n = criar_contrato(s, cli, produto, uphealth, ref, ls, "nome")
            else:
                c, n = criar_contrato(s, cli, prod_bluzz, easyplan, ref, ls, "cpf")
            print(f"  {cli.nome[:45]:45} {ref:28} início {c.data_inicio}  {n:4} colaboradores")
        s.commit()
        print(f"{len(clientes)} clientes, {len(por_ref)} contratos")


if __name__ == "__main__":
    main()
