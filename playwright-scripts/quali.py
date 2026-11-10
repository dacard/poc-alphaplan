"""Baixa o Relatório de Comissões (CSV) do portal da Quali, mês a mês.

O portal filtra por competência (MM/AAAA, com 1ª/2ª quinzena) e fica muito lento com
janelas longas, então exportamos um mês por vez (~70 s cada), da 1ª à 2ª quinzena.
O histórico começa em 05/2025.

Só baixa o que ainda não existe em disco. O mês atual e o anterior são baixados de novo
a cada execução, porque ainda podem receber lançamentos.

Saída: dados/brutos/quali/<AAAA-MM>/
         comissoes.csv
         info.txt   (competência)
"""
from datetime import date

from playwright.sync_api import sync_playwright

from comum import argumentos_base, credenciais, pasta_destino

URL = "https://autorizador.qualisaudeadm.com.br:8085/GuiasTISS/Logon"
INICIO_HISTORICO = "2025-05"
TIPO_ACESSO_VENDEDOR = "25"

# Define a competência pelo próprio componente de calendário da página (bootstrap-datetimepicker)
DEFINIR_MES_JS = """(e, v) => {
    const dp = jQuery(e).closest('.date, .input-group').data('DateTimePicker');
    if (dp) { dp.date(moment(v, 'MM/YYYY')); } else { e.value = v; }
    jQuery(e).trigger('change');
}"""


def meses(inicio: str, fim: str) -> list[str]:
    a, m = map(int, inicio.split("-"))
    saida = []
    while f"{a:04d}-{m:02d}" <= fim:
        saida.append(f"{a:04d}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return saida


def entrar(page, usuario, senha):
    page.goto(URL)
    page.get_by_label("Tipo de acesso:").select_option(TIPO_ACESSO_VENDEDOR)
    page.get_by_role("textbox", name="Usuário:").fill(usuario)
    page.get_by_role("textbox", name="Senha:").fill(senha)
    page.get_by_role("button", name="Entrar").click()
    page.get_by_role("button", name="Continuar").click()
    page.get_by_text("Relatório de Comissões").first.click()  # atalho no menu que abre após o login
    page.get_by_text("Competência Inicial").wait_for()
    page.get_by_role("checkbox", name="Comissão de Beneficiarios de").check()


def campo(page, rotulo):
    return page.locator(f"xpath=//*[normalize-space(text())='{rotulo}']/following::input[@type='text'][1]")


def exportar_mes(page, competencia: str, destino):
    a, m = competencia.split("-")
    valor = f"{m}/{a}"
    # Final antes da inicial: o calendário não deixa a inicial passar da final
    for rotulo in ("Competência Final", "Competência Inicial"):
        campo(page, rotulo).evaluate(DEFINIR_MES_JS, valor)
    if campo(page, "Competência Inicial").input_value() != valor or campo(page, "Competência Final").input_value() != valor:
        raise RuntimeError(f"Não consegui definir a competência {valor}")
    with page.expect_download(timeout=300_000) as info:
        page.get_by_role("button", name="Exportar (CSV)").click()
    info.value.save_as(destino)
    for aba in page.context.pages:
        if aba != page:
            aba.close()  # a exportação abre uma aba auxiliar


def coletar(refazer: bool = False, visivel: bool = False, desde: str = INICIO_HISTORICO, ate: str | None = None):
    usuario, senha = credenciais("quali")
    hoje = date.today()
    atual = hoje.strftime("%Y-%m")
    anterior = meses(f"{hoje.year - 1}-{hoje.month:02d}", atual)[-2]
    abertos = {atual, anterior}
    baixados, pulados, falhas = [], 0, []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not visivel)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()
        entrar(page, usuario, senha)

        for comp in meses(desde, ate or atual):
            pasta = pasta_destino("quali", comp)
            if (pasta / "comissoes.csv").exists() and comp not in abertos and not refazer:
                pulados += 1
                continue
            try:
                exportar_mes(page, comp, pasta / "comissoes.csv")
            except Exception as erro:
                print(f"  {comp}: falhou ({str(erro).splitlines()[0][:120]})")
                falhas.append(comp)
                continue
            (pasta / "info.txt").write_text(f"Competência: {comp}\nSituação: {'aberta' if comp in abertos else 'fechada'}\n")
            linhas = sum(1 for _ in open(pasta / "comissoes.csv", encoding="utf-8-sig")) - 1
            print(f"  {comp}: {linhas} linhas")
            baixados.append(pasta)

        context.close()
        browser.close()

    print(f"Quali: {len(baixados)} baixados, {pulados} já existiam" + (f", falhas: {falhas}" if falhas else ""))
    return baixados


if __name__ == "__main__":
    parser = argumentos_base("Coleta do relatório de comissões da Quali (mês a mês)")
    parser.add_argument("--refazer", action="store_true", help="baixa de novo mesmo os meses que já existem")
    parser.add_argument("--desde", default=INICIO_HISTORICO, help="primeiro mês (AAAA-MM)")
    parser.add_argument("--ate", help="último mês (AAAA-MM); padrão: mês atual")
    args = parser.parse_args()
    coletar(refazer=args.refazer, visivel=args.visivel, desde=args.desde, ate=args.ate)
