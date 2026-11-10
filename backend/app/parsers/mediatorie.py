"""Mediatorie: Excel "Extrato Comissao.xlsx" (aba "Exportação SAPUI5"), um por protocolo mensal.

Uma linha por beneficiário e produto, com CPF e data de nascimento.
Empresa = "Nome do Resp. Finan". A mesma pessoa pode ter plano médico e odonto com
percentuais diferentes, então o contrato é "<Contrato Cliente> / Médico|Odonto".
Competência = "Competência" (ex.: "10.2026"). Base = "Valor Competência".
"""
from datetime import date
from pathlib import Path

import pandas as pd

from .comum import numero_br, so_digitos

FONTE = "mediatorie"


def arquivos(pasta_fonte: Path):
    for pasta in sorted(p for p in pasta_fonte.iterdir() if p.is_dir()):
        if (pasta / "extrato.xlsx").exists():
            yield pasta, pasta / "extrato.xlsx"


def metadados(pasta: Path) -> dict:
    info = {}
    if (pasta / "info.txt").exists():
        for linha in (pasta / "info.txt").read_text().splitlines():
            chave, _, valor = linha.partition(":")
            info[chave.strip()] = valor.strip()
    emissao = info.get("Emissão", "")
    return {
        "referencia": f"Protocolo {info.get('Protocolo', pasta.name)}",
        "data_referencia": date(int(emissao[:4]), int(emissao[4:6]), 1) if len(emissao) == 8 else None,
        "status": None,
    }


def _numero(valor) -> float:
    # O Excel do SAP usa ponto decimal ("366.98"); numero_br trata vírgula como decimal
    texto = str(valor).strip()
    return float(texto) if texto and texto.lower() != "nan" and "," not in texto else numero_br(texto)


def ler(arquivo: Path) -> list[dict]:
    df = pd.read_excel(arquivo, dtype=str).fillna("")
    linhas = []
    for r in df.to_dict("records"):
        mes, ano = r["Competência"].strip().split(".")
        produto = "Odonto" if "odonto" in r["Texto Breve Material"].lower() else "Médico"
        comissao = _numero(r["Valor da Comissão"])
        nascimento = r["Dt.Nascimento Beneficiário"].strip()[:10]
        linhas.append({
            "contrato_ref": f"{int(r['Contrato Cliente'])} / {produto}",
            "empresa": r["Nome do Resp. Finan"].strip(),
            "nome": r["Nome do Beneficiário"].strip(),
            "cpf": so_digitos(r["CPF"]),
            "data_nascimento": date.fromisoformat(nascimento) if nascimento else None,
            "competencia": f"{ano}-{mes}",
            "parcela": int(r["Parcela"]) if r["Parcela"].strip().isdigit() else None,
            "percentual": _numero(r["Percentual de Comissão"]) if r["Percentual de Comissão"].strip() else None,
            "valor_base": _numero(r["Valor Competência"]),
            "valor_comissao": comissao,
            "valor_estorno": -comissao if comissao < 0 else 0.0,
        })
    return linhas
