"""Lê os arquivos em dados/brutos/<fonte>/ e grava no banco o que ainda não foi importado.

Um arquivo é identificado pelo hash do conteúdo. Se um relatório (mesma pasta) foi
baixado de novo com conteúdo diferente (ex.: Easyplan ainda não pago), a versão
anterior é substituída.
"""
import hashlib

from sqlmodel import Session, delete, select

from .db import PASTA_BRUTOS
from .models import LinhaRelatorio, Relatorio
from .parsers import PARSERS


def _hash(arquivo) -> str:
    return hashlib.md5(arquivo.read_bytes()).hexdigest()


def importar(session: Session, fonte: str | None = None) -> dict:
    resultado = {}
    for codigo, parser in PARSERS.items():
        if fonte and codigo != fonte:
            continue
        pasta_fonte = PASTA_BRUTOS / codigo
        novos = substituidos = 0
        if pasta_fonte.exists():
            for pasta, arquivo in parser.arquivos(pasta_fonte):
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
        session.commit()
        resultado[codigo] = {"importados": novos, "substituidos": substituidos}
    return resultado
