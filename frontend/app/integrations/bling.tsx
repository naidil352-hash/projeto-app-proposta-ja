import React, { useCallback, useState } from "react";
import { ActivityIndicator, Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";

import { api, formatApiError } from "../../src/api";
import { theme } from "../../src/theme";

type ConnectionStatus = { configured: boolean; connected: boolean; connected_at?: string | null };

export default function BlingIntegrationScreen() {
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true); setError(null);
      const response = await api.get("/integrations/bling/status");
      setStatus(response.data);
    } catch (requestError) { setError(formatApiError(requestError)); }
    finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const connect = async () => {
    try {
      setConnecting(true); setError(null);
      const response = await api.post("/integrations/bling/connect");
      await Linking.openURL(response.data.authorization_url);
    } catch (requestError) { setError(formatApiError(requestError)); }
    finally { setConnecting(false); }
  };

  return <SafeAreaView style={styles.root} edges={["top"]}><View style={styles.content}>
    <Text style={styles.eyebrow}>INTEGRAÇÕES</Text><Text style={styles.title}>Bling</Text>
    <Text style={styles.subtitle}>Conecte sua conta para preparar a importação de dados. Nenhum orçamento será importado sem revisão humana.</Text>
    {loading ? <ActivityIndicator color={theme.colors.primary} /> : <View style={styles.card}>
      <Text style={styles.status}>{status?.connected ? "CONECTADO" : status?.configured ? "PRONTO PARA CONECTAR" : "CONFIGURAÇÃO PENDENTE"}</Text>
      {status?.connected && <Text style={styles.muted}>Conta autorizada em {new Date(status.connected_at || "").toLocaleString("pt-BR")}</Text>}
      {!status?.configured && <Text style={styles.error}>As variáveis seguras do Bling ainda não estão disponíveis no backend.</Text>}
      {!status?.connected && <Pressable style={[styles.button, (!status?.configured || connecting) && styles.disabled]} disabled={!status?.configured || connecting} onPress={connect}>{connecting ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Conectar Bling</Text>}</Pressable>}
    </View>}
    {error && <Text style={styles.error}>{error}</Text>}
  </View></SafeAreaView>;
}

const styles = StyleSheet.create({ root: { flex: 1, backgroundColor: theme.colors.bg }, content: { width: "100%", maxWidth: 720, alignSelf: "center", padding: 24, gap: 14 }, eyebrow: { color: theme.colors.primary, fontWeight: "800", fontSize: 12, letterSpacing: 1 }, title: { color: theme.colors.text, fontSize: 30, fontWeight: "800" }, subtitle: { color: theme.colors.textMuted, lineHeight: 21 }, card: { backgroundColor: "#fff", borderRadius: 12, borderWidth: 1, borderColor: theme.colors.border, padding: 20, gap: 14 }, status: { color: theme.colors.primary, fontWeight: "900" }, muted: { color: theme.colors.textMuted }, button: { alignSelf: "flex-start", backgroundColor: theme.colors.primary, borderRadius: 8, paddingVertical: 12, paddingHorizontal: 16, minWidth: 155, alignItems: "center" }, buttonText: { color: "#fff", fontWeight: "800" }, disabled: { opacity: 0.45 }, error: { color: "#B42318", backgroundColor: "#FEE4E2", padding: 12, borderRadius: 8 } });
