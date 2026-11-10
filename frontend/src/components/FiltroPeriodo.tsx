import { useEffect, useRef, useState } from "react";
import { competencia } from "../formato";

export interface Periodo { inicio: string | null; fim: string | null }

const mesAtual = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};
/** Soma n meses a "AAAA-MM". */
const somar = (c: string, n: number) => {
  const [a, m] = c.split("-").map(Number);
  const t = a * 12 + (m - 1) + n;
  return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, "0")}`;
};

/** Atalhos: terminam no mês atual (fim aberto) para manter a projeção, salvo o ano anterior. */
function atalhos(): { rotulo: string; p: Periodo }[] {
  const hoje = mesAtual();
  const ano = Number(hoje.slice(0, 4));
  return [
    { rotulo: "Todo o período", p: { inicio: null, fim: null } },
    { rotulo: "Últimos 3 meses", p: { inicio: somar(hoje, -3), fim: null } },
    { rotulo: "Últimos 6 meses", p: { inicio: somar(hoje, -6), fim: null } },
    { rotulo: "Últimos 12 meses", p: { inicio: somar(hoje, -12), fim: null } },
    { rotulo: `Ano atual (${ano})`, p: { inicio: `${ano}-01`, fim: null } },
    { rotulo: `Ano anterior (${ano - 1})`, p: { inicio: `${ano - 1}-01`, fim: `${ano - 1}-12` } },
  ];
}

const igual = (a: Periodo, b: Periodo) => a.inicio === b.inicio && a.fim === b.fim;

export function rotuloPeriodo(p: Periodo) {
  const atalho = atalhos().find((x) => igual(x.p, p));
  if (atalho) return atalho.rotulo;
  if (p.inicio && p.fim) return p.inicio === p.fim ? competencia(p.inicio) : `${competencia(p.inicio)} a ${competencia(p.fim)}`;
  if (p.inicio) return `A partir de ${competencia(p.inicio)}`;
  return `Até ${competencia(p.fim!)}`;
}

/** Período por competência (mês). inicio/fim null = sem limite. */
export default function FiltroPeriodo({ valor, aoMudar, disponivel }: {
  valor: Periodo;
  aoMudar: (p: Periodo) => void;
  disponivel?: [string, string] | null;
}) {
  const [aberto, setAberto] = useState(false);
  const [rascunho, setRascunho] = useState<Periodo>(valor);
  const raiz = useRef<HTMLDivElement>(null);

  useEffect(() => { if (aberto) setRascunho(valor); }, [aberto]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const fora = (e: MouseEvent) => raiz.current && !raiz.current.contains(e.target as Node) && setAberto(false);
    document.addEventListener("mousedown", fora);
    return () => document.removeEventListener("mousedown", fora);
  }, []);

  const escolher = (p: Periodo) => { aoMudar(p); setAberto(false); };
  const invertido = !!(rascunho.inicio && rascunho.fim && rascunho.inicio > rascunho.fim);
  const [min, max] = disponivel ?? [undefined, undefined];

  return (
    <div className="filtro-clientes" ref={raiz}>
      <button className="secundario seletor" onClick={() => setAberto(!aberto)} aria-expanded={aberto}>
        <span className="mudo">Período:</span> {rotuloPeriodo(valor)} <span className="seta-baixo">▾</span>
      </button>
      {aberto && (
        <div className="filtro-painel filtro-periodo">
          <div className="periodo-atalhos">
            {atalhos().map((a) => (
              <button key={a.rotulo} className={igual(a.p, valor) ? "ativo" : ""} onClick={() => escolher(a.p)}>{a.rotulo}</button>
            ))}
          </div>
          <div className="periodo-personalizado">
            <span className="mudo pequeno">Personalizado (competência)</span>
            <div className="periodo-campos">
              <label>De<input type="month" value={rascunho.inicio ?? ""} min={min} max={max}
                onChange={(e) => setRascunho({ ...rascunho, inicio: e.target.value || null })} /></label>
              <label>Até<input type="month" value={rascunho.fim ?? ""} min={min} max={max}
                onChange={(e) => setRascunho({ ...rascunho, fim: e.target.value || null })} /></label>
            </div>
            {invertido && <div className="mudo pequeno erro-texto">O início é depois do fim.</div>}
            <button disabled={invertido} onClick={() => escolher(rascunho)}>Aplicar</button>
          </div>
        </div>
      )}
    </div>
  );
}
