import axios from "axios";
import { Platform } from "react-native";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "https://projeto-app-proposta-ja.onrender.com";

export const api = axios.create({
  baseURL: `${BASE}/api`,
  timeout: 60000,
});

const TOKEN_KEY = "propostaja_token";
const isWeb = Platform.OS === "web";

// Lazy-load SecureStore to avoid native init crashing on first boot
let SecureStoreMod: any = null;
function getSecureStore() {
  if (isWeb) return null;
  if (SecureStoreMod) return SecureStoreMod;
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    SecureStoreMod = require("expo-secure-store");
  } catch (e) {
    console.log("expo-secure-store not available:", e);
    SecureStoreMod = null;
  }
  return SecureStoreMod;
}

// In-memory fallback if SecureStore fails
let memoryToken: string | null = null;

export async function saveToken(token: string) {
  memoryToken = token;
  if (isWeb) {
    if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
    return;
  }
  const SS = getSecureStore();
  if (SS) {
    try {
      await SS.setItemAsync(TOKEN_KEY, token);
    } catch (e) {
      console.log("SecureStore.set failed:", e);
    }
  }
}

export async function loadToken(): Promise<string | null> {
  if (memoryToken) return memoryToken;
  if (isWeb) {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(TOKEN_KEY);
  }
  const SS = getSecureStore();
  if (SS) {
    try {
      const t = await SS.getItemAsync(TOKEN_KEY);
      if (t) memoryToken = t;
      return t;
    } catch (e) {
      console.log("SecureStore.get failed:", e);
      return null;
    }
  }
  return null;
}

export async function clearToken() {
  memoryToken = null;
  if (isWeb) {
    if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
    return;
  }
  const SS = getSecureStore();
  if (SS) {
    try {
      await SS.deleteItemAsync(TOKEN_KEY);
    } catch {}
  }
}

api.interceptors.request.use(async (config) => {
  const token = await loadToken();
  if (token) {
    config.headers = config.headers ?? {};
    (config.headers as any).Authorization = `Bearer ${token}`;
  }
  return config;
});

export function formatApiError(err: any): string {
  if (err?.code === "ECONNABORTED") return "Servidor demorou para responder. Tente novamente.";
  if (err?.message?.includes("Network Error")) return "Sem conexão com o servidor.";
  const d = err?.response?.data?.detail;
  if (!d) return err?.message || "Erro inesperado";
  if (typeof d === "string") return d;
  if (Array.isArray(d))
    return d.map((e) => (e?.msg ? e.msg : JSON.stringify(e))).join(" ");
  return JSON.stringify(d);
}
