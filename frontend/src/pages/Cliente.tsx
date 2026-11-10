import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Cliente as TCliente, ContratoResumo, enviar } from "../api";
import { contratoVazio, FormCliente, FormContrato } from "../components/Formularios";
import { Cabecalho, Carregando, Impacto, Status, useApi } from "../components/ui";
import { competencia, data } from "../formato";

export default function Cliente() {
  const { id } = useParams();
  const cliente = useApi<TCliente>(`/clientes/${id}`);
  const contratos = useApi<ContratoResumo[]>(`/clientes/${id}/contratos`);
  const [editando, setEditando] = useState(false);
  const [novoContrato, setNovoContrato] = useState(false);
  const navegar = useNavigate();

  if (!cliente.dados) return <Carregando erro={cliente.erro} />;

  const remover = async () => {
    if (!confirm(`Remover o cliente ${cliente.dados!.nome}?`)) return;
    try {
      await enviar(`/clientes/${id}`, "DELETE");
      navegar("/clientes");
    } catch (e: any) {
      alert(e.message);
    }
  };

  return (
    <>
      <Cabecalho
        migalhas={<><Link to="/clientes">Clientes</Link> /</>}
        titulo={cliente.dados.nome}
        subtitulo={cliente.dados.cnpj ? `CNPJ ${cliente.dados.cnpj}` : undefined}
        acoes={<>
          <button className="secundario" onClick={() => setEditando(true)}>Editar</button>
          <button className="secundario perigo" onClick={remover}>Remover</button>
          <button onClick={() => setNovoContrato(true)}>Novo contrato</button>
        </>}
      />

      <h2 className="secao">Contratos</h2>
      {!contratos.dados ? <Carregando erro={contratos.erro} /> : (
        <div className="cartao sem-padding">
          <table className="tabela clicavel">
            <thead>
              <tr>
                <th>Produto</th><th>Operadora</th><th>Administradora</th><th>Identificador</th>
                <th>Início</th><th className="num">Colaboradores</th><th>Último mês</th>
                <th className="num">Impacto acumulado</th>
              </tr>
            </thead>
            <tbody>
              {contratos.dados.map((c) => (
                <tr key={c.id} onClick={() => navegar(`/contratos/${c.id}`)}>
                  <td className="forte">{c.produto}</td>
                  <td>{c.operadora}</td>
                  <td>{c.administradora || <span className="mudo">direto</span>}</td>
                  <td className="mono">{c.identificador_relatorio}</td>
                  <td>{data(c.data_inicio)}</td>
                  <td className="num">{c.colaboradores_ativos}</td>
                  <td>{c.conciliacao?.ultimo_mes
                    ? <><span className="mudo">{competencia(c.conciliacao.ultimo_mes.competencia)}</span> <Status status={c.conciliacao.ultimo_mes.status} /></>
                    : <span className="mudo">sem relatórios</span>}</td>
                  <td className="num">{c.conciliacao ? <Impacto valor={c.conciliacao.impacto} /> : "—"}</td>
                </tr>
              ))}
              {!contratos.dados.length && <tr><td colSpan={8} className="vazio">Nenhum contrato cadastrado.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {editando && <FormCliente inicial={cliente.dados} aoFechar={() => setEditando(false)}
        aoSalvo={() => { setEditando(false); cliente.recarregar(); }} />}
      {novoContrato && <FormContrato inicial={contratoVazio(Number(id))} aoFechar={() => setNovoContrato(false)}
        aoSalvo={(c) => { setNovoContrato(false); navegar(`/contratos/${c.id}`); }} />}
    </>
  );
}
