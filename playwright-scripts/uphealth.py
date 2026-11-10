"""Baixa os extratos de comissão (TXT + PDF) do portal da Up Health.

Cada linha da tela "Extrato de Comissão" é um extrato mensal. Baixamos os dois formatos:
  - TXT: campos separados por '#', com todos os valores (base dos dados);
  - PDF: única fonte do nome do beneficiário (usado para completar o TXT).
O filtro de período vem com os últimos 2 meses; ampliamos para pegar o histórico.

Só baixa o que ainda não existe em disco. Extratos ainda "Aguardando..." são baixados
de novo a cada execução, porque o conteúdo pode mudar até o fechamento.

Saída: dados/brutos/uphealth/<AAAA-MM>_extrato-<nº>/
         extrato.txt
         extrato.pdf
         info.txt   (nº, período, situação)
"""
from datetime import datetime

from playwright.sync_api import sync_playwright

from comum import argumentos_base, credenciais, pasta_destino

URL = "https://uphealth.topadministradora.com.br/PortalCorretora/"
INICIO_HISTORICO = "01/01/2020"


def entrar(page, usuario, senha):
    page.goto(URL)
    page.get_by_role("textbox", name="Usuário").fill(usuario)
    page.get_by_role("textbox", name="Senha").fill(senha)
    page.get_by_role("button", name="ENTRAR").click()
    # Aviso que às vezes abre depois do login
    aviso = page.get_by_role("dialog").get_by_text("×")
    try:
        aviso.click(timeout=8_000)
    except Exception:
        pass


def abrir_extratos(page, desde: str):
    page.get_by_role("link", name="Relatórios").click()  # o menu fica recolhido
    page.get_by_role("link", name="Extrato de Comissão").click()
    page.locator("#periodo_inicio").wait_for()
    page.locator("#periodo_inicio").evaluate(
        "(e, v) => { e.value = v; e.dispatchEvent(new Event('change', {bubbles: true})) }", desde)
    page.get_by_text("Visualizar").click()
    page.locator("tr .imgGerarTxt").first.wait_for()


def baixar(page, linha, classe_icone, destino):
    # O aviso "Relatório gerado com sucesso!" fica por cima dos ícones e bloqueia o clique
    page.evaluate("document.querySelectorAll('#toast-container').forEach(e => e.remove())")
    with page.expect_download(timeout=90_000) as info:
        linha.locator(f".{classe_icone}").click()
    info.value.save_as(destino)


def coletar(refazer: bool = False, visivel: bool = False, desde: str = INICIO_HISTORICO):
    usuario, senha = credenciais("uphealth")
    baixados, pulados = [], 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not visivel)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()
        entrar(page, usuario, senha)
        abrir_extratos(page, desde)

        linhas = page.locator("tr").filter(has=page.locator(".imgGerarTxt"))
        total = linhas.count()
        print(f"Up Health: {total} extratos na lista")

        for i in range(total):
            linha = linhas.nth(i)
            numero, _adm, inicio, fim, situacao = [c.strip() for c in linha.locator("td").all_inner_texts()[:5]]
            mes = datetime.strptime(inicio, "%d/%m/%Y").strftime("%Y-%m")
            pasta = pasta_destino("uphealth", f"{mes}_extrato-{numero}")
            fechado = "aguardando" not in situacao.lower()

            if (pasta / "extrato.txt").exists() and (pasta / "extrato.pdf").exists() and fechado and not refazer:
                pulados += 1
                continue

            baixar(page, linha, "imgGerarTxt", pasta / "extrato.txt")
            baixar(page, linha, "imgGerarPdf", pasta / "extrato.pdf")
            (pasta / "info.txt").write_text(
                f"Extrato: {numero}\nPeríodo Inicial: {inicio}\nPeríodo Final: {fim}\nSituação: {situacao}\n")
            print(f"  extrato {numero} ({inicio} a {fim}, {situacao})")
            baixados.append(pasta)

        context.close()
        browser.close()

    print(f"Up Health: {len(baixados)} baixados, {pulados} já existiam")
    return baixados


if __name__ == "__main__":
    parser = argumentos_base("Coleta dos extratos de comissão da Up Health")
    parser.add_argument("--refazer", action="store_true", help="baixa de novo mesmo os extratos que já existem")
    parser.add_argument("--desde", default=INICIO_HISTORICO, help="início do período (dd/mm/aaaa)")
    args = parser.parse_args()
    coletar(refazer=args.refazer, visivel=args.visivel, desde=args.desde)
