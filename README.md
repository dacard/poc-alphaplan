# POC Alphaplan — conciliação de comissões

Baixa os relatórios de comissão dos portais das operadoras/administradoras, extrai os dados
e compara mês a mês com o cadastro dos contratos, mostrando as divergências e o impacto financeiro.

Fontes desta versão: **Samp** (operadora), **Easyplan**, **Up Health**, **Quali** e **Mediatorie** (administradoras).

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

Credenciais no `.env`: `USUARIO_<FONTE>` e `SENHA_<FONTE>` (ex.: `USUARIO_SAMP`, `SENHA_SAMP`) e
`ANTHROPIC_API_KEY` para o assistente de IA.

## Uso

```bash
# 1. Coletar relatórios (ou pelo botão "Coletar agora" na tela Relatórios)
.venv/bin/python playwright-scripts/samp.py
.venv/bin/python playwright-scripts/easyplan.py
.venv/bin/python playwright-scripts/uphealth.py
.venv/bin/python playwright-scripts/quali.py      # mês a mês, ~70 s por mês
.venv/bin/python playwright-scripts/mediatorie.py

# 2. (Re)criar a base de demonstração — APAGA dados/poc.db
cd backend && ../.venv/bin/python -m app.seed && cd ..

# 3. Subir API + frontend
./iniciar.sh            # http://localhost:5180
```

## Tela de Relatórios: coleta e upload manual

- Lista das fontes, todas pré-selecionadas: **Coletar** uma fonte ou **Coletar selecionadas** em massa.
  A coleta roda em segundo plano (robô + importação) e o estado aparece na própria lista.
- **Upload manual** por fonte, para quando o portal está fora do ar e o relatório chega por e-mail.
  Aceita os mesmos formatos do portal (Samp: ZIP ou CSV; Easyplan e Mediatorie: Excel; Up Health: TXT
  + PDF opcional; Quali: CSV). Os arquivos ficam em `dados/brutos/<fonte>/manual-<data>/`.
- Antes de importar, o arquivo é conferido: formato, colunas e **conteúdo já importado** (comparação
  linha a linha, porque o portal gera um arquivo diferente a cada download). Sobreposição parcial também
  é recusada, para não contar comissão em dobro.
- Quando o portal volta e o robô baixa um relatório com as mesmas linhas, **a versão do portal
  substitui o upload manual** automaticamente.
- Relatórios podem ser excluídos (upload errado, por exemplo).

## Dashboard (tela inicial)

Indicadores (clientes, operadoras, administradoras, contratos, colaboradores ativos, relatórios e
pagamentos processados, receita total), receita por competência × esperado pelo cadastro, vidas com
comissão e projeção dos próximos meses, tudo filtrável por cliente.

**Projeção** = tendência linear das vidas com comissão × tendência da receita por vida (amortecida),
calculadas nos últimos 6 meses completos. O mês em andamento entra como projeção. A faixa sombreada
é ± o desvio dos resíduos da receita por vida.

**Alertas** (top 10 contratos que precisam de atenção): maiores quedas de receita recorrente,
comparando a média dos últimos 3 meses completos com a dos 3 anteriores. Parcelas de agenciamento
(% ≥ 50) ficam de fora, porque o fim delas é esperado. A causa provável é a que mais explica a
queda: sem pagamentos, saída de colaboradores ou queda no valor por vida.

## Assistente de IA

Diálogo flutuante (canto inferior direito, ícone de estrelas) que responde perguntas sobre clientes,
contratos, colaboradores, comissões, divergências e relatórios. Usa a API da Anthropic
(`claude-opus-5-5`, chave `ANTHROPIC_API_KEY` no `.env`) com ferramentas de consulta aos dados da POC
(`backend/app/assistente/ferramentas.py`); o prompt e o loop ficam em `backend/app/assistente/agente.py`.
Fora desse contexto, ele recusa educadamente.

**Avaliação** com 20 perguntas de gestor (mais casos de regressão), cuja resposta certa é calculada direto do banco:

```bash
cd backend && ../.venv/bin/python -m avaliacao.avaliar_assistente   # relatório em dados/avaliacao_assistente.md
```

Mede compreensão (consultou os dados certos) e resposta (os fatos esperados aparecem no texto).
Cada rodada custa algumas chamadas à API.

## Regras da conciliação

- **Competência**: Samp = mês de vencimento da mensalidade; Easyplan = mês da previsão de pagamento;
  Up Health = "Mês Referência"; Quali = "Mês" (as duas quinzenas juntas); Mediatorie = "Competência".
- **Ligação relatório → contrato**: campo *Identificador no relatório* do contrato
  (Samp: nº do contrato; Easyplan: `PRODUTOR / Modalidade N` — PRODUTOR é a empresa, NOME CONTRATO o colaborador;
  Up Health: `<nº contrato> / Médico|Dental`; Quali: código da empresa;
  Mediatorie: `<Contrato Cliente> / Médico|Odonto`).
- **Casamento de pessoas**: CPF (se a chave do contrato for CPF) → nome exato → nome aproximado (≥ 90%).
- **Meses analisados**: do início do contrato até o último mês completo coberto pelos relatórios da fonte.
  Um contrato que para de gerar comissão continua aparecendo, com os colaboradores "sem comissão".
- **Comissão esperada**: mensalidade × % da regra para a parcela informada no relatório.
- **Mensalidade esperada**: tabela por faixa etária do produto (se houver e o colaborador tiver nascimento);
  senão, o valor cadastrado no colaborador, considerando os reajustes registrados (mês a partir do qual valem).
- **Divergências**: sem comissão (esperado e ausente), não cadastrado, mensalidade diferente,
  percentual diferente, comissão paga diferente de mensalidade × %, possível duplicidade (mesma parcela paga duas vezes — pode ser titular e dependente
  com o mesmo nome), estorno.
- **Impacto** = comissão recebida − comissão esperada (positivo: recebeu a mais; negativo: a menos).

## Particularidades por fonte

- **Up Health**: o extrato vem em TXT e PDF. O TXT (latin-1, campos separados por `#`) tem todos os
  valores mas não tem o nome do beneficiário; o PDF tem o nome. O leitor usa o TXT e busca o nome no PDF
  casando fatura + parcela + base + comissão (99,8% das linhas; o resto fica como "Item <código>").
- **Quali**: o portal fica muito lento com períodos longos, então o robô exporta o CSV um mês por vez
  (da 1ª à 2ª quinzena). O relatório não informa a operadora. A comissão de agenciamento costuma ser
  dividida entre as parcelas 1 e 2 (50% cada).
- **Mediatorie**: portal SAP UI5; a tela de comissão roda dentro de um iframe e cada protocolo mensal
  tem um botão "Extrato" que baixa o Excel. É a fonte mais completa (traz CPF e data de nascimento,
  usados no cadastro de demonstração). Na parcela 2 o percentual costuma ser 53% (agenciamento 50% + vitalício 3%).
