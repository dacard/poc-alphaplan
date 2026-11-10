"""Funções compartilhadas pelos scripts de coleta."""
import argparse
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "dados" / "brutos"

load_dotenv(RAIZ / ".env")


def credenciais(fonte: str) -> tuple[str, str]:
    """Lê USUARIO_<FONTE> e SENHA_<FONTE> do .env."""
    nome = fonte.upper()
    usuario = os.getenv(f"USUARIO_{nome}")
    senha = os.getenv(f"SENHA_{nome}")
    if not usuario or not senha:
        raise SystemExit(f"Defina USUARIO_{nome} e SENHA_{nome} no .env")
    return usuario, senha


def pasta_destino(fonte: str, subpasta: str) -> Path:
    """Cria e devolve dados/brutos/<fonte>/<subpasta>/."""
    pasta = PASTA_DADOS / fonte / subpasta
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def slug(texto: str) -> str:
    """'MIX TUDO - Pagamento de 01/11' -> 'mix-tudo-pagamento-de-01-11'."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")


def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def argumentos_base(descricao: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=descricao)
    parser.add_argument("--visivel", action="store_true", help="abre o navegador na tela")
    return parser
