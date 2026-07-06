import React, { useCallback, useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  TextInput,
  useWindowDimensions,
  Modal,
  Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useRouter } from "expo-router";
import { api } from "../../src/api";
import { theme, formatCurrency, formatDate } from "../../src/theme";
import { followUpMessage, openWhatsApp } from "../../src/pdf";
import { maskDocument, maskPhoneBR } from "../../src/masks";
import { useAuth } from "../../src/auth";

type Client = {
  client_id?: string;
  client_name: string;
  client_document: string;
  client_phone: string;
  email?: string;
  company?: string;
  city?: string;
  state?: string;
  address?: string;
  last_proposal_at: string;
  proposals_count: number;
  total_value: number;
};

export default function Clients() {
  const router = useRouter();
  const { user } = useAuth();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;
  const [items, setItems] = useState<Client[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const [cliName, setCliName] = useState("");
  const [cliDoc, setCliDoc] = useState("");
  const [cliPhone, setCliPhone] = useState("");
  const [cliEmail, setCliEmail] = useState("");
  const [cliCompany, setCliCompany] = useState("");
  const [cliCity, setCliCity] = useState("");
  const [cliState, setCliState] = useState("");
  const [cliAddress, setCliAddress] = useState("");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await api.get("/clients");
      setItems(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const saveClient = async () => {
    if (!editingId && user?.trial_is_expired) {
      Alert.alert(
        "Período de avaliação terminado",
        `Seu período de avaliação terminou.\n\nVocê já gerou:\n* ${user.trial_stats?.proposals_count ?? 0} propostas\n* ${user.trial_stats?.clients_count ?? 0} clientes\n* ${user.trial_stats?.negotiations_count ?? 0} negociações\n\nAssine o Plano Pro para continuar utilizando.`
      );
      return;
    }

    if (!cliName.trim() || !cliDoc.trim() || !cliPhone.trim()) {
      Alert.alert("Atenção", "Nome, documento e telefone são obrigatórios.");
      return;
    }

    const payload = {
      name: cliName.trim(),
      document: cliDoc.trim(),
      phone: cliPhone.trim(),
      email: cliEmail.trim(),
      company: cliCompany.trim(),
      city: cliCity.trim(),
      state: cliState.trim(),
      address: cliAddress.trim(),
    };

    try {
      setSaving(true);
      if (editingId) {
        await api.put(`/clients/${editingId}`, payload);
      } else {
        await api.post("/clients", payload);
      }
      setModalOpen(false);
      setEditingId(null);
      await load();
    } catch (e: any) {
      const msg = e.response?.data?.detail || "Falha ao salvar cliente";
      Alert.alert("Erro", msg);
    } finally {
      setSaving(false);
    }
  };

  const deleteClient = async (id: string) => {
    Alert.alert(
      "Excluir Cliente",
      "Deseja realmente excluir este cliente?",
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Excluir",
          style: "destructive",
          onPress: async () => {
            try {
              await api.delete(`/clients/${id}`);
              await load();
            } catch {
              Alert.alert("Erro", "Falha ao excluir cliente");
            }
          },
        },
      ]
    );
  };

  const startEdit = (c: Client) => {
    setEditingId(c.client_id || null);
    setCliName(c.client_name);
    setCliDoc(c.client_document);
    setCliPhone(c.client_phone);
    setCliEmail(c.email || "");
    setCliCompany(c.company || "");
    setCliCity(c.city || "");
    setCliState(c.state || "");
    setCliAddress(c.address || "");
    setModalOpen(true);
  };

  const totals = useMemo(() => {
    const active = items.filter((c) => c.proposals_count > 0).length;
    const totalProposals = items.reduce((sum, c) => sum + c.proposals_count, 0);
    return { total: items.length, active, totalProposals };
  }, [items]);

  const searchTerm = search.trim().toLowerCase();
  const filteredItems = useMemo(
    () =>
      items.filter((c) => {
        if (!searchTerm) return true;
        return [
          c.client_name || "",
          c.client_phone || "",
          c.client_document || "",
          c.city || "",
          c.state || "",
          c.company || "",
          c.email || "",
          c.address || ""
        ].some((value) => value.toLowerCase().includes(searchTerm));
      }),
    [items, searchTerm]
  );

  const openSummary =
    totals.active === 1 ? "1 cliente ativo" : `${totals.active} clientes ativos`;
  const historySummary = `${totals.total} clientes no histórico`;

  const renderMobile = () => (
    <ScrollView
      contentContainerStyle={s.list}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
    >
      {filteredItems.length === 0 && (
        <View style={s.empty}>
          <Ionicons name="people-outline" size={48} color={theme.colors.textMuted} />
          <Text style={s.emptyText}>Nenhum cliente encontrado</Text>
        </View>
      )}
      {filteredItems.map((c) => (
        <TouchableOpacity
          key={c.client_id || c.client_document || c.client_name}
          style={s.card}
          onPress={() => {
            if (c.client_id) {
              router.push(`/clients/${c.client_id}`);
            }
          }}
          testID={`client-item-${c.client_id}`}
        >
          <View style={s.avatar}>
            <Text style={s.avatarText}>{c.client_name?.[0]?.toUpperCase() || "?"}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.name}>{c.client_name}</Text>
            {c.company ? <Text style={{ fontSize: 13, color: theme.colors.text, fontWeight: "600" }}>{c.company}</Text> : null}
            <Text style={s.sub}>
              {c.client_document} · {c.client_phone}
            </Text>
            {c.email ? <Text style={s.sub}>{c.email}</Text> : null}
            {c.city ? <Text style={s.sub}>{c.city} - {c.state || ""}</Text> : null}
            <View style={s.row}>
              <View style={s.pill}>
                <Text style={s.pillText}>
                  {c.proposals_count} {c.proposals_count === 1 ? "proposta" : "propostas"}
                </Text>
              </View>
              <Text style={s.total}>{formatCurrency(c.total_value)}</Text>
            </View>
            <Text style={s.date}>Última: {formatDate(c.last_proposal_at)}</Text>
          </View>
          
          <View style={{ flexDirection: "column", gap: 6, alignItems: "center" }}>
            <TouchableOpacity
              style={s.whats}
              onPress={() => openWhatsApp(c.client_phone, followUpMessage(c.client_name))}
              testID={`whatsapp-${c.client_document}`}
            >
              <Ionicons name="logo-whatsapp" size={22} color="#fff" />
            </TouchableOpacity>

            <TouchableOpacity
              style={s.newPropBtnMobile}
              onPress={() =>
                router.push(
                  `/(tabs)/new?clientName=${encodeURIComponent(c.client_name)}` +
                  `&clientPhone=${encodeURIComponent(c.client_phone)}` +
                  `&clientDocument=${encodeURIComponent(c.client_document)}` +
                  `&clientEmail=${encodeURIComponent(c.email || "")}` +
                  `&clientCompany=${encodeURIComponent(c.company || "")}` +
                  `&clientCity=${encodeURIComponent(c.city || "")}` +
                  `&clientState=${encodeURIComponent(c.state || "")}` +
                  `&clientAddress=${encodeURIComponent(c.address || "")}` +
                  `&clientId=${encodeURIComponent(c.client_id || "")}`
                )
              }
              testID={`new-prop-mobile-${c.client_document}`}
            >
              <Ionicons name="document-text-outline" size={20} color="#fff" />
            </TouchableOpacity>

            <View style={{ flexDirection: "row", gap: 10, justifyContent: "center", marginTop: 4 }}>
              <TouchableOpacity onPress={() => startEdit(c)} testID={`edit-client-mobile-${c.client_id}`}>
                <Ionicons name="pencil-outline" size={18} color="#2563EB" />
              </TouchableOpacity>
              <TouchableOpacity onPress={() => deleteClient(c.client_id!)} testID={`delete-client-mobile-${c.client_id}`}>
                <Ionicons name="trash-outline" size={18} color="#DC2626" />
              </TouchableOpacity>
            </View>
          </View>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  const renderDesktop = () => (
    <ScrollView
      contentContainerStyle={s.desktopContainer}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
    >
      <View style={s.kpiRow}>
        <View style={s.kpiCard}>
          <Text style={s.kpiLabel}>Total de clientes</Text>
          <Text style={s.kpiValue}>{totals.total}</Text>
        </View>
        <View style={s.kpiCard}>
          <Text style={s.kpiLabel}>Clientes ativos</Text>
          <Text style={s.kpiValue}>{totals.active}</Text>
        </View>
        <View style={s.kpiCard}>
          <Text style={s.kpiLabel}>Propostas associadas</Text>
          <Text style={s.kpiValue}>{totals.totalProposals}</Text>
        </View>
      </View>

      <View style={s.searchWrapper}>
        <TextInput
          style={s.searchInput}
          placeholder="Buscar nome, telefone ou cidade"
          placeholderTextColor={theme.colors.textSec}
          value={search}
          onChangeText={setSearch}
        />
      </View>

      <View style={s.table}>
        <View style={[s.tableRow, s.tableHeader]}>
          <Text style={[s.tableCell, s.colClient, s.tableHeading]}>Cliente</Text>
          <Text style={[s.tableCell, s.colMedium, s.tableHeading]}>Cidade</Text>
          <Text style={[s.tableCell, s.colMedium, s.tableHeading]}>Telefone</Text>
          <Text style={[s.tableCell, s.colSmall, s.tableHeading]}>Última atividade</Text>
          <Text style={[s.tableCell, s.colActions, s.tableHeading]}>Ações</Text>
        </View>
        {filteredItems.map((c) => {
          const isActive = c.proposals_count > 0;
          return (
            <View key={c.client_id || c.client_document || c.client_name} style={[s.tableRow, isActive && s.tableRowSelected]}>
              <View style={[s.tableCell, s.colClient]}>
                <Text style={s.tableClientName}>{c.client_name}</Text>
                {c.company ? <Text style={{ fontSize: 13, color: theme.colors.text, fontWeight: "600" }}>{c.company}</Text> : null}
                <Text style={s.tableSub}>{c.client_document}</Text>
                {c.email ? <Text style={s.tableSub}>{c.email}</Text> : null}
              </View>
              <Text style={[s.tableCell, s.colMedium]}>{c.city ? `${c.city} - ${c.state || ""}` : "-"}</Text>
              <Text style={[s.tableCell, s.colMedium]}>{c.client_phone}</Text>
              <Text style={[s.tableCell, s.colSmall]}>{formatDate(c.last_proposal_at)}</Text>
              <View style={[s.tableCell, s.colActions, s.actionsCell]}>
                {c.client_id ? (
                  <TouchableOpacity
                    style={s.actionTextButton}
                    onPress={() => router.push(`/clients/${c.client_id}`)}
                  >
                    <Text style={s.actionTextButtonLabel}>Histórico</Text>
                  </TouchableOpacity>
                ) : null}
                <TouchableOpacity
                  style={s.actionTextButton}
                  onPress={() =>
                    router.push(
                      `/(tabs)/new?clientName=${encodeURIComponent(c.client_name)}` +
                      `&clientPhone=${encodeURIComponent(c.client_phone)}` +
                      `&clientDocument=${encodeURIComponent(c.client_document)}` +
                      `&clientEmail=${encodeURIComponent(c.email || "")}` +
                      `&clientCompany=${encodeURIComponent(c.company || "")}` +
                      `&clientCity=${encodeURIComponent(c.city || "")}` +
                      `&clientState=${encodeURIComponent(c.state || "")}` +
                      `&clientAddress=${encodeURIComponent(c.address || "")}` +
                      `&clientId=${encodeURIComponent(c.client_id || "")}`
                    )
                  }
                >
                  <Text style={s.actionTextButtonLabel}>Nova proposta</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={s.actionTextButton}
                  onPress={() => openWhatsApp(c.client_phone, followUpMessage(c.client_name))}
                >
                  <Text style={s.actionTextButtonLabel}>WhatsApp</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={s.actionTextButton}
                  onPress={() => startEdit(c)}
                >
                  <Text style={s.actionTextButtonLabel}>Editar</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={s.actionTextButton}
                  onPress={() => deleteClient(c.client_id!)}
                >
                  <Text style={[s.actionTextButtonLabel, { color: "#DC2626" }]}>Excluir</Text>
                </TouchableOpacity>
              </View>
            </View>
          );
        })}
      </View>
    </ScrollView>
  );

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="clients-screen">
      <Modal
        visible={modalOpen}
        transparent
        animationType="fade"
        onRequestClose={() => {
          setModalOpen(false);
          setEditingId(null);
        }}
      >
        <View
          style={{
            flex: 1,
            backgroundColor: "rgba(0,0,0,0.4)",
            justifyContent: "center",
            alignItems: "center",
            padding: 24,
          }}
        >
          <ScrollView
            style={{
              width: "100%",
              maxWidth: 600,
              backgroundColor: "#fff",
              borderRadius: 16,
              maxHeight: "90%",
            }}
            contentContainerStyle={{
              padding: 20,
              gap: 12,
            }}
            keyboardShouldPersistTaps="handled"
          >
            <Text style={{ fontSize: 22, fontWeight: "700", marginBottom: 10 }}>
              {editingId ? "Editar Cliente" : "Novo Cliente"}
            </Text>

            <TextInput
              style={s.formInput}
              placeholder="Nome *"
              placeholderTextColor={theme.colors.textSec}
              value={cliName}
              onChangeText={setCliName}
            />

            <TextInput
              style={s.formInput}
              placeholder="CNPJ / CPF *"
              placeholderTextColor={theme.colors.textSec}
              value={cliDoc}
              onChangeText={(v) => setCliDoc(maskDocument(v))}
              keyboardType="numeric"
            />

            <TextInput
              style={s.formInput}
              placeholder="Telefone *"
              placeholderTextColor={theme.colors.textSec}
              value={cliPhone}
              onChangeText={(v) => setCliPhone(maskPhoneBR(v))}
              keyboardType="phone-pad"
            />

            <TextInput
              style={s.formInput}
              placeholder="E-mail"
              placeholderTextColor={theme.colors.textSec}
              value={cliEmail}
              onChangeText={setCliEmail}
              keyboardType="email-address"
            />

            <TextInput
              style={s.formInput}
              placeholder="Empresa"
              placeholderTextColor={theme.colors.textSec}
              value={cliCompany}
              onChangeText={setCliCompany}
            />

            <TextInput
              style={s.formInput}
              placeholder="Cidade"
              placeholderTextColor={theme.colors.textSec}
              value={cliCity}
              onChangeText={setCliCity}
            />

            <TextInput
              style={s.formInput}
              placeholder="Estado"
              placeholderTextColor={theme.colors.textSec}
              value={cliState}
              onChangeText={setCliState}
            />

            <TextInput
              style={s.formInput}
              placeholder="Endereço"
              placeholderTextColor={theme.colors.textSec}
              value={cliAddress}
              onChangeText={setCliAddress}
            />

            <View
              style={{
                flexDirection: "row",
                justifyContent: "flex-end",
                gap: 10,
                marginTop: 10,
              }}
            >
              <TouchableOpacity
                onPress={() => {
                  setModalOpen(false);
                  setEditingId(null);
                  setCliName("");
                  setCliDoc("");
                  setCliPhone("");
                  setCliEmail("");
                  setCliCompany("");
                  setCliCity("");
                  setCliState("");
                  setCliAddress("");
                }}
                style={{ justifyContent: "center", paddingHorizontal: 10 }}
              >
                <Text style={{ color: theme.colors.textSec }}>Cancelar</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={s.saveBtn}
                onPress={saveClient}
                disabled={saving}
              >
                <Text style={s.saveBtnText}>
                  {saving ? "Salvando..." : "Salvar"}
                </Text>
              </TouchableOpacity>
            </View>
          </ScrollView>
        </View>
      </Modal>

      <View style={s.header}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>Clientes</Text>
            <Text style={s.subtitle}>
              {isDesktop ? `${openSummary}\n${historySummary}` : `${items.length} cliente(s) no histórico`}
            </Text>
          </View>
          {!isDesktop && (
            <TouchableOpacity
              style={s.newClientBtnMobile}
              onPress={() => {
                setEditingId(null);
                setCliName("");
                setCliDoc("");
                setCliPhone("");
                setCliEmail("");
                setCliCompany("");
                setCliCity("");
                setCliState("");
                setCliAddress("");
                setModalOpen(true);
              }}
              testID="new-client-mobile"
            >
              <Ionicons name="person-add" size={18} color="#fff" />
            </TouchableOpacity>
          )}
        </View>

        {isDesktop && (
          <View style={s.headerActions}>
            <TouchableOpacity
              style={s.newProposalBtn}
              onPress={() => router.push("/(tabs)/new")}
              testID="new-proposal"
            >
              <Ionicons name="add" size={18} color="#fff" />
              <Text style={s.newProposalText}>Nova Proposta</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={s.newClientBtn}
              onPress={() => {
                setEditingId(null);
                setCliName("");
                setCliDoc("");
                setCliPhone("");
                setCliEmail("");
                setCliCompany("");
                setCliCity("");
                setCliState("");
                setCliAddress("");
                setModalOpen(true);
              }}
              testID="new-client"
            >
              <Ionicons name="person-add" size={18} color="#fff" />
              <Text style={s.newProposalText}>Novo Cliente</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={theme.colors.primary} />
      ) : isDesktop ? (
        renderDesktop()
      ) : (
        renderMobile()
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.bg },
  header: { paddingHorizontal: 24, paddingTop: 12 },
  title: { fontSize: 28, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
  subtitle: { fontSize: 13, color: theme.colors.textSec, marginTop: 4 },
  list: { padding: 24, paddingBottom: 40, gap: 12 },
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 14,
    borderRadius: 16,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { color: "#fff", fontWeight: "800", fontSize: 16 },
  name: { fontSize: 15, fontWeight: "700", color: theme.colors.text },
  sub: { fontSize: 12, color: theme.colors.textSec, marginTop: 2 },
  row: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 8 },
  pill: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    backgroundColor: theme.colors.surfaceAlt,
    borderRadius: 999,
  },
  pillText: { fontSize: 11, color: theme.colors.textSec, fontWeight: "600" },
  total: { fontSize: 13, fontWeight: "700", color: theme.colors.text },
  date: { fontSize: 11, color: theme.colors.textMuted, marginTop: 4 },
  whats: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: theme.colors.whatsapp,
    alignItems: "center",
    justifyContent: "center",
  },
  desktopContainer: { padding: 24, gap: 20, paddingBottom: 120 },
  kpiRow: { flexDirection: "row", gap: 16, flexWrap: "wrap" },
  kpiCard: {
    flex: 1,
    minWidth: 200,
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
  colClient: { flex: 3, minWidth: 320 },
  colMedium: { flex: 2, minWidth: 180 },
  colSmall: { flex: 1, minWidth: 160 },
  colActions: { flex: 1.2, minWidth: 240 },
  tableClientName: { fontSize: 15, fontWeight: "700", color: theme.colors.text },
  tableSub: { fontSize: 12, color: theme.colors.textSec, marginTop: 4 },
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
  actionTextButtonLabel: { color: theme.colors.text, fontWeight: "700", fontSize: 12 },
  tableRowSelected: { backgroundColor: "#F8FAFC" },
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
  empty: { alignItems: "center", marginTop: 60, gap: 12 },
  emptyText: { color: theme.colors.textSec, textAlign: "center", paddingHorizontal: 32 },
  newClientBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 14,
    backgroundColor: theme.colors.primary,
  },
  newClientBtnMobile: {
    padding: 10,
    borderRadius: 14,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  newPropBtnMobile: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: theme.colors.accent,
    alignItems: "center",
    justifyContent: "center",
  },
  formInput: {
    minHeight: 50,
    width: "100%",
    paddingHorizontal: 18,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: "#fff",
    color: theme.colors.text,
  },
  saveBtn: {
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 14,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  saveBtnText: {
    color: "#fff",
    fontWeight: "700",
  },
});
