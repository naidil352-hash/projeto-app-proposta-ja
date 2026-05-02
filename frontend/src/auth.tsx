import React, { createContext, useContext, useEffect, useState } from "react";
import { api, saveToken, clearToken, loadToken, formatApiError } from "./api";

type User = { id: string; email: string; name: string };

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
    let cancelled = false;
    (async () => {
      let token: string | null = null;
      try {
        // Timeout hard após 4s para que o app NUNCA fique infinitamente na tela de loading
        token = await Promise.race<string | null>([
          loadToken(),
          new Promise<null>((resolve) => setTimeout(() => resolve(null), 4000)),
        ]);
      } catch (e) {
        console.log("loadToken failed:", e);
        token = null;
      }
      if (cancelled) return;
      if (!token) {
        setUser(null);
        return;
      }
      try {
        const { data } = await api.get("/auth/me", { timeout: 20000 });
        if (!cancelled) setUser({ id: data.id, email: data.email, name: data.name });
      } catch (e) {
        try {
          await clearToken();
        } catch {}
        if (!cancelled) setUser(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = async (email: string, password: string) => {
    try {
      const { data } = await api.post("/auth/login", { email, password });
      try {
        await saveToken(data.token);
      } catch (e) {
        console.log("saveToken failed:", e);
      }
      setUser(data.user);
    } catch (e) {
      throw new Error(formatApiError(e));
    }
  };

  const register = async (name: string, email: string, password: string, referralCode?: string) => {
    try {
      const payload: any = { name, email, password };
      if (referralCode && referralCode.trim()) payload.referral_code = referralCode.trim().toUpperCase();
      const { data } = await api.post("/auth/register", payload);
      try {
        await saveToken(data.token);
      } catch (e) {
        console.log("saveToken failed:", e);
      }
      setUser(data.user);
    } catch (e) {
      throw new Error(formatApiError(e));
    }
  };

  const logout = async () => {
    try {
      await clearToken();
    } catch {}
    setUser(null);
  };

  return <Ctx.Provider value={{ user, login, register, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  return useContext(Ctx);
}
