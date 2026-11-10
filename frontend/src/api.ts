// Cliente HTTP da API e tipos compartilhados.

export async function api<T = any>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const resp = await fetch(`/api${caminho}`, {
    headers: { "Content-Type": "application/json" },
    ...opcoes,
  });
  const corpo = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(corpo.detail || `Erro ${resp.status}`);
  return corpo as T;
}

export const enviar = (caminho: string, metodo: "POST" | "PUT" | "DELETE", dados?: unknown) =>
  api(caminho, { method: metodo, body: dados === undefined ? undefined : JSON.stringify(dados) });

export interface Operadora { id?: number; nome: string; codigo_fonte?: string | null }
export interface Administradora { id?: number; nome: string; codigo_fonte?: string | null }
export interface Produto { id?: number; nome: string; operadora_id: number; tabela_faixas?: number[] | null }
export interface Cliente { id?: number; nome: string; cnpj?: string | null }

export interface Regra { parcela_de: number; parcela_ate: number | null; percentual: number }

export interface Contrato {
  id?: number;
  cliente_id: number;
  produto_id: number;
  administradora_id: number | null;
  identificador_relatorio: string;
  data_inicio: string;
  regras_comissao: Regra[];
  chave_conciliacao: "nome" | "cpf";
  tolerancia: number;
  observacoes?: string | null;
}

export interface ContratoResumo extends Contrato {
  id: number;
  cliente: string;
  produto: string;
  operadora: string;
  administradora: string | null;
  fonte: string | null;
  colaboradores_ativos: number;
  colaboradores_total: number;
  conciliacao?: {
    meses: number;
    meses_divergentes: number;
    esperado: number;
    processado: number;
    impacto: number;
    ultimo_mes: { competencia: string; status: string; impacto: number } | null;
  };
}

export interface Colaborador {
  id?: number;
  contrato_id: number;
  nome: string;
  cpf?: string | null;
  data_nascimento?: string | null;
  data_inclusao: string;
  data_exclusao?: string | null;
  valor_mensalidade: number;
  historico_mensalidade?: { a_partir: string; valor: number }[];
}

/** Mensalidade cadastrada válida no mês (AAAA-MM), considerando reajustes. */
export function valorVigente(c: Colaborador, mes: string): number {
  const vigentes = (c.historico_mensalidade || []).filter((h) => h.a_partir <= mes);
  return vigentes.length ? vigentes.sort((a, b) => a.a_partir.localeCompare(b.a_partir)).at(-1)!.valor : c.valor_mensalidade;
}

export interface Relatorio {
  id: number;
  fonte: string;
  caminho: string;
  referencia: string;
  data_referencia: string;
  status: string | null;
  qtd_linhas: number;
  importado_em: string;
}

export interface RelatorioContrato extends Relatorio {
  linhas_contrato: number;
  pessoas: number;
  comissao: number;
  competencias: string[];
}

export interface Linha {
  id: number;
  nome: string;
  cpf: string | null;
  competencia: string;
  parcela: number | null;
  percentual: number | null;
  valor_base: number;
  valor_comissao: number;
  valor_estorno: number;
}

export interface Divergencia {
  tipos: string[];
  nome: string;
  colaborador_id: number | null;
  confianca: string | null;
  esperado: { mensalidade: number; percentual: number | null; comissao: number; parcela: number; cpf: string | null } | null;
  processado: {
    mensalidade: number; percentuais: number[]; comissao: number; estorno: number;
    parcelas: number[]; linhas: number; cpf: string | null; relatorios: number[];
  } | null;
  impacto: number;
}

export interface Mes {
  competencia: string;
  status: "ok" | "divergente";
  esperado: { vidas: number; mensalidades: number; comissao: number };
  processado: { vidas: number; mensalidades: number; comissao: number; linhas: number };
  casados: number;
  impacto: number;
  contagem: Record<string, number>;
  divergencias: Divergencia[];
}

export interface Conciliacao {
  contrato_id: number;
  tipos: Record<string, string>;
  meses: Mes[];
  totais: { meses: number; meses_divergentes: number; esperado: number; processado: number; impacto: number };
}
