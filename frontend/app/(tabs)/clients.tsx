import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "expo-router";
import { api } from "../../src/api";
import { theme, formatCurrency, formatDate } from "../../src/theme";
import { followUpMessage, openWhatsApp } from "../../src/pdf";

type Client = {
  client_name: string;
  client_document: string;
  client_phone: string;
  last_proposal_at: string;
  proposals_count: number;
  total_value: number;
};

export default function Clients() {
  const [items, setItems] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);

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

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="clients-screen">
      <View style={s.header}>
        <Text style={s.title}>Clientes</Text>
        <Text style={s.subtitle}>{items.length} cliente(s) no histórico</Text>
      </View>
      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={theme.colors.primary} />
      ) : (
        <ScrollView contentContainerStyle={s.list}>
          {items.length === 0 && (
            <View style={s.empty}>
              <Ionicons name="people-outline" size={48} color={theme.colors.textMuted} />
              <Text style={s.emptyText}>Seus clientes aparecem aqui ao criar propostas</Text>
            </View>
          )}
          {items.map((c) => (
            <View key={c.client_document || c.client_name} style={s.card}>
              <View style={s.avatar}>
                <Text style={s.avatarText}>
                  {c.client_name?.[0]?.toUpperCase() || "?"}
                </Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.name}>{c.client_name}</Text>
                <Text style={s.sub}>
                  {c.client_document} · {c.client_phone}
                </Text>
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
              <TouchableOpacity
                style={s.whats}
                onPress={() => openWhatsApp(c.client_phone, followUpMessage(c.client_name))}
                testID={`whatsapp-${c.client_document}`}
              >
                <Ionicons name="logo-whatsapp" size={22} color="#fff" />
              </TouchableOpacity>
            </View>
          ))}
        </ScrollView>
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
  empty: { alignItems: "center", marginTop: 60, gap: 12 },
  emptyText: { color: theme.colors.textSec, textAlign: "center", paddingHorizontal: 32 },
});
