import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Share,
  Platform,
  Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Clipboard from "expo-clipboard";
import { useFocusEffect, useRouter } from "expo-router";
import { api, formatApiError } from "../src/api";
import { theme } from "../src/theme";

type Ref = {
  code: string;
  invited_total: number;
  converted: number;
  bonus_days_earned: number;
  reward_days_per_conversion: number;
};

export default function ReferralScreen() {
  const router = useRouter();
  const [data, setData] = useState<Ref | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await api.get("/referrals/me");
      setData(data);
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

  const link = data?.code
    ? `https://propostaja.app/?ref=${data.code}`
    : "";

  const message = data?.code
    ? `🚀 Conheci o PROPOSTA JÁ — app pra criar orçamentos profissionais e enviar pelo WhatsApp em 30 segundos. Use meu código *${data.code}* ao se cadastrar e a gente ganha 1 mês Pro grátis: ${link}`
    : "";

  const copy = async () => {
    if (!data?.code) return;
    await Clipboard.setStringAsync(data.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const share = async () => {
    if (!message) return;
    try {
      if (Platform.OS === "web") {
        if ((navigator as any).share) {
          await (navigator as any).share({ text: message, title: "PROPOSTA JÁ" });
        } else {
          await Clipboard.setStringAsync(message);
          Alert.alert("Copiado!", "Cole onde quiser pra convidar seus amigos.");
        }
      } else {
        await Share.share({ message });
      }
    } catch {}
  };

  if (loading || !data) {
    return (
      <SafeAreaView style={s.root}>
        <ActivityIndicator style={{ marginTop: 60 }} color={theme.colors.primary} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="referral-screen">
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} style={s.back}>
          <Ionicons name="chevron-back" size={24} color={theme.colors.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Indique e ganhe</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={s.scroll}>
        <View style={s.heroIcon}>
          <Ionicons name="gift" size={32} color="#fff" />
        </View>
        <Text style={s.title}>Ganhe {data.reward_days_per_conversion} dias Pro grátis</Text>
        <Text style={s.subtitle}>
          Compartilhe seu código. Quando seu amigo assinar o Pro, vocês dois ganham {data.reward_days_per_conversion} dias 🎁
        </Text>

        <View style={s.codeBox}>
          <Text style={s.codeLabel}>Seu código</Text>
          <Text style={s.code} testID="ref-code">{data.code}</Text>
          <TouchableOpacity onPress={copy} style={s.copyBtn} testID="copy-code">
            <Ionicons name={copied ? "checkmark" : "copy-outline"} size={16} color="#fff" />
            <Text style={s.copyText}>{copied ? "Copiado" : "Copiar"}</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity style={s.shareBtn} onPress={share} testID="share-ref">
          <Ionicons name="share-social" size={20} color="#fff" />
          <Text style={s.shareText}>Compartilhar convite</Text>
        </TouchableOpacity>

        <View style={s.statsGrid}>
          <View style={s.stat}>
            <Text style={s.statValue}>{data.invited_total}</Text>
            <Text style={s.statLabel}>Convidados</Text>
          </View>
          <View style={s.stat}>
            <Text style={s.statValue}>{data.converted}</Text>
            <Text style={s.statLabel}>Assinaram</Text>
          </View>
          <View style={s.stat}>
            <Text style={s.statValue}>{data.bonus_days_earned}d</Text>
            <Text style={s.statLabel}>Você ganhou</Text>
          </View>
        </View>

        <View style={s.howCard}>
          <Text style={s.howTitle}>Como funciona</Text>
          <Step n="1" t="Compartilhe seu código com vendedores que conhece" />
          <Step n="2" t="Eles se cadastram usando seu código" />
          <Step n="3" t="Quando assinarem o Pro, vocês 2 ganham 30 dias 🎉" />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function Step({ n, t }: { n: string; t: string }) {
  return (
    <View style={s.stepRow}>
      <View style={s.stepNum}>
        <Text style={s.stepNumText}>{n}</Text>
      </View>
      <Text style={s.stepText}>{t}</Text>
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
  scroll: { padding: 24, paddingBottom: 40, gap: 16, alignItems: "center" },
  heroIcon: {
    width: 72,
    height: 72,
    borderRadius: 20,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  title: {
    fontSize: 26,
    fontWeight: "800",
    color: theme.colors.text,
    letterSpacing: -0.5,
    textAlign: "center",
  },
  subtitle: { color: theme.colors.textSec, fontSize: 14, textAlign: "center", marginBottom: 8 },
  codeBox: {
    alignSelf: "stretch",
    backgroundColor: "#fff",
    borderWidth: 2,
    borderColor: theme.colors.primary,
    borderStyle: "dashed",
    borderRadius: 16,
    padding: 20,
    alignItems: "center",
    gap: 8,
  },
  codeLabel: {
    fontSize: 11,
    color: theme.colors.textMuted,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 1.5,
  },
  code: {
    fontSize: 32,
    fontWeight: "800",
    color: theme.colors.text,
    letterSpacing: 4,
  },
  copyBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: theme.colors.primary,
    borderRadius: 999,
    marginTop: 4,
  },
  copyText: { color: "#fff", fontSize: 13, fontWeight: "700" },
  shareBtn: {
    alignSelf: "stretch",
    height: 56,
    borderRadius: 12,
    backgroundColor: theme.colors.whatsapp,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  shareText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  statsGrid: {
    flexDirection: "row",
    alignSelf: "stretch",
    gap: 8,
  },
  stat: {
    flex: 1,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 16,
    borderRadius: 14,
    alignItems: "center",
  },
  statValue: {
    fontSize: 24,
    fontWeight: "800",
    color: theme.colors.text,
    letterSpacing: -0.5,
  },
  statLabel: { fontSize: 11, color: theme.colors.textSec, marginTop: 4 },
  howCard: {
    alignSelf: "stretch",
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: 16,
    borderRadius: 14,
    gap: 10,
  },
  howTitle: {
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.textMuted,
    letterSpacing: 1.5,
    textTransform: "uppercase",
    marginBottom: 4,
  },
  stepRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  stepNum: {
    width: 28,
    height: 28,
    borderRadius: 8,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  stepNumText: { color: "#fff", fontWeight: "800", fontSize: 14 },
  stepText: { color: theme.colors.text, fontSize: 14, flex: 1 },
});
