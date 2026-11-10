import { Fragment, useState } from "react";
import { Linha, RelatorioContrato } from "../../api";
import { Carregando, useApi } from "../../components/ui";
import { competencia, data, moeda, pct } from "../../formato";

export default function AbaRelatorios({ contratoId, contratoRef }: { contratoId: number; contratoRef: string }) {
  const { dados, erro } = useApi<RelatorioContrato[]>(`/contratos/${contratoId}/relatorios`);
  const [aberto, setAberto] = useState<number | null>(null);

  if (!dados) return <Carregando erro={erro} />;
  if (!dados.length) return <div className="aviso">Nenhum relatório importado traz linhas deste contrato.
    Confira o identificador no relatório e se a fonte já foi coletada (menu Relatórios).</div>;

  return (
    <div className="cartao sem-padding">
      <table className="tabela clicavel">
        <thead>
          <tr><th>Data</th><th>Relatório</th><th>Status</th><th>Competências</th>
            <th className="num">Linhas do contrato</th><th className="num">Pessoas</th><th className="num">Comissão</th></tr>
        </thead>
        <tbody>
          {dados.map((r) => (
            <Fragment key={r.id}>
              <tr onClick={() => setAberto(aberto === r.id ? null : r.id)} className={aberto === r.id ? "expandida" : ""}>
                <td>{data(r.data_referencia)}</td>
                <td><span className="seta">{aberto === r.id ? "▾" : "▸"}</span> {r.referencia}
                  <div className="mudo pequeno mono">{r.caminho.split("/").slice(1).join("/")}</div></td>
                <td>{r.status || "—"}</td>
                <td>{r.competencias.map(competencia).join(", ")}</td>
                <td className="num">{r.linhas_contrato}</td>
                <td className="num">{r.pessoas}</td>
                <td className="num">{moeda(r.comissao)}</td>
              </tr>
              {aberto === r.id && (
                <tr className="detalhe"><td colSpan={7}><LinhasRelatorio relatorioId={r.id} contratoRef={contratoRef} /></td></tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LinhasRelatorio({ relatorioId, contratoRef }: { relatorioId: number; contratoRef: string }) {
  const { dados, erro } = useApi<Linha[]>(`/relatorios/${relatorioId}/linhas?contrato_ref=${encodeURIComponent(contratoRef)}`);
  if (!dados) return <Carregando erro={erro} />;
  return (
    <table className="tabela compacta">
      <thead>
        <tr><th>Nome</th><th>CPF</th><th>Competência</th><th className="num">Parcela</th><th className="num">%</th>
          <th className="num">Mensalidade</th><th className="num">Comissão</th><th className="num">Estorno</th></tr>
      </thead>
      <tbody>
        {dados.map((l) => (
          <tr key={l.id}>
            <td>{l.nome}</td><td className="mono">{l.cpf || "—"}</td><td>{competencia(l.competencia)}</td>
            <td className="num">{l.parcela ?? "—"}</td><td className="num">{pct(l.percentual)}</td>
            <td className="num">{moeda(l.valor_base)}</td><td className="num">{moeda(l.valor_comissao)}</td>
            <td className="num">{l.valor_estorno ? moeda(l.valor_estorno) : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
