import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useRouter } from "expo-router";
import { api, formatApiError } from "../../src/api";
import { useAuth } from "../../src/auth";
import { theme, formatCurrency } from "../../src/theme";

type Stats = {
  open_count: number;
  won_count: number;
  lost_count: number;
  open_value: number;
  month_won_value: number;
  stale_count: number;
};

export default function Dashboard() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setErr(null);
      const { data } = await api.get("/stats");
      setStats(data);
    } catch (e) {
      setErr(formatApiError(e));
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  return (
    <SafeAreaView style={s.root} testID="dashboard-screen" edges={["top"]}>
      <ScrollView
        contentContainerStyle={s.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        <View style={s.header}>
          <View>
            <Text style={s.hello}>Olá, {user?.name?.split(" ")[0] || ""} 👋</Text>
            <Text style={s.title}>Painel</Text>
          </View>
          <TouchableOpacity style={s.logout} onPress={logout} testID="logout-btn">
            <Ionicons name="log-out-outline" size={22} color={theme.colors.text} />
          </TouchableOpacity>
        </View>

        {err && <Text style={s.error}>{err}</Text>}

        {stats?.stale_count ? (
          <TouchableOpacity
            style={s.alert}
            onPress={() => router.push("/(tabs)/proposals")}
            testID="stale-alert"
          >
            <Ionicons name="alert-circle" size={24} color={theme.colors.warn} />
            <View style={{ flex: 1 }}>
              <Text style={s.alertTitle}>{stats.stale_count} proposta(s) precisam de follow-up</Text>
              <Text style={s.alertSub}>Abertas há 3+ dias · toque para revisar</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={theme.colors.textMuted} />
          </TouchableOpacity>
        ) : null}

        <View style={s.bigCard} testID="card-month-won">
          <Text style={s.bigLabel}>Ganho este mês</Text>
          <Text style={s.bigValue}>{formatCurrency(stats?.month_won_value || 0)}</Text>
          <View style={s.row}>
            <View style={s.pill}>
              <Ionicons name="checkmark-circle" size={14} color="#fff" />
              <Text style={s.pillText}>{stats?.won_count || 0} realizados</Text>
            </View>
          </View>
        </View>

        <View style={s.grid}>
          <MetricCard
            testID="card-open"
            icon="time-outline"
            label="Abertos"
            value={String(stats?.open_count ?? 0)}
            sub={formatCurrency(stats?.open_value || 0)}
            accent={theme.colors.statusOpenText}
          />
          <MetricCard
            testID="card-lost"
            icon="close-circle-outline"
            label="Perdidos"
            value={String(stats?.lost_count ?? 0)}
            sub="total"
            accent={theme.colors.statusLostText}
          />
        </View>

        <TouchableOpacity
          style={s.newBtn}
          onPress={() => router.push("/(tabs)/new")}
          testID="create-new-btn"
        >
          <Ionicons name="add-circle" size={22} color="#fff" />
          <Text style={s.newBtnText}>Criar nova proposta</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function MetricCard({
  icon,
  label,
  value,
  sub,
  accent,
  testID,
}: {
  icon: any;
  label: string;
  value: string;
  sub: string;
  accent: string;
  testID?: string;
}) {
  return (
    <View style={s.metric} testID={testID}>
      <View style={[s.metricIcon, { backgroundColor: accent + "18" }]}>
        <Ionicons name={icon} size={18} color={accent} />
      </View>
      <Text style={s.metricLabel}>{label}</Text>
      <Text style={s.metricValue}>{value}</Text>
      <Text style={s.metricSub}>{sub}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.bg },
  scroll: { padding: 24, paddingBottom: 40, gap: 16 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  hello: { color: theme.colors.textSec, fontSize: 14 },
  title: { color: theme.colors.text, fontSize: 28, fontWeight: "800", letterSpacing: -0.5 },
  logout: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  error: { color: theme.colors.danger, fontSize: 14 },
  alert: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: "#FFFBEB",
    borderWidth: 1,
    borderColor: "#FDE68A",
    padding: 16,
    borderRadius: 12,
  },
  alertTitle: { fontWeight: "700", color: theme.colors.text, fontSize: 15 },
  alertSub: { fontSize: 12, color: theme.colors.textSec, marginTop: 2 },
  bigCard: {
    backgroundColor: theme.colors.primary,
    borderRadius: 20,
    padding: 24,
  },
  bigLabel: {
    color: "#94A3B8",
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1.5,
    textTransform: "uppercase",
  },
  bigValue: { color: "#fff", fontSize: 36, fontWeight: "800", letterSpacing: -1, marginTop: 8 },
  row: { flexDirection: "row", marginTop: 14, gap: 8 },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: "rgba(255,255,255,0.15)",
    borderRadius: 999,
  },
  pillText: { color: "#fff", fontSize: 12, fontWeight: "600" },
  grid: { flexDirection: "row", gap: 12 },
  metric: {
    flex: 1,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 16,
    borderRadius: 16,
    gap: 6,
  },
  metricIcon: {
    width: 32,
    height: 32,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 6,
  },
  metricLabel: { fontSize: 12, color: theme.colors.textSec, fontWeight: "600" },
  metricValue: { fontSize: 28, color: theme.colors.text, fontWeight: "800", letterSpacing: -0.5 },
  metricSub: { fontSize: 12, color: theme.colors.textMuted },
  newBtn: {
    marginTop: 8,
    height: 56,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  newBtnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
});
