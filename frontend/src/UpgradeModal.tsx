import React from "react";
import { View, Text, Modal, TouchableOpacity, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { theme } from "./theme";

type Props = {
  visible: boolean;
  onClose: () => void;
  message?: string;
};

export default function UpgradeModal({ visible, onClose, message }: Props) {
  const router = useRouter();
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={s.root} testID="upgrade-modal">
        <View style={s.card}>
          <View style={s.iconWrap}>
            <Ionicons name="star" size={28} color="#fff" />
          </View>
          <Text style={s.title}>Limite atingido</Text>
          <Text style={s.body}>
            {message ||
              "Você atingiu o limite de 10 propostas do plano grátis este mês. Faça upgrade para o Pro e tenha propostas ilimitadas."}
          </Text>

          <View style={s.benefits}>
            <Benefit text="Propostas ilimitadas" />
            <Benefit text="PDF profissional com sua logo" />
            <Benefit text="Follow-up automático no WhatsApp" />
            <Benefit text="Cancele quando quiser" />
          </View>

          <TouchableOpacity
            style={s.btnPrimary}
            testID="upgrade-go"
            onPress={() => {
              onClose();
              router.push("/subscription");
            }}
          >
            <Ionicons name="lock-open-outline" size={18} color="#fff" />
            <Text style={s.btnPrimaryText}>Ver planos Pro</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.btnGhost} onPress={onClose} testID="upgrade-later">
            <Text style={s.btnGhostText}>Mais tarde</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

function Benefit({ text }: { text: string }) {
  return (
    <View style={s.bRow}>
      <Ionicons name="checkmark-circle" size={18} color={theme.colors.statusWonText} />
      <Text style={s.bText}>{text}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.55)",
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
  },
  card: {
    width: "100%",
    maxWidth: 420,
    backgroundColor: "#fff",
    borderRadius: 20,
    padding: 24,
    alignItems: "center",
  },
  iconWrap: {
    width: 56,
    height: 56,
    borderRadius: 16,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 12,
  },
  title: { fontSize: 22, fontWeight: "800", color: theme.colors.text, letterSpacing: -0.5 },
  body: {
    color: theme.colors.textSec,
    fontSize: 14,
    textAlign: "center",
    marginTop: 8,
    marginBottom: 16,
  },
  benefits: { gap: 8, alignSelf: "stretch", marginBottom: 16 },
  bRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  bText: { color: theme.colors.text, fontSize: 14 },
  btnPrimary: {
    alignSelf: "stretch",
    height: 52,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  btnPrimaryText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  btnGhost: { padding: 14, marginTop: 4 },
  btnGhostText: { color: theme.colors.textSec, fontWeight: "600" },
});
