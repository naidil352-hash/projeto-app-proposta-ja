import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  useWindowDimensions,
  Linking,
  Image,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { api, formatApiError } from "../../../src/api";
import { theme, formatCurrency, formatDate, getRoleLabel } from "../../../src/theme";
import { Ionicons } from "@expo/vector-icons";

type Proposal = {
  id: string;
  client_name: string;
  client_document: string;
  client_phone: string;
  products: any[];
  shipping_deadline: string;
  notes?: string;
  status: string;
  total: number;
  grand_total?: number;
  subtotal?: number;
  discount?: number;
  payment_terms?: string;
  validity_days?: number;
  created_at: string;
  seller_name?: string;
  seller_email?: string;
  seller_phone?: string;
  seller_whatsapp?: string;
  seller_role?: string;
  acceptance_status?: string;
  accept_name?: string;
  accept_document?: string;
  accept_role?: string;
  accept_date?: string;
  accept_ip?: string;
  accept_device?: string;
};

type Company = {
  company_name?: string;
  cnpj?: string;
  phone?: string;
  email?: string;
  address?: string;
  logo_base64?: string;
};

const getValidityDateStr = (createdAtStr: string, validityDays?: number) => {
  if (!validityDays) return "";
  try {
    const d = new Date(createdAtStr);
    d.setDate(d.getDate() + validityDays);
    return d.toLocaleDateString("pt-BR");
  } catch (e) {
    return "";
  }
};

export default function PublicAccept() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 900;

  const [p, setP] = useState<Proposal | null>(null);
  const [company, setCompany] = useState<Company | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  // Form states
  const [name, setName] = useState("");
  const [document, setDocument] = useState("");
  const [role, setRole] = useState("");
  const [termsAccepted, setTermsAccepted] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await api.get(`/public/proposals/${id}`);
      setP(data.proposal);
      setCompany(data.company);
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [id]);

  React.useEffect(() => {
    load();
  }, [load]);

  const handleResponse = async (accepted: boolean) => {
    if (accepted) {
      if (!name.trim()) return Alert.alert("Atenção", "Por favor, digite seu nome completo.");
      if (!document.trim()) return Alert.alert("Atenção", "Por favor, digite seu CPF/CNPJ.");
      if (!role.trim()) return Alert.alert("Atenção", "Por favor, digite seu cargo.");
      if (!termsAccepted) return Alert.alert("Atenção", "Você precisa aceitar os termos da proposta.");
    }

    try {
      setBusy(true);
      const { data } = await api.post(`/proposals/${id}/accept`, {
        name: name.trim(),
        document: document.trim(),
        role: role.trim(),
        accepted,
      });
      setP(data);
      Alert.alert(
        "Sucesso",
        accepted ? "Proposta aceita com sucesso!" : "Proposta recusada."
      );
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <View style={s.center}>
        <ActivityIndicator size="large" color={theme.colors.primary} />
      </View>
    );
  }

  if (!p) {
    return (
      <View style={s.center}>
        <Ionicons name="alert-circle-outline" size={48} color={theme.colors.danger} />
        <Text style={s.errorText}>Proposta não encontrada.</Text>
      </View>
    );
  }

  const subtotal = p.subtotal ?? p.total;
  const isFinalized = p.acceptance_status === "accepted" || p.acceptance_status === "rejected";

  return (
    <ScrollView contentContainerStyle={s.scroll}>
      <View style={[s.container, isDesktop && s.desktopWidth]}>
        
        {/* Header da Empresa */}
        <View style={s.headerCard}>
          {company?.logo_base64 ? (
            <Image
              source={{
                uri: company.logo_base64.startsWith("data:")
                  ? company.logo_base64
                  : `data:image/png;base64,${company.logo_base64}`,
              }}
              style={s.companyLogo}
              testID="company-logo"
            />
          ) : null}
          <Text style={s.companyName}>{company?.company_name || "Sua Empresa"}</Text>
          {company?.cnpj ? <Text style={s.companyMeta}>CNPJ: {company.cnpj}</Text> : null}
          {company?.phone || company?.email ? (
            <Text style={s.companyMeta}>
              {company.phone} {company.phone && company.email ? "·" : ""} {company.email}
            </Text>
          ) : null}
          <View style={s.divider} />
          <View style={s.metaRow}>
            <View>
              <Text style={s.metaLabel}>PROPOSTA</Text>
              <Text style={s.metaVal}>#{p.id.slice(0, 8).toUpperCase()}</Text>
            </View>
            <View>
              <Text style={s.metaLabel}>EMISSÃO</Text>
              <Text style={s.metaVal}>{formatDate(p.created_at)}</Text>
            </View>
            {p.validity_days ? (
              <View>
                <Text style={s.metaLabel}>VALIDADE</Text>
                <Text style={s.metaVal}>{getValidityDateStr(p.created_at, p.validity_days)}</Text>
              </View>
            ) : null}
          </View>
        </View>

        {/* Cliente */}
        <View style={s.card}>
          <Text style={s.sectionTitle}>Cliente</Text>
          <Text style={s.clientName}>{p.client_name}</Text>
          <Text style={s.clientMeta}>CPF/CNPJ: {p.client_document} · Tel: {p.client_phone}</Text>
        </View>

        {/* Produtos/Serviços */}
        <View style={s.card}>
          <Text style={s.sectionTitle}>Itens da Proposta</Text>
          {p.products?.map((item, idx) => (
            <View key={idx} style={s.itemRow}>
              <View style={{ flex: 1 }}>
                <Text style={s.itemName}>{item.name}</Text>
                {item.description ? <Text style={s.itemDesc}>{item.description}</Text> : null}
                <Text style={s.itemQty}>
                  {item.quantity} {item.unit || "UN"} x {formatCurrency(item.unit_price || item.price || 0)}
                </Text>
              </View>
              <Text style={s.itemTotal}>
                {formatCurrency(item.total || ((item.quantity || 0) * (item.unit_price || item.price || 0)))}
              </Text>
            </View>
          ))}
          <View style={s.divider} />
          <View style={s.summaryRow}>
            <Text style={s.summaryLabel}>Subtotal</Text>
            <Text style={s.summaryValue}>{formatCurrency(subtotal)}</Text>
          </View>
          {p.discount && p.discount > 0 ? (
            <View style={s.summaryRow}>
              <Text style={s.summaryLabel}>Desconto</Text>
              <Text style={[s.summaryValue, { color: theme.colors.danger }]}>- {formatCurrency(p.discount)}</Text>
            </View>
          ) : null}
          <View style={[s.summaryRow, s.grandTotalRow]}>
            <Text style={s.grandTotalLabel}>Total Geral</Text>
            <Text style={s.grandTotalValue}>{formatCurrency(p.grand_total ?? p.total)}</Text>
          </View>
        </View>

        {/* Consultor Comercial */}
        {p.seller_name ? (
          <View style={s.card}>
            <Text style={s.sectionTitle}>Consultor Comercial</Text>
            <Text style={s.sellerName}>{p.seller_name}</Text>
            {p.seller_role ? <Text style={s.sellerMeta}>Cargo: {getRoleLabel(p.seller_role)}</Text> : null}
            {p.seller_phone ? <Text style={s.sellerMeta}>Telefone: {p.seller_phone}</Text> : null}
            {p.seller_email ? <Text style={s.sellerMeta}>E-mail: {p.seller_email}</Text> : null}
            {p.seller_whatsapp ? (
              <TouchableOpacity
                style={s.whatsappBtn}
                onPress={() => {
                  const cleaned = p.seller_whatsapp!.replace(/\D/g, "");
                  const phoneWithCountry = cleaned.startsWith("55") ? cleaned : `55${cleaned}`;
                  Linking.openURL(`https://wa.me/${phoneWithCountry}`);
                }}
                testID="btn-whatsapp"
              >
                <Ionicons name="logo-whatsapp" size={16} color="#fff" />
                <Text style={s.whatsappBtnText}>FALAR COM O CONSULTOR</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        ) : null}

        {/* Status de Aceite Finalizado */}
        {isFinalized ? (
          <View style={[s.card, p.acceptance_status === "accepted" ? s.acceptedCard : s.rejectedCard]}>
            <View style={s.rowAlign}>
              <Text style={[s.statusTitle, { color: p.acceptance_status === "accepted" ? theme.colors.success : theme.colors.danger, marginBottom: 4 }]} testID="status-title">
                {p.acceptance_status === "accepted" ? "✅ Proposta aceita com sucesso." : "❌ Proposta recusada."}
              </Text>
            </View>
            {p.acceptance_status === "accepted" ? (
              <Text style={{ fontSize: 14, color: theme.colors.textSec, marginBottom: 4 }}>
                Obrigado pela confiança.
              </Text>
            ) : null}
            <Text style={{ fontSize: 14, color: theme.colors.textSec, marginBottom: 12 }}>
              Seu consultor comercial foi notificado.
            </Text>
            {p.acceptance_status === "accepted" ? (
              <View style={s.evidenceBox} testID="evidence-box">
                <Text style={s.evidenceText}><Text style={{ fontWeight: "700" }}>Assinado por:</Text> {p.accept_name || "-"}</Text>
                <Text style={s.evidenceText}><Text style={{ fontWeight: "700" }}>Documento:</Text> {p.accept_document || "-"}</Text>
                <Text style={s.evidenceText}><Text style={{ fontWeight: "700" }}>Cargo:</Text> {p.accept_role || "-"}</Text>
                <Text style={s.evidenceText}><Text style={{ fontWeight: "700" }}>Data/Hora:</Text> {formatDate(p.accept_date || "")}</Text>
                <Text style={s.evidenceText}><Text style={{ fontWeight: "700" }}>IP de registro:</Text> {p.accept_ip || "-"}</Text>
                <Text style={s.evidenceText}><Text style={{ fontWeight: "700" }}>Dispositivo:</Text> {p.accept_device || "-"}</Text>
              </View>
            ) : null}
            {p.seller_whatsapp ? (
              <TouchableOpacity
                style={[s.whatsappBtn, { marginTop: 16, width: "100%", alignSelf: "stretch" }]}
                onPress={() => {
                  const cleaned = p.seller_whatsapp!.replace(/\D/g, "");
                  const phoneWithCountry = cleaned.startsWith("55") ? cleaned : `55${cleaned}`;
                  Linking.openURL(`https://wa.me/${phoneWithCountry}`);
                }}
                testID="btn-finalized-whatsapp"
              >
                <Ionicons name="logo-whatsapp" size={16} color="#fff" />
                <Text style={s.whatsappBtnText}>FALAR COM CONSULTOR</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        ) : (
          /* Form de Aceite */
          <View style={s.card} testID="aceite-comercial-section">
            <Text style={s.sectionTitle}>Aceite Comercial</Text>
            <Text style={s.inputLabel}>Nome completo *</Text>
            <TextInput
              style={s.input}
              placeholder="Ex: João da Silva"
              value={name}
              onChangeText={setName}
              testID="accept-input-name"
            />

            <Text style={s.inputLabel}>CPF/CNPJ *</Text>
            <TextInput
              style={s.input}
              placeholder="Ex: 000.000.000-00"
              value={document}
              onChangeText={setDocument}
              testID="accept-input-document"
            />

            <Text style={s.inputLabel}>Cargo *</Text>
            <TextInput
              style={s.input}
              placeholder="Ex: Diretor Financeiro"
              value={role}
              onChangeText={setRole}
              testID="accept-input-role"
            />

            <TouchableOpacity
              style={s.checkboxContainer}
              onPress={() => setTermsAccepted(!termsAccepted)}
              testID="accept-checkbox-terms"
            >
              <Ionicons
                name={termsAccepted ? "checkbox" : "square-outline"}
                size={22}
                color={termsAccepted ? theme.colors.primary : "#64748B"}
              />
              <Text style={s.checkboxText}>Li e concordo com os termos desta proposta.</Text>
            </TouchableOpacity>

            <View style={s.btnRow}>
              <TouchableOpacity
                style={[s.btn, s.btnAccept, busy && s.btnDisabled]}
                onPress={() => handleResponse(true)}
                disabled={busy}
                testID="btn-submit-accept"
              >
                {busy ? <ActivityIndicator color="#fff" /> : <Text style={s.btnText}>ACEITAR PROPOSTA</Text>}
              </TouchableOpacity>
              
              <TouchableOpacity
                style={[s.btn, s.btnReject, busy && s.btnDisabled]}
                onPress={() => handleResponse(false)}
                disabled={busy}
                testID="btn-submit-reject"
              >
                {busy ? <ActivityIndicator color="#fff" /> : <Text style={[s.btnText, { color: theme.colors.danger }]}>RECUSAR PROPOSTA</Text>}
              </TouchableOpacity>
            </View>
          </View>
        )}
      </View>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: theme.colors.bg },
  scroll: { paddingVertical: 24, paddingHorizontal: 16, backgroundColor: theme.colors.bg },
  container: { width: "100%", alignSelf: "center", gap: 16 },
  desktopWidth: { maxWidth: 640 },
  errorText: { marginTop: 12, fontSize: 16, color: theme.colors.textSec },
  headerCard: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 16,
    padding: 20,
  },
  companyLogo: { width: 120, height: 60, resizeMode: "contain", marginBottom: 12 },
  companyName: { fontSize: 22, fontWeight: "800", color: theme.colors.text },
  companyMeta: { fontSize: 13, color: theme.colors.textSec, marginTop: 4 },
  divider: { height: 1, backgroundColor: theme.colors.border, marginVertical: 16 },
  metaRow: { flexDirection: "row", justifyContent: "space-between" },
  metaLabel: { fontSize: 11, fontWeight: "700", color: theme.colors.textMuted, letterSpacing: 1 },
  metaVal: { fontSize: 14, fontWeight: "700", color: theme.colors.text, marginTop: 2 },
  card: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 16,
    padding: 20,
  },
  sectionTitle: { fontSize: 15, fontWeight: "800", color: theme.colors.text, marginBottom: 12, textTransform: "uppercase", letterSpacing: 0.5 },
  clientName: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
  clientMeta: { fontSize: 13, color: theme.colors.textSec, marginTop: 4 },
  itemRow: { flexDirection: "row", justifyContent: "space-between", marginVertical: 8 },
  itemName: { fontSize: 14, fontWeight: "700", color: theme.colors.text },
  itemDesc: { fontSize: 12, color: theme.colors.textSec, marginTop: 2 },
  itemQty: { fontSize: 12, color: theme.colors.textMuted, marginTop: 2 },
  itemTotal: { fontSize: 14, fontWeight: "700", color: theme.colors.text },
  summaryRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
  summaryLabel: { fontSize: 13, color: theme.colors.textSec },
  summaryValue: { fontSize: 13, color: theme.colors.text, fontWeight: "600" },
  grandTotalRow: { borderTopWidth: 1, borderTopColor: theme.colors.border, marginTop: 8, paddingTop: 8 },
  grandTotalLabel: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
  grandTotalValue: { fontSize: 20, fontWeight: "800", color: theme.colors.primary },
  sellerName: { fontSize: 15, fontWeight: "700", color: theme.colors.text },
  sellerMeta: { fontSize: 13, color: theme.colors.textSec, marginTop: 4 },
  acceptedCard: { borderColor: theme.colors.success, backgroundColor: "#F0FDF4" },
  rejectedCard: { borderColor: theme.colors.danger, backgroundColor: "#FEF2F2" },
  rowAlign: { flexDirection: "row", alignItems: "center", gap: 8 },
  statusTitle: { fontSize: 16, fontWeight: "800" },
  evidenceBox: { marginTop: 12, padding: 12, backgroundColor: "rgba(255,255,255,0.7)", borderRadius: 8, borderWidth: 1, borderColor: "rgba(0,0,0,0.05)", gap: 4 },
  evidenceText: { fontSize: 13, color: theme.colors.text },
  inputLabel: { fontSize: 13, fontWeight: "600", color: theme.colors.textSec, marginBottom: 6, marginTop: 10 },
  input: { height: 44, borderWidth: 1, borderColor: theme.colors.border, borderRadius: 8, paddingHorizontal: 12, fontSize: 14, color: theme.colors.text, backgroundColor: "#F8FAFC" },
  checkboxContainer: { flexDirection: "row", alignItems: "center", gap: 8, marginVertical: 16 },
  checkboxText: { fontSize: 13, color: theme.colors.textSec, flex: 1 },
  btnRow: { flexDirection: "row", gap: 12, marginTop: 12 },
  btn: { flex: 1, height: 44, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  btnAccept: { backgroundColor: theme.colors.primary },
  btnReject: { backgroundColor: "#fff", borderWidth: 1, borderColor: theme.colors.danger },
  btnText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  btnDisabled: { opacity: 0.6 },
  whatsappBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#25D366",
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 12,
    marginTop: 12,
    gap: 8,
    alignSelf: "flex-start",
  },
  whatsappBtnText: {
    color: "#fff",
    fontWeight: "700",
    fontSize: 13,
  },
});
