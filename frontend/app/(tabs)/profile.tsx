import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Image,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { useFocusEffect } from "expo-router";
import { api, formatApiError } from "../../src/api";
import { theme } from "../../src/theme";
import { useAuth } from "../../src/auth";

export default function Profile() {
  const { user, logout } = useAuth();
  const [companyName, setCompanyName] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");
  const [logo, setLogo] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await api.get("/company");
      setCompanyName(data.company_name || "");
      setCnpj(data.cnpj || "");
      setPhone(data.phone || "");
      setEmail(data.email || "");
      setAddress(data.address || "");
      setLogo(data.logo_base64 || "");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const pickLogo = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert("Permissão", "Permita o acesso à galeria para adicionar a logo.");
      return;
    }
    const r = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      base64: true,
      quality: 0.8,
      allowsEditing: true,
      aspect: [1, 1],
    });
    if (!r.canceled && r.assets?.[0]?.base64) {
      const a = r.assets[0];
      setLogo(`data:${a.mimeType || "image/jpeg"};base64,${a.base64}`);
    }
  };

  const save = async () => {
    try {
      setSaving(true);
      await api.put("/company", {
        company_name: companyName,
        cnpj,
        phone,
        email,
        address,
        logo_base64: logo,
      });
      Alert.alert("Pronto!", "Dados da empresa salvos.");
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={s.root}>
        <ActivityIndicator style={{ marginTop: 60 }} color={theme.colors.primary} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="profile-screen">
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
          <View style={s.header}>
            <View>
              <Text style={s.title}>Minha empresa</Text>
              <Text style={s.subtitle}>Aparecerá no topo do PDF</Text>
            </View>
          </View>

          <TouchableOpacity style={s.logoWrap} onPress={pickLogo} testID="pick-logo">
            {logo ? (
              <Image source={{ uri: logo }} style={s.logo} />
            ) : (
              <View style={s.logoPh}>
                <Ionicons name="image-outline" size={28} color={theme.colors.textMuted} />
                <Text style={s.logoPhText}>Toque para adicionar logo</Text>
              </View>
            )}
          </TouchableOpacity>

          <Input testID="inp-company-name" label="Nome da empresa" value={companyName} onChangeText={setCompanyName} />
          <Input testID="inp-company-cnpj" label="CNPJ" value={cnpj} onChangeText={setCnpj} keyboardType="number-pad" />
          <Input testID="inp-company-phone" label="Telefone" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
          <Input testID="inp-company-email" label="Email" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
          <Input testID="inp-company-address" label="Endereço" value={address} onChangeText={setAddress} multiline />

          <TouchableOpacity
            testID="save-company"
            style={[s.cta, saving && { opacity: 0.7 }]}
            onPress={save}
            disabled={saving}
          >
            {saving ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Ionicons name="save-outline" size={20} color="#fff" />
                <Text style={s.ctaText}>Salvar</Text>
              </>
            )}
          </TouchableOpacity>

          <View style={s.divider} />

          <View style={s.userCard}>
            <Text style={s.userLabel}>Conta</Text>
            <Text style={s.userName}>{user?.name}</Text>
            <Text style={s.userEmail}>{user?.email}</Text>
          </View>
          <TouchableOpacity style={s.logout} onPress={logout} testID="logout-button">
            <Ionicons name="log-out-outline" size={20} color={theme.colors.danger} />
            <Text style={s.logoutText}>Sair da conta</Text>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
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
  scroll: { padding: 24, paddingBottom: 40, gap: 12 },
  header: { marginBottom: 4 },
  title: { fontSize: 28, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
  subtitle: { fontSize: 13, color: theme.colors.textSec, marginTop: 4 },
  logoWrap: { alignItems: "center", marginVertical: 12 },
  logo: { width: 112, height: 112, borderRadius: 16, borderWidth: 1, borderColor: theme.colors.border },
  logoPh: {
    width: 112,
    height: 112,
    borderRadius: 16,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderStyle: "dashed",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    padding: 8,
  },
  logoPhText: { fontSize: 11, color: theme.colors.textMuted, textAlign: "center" },
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
  cta: {
    height: 56,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    marginTop: 16,
  },
  ctaText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  divider: { height: 1, backgroundColor: theme.colors.border, marginVertical: 16 },
  userCard: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 16,
    borderRadius: 14,
    gap: 2,
  },
  userLabel: {
    fontSize: 11,
    color: theme.colors.textMuted,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 1,
    marginBottom: 4,
  },
  userName: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
  userEmail: { fontSize: 13, color: theme.colors.textSec },
  logout: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingVertical: 14,
  },
  logoutText: { color: theme.colors.danger, fontWeight: "700" },
});
