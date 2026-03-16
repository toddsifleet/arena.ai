import { createContext, useContext, type ParentComponent } from "solid-js";
import { createSignal } from "solid-js";

const CLIENT_ID_KEY = "minirtc_client_id";

function getStoredClientId(): string | null {
  try {
    return localStorage.getItem(CLIENT_ID_KEY);
  } catch {
    return null;
  }
}

function setStoredClientId(clientId: string): void {
  try {
    localStorage.setItem(CLIENT_ID_KEY, clientId);
  } catch {
    // ignore localStorage errors (e.g. private browsing)
  }
}

interface ClientContextValue {
  clientId: () => string | null;
  persistClientId: (id: string) => void;
}

const ClientContext = createContext<ClientContextValue>();

export const ClientProvider: ParentComponent = (props) => {
  const [clientId, setClientId] = createSignal<string | null>(getStoredClientId());

  const persistClientId = (id: string) => {
    setClientId(id);
    setStoredClientId(id);
  };

  return (
    <ClientContext.Provider value={{ clientId, persistClientId }}>
      {props.children}
    </ClientContext.Provider>
  );
};

export const useClient = () => {
  const ctx = useContext(ClientContext);
  if (!ctx) throw new Error("useClient must be used within <ClientProvider>");
  return ctx;
};
