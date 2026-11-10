# POC Alphaplan — conciliação de comissões

Baixa os relatórios de comissão dos portais das operadoras/administradoras, extrai os dados
e compara mês a mês com o cadastro dos contratos, mostrando as divergências e o impacto financeiro.

Fontes desta versão: **Samp** (operadora) e **Easyplan** (administradora).

## Estrutura

```
playwright-scripts/   robôs de coleta (um por fonte) -> dados/brutos/<fonte>/
backend/app/
  parsers/            leitores de relatório (um por fonte) -> formato padrão
  importador.py       grava no banco os arquivos ainda não importados
  conciliacao.py      cadastro (esperado) x relatórios (processado), mês a mês
  main.py             API (FastAPI)
  seed.py             base de demonstração gerada a partir dos relatórios
frontend/             telas (React + Vite)
dados/                arquivos baixados e banco SQLite (fora do git: dados pessoais)
```

## Instalação (uma vez)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
(cd frontend && npm install)
```

Credenciais no `.env`: `USUARIO_<FONTE>` e `SENHA_<FONTE>` (ex.: `USUARIO_SAMP`, `SENHA_SAMP`).

## Uso

```bash
# 1. Coletar relatórios (ou pelo botão "Coletar agora" na tela Relatórios)
.venv/bin/python playwright-scripts/samp.py
.venv/bin/python playwright-scripts/easyplan.py

# 2. (Re)criar a base de demonstração — APAGA dados/poc.db
cd backend && ../.venv/bin/python -m app.seed && cd ..

# 3. Subir API + frontend
./iniciar.sh            # http://localhost:5180
```

## Regras da conciliação

- **Competência**: Samp = mês de vencimento da mensalidade; Easyplan = mês da previsão de pagamento.
- **Ligação relatório → contrato**: campo *Identificador no relatório* do contrato
  (Samp: nº do contrato; Easyplan: `Operadora / Modalidade N`, pois o relatório não traz a empresa).
- **Casamento de pessoas**: CPF (se a chave do contrato for CPF) → nome exato → nome aproximado (≥ 90%).
- **Comissão esperada**: mensalidade × % da regra para a parcela informada no relatório.
- **Mensalidade esperada**: tabela por faixa etária do produto (se houver e o colaborador tiver nascimento);
  senão, o valor cadastrado no colaborador.
- **Divergências**: sem comissão (esperado e ausente), não cadastrado, mensalidade diferente,
  percentual diferente, mesma parcela paga duas vezes, estorno.
- **Impacto** = comissão recebida − comissão esperada (positivo: recebeu a mais; negativo: a menos).
