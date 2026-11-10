const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
  "setembro", "outubro", "novembro", "dezembro"];

export const moeda = (v: number | null | undefined) => (v == null ? "—" : brl.format(v));

export const moedaSinal = (v: number) => (v > 0 ? "+" : "") + brl.format(v);

export const pct = (v: number | null | undefined) =>
  v == null ? "—" : `${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;

/** "2026-05" -> "mai/2026" */
export const competencia = (c: string) => {
  const [a, m] = c.split("-");
  return `${MESES[Number(m) - 1]}/${a}`;
};

/** "2026-05" -> "maio de 2026" */
export const competenciaLonga = (c: string) => {
  const [a, m] = c.split("-");
  const nome = MESES_LONGOS[Number(m) - 1];
  return `${nome[0].toUpperCase()}${nome.slice(1)} de ${a}`;
};

/** "2026-05-01" -> "01/05/2026" */
export const data = (d: string | null | undefined) => {
  if (!d) return "—";
  const [a, m, dia] = d.slice(0, 10).split("-");
  return `${dia}/${m}/${a}`;
};

export const classeImpacto = (v: number) => (v > 0.004 ? "positivo" : v < -0.004 ? "negativo" : "neutro");

export const plural = (n: number, um: string, varios: string) => `${n.toLocaleString("pt-BR")} ${n === 1 ? um : varios}`;
