"""Baixa os relatórios de comissão (Excel) do portal da Easyplan.

A tela "Relatório de Comissões" lista um relatório por linha, do mais recente para o
mais antigo, e só mostra todos depois de clicar várias vezes em "Carregar Mais...".
O filtro de período do portal não funciona, por isso carregamos a lista inteira.

Só baixa o que ainda não existe em disco. Relatórios ainda não pagos são baixados
de novo a cada execução, porque o conteúdo pode mudar até o pagamento.

Saída: dados/brutos/easyplan/<data relatório AAAA-MM-DD>_<valor>/
         <arquivo>.xlsx
         info.txt   (linha da tabela: data, valor, status...)
"""
import re
from datetime import datetime

from playwright.sync_api import sync_playwright

from comum import argumentos_base, credenciais, pasta_destino

URL = "https://corretor.easyplan.com.br/auth"
STATUS_FINAL = "PAGO"

# Colunas da tabela (pela ordem da tela)
COL_DATA, COL_VALOR = 0, 1
COLUNAS = ["Data Relatório", "Valor Comissão", "Exportar", "Upload NF", "Status NF",
           "Motivo", "Data Previsão", "Data Pagamento", "Status Pagamento"]


def carregar_tudo(page, linhas):
    """Clica em "Carregar Mais..." até o botão sumir."""
    botao = page.get_by_text(re.compile(r"Carregar Mais", re.I))
    while botao.count() and botao.first.is_visible():
        antes = linhas.count()
        botao.first.click()
        try:
            page.wait_for_function(
                "([sel, n]) => document.querySelectorAll(sel).length > n",
                arg=["tbody tr", antes], timeout=15_000)
        except Exception:
            break
    return linhas.count()


def fechar_janela(page):
    """Fecha a janela de exportação, que continua aberta depois do download."""
    janela = page.locator("[role=dialog]")
    janela.get_by_role("button", name="Fechar").click()
    janela.wait_for(state="hidden", timeout=10_000)


def ler_linha(linha):
    celulas = [c.strip() for c in linha.locator("td").all_inner_texts()]
    dados = dict(zip(COLUNAS, celulas))
    data = datetime.strptime(celulas[COL_DATA], "%d/%m/%Y").strftime("%Y-%m-%d")
    valor = re.sub(r"[^\d,]", "", celulas[COL_VALOR]).replace(",", ".")
    return f"{data}_{valor}", dados


def coletar(refazer: bool = False, visivel: bool = False):
    usuario, senha = credenciais("easyplan")
    baixados, pulados = [], 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not visivel)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        page.goto(URL)
        page.get_by_role("button", name="Corretora Acesso com CNPJ").click()
        page.get_by_role("textbox", name="CNPJ").fill(usuario)
        page.get_by_role("textbox", name="Senha").fill(senha)
        page.get_by_role("button", name="Entrar").click()

        page.get_by_role("link", name="Relatório de Comissões").click()
        # Localiza pela estrutura da tabela (CSS), não por "role": enquanto a janela
        # de exportação está aberta, o resto da página fica oculto para os locators de role.
        linhas = page.locator("tbody tr").filter(has=page.locator("button", has_text="Exportar"))
        linhas.first.wait_for()
        total = carregar_tudo(page, linhas)
        print(f"Easyplan: {total} relatórios na lista")

        for i in range(total):
            linha = linhas.nth(i)
            chave, dados = ler_linha(linha)
            pasta = pasta_destino("easyplan", chave)
            existente = next(pasta.glob("*.xlsx"), None)
            pago = dados.get("Status Pagamento", "").upper() == STATUS_FINAL

            if existente and pago and not refazer:
                pulados += 1
                continue

            linha.locator("button", has_text="Exportar").click()
            with page.expect_download() as info:
                page.get_by_role("button", name="Baixar Excel Planilha editável").click()
            download = info.value

            if existente:
                existente.unlink()
            destino = pasta / download.suggested_filename
            download.save_as(destino)
            fechar_janela(page)
            (pasta / "info.txt").write_text(
                "\n".join(f"{k}: {v}" for k, v in dados.items()) + "\n")
            print(f"  {chave} ({dados.get('Status Pagamento', '?')}): {destino.name}")
            baixados.append(destino)

        context.close()
        browser.close()

    print(f"Easyplan: {len(baixados)} baixados, {pulados} já existiam")
    return baixados


if __name__ == "__main__":
    parser = argumentos_base("Coleta dos relatórios de comissão da Easyplan")
    parser.add_argument("--refazer", action="store_true",
                        help="baixa de novo mesmo os relatórios que já existem")
    args = parser.parse_args()
    coletar(refazer=args.refazer, visivel=args.visivel)
