import { ReactNode, useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { classeImpacto, moedaSinal } from "../formato";

/** Carrega dados da API e expõe { dados, erro, carregando, recarregar }. */
export function useApi<T>(caminho: string | null) {
  const [dados, setDados] = useState<T | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  const recarregar = useCallback(() => {
    if (!caminho) return;
    setCarregando(true);
    api<T>(caminho)
      .then((d) => { setDados(d); setErro(null); })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, [caminho]);

  useEffect(recarregar, [recarregar]);
  return { dados, erro, carregando, recarregar };
}

export function Carregando({ erro }: { erro?: string | null }) {
  if (erro) return <div className="aviso erro">{erro}</div>;
  return <div className="carregando">Carregando…</div>;
}

export function Modal({ titulo, aoFechar, children, largo }: {
  titulo: string; aoFechar: () => void; children: ReactNode; largo?: boolean;
}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && aoFechar();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [aoFechar]);
  return (
    <div className="modal-fundo" onMouseDown={aoFechar}>
      <div className={`modal ${largo ? "largo" : ""}`} onMouseDown={(e) => e.stopPropagation()}>
        <header>
          <h2>{titulo}</h2>
          <button className="icone" onClick={aoFechar} aria-label="Fechar">×</button>
        </header>
        {children}
      </div>
    </div>
  );
}

export function Campo({ rotulo, children, dica }: { rotulo: string; children: ReactNode; dica?: string }) {
  return (
    <label className="campo">
      <span>{rotulo}</span>
      {children}
      {dica && <small>{dica}</small>}
    </label>
  );
}

export function Impacto({ valor }: { valor: number }) {
  return <span className={`impacto ${classeImpacto(valor)}`}>{moedaSinal(valor)}</span>;
}

export function Status({ status }: { status: "ok" | "divergente" | string }) {
  return <span className={`selo ${status === "ok" ? "ok" : "alerta"}`}>{status === "ok" ? "Sem divergência" : "Divergente"}</span>;
}

export function Cabecalho({ titulo, subtitulo, migalhas, acoes }: {
  titulo: string; subtitulo?: ReactNode; migalhas?: ReactNode; acoes?: ReactNode;
}) {
  return (
    <div className="cabecalho">
      {migalhas && <div className="migalhas">{migalhas}</div>}
      <div className="cabecalho-linha">
        <div>
          <h1>{titulo}</h1>
          {subtitulo && <p className="subtitulo">{subtitulo}</p>}
        </div>
        {acoes && <div className="acoes">{acoes}</div>}
      </div>
    </div>
  );
}

/** Rodapé padrão de formulário com mensagem de erro. */
export function RodapeForm({ erro, aoCancelar, salvando, rotulo = "Salvar" }: {
  erro?: string | null; aoCancelar: () => void; salvando?: boolean; rotulo?: string;
}) {
  return (
    <>
      {erro && <div className="aviso erro">{erro}</div>}
      <footer>
        <button type="button" className="secundario" onClick={aoCancelar}>Cancelar</button>
        <button type="submit" disabled={salvando}>{salvando ? "Salvando…" : rotulo}</button>
      </footer>
    </>
  );
}
