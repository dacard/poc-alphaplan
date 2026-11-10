import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ContratoResumo, enviar } from "../api";
import { FormContrato } from "../components/Formularios";
import { Cabecalho, Carregando, useApi } from "../components/ui";
import { data, moeda, pct } from "../formato";
import AbaColaboradores from "./contrato/AbaColaboradores";
import AbaProcessado from "./contrato/AbaProcessado";
import AbaRelatorios from "./contrato/AbaRelatorios";

const ABAS = [
  { id: "colaboradores", rotulo: "Colaboradores" },
  { id: "relatorios", rotulo: "Relatórios" },
  { id: "processado", rotulo: "Processado" },
];

export default function Contrato() {
  const { id } = useParams();
  const contratoId = Number(id);
  const { dados: c, erro, recarregar } = useApi<ContratoResumo>(`/contratos/${id}/resumo`);
  const [params, setParams] = useSearchParams();
  const aba = params.get("aba") || "colaboradores";
  const [editando, setEditando] = useState(false);
  const [versao, setVersao] = useState(0); // força recarga das abas após mudanças no cadastro
  const navegar = useNavigate();

  if (!c) return <Carregando erro={erro} />;

  const atualizar = () => { recarregar(); setVersao((v) => v + 1); };
  const remover = async () => {
    if (!confirm("Remover este contrato?")) return;
    try {
      await enviar(`/contratos/${id}`, "DELETE");
      navegar(`/clientes/${c.cliente_id}`);
    } catch (e: any) {
      alert(e.message);
    }
  };

  return (
    <>
      <Cabecalho
        migalhas={<><Link to="/clientes">Clientes</Link> / <Link to={`/clientes/${c.cliente_id}`}>{c.cliente}</Link> /</>}
        titulo={`${c.produto}`}
        subtitulo={<>{c.operadora}{c.administradora && <> · comercializado por <b>{c.administradora}</b></>}</>}
        acoes={<>
          <button className="secundario" onClick={() => setEditando(true)}>Editar contrato</button>
          <button className="secundario perigo" onClick={remover}>Remover</button>
        </>}
      />

      <div className="cartao ficha">
        <div><span>Identificador no relatório</span><b className="mono">{c.identificador_relatorio}</b></div>
        <div><span>Fonte dos relatórios</span><b>{c.fonte || "—"}</b></div>
        <div><span>Início</span><b>{data(c.data_inicio)}</b></div>
        <div><span>Colaboradores ativos</span><b>{c.colaboradores_ativos}</b></div>
        <div><span>Casamento por</span><b>{c.chave_conciliacao === "cpf" ? "CPF, depois nome" : "Nome"}</b></div>
        <div><span>Tolerância</span><b>{moeda(c.tolerancia)}</b></div>
        <div className="largo">
          <span>Regras de comissão</span>
          <b>{c.regras_comissao.map((r, i) => (
            <span key={i} className="regra">
              {r.parcela_ate === r.parcela_de ? `parcela ${r.parcela_de}` :
                r.parcela_ate ? `parcelas ${r.parcela_de}–${r.parcela_ate}` : `parcela ${r.parcela_de} em diante`}: {pct(r.percentual)}
            </span>))}</b>
        </div>
        {c.observacoes && <div className="largo"><span>Observações</span><b className="normal">{c.observacoes}</b></div>}
      </div>

      <nav className="abas">
        {ABAS.map((a) => (
          <button key={a.id} className={aba === a.id ? "ativa" : ""} onClick={() => setParams({ aba: a.id })}>
            {a.rotulo}
          </button>
        ))}
      </nav>

      {aba === "colaboradores" && <AbaColaboradores key={versao} contratoId={contratoId} aoMudar={atualizar} />}
      {aba === "relatorios" && <AbaRelatorios key={versao} contratoId={contratoId} contratoRef={c.identificador_relatorio} />}
      {aba === "processado" && <AbaProcessado key={versao} contratoId={contratoId} aoMudar={atualizar} />}

      {editando && <FormContrato inicial={c} aoFechar={() => setEditando(false)}
        aoSalvo={() => { setEditando(false); atualizar(); }} />}
    </>
  );
}
