import { FormEvent, useState } from "react";
import {
  Administradora, Cliente, Colaborador, Contrato, enviar, Operadora, Produto, Regra,
} from "../api";
import { Campo, Modal, RodapeForm, useApi } from "./ui";

const FAIXAS = ["0–18", "19–23", "24–28", "29–33", "34–38", "39–43", "44–48", "49–53", "54–58", "59+"];
const FONTES = ["", "samp", "easyplan"];

/** Salva (POST ou PUT) e trata erro/estado. */
function useSalvar<T extends { id?: number }>(recurso: string, aoSalvo: (item: T) => void) {
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const salvar = async (e: FormEvent, item: T) => {
    e.preventDefault();
    setSalvando(true);
    setErro(null);
    try {
      const salvo = item.id
        ? await enviar(`/${recurso}/${item.id}`, "PUT", item)
        : await enviar(`/${recurso}`, "POST", item);
      aoSalvo(salvo as T);
    } catch (err: any) {
      setErro(err.message);
    } finally {
      setSalvando(false);
    }
  };
  return { erro, salvando, salvar };
}

interface PropsForm<T> { inicial: T; aoFechar: () => void; aoSalvo: (item: T) => void }

// ---------- Operadora / Administradora ----------

export function FormEmpresa({ tipo, inicial, aoFechar, aoSalvo }:
  PropsForm<Operadora | Administradora> & { tipo: "operadoras" | "administradoras" }) {
  const [item, setItem] = useState(inicial);
  const { erro, salvando, salvar } = useSalvar(tipo, aoSalvo);
  const nome = tipo === "operadoras" ? "operadora" : "administradora";
  return (
    <Modal titulo={item.id ? `Editar ${nome}` : `Nova ${nome}`} aoFechar={aoFechar}>
      <form onSubmit={(e) => salvar(e, item)}>
        <Campo rotulo="Nome">
          <input required autoFocus value={item.nome} onChange={(e) => setItem({ ...item, nome: e.target.value })} />
        </Campo>
        <Campo rotulo="Conector de relatórios" dica="Robô + leitor de relatório usado para esta fonte. Vazio se os relatórios não vêm dela.">
          <select value={item.codigo_fonte || ""} onChange={(e) => setItem({ ...item, codigo_fonte: e.target.value || null })}>
            {FONTES.map((f) => <option key={f} value={f}>{f || "— nenhum —"}</option>)}
          </select>
        </Campo>
        <RodapeForm erro={erro} salvando={salvando} aoCancelar={aoFechar} />
      </form>
    </Modal>
  );
}

// ---------- Produto ----------

export function FormProduto({ inicial, aoFechar, aoSalvo }: PropsForm<Produto>) {
  const [item, setItem] = useState(inicial);
  const [usarFaixas, setUsarFaixas] = useState(!!inicial.tabela_faixas?.length);
  const operadoras = useApi<Operadora[]>("/operadoras");
  const { erro, salvando, salvar } = useSalvar("produtos", aoSalvo);
  const faixas = item.tabela_faixas?.length ? item.tabela_faixas : Array(10).fill(0);

  return (
    <Modal titulo={item.id ? "Editar produto" : "Novo produto"} aoFechar={aoFechar}>
      <form onSubmit={(e) => salvar(e, { ...item, tabela_faixas: usarFaixas ? faixas : null })}>
        <div className="grade-2">
          <Campo rotulo="Nome do produto">
            <input required autoFocus value={item.nome} onChange={(e) => setItem({ ...item, nome: e.target.value })} />
          </Campo>
          <Campo rotulo="Operadora">
            <select required value={item.operadora_id || ""} onChange={(e) => setItem({ ...item, operadora_id: Number(e.target.value) })}>
              <option value="">Selecione…</option>
              {operadoras.dados?.map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}
            </select>
          </Campo>
        </div>
        <label className="checkbox">
          <input type="checkbox" checked={usarFaixas} onChange={(e) => setUsarFaixas(e.target.checked)} />
          Mensalidade por faixa etária (ANS)
        </label>
        {usarFaixas && (
          <div className="faixas">
            {FAIXAS.map((f, i) => (
              <Campo key={f} rotulo={f}>
                <input type="number" step="0.01" min="0" value={faixas[i]}
                  onChange={(e) => {
                    const novo = [...faixas];
                    novo[i] = Number(e.target.value);
                    setItem({ ...item, tabela_faixas: novo });
                  }} />
              </Campo>
            ))}
          </div>
        )}
        <p className="nota">Com a tabela preenchida, a mensalidade esperada de quem tem data de nascimento cadastrada
          é calculada pela idade em cada mês. Sem ela, vale o valor informado no colaborador.</p>
        <RodapeForm erro={erro} salvando={salvando} aoCancelar={aoFechar} />
      </form>
    </Modal>
  );
}

// ---------- Cliente ----------

export function FormCliente({ inicial, aoFechar, aoSalvo }: PropsForm<Cliente>) {
  const [item, setItem] = useState(inicial);
  const { erro, salvando, salvar } = useSalvar("clientes", aoSalvo);
  return (
    <Modal titulo={item.id ? "Editar cliente" : "Novo cliente"} aoFechar={aoFechar}>
      <form onSubmit={(e) => salvar(e, item)}>
        <Campo rotulo="Razão social / nome">
          <input required autoFocus value={item.nome} onChange={(e) => setItem({ ...item, nome: e.target.value })} />
        </Campo>
        <Campo rotulo="CNPJ">
          <input value={item.cnpj || ""} onChange={(e) => setItem({ ...item, cnpj: e.target.value || null })} />
        </Campo>
        <RodapeForm erro={erro} salvando={salvando} aoCancelar={aoFechar} />
      </form>
    </Modal>
  );
}

// ---------- Contrato ----------

export function FormContrato({ inicial, aoFechar, aoSalvo }: PropsForm<Contrato>) {
  const [item, setItem] = useState(inicial);
  const produtos = useApi<Produto[]>("/produtos");
  const operadoras = useApi<Operadora[]>("/operadoras");
  const adms = useApi<Administradora[]>("/administradoras");
  const { erro, salvando, salvar } = useSalvar("contratos", aoSalvo);
  const nomeOperadora = (id: number) => operadoras.dados?.find((o) => o.id === id)?.nome ?? "";

  const setRegra = (i: number, campo: keyof Regra, valor: string) => {
    const regras = item.regras_comissao.map((r, j) =>
      j !== i ? r : { ...r, [campo]: valor === "" ? null : Number(valor) });
    setItem({ ...item, regras_comissao: regras });
  };

  return (
    <Modal titulo={item.id ? "Editar contrato" : "Novo contrato"} aoFechar={aoFechar} largo>
      <form onSubmit={(e) => salvar(e, item)}>
        <div className="grade-2">
          <Campo rotulo="Produto (plano)">
            <select required value={item.produto_id || ""} onChange={(e) => setItem({ ...item, produto_id: Number(e.target.value) })}>
              <option value="">Selecione…</option>
              {produtos.dados?.map((p) => <option key={p.id} value={p.id}>{p.nome} — {nomeOperadora(p.operadora_id)}</option>)}
            </select>
          </Campo>
          <Campo rotulo="Administradora" dica="Vazio quando o contrato é direto com a operadora.">
            <select value={item.administradora_id ?? ""} onChange={(e) => setItem({ ...item, administradora_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">— direto com a operadora —</option>
              {adms.dados?.map((a) => <option key={a.id} value={a.id}>{a.nome}</option>)}
            </select>
          </Campo>
          <Campo rotulo="Identificador no relatório" dica="Como o contrato aparece no relatório da fonte. Samp: nº do contrato. Easyplan: “PRODUTOR / Modalidade N” (PRODUTOR = empresa).">
            <input required value={item.identificador_relatorio} onChange={(e) => setItem({ ...item, identificador_relatorio: e.target.value })} />
          </Campo>
          <Campo rotulo="Início do contrato">
            <input required type="date" value={item.data_inicio} onChange={(e) => setItem({ ...item, data_inicio: e.target.value })} />
          </Campo>
          <Campo rotulo="Chave para casar colaboradores">
            <select value={item.chave_conciliacao} onChange={(e) => setItem({ ...item, chave_conciliacao: e.target.value as "nome" | "cpf" })}>
              <option value="nome">Nome</option>
              <option value="cpf">CPF (usa o nome quando faltar CPF)</option>
            </select>
          </Campo>
          <Campo rotulo="Tolerância na mensalidade (R$)">
            <input type="number" step="0.01" min="0" value={item.tolerancia} onChange={(e) => setItem({ ...item, tolerancia: Number(e.target.value) })} />
          </Campo>
        </div>

        <h3>Regras de comissão</h3>
        <table className="tabela compacta">
          <thead><tr><th>Da parcela</th><th>Até a parcela</th><th>% sobre a mensalidade</th><th /></tr></thead>
          <tbody>
            {item.regras_comissao.map((r, i) => (
              <tr key={i}>
                <td><input type="number" min="1" required value={r.parcela_de} onChange={(e) => setRegra(i, "parcela_de", e.target.value)} /></td>
                <td><input type="number" min="1" placeholder="em diante" value={r.parcela_ate ?? ""} onChange={(e) => setRegra(i, "parcela_ate", e.target.value)} /></td>
                <td><input type="number" step="0.01" min="0" required value={r.percentual} onChange={(e) => setRegra(i, "percentual", e.target.value)} /></td>
                <td><button type="button" className="icone" onClick={() => setItem({ ...item, regras_comissao: item.regras_comissao.filter((_, j) => j !== i) })}>×</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <button type="button" className="link" onClick={() => {
          const ultima = item.regras_comissao.at(-1);
          const de = ultima ? (ultima.parcela_ate ?? ultima.parcela_de) + 1 : 1;
          setItem({ ...item, regras_comissao: [...item.regras_comissao, { parcela_de: de, parcela_ate: null, percentual: 0 }] });
        }}>+ adicionar faixa de parcelas</button>
        <p className="nota">Ex.: parcela 1 = 100% (a 1ª mensalidade inteira é da Alphaplan); parcela 2 em diante = 5%.</p>

        <Campo rotulo="Observações">
          <textarea rows={2} value={item.observacoes || ""} onChange={(e) => setItem({ ...item, observacoes: e.target.value })} />
        </Campo>
        <RodapeForm erro={erro} salvando={salvando} aoCancelar={aoFechar} />
      </form>
    </Modal>
  );
}

export const contratoVazio = (cliente_id: number): Contrato => ({
  cliente_id, produto_id: 0, administradora_id: null, identificador_relatorio: "",
  data_inicio: new Date().toISOString().slice(0, 10), chave_conciliacao: "nome", tolerancia: 0.05,
  regras_comissao: [
    { parcela_de: 1, parcela_ate: 1, percentual: 100 },
    { parcela_de: 2, parcela_ate: null, percentual: 5 },
  ],
});

// ---------- Colaborador ----------

export function FormColaborador({ inicial, aoFechar, aoSalvo }: PropsForm<Colaborador>) {
  const [item, setItem] = useState(inicial);
  const { erro, salvando, salvar } = useSalvar("colaboradores", aoSalvo);
  const set = (campo: keyof Colaborador, valor: string) =>
    setItem({ ...item, [campo]: valor === "" ? null : valor });
  const setHistorico = (i: number, h: { a_partir: string; valor: number }) =>
    setItem({ ...item, historico_mensalidade: (item.historico_mensalidade || []).map((x, j) => (j === i ? h : x)) });
  return (
    <Modal titulo={item.id ? "Editar colaborador" : "Novo colaborador"} aoFechar={aoFechar}>
      <form onSubmit={(e) => salvar(e, item)}>
        <Campo rotulo="Nome">
          <input required autoFocus value={item.nome} onChange={(e) => set("nome", e.target.value)} />
        </Campo>
        <div className="grade-2">
          <Campo rotulo="CPF">
            <input value={item.cpf || ""} onChange={(e) => set("cpf", e.target.value.replace(/\D/g, ""))} />
          </Campo>
          <Campo rotulo="Data de nascimento" dica="Usada com a tabela por faixa etária do produto.">
            <input type="date" value={item.data_nascimento || ""} onChange={(e) => set("data_nascimento", e.target.value)} />
          </Campo>
          <Campo rotulo="Inclusão no contrato">
            <input required type="date" value={item.data_inclusao} onChange={(e) => set("data_inclusao", e.target.value)} />
          </Campo>
          <Campo rotulo="Exclusão" dica="A partir deste mês não deve haver cobrança.">
            <input type="date" value={item.data_exclusao || ""} onChange={(e) => set("data_exclusao", e.target.value)} />
          </Campo>
          <Campo rotulo="Mensalidade inicial (R$)">
            <input required type="number" step="0.01" min="0" value={item.valor_mensalidade}
              onChange={(e) => setItem({ ...item, valor_mensalidade: Number(e.target.value) })} />
          </Campo>
        </div>

        <h3>Reajustes de mensalidade</h3>
        {(item.historico_mensalidade || []).map((h, i) => (
          <div key={i} className="grade-reajuste">
            <input type="month" required value={h.a_partir} onChange={(e) => setHistorico(i, { ...h, a_partir: e.target.value })} />
            <input type="number" step="0.01" min="0" required value={h.valor} onChange={(e) => setHistorico(i, { ...h, valor: Number(e.target.value) })} />
            <button type="button" className="icone" onClick={() => setItem({ ...item, historico_mensalidade: item.historico_mensalidade!.filter((_, j) => j !== i) })}>×</button>
          </div>
        ))}
        <button type="button" className="link" onClick={() => setItem({
          ...item, historico_mensalidade: [...(item.historico_mensalidade || []), { a_partir: new Date().toISOString().slice(0, 7), valor: item.valor_mensalidade }],
        })}>+ adicionar reajuste (mês a partir do qual vale o novo valor)</button>
        <RodapeForm erro={erro} salvando={salvando} aoCancelar={aoFechar} />
      </form>
    </Modal>
  );
}
