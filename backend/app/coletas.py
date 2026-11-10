"""Coleta (robôs Playwright) em segundo plano e upload manual de relatórios.

Cada fonte tem no máximo uma coleta rodando por vez. O estado fica em memória
(basta para a POC) e a tela consulta via /api/fontes.
"""
import hashlib
import shutil
import subprocess
import sys
import threading
from datetime import datetime

from sqlmodel import Session, select

from .db import PASTA_BRUTOS, RAIZ, engine
from .importador import COBERTURA_DUPLICADO, importar, sobreposicao
from .models import Relatorio
from .parsers import PARSERS
from .parsers.comum import ArquivoInvalido

_trava_importacao = threading.Lock()  # o SQLite aceita um escritor por vez
_estado: dict[str, dict] = {}


def estado(fonte: str) -> dict | None:
    return _estado.get(fonte)


def importar_com_trava(fonte: str, somente=None) -> dict:
    with _trava_importacao, Session(engine) as session:
        return importar(session, fonte, somente)[fonte]


def iniciar_coleta(fonte: str) -> dict:
    script = RAIZ / "playwright-scripts" / f"{fonte}.py"
    if fonte not in PARSERS or not script.exists():
        raise KeyError(f"Fonte '{fonte}' sem script de coleta")
    atual = _estado.get(fonte)
    if atual and atual["situacao"] == "executando":
        return atual
    _estado[fonte] = {"situacao": "executando", "inicio": datetime.now().isoformat(timespec="seconds"),
                      "fim": None, "mensagem": "Coletando no portal…", "importacao": None}
    threading.Thread(target=_rodar, args=(fonte, script), daemon=True).start()
    return _estado[fonte]


def _rodar(fonte: str, script):
    e = _estado[fonte]
    try:
        proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=3600)
        if proc.returncode != 0:
            erro = (proc.stderr.strip().splitlines() or ["erro desconhecido"])[-1]
            e.update(situacao="erro", mensagem=f"Falha na coleta: {erro[:300]}")
            return
        resumo = (proc.stdout.strip().splitlines() or [""])[-1]
        e["mensagem"] = "Importando…"
        imp = importar_com_trava(fonte)
        e.update(situacao="ok", importacao=imp,
                 mensagem=f"{resumo} · {imp['importados']} novos importados"
                          + (f", {imp['substituidos']} atualizados" if imp["substituidos"] else "")
                          + (f", {imp['manuais_substituidos']} uploads manuais substituídos pelo portal"
                             if imp.get("manuais_substituidos") else ""))
    except Exception as erro:  # noqa: BLE001 — qualquer falha vira mensagem na tela
        e.update(situacao="erro", mensagem=str(erro)[:300])
    finally:
        e["fim"] = datetime.now().isoformat(timespec="seconds")


def receber_upload(fonte: str, arquivos: list[tuple[str, bytes]]) -> dict:
    """Arruma os arquivos no mesmo formato da coleta, valida e importa."""
    parser = PARSERS.get(fonte)
    if not parser or not hasattr(parser, "preparar_upload"):
        raise KeyError(f"Fonte '{fonte}' não aceita upload")
    if not arquivos:
        raise ArquivoInvalido("Nenhum arquivo enviado.")

    pasta = PASTA_BRUTOS / fonte / f"manual-{datetime.now():%Y%m%d-%H%M%S}"
    pasta.mkdir(parents=True)
    try:
        parser.preparar_upload(arquivos, pasta)
        encontrados = list(parser.arquivos(pasta.parent))
        principal = next((arq for p, arq in encontrados if p == pasta), None)
        if principal is None:
            raise ArquivoInvalido("Não encontrei o arquivo principal do relatório no que foi enviado.")
        try:
            linhas = parser.ler(principal)
        except KeyError as erro:
            raise ArquivoInvalido(f"O arquivo não tem o formato do relatório desta fonte (falta a coluna {erro}).")
        except Exception as erro:  # noqa: BLE001
            raise ArquivoInvalido(f"Não consegui ler o arquivo: {erro}")

        h = hashlib.md5(principal.read_bytes()).hexdigest()
        with Session(engine) as session:
            existente = session.exec(select(Relatorio).where(Relatorio.hash == h)).first()
            if existente:
                raise ArquivoInvalido(f"Este relatório já foi importado antes ({existente.referencia}).")
            # O portal gera o arquivo de novo a cada download: compara o conteúdo, linha a linha
            iguais = sobreposicao(session, fonte, linhas)
            total_iguais = sum(iguais.values())
            if linhas and total_iguais:
                refs = ", ".join(session.get(Relatorio, rid).referencia for rid in sorted(iguais)[:3])
                if total_iguais >= COBERTURA_DUPLICADO * len(linhas):
                    raise ArquivoInvalido(f"Este relatório já foi importado antes ({refs}).")
                raise ArquivoInvalido(
                    f"{total_iguais} das {len(linhas)} linhas já estão importadas ({refs}). "
                    "Envie um arquivo só com o período que falta, para não contar comissão em dobro.")

        imp = importar_com_trava(fonte, somente=pasta)
        return {"ok": True, "linhas": len(linhas), "pasta": str(pasta.relative_to(PASTA_BRUTOS)), "importacao": imp}
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
