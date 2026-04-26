import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { api, formatApiError } from "../../src/api";
import { theme, formatCurrency } from "../../src/theme";
import {
  maskDocument,
  maskPhoneBR,
  maskCurrency,
  parseCurrency,
  parseNumber,
} from "../../src/masks";
import UpgradeModal from "../../src/UpgradeModal";

type Product = { name: string; quantity: string; price: string };

export default function NewProposal() {
  const router = useRouter();
  const [clientName, setClientName] = useState("");
  const [doc, setDoc] = useState("");
  const [phone, setPhone] = useState("");
  const [deadline, setDeadline] = useState("");
  const [notes, setNotes] = useState("");
  const [discount, setDiscount] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("");
  const [validity, setValidity] = useState("15");
  const [products, setProducts] = useState<Product[]>([{ name: "", quantity: "", price: "" }]);
  const [saving, setSaving] = useState(false);
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [upgradeMsg, setUpgradeMsg] = useState<string | undefined>();

  const addProduct = () => setProducts([...products, { name: "", quantity: "", price: "" }]);
  const removeProduct = (i: number) => {
    if (products.length === 1) return;
    setProducts(products.filter((_, idx) => idx !== i));
  };
  const updateProduct = (i: number, key: keyof Product, value: string) => {
    setProducts(products.map((p, idx) => (idx === i ? { ...p, [key]: value } : p)));
  };

  const subtotal = products.reduce(
    (acc, p) => acc + (parseNumber(p.quantity) || 0) * (parseCurrency(p.price) || 0),
    0
  );
  const discountNum = parseCurrency(discount);
  const total = Math.max(subtotal - discountNum, 0);

  const reset = () => {
    setClientName("");
    setDoc("");
    setPhone("");
    setDeadline("");
    setNotes("");
    setDiscount("");
    setPaymentTerms("");
    setValidity("15");
    setProducts([{ name: "", quantity: "", price: "" }]);
  };

  const submit = async () => {
    if (!clientName || !doc || !phone || !deadline) {
      Alert.alert("Atenção", "Preencha cliente, CNPJ/CPF, telefone e prazo.");
      return;
    }
    const cleanProducts = products
      .filter((p) => p.name.trim())
      .map((p) => ({
        name: p.name.trim(),
        quantity: parseNumber(p.quantity),
        price: parseCurrency(p.price),
      }));
    if (!cleanProducts.length) {
      Alert.alert("Atenção", "Adicione pelo menos 1 produto.");
      return;
    }
    try {
      setSaving(true);
      const { data } = await api.post("/proposals", {
        client_name: clientName.trim(),
        client_document: doc.trim(),
        client_phone: phone.trim(),
        products: cleanProducts,
        shipping_deadline: deadline.trim(),
        notes: notes.trim(),
        discount: discountNum,
        payment_terms: paymentTerms.trim(),
        validity_days: parseInt(validity || "15", 10) || 15,
      });
      reset();
      router.push(`/proposal/${data.id}`);
    } catch (e: any) {
      if (e?.response?.status === 402) {
        setUpgradeMsg(e.response.data?.detail);
        setUpgradeOpen(true);
      } else {
        Alert.alert("Erro", formatApiError(e));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="new-proposal-screen">
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={{ flex: 1 }}
      >
        <View style={s.header}>
          <Text style={s.title}>Nova proposta</Text>
          <Text style={s.subtitle}>Preencha rápido e envie no WhatsApp</Text>
        </View>
        <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
          <Section title="Cliente">
            <Input testID="inp-client-name" label="Nome *" value={clientName} onChangeText={setClientName} placeholder="Nome do cliente" />
            <Input
              testID="inp-client-doc"
              label="CNPJ / CPF *"
              value={doc}
              onChangeText={(v: string) => setDoc(maskDocument(v))}
              keyboardType="number-pad"
              placeholder="000.000.000-00"
            />
            <Input
              testID="inp-client-phone"
              label="Telefone *"
              value={phone}
              onChangeText={(v: string) => setPhone(maskPhoneBR(v))}
              keyboardType="phone-pad"
              placeholder="(11) 99999-9999"
            />
          </Section>

          <Section
            title="Itens"
            right={
              <TouchableOpacity onPress={addProduct} testID="add-product">
                <Text style={s.link}>+ Adicionar</Text>
              </TouchableOpacity>
            }
          >
            {products.map((p, i) => (
              <View key={i} style={s.product} testID={`product-row-${i}`}>
                <View style={s.productHeader}>
                  <Text style={s.productHeaderText}>Item {i + 1}</Text>
                  {products.length > 1 && (
                    <TouchableOpacity onPress={() => removeProduct(i)} testID={`rm-product-${i}`}>
                      <Ionicons name="trash-outline" size={18} color={theme.colors.danger} />
                    </TouchableOpacity>
                  )}
                </View>
                <Input
                  testID={`inp-product-name-${i}`}
                  label="Produto"
                  value={p.name}
                  onChangeText={(v: string) => updateProduct(i, "name", v)}
                  placeholder="Nome do produto"
                />
                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Input
                      testID={`inp-product-qty-${i}`}
                      label="Qtd"
                      value={p.quantity}
                      onChangeText={(v: string) => updateProduct(i, "quantity", v.replace(/[^0-9,.]/g, ""))}
                      keyboardType="numeric"
                      placeholder="0"
                    />
                  </View>
                  <View style={{ flex: 1.4 }}>
                    <Input
                      testID={`inp-product-price-${i}`}
                      label="Preço un."
                      value={p.price}
                      onChangeText={(v: string) => updateProduct(i, "price", maskCurrency(v))}
                      keyboardType="numeric"
                      placeholder="0,00"
                    />
                  </View>
                </View>
              </View>
            ))}
          </Section>

          <Section title="Condições">
            <Input
              testID="inp-deadline"
              label="Prazo de embarque *"
              value={deadline}
              onChangeText={setDeadline}
              placeholder="Ex: 15 dias úteis"
            />
            <Input
              testID="inp-payment-terms"
              label="Condições de pagamento"
              value={paymentTerms}
              onChangeText={setPaymentTerms}
              placeholder="Ex: 30/60/90 dias, Pix à vista"
            />
            <View style={{ flexDirection: "row", gap: 8 }}>
              <View style={{ flex: 1 }}>
                <Input
                  testID="inp-discount"
                  label="Desconto (R$)"
                  value={discount}
                  onChangeText={(v: string) => setDiscount(maskCurrency(v))}
                  keyboardType="numeric"
                  placeholder="0,00"
                />
              </View>
              <View style={{ flex: 1 }}>
                <Input
                  testID="inp-validity"
                  label="Validade (dias)"
                  value={validity}
                  onChangeText={(v: string) => setValidity(v.replace(/\D/g, "").slice(0, 3))}
                  keyboardType="number-pad"
                  placeholder="15"
                />
              </View>
            </View>
            <Input
              testID="inp-notes"
              label="Observações"
              value={notes}
              onChangeText={setNotes}
              placeholder="Opcional"
              multiline
            />
          </Section>

          <View style={s.totalBox} testID="total-preview">
            <View style={{ flex: 1 }}>
              <Text style={s.totalLabel}>Subtotal</Text>
              <Text style={s.subValue}>{formatCurrency(subtotal)}</Text>
              {discountNum > 0 && (
                <Text style={s.subValue}>- {formatCurrency(discountNum)} desconto</Text>
              )}
            </View>
            <View style={{ alignItems: "flex-end" }}>
              <Text style={s.totalLabel}>Total</Text>
              <Text style={s.totalValue}>{formatCurrency(total)}</Text>
            </View>
          </View>
        </ScrollView>

        <View style={s.bottom}>
          <TouchableOpacity
            testID="submit-proposal"
            style={[s.cta, saving && { opacity: 0.7 }]}
            onPress={submit}
            disabled={saving}
          >
            {saving ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Ionicons name="checkmark-circle" size={22} color="#fff" />
                <Text style={s.ctaText}>Criar proposta</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
      <UpgradeModal
        visible={upgradeOpen}
        message={upgradeMsg}
        onClose={() => setUpgradeOpen(false)}
      />
    </SafeAreaView>
  );
}

function Section({ title, right, children }: any) {
  return (
    <View style={s.section}>
      <View style={s.sectionHead}>
        <Text style={s.sectionTitle}>{title}</Text>
        {right}
      </View>
      <View style={{ gap: 10 }}>{children}</View>
    </View>
  );
}

function Input({ label, testID, ...props }: any) {
  return (
    <View style={{ gap: 6 }}>
      <Text style={s.label}>{label}</Text>
      <TextInput
        {...props}
        testID={testID}
        style={[s.input, props.multiline && { height: 80, paddingTop: 12, textAlignVertical: "top" }]}
        placeholderTextColor={theme.colors.textMuted}
      />
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.bg },
  header: { paddingHorizontal: 24, paddingTop: 12 },
  title: { fontSize: 28, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
  subtitle: { fontSize: 13, color: theme.colors.textSec, marginTop: 4 },
  scroll: { padding: 24, paddingBottom: 120, gap: 16 },
  section: { gap: 10 },
  sectionHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sectionTitle: {
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.textMuted,
    letterSpacing: 1.5,
    textTransform: "uppercase",
  },
  link: { color: theme.colors.text, fontWeight: "700", fontSize: 14 },
  label: {
    fontSize: 11,
    color: theme.colors.textMuted,
    fontWeight: "700",
    letterSpacing: 0.5,
    textTransform: "uppercase",
  },
  input: {
    height: 52,
    borderRadius: 12,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    paddingHorizontal: 14,
    fontSize: 16,
    color: theme.colors.text,
  },
  product: {
    padding: 14,
    backgroundColor: "#F1F5F9",
    borderRadius: 14,
    gap: 10,
  },
  productHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  productHeaderText: { fontWeight: "700", color: theme.colors.text },
  totalBox: {
    marginTop: 8,
    padding: 20,
    backgroundColor: theme.colors.primary,
    borderRadius: 16,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
  },
  totalLabel: { color: "#94A3B8", fontSize: 11, letterSpacing: 1.5, textTransform: "uppercase", fontWeight: "700" },
  totalValue: { color: "#fff", fontSize: 26, fontWeight: "800", letterSpacing: -0.5, marginTop: 4 },
  subValue: { color: "rgba(255,255,255,0.7)", fontSize: 14, marginTop: 4 },
  bottom: { position: "absolute", left: 16, right: 16, bottom: 16 },
  cta: {
    height: 56,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "700" },
});
