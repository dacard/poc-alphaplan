"""Baixa os demonstrativos de pagamento da Samp e extrai o CSV de interesse.

Cada linha da tela "Demonstrativo de pagamento" é um pagamento semanal.
O link "Recibo completo" abre uma aba que dispara o download de um ZIP com 2 CSVs;
o que interessa é o que NÃO termina em Nao_pagos.csv.
Só baixa pagamentos com NF "Confirmada" e que ainda não existam em disco.

Saída: dados/brutos/samp/<vencimento AAAA-MM-DD>_<referência>/
       (há vencimentos com 2 pagamentos: o semanal e um avulso, ex. "MIX TUDO")
         <arquivo>.zip
         extraido/...           (todos os arquivos do ZIP)
         <...>.csv              (cópia do CSV de interesse)
"""
import shutil
import zipfile
from datetime import datetime

from playwright.sync_api import sync_playwright

from comum import argumentos_base, credenciais, pasta_destino, slug

URL = "https://sampweb.samp.com.br/solusweb/comercial/index.php"
SUFIXO_IGNORADO = "nao_pagos.csv"
STATUS_CONFIRMADO = "Confirmada"
COL_VENCIMENTO, COL_REFERENCIA, COL_STATUS_NF = 0, 1, 6


def extrair_csv(arquivo_zip, pasta):
    pasta_extraido = pasta / "extraido"
    with zipfile.ZipFile(arquivo_zip) as z:
        z.extractall(pasta_extraido)
    encontrados = [f for f in pasta_extraido.rglob("*.csv")
                   if not f.name.lower().endswith(SUFIXO_IGNORADO)]
    if len(encontrados) != 1:
        raise RuntimeError(f"Esperava 1 CSV de pagamento em {arquivo_zip.name}, "
                           f"achei {[f.name for f in encontrados]}")
    csv = pasta / encontrados[0].name
    shutil.copy2(encontrados[0], csv)
    return csv


def coletar(ultimos: int | None = None, refazer: bool = False, visivel: bool = False):
    usuario, senha = credenciais("samp")
    gerados, pulados = [], 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not visivel)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        page.goto(URL)
        page.get_by_role("textbox", name="Login").fill(usuario)
        page.get_by_role("textbox", name="Senha").fill(senha)
        page.get_by_role("button", name="Entrar").click()

        page.get_by_role("link", name="Relatórios").click()
        page.get_by_role("link", name="Demonstrativo de pagamento").click()
        page.get_by_role("button", name="Listar").click()

        recibo = page.get_by_role("link", name="Recibo completo")
        recibo.first.wait_for()
        linhas = page.locator("tr").filter(has=recibo)
        total = linhas.count()

        # A tabela vem do vencimento mais recente para o mais antigo.
        confirmados = 0
        for i in range(total):
            linha = linhas.nth(i)
            celulas = [c.strip() for c in linha.locator("td").all_inner_texts()]
            if celulas[COL_STATUS_NF] != STATUS_CONFIRMADO:
                continue
            confirmados += 1
            if ultimos and confirmados > ultimos:
                break
            vencimento_br = celulas[COL_VENCIMENTO]
            referencia = " ".join(celulas[COL_REFERENCIA].split())
            vencimento = datetime.strptime(vencimento_br, "%d/%m/%Y").strftime("%Y-%m-%d")

            pasta = pasta_destino("samp", f"{vencimento}_{slug(referencia)}")
            if (pasta / "referencia.txt").exists() and not refazer:
                pulados += 1
                continue
            if refazer:
                for antigo in pasta.iterdir():
                    shutil.rmtree(antigo) if antigo.is_dir() else antigo.unlink()

            with page.expect_popup() as info_popup:
                linha.get_by_role("link", name="Recibo completo").click()
            popup = info_popup.value
            download = popup.wait_for_event("download", timeout=60_000)

            arquivo_zip = pasta / download.suggested_filename
            download.save_as(arquivo_zip)
            popup.close()

            csv = extrair_csv(arquivo_zip, pasta)
            (pasta / "referencia.txt").write_text(f"{vencimento_br} | {referencia}\n")
            print(f"  {vencimento} ({referencia}): {csv.name}")
            gerados.append(csv)

        context.close()
        browser.close()

    print(f"Samp: {len(gerados)} baixados, {pulados} já existiam")
    return gerados


if __name__ == "__main__":
    parser = argumentos_base("Coleta dos demonstrativos de pagamento da Samp")
    parser.add_argument("--ultimos", type=int,
                        help="olha só os N pagamentos confirmados mais recentes (padrão: todos)")
    parser.add_argument("--refazer", action="store_true",
                        help="baixa de novo mesmo os vencimentos que já existem")
    args = parser.parse_args()
    coletar(ultimos=args.ultimos, refazer=args.refazer, visivel=args.visivel)
