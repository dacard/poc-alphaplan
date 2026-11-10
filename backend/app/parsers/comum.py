import re
import unicodedata
from datetime import date


class ArquivoInvalido(ValueError):
    """Arquivo enviado manualmente que não corresponde ao relatório esperado."""


def hoje_br() -> str:
    return date.today().strftime("%d/%m/%Y")


def separar(arquivos: list[tuple[str, bytes]], *extensoes: str) -> dict[str, list[tuple[str, bytes]]]:
    """Agrupa os arquivos enviados por extensão; recusa extensões não aceitas."""
    grupos = {e: [] for e in extensoes}
    for nome, conteudo in arquivos:
        ext = nome.lower().rsplit(".", 1)[-1] if "." in nome else ""
        if ext not in grupos:
            raise ArquivoInvalido(f"Formato não aceito: {nome} (aceitos: {', '.join(extensoes)})")
        grupos[ext].append((nome, conteudo))
    return grupos


def numero_br(valor) -> float:
    """'R$ 1.234,56' -> 1234.56 ; '5.00 %' -> 5.0 ; '66,66' -> 66.66"""
    if valor is None:
        return 0.0
    texto = str(valor).strip()
    if not texto or texto.lower() == "nan":
        return 0.0
    texto = re.sub(r"[^\d,.\-]", "", texto)
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto) if texto else 0.0


def so_digitos(valor) -> str | None:
    if valor is None:
        return None
    digitos = re.sub(r"\D", "", str(valor))
    return digitos or None


def normalizar_nome(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode()
    return " ".join(sem_acento.upper().split())
