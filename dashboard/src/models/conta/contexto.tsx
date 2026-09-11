/**
 * Estado de sessao (quem esta logado) - um `onAuthStateChanged` so, no topo
 * do app, distribuido por contexto. `carregando` existe porque o Firebase
 * leva um instante pra confirmar a sessao guardada (IndexedDB) na primeira
 * carga da pagina - sem isso, toda rota protegida piscaria a tela de login
 * antes de descobrir que a pessoa ja estava logada.
 */

import { onAuthStateChanged, type User } from "firebase/auth";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { auth } from "./cliente";

interface EstadoConta {
  usuario: User | null;
  carregando: boolean;
}

const ContextoConta = createContext<EstadoConta>({ usuario: null, carregando: true });

export function ProvedorConta({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<User | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    const cancelar = onAuthStateChanged(auth, (atual) => {
      setUsuario(atual);
      setCarregando(false);
    });
    return cancelar;
  }, []);

  return (
    <ContextoConta.Provider value={{ usuario, carregando }}>
      {children}
    </ContextoConta.Provider>
  );
}

export function useUsuario(): EstadoConta {
  return useContext(ContextoConta);
}
