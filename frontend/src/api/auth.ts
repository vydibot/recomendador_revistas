import { api } from "./client";

export const login = (password: string) =>
  api<{ access_token: string; expires_in: number }>("/auth/login", {
    method: "POST",
    body: { password },
  });

export const checkSession = () => api<{ role: string }>("/auth/me");
