"""Tabelas da POC.

Cadastro (o esperado): Operadora, Administradora, Produto, Cliente, Contrato, Colaborador.
Relatórios (o processado): Relatorio (um arquivo baixado) e LinhaRelatorio (uma linha dele,
já no formato padrão, igual para todas as fontes).
"""
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


# ---------- Cadastro ----------

class Operadora(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nome: str
    # Código do conector quando os relatórios vêm direto da operadora (ex.: "samp")
    codigo_fonte: str | None = None


class Administradora(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nome: str
    codigo_fonte: str | None = None  # ex.: "easyplan"


class Produto(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nome: str
    operadora_id: int = Field(foreign_key="operadora.id")
    # Mensalidade por faixa etária ANS (10 valores: 0-18, 19-23, ..., 59+). Opcional.
    tabela_faixas: list[float] | None = Field(default=None, sa_column=Column(JSON))


class Cliente(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nome: str
    cnpj: str | None = None


class Contrato(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    cliente_id: int = Field(foreign_key="cliente.id")
    produto_id: int = Field(foreign_key="produto.id")
    administradora_id: int | None = Field(default=None, foreign_key="administradora.id")
    # Como o contrato aparece no relatório da fonte (ex.: nº do contrato na Samp)
    identificador_relatorio: str
    data_inicio: date
    # [{"parcela_de": 1, "parcela_ate": 1, "percentual": 100}, {"parcela_de": 2, "parcela_ate": null, "percentual": 5}]
    regras_comissao: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    chave_conciliacao: str = "nome"  # "nome" ou "cpf" (cai para nome quando faltar CPF)
    tolerancia: float = 0.05  # diferença de mensalidade aceita, em R$
    observacoes: str | None = None


class Colaborador(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    contrato_id: int = Field(foreign_key="contrato.id", index=True)
    nome: str
    cpf: str | None = None
    data_nascimento: date | None = None
    data_inclusao: date
    data_exclusao: date | None = None
    valor_mensalidade: float  # valor inicial (sem tabela por faixa etária ou sem nascimento)
    # Reajustes: [{"a_partir": "2026-04", "valor": 553.64}] — vale o mais recente até o mês
    historico_mensalidade: list[dict] = Field(default_factory=list, sa_column=Column(JSON))


# ---------- Relatórios ----------

class Relatorio(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    fonte: str = Field(index=True)
    caminho: str  # relativo a dados/brutos
    hash: str = Field(unique=True)
    referencia: str  # texto do portal, ex. "Pagamento de 22/10/2026 a 28/10/2026"
    data_referencia: date
    status: str | None = None
    qtd_linhas: int = 0
    importado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LinhaRelatorio(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    relatorio_id: int = Field(foreign_key="relatorio.id", index=True)
    fonte: str = Field(index=True)
    contrato_ref: str = Field(index=True)
    empresa: str | None = None
    nome: str
    cpf: str | None = None
    competencia: str = Field(index=True)  # "AAAA-MM"
    parcela: int | None = None
    percentual: float | None = None
    valor_base: float = 0
    valor_comissao: float = 0
    valor_estorno: float = 0
