# POC Alphaplan — conciliação de comissões

Baixa os relatórios de comissão dos portais das operadoras/administradoras, extrai os dados
e compara mês a mês com o cadastro dos contratos, mostrando as divergências e o impacto financeiro.

Fontes desta versão: **Samp** (operadora), **Easyplan** e **Up Health** (administradoras).

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
.venv/bin/python playwright-scripts/uphealth.py

# 2. (Re)criar a base de demonstração — APAGA dados/poc.db
cd backend && ../.venv/bin/python -m app.seed && cd ..

# 3. Subir API + frontend
./iniciar.sh            # http://localhost:5180
```

## Regras da conciliação

- **Competência**: Samp = mês de vencimento da mensalidade; Easyplan = mês da previsão de pagamento;
  Up Health = "Mês Referência".
- **Ligação relatório → contrato**: campo *Identificador no relatório* do contrato
  (Samp: nº do contrato; Easyplan: `PRODUTOR / Modalidade N` — PRODUTOR é a empresa, NOME CONTRATO o colaborador;
  Up Health: `<nº contrato> / Médico|Dental`).
- **Casamento de pessoas**: CPF (se a chave do contrato for CPF) → nome exato → nome aproximado (≥ 90%).
- **Comissão esperada**: mensalidade × % da regra para a parcela informada no relatório.
- **Mensalidade esperada**: tabela por faixa etária do produto (se houver e o colaborador tiver nascimento);
  senão, o valor cadastrado no colaborador, considerando os reajustes registrados (mês a partir do qual valem).
- **Divergências**: sem comissão (esperado e ausente), não cadastrado, mensalidade diferente,
  percentual diferente, possível duplicidade (mesma parcela paga duas vezes — pode ser titular e dependente
  com o mesmo nome), estorno.
- **Impacto** = comissão recebida − comissão esperada (positivo: recebeu a mais; negativo: a menos).

## Particularidades por fonte

- **Up Health**: o extrato vem em TXT e PDF. O TXT (latin-1, campos separados por `#`) tem todos os
  valores mas não tem o nome do beneficiário; o PDF tem o nome. O leitor usa o TXT e busca o nome no PDF
  casando fatura + parcela + base + comissão (99,8% das linhas; o resto fica como "Item <código>").
