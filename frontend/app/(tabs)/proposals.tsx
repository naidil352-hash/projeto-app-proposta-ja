import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useRouter } from "expo-router";
import { api, formatApiError } from "../../src/api";
import { theme, statusMeta, formatCurrency, formatDate, daysSince } from "../../src/theme";
import { followUpMessage, openWhatsApp, generateProposalPdf, sharePdf } from "../../src/pdf";

type Proposal = {
  id: string;
  client_name: string;
  client_document: string;
  client_phone: string;
  products: any[];
  shipping_deadline: string;
  status: string;
  total: number;
  created_at: string;
};

type Company = { company_name?: string; [k: string]: any };

const FILTERS: { key: string; label: string }[] = [
  { key: "all", label: "Todos" },
  { key: "aberto", label: "Abertos" },
  { key: "realizado", label: "Realizados" },
  { key: "perdido", label: "Perdidos" },
];

export default function Proposals() {
  const router = useRouter();
  const [items, setItems] = useState<Proposal[]>([]);
  const [company, setCompany] = useState<Company>({});
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectMode, setSelectMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const load = useCallback(async (f = filter) => {
    try {
      setLoading(true);
      const qs = f === "all" ? "" : `?status=${f}`;
      const [prop, comp] = await Promise.all([api.get(`/proposals${qs}`), api.get("/company")]);
      setItems(prop.data);
      setCompany(comp.data);
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useFocusEffect(
    useCallback(() => {
      load(filter);
    }, [load, filter])
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load(filter);
    setRefreshing(false);
  };

  const toggleSelect = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const exitSelect = () => {
    setSelectMode(false);
    setSelected(new Set());
  };

  const shareSelected = async () => {
    try {
      const list = items.filter((p) => selected.has(p.id));
      if (!list.length) return;
      for (const p of list) {
        const uri = await generateProposalPdf(p as any, company);
        await sharePdf(uri);
      }
      exitSelect();
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Falha ao gerar PDF");
    }
  };

  const followUpSelected = async () => {
    const list = items.filter((p) => selected.has(p.id) && p.status === "aberto");
    if (!list.length) {
      Alert.alert("Atenção", "Selecione ao menos 1 proposta aberta");
      return;
    }
    for (const p of list) {
      await openWhatsApp(p.client_phone, followUpMessage(p.client_name));
    }
    exitSelect();
  };

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="proposals-screen">
      <View style={s.header}>
        <Text style={s.title}>Propostas</Text>
        {selectMode ? (
          <TouchableOpacity onPress={exitSelect} testID="cancel-select">
            <Text style={s.headerAction}>Cancelar</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity onPress={() => setSelectMode(true)} testID="enter-select">
            <Text style={s.headerAction}>Selecionar</Text>
          </TouchableOpacity>
        )}
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={s.filters}
      >
        {FILTERS.map((f) => (
          <TouchableOpacity
            key={f.key}
            testID={`filter-${f.key}`}
            onPress={() => setFilter(f.key)}
            style={[s.chip, filter === f.key && s.chipActive]}
          >
            <Text style={[s.chipText, filter === f.key && s.chipTextActive]}>{f.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={theme.colors.primary} />
      ) : (
        <ScrollView
          contentContainerStyle={s.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        >
          {items.length === 0 && (
            <View style={s.empty} testID="empty-state">
              <Ionicons name="document-text-outline" size={48} color={theme.colors.textMuted} />
              <Text style={s.emptyText}>Nenhuma proposta por aqui ainda</Text>
              <TouchableOpacity style={s.emptyBtn} onPress={() => router.push("/(tabs)/new")}>
                <Text style={s.emptyBtnText}>Criar primeira</Text>
              </TouchableOpacity>
            </View>
          )}
          {items.map((p) => {
            const st = statusMeta[p.status];
            const stale = p.status === "aberto" && daysSince(p.created_at) >= 3;
            const isSel = selected.has(p.id);
            return (
              <TouchableOpacity
                key={p.id}
                testID={`proposal-item-${p.id}`}
                style={[s.card, isSel && s.cardSelected]}
                onPress={() => {
                  if (selectMode) toggleSelect(p.id);
                  else router.push(`/proposal/${p.id}`);
                }}
                onLongPress={() => {
                  setSelectMode(true);
                  toggleSelect(p.id);
                }}
              >
                {selectMode && (
                  <View style={[s.checkbox, isSel && s.checkboxOn]}>
                    {isSel && <Ionicons name="checkmark" size={16} color="#fff" />}
                  </View>
                )}
                <View style={{ flex: 1 }}>
                  <View style={s.rowTop}>
                    <Text style={s.name} numberOfLines={1}>
                      {p.client_name}
                    </Text>
                    <View style={[s.badge, { backgroundColor: st.bg, borderColor: st.border }]}>
                      <Text style={[s.badgeText, { color: st.text }]}>{st.label}</Text>
                    </View>
                  </View>
                  <Text style={s.sub} numberOfLines={1}>
                    {p.client_document} · {p.client_phone}
                  </Text>
                  <View style={s.rowBottom}>
                    <Text style={s.total}>{formatCurrency(p.total)}</Text>
                    <Text style={s.date}>{formatDate(p.created_at)}</Text>
                  </View>
                  {stale && (
                    <View style={s.staleTag}>
                      <Ionicons name="alarm-outline" size={12} color={theme.colors.warn} />
                      <Text style={s.staleText}>Aberto há {daysSince(p.created_at)} dias</Text>
                    </View>
                  )}
                </View>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      )}

      {selectMode && selected.size > 0 && (
        <View style={s.actionBar} testID="bulk-action-bar">
          <TouchableOpacity style={s.actionBtn} onPress={shareSelected} testID="bulk-share">
            <Ionicons name="share-outline" size={20} color="#fff" />
            <Text style={s.actionText}>Enviar PDF ({selected.size})</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.actionBtn, { backgroundColor: theme.colors.whatsapp }]}
            onPress={followUpSelected}
            testID="bulk-followup"
          >
            <Ionicons name="logo-whatsapp" size={20} color="#fff" />
            <Text style={s.actionText}>Follow-up</Text>
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.bg },
  header: {
    paddingHorizontal: 24,
    paddingTop: 12,
    paddingBottom: 4,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  title: { fontSize: 28, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
  headerAction: { color: theme.colors.text, fontWeight: "700" },
  filters: { paddingHorizontal: 24, paddingVertical: 12, gap: 8 },
  chip: {
    height: 36,
    paddingHorizontal: 14,
    borderRadius: 999,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 8,
  },
  chipActive: { backgroundColor: theme.colors.primary, borderColor: theme.colors.primary },
  chipText: { color: theme.colors.textSec, fontSize: 13, fontWeight: "600" },
  chipTextActive: { color: "#fff" },
  list: { padding: 24, paddingBottom: 120, gap: 12 },
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 16,
    borderRadius: 16,
  },
  cardSelected: { borderColor: theme.colors.primary, backgroundColor: "#F8FAFC" },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: theme.colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  checkboxOn: { backgroundColor: theme.colors.primary, borderColor: theme.colors.primary },
  rowTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  name: { fontSize: 16, fontWeight: "700", color: theme.colors.text, flex: 1 },
  badge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, borderWidth: 1 },
  badgeText: { fontSize: 11, fontWeight: "700" },
  sub: { fontSize: 13, color: theme.colors.textSec, marginTop: 4 },
  rowBottom: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 10 },
  total: { fontSize: 18, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
  date: { fontSize: 12, color: theme.colors.textMuted },
  staleTag: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    marginTop: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
    backgroundColor: "#FFFBEB",
    alignSelf: "flex-start",
    borderRadius: 6,
  },
  staleText: { fontSize: 11, color: theme.colors.warn, fontWeight: "600" },
  empty: { alignItems: "center", marginTop: 60, gap: 12 },
  emptyText: { color: theme.colors.textSec },
  emptyBtn: {
    marginTop: 8,
    paddingHorizontal: 20,
    paddingVertical: 12,
    backgroundColor: theme.colors.primary,
    borderRadius: 12,
  },
  emptyBtnText: { color: "#fff", fontWeight: "700" },
  actionBar: {
    position: "absolute",
    bottom: 16,
    left: 16,
    right: 16,
    flexDirection: "row",
    gap: 8,
  },
  actionBtn: {
    flex: 1,
    height: 52,
    backgroundColor: theme.colors.primary,
    borderRadius: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  actionText: { color: "#fff", fontWeight: "700" },
});
