import React, { useCallback, useState } from "react";
import {
  View,
  Image,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from "react-native";

import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import {
  useFocusEffect,
  useLocalSearchParams,
  useRouter,
} from "expo-router";

import { api, formatApiError } from "../../src/api";

import {
  theme,
  statusMeta,
  formatCurrency,
  formatDate,
  daysSince,
  getRoleLabel,
} from "../../src/theme";

import {
  generateProposalPdf,
  sharePdf,
  printPdf,
  openWhatsApp,
  followUpMessage,
  proposalShareMessage,
} from "../../src/pdf";

import UpgradeModal from "../../src/UpgradeModal";
import { useAuth } from "../../src/auth";

const formatTimeAgo = (dateStr?: string) => {
  if (!dateStr) return "";
  try {
    const past = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - past.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "agora mesmo";
    if (diffMins < 60) return `há ${diffMins} ${diffMins === 1 ? "minuto" : "minutos"}`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `há ${diffHours} ${diffHours === 1 ? "hora" : "horas"}`;
    const diffDays = Math.floor(diffHours / 24);
    return `há ${diffDays} ${diffDays === 1 ? "dia" : "dias"}`;
  } catch {
    return "";
  }
};

const formatDateTime = (dateStr?: string) => {
  if (!dateStr) return "";
  try {
    const d = new Date(dateStr);
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const year = d.getFullYear();
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return `${day}/${month}/${year} às ${hours}:${minutes}`;
  } catch {
    return "";
  }
};

export default function ProposalDetail() {
  const { id } =
    useLocalSearchParams<{
      id: string;
    }>();

  const router = useRouter();
  const { user } = useAuth();

  const [p, setP] =
    useState<any>(null);

  const [company, setCompany] =
    useState<any>({});

  const [loading, setLoading] =
    useState(true);

  const [lostModal, setLostModal] =
    useState(false);

  const [lostReason, setLostReason] =
    useState("");

  const [busy, setBusy] =
    useState(false);

  const [
    upgradeOpen,
    setUpgradeOpen,
  ] = useState(false);

  const [upgradeMsg, setUpgradeMsg] =
    useState<string | undefined>();

  const safeBack = () => {
    try {
      if (
        router.canGoBack &&
        router.canGoBack()
      ) {
        router.back();
      } else {
        router.replace(
          "/(tabs)/proposals"
        );
      }
    } catch {
      router.replace(
        "/(tabs)/proposals"
      );
    }
  };

  const load = useCallback(
    async () => {
      try {
        setLoading(true);

        const [prop, comp] = await Promise.all([
  api.get(`/proposals/${id}`),
  api.get("/company"),
]);

console.log(
  "PROPOSTA API",
  JSON.stringify(prop.data, null, 2)
);

setP(prop.data);

		console.log("PROPOSTA COMPLETA", prop.data);

        setCompany(comp.data);
      } catch (e) {
        Alert.alert(
          "Erro",
          formatApiError(e)
        );
      } finally {
        setLoading(false);
      }
    },
    [id]
  );

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const changeStatus = async (
    status: string,
    reason?: string
  ) => {
    try {
      setBusy(true);

      await api.patch(
        `/proposals/${id}/status`,
        {
          status,
          lost_reason:
            reason || null,
        }
      );

      setLostModal(false);

      setLostReason("");

      await load();
    } catch (e) {
      Alert.alert(
        "Erro",
        formatApiError(e)
      );
    } finally {
      setBusy(false);
    }
  };

  const onShare = async () => {
    try {
      setBusy(true);

      const uri =
        await generateProposalPdf(
          p,
          company
        );

      await sharePdf(uri);
    } catch (e: any) {
      Alert.alert(
        "Erro",
        e.message ||
          "Falha ao gerar PDF"
      );
    } finally {
      setBusy(false);
    }
  };

  const onPrint = async () => {
    try {
      setBusy(true);

      const uri =
        await generateProposalPdf(
          p,
          company
        );

      await printPdf(uri);
    } catch (e: any) {
      Alert.alert(
        "Erro",
        e.message ||
          "Falha ao imprimir"
      );
    } finally {
      setBusy(false);
    }
  };

  const onWhats = () => {
    openWhatsApp(
      p.client_phone,
      proposalShareMessage(
        p,
        company
      )
    );
  };

  const onFollowUp = () => {
    openWhatsApp(
      p.client_phone,
      followUpMessage(
        p.client_name
      )
    );
  };

  const onEdit = () => {
    if (p.acceptance_status === "accepted") {
      Alert.alert("Atenção", "Esta proposta já foi aceita e não pode ser editada.");
      return;
    }
    router.push(
      `/(tabs)/new?editId=${p.id}`
    );
  };

  const onReopen = async () => {
    try {
      setBusy(true);
      await api.post(`/proposals/${id}/reopen`);
      Alert.alert("Sucesso", "Proposta reaberta com sucesso!");
      await load();
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const onDuplicate =
    async () => {
      if (user?.trial_is_expired) {
        Alert.alert(
          "Período de avaliação terminado",
          `Seu período de avaliação terminou.\n\nVocê já gerou:\n* ${user.trial_stats?.proposals_count ?? 0} propostas\n* ${user.trial_stats?.clients_count ?? 0} clientes\n* ${user.trial_stats?.negotiations_count ?? 0} negociações\n\nAssine o Plano Pro para continuar utilizando.`
        );
        return;
      }
      try {
        setBusy(true);

        const { data } =
          await api.post(
            `/proposals/${id}/duplicate`
          );

        router.replace(
          `/proposal/${data.id}`
        );
      } catch (e: any) {
        if (
          e?.response?.status ===
          402
        ) {
          setUpgradeMsg(
            e.response.data
              ?.detail
          );

          setUpgradeOpen(
            true
          );
        } else if (
          e?.response?.status ===
          403
        ) {
          Alert.alert(
            "Período de avaliação terminado",
            e.response.data?.detail || "Seu período de avaliação terminou. Assine o Plano Pro para continuar utilizando."
          );
        } else {
          Alert.alert(
            "Erro",
            formatApiError(e)
          );
        }
      } finally {
        setBusy(false);
      }
    };

  const convertManualItem = async (index: number) => {
    try {
      setBusy(true);
      const { data } = await api.post(`/proposals/${id}/items/${index}/convert`);
      Alert.alert(
        "Sucesso",
        `Produto ${data.code} criado com sucesso a partir do item manual!`
      );
      await load();
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const onDelete = () => {
    if (p.acceptance_status === "accepted") {
      Alert.alert("Atenção", "Esta proposta já foi aceita e não pode ser excluída.");
      return;
    }
    Alert.alert(
      "Excluir proposta",
      "Tem certeza?",
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
              await api.delete(
                `/proposals/${id}`
              );

              router.replace(
                "/(tabs)/proposals"
              );
            } catch (e) {
              Alert.alert(
                "Erro",
                formatApiError(e)
              );
            }
          },
        },
      ]
    );
  };

  if (loading || !p) {
    return (
      <SafeAreaView
        style={s.root}
      >
        <ActivityIndicator
          style={{
            marginTop: 60,
          }}
          color={
            theme.colors.primary
          }
        />
      </SafeAreaView>
    );
  }

  const st =
    statusMeta[p.status];

  const stale =
    p.status === "aberto" &&
    daysSince(
      p.created_at
    ) >= 3;

  return (
    <SafeAreaView
      style={s.root}
      edges={["top"]}
      testID="proposal-detail"
    >
      <View style={s.topbar}>
        <TouchableOpacity
          onPress={safeBack}
          style={s.back}
          testID="back-btn"
        >
          <Ionicons
            name="chevron-back"
            size={24}
            color={
              theme.colors.text
            }
          />
        </TouchableOpacity>

        <Text style={s.topTitle}>
          #
          {p.id
            .slice(0, 8)
            .toUpperCase()}
        </Text>

        <TouchableOpacity
          onPress={onDelete}
          testID="delete-proposal"
        >
          <Ionicons
            name="trash-outline"
            size={22}
            color={
              theme.colors
                .danger
            }
          />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={
          s.scroll
        }
      >
        <View
          style={[
            s.badge,
            {
              backgroundColor:
                st.bg,

              borderColor:
                st.border,
            },
          ]}
        >
          <Text
            style={[
              s.badgeText,
              {
                color: st.text,
              },
            ]}
          >
            {st.label}
          </Text>
        </View>

        {p.proposal_viewed_at ? (
          <View style={s.viewedStatusRow}>
            <Text style={s.viewedStatusText}>
              ✓ Visualizada em {formatDateTime(p.proposal_viewed_at)}
            </Text>
          </View>
        ) : null}

        {p.status === "aberto" && p.proposal_viewed_at ? (
          <View style={s.viewedCard}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
              <Ionicons name="eye-outline" size={24} color={theme.colors.primary} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 15, fontWeight: "700", color: theme.colors.text }}>
                  Cliente visualizou a proposta.
                </Text>
                <Text style={{ fontSize: 13, color: theme.colors.textSec }}>
                  Cliente visualizou {formatTimeAgo(p.proposal_viewed_at)}.
                </Text>
              </View>
            </View>
            <TouchableOpacity
              style={s.viewedBtn}
              onPress={onFollowUp}
              testID="btn-viewed-whatsapp"
            >
              <Ionicons name="logo-whatsapp" size={16} color="#fff" />
              <Text style={s.viewedBtnText}>Enviar WhatsApp</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {stale && (
          <View
            style={s.staleCard}
          >
            <Ionicons
              name="alarm"
              size={18}
              color={
                theme.colors.warn
              }
            />

            <Text
              style={s.staleText}
            >
              Aberto há{" "}
              {daysSince(
                p.created_at
              )}{" "}
              dias — hora de
              fazer um
              follow-up!
            </Text>
          </View>
        )}

        <View style={s.card}>
          <Text style={s.h1}>
            {p.client_name}
          </Text>

          <Text style={s.sub}>
            {p.client_document}
          </Text>

          <Text style={s.sub}>
            {p.client_phone}
          </Text>
        </View>

        {p.acceptance_status && p.acceptance_status !== "pending" && (
          <View style={[s.card, p.acceptance_status === "accepted" ? { borderColor: theme.colors.success } : { borderColor: theme.colors.danger }]}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Ionicons
                name={p.acceptance_status === "accepted" ? "checkmark-circle" : "close-circle"}
                size={22}
                color={p.acceptance_status === "accepted" ? theme.colors.success : theme.colors.danger}
              />
              <Text style={{ fontSize: 15, fontWeight: "800", color: p.acceptance_status === "accepted" ? theme.colors.success : theme.colors.danger }}>
                {p.acceptance_status === "accepted" ? "PROPOSTA ACEITA" : "PROPOSTA RECUSADA"}
              </Text>
            </View>
            <View style={{ gap: 4, backgroundColor: "#F8FAFC", padding: 12, borderRadius: 8, borderWidth: 1, borderColor: "#E2E8F0" }}>
              <Text style={{ fontSize: 13, color: theme.colors.text }}><strong>Assinado por:</strong> {p.accept_name || "-"}</Text>
              <Text style={{ fontSize: 13, color: theme.colors.text }}><strong>Documento:</strong> {p.accept_document || "-"}</Text>
              <Text style={{ fontSize: 13, color: theme.colors.text }}><strong>Cargo:</strong> {p.accept_role || "-"}</Text>
              <Text style={{ fontSize: 13, color: theme.colors.text }}><strong>Data/Hora:</strong> {formatDate(p.accept_date || "")}</Text>
              <Text style={{ fontSize: 13, color: theme.colors.text }}><strong>IP:</strong> {p.accept_ip || "-"}</Text>
              <Text style={{ fontSize: 13, color: theme.colors.text }}><strong>Dispositivo:</strong> {p.accept_device || "-"}</Text>
            </View>
            {p.acceptance_status === "accepted" && user?.role === "owner" && (
              <TouchableOpacity
                style={{ marginTop: 12, height: 40, backgroundColor: theme.colors.primary, borderRadius: 8, alignItems: "center", justifyContent: "center" }}
                onPress={onReopen}
                disabled={busy}
                testID="btn-reopen-proposal"
              >
                <Text style={{ color: "#fff", fontWeight: "700", fontSize: 13 }}>Reabrir Proposta</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

                <View style={s.card}>
          <Text style={s.sectionLabel}>Itens</Text>
          
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={{ minWidth: 740 }}>
              <View style={s.tableHeader}>
                <Text style={[s.tableHeadCell, { width: 60 }]}>Cód</Text>
                <Text style={[s.tableHeadCell, { width: 140 }]}>Produto</Text>
                <Text style={[s.tableHeadCell, { width: 160 }]}>Descrição</Text>
                <Text style={[s.tableHeadCell, { width: 60, textAlign: "center" }]}>Qtd</Text>
                <Text style={[s.tableHeadCell, { width: 90, textAlign: "right" }]}>Preço Un.</Text>
                <Text style={[s.tableHeadCell, { width: 90, textAlign: "right" }]}>Total</Text>
                <Text style={[s.tableHeadCell, { width: 140, textAlign: "center" }]}>Ação</Text>
              </View>
              
              {p.products.map((pr: any, i: number) => {
                const unitPrice = pr.unit_price ?? pr.price ?? 0;
                const itemTotal = pr.total ?? (pr.quantity * unitPrice);
                return (
                  <View key={i} style={s.tableRow}>
                    <Text style={[s.tableCell, { width: 60 }]}>{pr.code || ""}</Text>
                    <Text style={[s.tableCell, { width: 140, fontWeight: "600" }]}>{pr.name || ""}</Text>
                    <Text style={[s.tableCell, { width: 160, fontSize: 12, color: theme.colors.textMuted }]}>{pr.description || "-"}</Text>
                    <Text style={[s.tableCell, { width: 60, textAlign: "center" }]}>{pr.quantity} {pr.unit || "UN"}</Text>
                    <Text style={[s.tableCell, { width: 90, textAlign: "right" }]}>{formatCurrency(unitPrice)}</Text>
                    <Text style={[s.tableCell, { width: 90, textAlign: "right", fontWeight: "700" }]}>{formatCurrency(itemTotal)}</Text>
                    <View style={{ width: 140, alignItems: "center", justifyContent: "center" }}>
                      {pr.item_type === "manual" ? (
                        <TouchableOpacity
                          style={s.convertBtn}
                          onPress={() => convertManualItem(i)}
                          testID={`convert-item-${i}`}
                        >
                          <Text style={s.convertBtnText}>Transformar em Produto</Text>
                        </TouchableOpacity>
                      ) : (
                        <Text style={{ fontSize: 12, color: theme.colors.textMuted }}>Catálogo</Text>
                      )}
                    </View>
                  </View>
                );
              })}
            </View>
          </ScrollView>

          <View style={s.footerSummary}>
            <View style={s.summaryRow}>
              <Text style={s.summaryLabel}>Subtotal</Text>
              <Text style={s.summaryValue}>{formatCurrency(p.subtotal ?? (p.total + (p.discount ?? 0)))}</Text>
            </View>
            {(p.discount || 0) > 0 ? (
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
        </View>

        <View style={s.card}>
          <Text
            style={
              s.sectionLabel
            }
          >
            Prazo de embarque
          </Text>

          <Text style={s.itemName}>
            {p.shipping_deadline}
          </Text>
        </View>

        {p.seller_name ? (
          <View style={s.card}>
            <Text style={s.sectionLabel}>Consultor Comercial</Text>
            <Text style={s.itemName}>{p.seller_name}</Text>
            {p.seller_role ? <Text style={s.sub}>Cargo: {getRoleLabel(p.seller_role)}</Text> : null}
            {p.seller_phone ? <Text style={s.sub}>Telefone: {p.seller_phone}</Text> : null}
            {p.seller_email ? <Text style={s.sub}>E-mail: {p.seller_email}</Text> : null}
          </View>
        ) : null}

        {p.images?.length ? (
          <View style={s.card}>
            <Text
              style={
                s.sectionLabel
              }
            >
              Imagens
            </Text>

            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={{
                gap: 12,
              }}
            >
              {p.images.map(
                (
                  img: string,
                  i: number
                ) => (
                  <Image
					key={i}
					source={{ uri: img }}
					style={s.previewImage}
					resizeMode="contain"
					fadeDuration={0}
				  />
                )
              )}
            </ScrollView>
          </View>
        ) : null}

        {p.notes ? (
          <View style={s.card}>
            <Text
              style={
                s.sectionLabel
              }
            >
              Observações
            </Text>

            <Text style={s.sub}>
              {p.notes}
            </Text>
          </View>
        ) : null}

        {p.status === "perdido" &&
        p.lost_reason ? (
          <View
            style={[
              s.card,
              {
                borderColor:
                  theme.colors
                    .statusLostBorder,
              },
            ]}
          >
            <Text
              style={
                s.sectionLabel
              }
            >
              Motivo da perda
            </Text>

            <Text style={s.sub}>
              {p.lost_reason}
            </Text>
          </View>
        ) : null}

        <Text style={s.created}>
          Criado em{" "}
          {formatDate(
            p.created_at
          )}
        </Text>

        <Text
          style={
            s.sectionLabelBig
          }
        >
          Ações
        </Text>

        <View style={s.grid}>
          <ActionBtn
            testID="act-share"
            icon="share-outline"
            label="Enviar PDF"
            onPress={onShare}
          />

          <ActionBtn
            testID="act-print"
            icon="print-outline"
            label="Imprimir"
            onPress={onPrint}
          />

          <ActionBtn
            testID="act-whatsapp"
            icon="logo-whatsapp"
            label="WhatsApp"
            color={
              theme.colors
                .whatsapp
            }
            onPress={onWhats}
          />

          {p.status ===
            "aberto" && (
            <ActionBtn
              testID="act-followup"
              icon="chatbubble-ellipses-outline"
              label="Follow-up IA"
              onPress={
                onFollowUp
              }
            />
          )}

          <ActionBtn
            testID="act-edit"
            icon="create-outline"
            label="Editar"
            onPress={onEdit}
          />

          <ActionBtn
            testID="act-duplicate"
            icon="copy-outline"
            label="Duplicar"
            onPress={
              onDuplicate
            }
          />
        </View>

        {["aberto", "qualificado", "negociacao"].includes(p.status) && (
          <>
            <Text style={s.sectionLabelBig}>Atualizar status</Text>
            <View style={s.grid}>
              {p.status === "aberto" && (
                <>
                  <TouchableOpacity
                    style={[s.statBtn, { backgroundColor: "#6D28D9" }]}
                    onPress={() => changeStatus("qualificado")}
                    testID="status-qualificar"
                    disabled={busy}
                  >
                    <Ionicons name="funnel-outline" size={20} color="#fff" />
                    <Text style={s.statText}>Qualificar</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[s.statBtn, { backgroundColor: "#B45309" }]}
                    onPress={() => changeStatus("negociacao")}
                    testID="status-negociacao"
                    disabled={busy}
                  >
                    <Ionicons name="chatbubbles-outline" size={20} color="#fff" />
                    <Text style={s.statText}>Negociação</Text>
                  </TouchableOpacity>
                </>
              )}

              {p.status === "qualificado" && (
                <TouchableOpacity
                  style={[s.statBtn, { backgroundColor: "#B45309", minWidth: "100%" }]}
                  onPress={() => changeStatus("negociacao")}
                  testID="status-negociacao"
                  disabled={busy}
                >
                  <Ionicons name="chatbubbles-outline" size={20} color="#fff" />
                  <Text style={s.statText}>Iniciar Negociação</Text>
                </TouchableOpacity>
              )}

              {p.status === "negociacao" && (
                <>
                  <TouchableOpacity
                    style={[s.statBtn, { backgroundColor: theme.colors.statusWonText }]}
                    onPress={() => changeStatus("aprovado")}
                    testID="status-won"
                    disabled={busy}
                  >
                    <Ionicons name="checkmark-circle" size={20} color="#fff" />
                    <Text style={s.statText}>Aprovar</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[s.statBtn, { backgroundColor: theme.colors.statusLostText }]}
                    onPress={() => setLostModal(true)}
                    testID="status-lost"
                    disabled={busy}
                  >
                    <Ionicons name="close-circle" size={20} color="#fff" />
                    <Text style={s.statText}>Perdido</Text>
                  </TouchableOpacity>
                </>
              )}
            </View>
          </>
        )}
      </ScrollView>

      <Modal
        visible={lostModal}
        transparent
        animationType="fade"
        onRequestClose={() =>
          setLostModal(false)
        }
      >
        <KeyboardAvoidingView
          style={s.modalRoot}
          behavior={
            Platform.OS ===
            "ios"
              ? "padding"
              : undefined
          }
        >
          <View
            style={s.modalCard}
            testID="lost-modal"
          >
            <Text
              style={
                s.modalTitle
              }
            >
              Por que a
              proposta foi
              perdida?
            </Text>

            <Text
              style={s.modalSub}
            >
              Obrigatório
              para ajudar a
              melhorar suas
              vendas
            </Text>

            <TextInput
              testID="lost-reason-input"
              style={
                s.modalInput
              }
              value={lostReason}
              onChangeText={
                setLostReason
              }
              placeholder="Ex: cliente escolheu concorrente"
              placeholderTextColor={
                theme.colors
                  .textMuted
              }
              multiline
            />

            <View
              style={{
                flexDirection:
                  "row",

                gap: 8,

                marginTop: 16,
              }}
            >
              <TouchableOpacity
                style={
                  s.modalCancel
                }
                onPress={() =>
                  setLostModal(
                    false
                  )
                }
              >
                <Text
                  style={{
                    color:
                      theme
                        .colors
                        .text,

                    fontWeight:
                      "700",
                  }}
                >
                  Cancelar
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                testID="lost-confirm"
                style={[
                  s.modalConfirm,
                  (!lostReason.trim() ||
                    busy) && {
                    opacity: 0.5,
                  },
                ]}
                disabled={
                  !lostReason.trim() ||
                  busy
                }
                onPress={() =>
                  changeStatus(
                    "perdido",
                    lostReason.trim()
                  )
                }
              >
                <Text
                  style={{
                    color:
                      "#fff",

                    fontWeight:
                      "700",
                  }}
                >
                  Confirmar
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      <UpgradeModal
        visible={upgradeOpen}
        message={upgradeMsg}
        onClose={() =>
          setUpgradeOpen(
            false
          )
        }
      />
    </SafeAreaView>
  );
}

function ActionBtn({
  icon,
  label,
  onPress,
  color,
  testID,
}: any) {
  return (
    <TouchableOpacity
      style={s.actBtn}
      onPress={onPress}
      testID={testID}
    >
      <View
        style={[
          s.actIcon,
          {
            backgroundColor:
              color ||
              theme.colors
                .primary,
          },
        ]}
      >
        <Ionicons
          name={icon}
          size={20}
          color="#fff"
        />
      </View>

      <Text style={s.actText}>
        {label}
      </Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor:
      theme.colors.bg,
  },

  topbar: {
    height: 52,

    paddingHorizontal: 16,

    flexDirection: "row",

    alignItems: "center",

    justifyContent:
      "space-between",
  },

  back: {
    padding: 4,
  },

  topTitle: {
    fontSize: 14,

    fontWeight: "700",

    color:
      theme.colors.textSec,
  },

  scroll: {
    padding: 24,

    paddingBottom: 120,

    gap: 12,
  },

  badge: {
    alignSelf:
      "flex-start",

    paddingHorizontal: 12,

    paddingVertical: 6,

    borderRadius: 999,

    borderWidth: 1,
  },

  badgeText: {
    fontSize: 12,

    fontWeight: "700",
  },

  staleCard: {
    flexDirection: "row",

    gap: 8,

    alignItems: "center",

    backgroundColor:
      "#FFFBEB",

    borderWidth: 1,

    borderColor:
      "#FDE68A",

    padding: 12,

    borderRadius: 12,
  },

  staleText: {
    color: theme.colors.text,

    fontSize: 13,

    flex: 1,
  },

  card: {
    backgroundColor: "#fff",

    borderWidth: 1,

    borderColor:
      theme.colors.border,

    padding: 16,

    borderRadius: 16,

    gap: 4,
  },

  h1: {
    fontSize: 22,

    fontWeight: "800",

    color: theme.colors.text,

    letterSpacing: -0.5,
  },

  sub: {
    color:
      theme.colors.textSec,

    fontSize: 14,
  },

  sectionLabel: {
    fontSize: 11,

    color:
      theme.colors.textMuted,

    fontWeight: "700",

    letterSpacing: 1,

    textTransform:
      "uppercase",

    marginBottom: 8,
  },

  sectionLabelBig: {
    fontSize: 11,

    color:
      theme.colors.textMuted,

    fontWeight: "700",

    letterSpacing: 1,

    textTransform:
      "uppercase",

    marginTop: 12,

    marginBottom: 4,
  },

  itemRow: {
    flexDirection: "row",

    justifyContent:
      "space-between",

    paddingVertical: 10,

    borderTopWidth: 1,

    borderTopColor:
      theme.colors.border,
  },

  itemName: {
    fontWeight: "600",

    color: theme.colors.text,
  },

  itemSub: {
    fontSize: 12,

    color:
      theme.colors.textSec,
  },
  
  itemDescription: {
  color: "#64748B",
  fontSize: 13,
  marginTop: 2,
  marginBottom: 4,
},

    itemTotal: {
    fontWeight: "700",

    color: theme.colors.text,
  },

  tableHeader: {
    flexDirection: "row",
    paddingVertical: 8,
    backgroundColor: "#F1F5F9",
    borderTopLeftRadius: 8,
    borderTopRightRadius: 8,
    paddingHorizontal: 8,
  },
  tableHeadCell: {
    fontSize: 11,
    fontWeight: "700",
    color: theme.colors.textSec,
    textTransform: "uppercase",
  },
  tableRow: {
    flexDirection: "row",
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    paddingHorizontal: 8,
    alignItems: "center",
  },
  tableCell: {
    fontSize: 13,
    color: theme.colors.text,
  },
  footerSummary: {
    marginTop: 16,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    gap: 6,
  },
  summaryRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  summaryLabel: {
    fontSize: 13,
    color: theme.colors.textSec,
  },
  summaryValue: {
    fontSize: 14,
    fontWeight: "600",
    color: theme.colors.text,
  },
  grandTotalRow: {
    marginTop: 6,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
  },
  grandTotalLabel: {
    fontSize: 15,
    fontWeight: "700",
    color: theme.colors.text,
  },
  grandTotalValue: {
    fontSize: 18,
    fontWeight: "800",
    color: theme.colors.primary,
  },

  totalRow: {
    marginTop: 8,

    paddingTop: 12,

    borderTopWidth: 1,

    borderTopColor:
      theme.colors.border,

    flexDirection: "row",

    justifyContent:
      "space-between",
  },

  totalLabel: {
    fontWeight: "700",

    color:
      theme.colors.textSec,
  },

  totalValue: {
    fontWeight: "800",

    fontSize: 18,

    color: theme.colors.text,
  },

  created: {
    fontSize: 12,

    color:
      theme.colors.textMuted,

    textAlign: "center",

    marginTop: 4,
  },

  grid: {
    flexDirection: "row",

    flexWrap: "wrap",

    gap: 8,
  },

  actBtn: {
    width: "48.5%",

    backgroundColor: "#fff",

    borderWidth: 1,

    borderColor:
      theme.colors.border,

    padding: 14,

    borderRadius: 14,

    flexDirection: "row",

    alignItems: "center",

    gap: 10,
  },

  actIcon: {
    width: 36,

    height: 36,

    borderRadius: 10,

    alignItems: "center",

    justifyContent:
      "center",
  },

  actText: {
    fontWeight: "700",

    color: theme.colors.text,

    flex: 1,
  },

  statBtn: {
    flex: 1,

    minWidth: "48%",

    height: 52,

    flexDirection: "row",

    alignItems: "center",

    justifyContent:
      "center",

    gap: 6,

    borderRadius: 12,
  },

  statText: {
    color: "#fff",

    fontWeight: "700",
  },

  reopenBtn: {
    marginTop: 8,

    height: 52,

    flexDirection: "row",

    gap: 8,

    alignItems: "center",

    justifyContent:
      "center",

    backgroundColor: "#fff",

    borderWidth: 1,

    borderColor:
      theme.colors.border,

    borderRadius: 12,
  },

  reopenText: {
    color: theme.colors.text,

    fontWeight: "700",
  },

  previewImage: {
    width: 220,
    height: 220,
    borderRadius: 16,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: "#ddd",
},

  modalRoot: {
    flex: 1,

    backgroundColor:
      "rgba(0,0,0,0.5)",

    justifyContent:
      "center",

    padding: 24,
  },

  modalCard: {
    backgroundColor: "#fff",

    borderRadius: 16,

    padding: 20,
  },

  modalTitle: {
    fontSize: 18,

    fontWeight: "800",

    color: theme.colors.text,
  },

  modalSub: {
    color:
      theme.colors.textSec,

    fontSize: 13,

    marginTop: 4,

    marginBottom: 12,
  },

  modalInput: {
    minHeight: 80,

    borderRadius: 12,

    borderWidth: 1,

    borderColor:
      theme.colors.border,

    padding: 12,

    fontSize: 15,

    color: theme.colors.text,

    textAlignVertical:
      "top",
  },

  modalCancel: {
    flex: 1,

    height: 48,

    borderRadius: 12,

    borderWidth: 1,

    borderColor:
      theme.colors.border,

    alignItems: "center",

    justifyContent:
      "center",
  },

  modalConfirm: {
    flex: 1,

    height: 48,

    borderRadius: 12,

    backgroundColor:
      theme.colors
        .statusLostText,

    alignItems: "center",

    justifyContent:
      "center",
  },

  convertBtn: {
    backgroundColor: "#3B82F6",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
    alignItems: "center",
    justifyContent: "center",
  },

  convertBtnText: {
    color: "#fff",
    fontSize: 10,
    fontWeight: "700",
  },
  viewedCard: {
    backgroundColor: "#F0FDF4",
    borderWidth: 1,
    borderColor: "#BBF7D0",
    padding: 16,
    borderRadius: 16,
    gap: 12,
  },
  viewedText: {
    color: theme.colors.text,
    fontSize: 13,
    flex: 1,
  },
  viewedBtn: {
    backgroundColor: "#25D366",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 10,
    gap: 8,
    alignSelf: "flex-start",
  },
  viewedBtnText: {
    color: "#fff",
    fontWeight: "700",
    fontSize: 13,
  },
  viewedStatusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: 4,
  },
  viewedStatusText: {
    fontSize: 12,
    fontWeight: "600",
    color: theme.colors.success,
  },
});