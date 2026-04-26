import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  ActivityIndicator,
  Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Link } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "../../src/auth";
import { theme } from "../../src/theme";

export default function Register() {
  const { register } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async () => {
    if (!name || !email || password.length < 6) {
      Alert.alert("Atenção", "Preencha nome, email e senha (mín. 6 caracteres)");
      return;
    }
    try {
      setLoading(true);
      await register(name.trim(), email.trim(), password);
    } catch (e: any) {
      Alert.alert("Erro", e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={s.root} testID="register-screen">
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={{ flex: 1 }}
      >
        <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
          <View style={s.brand}>
            <View style={s.logo}>
              <Ionicons name="flash" size={28} color="#fff" />
            </View>
            <Text style={s.brandText}>Criar conta</Text>
            <Text style={s.subtitle}>Comece a fechar mais em minutos</Text>
          </View>

          <View style={s.form}>
            <Text style={s.label}>Nome</Text>
            <TextInput
              testID="register-name"
              style={s.input}
              placeholder="Seu nome"
              placeholderTextColor={theme.colors.textMuted}
              value={name}
              onChangeText={setName}
            />
            <Text style={s.label}>Email</Text>
            <TextInput
              testID="register-email"
              style={s.input}
              placeholder="seu@email.com"
              placeholderTextColor={theme.colors.textMuted}
              autoCapitalize="none"
              keyboardType="email-address"
              value={email}
              onChangeText={setEmail}
            />
            <Text style={s.label}>Senha</Text>
            <TextInput
              testID="register-password"
              style={s.input}
              placeholder="Mínimo 6 caracteres"
              placeholderTextColor={theme.colors.textMuted}
              secureTextEntry
              value={password}
              onChangeText={setPassword}
            />

            <View style={s.trialBadge}>
              <Ionicons name="gift" size={16} color={theme.colors.statusWonText} />
              <Text style={s.trialText}>7 dias de Pro grátis ao se cadastrar 🎁</Text>
            </View>

            {!showRef ? (
              <TouchableOpacity onPress={() => setShowRef(true)} testID="show-referral">
                <Text style={s.link}>Tem código de indicação? Toque aqui</Text>
              </TouchableOpacity>
            ) : (
              <>
                <Text style={s.label}>Código de indicação (opcional)</Text>
                <TextInput
                  testID="register-referral"
                  style={s.input}
                  placeholder="Ex: ABC12345"
                  placeholderTextColor={theme.colors.textMuted}
                  autoCapitalize="characters"
                  value={referralCode}
                  onChangeText={(v) => setReferralCode(v.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8))}
                />
              </>
            )}

            <TouchableOpacity
              testID="register-submit"
              style={[s.btn, loading && { opacity: 0.7 }]}
              onPress={onSubmit}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <>
                  <Text style={s.btnText}>Criar conta</Text>
                  <Ionicons name="arrow-forward" size={20} color="#fff" />
                </>
              )}
            </TouchableOpacity>

            <View style={s.footer}>
              <Text style={s.footerText}>Já tem conta?</Text>
              <Link href="/(auth)/login" asChild>
                <TouchableOpacity testID="goto-login">
                  <Text style={s.footerLink}>Entrar</Text>
                </TouchableOpacity>
              </Link>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.bg },
  scroll: { flexGrow: 1, padding: 24, justifyContent: "center" },
  brand: { alignItems: "center", marginBottom: 32 },
  logo: {
    width: 64,
    height: 64,
    backgroundColor: theme.colors.primary,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
  },
  brandText: {
    fontSize: 26,
    fontWeight: "800",
    color: theme.colors.text,
    letterSpacing: -0.5,
  },
  subtitle: { fontSize: 14, color: theme.colors.textSec, marginTop: 6 },
  form: { gap: 12 },
  label: {
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.textMuted,
    letterSpacing: 1,
    textTransform: "uppercase",
    marginTop: 8,
  },
  input: {
    height: 56,
    borderRadius: 12,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    paddingHorizontal: 16,
    fontSize: 16,
    color: theme.colors.text,
  },
  btn: {
    height: 56,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    marginTop: 16,
  },
  btnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  footer: { flexDirection: "row", justifyContent: "center", gap: 8, marginTop: 24 },
  footerText: { color: theme.colors.textSec },
  footerLink: { color: theme.colors.text, fontWeight: "700" },
  trialBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: "#ECFDF5",
    borderWidth: 1,
    borderColor: "#A7F3D0",
    padding: 12,
    borderRadius: 12,
    marginTop: 8,
  },
  trialText: { color: theme.colors.statusWonText, fontWeight: "700", fontSize: 13 },
  link: { color: theme.colors.text, fontWeight: "700", fontSize: 13, textAlign: "center", marginTop: 4 },
});
