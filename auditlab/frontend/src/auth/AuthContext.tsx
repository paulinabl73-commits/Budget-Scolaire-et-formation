import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, post, tokenStore, UNAUTHORIZED_EVENT } from "../api/client";
import type { LoginResult, Me } from "../api/types";

interface AuthState {
  user: Me | null;
  loading: boolean;
  sessionExpired: boolean;
  login: (email: string, password: string, totpCode?: string) => Promise<LoginResult>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);

  const refresh = useCallback(async () => {
    if (!tokenStore.get()) {
      setUser(null);
      return;
    }
    try {
      setUser(await api<Me>("/auth/me"));
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    void refresh().finally(() => setLoading(false));
    const onUnauthorized = () => {
      setUser(null);
      setSessionExpired(true);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string, totpCode?: string) => {
      const result = await post<LoginResult>("/auth/login", {
        email,
        password,
        totp_code: totpCode || undefined,
      });
      tokenStore.set(result.token);
      setSessionExpired(false);
      await refresh();
      return result;
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    try {
      await post("/auth/logout");
    } finally {
      tokenStore.clear();
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, sessionExpired, login, logout, refresh }),
    [user, loading, sessionExpired, login, logout, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé dans AuthProvider");
  return ctx;
}
