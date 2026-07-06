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
import { useFocusEffect } from "expo-router";

import { api } from "../../src/api";
import { theme, formatCurrency } from "../../src/theme";
import { useAuth } from "../../src/auth";
import { maskCurrency, parseCurrency, formatCurrencyFromBackend } from "../../src/masks";

type Product = {
  id: string;
  code: string;
  name: string;
  description: string;
  price: number;
  unit: string;
};

export default function Products() {
  const { user } = useAuth();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;

  const [items, setItems] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [modalOpen, setModalOpen] = useState(false);

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [price, setPrice] = useState("");
  const [unit, setUnit] = useState("UN");

  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  
  const load = useCallback(async () => {
    try {
      setLoading(true);
      const { data } = await api.get("/products");
      setItems(Array.isArray(data) ? data : []);
    } catch (e) {
      Alert.alert("Erro", "Falha ao carregar produtos");
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return items;

    return items.filter(
      (p) =>
        p.code?.toLowerCase().includes(term) ||
        p.name?.toLowerCase().includes(term)
    );
  }, [items, search]);

  const editProduct = (p: Product) => {
    setEditingId(p.id);
    setCode(p.code);
    setName(p.name);
    setDescription(p.description || "");
    setPrice(formatCurrencyFromBackend(p.price));
    setUnit(p.unit || "UN");
    setModalOpen(true);
  };

  const deleteProduct = async (id: string) => {
    Alert.alert(
      "Excluir Produto",
      "Deseja realmente excluir este produto?",
      [
        {
          text: "Cancelar",
          style: "cancel",
        },
        {
          text: "Excluir",
          style: "destructive",
          onPress: async () => {
            try {
              await api.delete(`/products/${id}`);
              await load();
            } catch {
              Alert.alert("Erro", "Falha ao excluir produto");
            }
          },
        },
      ]
    );
  };

  const saveProduct = async () => {
    if (!editingId && user?.trial_is_expired) {
      Alert.alert(
        "Período de avaliação terminado",
        `Seu período de avaliação terminou.\n\nVocê já gerou:\n* ${user.trial_stats?.proposals_count ?? 0} propostas\n* ${user.trial_stats?.clients_count ?? 0} clientes\n* ${user.trial_stats?.negotiations_count ?? 0} negociações\n\nAssine o Plano Pro para continuar utilizando.`
      );
      return;
    }

    if (!code.trim() || !name.trim() || !price.trim()) {
      Alert.alert("Atenção", "Código, nome e preço são obrigatórios.");
      return;
    }

    const productPayload = {
      code: code.trim(),
      name: name.trim(),
      description: description.trim(),
      price: parseCurrency(price),
      unit: unit.trim() || "UN",
    };

    try {
      setSaving(true);

      if (editingId) {
        await api.put(`/products/${editingId}`, productPayload);
      } else {
        await api.post("/products", productPayload);
      }

      setModalOpen(false);
      setCode("");
      setName("");
      setDescription("");
      setPrice("");
      setUnit("UN");
      setEditingId(null);

      await load();
    } catch (e: any) {
      if (e?.response?.status === 403) {
        Alert.alert(
          "Período de avaliação terminado",
          e.response.data?.detail || "Seu período de avaliação terminou. Assine o Plano Pro para continuar utilizando."
        );
      } else {
        Alert.alert("Erro", "Falha ao salvar produto");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={s.root} edges={["top"]}>
      <View style={s.header}>
        <View>
          <Text style={s.title}>Produtos</Text>
          <Text style={s.subtitle}>
            {items.length} produto(s) cadastrados
          </Text>
        </View>

        <TouchableOpacity
          style={s.newBtn}
          onPress={() => setModalOpen(true)}
        >
          <Ionicons name="add" size={18} color="#fff" />
          <Text style={s.newBtnText}>
            {editingId ? "Editar Produto" : "Novo Produto"}
          </Text>
        </TouchableOpacity>
      </View>

      <View style={s.searchWrap}>
        <TextInput
          style={s.search}
          value={search}
          onChangeText={setSearch}
          placeholder="Buscar código ou produto"
          placeholderTextColor={theme.colors.textMuted}
        />
      </View>

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
          <View
            style={{
              width: "100%",
              maxWidth: 600,
              backgroundColor: "#fff",
              borderRadius: 16,
              padding: 20,
              gap: 12,
            }}
          >
            <Text style={{ fontSize: 22, fontWeight: "700" }}>
              {editingId ? "Editar Produto" : "Novo Produto"}
            </Text>

            <TextInput
              style={s.search}
              placeholder="Código"
              value={code}
              onChangeText={setCode}
            />

            <TextInput
              style={s.search}
              placeholder="Nome"
              value={name}
              onChangeText={setName}
            />

            <TextInput
              style={s.search}
              placeholder="Descrição"
              value={description}
              onChangeText={setDescription}
            />

            <TextInput
              style={s.search}
              placeholder="Preço"
              value={price}
              onChangeText={(v) => setPrice(maskCurrency(v))}
              keyboardType="numeric"
            />

            <TextInput
              style={s.search}
              placeholder="Unidade"
              value={unit}
              onChangeText={setUnit}
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
                  setCode("");
                  setName("");
                  setDescription("");
                  setPrice("");
                  setUnit("UN");
                }}
                style={{ justifyContent: "center", paddingHorizontal: 10 }}
              >
                <Text style={{ color: theme.colors.textSec }}>Cancelar</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={s.newBtn}
                onPress={saveProduct}
                disabled={saving}
              >
                <Text style={s.newBtnText}>
                  {saving ? "Salvando..." : "Salvar"}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {loading ? (
        <ActivityIndicator
          style={{ marginTop: 40 }}
          color={theme.colors.primary}
        />
      ) : (
        <ScrollView
          contentContainerStyle={s.list}
          refreshControl={
            <RefreshControl refreshing={loading} onRefresh={load} />
          }
        >
          {filtered.map((p) => (
            <View key={p.id} style={s.card}>
              <View style={{ flex: 1 }}>
                <Text style={s.code}>{p.code}</Text>
                <Text style={s.name}>{p.name}</Text>
                <Text style={s.desc}>{p.description}</Text>
              </View>

              <View style={{ alignItems: "flex-end", gap: 8 }}>
                <Text style={s.price}>{formatCurrency(p.price)}</Text>
                <Text style={s.unit}>{p.unit}</Text>

                <View style={{ flexDirection: "row", gap: 12, marginTop: 4 }}>
                  <TouchableOpacity onPress={() => editProduct(p)}>
                    <Ionicons name="create-outline" size={20} color="#2563EB" />
                  </TouchableOpacity>

                  <TouchableOpacity onPress={() => deleteProduct(p.id)}>
                    <Ionicons name="trash-outline" size={20} color="#DC2626" />
                  </TouchableOpacity>
                </View>
              </View>
            </View>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: theme.colors.bg,
  },
  header: {
    padding: 24,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  title: {
    fontSize: 28,
    fontWeight: "800",
    color: theme.colors.text,
  },
  subtitle: {
    marginTop: 4,
    color: theme.colors.textSec,
  },
  newBtn: {
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
    backgroundColor: theme.colors.primary,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 12,
  },
  newBtnText: {
    color: "#fff",
    fontWeight: "700",
  },
  searchWrap: {
    paddingHorizontal: 24,
    marginBottom: 10,
  },
  search: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 12,
    height: 50,
    paddingHorizontal: 14,
    color: theme.colors.text,
  },
  list: {
    padding: 24,
    gap: 12,
  },
  card: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 14,
    padding: 14,
    flexDirection: "row",
    justifyContent: "space-between",
  },
  code: {
    fontSize: 12,
    color: theme.colors.textMuted,
  },
  name: {
    fontSize: 16,
    fontWeight: "700",
    marginTop: 4,
    color: theme.colors.text,
  },
  desc: {
    marginTop: 4,
    color: theme.colors.textSec,
  },
  price: {
    fontWeight: "700",
    textAlign: "right",
    color: theme.colors.text,
  },
  unit: {
    marginTop: 4,
    textAlign: "right",
    color: theme.colors.textMuted,
  },
});