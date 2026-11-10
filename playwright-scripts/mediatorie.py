"""Baixa os extratos de comissão (Excel) do portal da Mediatorie (SAP UI5).

Fluxo: login -> "Comissão e Status de Pagamento" -> "Início" (sem filtro lista todos os
protocolos mensais) -> botão "Extrato" de cada protocolo, que baixa "Extrato Comissao.xlsx".
A tela de comissão roda dentro de um iframe. A tabela do SAP só desenha as linhas visíveis,
então percorremos a lista rolando a tabela.

Só baixa protocolos que ainda não existem em disco (um protocolo é um extrato fechado).

Saída: dados/brutos/mediatorie/<AAAA-MM da emissão>_<protocolo>/
         extrato.xlsx
         info.txt   (protocolo, emissão, valor)
"""
import re

from playwright.sync_api import sync_playwright

from comum import argumentos_base, credenciais, pasta_destino

URL = "https://mediatorie.portalacesso.adm.br:8100/sap/bc/ui5_ui5/sap/zuxcor_login/index.html?sap-client=400#"
ICONE_EXTRATO = "button[title='manager-insight']"


def entrar(page, usuario, senha):
    page.goto(URL)
    page.locator("input[id$='ID_CREDENTIAL-inner']").fill(usuario)
    page.locator("input[id$='ID_PASSWORD-inner']").fill(senha)
    page.get_by_role("button", name="Entrar").click()
    page.get_by_text("Comissão e Status de Pagamento").first.click()
    tela = page.frame_locator("iframe[src*='zuxcor_relcomis']")
    tela.get_by_role("button", name="Início").click()
    tela.locator(ICONE_EXTRATO).first.wait_for()
    return tela


def total_itens(tela) -> int:
    texto = tela.get_by_text(re.compile(r"Itens \(\d+\)")).first.inner_text()
    return int(re.search(r"\((\d+)\)", texto).group(1))


def rolar_para(tela, primeira_linha: int):
    """Usa a API da tabela SAP para mostrar a partir de uma linha."""
    tela.locator("table[id$='-table']").first.evaluate(
        """(e, n) => {
            const id = e.id.replace(/-table$/, '');
            sap.ui.getCore().byId(id).setFirstVisibleRow(n);
        }""", primeira_linha)


def linhas_visiveis(tela) -> list[dict]:
    saida = []
    for tr in tela.locator("tr.sapUiTableContentRow").all():
        textos = [t.strip() for t in tr.locator("td").all_inner_texts()]
        protocolo = next((t for t in textos if re.fullmatch(r"\d{14}", t)), None)
        if not protocolo:
            continue
        emissao = next(t for t in textos if re.fullmatch(r"\d{8}", t))
        valor = next((m.group(0) for t in textos if (m := re.match(r"[\d.]+,\d{2}\b", t))), "")
        saida.append({"protocolo": protocolo, "emissao": emissao, "valor": valor, "tr": tr})
    return saida


def coletar(refazer: bool = False, visivel: bool = False):
    usuario, senha = credenciais("mediatorie")
    baixados, pulados, vistos = [], 0, set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not visivel)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()
        tela = entrar(page, usuario, senha)
        total = total_itens(tela)
        print(f"Mediatorie: {total} protocolos na lista")

        inicio = 0
        while len(vistos) < total:
            rolar_para(tela, inicio)
            page.wait_for_timeout(800)
            novos = [l for l in linhas_visiveis(tela) if l["protocolo"] not in vistos]
            if not novos:
                break
            for l in novos:
                vistos.add(l["protocolo"])
                mes = f"{l['emissao'][:4]}-{l['emissao'][4:6]}"
                pasta = pasta_destino("mediatorie", f"{mes}_{l['protocolo']}")
                if (pasta / "extrato.xlsx").exists() and not refazer:
                    pulados += 1
                    continue
                with page.expect_download(timeout=120_000) as info:
                    l["tr"].locator(ICONE_EXTRATO).click()
                info.value.save_as(pasta / "extrato.xlsx")
                (pasta / "info.txt").write_text(
                    f"Protocolo: {l['protocolo']}\nEmissão: {l['emissao']}\nValor: {l['valor']}\n")
                print(f"  protocolo {l['protocolo']} (emissão {l['emissao']}, R$ {l['valor']})")
                baixados.append(pasta)
            inicio += len(novos)

        context.close()
        browser.close()

    print(f"Mediatorie: {len(baixados)} baixados, {pulados} já existiam")
    return baixados


if __name__ == "__main__":
    parser = argumentos_base("Coleta dos extratos de comissão da Mediatorie")
    parser.add_argument("--refazer", action="store_true", help="baixa de novo mesmo os protocolos que já existem")
    args = parser.parse_args()
    coletar(refazer=args.refazer, visivel=args.visivel)
