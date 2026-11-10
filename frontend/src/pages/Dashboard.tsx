import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Cliente } from "../api";
import FiltroClientes from "../components/FiltroClientes";
import GraficoLinha, { Serie } from "../components/GraficoLinha";
import { Cabecalho, Carregando, Impacto, useApi } from "../components/ui";
import { competencia, moeda } from "../formato";

interface PontoSerie {
  competencia: string; receita: number; bruta: number; estornos: number;
  esperado: number | null; vidas: number; parcial: boolean;
}
interface PontoProjecao { competencia: string; vidas: number; receita: number; receita_min: number; receita_max: number }
interface Alerta {
  contrato_id: number; cliente: string; produto: string; identificador: string;
  receita_antes: number; receita_depois: number; variacao: number; variacao_pct: number;
  vidas_antes: number; vidas_depois: number; causa: string; tipo: "sem_pagamento" | "vidas" | "valor";
}
interface DadosDashboard {
  alertas: { periodo_anterior: [string, string]; periodo_recente: [string, string]; total: number; perda_mensal: number; itens: Alerta[] };
  indicadores: Record<"clientes" | "operadoras" | "administradoras" | "contratos" | "colaboradores" |
    "relatorios" | "pagamentos" | "receita" | "estornos", number>;
  serie: PontoSerie[];
  projecao: {
    meses: PontoProjecao[];
    base: string[];
    resumo: null | {
      vidas_por_mes: number; receita_por_vida: number; receita_por_vida_por_mes: number; estornos_medios: number;
      vidas_atual: number; receita_atual: number; vidas_fim: number; receita_fim: number; receita_total_projetada: number;
    };
  };
}

const COR = { receita: "#2a78d6", esperado: "#eb6834" };
const compacto = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
const moedaEixo = (v: number) => `R$ ${compacto.format(v)}`;
const inteiro = (v: number) => Math.round(v).toLocaleString("pt-BR");

export default function Dashboard() {
  const clientes = useApi<Cliente[]>("/clientes");
  const [selecao, setSelecao] = useState<number[] | null>(null);
  const caminho = selecao == null ? "/dashboard" : `/dashboard?clientes=${selecao.join(",")}`;
  const { dados, erro, carregando } = useApi<DadosDashboard>(caminho);
  const [tabela, setTabela] = useState(false);

  const opcoes = useMemo(() => (clientes.dados || [])
    .map((c) => ({ id: c.id!, nome: c.nome }))
    .sort((a, b) => a.nome.localeCompare(b.nome)), [clientes.dados]);

  return (
    <>
      <Cabecalho titulo="Dashboard" subtitulo="Visão geral das comissões processadas e da projeção para os próximos meses." />
      <div className="barra">
        <FiltroClientes opcoes={opcoes} selecionados={selecao} aoMudar={setSelecao} />
      </div>
      {!dados ? <Carregando erro={erro} /> : (
        <div className={carregando ? "recarregando" : ""}>
          <Indicadores d={dados} />
          <PainelAlertas a={dados.alertas} />
          {dados.serie.length ? (
            <>
              <CartaoReceita d={dados} tabela={tabela} setTabela={setTabela} />
              <CartaoVidas d={dados} />
            </>
          ) : <div className="aviso">Nenhum relatório processado para a seleção.</div>}
        </div>
      )}
    </>
  );
}

const ROTULO_CAUSA = { sem_pagamento: "Sem pagamentos", vidas: "Saída de colaboradores", valor: "Valor por vida" };

function PainelAlertas({ a }: { a: DadosDashboard["alertas"] }) {
  const navegar = useNavigate();
  const periodo = (p: [string, string]) => `${competencia(p[0])}–${competencia(p[1])}`;
  return (
    <div className="cartao grafico-cartao sem-padding alertas">
      <div className="grafico-topo alertas-topo">
        <div>
          <h2>Contratos que precisam de atenção</h2>
          <p className="mudo pequeno">
            Maiores quedas de receita recorrente: média de {periodo(a.periodo_recente)} contra {periodo(a.periodo_anterior)}.
            Parcelas de agenciamento ficam de fora (o fim delas é esperado).
          </p>
        </div>
        {a.total > 0 && (
          <div className="alertas-resumo">
            <b>{a.total}</b> <span className="mudo">contratos com queda</span>
            <Impacto valor={a.perda_mensal} /><span className="mudo">/mês</span>
          </div>
        )}
      </div>
      {!a.itens.length ? (
        <div className="vazio">Nenhum contrato com queda de receita no período.</div>
      ) : (
        <table className="tabela clicavel">
          <thead>
            <tr>
              <th className="num">#</th><th>Cliente / contrato</th>
              <th className="num">Receita/mês antes</th><th className="num">Agora</th>
              <th className="num">Variação</th><th>Causa provável</th>
            </tr>
          </thead>
          <tbody>
            {a.itens.map((x, i) => (
              <tr key={x.contrato_id} onClick={() => navegar(`/contratos/${x.contrato_id}?aba=processado`)}>
                <td className="num mudo">{i + 1}</td>
                <td><div className="forte">{x.cliente}</div>
                  <div className="mudo pequeno">{x.produto} · <span className="mono">{x.identificador}</span></div></td>
                <td className="num">{moeda(x.receita_antes)}</td>
                <td className="num">{moeda(x.receita_depois)}</td>
                <td className="num"><Impacto valor={x.variacao} />
                  <div className="mudo pequeno">{x.variacao_pct.toLocaleString("pt-BR")}%</div></td>
                <td><span className={`tag tag-causa-${x.tipo}`}>{ROTULO_CAUSA[x.tipo]}</span>
                  <div className="mudo pequeno">{x.causa}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Indicadores({ d }: { d: DadosDashboard }) {
  const i = d.indicadores;
  const itens: [string, string, string?][] = [
    ["Clientes", inteiro(i.clientes), "/clientes"],
    ["Operadoras", inteiro(i.operadoras), "/operadoras"],
    ["Administradoras", inteiro(i.administradoras), "/administradoras"],
    ["Contratos", inteiro(i.contratos)],
    ["Colaboradores ativos", inteiro(i.colaboradores)],
    ["Relatórios processados", inteiro(i.relatorios), "/relatorios"],
    ["Pagamentos processados", inteiro(i.pagamentos)],
  ];
  return (
    <div className="painel-indicadores">
      <div className="cartao heroi">
        <span>Receita total</span>
        <b>{moeda(i.receita)}</b>
        <small className="mudo">comissões recebidas, já descontados {moeda(i.estornos)} de estornos</small>
      </div>
      <div className="grade-indicadores">
        {itens.map(([rotulo, valor, link]) => (
          <div key={rotulo} className="cartao indicador-mini">
            <span>{rotulo}</span>
            {link ? <Link to={link}><b>{valor}</b></Link> : <b>{valor}</b>}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Junta realizado (sem o mês parcial) e projeção no mesmo eixo de meses. */
function useEixo(d: DadosDashboard) {
  return useMemo(() => {
    const reais = d.serie.filter((s) => !s.parcial);
    const proj = d.projecao.meses;
    const meses = [...reais.map((s) => s.competencia), ...proj.map((p) => p.competencia)];
    return { reais, proj, meses, inicioProjecao: proj.length ? reais.length : null };
  }, [d]);
}

function CartaoReceita({ d, tabela, setTabela }: { d: DadosDashboard; tabela: boolean; setTabela: (v: boolean) => void }) {
  const { reais, proj, meses, inicioProjecao } = useEixo(d);
  const parcial = d.serie.find((s) => s.parcial);
  const r = d.projecao.resumo;

  const series: Serie[] = [
    { id: "receita", nome: "Receita recebida", cor: COR.receita,
      valores: [...reais.map((s) => s.receita), ...proj.map(() => null)] },
    { id: "esperado", nome: "Esperado pelo cadastro", cor: COR.esperado,
      valores: [...reais.map((s) => s.esperado), ...proj.map(() => null)] },
  ];
  if (proj.length && reais.length) {
    const ultimo = reais[reais.length - 1];
    series.push({
      id: "projecao", nome: "Projeção", cor: COR.receita, tracejado: true,
      // começa no último mês realizado para a linha continuar sem quebra
      valores: [...reais.map((s, i) => (i === reais.length - 1 ? ultimo.receita : null)), ...proj.map((p) => p.receita)],
      faixa: [...reais.map((_, i) => (i === reais.length - 1 ? [ultimo.receita, ultimo.receita] as [number, number] : null)),
        ...proj.map((p) => [p.receita_min, p.receita_max] as [number, number])],
    });
  }

  return (
    <div className="cartao grafico-cartao">
      <div className="grafico-topo">
        <div>
          <h2>Receita por competência</h2>
          <p className="mudo pequeno">Comissão líquida recebida em cada mês de competência, comparada ao esperado pelo cadastro.
            A área sombreada é a projeção.</p>
        </div>
        <div className="segmentado">
          <button className={!tabela ? "ativo" : ""} onClick={() => setTabela(false)}>Gráfico</button>
          <button className={tabela ? "ativo" : ""} onClick={() => setTabela(true)}>Tabela</button>
        </div>
      </div>

      {tabela ? <TabelaReceita d={d} /> : (
        <GraficoLinha rotulos={meses.map(competencia)} series={series} formatar={moeda}
          formatarEixo={moedaEixo} inicioProjecao={inicioProjecao} />
      )}

      {r && (
        <div className="resumo-projecao">
          <div><span>Receita projetada ({competencia(proj[0].competencia)} a {competencia(proj[proj.length - 1].competencia)})</span>
            <b>{moeda(r.receita_total_projetada)}</b><small className="mudo">{proj.length} meses</small></div>
          <div><span>Receita prevista em {competencia(proj[proj.length - 1].competencia)}</span><b>{moeda(r.receita_fim)}</b>
            <small className="mudo">hoje {moeda(r.receita_atual)}/mês</small></div>
          <div><span>Tendência de vidas</span><b>{r.vidas_por_mes >= 0 ? "+" : ""}{r.vidas_por_mes.toLocaleString("pt-BR")}/mês</b>
            <small className="mudo">{inteiro(r.vidas_atual)} → {inteiro(r.vidas_fim)} vidas</small></div>
          <div><span>Receita por vida</span><b>{moeda(r.receita_por_vida)}</b>
            <small className="mudo">{r.receita_por_vida_por_mes >= 0 ? "subindo" : "caindo"} {moeda(Math.abs(r.receita_por_vida_por_mes))}/mês</small></div>
          <div><span>Estornos (média mensal)</span><b>{moeda(r.estornos_medios)}</b></div>
        </div>
      )}
      <p className="nota">
        Projeção: tendência das vidas com comissão × tendência da receita por vida nos últimos {d.projecao.base.length} meses
        completos ({d.projecao.base.length ? `${competencia(d.projecao.base[0])} a ${competencia(d.projecao.base[d.projecao.base.length - 1])}` : "—"}).
        A receita por vida usa tendência amortecida, porque quedas como o fim do agenciamento se estabilizam.
        {parcial && <> O mês em andamento ({competencia(parcial.competencia)}, {moeda(parcial.receita)} até agora) entra como projeção.</>}
      </p>
    </div>
  );
}

function CartaoVidas({ d }: { d: DadosDashboard }) {
  const { reais, proj, meses, inicioProjecao } = useEixo(d);
  const series: Serie[] = [
    { id: "vidas", nome: "Vidas com comissão", cor: COR.receita,
      valores: [...reais.map((s) => s.vidas), ...proj.map(() => null)] },
  ];
  if (proj.length && reais.length) {
    series.push({
      id: "vidas-proj", nome: "Projeção", cor: COR.receita, tracejado: true,
      valores: [...reais.map((s, i) => (i === reais.length - 1 ? s.vidas : null)), ...proj.map((p) => p.vidas)],
    });
  }
  return (
    <div className="cartao grafico-cartao">
      <div className="grafico-topo">
        <div>
          <h2>Colaboradores com comissão por competência</h2>
          <p className="mudo pequeno">Pessoas distintas com pagamento de comissão no mês: mostra a entrada e saída de colaboradores dos contratos.</p>
        </div>
      </div>
      <GraficoLinha rotulos={meses.map(competencia)} series={series} formatar={(v) => `${inteiro(v)} vidas`}
        formatarEixo={(v) => compacto.format(v)} altura={220} inicioProjecao={inicioProjecao} />
    </div>
  );
}

function TabelaReceita({ d }: { d: DadosDashboard }) {
  return (
    <div className="tabela-rolagem">
      <table className="tabela compacta">
        <thead>
          <tr><th>Competência</th><th className="num">Recebido (bruto)</th><th className="num">Estornos</th>
            <th className="num">Receita líquida</th><th className="num">Esperado</th><th className="num">Vidas</th></tr>
        </thead>
        <tbody>
          {[...d.serie].reverse().map((s) => (
            <tr key={s.competencia}>
              <td>{competencia(s.competencia)}{s.parcial && <span className="mudo pequeno"> (em andamento)</span>}</td>
              <td className="num">{moeda(s.bruta)}</td>
              <td className="num">{s.estornos ? moeda(s.estornos) : "—"}</td>
              <td className="num forte">{moeda(s.receita)}</td>
              <td className="num">{moeda(s.esperado)}</td>
              <td className="num">{inteiro(s.vidas)}</td>
            </tr>
          ))}
          {d.projecao.meses.map((p) => (
            <tr key={`p-${p.competencia}`} className="linha-projecao">
              <td>{competencia(p.competencia)} <span className="mudo pequeno">(projeção)</span></td>
              <td className="num">—</td><td className="num">—</td>
              <td className="num forte">{moeda(p.receita)}
                <div className="mudo pequeno">{moeda(p.receita_min)} – {moeda(p.receita_max)}</div></td>
              <td className="num">—</td>
              <td className="num">{inteiro(p.vidas)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
