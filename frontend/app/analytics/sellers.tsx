import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useRouter } from "expo-router";
import { api, formatApiError } from "../../src/api";
import { theme, formatCurrency } from "../../src/theme";

type SellerAnalytic = {
  seller_name: string;
  proposal_count: number;
  approved_count: number;
  lost_count: number;
  open_count?: number;
  won_count?: number;
  negotiation_count?: number;
  conversion_rate: number;
  ticket_average: number;
  revenue: number;
  value_sold?: number;
  value_negotiated?: number;
};

export default function SellerRanking() {
  const router = useRouter();
  const [items, setItems] = useState<SellerAnalytic[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await api.get("/analytics/sellers");
      setItems(data);
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

  const safeBack = () => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace("/(tabs)");
    }
  };

  return (
    <SafeAreaView style={s.root} edges={["top"]} testID="seller-analytics-screen">
      <View style={s.topbar}>
        <TouchableOpacity onPress={safeBack} style={s.backIcon}>
          <Ionicons name="chevron-back" size={24} color={theme.colors.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Ranking de Vendedores</Text>
        <View style={{ width: 24 }} />
      </View>

      {loading ? (
        <View style={s.center}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
        </View>
      ) : (
        <ScrollView contentContainerStyle={s.scroll}>
          {items.length === 0 ? (
            <View style={s.empty}>
              <Ionicons name="people-outline" size={48} color={theme.colors.textMuted} />
              <Text style={s.emptyText}>Nenhuma proposta registrada ainda.</Text>
            </View>
          ) : (
            <View style={s.card}>
              <Text style={s.cardTitle}>Desempenho Geral de Vendas</Text>
              
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <View style={{ minWidth: 1010 }}>
                  <View style={s.tableHeader}>
                    <Text style={[s.headerCell, { width: 180 }]}>Vendedor</Text>
                    <Text style={[s.headerCell, { width: 90, textAlign: "center" }]}>Propostas</Text>
                    <Text style={[s.headerCell, { width: 80, textAlign: "center" }]}>Abertas</Text>
                    <Text style={[s.headerCell, { width: 90, textAlign: "center" }]}>Aprovadas</Text>
                    <Text style={[s.headerCell, { width: 90, textAlign: "center" }]}>Perdidas</Text>
                    <Text style={[s.headerCell, { width: 90, textAlign: "center" }]}>Conversão</Text>
                    <Text style={[s.headerCell, { width: 130, textAlign: "right" }]}>Ticket Médio</Text>
                    <Text style={[s.headerCell, { width: 130, textAlign: "right" }]}>Negociando</Text>
                    <Text style={[s.headerCell, { width: 130, textAlign: "right" }]}>Receita</Text>
                  </View>

                  {items.map((item, index) => (
                    <View key={index} style={s.tableRow}>
                      <View style={{ width: 180, flexDirection: "row", alignItems: "center", gap: 8 }}>
                        <Text style={s.rankText}>{index + 1}.</Text>
                        <Text style={s.sellerName} numberOfLines={2}>{item.seller_name || "Desconhecido"}</Text>
                      </View>
                      <Text style={[s.cell, { width: 90, textAlign: "center" }]}>{item.proposal_count}</Text>
                      <Text style={[s.cell, { width: 80, textAlign: "center", color: "#f59e0b" }]}>
                        {item.open_count || 0}
                      </Text>
                      <Text style={[s.cell, { width: 90, textAlign: "center", fontWeight: "600", color: theme.colors.success }]}>
                        {item.approved_count}
                      </Text>
                      <Text style={[s.cell, { width: 90, textAlign: "center", fontWeight: "600", color: theme.colors.danger }]}>
                        {item.lost_count}
                      </Text>
                      <Text style={[s.cell, { width: 90, textAlign: "center", fontWeight: "600", color: "#6D28D9" }]}>
                        {item.conversion_rate}%
                      </Text>
                      <Text style={[s.cell, { width: 130, textAlign: "right" }]}>
                        {formatCurrency(item.ticket_average)}
                      </Text>
                      <Text style={[s.cell, { width: 130, textAlign: "right", color: "#0284c7" }]}>
                        {formatCurrency(item.value_negotiated || 0)}
                      </Text>
                      <Text style={[s.cell, { width: 130, textAlign: "right", fontWeight: "700", color: theme.colors.success }]}>
                        {formatCurrency(item.value_sold || item.revenue)}
                      </Text>
                    </View>
                  ))}
                </View>
              </ScrollView>
            </View>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  topbar: {
    height: 52,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  backIcon: { padding: 4 },
  topTitle: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
  scroll: { padding: 24, gap: 16, paddingBottom: 60 },
  empty: { alignItems: "center", marginTop: 80, gap: 12 },
  emptyText: { color: theme.colors.textSec, fontSize: 15 },
  card: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 16,
    padding: 16,
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: "800",
    color: theme.colors.text,
    marginBottom: 16,
  },
  tableHeader: {
    flexDirection: "row",
    paddingVertical: 10,
    borderBottomWidth: 2,
    borderBottomColor: theme.colors.border,
    backgroundColor: "#F8FAFC",
    paddingHorizontal: 8,
  },
  headerCell: {
    fontSize: 11,
    fontWeight: "700",
    color: theme.colors.textSec,
    textTransform: "uppercase",
  },
  tableRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    paddingHorizontal: 8,
  },
  cell: {
    fontSize: 13,
    color: theme.colors.text,
  },
  rankText: {
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.textMuted,
    minWidth: 18,
  },
  sellerName: {
    fontSize: 13,
    fontWeight: "600",
    color: theme.colors.text,
    flex: 1,
  },
});
