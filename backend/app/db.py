from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

RAIZ = Path(__file__).resolve().parents[2]
PASTA_DADOS = RAIZ / "dados"
PASTA_BRUTOS = PASTA_DADOS / "brutos"
ARQUIVO_DB = PASTA_DADOS / "poc.db"

PASTA_DADOS.mkdir(exist_ok=True)
engine = create_engine(f"sqlite:///{ARQUIVO_DB}", connect_args={"check_same_thread": False})


def criar_tabelas():
    from . import models  # noqa: F401  (registra as tabelas)
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
