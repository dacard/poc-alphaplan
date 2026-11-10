import { useState } from "react";
import { Administradora, enviar, Operadora, Produto } from "../api";
import { FormEmpresa, FormProduto } from "../components/Formularios";
import { Cabecalho, Carregando, useApi } from "../components/ui";
import { moeda } from "../formato";

async function remover(caminho: string, nome: string, aoRemovido: () => void) {
  if (!confirm(`Remover ${nome}?`)) return;
  try {
    await enviar(caminho, "DELETE");
    aoRemovido();
  } catch (e: any) {
    alert(e.message);
  }
}

export function Empresas({ tipo }: { tipo: "operadoras" | "administradoras" }) {
  const { dados, erro, recarregar } = useApi<(Operadora | Administradora)[]>(`/${tipo}`);
  const [editando, setEditando] = useState<Operadora | null>(null);
  const titulo = tipo === "operadoras" ? "Operadoras" : "Administradoras";
  const descricao = tipo === "operadoras"
    ? "Donas dos planos (Unimed, Amil, Samp…)."
    : "Comercializam planos das operadoras (Benevix, Easyplan…).";

  return (
    <>
      <Cabecalho titulo={titulo} subtitulo={descricao}
        acoes={<button onClick={() => setEditando({ nome: "", codigo_fonte: null })}>Nova</button>} />
      {!dados ? <Carregando erro={erro} /> : (
        <div className="cartao sem-padding">
          <table className="tabela">
            <thead><tr><th>Nome</th><th>Conector de relatórios</th><th /></tr></thead>
            <tbody>
              {dados.map((o) => (
                <tr key={o.id}>
                  <td className="forte">{o.nome}</td>
                  <td>{o.codigo_fonte ? <span className="selo ok">{o.codigo_fonte}</span> : <span className="mudo">—</span>}</td>
                  <td className="acoes-linha">
                    <button className="link" onClick={() => setEditando(o)}>Editar</button>
                    <button className="link perigo" onClick={() => remover(`/${tipo}/${o.id}`, o.nome, recarregar)}>Remover</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editando && <FormEmpresa key={editando.id ?? "novo"} tipo={tipo} inicial={editando} aoFechar={() => setEditando(null)}
        aoSalvo={() => { setEditando(null); recarregar(); }} />}
    </>
  );
}

export function Produtos() {
  const { dados, erro, recarregar } = useApi<Produto[]>("/produtos");
  const operadoras = useApi<Operadora[]>("/operadoras");
  const [editando, setEditando] = useState<Produto | null>(null);
  const nomeOp = (id: number) => operadoras.dados?.find((o) => o.id === id)?.nome ?? "—";

  return (
    <>
      <Cabecalho titulo="Produtos" subtitulo="Planos de cada operadora (Plano Gold, Plano A…)."
        acoes={<button onClick={() => setEditando({ nome: "", operadora_id: 0 })}>Novo produto</button>} />
      {!dados ? <Carregando erro={erro} /> : (
        <div className="cartao sem-padding">
          <table className="tabela">
            <thead><tr><th>Produto</th><th>Operadora</th><th>Mensalidade por faixa etária</th><th /></tr></thead>
            <tbody>
              {dados.map((p) => (
                <tr key={p.id}>
                  <td className="forte">{p.nome}</td>
                  <td>{nomeOp(p.operadora_id)}</td>
                  <td>{p.tabela_faixas?.length
                    ? <span className="mudo">{moeda(p.tabela_faixas[0])} (0–18) … {moeda(p.tabela_faixas.at(-1))} (59+)</span>
                    : <span className="mudo">valor fixo por colaborador</span>}</td>
                  <td className="acoes-linha">
                    <button className="link" onClick={() => setEditando(p)}>Editar</button>
                    <button className="link perigo" onClick={() => remover(`/produtos/${p.id}`, p.nome, recarregar)}>Remover</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editando && <FormProduto key={editando.id ?? "novo"} inicial={editando} aoFechar={() => setEditando(null)}
        aoSalvo={() => { setEditando(null); recarregar(); }} />}
    </>
  );
}
