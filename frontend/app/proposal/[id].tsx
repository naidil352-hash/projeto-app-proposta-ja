import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { api, formatApiError } from "../../src/api";
import { theme, statusMeta, formatCurrency, formatDate, daysSince } from "../../src/theme";
import {
  generateProposalPdf,
  sharePdf,
  printPdf,
  openWhatsApp,
  followUpMessage,
  proposalShareMessage,
} from "../../src/pdf";
import UpgradeModal from "../../src/UpgradeModal";

export default function ProposalDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [p, setP] = useState<any>(null);
  const [company, setCompany] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [lostModal, setLostModal] = useState(false);
  const [lostReason, setLostReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [upgradeMsg, setUpgradeMsg] = useState<string | undefined>();

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [prop, comp] = await Promise.all([api.get(`/proposals/${id}`), api.get("/company")]);
      setP(prop.data);
      setCompany(comp.data);
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

  const changeStatus = async (status: string, reason?: string) => {
    try {
      setBusy(true);
      await api.patch(`/proposals/${id}/status`, {
        status,
        lost_reason: reason || null,
      });
      setLostModal(false);
      setLostReason("");
      await load();
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const onShare = async () => {
    try {
      setBusy(true);
      const uri = await generateProposalPdf(p, company);
      await sharePdf(uri);
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Falha ao gerar PDF");
    } finally {
      setBusy(false);
    }
  };

  const onPrint = async () => {
    try {
      setBusy(true);
      const uri = await generateProposalPdf(p, company);
      await printPdf(uri);
    } catch (e: any) {
      Alert.alert("Erro", e.message || "Falha ao imprimir");
    } finally {
      setBusy(false);
    }
  };

  const onWhats = () => {
    openWhatsApp(p.client_phone, proposalShareMessage(p, company));
  };

  const onFollowUp = () => {
    openWhatsApp(p.client_phone, followUpMessage(p.client_name));
  };

  const onDuplicate = async () => {
    try {
      setBusy(true);
      const { data } = await api.post(`/proposals/${id}/duplicate`);
      router.replace(`/proposal/${data.id}`);
    } catch (e: any) {
      if (e?.response?.status === 402) {
        setUpgradeMsg(e.response.data?.detail);
        setUpgradeOpen(true);
      } else {
        Alert.alert("Erro", formatApiError(e));
      }
    } finally {
      setBusy(false);
    }
  };

  const onDelete = () => {
    Alert.alert("Excluir proposta", "Tem certeza?", [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir",
        style: "destructive",
        onPress: async () => {
          try {
            await api.delete(`/proposals/${id}`);
            router.back();
          } catch (e) {
            Alert.alert("Erro", formatApiError(e));
          }
        },
      },
    ]);
  };

  if (loading || !p) {
    return (
      <SafeAreaView style={s.root}>
        <ActivityIndicator style={{ marginTop: 60 }} color={theme.colors.primary} />
      </SafeAreaView>
    );
  }

  const st = statusMeta[p.status];
  const stale = p.status === "aberto" && daysSince(p.created_at) >= 3;

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="proposal-detail">
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} style={s.back} testID="back-btn">
          <Ionicons name="chevron-back" size={24} color={theme.colors.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>#{p.id.slice(0, 8).toUpperCase()}</Text>
        <TouchableOpacity onPress={onDelete} testID="delete-proposal">
          <Ionicons name="trash-outline" size={22} color={theme.colors.danger} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={s.scroll}>
        <View style={[s.badge, { backgroundColor: st.bg, borderColor: st.border }]}>
          <Text style={[s.badgeText, { color: st.text }]}>{st.label}</Text>
        </View>

        {stale && (
          <View style={s.staleCard}>
            <Ionicons name="alarm" size={18} color={theme.colors.warn} />
            <Text style={s.staleText}>
              Aberto há {daysSince(p.created_at)} dias — hora de fazer um follow-up!
            </Text>
          </View>
        )}

        <View style={s.card}>
          <Text style={s.h1}>{p.client_name}</Text>
          <Text style={s.sub}>{p.client_document}</Text>
          <Text style={s.sub}>{p.client_phone}</Text>
        </View>

        <View style={s.card}>
          <Text style={s.sectionLabel}>Itens</Text>
          {p.products.map((pr: any, i: number) => (
            <View key={i} style={s.itemRow}>
              <View style={{ flex: 1 }}>
                <Text style={s.itemName}>{pr.name}</Text>
                <Text style={s.itemSub}>
                  {pr.quantity} × {formatCurrency(pr.price)}
                </Text>
              </View>
              <Text style={s.itemTotal}>{formatCurrency(pr.quantity * pr.price)}</Text>
            </View>
          ))}
          <View style={s.totalRow}>
            <Text style={s.totalLabel}>Total</Text>
            <Text style={s.totalValue}>{formatCurrency(p.total)}</Text>
          </View>
        </View>

        <View style={s.card}>
          <Text style={s.sectionLabel}>Prazo de embarque</Text>
          <Text style={s.itemName}>{p.shipping_deadline}</Text>
        </View>

        {p.notes ? (
          <View style={s.card}>
            <Text style={s.sectionLabel}>Observações</Text>
            <Text style={s.sub}>{p.notes}</Text>
          </View>
        ) : null}

        {p.status === "perdido" && p.lost_reason ? (
          <View style={[s.card, { borderColor: theme.colors.statusLostBorder }]}>
            <Text style={s.sectionLabel}>Motivo da perda</Text>
            <Text style={s.sub}>{p.lost_reason}</Text>
          </View>
        ) : null}

        <Text style={s.created}>Criado em {formatDate(p.created_at)}</Text>

        <Text style={s.sectionLabelBig}>Ações</Text>
        <View style={s.grid}>
          <ActionBtn testID="act-share" icon="share-outline" label="Enviar PDF" onPress={onShare} />
          <ActionBtn testID="act-print" icon="print-outline" label="Imprimir" onPress={onPrint} />
          <ActionBtn
            testID="act-whatsapp"
            icon="logo-whatsapp"
            label="WhatsApp"
            color={theme.colors.whatsapp}
            onPress={onWhats}
          />
          {p.status === "aberto" && (
            <ActionBtn
              testID="act-followup"
              icon="chatbubble-ellipses-outline"
              label="Follow-up IA"
              onPress={onFollowUp}
            />
          )}
          <ActionBtn
            testID="act-duplicate"
            icon="copy-outline"
            label="Duplicar"
            onPress={onDuplicate}
          />
        </View>

        {p.status === "aberto" && (
          <>
            <Text style={s.sectionLabelBig}>Atualizar status</Text>
            <View style={s.grid}>
              <TouchableOpacity
                style={[s.statBtn, { backgroundColor: theme.colors.statusWonText }]}
                onPress={() => changeStatus("realizado")}
                testID="status-won"
                disabled={busy}
              >
                <Ionicons name="checkmark-circle" size={20} color="#fff" />
                <Text style={s.statText}>Realizado</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.statBtn, { backgroundColor: theme.colors.statusLostText }]}
                onPress={() => setLostModal(true)}
                testID="status-lost"
                disabled={busy}
              >
                <Ionicons name="close-circle" size={20} color="#fff" />
                <Text style={s.statText}>Perdido</Text>
              </TouchableOpacity>
            </View>
          </>
        )}

        {p.status !== "aberto" && (
          <TouchableOpacity
            style={s.reopenBtn}
            onPress={() => changeStatus("aberto")}
            testID="status-reopen"
            disabled={busy}
          >
            <Ionicons name="refresh" size={20} color={theme.colors.text} />
            <Text style={s.reopenText}>Reabrir proposta</Text>
          </TouchableOpacity>
        )}
      </ScrollView>

      <Modal visible={lostModal} transparent animationType="fade" onRequestClose={() => setLostModal(false)}>
        <KeyboardAvoidingView
          style={s.modalRoot}
          behavior={Platform.OS === "ios" ? "padding" : undefined}
        >
          <View style={s.modalCard} testID="lost-modal">
            <Text style={s.modalTitle}>Por que a proposta foi perdida?</Text>
            <Text style={s.modalSub}>Obrigatório para ajudar a melhorar suas vendas</Text>
            <TextInput
              testID="lost-reason-input"
              style={s.modalInput}
              value={lostReason}
              onChangeText={setLostReason}
              placeholder="Ex: cliente escolheu concorrente"
              placeholderTextColor={theme.colors.textMuted}
              multiline
            />
            <View style={{ flexDirection: "row", gap: 8, marginTop: 16 }}>
              <TouchableOpacity style={s.modalCancel} onPress={() => setLostModal(false)}>
                <Text style={{ color: theme.colors.text, fontWeight: "700" }}>Cancelar</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="lost-confirm"
                style={[
                  s.modalConfirm,
                  (!lostReason.trim() || busy) && { opacity: 0.5 },
                ]}
                disabled={!lostReason.trim() || busy}
                onPress={() => changeStatus("perdido", lostReason.trim())}
              >
                <Text style={{ color: "#fff", fontWeight: "700" }}>Confirmar</Text>
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
      <UpgradeModal
        visible={upgradeOpen}
        message={upgradeMsg}
        onClose={() => setUpgradeOpen(false)}
      />
    </SafeAreaView>
  );
}

function ActionBtn({ icon, label, onPress, color, testID }: any) {
  return (
    <TouchableOpacity style={s.actBtn} onPress={onPress} testID={testID}>
      <View style={[s.actIcon, { backgroundColor: color || theme.colors.primary }]}>
        <Ionicons name={icon} size={20} color="#fff" />
      </View>
      <Text style={s.actText}>{label}</Text>
    </TouchableOpacity>
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
  scroll: { padding: 24, paddingBottom: 40, gap: 12 },
  badge: {
    alignSelf: "flex-start",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 999,
    borderWidth: 1,
  },
  badgeText: { fontSize: 12, fontWeight: "700" },
  staleCard: {
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
    backgroundColor: "#FFFBEB",
    borderWidth: 1,
    borderColor: "#FDE68A",
    padding: 12,
    borderRadius: 12,
  },
  staleText: { color: theme.colors.text, fontSize: 13, flex: 1 },
  card: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 16,
    borderRadius: 16,
    gap: 4,
  },
  h1: { fontSize: 22, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
  sub: { color: theme.colors.textSec, fontSize: 14 },
  sectionLabel: {
    fontSize: 11,
    color: theme.colors.textMuted,
    fontWeight: "700",
    letterSpacing: 1,
    textTransform: "uppercase",
    marginBottom: 8,
  },
  sectionLabelBig: {
    fontSize: 11,
    color: theme.colors.textMuted,
    fontWeight: "700",
    letterSpacing: 1,
    textTransform: "uppercase",
    marginTop: 12,
    marginBottom: 4,
  },
  itemRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
  },
  itemName: { fontWeight: "600", color: theme.colors.text },
  itemSub: { fontSize: 12, color: theme.colors.textSec },
  itemTotal: { fontWeight: "700", color: theme.colors.text },
  totalRow: {
    marginTop: 8,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    flexDirection: "row",
    justifyContent: "space-between",
  },
  totalLabel: { fontWeight: "700", color: theme.colors.textSec },
  totalValue: { fontWeight: "800", fontSize: 18, color: theme.colors.text },
  created: { fontSize: 12, color: theme.colors.textMuted, textAlign: "center", marginTop: 4 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  actBtn: {
    width: "48.5%",
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 14,
    borderRadius: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  actIcon: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  actText: { fontWeight: "700", color: theme.colors.text, flex: 1 },
  statBtn: {
    flex: 1,
    minWidth: "48%",
    height: 52,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    borderRadius: 12,
  },
  statText: { color: "#fff", fontWeight: "700" },
  reopenBtn: {
    marginTop: 8,
    height: 52,
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 12,
  },
  reopenText: { color: theme.colors.text, fontWeight: "700" },
  modalRoot: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "center", padding: 24 },
  modalCard: { backgroundColor: "#fff", borderRadius: 16, padding: 20 },
  modalTitle: { fontSize: 18, fontWeight: "800", color: theme.colors.text },
  modalSub: { color: theme.colors.textSec, fontSize: 13, marginTop: 4, marginBottom: 12 },
  modalInput: {
    minHeight: 80,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 12,
    fontSize: 15,
    color: theme.colors.text,
    textAlignVertical: "top",
  },
  modalCancel: {
    flex: 1,
    height: 48,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: theme.colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  modalConfirm: {
    flex: 1,
    height: 48,
    borderRadius: 12,
    backgroundColor: theme.colors.statusLostText,
    alignItems: "center",
    justifyContent: "center",
  },
});
