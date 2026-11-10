import { useState } from "react";
import { Conciliacao, Divergencia, enviar, Mes } from "../../api";
import { Carregando, Impacto, Status, useApi } from "../../components/ui";
import { competencia, competenciaLonga, moeda, pct, plural } from "../../formato";

const ROTULO_CURTO: Record<string, string> = {
  ausente: "Sem comissão",
  nao_cadastrado: "Não cadastrado",
  mensalidade: "Mensalidade",
  percentual: "Percentual",
  duplicidade: "Duplicidade",
  estorno: "Estorno",
};

export default function AbaProcessado({ contratoId, aoMudar }: { contratoId: number; aoMudar: () => void }) {
  const { dados, erro, recarregar } = useApi<Conciliacao>(`/contratos/${contratoId}/conciliacao`);
  const [aberto, setAberto] = useState<string | null>(null);

  if (!dados) return <Carregando erro={erro} />;
  if (!dados.meses.length) return <div className="aviso">Ainda não há relatórios para este contrato.</div>;

  const t = dados.totais;
  const mudou = () => { recarregar(); aoMudar(); };

  return (
    <>
      <div className="indicadores">
        <div className="indicador"><span>Meses analisados</span><b>{t.meses}</b></div>
        <div className="indicador"><span>Meses com divergência</span><b className={t.meses_divergentes ? "txt-alerta" : "txt-ok"}>{t.meses_divergentes}</b></div>
        <div className="indicador"><span>Comissão esperada</span><b>{moeda(t.esperado)}</b></div>
        <div className="indicador"><span>Comissão recebida</span><b>{moeda(t.processado)}</b></div>
        <div className="indicador destaque"><span>Diferença (recebido − esperado)</span><b><Impacto valor={t.impacto} /></b></div>
      </div>

      <div className="meses">
        {dados.meses.map((m) => (
          <CartaoMes key={m.competencia} mes={m} tipos={dados.tipos} contratoId={contratoId}
            aberto={aberto === m.competencia} alternar={() => setAberto(aberto === m.competencia ? null : m.competencia)}
            aoMudar={mudou} />
        ))}
      </div>
    </>
  );
}

function resumoMes(m: Mes): string {
  const c = m.contagem;
  const esp = m.esperado.vidas;
  if (m.status === "ok") {
    return `Sem divergências: ${plural(esp, "colaborador esperado teve", "colaboradores esperados tiveram")} comissão conforme o contrato.`;
  }
  const partes: string[] = [];
  if (esp) {
    const comRegistro = esp - (c.ausente || 0);
    partes.push(`Dos ${esp.toLocaleString("pt-BR")} colaboradores esperados, ${comRegistro.toLocaleString("pt-BR")} tiveram registro de comissão`
      + (c.ausente ? ` e ${plural(c.ausente, "ficou sem", "ficaram sem")}` : ""));
  } else {
    partes.push("Nenhum colaborador esperado neste mês");
  }
  if (c.nao_cadastrado) partes.push(`${plural(c.nao_cadastrado, "pessoa no relatório não está", "pessoas no relatório não estão")} no cadastro`);
  if (c.mensalidade) partes.push(`${plural(c.mensalidade, "mensalidade diferente", "mensalidades diferentes")} do cadastrado`);
  if (c.percentual) partes.push(`${plural(c.percentual, "percentual diferente", "percentuais diferentes")} da regra`);
  if (c.duplicidade) partes.push(`${plural(c.duplicidade, "parcela paga", "parcelas pagas")} em duplicidade`);
  if (c.estorno) partes.push(`${plural(c.estorno, "estorno", "estornos")}`);
  return partes.join("; ") + ".";
}

function CartaoMes({ mes: m, tipos, contratoId, aberto, alternar, aoMudar }: {
  mes: Mes; tipos: Record<string, string>; contratoId: number; aberto: boolean;
  alternar: () => void; aoMudar: () => void;
}) {
  const [filtro, setFiltro] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const divergente = m.status === "divergente";
  const lista = m.divergencias.filter((d) =>
    (!filtro || d.tipos.includes(filtro)) && d.nome.toLowerCase().includes(busca.toLowerCase()));

  return (
    <div className={`cartao mes ${divergente ? "divergente" : "ok"} ${aberto ? "aberto" : ""}`}>
      <button className="mes-topo" onClick={divergente ? alternar : undefined} disabled={!divergente}>
        <div className="mes-nome">
          {divergente && <span className="seta">{aberto ? "▾" : "▸"}</span>}
          <b>{competenciaLonga(m.competencia)}</b>
          <Status status={m.status} />
        </div>
        <div className="mes-col"><span>Esperado</span><b>{m.esperado.vidas} vidas · {moeda(m.esperado.comissao)}</b></div>
        <div className="mes-col"><span>Processado</span><b>{m.processado.vidas} vidas · {moeda(m.processado.comissao)}</b></div>
        <div className="mes-col dir"><span>Impacto</span><b><Impacto valor={m.impacto} /></b></div>
      </button>
      <p className="mes-resumo">{resumoMes(m)}</p>

      {aberto && (
        <div className="mes-detalhe">
          <div className="barra">
            <div className="filtros">
              <button className={!filtro ? "chip ativo" : "chip"} onClick={() => setFiltro(null)}>Todos ({m.divergencias.length})</button>
              {Object.entries(m.contagem).map(([t, n]) => (
                <button key={t} className={`chip ${filtro === t ? "ativo" : ""}`} title={tipos[t]} onClick={() => setFiltro(filtro === t ? null : t)}>
                  {ROTULO_CURTO[t] || t} ({n})
                </button>))}
            </div>
            <input className="busca pequena" placeholder="Buscar nome…" value={busca} onChange={(e) => setBusca(e.target.value)} />
          </div>
          <table className="tabela compacta divergencias">
            <thead>
              <tr>
                <th rowSpan={2}>Colaborador</th><th rowSpan={2}>Divergência</th>
                <th colSpan={3} className="grupo">Esperado (cadastro)</th>
                <th colSpan={3} className="grupo">Processado (relatório)</th>
                <th rowSpan={2} className="num">Impacto</th><th rowSpan={2} />
              </tr>
              <tr>
                <th className="num">Mensalidade</th><th className="num">%</th><th className="num">Comissão</th>
                <th className="num">Mensalidade</th><th className="num">% · parcela</th><th className="num">Comissão</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((d, i) => <LinhaDivergencia key={i} d={d} tipos={tipos} competencia={m.competencia} contratoId={contratoId} aoMudar={aoMudar} />)}
              {!lista.length && <tr><td colSpan={10} className="vazio">Nenhum registro com esse filtro.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function LinhaDivergencia({ d, tipos, competencia: comp, contratoId, aoMudar }: {
  d: Divergencia; tipos: Record<string, string>; competencia: string; contratoId: number; aoMudar: () => void;
}) {
  const [executando, setExecutando] = useState(false);
  const e = d.esperado, p = d.processado;

  const acao = async (corpo: object, pergunta: string) => {
    if (!confirm(pergunta)) return;
    setExecutando(true);
    try {
      await enviar(`/contratos/${contratoId}/acoes`, "POST", { ...corpo, competencia: comp });
      aoMudar();
    } catch (err: any) {
      alert(err.message);
      setExecutando(false);
    }
  };

  return (
    <tr>
      <td className="forte">{d.nome}
        {d.confianca?.startsWith("nome aproximado") && <div className="pequeno txt-alerta" title="Casado por semelhança de nome">≈ {d.confianca}</div>}
      </td>
      <td>{d.tipos.map((t) => <span key={t} className={`tag tag-${t}`} title={tipos[t]}>{ROTULO_CURTO[t] || t}</span>)}</td>
      <td className="num">{e ? moeda(e.mensalidade) : "—"}</td>
      <td className="num">{e ? pct(e.percentual) : "—"}</td>
      <td className="num">{e ? moeda(e.comissao) : "—"}</td>
      <td className={`num ${d.tipos.includes("mensalidade") ? "marcado" : ""}`}>{p ? moeda(p.mensalidade) : "—"}</td>
      <td className={`num ${d.tipos.includes("percentual") ? "marcado" : ""}`}>
        {p ? <>{p.percentuais.map((x) => pct(x)).join(", ") || "—"}<div className="mudo pequeno">parc. {p.parcelas.join(", ") || "—"}</div></> : "—"}
      </td>
      <td className="num">{p ? <>{moeda(p.comissao)}{p.estorno > 0 && <div className="pequeno txt-negativo">estorno {moeda(p.estorno)}</div>}</> : "—"}</td>
      <td className="num"><Impacto valor={d.impacto} /></td>
      <td className="acoes-linha">
        {d.tipos.includes("nao_cadastrado") && p && (
          <button className="link" disabled={executando} onClick={() => acao(
            { acao: "incluir", nome: d.nome, cpf: p.cpf, valor_mensalidade: p.mensalidade },
            `Incluir ${d.nome} no cadastro a partir de ${competencia(comp)}, com mensalidade ${moeda(p.mensalidade)}?`)}>
            Incluir no cadastro
          </button>)}
        {d.tipos.includes("ausente") && d.colaborador_id && (
          <button className="link" disabled={executando} onClick={() => acao(
            { acao: "desligar", colaborador_id: d.colaborador_id },
            `Registrar a saída de ${d.nome} a partir de ${competencia(comp)}?`)}>
            Registrar saída
          </button>)}
      </td>
    </tr>
  );
}
