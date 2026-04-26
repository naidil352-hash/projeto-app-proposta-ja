import axios from "axios";
import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL as string;

export const api = axios.create({
  baseURL: `${BASE}/api`,
  timeout: 60000, // 60s — Render free tier may take up to 30s on cold start
});

const TOKEN_KEY = "propostaja_token";
const isWeb = Platform.OS === "web";

export async function saveToken(token: string) {
  if (isWeb) {
    if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
    return;
  }
  await SecureStore.setItemAsync(TOKEN_KEY, token);
}

export async function loadToken(): Promise<string | null> {
  if (isWeb) {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(TOKEN_KEY);
  }
  return await SecureStore.getItemAsync(TOKEN_KEY);
}

export async function clearToken() {
  if (isWeb) {
    if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
    return;
  }
  await SecureStore.deleteItemAsync(TOKEN_KEY);
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
  const d = err?.response?.data?.detail;
  if (!d) return err?.message || "Erro inesperado";
  if (typeof d === "string") return d;
  if (Array.isArray(d))
    return d.map((e) => (e?.msg ? e.msg : JSON.stringify(e))).join(" ");
  return JSON.stringify(d);
}
