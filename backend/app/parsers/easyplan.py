"""Easyplan: Excel 'Relatório_-_*.xlsx' (aba 'Relatório').

Uma linha por colaborador. PRODUTOR = empresa cliente; NOME CONTRATO = colaborador.
Cada MODALIDADE tem percentuais próprios (produtos diferentes), então o contrato é
identificado por "<PRODUTOR> / Modalidade <MODALIDADE>".
Competência = mês da PREVISÃO PAGAMENTO. Comissão líquida = provisionado - estorno.
"""
from datetime import datetime
from pathlib import Path

import pandas as pd

from .comum import numero_br, so_digitos

FONTE = "easyplan"


def arquivos(pasta_fonte: Path):
    for pasta in sorted(p for p in pasta_fonte.iterdir() if p.is_dir()):
        xlsx = list(pasta.glob("*.xlsx"))
        if xlsx:
            yield pasta, xlsx[0]


def metadados(pasta: Path) -> dict:
    info = {}
    if (pasta / "info.txt").exists():
        for linha in (pasta / "info.txt").read_text().splitlines():
            chave, _, valor = linha.partition(":")
            info[chave.strip()] = valor.strip()
    data = info.get("Data Relatório")
    return {
        "referencia": f"Relatório de {data}" if data else pasta.name,
        "data_referencia": datetime.strptime(data, "%d/%m/%Y").date() if data else None,
        "status": info.get("Status Pagamento"),
    }


def contrato_ref(produtor: str, modalidade: str) -> str:
    return f"{produtor.strip()} / Modalidade {modalidade.strip()}"


def ler(arquivo: Path) -> list[dict]:
    df = pd.read_excel(arquivo, dtype=str).fillna("")
    linhas = []
    for r in df.to_dict("records"):
        previsao = datetime.strptime(r["PREVISÃO PAGAMENTO"].strip(), "%d/%m/%Y")
        provisionado = numero_br(r["VALOR PROVISIONADO"])
        estorno = numero_br(r["VALOR ESTORNO"])
        linhas.append({
            "contrato_ref": contrato_ref(r["PRODUTOR"], r["MODALIDADE"]),
            "empresa": r["PRODUTOR"].strip(),
            "nome": r["NOME CONTRATO"].strip(),
            "cpf": so_digitos(r["CPF / CNPJ"]),
            "competencia": previsao.strftime("%Y-%m"),
            "parcela": int(r["PARCELA"]) if r["PARCELA"].strip() else None,
            "percentual": numero_br(r["% COMISSÃO"]),
            "valor_base": numero_br(r["VALOR CONTRATO"]),
            "valor_comissao": round(provisionado - estorno, 2),
            "valor_estorno": estorno,
        })
    return linhas
