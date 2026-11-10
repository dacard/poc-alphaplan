import { useEffect, useMemo, useRef, useState } from "react";

interface Opcao { id: number; nome: string }

/** Seleção múltipla de clientes; null = todos. */
export default function FiltroClientes({ opcoes, selecionados, aoMudar }: {
  opcoes: Opcao[];
  selecionados: number[] | null;
  aoMudar: (ids: number[] | null) => void;
}) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");
  const raiz = useRef<HTMLDivElement>(null);
  const marcados = new Set(selecionados ?? opcoes.map((o) => o.id));

  useEffect(() => {
    const fora = (e: MouseEvent) => raiz.current && !raiz.current.contains(e.target as Node) && setAberto(false);
    document.addEventListener("mousedown", fora);
    return () => document.removeEventListener("mousedown", fora);
  }, []);

  const lista = useMemo(
    () => opcoes.filter((o) => o.nome.toLowerCase().includes(busca.toLowerCase())),
    [opcoes, busca]);

  const definir = (ids: Set<number>) => aoMudar(ids.size === opcoes.length ? null : [...ids]);
  const alternar = (id: number) => {
    const novo = new Set(marcados);
    novo.has(id) ? novo.delete(id) : novo.add(id);
    definir(novo);
  };

  const rotulo = selecionados == null ? `Todos os clientes (${opcoes.length})`
    : selecionados.length === 0 ? "Nenhum cliente"
    : selecionados.length === 1 ? opcoes.find((o) => o.id === selecionados[0])?.nome ?? "1 cliente"
    : `${selecionados.length} de ${opcoes.length} clientes`;

  return (
    <div className="filtro-clientes" ref={raiz}>
      <button className="secundario seletor" onClick={() => setAberto(!aberto)} aria-expanded={aberto}>
        <span className="mudo">Cliente:</span> {rotulo} <span className="seta-baixo">▾</span>
      </button>
      {aberto && (
        <div className="filtro-painel">
          <input autoFocus className="busca pequena" placeholder="Buscar cliente…" value={busca}
            onChange={(e) => setBusca(e.target.value)} />
          <div className="filtro-acoes">
            <button className="link" onClick={() => aoMudar(null)}>Selecionar todos</button>
            <button className="link" onClick={() => aoMudar([])}>Limpar</button>
            {busca && <button className="link" onClick={() => definir(new Set(lista.map((o) => o.id)))}>Só os encontrados</button>}
          </div>
          <div className="filtro-lista">
            {lista.map((o) => (
              <label key={o.id} className="checkbox">
                <input type="checkbox" checked={marcados.has(o.id)} onChange={() => alternar(o.id)} />
                {o.nome}
              </label>
            ))}
            {!lista.length && <div className="mudo pequeno">Nenhum cliente encontrado.</div>}
          </div>
        </div>
      )}
    </div>
  );
}
