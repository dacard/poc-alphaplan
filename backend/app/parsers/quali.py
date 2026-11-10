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

from collections import Counter

from .comum import ArquivoInvalido, numero_br, separar

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


# ---------- upload manual ----------
ACEITA = ".csv"
INSTRUCOES = "CSV do Relatório de Comissões (botão \"Exportar (CSV)\"), de preferência um mês por arquivo."


def preparar_upload(arquivos: list[tuple[str, bytes]], pasta: Path) -> None:
    grupos = separar(arquivos, "csv")
    if len(grupos["csv"]) != 1:
        raise ArquivoInvalido("Envie um único CSV do relatório da Quali.")
    conteudo = grupos["csv"][0][1]
    (pasta / "comissoes.csv").write_bytes(conteudo)
    linhas = list(csv.DictReader(conteudo.decode("utf-8-sig").splitlines(), delimiter=";"))
    if not linhas or "Mês" not in linhas[0]:
        raise ArquivoInvalido("O CSV não parece o relatório de comissões da Quali (sem a coluna \"Mês\").")
    ano, mes = Counter(l["Mês"].split("-")[0] for l in linhas).most_common(1)[0][0].split("/")
    (pasta / "info.txt").write_text(f"Competência: {ano}-{mes}\nSituação: Upload manual\n")


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
