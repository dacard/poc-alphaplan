"""Samp: CSV 'Planilha_do_Pagamento_*.csv' (separador ';', latin-1).

Uma linha por beneficiário e parcela. Competência = mês do VENCIMENTO da mensalidade.
O nº do CONTRATO identifica o contrato do cliente (EMPRESA/TITULAR).
Estornos vêm com COMISSAO negativa e sem VENCIMENTO: a competência passa a ser a da
parcela estornada (mês de DT. INCLUSAO + PARCELA - 1).
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

import io
import zipfile

from .comum import ArquivoInvalido, hoje_br, numero_br, separar

FONTE = "samp"


def arquivos(pasta_fonte: Path):
    """Um relatório por pasta de pagamento."""
    for pasta in sorted(p for p in pasta_fonte.iterdir() if p.is_dir()):
        csvs = [f for f in pasta.glob("*.csv") if not f.name.lower().endswith("nao_pagos.csv")]
        if csvs:
            yield pasta, csvs[0]


def metadados(pasta: Path) -> dict:
    texto = (pasta / "referencia.txt").read_text().strip() if (pasta / "referencia.txt").exists() else ""
    vencimento, _, referencia = texto.partition("|")
    data = datetime.strptime(vencimento.strip(), "%d/%m/%Y").date() if vencimento.strip() else None
    status = "Upload manual" if pasta.name.startswith("manual-") else "Confirmada"
    return {"referencia": referencia.strip() or pasta.name, "data_referencia": data, "status": status}


# ---------- upload manual ----------
ACEITA = ".zip,.csv"
INSTRUCOES = ("ZIP do recibo completo, como vem do portal/e-mail, ou só o CSV "
              "\"Planilha_do_Pagamento_*.csv\" (não o de não pagos).")


def preparar_upload(arquivos: list[tuple[str, bytes]], pasta: Path) -> None:
    grupos = separar(arquivos, "zip", "csv")
    candidatos = []
    for nome, conteudo in grupos["zip"]:
        (pasta / nome).write_bytes(conteudo)
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            z.extractall(pasta / "extraido")
        candidatos += [(f.name, f.read_bytes()) for f in (pasta / "extraido").rglob("*.csv")]
    candidatos += grupos["csv"]
    pagamento = [(n, c) for n, c in candidatos if not n.lower().endswith("nao_pagos.csv")]
    if len(pagamento) != 1:
        raise ArquivoInvalido("Envie exatamente uma planilha de pagamento da Samp "
                              "(o CSV que não termina em Nao_pagos), direto ou dentro do ZIP.")
    nome, conteudo = pagamento[0]
    (pasta / nome).write_bytes(conteudo)
    (pasta / "referencia.txt").write_text(f"{hoje_br()} | Upload manual — {nome}\n")


def ler(arquivo: Path) -> list[dict]:
    df = pd.read_csv(arquivo, sep=";", dtype=str, encoding="latin-1")
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")].fillna("")
    linhas = []
    for r in df.to_dict("records"):
        parcela = int(r["PARCELA"]) if r["PARCELA"].strip() else None
        comissao = numero_br(r["COMISSAO"])
        if r["VENCIMENTO"].strip():
            competencia = datetime.strptime(r["VENCIMENTO"].strip(), "%d/%m/%Y").strftime("%Y-%m")
        else:
            inclusao = datetime.strptime(r["DT. INCLUSAO"].strip(), "%d/%m/%y")
            meses = inclusao.year * 12 + inclusao.month - 1 + (parcela or 1) - 1
            competencia = f"{meses // 12:04d}-{meses % 12 + 1:02d}"
        linhas.append({
            "contrato_ref": r["CONTRATO"].strip(),
            "empresa": r["EMPRESA/TITULAR"].strip(),
            "nome": r["HISTORICO"].strip(),
            "cpf": None,
            "competencia": competencia,
            "parcela": parcela,
            "percentual": numero_br(r["PERC"]),
            "valor_base": numero_br(r["VALOR BASE"]),
            "valor_comissao": comissao,
            "valor_estorno": -comissao if comissao < 0 else 0.0,
        })
    return linhas
