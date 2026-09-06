import React, { useCallback, useState } from "react";
import { ActivityIndicator, Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";

import { api, formatApiError } from "../../src/api";
import { theme } from "../../src/theme";

type ConnectionStatus = { configured: boolean; connected: boolean; connected_at?: string | null };
type CommercialProposal = { external_id: string; number: string; date?: string | null; total: number; client_name: string; status: string };

export default function BlingIntegrationScreen() {
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [proposals, setProposals] = useState<CommercialProposal[] | null>(null);
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

  const preview = async () => {
    try {
      setPreviewing(true); setError(null);
      const response = await api.get("/integrations/bling/commercial-proposals", { params: { limit: 25 } });
      setProposals(response.data.proposals || []);
    } catch (requestError) { setError(formatApiError(requestError)); }
    finally { setPreviewing(false); }
  };

  return <SafeAreaView style={styles.root} edges={["top"]}><View style={styles.content}>
    <Text style={styles.eyebrow}>INTEGRAÇÕES</Text><Text style={styles.title}>Bling</Text>
    <Text style={styles.subtitle}>Conecte sua conta para preparar a importação de dados. Nenhum orçamento será importado sem revisão humana.</Text>
    {loading ? <ActivityIndicator color={theme.colors.primary} /> : <View style={styles.card}>
      <Text style={styles.status}>{status?.connected ? "CONECTADO" : status?.configured ? "PRONTO PARA CONECTAR" : "CONFIGURAÇÃO PENDENTE"}</Text>
      {status?.connected && <Text style={styles.muted}>Conta autorizada em {new Date(status.connected_at || "").toLocaleString("pt-BR")}</Text>}
      {!status?.configured && <Text style={styles.error}>As variáveis seguras do Bling ainda não estão disponíveis no backend.</Text>}
      {!status?.connected && <Pressable style={[styles.button, (!status?.configured || connecting) && styles.disabled]} disabled={!status?.configured || connecting} onPress={connect}>{connecting ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Conectar Bling</Text>}</Pressable>}
      {status?.connected && <Pressable style={[styles.button, previewing && styles.disabled]} disabled={previewing} onPress={preview}>{previewing ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Ver prévia de propostas</Text>}</Pressable>}
    </View>}
    {proposals !== null && <View style={styles.preview}><Text style={styles.previewTitle}>Prévia do Bling</Text>{proposals.length === 0 ? <Text style={styles.muted}>Nenhuma proposta comercial foi encontrada.</Text> : proposals.map((proposal) => <View key={proposal.external_id} style={styles.proposal}><Text style={styles.proposalName}>{proposal.client_name}</Text><Text style={styles.muted}>Orçamento {proposal.number} · {proposal.date || "sem data"}</Text><Text style={styles.proposalTotal}>R$ {Number(proposal.total || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</Text></View>)}<Text style={styles.muted}>Esta é uma consulta de leitura. A importação será uma etapa posterior e confirmada.</Text></View>}
    {error && <Text style={styles.error}>{error}</Text>}
  </View></SafeAreaView>;
}

const styles = StyleSheet.create({ root: { flex: 1, backgroundColor: theme.colors.bg }, content: { width: "100%", maxWidth: 720, alignSelf: "center", padding: 24, gap: 14 }, eyebrow: { color: theme.colors.primary, fontWeight: "800", fontSize: 12, letterSpacing: 1 }, title: { color: theme.colors.text, fontSize: 30, fontWeight: "800" }, subtitle: { color: theme.colors.textMuted, lineHeight: 21 }, card: { backgroundColor: "#fff", borderRadius: 12, borderWidth: 1, borderColor: theme.colors.border, padding: 20, gap: 14 }, status: { color: theme.colors.primary, fontWeight: "900" }, muted: { color: theme.colors.textMuted }, button: { alignSelf: "flex-start", backgroundColor: theme.colors.primary, borderRadius: 8, paddingVertical: 12, paddingHorizontal: 16, minWidth: 155, alignItems: "center" }, buttonText: { color: "#fff", fontWeight: "800" }, disabled: { opacity: 0.45 }, error: { color: "#B42318", backgroundColor: "#FEE4E2", padding: 12, borderRadius: 8 }, preview: { backgroundColor: "#fff", borderRadius: 12, borderWidth: 1, borderColor: theme.colors.border, padding: 20, gap: 12 }, previewTitle: { color: theme.colors.text, fontSize: 18, fontWeight: "800" }, proposal: { borderTopWidth: 1, borderColor: theme.colors.border, paddingTop: 12, gap: 4 }, proposalName: { color: theme.colors.text, fontWeight: "800" }, proposalTotal: { color: theme.colors.text, fontWeight: "800", textAlign: "right" } });
