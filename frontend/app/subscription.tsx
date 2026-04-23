import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Platform,
  AppState,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as WebBrowser from "expo-web-browser";
import { useFocusEffect, useRouter } from "expo-router";
import { api, formatApiError } from "../src/api";
import { theme, formatCurrency, formatDate } from "../src/theme";

type Plan = { id: string; amount: number; currency: string; days: number; label: string };

type MeState = {
  plan: string;
  pro_until: string | null;
  month_count: number;
  month_quota: number | null;
  is_pro: boolean;
};

export default function SubscriptionScreen() {
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [me, setMe] = useState<MeState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const pollingRef = useRef<{ session: string | null; stop: boolean }>({ session: null, stop: true });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [pl, mine] = await Promise.all([
        api.get("/subscription/plans"),
        api.get("/subscription/me"),
      ]);
      setPlans(pl.data.plans || []);
      setMe(mine.data);
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  // Stop polling when unmounted
  useEffect(() => {
    return () => {
      pollingRef.current.stop = true;
    };
  }, []);

  // Refresh on returning from browser (AppState → active)
  useEffect(() => {
    const sub = AppState.addEventListener("change", (st) => {
      if (st === "active" && pollingRef.current.session) {
        pollStatus(pollingRef.current.session);
      }
    });
    return () => sub.remove();
  }, []);

  const pollStatus = async (session_id: string) => {
    pollingRef.current.session = session_id;
    pollingRef.current.stop = false;
    const maxTries = 20;
    for (let i = 0; i < maxTries; i++) {
      if (pollingRef.current.stop) return;
      try {
        const { data } = await api.get(`/subscription/status/${session_id}`);
        if (data.payment_status === "paid") {
          setMe({
            plan: data.plan,
            pro_until: data.pro_until,
            month_count: data.month_count,
            month_quota: data.month_quota,
            is_pro: data.is_pro,
          });
          pollingRef.current.stop = true;
          Alert.alert("Plano Pro ativado! 🎉", "Agora você tem propostas ilimitadas.");
          return;
        }
        if (data.status === "expired") {
          pollingRef.current.stop = true;
          return;
        }
      } catch {}
      await new Promise((r) => setTimeout(r, 3000));
    }
  };

  const subscribe = async (planId: string) => {
    try {
      setBusy(planId);
      const { data } = await api.post("/subscription/checkout", { plan: planId });
      const { url, session_id } = data;
      if (!url) {
        Alert.alert("Erro", "Falha ao iniciar pagamento");
        return;
      }
      pollingRef.current.session = session_id;
      if (Platform.OS === "web") {
        // On web, open in new tab; we still poll
        window.open(url, "_blank");
      } else {
        await WebBrowser.openBrowserAsync(url);
      }
      // Start polling in background
      pollStatus(session_id);
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={s.root}>
        <ActivityIndicator style={{ marginTop: 60 }} color={theme.colors.primary} />
      </SafeAreaView>
    );
  }

  const usedPct =
    me?.month_quota && me?.month_count !== undefined
      ? Math.min(100, Math.round((me.month_count / me.month_quota) * 100))
      : null;

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="subscription-screen">
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} style={s.back}>
          <Ionicons name="chevron-back" size={24} color={theme.colors.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Planos</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={s.scroll}>
        <Text style={s.title}>Escolha seu plano</Text>
        <Text style={s.subtitle}>
          Comece grátis com {me?.month_quota ?? 10} propostas por mês. Pro libera tudo.
        </Text>

        {me?.is_pro ? (
          <View style={s.proCard} testID="active-pro">
            <Ionicons name="star" size={22} color="#fff" />
            <View style={{ flex: 1 }}>
              <Text style={s.proTitle}>Plano Pro ativo ✨</Text>
              <Text style={s.proSub}>Válido até {formatDate(me.pro_until)}</Text>
            </View>
          </View>
        ) : (
          <View style={s.usageCard}>
            <Text style={s.usageLabel}>
              Uso do mês ({me?.month_count || 0} / {me?.month_quota || 10})
            </Text>
            <View style={s.bar}>
              <View style={[s.barFill, { width: `${usedPct || 0}%` }]} />
            </View>
            {usedPct && usedPct >= 80 && (
              <Text style={s.warnText}>
                ⚠️ Quase atingindo o limite — considere o upgrade.
              </Text>
            )}
          </View>
        )}

        {plans.map((p) => {
          const monthly = p.id === "pro_monthly";
          const perMonth = monthly ? p.amount : p.amount / 12;
          return (
            <View key={p.id} style={[s.planCard, !monthly && s.planCardBest]}>
              {!monthly && (
                <View style={s.best}>
                  <Text style={s.bestText}>🔥 2 meses grátis</Text>
                </View>
              )}
              <Text style={s.planLabel}>{p.label}</Text>
              <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 4, marginTop: 6 }}>
                <Text style={s.planPrice}>{formatCurrency(p.amount)}</Text>
                <Text style={s.planPer}>/ {monthly ? "mês" : "ano"}</Text>
              </View>
              {!monthly && (
                <Text style={s.planSub}>
                  Equivale a {formatCurrency(perMonth)}/mês
                </Text>
              )}
              <View style={s.feats}>
                <Feat text="Propostas ilimitadas" />
                <Feat text="Histórico completo de clientes" />
                <Feat text="PDF com logo personalizada" />
                <Feat text="Follow-up automático no WhatsApp" />
                <Feat text="Dashboard com métricas de venda" />
              </View>
              <TouchableOpacity
                testID={`subscribe-${p.id}`}
                style={[
                  s.subBtn,
                  me?.is_pro && { opacity: 0.5 },
                  busy === p.id && { opacity: 0.7 },
                ]}
                onPress={() => subscribe(p.id)}
                disabled={me?.is_pro || !!busy}
              >
                {busy === p.id ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <>
                    <Ionicons name="lock-open-outline" size={18} color="#fff" />
                    <Text style={s.subBtnText}>
                      {me?.is_pro ? "Plano ativo" : "Assinar agora"}
                    </Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          );
        })}

        <View style={s.trust}>
          <Ionicons name="shield-checkmark-outline" size={16} color={theme.colors.textSec} />
          <Text style={s.trustText}>Pagamento seguro via Stripe · cancele quando quiser</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function Feat({ text }: { text: string }) {
  return (
    <View style={s.featRow}>
      <Ionicons name="checkmark-circle" size={18} color={theme.colors.statusWonText} />
      <Text style={s.featText}>{text}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.bg },
  topbar: {
    height: 52,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  back: { padding: 4 },
  topTitle: { fontSize: 14, fontWeight: "700", color: theme.colors.textSec },
  scroll: { padding: 24, paddingBottom: 40, gap: 16 },
  title: { fontSize: 28, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
  subtitle: { color: theme.colors.textSec, fontSize: 14 },
  proCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: theme.colors.primary,
    padding: 18,
    borderRadius: 16,
  },
  proTitle: { color: "#fff", fontWeight: "800", fontSize: 16 },
  proSub: { color: "#94A3B8", fontSize: 13, marginTop: 2 },
  usageCard: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 16,
    borderRadius: 14,
  },
  usageLabel: { fontSize: 13, color: theme.colors.textSec, fontWeight: "600" },
  bar: { height: 8, backgroundColor: theme.colors.surfaceAlt, borderRadius: 4, marginTop: 10 },
  barFill: { height: 8, backgroundColor: theme.colors.primary, borderRadius: 4 },
  warnText: { color: theme.colors.warn, fontSize: 12, marginTop: 8 },
  planCard: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 20,
    borderRadius: 18,
    gap: 4,
    marginTop: 8,
  },
  planCardBest: { borderColor: theme.colors.primary, borderWidth: 2 },
  best: {
    position: "absolute",
    top: -12,
    right: 16,
    backgroundColor: theme.colors.primary,
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 999,
  },
  bestText: { color: "#fff", fontSize: 11, fontWeight: "700" },
  planLabel: {
    fontSize: 12,
    color: theme.colors.textMuted,
    fontWeight: "700",
    letterSpacing: 1.5,
    textTransform: "uppercase",
  },
  planPrice: { fontSize: 34, fontWeight: "800", color: theme.colors.text, letterSpacing: -1 },
  planPer: { color: theme.colors.textSec, fontSize: 15, marginBottom: 6 },
  planSub: { color: theme.colors.textSec, fontSize: 12 },
  feats: { marginTop: 14, gap: 8 },
  featRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  featText: { color: theme.colors.text, fontSize: 14 },
  subBtn: {
    marginTop: 14,
    height: 52,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
  },
  subBtnText: { color: "#fff", fontSize: 15, fontWeight: "700" },
  trust: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    justifyContent: "center",
    marginTop: 8,
  },
  trustText: { color: theme.colors.textSec, fontSize: 12 },
});
