"""Quali: CSV do "Relatório de Comissões" (UTF-8 com BOM, separador ';'), um arquivo por mês.

Uma linha por beneficiário e parcela. Empresa = "Nome da Empresa"; o contrato é identificado
pelo "Código da Empresa". Beneficiário vem como "<código> <NOME>".
Competência = "Mês" (ex.: "2026/10-1" = outubro, 1ª quinzena).
Tipo "Prov." = provento; "Est." = estorno (valor negativo).
O percentual aparece no texto da coluna "Comissão" ("... - Comissão(%): 3,00").
"""
import csv
import re
from datetime import date
from pathlib import Path

from .comum import numero_br

FONTE = "quali"
PERCENTUAL = re.compile(r"Comissão\(%\):\s*([\d.,]+)")


def arquivos(pasta_fonte: Path):
    for pasta in sorted(p for p in pasta_fonte.iterdir() if p.is_dir()):
        if (pasta / "comissoes.csv").exists():
            yield pasta, pasta / "comissoes.csv"


def metadados(pasta: Path) -> dict:
    info = {}
    if (pasta / "info.txt").exists():
        for linha in (pasta / "info.txt").read_text().splitlines():
            chave, _, valor = linha.partition(":")
            info[chave.strip()] = valor.strip()
    comp = info.get("Competência", pasta.name)
    ano, mes = comp.split("-")
    return {
        "referencia": f"Comissões de {mes}/{ano}",
        "data_referencia": date(int(ano), int(mes), 1),
        "status": info.get("Situação"),
    }


def ler(arquivo: Path) -> list[dict]:
    linhas = []
    with open(arquivo, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            ano_mes = r["Mês"].strip().split("-")[0]  # "2026/10-1" -> "2026/10"
            ano, mes = ano_mes.split("/")
            parcela = r["Parc."].split("/")[0].strip()
            pct = PERCENTUAL.search(r["Comissão"] or "")
            valor = numero_br(r["Valor"])
            linhas.append({
                "contrato_ref": r["Código da Empresa"].strip(),
                "empresa": r["Nome da Empresa"].strip(),
                "nome": re.sub(r"^\S+\s+", "", r["Beneficiário"].strip()),
                "cpf": None,
                "competencia": f"{ano}-{mes}",
                "parcela": int(parcela) if parcela.isdigit() else None,
                "percentual": numero_br(pct.group(1)) if pct else None,
                "valor_base": abs(numero_br(r["Vlr. Bol"])),
                "valor_comissao": valor,
                "valor_estorno": -valor if valor < 0 else 0.0,
            })
    return linhas
