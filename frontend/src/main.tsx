import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, NavLink, Route, Routes } from "react-router-dom";
import Cliente from "./pages/Cliente";
import Clientes from "./pages/Clientes";
import Contrato from "./pages/Contrato";
import Dashboard from "./pages/Dashboard";
import { Empresas, Produtos } from "./pages/Cadastros";
import Relatorios from "./pages/Relatorios";
import "./styles.css";

const MENU = [
  { para: "/dashboard", rotulo: "Dashboard" },
  { para: "/clientes", rotulo: "Clientes" },
  { para: "/operadoras", rotulo: "Operadoras" },
  { para: "/administradoras", rotulo: "Administradoras" },
  { para: "/produtos", rotulo: "Produtos" },
  { para: "/relatorios", rotulo: "Relatórios" },
];

function App() {
  return (
    <div className="app">
      <aside className="lateral">
        <div className="marca">alphaplan<span>conciliação de comissões · POC</span></div>
        <nav>
          {MENU.map((m) => <NavLink key={m.para} to={m.para}>{m.rotulo}</NavLink>)}
        </nav>
      </aside>
      <main className="conteudo">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/clientes" element={<Clientes />} />
          <Route path="/clientes/:id" element={<Cliente />} />
          <Route path="/contratos/:id" element={<Contrato />} />
          <Route path="/operadoras" element={<Empresas key="op" tipo="operadoras" />} />
          <Route path="/administradoras" element={<Empresas key="adm" tipo="administradoras" />} />
          <Route path="/produtos" element={<Produtos />} />
          <Route path="/relatorios" element={<Relatorios />} />
        </Routes>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
