"""Up Health: extrato mensal em TXT + PDF.

TXT (latin-1, campos separados por '#', quebras de linha misturadas CR/LF/CRLF):
  cabeçalho do extrato, depois a tabela a partir da linha "Porte Contrato#Fatura#...".
  Tem todos os valores, mas NÃO tem o nome do beneficiário.
PDF: mesma tabela em texto corrido, com o nome do beneficiário ("<proposta> - <NOME>").
  Usado só para completar o nome, casando por fatura + parcela + base + comissão.

Uma linha por beneficiário/item. Empresa = "Nome/Empresa Titular". O percentual muda entre
Médico e Dental, então o contrato é identificado por "<nº do contrato> / <Tipo Produto>".
Competência = "Mês Referência".
"""
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pdfplumber

from .comum import numero_br

FONTE = "uphealth"

LINHA_PDF = re.compile(
    r"^(?P<fatura>\d+) (?P<proposta>\d+) - (?P<nome>.+?)\s*(?P<parcela>\d+) (?P<ref>\d{2}/\d{4}) "
    r"(?P<valor_fatura>[\d.]+,\d{2})\s*(?P<produto>Médico|Dental) (?P<vidas>\d+) "
    r"(?P<vencimento>\d{2}/\d{2}/\d{4}) (?P<operacao>\d{2}/\d{2}/\d{4})\s*(?P<funcao>.*?) "
    r"(?P<percentual>[\d.]+,\d{2}) (?P<base>[\d.]+,\d{2}) (?P<comissao>-?[\d.]+,\d{2})$")


def arquivos(pasta_fonte: Path):
    for pasta in sorted(p for p in pasta_fonte.iterdir() if p.is_dir()):
        if (pasta / "extrato.txt").exists():
            yield pasta, pasta / "extrato.txt"


def metadados(pasta: Path) -> dict:
    info = {}
    if (pasta / "info.txt").exists():
        for linha in (pasta / "info.txt").read_text().splitlines():
            chave, _, valor = linha.partition(":")
            info[chave.strip()] = valor.strip()
    fim = info.get("Período Final")
    return {
        "referencia": f"Extrato {info.get('Extrato', '?')} — {info.get('Período Inicial', '?')} a {fim or '?'}",
        "data_referencia": datetime.strptime(fim, "%d/%m/%Y").date() if fim else None,
        "status": info.get("Situação"),
    }


def _chave(fatura, parcela, base, comissao):
    return (fatura.strip(), parcela.strip(), round(numero_br(base), 2), round(numero_br(comissao), 2))


def nomes_do_pdf(arquivo_pdf: Path) -> dict[tuple, list[str]]:
    """{(fatura, parcela, base, comissão): [nomes...]} — lista porque pode haver valores repetidos."""
    nomes = defaultdict(list)
    if not arquivo_pdf.exists():
        return nomes
    with pdfplumber.open(arquivo_pdf) as pdf:
        for pagina in pdf.pages:
            for linha in (pagina.extract_text() or "").splitlines():
                m = LINHA_PDF.match(linha.strip())
                if m:
                    nomes[_chave(m["fatura"], m["parcela"], m["base"], m["comissao"])].append(m["nome"].strip())
    return nomes


def ler_txt(arquivo: Path) -> list[dict]:
    texto = arquivo.read_text(encoding="latin-1")
    linhas = re.split(r"\r\n|\r|\n", texto)
    inicio = next(i for i, l in enumerate(linhas) if l.startswith("Porte Contrato#"))
    cabecalho = linhas[inicio].split("#")
    registros = []
    for l in linhas[inicio + 1:]:
        if not l.strip() or l.startswith("#"):
            break  # fim da tabela (começa o "Quadro Resumo")
        campos = l.split("#")
        if len(campos) == len(cabecalho):
            registros.append(dict(zip(cabecalho, campos)))
    return registros


def ler(arquivo: Path) -> list[dict]:
    nomes = nomes_do_pdf(arquivo.with_name("extrato.pdf"))
    linhas = []
    for r in ler_txt(arquivo):
        chave = _chave(r["Fatura"], r["Parcela"], r["Base Cálculo"], r["Comissão"])
        nome = nomes[chave].pop(0) if nomes.get(chave) else f"Item {r['Item de Venda'].strip()}"
        mes, ano = r["Mês Referência"].strip().split("/")
        comissao = numero_br(r["Comissão"])
        numero_contrato = r["Contrato"].strip().split(" ")[0]
        linhas.append({
            "contrato_ref": f"{numero_contrato} / {r['Tipo Produto'].strip()}",
            "empresa": r["Nome/Empresa Titular"].strip(),
            "nome": nome,
            "cpf": None,
            "competencia": f"{ano}-{mes}",
            "parcela": int(r["Parcela"]) if r["Parcela"].strip() else None,
            "percentual": numero_br(r["Percentual"]) if r["Percentual"].strip() else None,
            "valor_base": numero_br(r["Base Cálculo"]),
            "valor_comissao": comissao,
            "valor_estorno": -comissao if comissao < 0 else 0.0,
        })
    return linhas
