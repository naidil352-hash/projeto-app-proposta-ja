import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { api, formatApiError } from "../../src/api";
import { theme, formatCurrency, formatDate } from "../../src/theme";

type ClientHistory = {
  client_id: string;
  client_name: string;
  proposal_count: number;
  open_count: number;
  qualified_count: number;
  negotiation_count: number;
  approved_count: number;
  lost_count: number;
  total_value: number;
  won_value: number;
  lost_value: number;
  open_value: number;
  conversion_rate: number;
  last_proposal_date: string | null;
};

export default function ClientHistoryDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [history, setHistory] = useState<ClientHistory | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await api.get(`/clients/${id}/history`);
      setHistory(data);
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const safeBack = () => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace("/(tabs)/clients");
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={s.root} edges={["top"]}>
        <View style={s.center}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  if (!history) {
    return (
      <SafeAreaView style={s.root} edges={["top"]}>
        <View style={s.center}>
          <Text style={s.emptyText}>Erro ao carregar histórico do cliente.</Text>
          <TouchableOpacity style={s.backBtn} onPress={safeBack}>
            <Text style={s.backBtnText}>Voltar</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="client-history-screen">
      <View style={s.topbar}>
        <TouchableOpacity onPress={safeBack} style={s.backIcon}>
          <Ionicons name="chevron-back" size={24} color={theme.colors.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Histórico de Cliente</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={s.scroll}>
        <View style={s.headerCard}>
          <View style={s.avatar}>
            <Text style={s.avatarText}>
              {history.client_name?.[0]?.toUpperCase() || "?"}
            </Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.clientName}>{history.client_name}</Text>
            <Text style={s.clientSub}>ID: {history.client_id}</Text>
          </View>
        </View>

        <Text style={s.sectionTitle}>Resumo de Conversão</Text>
        <View style={s.kpiRow}>
          <View style={s.kpiCard}>
            <Text style={s.kpiLabel}>Total de Propostas</Text>
            <Text style={s.kpiValue}>{history.proposal_count}</Text>
          </View>
          <View style={[s.kpiCard, { borderColor: "#DDD6FE" }]}>
            <Text style={[s.kpiLabel, { color: "#6D28D9" }]}>Taxa de Conversão</Text>
            <Text style={[s.kpiValue, { color: "#6D28D9" }]}>
              {history.conversion_rate}%
            </Text>
          </View>
        </View>

        <Text style={s.sectionTitle}>Valores Negociados</Text>
        <View style={s.grid}>
          <View style={s.gridRow}>
            <View style={s.metricCard}>
              <Text style={s.metricLabel}>Receita Ganha</Text>
              <Text style={[s.metricValue, { color: theme.colors.success }]}>
                {formatCurrency(history.won_value)}
              </Text>
            </View>
            <View style={s.metricCard}>
              <Text style={s.metricLabel}>Valor Aberto</Text>
              <Text style={[s.metricValue, { color: theme.colors.statusOpenText }]}>
                {formatCurrency(history.open_value)}
              </Text>
            </View>
          </View>
          <View style={s.gridRow}>
            <View style={s.metricCard}>
              <Text style={s.metricLabel}>Valor Perdido</Text>
              <Text style={[s.metricValue, { color: theme.colors.danger }]}>
                {formatCurrency(history.lost_value)}
              </Text>
            </View>
            <View style={s.metricCard}>
              <Text style={s.metricLabel}>Total Geral</Text>
              <Text style={s.metricValue}>{formatCurrency(history.total_value)}</Text>
            </View>
          </View>
        </View>

        <Text style={s.sectionTitle}>Pipeline (Propostas por Status)</Text>
        <View style={s.pipelineCard}>
          <StatusCountRow label="Aberto" count={history.open_count} color={theme.colors.statusOpenText} />
          <StatusCountRow label="Qualificado" count={history.qualified_count} color="#6D28D9" />
          <StatusCountRow label="Negociação" count={history.negotiation_count} color="#B45309" />
          <StatusCountRow label="Aprovado" count={history.approved_count} color={theme.colors.statusWonText} />
          <StatusCountRow label="Perdido" count={history.lost_count} color={theme.colors.statusLostText} />
        </View>

        {history.last_proposal_date ? (
          <Text style={s.footerDate}>
            Última proposta: {formatDate(history.last_proposal_date)}
          </Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function StatusCountRow({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <View style={s.statusRow}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        <View style={[s.statusDot, { backgroundColor: color }]} />
        <Text style={s.statusLabel}>{label}</Text>
      </View>
      <Text style={[s.statusCount, { color }]}>{count}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  emptyText: { color: theme.colors.textSec, fontSize: 15, marginBottom: 16 },
  backBtn: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    backgroundColor: theme.colors.primary,
    borderRadius: 12,
  },
  backBtnText: { color: "#fff", fontWeight: "700" },
  topbar: {
    height: 52,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  backIcon: { padding: 4 },
  topTitle: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
  scroll: { padding: 24, gap: 16, paddingBottom: 60 },
  headerCard: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 16,
    borderRadius: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { color: "#fff", fontWeight: "800", fontSize: 18 },
  clientName: { fontSize: 18, fontWeight: "800", color: theme.colors.text },
  clientSub: { fontSize: 12, color: theme.colors.textMuted },
  sectionTitle: {
    fontSize: 14,
    fontWeight: "800",
    color: theme.colors.textSec,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginTop: 8,
  },
  kpiRow: { flexDirection: "row", gap: 12 },
  kpiCard: {
    flex: 1,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 14,
    borderRadius: 16,
    gap: 4,
  },
  kpiLabel: { fontSize: 12, color: theme.colors.textSec, fontWeight: "600" },
  kpiValue: { fontSize: 24, fontWeight: "800", color: theme.colors.text },
  grid: { gap: 12 },
  gridRow: { flexDirection: "row", gap: 12 },
  metricCard: {
    flex: 1,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 14,
    borderRadius: 16,
    gap: 4,
  },
  metricLabel: { fontSize: 11, color: theme.colors.textSec, fontWeight: "600", textTransform: "uppercase" },
  metricValue: { fontSize: 16, fontWeight: "800", color: theme.colors.text },
  pipelineCard: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 16,
    paddingHorizontal: 16,
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  statusDot: { width: 10, height: 10, borderRadius: 999 },
  statusLabel: { fontSize: 14, color: theme.colors.text, fontWeight: "600" },
  statusCount: { fontSize: 14, fontWeight: "700" },
  footerDate: { fontSize: 12, color: theme.colors.textMuted, textAlign: "center", marginTop: 12 },
});
