import { useEffect, useMemo, useRef, useState } from "react";

export interface Serie {
  id: string;
  nome: string;
  cor: string;
  valores: (number | null)[];
  tracejado?: boolean;
  /** faixa de incerteza [mín, máx] por ponto, desenhada como área clara */
  faixa?: ([number, number] | null)[];
}

interface Props {
  rotulos: string[];          // um por posição no eixo X
  series: Serie[];
  formatar: (v: number) => string;
  formatarEixo?: (v: number) => string;
  altura?: number;
  /** índice a partir do qual o fundo indica projeção */
  inicioProjecao?: number | null;
}

const MARGEM = { topo: 12, direita: 16, base: 28, esquerda: 64 };

function passoBonito(max: number, alvoLinhas = 4) {
  if (max <= 0) return 1;
  const bruto = max / alvoLinhas;
  const mag = 10 ** Math.floor(Math.log10(bruto));
  const n = bruto / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
}

export default function GraficoLinha({ rotulos, series, formatar, formatarEixo = formatar, altura = 280, inicioProjecao }: Props) {
  const caixa = useRef<HTMLDivElement>(null);
  const [largura, setLargura] = useState(720);
  const [foco, setFoco] = useState<number | null>(null);

  useEffect(() => {
    if (!caixa.current) return;
    const obs = new ResizeObserver(([e]) => setLargura(Math.max(320, e.contentRect.width)));
    obs.observe(caixa.current);
    return () => obs.disconnect();
  }, []);

  const n = rotulos.length;
  const w = largura - MARGEM.esquerda - MARGEM.direita;
  const h = altura - MARGEM.topo - MARGEM.base;

  const { passo, topo } = useMemo(() => {
    let max = 0;
    for (const s of series) {
      s.valores.forEach((v) => { if (v != null) max = Math.max(max, v); });
      s.faixa?.forEach((f) => { if (f) max = Math.max(max, f[1]); });
    }
    const p = passoBonito(max);
    return { passo: p, topo: Math.max(p, Math.ceil(max / p) * p) };
  }, [series]);

  const x = (i: number) => MARGEM.esquerda + (n <= 1 ? w / 2 : (i * w) / (n - 1));
  const y = (v: number) => MARGEM.topo + h - (v / topo) * h;

  const caminho = (valores: (number | null)[]) => {
    let d = "";
    let aberto = false;
    valores.forEach((v, i) => {
      if (v == null) { aberto = false; return; }
      d += `${aberto ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      aberto = true;
    });
    return d;
  };

  const area = (faixa: ([number, number] | null)[]) => {
    const pts = faixa.map((f, i) => (f ? { i, f } : null)).filter(Boolean) as { i: number; f: [number, number] }[];
    if (pts.length < 2) return "";
    const cima = pts.map((p) => `${x(p.i).toFixed(1)},${y(p.f[1]).toFixed(1)}`).join("L");
    const baixo = [...pts].reverse().map((p) => `${x(p.i).toFixed(1)},${y(p.f[0]).toFixed(1)}`).join("L");
    return `M${cima}L${baixo}Z`;
  };

  const linhasGrade: number[] = [];
  for (let v = 0; v <= topo + 1e-9; v += passo) linhasGrade.push(v);

  // Rótulos do eixo X sem colisão: um a cada k meses
  const k = Math.max(1, Math.ceil(n / Math.max(1, Math.floor(w / 64))));

  const aoMover = (e: React.PointerEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - r.left;
    const i = n <= 1 ? 0 : Math.round((px / r.width) * (n - 1));
    setFoco(Math.max(0, Math.min(n - 1, i)));
  };

  const ultimoValor = (s: Serie) => {
    for (let i = s.valores.length - 1; i >= 0; i--) if (s.valores[i] != null) return i;
    return -1;
  };

  return (
    <div className="grafico" ref={caixa}>
      <div className="legenda">
        {series.map((s) => (
          <span key={s.id}>
            <svg width="22" height="10" aria-hidden="true">
              <line x1="1" y1="5" x2="21" y2="5" stroke={s.cor} strokeWidth="2" strokeLinecap="round"
                strokeDasharray={s.tracejado ? "4 4" : undefined} />
            </svg>
            {s.nome}
          </span>
        ))}
      </div>
      <svg width={largura} height={altura} role="img" aria-label={series.map((s) => s.nome).join(", ")}>
        {inicioProjecao != null && inicioProjecao < n && (
          <rect x={x(Math.max(0, inicioProjecao - 0.5))} y={MARGEM.topo}
            width={x(n - 1) - x(Math.max(0, inicioProjecao - 0.5)) + MARGEM.direita / 2} height={h}
            className="fundo-projecao" />
        )}
        {linhasGrade.map((v) => (
          <g key={v}>
            <line x1={MARGEM.esquerda} x2={MARGEM.esquerda + w} y1={y(v)} y2={y(v)} className="grade" />
            <text x={MARGEM.esquerda - 8} y={y(v)} className="eixo" textAnchor="end" dominantBaseline="middle">
              {formatarEixo(v)}
            </text>
          </g>
        ))}
        {rotulos.map((r, i) => (i % k === 0 || i === n - 1) && (i === n - 1 || n - 1 - i >= k / 2) ? (
          <text key={r} x={x(i)} y={altura - 8} className="eixo"
            textAnchor={i === n - 1 ? "end" : i === 0 ? "start" : "middle"}>{r}</text>
        ) : null)}

        {series.map((s) => s.faixa && <path key={`f-${s.id}`} d={area(s.faixa)} fill={s.cor} opacity={0.12} />)}
        {series.map((s) => (
          <path key={s.id} d={caminho(s.valores)} fill="none" stroke={s.cor} strokeWidth={2}
            strokeLinejoin="round" strokeLinecap="round" strokeDasharray={s.tracejado ? "5 5" : undefined} />
        ))}
        {series.map((s) => {
          const i = ultimoValor(s);
          return i >= 0 ? <circle key={`p-${s.id}`} cx={x(i)} cy={y(s.valores[i]!)} r={4} fill={s.cor}
            stroke="var(--superficie)" strokeWidth={2} /> : null;
        })}

        {foco != null && (
          <g>
            <line x1={x(foco)} x2={x(foco)} y1={MARGEM.topo} y2={MARGEM.topo + h} className="mira" />
            {series.map((s) => s.valores[foco] != null && (
              <circle key={`m-${s.id}`} cx={x(foco)} cy={y(s.valores[foco]!)} r={4} fill={s.cor}
                stroke="var(--superficie)" strokeWidth={2} />
            ))}
          </g>
        )}
        <rect x={MARGEM.esquerda - 10} y={0} width={w + 20} height={altura} fill="transparent"
          onPointerMove={aoMover} onPointerLeave={() => setFoco(null)} />
      </svg>

      {foco != null && (
        <div className="tooltip" style={{
          left: Math.min(x(foco) + 12, largura - 200),
          top: MARGEM.topo,
        }}>
          <div className="tooltip-titulo">{rotulos[foco]}</div>
          {series.filter((s) => s.valores[foco] != null).map((s) => (
            <div key={s.id} className="tooltip-linha">
              <svg width="14" height="8" aria-hidden="true">
                <line x1="1" y1="4" x2="13" y2="4" stroke={s.cor} strokeWidth="2"
                  strokeDasharray={s.tracejado ? "3 3" : undefined} />
              </svg>
              <b>{formatar(s.valores[foco]!)}</b>
              <span>{s.nome}</span>
            </div>
          ))}
          {series.map((s) => s.faixa?.[foco] && (
            <div key={`fx-${s.id}`} className="tooltip-nota">
              faixa {formatar(s.faixa[foco]![0])} – {formatar(s.faixa[foco]![1])}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
