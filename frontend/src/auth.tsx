import React, { createContext, useContext, useEffect, useState } from "react";
import { api, saveToken, clearToken, loadToken, formatApiError } from "./api";

type User = { id: string; email: string; name: string; role: string };

type AuthCtx = {
  user: User | null | undefined;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string, referralCode?: string) => Promise<void>;
  logout: () => Promise<void>;
};

const Ctx = createContext<AuthCtx>({} as any);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    (async () => {
      const token = await loadToken();
      if (!token) {
        setUser(null);
        return;
      }

      try {
        const { data } = await api.get("/auth/me");
        setUser({ id: data.id, email: data.email, name: data.name, role: data.role });
      } catch (e) {
        console.log("AUTH LOAD ERROR:", e);
        await clearToken();
        setUser(null);
      }
    })();
  }, []);

  const login = async (email: string, password: string) => {
    try {
      const res = await api.post("/auth/login", { email, password });

      if (!res?.data?.token) {
        throw new Error("Resposta inválida do servidor");
      }

      await saveToken(res.data.token);
      const meRes = await api.get("/auth/me");
      setUser({ id: meRes.data.id, email: meRes.data.email, name: meRes.data.name, role: meRes.data.role });

    } catch (e: any) {
      console.log("LOGIN ERROR:", e);
      throw new Error(formatApiError(e) || "Erro ao fazer login");
    }
  };

  const register = async (name: string, email: string, password: string, referralCode?: string) => {
    try {
      const payload: any = { name, email, password };

      if (referralCode && referralCode.trim()) {
        payload.referral_code = referralCode.trim().toUpperCase();
      }

      // 🔥 chamada protegida
      const res = await api.post("/auth/register", payload);

      console.log("REGISTER RESPONSE:", res?.data);

      if (!res || !res.data) {
        throw new Error("Sem resposta do servidor");
      }

      if (!res.data.token || !res.data.user) {
        throw new Error("Resposta inválida do servidor");
      }

      await saveToken(res.data.token);
      const meRes = await api.get("/auth/me");
      setUser({ id: meRes.data.id, email: meRes.data.email, name: meRes.data.name, role: meRes.data.role });

    } catch (e: any) {
      console.log("REGISTER ERROR:", e);

      // 🔥 evita crash
      const msg =
        e?.response?.data?.detail ||
        e?.message ||
        "Erro ao criar conta";

      throw new Error(msg);
    }
  };

  const logout = async () => {
    await clearToken();
    setUser(null);
  };

  return <Ctx.Provider value={{ user, login, register, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  return useContext(Ctx);
}
