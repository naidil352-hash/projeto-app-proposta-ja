import React, { createContext, useContext, useEffect, useState } from "react";
import { api, saveToken, clearToken, loadToken, formatApiError } from "./api";

type User = { id: string; email: string; name: string };

type AuthCtx = {
  user: User | null | undefined; // undefined=loading
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
        setUser({ id: data.id, email: data.email, name: data.name });
      } catch {
        await clearToken();
        setUser(null);
      }
    })();
  }, []);

  const login = async (email: string, password: string) => {
    try {
      const { data } = await api.post("/auth/login", { email, password });
      await saveToken(data.token);
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
      await saveToken(data.token);
      setUser(data.user);
    } catch (e) {
      throw new Error(formatApiError(e));
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
