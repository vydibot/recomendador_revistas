import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { checkSession, login as loginRequest } from "@/api/auth";
import { setUnauthorizedHandler, tokenStore } from "@/api/client";

interface AuthState {
  isAdmin: boolean;
  login: (password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAdmin, setIsAdmin] = useState<boolean>(() => tokenStore.get() !== null);
  const queryClient = useQueryClient();

  const logout = useCallback(() => {
    tokenStore.clear();
    setIsAdmin(false);
    queryClient.invalidateQueries({ queryKey: ["journals"] });
  }, [queryClient]);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    // Un token guardado puede haber expirado: se valida una vez al cargar.
    if (tokenStore.get()) checkSession().catch(() => undefined);
  }, [logout]);

  const login = useCallback(async (password: string) => {
    const { access_token } = await loginRequest(password);
    tokenStore.set(access_token);
    setIsAdmin(true);
  }, []);

  const value = useMemo(() => ({ isAdmin, login, logout }), [isAdmin, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return context;
}
