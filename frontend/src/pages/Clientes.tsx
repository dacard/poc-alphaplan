import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Cliente } from "../api";
import { FormCliente } from "../components/Formularios";
import { Cabecalho, Carregando, Impacto, useApi } from "../components/ui";
import { plural } from "../formato";

interface ClienteResumo extends Cliente {
  id: number;
  contratos: number;
  colaboradores_ativos: number;
  meses_divergentes: number;
  impacto: number;
}

export default function Clientes() {
  const { dados, erro, recarregar } = useApi<ClienteResumo[]>("/clientes-resumo");
  const [busca, setBusca] = useState("");
  const [novo, setNovo] = useState(false);
  const navegar = useNavigate();

  const lista = useMemo(
    () => (dados || []).filter((c) => c.nome.toLowerCase().includes(busca.toLowerCase())),
    [dados, busca]);

  return (
    <>
      <Cabecalho
        titulo="Clientes"
        subtitulo="Empresas atendidas pela Alphaplan. Clique em um cliente para ver os contratos."
        acoes={<button onClick={() => setNovo(true)}>Novo cliente</button>}
      />
      <input className="busca" placeholder="Buscar cliente…" value={busca} onChange={(e) => setBusca(e.target.value)} />
      {!dados ? <Carregando erro={erro} /> : (
        <div className="cartao sem-padding">
          <table className="tabela clicavel">
            <thead>
              <tr>
                <th>Cliente</th><th>CNPJ</th><th className="num">Contratos</th>
                <th className="num">Colaboradores ativos</th><th>Situação</th>
                <th className="num">Impacto acumulado</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((c) => (
                <tr key={c.id} onClick={() => navegar(`/clientes/${c.id}`)}>
                  <td className="forte">{c.nome}</td>
                  <td>{c.cnpj || "—"}</td>
                  <td className="num">{c.contratos}</td>
                  <td className="num">{c.colaboradores_ativos.toLocaleString("pt-BR")}</td>
                  <td>{c.meses_divergentes
                    ? <span className="selo alerta">{plural(c.meses_divergentes, "mês divergente", "meses divergentes")}</span>
                    : <span className="selo ok">Sem divergência</span>}</td>
                  <td className="num"><Impacto valor={c.impacto} /></td>
                </tr>
              ))}
              {!lista.length && <tr><td colSpan={6} className="vazio">Nenhum cliente encontrado.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {novo && <FormCliente inicial={{ nome: "" }} aoFechar={() => setNovo(false)}
        aoSalvo={(c) => { setNovo(false); recarregar(); navegar(`/clientes/${c.id}`); }} />}
    </>
  );
}
