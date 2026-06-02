import React, { useCallback, useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Alert,
  TextInput,
  useWindowDimensions,
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
  const { width } = useWindowDimensions();
  const isDesktop = width >= 900;
  const [items, setItems] = useState<Proposal[]>([]);
  const [company, setCompany] = useState<Company>({});
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
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

  const shareProposal = async (proposal: Proposal) => {
    try {
      const uri = await generateProposalPdf(proposal as any, company);
      await sharePdf(uri);
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Falha ao gerar PDF");
    }
  };

  const followUpProposal = async (proposal: Proposal) => {
    if (proposal.status !== "aberto") {
      Alert.alert("Atenção", "Follow-up disponível apenas para propostas abertas");
      return;
    }
    await openWhatsApp(proposal.client_phone, followUpMessage(proposal.client_name));
  };

  const searchTerm = search.trim().toLowerCase();
  const filteredItems = useMemo(() => {
    return items.filter((p) => {
      const statusMatch = filter === "all" || p.status === filter;
      if (!statusMatch) return false;
      if (!searchTerm) return true;
      return [p.client_name, p.client_document, p.client_phone, formatCurrency(p.total)]
        .some((value) => value.toLowerCase().includes(searchTerm));
    });
  }, [items, filter, searchTerm]);

  const totals = useMemo(() => {
    const open = items.filter((p) => p.status === "aberto").length;
    const won = items.filter((p) => p.status === "realizado").length;
    const lost = items.filter((p) => p.status === "perdido").length;
    const revenue = items.reduce((sum, p) => sum + p.total, 0);
    return { open, won, lost, revenue };
  }, [items]);

  const openSummary = totals.open === 1 ? "1 proposta aberta" : `${totals.open} propostas abertas`;
  const negotiationSummary = `${formatCurrency(totals.revenue)} em negociação`;

  const renderMobile = () => (
    <ScrollView
      contentContainerStyle={s.list}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      {filteredItems.length === 0 && (
        <View style={s.empty} testID="empty-state">
          <Ionicons name="document-text-outline" size={48} color={theme.colors.textMuted} />
          <Text style={s.emptyText}>Nenhuma proposta por aqui ainda</Text>
          <TouchableOpacity style={s.emptyBtn} onPress={() => router.push("/(tabs)/new")}> 
            <Text style={s.emptyBtnText}>Criar primeira</Text>
          </TouchableOpacity>
        </View>
      )}

      {filteredItems.map((p) => {
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
  );

  const renderDesktop = () => (
    <ScrollView
      contentContainerStyle={s.desktopContainer}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      <View style={s.kpiRow}>
        <View style={s.kpiCard}>
          <Text style={s.kpiLabel}>Total de propostas</Text>
          <Text style={s.kpiValue}>{items.length}</Text>
        </View>
        <View style={s.kpiCard}>
          <Text style={s.kpiLabel}>Abertas</Text>
          <Text style={s.kpiValue}>{totals.open}</Text>
        </View>
        <View style={s.kpiCard}>
          <Text style={s.kpiLabel}>Realizadas</Text>
          <Text style={s.kpiValue}>{totals.won}</Text>
        </View>
        <View style={s.kpiCard}>
          <Text style={s.kpiLabel}>Perdidas</Text>
          <Text style={s.kpiValue}>{totals.lost}</Text>
        </View>
        <View style={s.kpiCard}>
          <Text style={s.kpiLabel}>Valor total</Text>
          <Text style={s.kpiValue}>{formatCurrency(totals.revenue)}</Text>
        </View>
      </View>

      <View style={s.searchWrapper}>
        <TextInput
          style={s.searchInput}
          placeholder="Buscar cliente, documento, telefone ou valor"
          placeholderTextColor={theme.colors.textSec}
          value={search}
          onChangeText={setSearch}
        />
      </View>

      <View style={s.table}>
        <View style={[s.tableRow, s.tableHeader]}>
          <Text style={[s.tableCell, s.colClient, s.tableHeading]}>Cliente</Text>
          <Text style={[s.tableCell, s.colMedium, s.tableHeading]}>Documento</Text>
          <Text style={[s.tableCell, s.colMedium, s.tableHeading]}>Telefone</Text>
          <Text style={[s.tableCell, s.colSmall, s.tableHeading]}>Status</Text>
          <Text style={[s.tableCell, s.colSmall, s.tableHeading]}>Total</Text>
          <Text style={[s.tableCell, s.colSmall, s.tableHeading]}>Criado</Text>
          <Text style={[s.tableCell, s.colActions, s.tableHeading]}>Ações</Text>
        </View>
        {filteredItems.map((p) => {
          const st = statusMeta[p.status];
          const stale = p.status === "aberto" && daysSince(p.created_at) >= 3;
          const isSel = selected.has(p.id);
          return (
            <View key={p.id} style={[s.tableRow, isSel && s.tableRowSelected]}>
              <TouchableOpacity
                style={[s.tableCell, s.colClient]}
                onPress={() => router.push(`/proposal/${p.id}`)}
              >
                <Text style={s.tableClientName}>{p.client_name}</Text>
              </TouchableOpacity>
              <Text style={[s.tableCell, s.colMedium]}>{p.client_document}</Text>
              <Text style={[s.tableCell, s.colMedium]}>{p.client_phone}</Text>
              <View style={[s.tableCell, s.colSmall]}> 
                <View style={[s.badge, { backgroundColor: st.bg, borderColor: st.border }]}>
                  <Text style={[s.badgeText, { color: st.text }]}>{st.label}</Text>
                </View>
              </View>
              <Text style={[s.tableCell, s.colSmall]}>{formatCurrency(p.total)}</Text>
              <Text style={[s.tableCell, s.colSmall]}>{formatDate(p.created_at)}</Text>
              <View style={[s.tableCell, s.colActions, s.actionsCell]}> 
                <TouchableOpacity
                  style={s.actionTextButton}
                  onPress={() => router.push(`/proposal/${p.id}`)}
                >
                  <Text style={s.actionTextButtonLabel}>Abrir</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={s.actionTextButton}
                  onPress={() => shareProposal(p)}
                >
                  <Text style={s.actionTextButtonLabel}>PDF</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={s.actionTextButton}
                  onPress={() => followUpProposal(p)}
                >
                  <Text style={s.actionTextButtonLabel}>WhatsApp</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.selectCheckbox, isSel && s.selectCheckboxOn]}
                  onPress={() => {
                    if (!selectMode) setSelectMode(true);
                    toggleSelect(p.id);
                  }}
                  testID={`select-checkbox-${p.id}`}
                >
                  {isSel && <Ionicons name="checkmark" size={16} color="#fff" />}
                </TouchableOpacity>
              </View>
            </View>
          );
        })}
      </View>
    </ScrollView>
  );

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="proposals-screen">
      <View style={s.header}>
        <View>
          <Text style={s.title}>Propostas</Text>
          <Text style={s.subtitle}>
            {isDesktop ? `${openSummary}\n${negotiationSummary}` : "Visualização desktop com indicadores e tabela"}
          </Text>
        </View>

        <View style={s.headerActions}>
          {isDesktop && (
            <TouchableOpacity
              style={s.newProposalBtn}
              onPress={() => router.push("/(tabs)/new")}
              testID="new-proposal"
            >
              <Ionicons name="add" size={18} color="#fff" />
              <Text style={s.newProposalText}>Nova Proposta</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={() => setSelectMode((prev) => !prev)} testID="toggle-select">
            <Text style={s.headerAction}>{selectMode ? "Cancelar" : "Selecionar"}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={s.filtersWrapper}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.filters}>
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
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={theme.colors.primary} />
      ) : isDesktop ? (
        renderDesktop()
      ) : (
        renderMobile()
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
    alignItems: "flex-end",
  },
  title: { fontSize: 28, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
  subtitle: { color: theme.colors.textSec, marginTop: 4 },
  headerAction: { color: theme.colors.text, fontWeight: "700" },
  filtersWrapper: { paddingTop: 12 },
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
  desktopContainer: { padding: 24, gap: 20, paddingBottom: 120 },
  kpiRow: { flexDirection: "row", gap: 16, flexWrap: "wrap" },
  kpiCard: {
    flex: 1,
    minWidth: 180,
    padding: 14,
    borderRadius: 20,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  kpiLabel: { color: theme.colors.textSec, fontSize: 13, marginBottom: 6 },
  kpiValue: { color: theme.colors.text, fontSize: 22, fontWeight: "800" },
  searchWrapper: { marginTop: 16, paddingHorizontal: 0 },
  searchInput: {
    minHeight: 50,
    width: "100%",
    paddingHorizontal: 18,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: "#fff",
    color: theme.colors.text,
  },
  table: {
    minWidth: 1200,
    width: "100%",
    backgroundColor: "#fff",
    borderRadius: 12,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  tableRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 16,
    paddingHorizontal: 20,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  tableHeader: { backgroundColor: theme.colors.bg },
  tableCell: { color: theme.colors.text, fontSize: 14, flexGrow: 1 },
  tableHeading: { fontWeight: "700", color: theme.colors.text, textTransform: "uppercase", fontSize: 12 },
  colClient: { flex: 4, minWidth: 320 },
  colMedium: { flex: 1.8, minWidth: 160 },
  colSmall: { flex: 1, minWidth: 120 },
  colActions: { flex: 0.8, minWidth: 140 },
  tableClientName: { fontSize: 15, fontWeight: "700", color: theme.colors.text },
  actionsCell: { flexDirection: "row", justifyContent: "flex-end", gap: 8, flexWrap: "wrap" },
  actionTextButton: {
    minHeight: 36,
    minWidth: 84,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 10,
    backgroundColor: "#F8FAFC",
    borderWidth: 1,
    borderColor: theme.colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  actionTextButtonSelected: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  actionTextButtonLabel: { color: theme.colors.text, fontWeight: "700", fontSize: 12 },
  actionTextButtonSelectedLabel: { color: "#fff" },
  selectCheckbox: {
    width: 36,
    height: 36,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: theme.colors.border,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#fff",
  },
  selectCheckboxOn: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  headerActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  newProposalBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 14,
    backgroundColor: theme.colors.accent,
  },
  newProposalText: {
    color: "#fff",
    fontWeight: "700",
  },
  rowAction: {
    width: 34,
    height: 34,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#F8FAFC",
  },
  tableRowSelected: { backgroundColor: "#F8FAFC" },
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
