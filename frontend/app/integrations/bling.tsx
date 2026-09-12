import React, { useCallback, useRef, useState } from "react";
import { ActivityIndicator, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";

import { api, formatApiError } from "../../src/api";
import { theme } from "../../src/theme";

type ConnectionStatus = { configured: boolean; connected: boolean; connected_at?: string | null };
type CommercialProposal = { external_id: string; number: string; date?: string | null; total: number; client_name: string; status: string };
type ProposalDetail = { external_id: string; number: string; client_name: string; document: string | null; total: number | null; items: { description: string; code: string | null; quantity: number | null; unit: string | null; unit_price: number | null; gross_total: number | null }[] };
type DetailState = { loading?: boolean; data?: ProposalDetail; error?: string };
const money = (value: number | null) => value === null ? "Não informado" : Number(value).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export default function BlingIntegrationScreen() {
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [proposals, setProposals] = useState<CommercialProposal[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [details, setDetails] = useState<Record<string, DetailState>>({});
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const busy = useRef(false);

  const load = useCallback(async () => {
    const current = ++generation.current;
    busy.current = false;
    setFetching(false); setPreviewing(false); setProposals(null); setSelected([]); setDetails({});
    try {
      setLoading(true); setError(null);
      const response = await api.get("/integrations/bling/status");
      if (current === generation.current) setStatus(response.data);
    } catch (requestError) { if (current === generation.current) setError(formatApiError(requestError)); }
    finally { if (current === generation.current) setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); return () => { generation.current += 1; }; }, [load]));

  const connect = async () => {
    try {
      setConnecting(true); setError(null);
      const response = await api.post("/integrations/bling/connect");
      await Linking.openURL(response.data.authorization_url);
    } catch (requestError) { setError(formatApiError(requestError)); }
    finally { setConnecting(false); }
  };

  const preview = async () => {
    if (busy.current) return;
    busy.current = true;
    const current = ++generation.current;
    try {
      setPreviewing(true); setError(null); setSelected([]); setDetails({}); setProposals(null);
      const response = await api.get("/integrations/bling/commercial-proposals", { params: { limit: 25 } });
      if (current === generation.current) setProposals(response.data.proposals || []);
    } catch (requestError) { if (current === generation.current) setError(formatApiError(requestError)); }
    finally { if (current === generation.current) { setPreviewing(false); busy.current = false; } }
  };

  const fetchSelected = async () => {
    if (busy.current || selected.length === 0) return;
    busy.current = true; setFetching(true);
    const current = generation.current;
    // Sequential reads avoid a burst of requests and concurrent token refreshes.
    try {
      for (const id of selected) {
        if (current !== generation.current) break;
        setDetails((previous) => ({ ...previous, [id]: { loading: true } }));
        try {
          const response = await api.get(`/integrations/bling/commercial-proposals/${encodeURIComponent(id)}`);
          if (current === generation.current) setDetails((previous) => ({ ...previous, [id]: { data: response.data.proposal } }));
        } catch (requestError) {
          if (current === generation.current) setDetails((previous) => ({ ...previous, [id]: { error: formatApiError(requestError) } }));
        }
      }
    } finally { if (current === generation.current) { setFetching(false); busy.current = false; } }
  };

  return <SafeAreaView style={styles.root} edges={["top"]}><ScrollView contentContainerStyle={styles.content}>
    <Text style={styles.eyebrow}>INTEGRAÇÕES</Text><Text style={styles.title}>Bling</Text>
    <Text style={styles.subtitle}>Prévia de leitura. Consulte propostas comerciais e seus detalhes. Nenhum dado é importado, nenhuma proposta ou pedido é criado e nenhum webhook é ativado.</Text>
    {loading ? <ActivityIndicator color={theme.colors.primary} /> : <View style={styles.card}>
      <Text style={styles.status}>{status?.connected ? "CONECTADO · SOMENTE LEITURA" : status?.configured ? "PRONTO PARA CONECTAR" : "CONFIGURAÇÃO PENDENTE"}</Text>
      {status?.connected && <Text style={styles.muted}>Conta autorizada em {new Date(status.connected_at || "").toLocaleString("pt-BR")}</Text>}
      {!status?.configured && <Text style={styles.error}>As variáveis seguras do Bling ainda não estão disponíveis no backend.</Text>}
      {!status?.connected && <Pressable accessibilityRole="button" style={[styles.button, (!status?.configured || connecting) && styles.disabled]} disabled={!status?.configured || connecting} onPress={connect}>{connecting ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Conectar Bling</Text>}</Pressable>}
      {status?.connected && <Pressable accessibilityRole="button" style={[styles.button, (previewing || fetching) && styles.disabled]} disabled={previewing || fetching} onPress={preview}>{previewing ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Ver prévia de propostas</Text>}</Pressable>}
    </View>}
    {proposals !== null && <View style={styles.preview}>
      <Text style={styles.previewTitle}>Prévia do Bling · até 25 propostas</Text>
      <Text style={styles.muted}>Selecione as propostas e consulte os detalhes. Os dados são exibidos apenas nesta prévia.</Text>
      {proposals.length === 0 ? <Text style={styles.muted}>Nenhuma proposta comercial foi encontrada.</Text> : <>
        <Pressable accessibilityRole="button" style={[styles.button, (fetching || selected.length === 0) && styles.disabled]} disabled={fetching || selected.length === 0} onPress={fetchSelected}>
          <Text style={styles.buttonText}>{fetching ? "Consultando detalhes..." : `Buscar detalhes (${selected.length})`}</Text>
        </Pressable>
        {proposals.map((proposal) => {
          const checked = selected.includes(proposal.external_id);
          const detail = details[proposal.external_id];
          return <View key={proposal.external_id} style={styles.proposal}>
            <Pressable accessibilityRole="checkbox" accessibilityLabel={`Selecionar proposta ${proposal.number}`} accessibilityState={{ checked, disabled: fetching }} disabled={fetching} style={styles.selection} onPress={() => setSelected((previous) => checked ? previous.filter((id) => id !== proposal.external_id) : [...previous, proposal.external_id])}>
              <Text style={styles.status}>{checked ? "☑" : "☐"} Proposta {proposal.number}</Text>
              <Text style={styles.proposalName}>{proposal.client_name}</Text>
              <Text style={styles.muted}>{proposal.date || "Sem data"} · {money(proposal.total)}</Text>
            </Pressable>
            {checked && detail?.loading && <ActivityIndicator accessibilityLabel="Carregando detalhes" color={theme.colors.primary} />}
            {checked && detail?.error && <Text accessibilityRole="alert" style={styles.error}>{detail.error} Selecione “Buscar detalhes” para tentar novamente.</Text>}
            {checked && detail?.data && <View style={styles.detail}>
              <Text style={styles.previewTitle}>Detalhes · somente leitura</Text>
              <Text style={styles.proposalName}>Cliente: {detail.data.client_name}</Text>
              <Text style={styles.muted}>CNPJ/CPF: {detail.data.document || "Não informado"}</Text>
              {detail.data.items.length === 0 && <Text style={styles.muted}>Nenhum item informado pelo Bling.</Text>}
              {detail.data.items.map((item, index) => <View key={index} style={styles.proposal}>
                <Text style={styles.proposalName}>{item.description}</Text>
                {item.code && <Text style={styles.muted}>Código: {item.code}</Text>}
                <Text style={styles.muted}>Quantidade: {item.quantity === null ? "Não informada" : Number(item.quantity).toLocaleString("pt-BR", { maximumFractionDigits: 6 })} · Unidade: {item.unit || "Não informada"}</Text>
                <Text style={styles.muted}>Preço unitário: {money(item.unit_price)}</Text>
                <Text style={styles.proposalName}>Subtotal bruto: {money(item.gross_total)}</Text>
              </View>)}
              <Text style={styles.muted}>Subtotal bruto = quantidade × preço unitário, antes de descontos. O total do Bling pode incluir descontos, frete e outras despesas.</Text>
              <Text style={styles.proposalTotal}>Total da proposta no Bling: {money(detail.data.total)}</Text>
            </View>}
          </View>;
        })}
      </>}
    </View>}
    {error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
  </ScrollView></SafeAreaView>;
}

const styles = StyleSheet.create({ root: { flex: 1, backgroundColor: theme.colors.bg }, content: { width: "100%", maxWidth: 720, alignSelf: "center", padding: 24, gap: 14 }, eyebrow: { color: theme.colors.primary, fontWeight: "800", fontSize: 12, letterSpacing: 1 }, title: { color: theme.colors.text, fontSize: 30, fontWeight: "800" }, subtitle: { color: theme.colors.textMuted, lineHeight: 21 }, card: { backgroundColor: "#fff", borderRadius: 12, borderWidth: 1, borderColor: theme.colors.border, padding: 20, gap: 14 }, status: { color: theme.colors.primary, fontWeight: "900" }, muted: { color: theme.colors.textMuted }, button: { alignSelf: "flex-start", backgroundColor: theme.colors.primary, borderRadius: 8, paddingVertical: 12, paddingHorizontal: 16, minWidth: 155, alignItems: "center" }, buttonText: { color: "#fff", fontWeight: "800" }, disabled: { opacity: 0.45 }, error: { color: "#B42318", backgroundColor: "#FEE4E2", padding: 12, borderRadius: 8 }, preview: { backgroundColor: "#fff", borderRadius: 12, borderWidth: 1, borderColor: theme.colors.border, padding: 20, gap: 12 }, previewTitle: { color: theme.colors.text, fontSize: 18, fontWeight: "800" }, proposal: { borderTopWidth: 1, borderColor: theme.colors.border, paddingTop: 12, gap: 8 }, proposalName: { color: theme.colors.text, fontWeight: "800" }, proposalTotal: { color: theme.colors.text, fontWeight: "800", textAlign: "right" }, selection: { paddingVertical: 8, gap: 6 }, detail: { gap: 12, paddingVertical: 12 } });
