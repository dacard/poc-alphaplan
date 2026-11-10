import { useState } from "react";
import { api, Relatorio } from "../api";
import { Cabecalho, Carregando, useApi } from "../components/ui";
import { data } from "../formato";

interface Fonte { codigo: string; relatorios: number }

export default function Relatorios() {
  const fontes = useApi<Fonte[]>("/fontes");
  const [fonte, setFonte] = useState<string>("");
  const relatorios = useApi<Relatorio[]>(`/relatorios${fonte ? `?fonte=${fonte}` : ""}`);
  const [executando, setExecutando] = useState<string | null>(null);
  const [mensagem, setMensagem] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);

  const rodar = async (rotulo: string, caminho: string) => {
    setExecutando(rotulo);
    setMensagem(null);
    try {
      const r = await api<any>(caminho, { method: "POST" });
      const imp = r.importacao ?? r;
      const resumo = Object.entries(imp).map(([f, v]: [string, any]) =>
        `${f}: ${v.importados} novos${v.substituidos ? `, ${v.substituidos} atualizados` : ""}`).join(" · ");
      setMensagem({ tipo: "ok", texto: `${rotulo} concluída — ${resumo}` });
      fontes.recarregar();
      relatorios.recarregar();
    } catch (e: any) {
      setMensagem({ tipo: "erro", texto: e.message });
    } finally {
      setExecutando(null);
    }
  };

  return (
    <>
      <Cabecalho titulo="Relatórios"
        subtitulo="Coleta nos portais (robô Playwright) e importação dos arquivos baixados em dados/brutos/."
        acoes={<button className="secundario" disabled={!!executando} onClick={() => rodar("Importação", "/importar")}>
          {executando === "Importação" ? "Importando…" : "Importar arquivos baixados"}</button>} />

      <div className="fontes">
        {fontes.dados?.map((f) => (
          <div key={f.codigo} className="cartao fonte">
            <div><b>{f.codigo}</b><span className="mudo">{f.relatorios} relatórios importados</span></div>
            <button disabled={!!executando} onClick={() => rodar(`Coleta ${f.codigo}`, `/coletar/${f.codigo}`)}>
              {executando === `Coleta ${f.codigo}` ? "Coletando… (pode levar alguns minutos)" : "Coletar agora"}
            </button>
          </div>
        ))}
      </div>
      {mensagem && <div className={`aviso ${mensagem.tipo}`}>{mensagem.texto}</div>}

      <div className="barra">
        <div className="segmentado">
          {["", ...(fontes.dados?.map((f) => f.codigo) || [])].map((f) => (
            <button key={f} className={fonte === f ? "ativo" : ""} onClick={() => setFonte(f)}>{f || "Todas"}</button>))}
        </div>
      </div>
      {!relatorios.dados ? <Carregando erro={relatorios.erro} /> : (
        <div className="cartao sem-padding">
          <table className="tabela">
            <thead><tr><th>Fonte</th><th>Data</th><th>Referência</th><th>Status</th><th className="num">Linhas</th><th>Arquivo</th></tr></thead>
            <tbody>
              {relatorios.dados.map((r) => (
                <tr key={r.id}>
                  <td><span className="selo neutro">{r.fonte}</span></td>
                  <td>{data(r.data_referencia)}</td>
                  <td>{r.referencia}</td>
                  <td>{r.status || "—"}</td>
                  <td className="num">{r.qtd_linhas}</td>
                  <td className="mudo pequeno mono">{r.caminho}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
