import { useMemo, useState } from "react";
import { Colaborador, enviar } from "../../api";
import { FormColaborador } from "../../components/Formularios";
import { Carregando, useApi } from "../../components/ui";
import { data, moeda } from "../../formato";

const hojeMes = new Date().toISOString().slice(0, 7);
const ativo = (c: Colaborador) => c.data_inclusao.slice(0, 7) <= hojeMes &&
  (!c.data_exclusao || c.data_exclusao.slice(0, 7) > hojeMes);

export default function AbaColaboradores({ contratoId, aoMudar }: { contratoId: number; aoMudar: () => void }) {
  const { dados, erro } = useApi<Colaborador[]>(`/contratos/${contratoId}/colaboradores`);
  const [busca, setBusca] = useState("");
  const [filtro, setFiltro] = useState<"todos" | "ativos" | "excluidos">("ativos");
  const [editando, setEditando] = useState<Colaborador | null>(null);

  const lista = useMemo(() => (dados || []).filter((c) =>
    (c.nome.toLowerCase().includes(busca.toLowerCase()) || (c.cpf || "").includes(busca)) &&
    (filtro === "todos" || (filtro === "ativos") === ativo(c))), [dados, busca, filtro]);

  if (!dados) return <Carregando erro={erro} />;

  const remover = async (c: Colaborador) => {
    if (!confirm(`Remover ${c.nome} do cadastro? Para registrar um desligamento, prefira preencher a data de exclusão.`)) return;
    await enviar(`/colaboradores/${c.id}`, "DELETE");
    aoMudar();
  };

  const total = dados.reduce((s, c) => s + (ativo(c) ? c.valor_mensalidade : 0), 0);

  return (
    <>
      <div className="barra">
        <input className="busca" placeholder="Buscar por nome ou CPF…" value={busca} onChange={(e) => setBusca(e.target.value)} />
        <div className="segmentado">
          {(["ativos", "excluidos", "todos"] as const).map((f) => (
            <button key={f} className={filtro === f ? "ativo" : ""} onClick={() => setFiltro(f)}>
              {f === "ativos" ? "Ativos" : f === "excluidos" ? "Excluídos" : "Todos"}
            </button>))}
        </div>
        <span className="mudo">{lista.length} de {dados.length} · mensalidades ativas {moeda(total)}</span>
        <button onClick={() => setEditando({ contrato_id: contratoId, nome: "", data_inclusao: new Date().toISOString().slice(0, 10), valor_mensalidade: 0 })}>
          Novo colaborador
        </button>
      </div>
      <div className="cartao sem-padding">
        <table className="tabela">
          <thead>
            <tr><th>Nome</th><th>CPF</th><th>Nascimento</th><th>Inclusão</th><th>Exclusão</th>
              <th className="num">Mensalidade</th><th /></tr>
          </thead>
          <tbody>
            {lista.map((c) => (
              <tr key={c.id} className={ativo(c) ? "" : "inativo"}>
                <td className="forte">{c.nome}</td>
                <td className="mono">{c.cpf || "—"}</td>
                <td>{data(c.data_nascimento)}</td>
                <td>{data(c.data_inclusao)}</td>
                <td>{data(c.data_exclusao)}</td>
                <td className="num">{moeda(c.valor_mensalidade)}</td>
                <td className="acoes-linha">
                  <button className="link" onClick={() => setEditando(c)}>Editar</button>
                  <button className="link perigo" onClick={() => remover(c)}>Remover</button>
                </td>
              </tr>
            ))}
            {!lista.length && <tr><td colSpan={7} className="vazio">Nenhum colaborador.</td></tr>}
          </tbody>
        </table>
      </div>
      {editando && <FormColaborador inicial={editando} aoFechar={() => setEditando(null)}
        aoSalvo={() => { setEditando(null); aoMudar(); }} />}
    </>
  );
}
