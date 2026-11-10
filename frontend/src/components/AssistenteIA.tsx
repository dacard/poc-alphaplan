import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Mensagem {
  papel: "usuario" | "assistente" | "erro";
  texto: string;
  consultas?: string[];
}

const SUGESTOES = [
  "Quais contratos apresentaram redução no último mês?",
  "Qual o contrato mais lucrativo?",
  "Quais empresas estão com resultado negativo?",
  "Qual o último relatório processado da Quali?",
];

const ROTULO_CONSULTA: Record<string, string> = {
  buscar_clientes: "clientes",
  listar_contratos: "contratos",
  ranking: "ranking",
  movimentacao_colaboradores: "movimentação de colaboradores",
  conciliacao_contrato: "conciliação",
  ultimos_relatorios: "relatórios",
  serie_mensal: "receita mês a mês",
  resumo_geral: "indicadores gerais",
};

const CHAVE_ABERTO = "assistente-aberto";
const lerAberto = () => { try { return localStorage.getItem(CHAVE_ABERTO) === "1"; } catch { return false; } };
const gravarAberto = (v: boolean) => { try { localStorage.setItem(CHAVE_ABERTO, v ? "1" : "0"); } catch { /* sem storage */ } };

/** Ícone de IA: três estrelas de quatro pontas. */
export function IconeEstrelas({ tamanho = 20 }: { tamanho?: number }) {
  return (
    <svg width={tamanho} height={tamanho} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M10 3.5c.4 3.6 2.4 5.6 6 6-3.6.4-5.6 2.4-6 6-.4-3.6-2.4-5.6-6-6 3.6-.4 5.6-2.4 6-6Z" />
      <path d="M18 2c.2 1.6 1 2.4 2.6 2.6-1.6.2-2.4 1-2.6 2.6-.2-1.6-1-2.4-2.6-2.6C17 4.4 17.8 3.6 18 2Z" />
      <path d="M17.5 14.5c.25 2 1.25 3 3.25 3.25-2 .25-3 1.25-3.25 3.25-.25-2-1.25-3-3.25-3.25 2-.25 3-1.25 3.25-3.25Z" />
    </svg>
  );
}

export default function AssistenteIA() {
  const [aberto, setAberto] = useState(lerAberto);
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [texto, setTexto] = useState("");
  const [aguardando, setAguardando] = useState(false);
  const [conversaId, setConversaId] = useState<string | null>(null);
  const fim = useRef<HTMLDivElement>(null);
  const entrada = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { gravarAberto(aberto); if (aberto) entrada.current?.focus(); }, [aberto]);
  useEffect(() => { fim.current?.scrollIntoView({ behavior: "smooth" }); }, [mensagens, aguardando]);

  const enviar = async (pergunta: string) => {
    const limpa = pergunta.trim();
    if (!limpa || aguardando) return;
    setMensagens((m) => [...m, { papel: "usuario", texto: limpa }]);
    setTexto("");
    setAguardando(true);
    try {
      const resp = await fetch("/api/assistente", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mensagem: limpa, conversa_id: conversaId }),
      });
      const dados = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(dados.detail || `Erro ${resp.status}`);
      setConversaId(dados.conversa_id);
      const consultas = [...new Set<string>(dados.ferramentas.map((f: { ferramenta: string }) => ROTULO_CONSULTA[f.ferramenta] || f.ferramenta))];
      setMensagens((m) => [...m, { papel: "assistente", texto: dados.resposta, consultas }]);
    } catch (e: any) {
      setMensagens((m) => [...m, { papel: "erro", texto: e.message || "Não foi possível falar com o assistente." }]);
    } finally {
      setAguardando(false);
      entrada.current?.focus();
    }
  };

  const novaConversa = () => {
    if (conversaId) fetch(`/api/assistente/${conversaId}`, { method: "DELETE" }).catch(() => {});
    setConversaId(null);
    setMensagens([]);
    entrada.current?.focus();
  };

  const aoEnviar = (e: FormEvent) => { e.preventDefault(); enviar(texto); };
  const aoTeclar = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(texto); }
  };

  if (!aberto) {
    return (
      <button className="ia-botao" onClick={() => setAberto(true)} aria-label="Abrir assistente de IA" title="Assistente de IA">
        <IconeEstrelas tamanho={24} />
      </button>
    );
  }

  return (
    <section className="ia-painel" role="dialog" aria-label="Assistente de IA">
      <header className="ia-topo">
        <span className="ia-marca"><IconeEstrelas /> Assistente IA</span>
        <div className="ia-acoes">
          {!!mensagens.length && (
            <button className="ia-icone" onClick={novaConversa} title="Nova conversa" aria-label="Nova conversa">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <path d="M12 5v14M5 12h14" />
              </svg>
            </button>
          )}
          <button className="ia-icone" onClick={() => setAberto(false)} title="Recolher" aria-label="Recolher assistente">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
        </div>
      </header>

      <div className="ia-mensagens" aria-live="polite">
        {!mensagens.length && (
          <div className="ia-boas-vindas">
            <div className="ia-boas-icone"><IconeEstrelas tamanho={28} /></div>
            <p><b>Pergunte sobre clientes, contratos, comissões e relatórios.</b></p>
            <p className="mudo pequeno">As respostas vêm dos dados processados na POC.</p>
            <div className="ia-sugestoes">
              {SUGESTOES.map((s) => <button key={s} onClick={() => enviar(s)}>{s}</button>)}
            </div>
          </div>
        )}
        {mensagens.map((m, i) => (
          <div key={i} className={`ia-msg ia-${m.papel}`}>
            {m.papel === "assistente" ? (
              <>
                <div className="ia-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.texto}</ReactMarkdown></div>
                {!!m.consultas?.length && <div className="ia-consultas">Consultou: {m.consultas.join(", ")}</div>}
              </>
            ) : m.texto}
          </div>
        ))}
        {aguardando && (
          <div className="ia-msg ia-assistente ia-pensando"><span /><span /><span /> Consultando os dados…</div>
        )}
        <div ref={fim} />
      </div>

      <form className="ia-entrada" onSubmit={aoEnviar}>
        <textarea ref={entrada} rows={1} value={texto} placeholder="Faça uma pergunta…" maxLength={2000}
          onChange={(e) => setTexto(e.target.value)} onKeyDown={aoTeclar} aria-label="Pergunta para o assistente" />
        <button type="submit" disabled={!texto.trim() || aguardando} aria-label="Enviar">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        </button>
      </form>
    </section>
  );
}
