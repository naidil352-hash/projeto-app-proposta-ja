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

type ProductAnalytic = {
  name: string;
  quantity_sold: number;
  proposal_count: number;
  revenue: number;
};

export default function ProductRanking() {
  const router = useRouter();
  const [items, setItems] = useState<ProductAnalytic[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await api.get("/analytics/products");
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
    <SafeAreaView style={s.root} edges={["top"]} testID="product-analytics-screen">
      <View style={s.topbar}>
        <TouchableOpacity onPress={safeBack} style={s.backIcon}>
          <Ionicons name="chevron-back" size={24} color={theme.colors.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Ranking de Produtos</Text>
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
              <Ionicons name="cube-outline" size={48} color={theme.colors.textMuted} />
              <Text style={s.emptyText}>Nenhuma venda registrada ainda.</Text>
            </View>
          ) : (
            <View style={s.card}>
              <Text style={s.cardTitle}>Desempenho por Receita</Text>
              
              <View style={s.tableHeader}>
                <Text style={[s.headerCell, { flex: 2 }]}>Produto</Text>
                <Text style={[s.headerCell, { flex: 1, textAlign: "center" }]}>Qtd</Text>
                <Text style={[s.headerCell, { flex: 1, textAlign: "center" }]}>Propostas</Text>
                <Text style={[s.headerCell, { flex: 1.5, textAlign: "right" }]}>Receita</Text>
              </View>

              {items.map((item, index) => (
                <View key={index} style={s.tableRow}>
                  <View style={[s.cell, { flex: 2, flexDirection: "row", alignItems: "center", gap: 8 }]}>
                    <Text style={s.rankText}>{index + 1}.</Text>
                    <Text style={s.productName} numberOfLines={2}>{item.name}</Text>
                  </View>
                  <Text style={[s.cell, { flex: 1, textAlign: "center" }]}>{item.quantity_sold}</Text>
                  <Text style={[s.cell, { flex: 1, textAlign: "center" }]}>{item.proposal_count}</Text>
                  <Text style={[s.cell, { flex: 1.5, textAlign: "right", fontWeight: "700", color: theme.colors.success }]}>
                    {formatCurrency(item.revenue)}
                  </Text>
                </View>
              ))}
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
  productName: {
    fontSize: 13,
    fontWeight: "600",
    color: theme.colors.text,
    flex: 1,
  },
});
