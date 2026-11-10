"""Um parser por fonte. Cada um lê os arquivos baixados e devolve linhas no formato padrão."""
from . import easyplan, samp

PARSERS = {
    "samp": samp,
    "easyplan": easyplan,
}
