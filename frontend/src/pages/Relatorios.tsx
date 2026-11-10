import { DragEvent, FormEvent, useEffect, useRef, useState } from "react";
import { api, enviar, Relatorio } from "../api";
import { Cabecalho, Carregando, Modal, useApi } from "../components/ui";
import { data } from "../formato";

interface Coleta {
  situacao: "executando" | "ok" | "erro";
  inicio: string;
  fim: string | null;
  mensagem: string;
}
interface Fonte {
  codigo: string;
  nome: string;
  relatorios: number;
  ultimo_relatorio: string | null;
  ultima_importacao: string | null;
  tem_robo: boolean;
  aceita: string | null;
  instrucoes: string | null;
  coleta: Coleta | null;
}

const hora = (iso: string | null) => (iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—");

export default function Relatorios() {
  const fontes = useApi<Fonte[]>("/fontes");
  const [filtro, setFiltro] = useState("");
  const relatorios = useApi<Relatorio[]>(`/relatorios${filtro ? `?fonte=${filtro}` : ""}`);
  const [selecionadas, setSelecionadas] = useState<Set<string> | null>(null); // null = todas
  const [upload, setUpload] = useState<Fonte | null>(null);
  const [mensagem, setMensagem] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);
  const [importando, setImportando] = useState(false);
  const executandoAntes = useRef(false);

  const lista = fontes.dados || [];
  const marcadas = selecionadas ?? new Set(lista.map((f) => f.codigo));
  const executando = lista.some((f) => f.coleta?.situacao === "executando");

  // Acompanha as coletas em andamento; ao terminar, atualiza a lista de relatórios
  useEffect(() => {
    if (executando) {
      executandoAntes.current = true;
      const t = setTimeout(fontes.recarregar, 3000);
      return () => clearTimeout(t);
    }
    if (executandoAntes.current) {
      executandoAntes.current = false;
      relatorios.recarregar();
    }
  }, [fontes.dados]); // eslint-disable-line react-hooks/exhaustive-deps

  const alternar = (codigo: string) => {
    const novo = new Set(marcadas);
    novo.has(codigo) ? novo.delete(codigo) : novo.add(codigo);
    setSelecionadas(novo.size === lista.length ? null : novo);
  };
  const todasMarcadas = marcadas.size === lista.length;

  const coletar = async (codigos: string[]) => {
    setMensagem(null);
    try {
      await Promise.all(codigos.map((c) => enviar(`/coletar/${c}`, "POST")));
      fontes.recarregar();
    } catch (e: any) {
      setMensagem({ tipo: "erro", texto: e.message });
    }
  };

  const importarBaixados = async () => {
    setImportando(true);
    setMensagem(null);
    try {
      const r = await api<Record<string, { importados: number }>>("/importar", { method: "POST" });
      const total = Object.values(r).reduce((s, v) => s + v.importados, 0);
      setMensagem({ tipo: "ok", texto: total ? `${total} relatórios novos importados.` : "Nenhum arquivo novo em dados/brutos/." });
      fontes.recarregar();
      relatorios.recarregar();
    } catch (e: any) {
      setMensagem({ tipo: "erro", texto: e.message });
    } finally {
      setImportando(false);
    }
  };

  const excluir = async (r: Relatorio) => {
    const manual = r.caminho.includes("/manual-");
    const aviso = manual
      ? "O arquivo enviado será apagado."
      : "O arquivo baixado pelo robô continua em disco e volta na próxima importação.";
    if (!confirm(`Excluir "${r.referencia}" (${r.fonte})? ${aviso}`)) return;
    await enviar(`/relatorios/${r.id}`, "DELETE");
    fontes.recarregar();
    relatorios.recarregar();
  };

  const coletaveis = lista.filter((f) => marcadas.has(f.codigo) && f.tem_robo && f.coleta?.situacao !== "executando");

  return (
    <>
      <Cabecalho titulo="Relatórios"
        subtitulo="Coleta nos portais pelo robô, ou upload manual quando o relatório chega por e-mail (portal indisponível)."
        acoes={<>
          <button className="secundario" disabled={importando} onClick={importarBaixados}>
            {importando ? "Importando…" : "Importar arquivos baixados"}</button>
          <button disabled={!coletaveis.length} onClick={() => coletar(coletaveis.map((f) => f.codigo))}>
            Coletar selecionadas ({coletaveis.length})</button>
        </>} />

      {mensagem && <div className={`aviso ${mensagem.tipo}`}>{mensagem.texto}</div>}

      {!fontes.dados ? <Carregando erro={fontes.erro} /> : (
        <div className="cartao sem-padding">
          <table className="tabela fontes-tabela">
            <thead>
              <tr>
                <th className="col-check">
                  <input type="checkbox" checked={todasMarcadas} aria-label="Selecionar todas"
                    onChange={() => setSelecionadas(todasMarcadas ? new Set() : null)} />
                </th>
                <th>Fonte</th><th className="num">Relatórios</th><th>Último relatório</th>
                <th>Última coleta</th><th />
              </tr>
            </thead>
            <tbody>
              {lista.map((f) => (
                <tr key={f.codigo} className={marcadas.has(f.codigo) ? "" : "inativo"}>
                  <td className="col-check">
                    <input type="checkbox" checked={marcadas.has(f.codigo)} onChange={() => alternar(f.codigo)}
                      aria-label={`Selecionar ${f.nome}`} />
                  </td>
                  <td><div className="forte">{f.nome}</div><div className="mudo pequeno mono">{f.codigo}</div></td>
                  <td className="num">{f.relatorios}</td>
                  <td>{data(f.ultimo_relatorio)}<div className="mudo pequeno">importado {hora(f.ultima_importacao)}</div></td>
                  <td className="col-coleta"><SituacaoColeta c={f.coleta} /></td>
                  <td className="acoes-linha">
                    <button className="secundario" disabled={!f.tem_robo || f.coleta?.situacao === "executando"}
                      onClick={() => coletar([f.codigo])}>Coletar</button>
                    <button className="secundario" disabled={!f.aceita} onClick={() => setUpload(f)}>Upload manual</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 className="secao topo-secao">Relatórios importados</h2>
      <div className="barra">
        <div className="segmentado">
          {[{ codigo: "", nome: "Todas" }, ...lista].map((f) => (
            <button key={f.codigo} className={filtro === f.codigo ? "ativo" : ""} onClick={() => setFiltro(f.codigo)}>{f.nome}</button>))}
        </div>
      </div>
      {!relatorios.dados ? <Carregando erro={relatorios.erro} /> : (
        <div className="cartao sem-padding">
          <table className="tabela">
            <thead><tr><th>Fonte</th><th>Data</th><th>Referência</th><th>Origem</th><th>Status</th>
              <th className="num">Linhas</th><th>Arquivo</th><th /></tr></thead>
            <tbody>
              {relatorios.dados.map((r) => (
                <tr key={r.id}>
                  <td><span className="selo neutro">{r.fonte}</span></td>
                  <td>{data(r.data_referencia)}</td>
                  <td>{r.referencia}</td>
                  <td>{r.caminho.includes("/manual-")
                    ? <span className="tag tag-manual">Upload manual</span>
                    : <span className="tag tag-portal">Portal</span>}</td>
                  <td>{r.status || "—"}</td>
                  <td className="num">{r.qtd_linhas}</td>
                  <td className="mudo pequeno mono">{r.caminho}</td>
                  <td className="acoes-linha"><button className="link perigo" onClick={() => excluir(r)}>Excluir</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {upload && <ModalUpload fonte={upload} aoFechar={() => setUpload(null)}
        aoConcluir={(texto) => { setUpload(null); setMensagem({ tipo: "ok", texto }); fontes.recarregar(); relatorios.recarregar(); }} />}
    </>
  );
}

function SituacaoColeta({ c }: { c: Coleta | null }) {
  if (!c) return <span className="mudo">—</span>;
  const rotulo = { executando: "Coletando…", ok: "Concluída", erro: "Falhou" }[c.situacao];
  const classe = { executando: "neutro", ok: "ok", erro: "erro" }[c.situacao];
  return (
    <>
      <span className={`selo ${classe}`}>{c.situacao === "executando" && <span className="girando" />}{rotulo}</span>
      <div className="mudo pequeno">{c.mensagem}</div>
      <div className="mudo pequeno">{c.situacao === "executando" ? `desde ${hora(c.inicio)}` : hora(c.fim)}</div>
    </>
  );
}

function ModalUpload({ fonte, aoFechar, aoConcluir }: {
  fonte: Fonte; aoFechar: () => void; aoConcluir: (mensagem: string) => void;
}) {
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [arrastando, setArrastando] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);

  const adicionar = (lista: FileList | null) => {
    // Copia já: a FileList do input é esvaziada logo depois (para permitir escolher o mesmo arquivo de novo)
    const novos = lista ? Array.from(lista) : [];
    if (novos.length) setArquivos((atual) => [...atual, ...novos]);
    setErro(null);
  };
  const soltar = (e: DragEvent) => {
    e.preventDefault();
    setArrastando(false);
    adicionar(e.dataTransfer.files);
  };

  const enviarArquivos = async (e: FormEvent) => {
    e.preventDefault();
    if (!arquivos.length) return setErro("Escolha ao menos um arquivo.");
    setEnviando(true);
    setErro(null);
    const corpo = new FormData();
    arquivos.forEach((a) => corpo.append("arquivos", a));
    try {
      const resp = await fetch(`/api/upload/${fonte.codigo}`, { method: "POST", body: corpo });
      const r = await resp.json();
      if (!resp.ok) throw new Error(r.detail || `Erro ${resp.status}`);
      aoConcluir(`${fonte.nome}: relatório importado por upload manual (${r.linhas} linhas).`);
    } catch (err: any) {
      setErro(err.message);
      setEnviando(false);
    }
  };

  return (
    <Modal titulo={`Upload manual — ${fonte.nome}`} aoFechar={aoFechar}>
      <form onSubmit={enviarArquivos}>
        <p className="nota">{fonte.instrucoes}</p>
        <div className={`area-upload ${arrastando ? "arrastando" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setArrastando(true); }}
          onDragLeave={() => setArrastando(false)} onDrop={soltar}
          onClick={() => entrada.current?.click()} role="button" tabIndex={0}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && entrada.current?.click()}>
          <b>Arraste os arquivos aqui</b>
          <span className="mudo pequeno">ou clique para escolher · aceitos: {fonte.aceita}</span>
          <input ref={entrada} type="file" multiple accept={fonte.aceita || undefined} hidden
            onChange={(e) => { adicionar(e.target.files); e.target.value = ""; }} />
        </div>
        {!!arquivos.length && (
          <ul className="lista-arquivos">
            {arquivos.map((a, i) => (
              <li key={i}>
                <span>{a.name}</span><span className="mudo pequeno">{(a.size / 1024).toFixed(0)} KB</span>
                <button type="button" className="icone" aria-label={`Remover ${a.name}`}
                  onClick={() => setArquivos(arquivos.filter((_, j) => j !== i))}>×</button>
              </li>
            ))}
          </ul>
        )}
        <p className="nota">O arquivo é conferido antes de entrar: formato, colunas e se o conteúdo já foi importado.
          Quando o portal voltar e o robô baixar o mesmo relatório, a versão do portal substitui esta.</p>
        {erro && <div className="aviso erro">{erro}</div>}
        <footer>
          <button type="button" className="secundario" onClick={aoFechar}>Cancelar</button>
          <button type="submit" disabled={enviando || !arquivos.length}>{enviando ? "Enviando…" : "Enviar e importar"}</button>
        </footer>
      </form>
    </Modal>
  );
}
