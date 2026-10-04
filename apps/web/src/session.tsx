import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setToken, type User } from "./lib/api";
import { ensureIdentity, invalidateDevices, receiveEnvelope, syncPending, type Identity } from "./lib/messenger";
import { Realtime } from "./lib/realtime";

interface Session {
  user: User | null;
  token: string | null;
  identity: Identity | null;
  rt: Realtime | null;
  ready: boolean;
  signIn: (token: string, user: User) => void;
  signOut: () => void;
  setUser: (u: User) => void;
}

const Ctx = createContext<Session | null>(null);
const KEY = "hamsa.session";

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("SessionProvider missing");
  return s;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [token, setTok] = useState<string | null>(() => localStorage.getItem(KEY));
  const [user, setUser] = useState<User | null>(null);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [rt, setRt] = useState<Realtime | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let realtime: Realtime | null = null;
    setReady(false);
    setToken(token);
    if (!token) {
      setUser(null);
      setIdentity(null);
      setReady(true);
      return;
    }
    (async () => {
      try {
        const me = await api<User>("/me");
        const id = me.is_guest ? null : await ensureIdentity(me.id);
        if (cancelled) return;
        const proto = location.protocol === "https:" ? "wss" : "ws";
        const qs = new URLSearchParams({ token, ...(id ? { device_id: id.deviceId } : {}) });
        realtime = new Realtime(`${proto}://${location.host}/api/ws?${qs}`);
        realtime.on(async (ev) => {
          if (ev.type === "envelope" && id) await receiveEnvelope(id, ev.envelope as never).then((m) => {
            if (m) window.dispatchEvent(new CustomEvent("hamsa:local-message", { detail: m }));
          });
          if (ev.type === "devices_changed") invalidateDevices();
        });
        realtime.onOpen = () => {
          if (id) syncPending(id).then((ms) => ms.forEach((m) => window.dispatchEvent(new CustomEvent("hamsa:local-message", { detail: m }))));
        };
        realtime.start();
        setUser(me);
        setIdentity(id);
        setRt(realtime);
      } catch {
        localStorage.removeItem(KEY);
        setTok(null);
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
      realtime?.stop();
    };
  }, [token]);

  const signIn = useCallback((t: string, u: User) => {
    localStorage.setItem(KEY, t);
    setUser(u);
    setTok(t);
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem(KEY);
    setTok(null);
  }, []);

  const value = useMemo(() => ({ user, token, identity, rt, ready, signIn, signOut, setUser }), [user, token, identity, rt, ready, signIn, signOut]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
