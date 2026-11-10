"""Lê os arquivos em dados/brutos/<fonte>/ e grava no banco o que ainda não foi importado.

Um arquivo é identificado pelo hash do conteúdo. Se um relatório (mesma pasta) foi
baixado de novo com conteúdo diferente (ex.: Easyplan ainda não pago), a versão
anterior é substituída.

Uploads manuais (pastas "manual-*") cobrem a indisponibilidade do portal. Quando o robô
baixa depois um relatório com as mesmas linhas, o do portal prevalece e o manual sai.
"""
import hashlib
import shutil
from collections import Counter

from sqlmodel import Session, delete, select

from .db import PASTA_BRUTOS
from .models import LinhaRelatorio, Relatorio
from .parsers import PARSERS
from .parsers.comum import normalizar_nome

COBERTURA_DUPLICADO = 0.9  # fração de linhas iguais para considerar o mesmo relatório


def chave_linha(l) -> tuple:
    g = l.get if isinstance(l, dict) else lambda k: getattr(l, k)
    return (g("contrato_ref"), normalizar_nome(g("nome")), g("competencia"), g("parcela"),
            round(g("valor_comissao"), 2))


def sobreposicao(session: Session, fonte: str, linhas: list, ignorar: set[int] = frozenset()) -> dict[int, int]:
    """Quantas das linhas informadas já existem em cada relatório importado da fonte."""
    novas = Counter(chave_linha(l) for l in linhas)
    por_relatorio: dict[int, Counter] = {}
    for l in session.exec(select(LinhaRelatorio).where(LinhaRelatorio.fonte == fonte)):
        if l.relatorio_id not in ignorar:
            por_relatorio.setdefault(l.relatorio_id, Counter())[chave_linha(l)] += 1
    return {rid: sum((novas & existentes).values()) for rid, existentes in por_relatorio.items()
            if novas & existentes}


def remover_relatorio(session: Session, rel: Relatorio) -> bool:
    """Apaga o relatório e suas linhas; se veio de upload manual, apaga também os arquivos.
    Devolve True quando os arquivos foram apagados."""
    session.exec(delete(LinhaRelatorio).where(LinhaRelatorio.relatorio_id == rel.id))
    session.delete(rel)
    pasta = (PASTA_BRUTOS / rel.caminho).parent
    manual = pasta.name.startswith("manual-")
    if manual:
        shutil.rmtree(pasta, ignore_errors=True)
    return manual


def _hash(arquivo) -> str:
    return hashlib.md5(arquivo.read_bytes()).hexdigest()


def importar(session: Session, fonte: str | None = None, somente=None) -> dict:
    """somente: importa só esta pasta (usado no upload manual)."""
    resultado = {}
    for codigo, parser in PARSERS.items():
        if fonte and codigo != fonte:
            continue
        pasta_fonte = PASTA_BRUTOS / codigo
        novos = substituidos = manuais_substituidos = 0
        if pasta_fonte.exists():
            for pasta, arquivo in parser.arquivos(pasta_fonte):
                if somente is not None and pasta != somente:
                    continue
                h = _hash(arquivo)
                if session.exec(select(Relatorio).where(Relatorio.hash == h)).first():
                    continue
                caminho = str(arquivo.relative_to(PASTA_BRUTOS))
                pasta_rel = str(pasta.relative_to(PASTA_BRUTOS))
                antigo = session.exec(select(Relatorio).where(
                    Relatorio.fonte == codigo, Relatorio.caminho.startswith(pasta_rel + "/"))).first()
                if antigo:
                    session.exec(delete(LinhaRelatorio).where(LinhaRelatorio.relatorio_id == antigo.id))
                    session.delete(antigo)
                    substituidos += 1

                meta = parser.metadados(pasta)
                linhas = parser.ler(arquivo)
                rel = Relatorio(fonte=codigo, caminho=caminho, hash=h, qtd_linhas=len(linhas), **meta)
                session.add(rel)
                session.flush()
                session.add_all(LinhaRelatorio(relatorio_id=rel.id, fonte=codigo, **l) for l in linhas)
                novos += 1
                if not pasta.name.startswith("manual-") and linhas:
                    manuais_substituidos += _substituir_manuais(session, codigo, linhas, rel.id)
        session.commit()
        resultado[codigo] = {"importados": novos, "substituidos": substituidos,
                             "manuais_substituidos": manuais_substituidos}
    return resultado


def _substituir_manuais(session: Session, fonte: str, linhas: list, novo_id: int) -> int:
    """Remove uploads manuais cujas linhas estão (quase) todas no relatório do portal."""
    if not session.exec(select(Relatorio.id).where(
            Relatorio.fonte == fonte, Relatorio.caminho.contains("/manual-"))).first():
        return 0
    removidos = 0
    for rid, iguais in sobreposicao(session, fonte, linhas, ignorar={novo_id}).items():
        rel = session.get(Relatorio, rid)
        if rel and "/manual-" in "/" + rel.caminho and iguais >= COBERTURA_DUPLICADO * max(rel.qtd_linhas, 1):
            remover_relatorio(session, rel)
            removidos += 1
    return removidos
