import React, {
  useCallback,
  useEffect,
  useState,
} from "react";

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
  useWindowDimensions,
  Modal,
} from "react-native";

import { SafeAreaView } from "react-native-safe-area-context";

import { Ionicons } from "@expo/vector-icons";

import * as ImagePicker from "expo-image-picker";

import {
  useFocusEffect,
  useRouter,
} from "expo-router";

import {
  api,
  formatApiError,
} from "../../src/api";

import { theme, getRoleLabel } from "../../src/theme";

import { useAuth } from "../../src/auth";

type SubscriptionState = {
  plan: "free" | "pro";
  is_pro: boolean;
  is_trial: boolean;
  pro_until?: string | null;
  month_count?: number;
  month_quota?: number | null;
};

export default function Profile() {
  const { user, logout } =
    useAuth();

  const router = useRouter();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;

  const [
    companyName,
    setCompanyName,
  ] = useState("");

  const [cnpj, setCnpj] =
    useState("");

  const [phone, setPhone] =
    useState("");

  const [email, setEmail] =
    useState("");

  const [address, setAddress] =
    useState("");

  const [logo, setLogo] =
    useState("");

  const [loading, setLoading] =
    useState(true);

  const [saving, setSaving] =
    useState(false);

  const [
    subscription,
    setSubscription,
  ] =
    useState<SubscriptionState | null>(
      null
    );

  const [activeTab, setActiveTab] = useState<"empresa" | "users">("empresa");
  const [usersList, setUsersList] = useState<any[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [userModalVisible, setUserModalVisible] = useState(false);
  const [editingUser, setEditingUser] = useState<any | null>(null);

  const [formName, setFormName] = useState("");
  const [formEmail, setFormEmail] = useState("");
  const [formPassword, setFormPassword] = useState("");
  const [formRole, setFormRole] = useState<"admin" | "seller">("seller");
  const [formPhone, setFormPhone] = useState("");
  const [formWhatsapp, setFormWhatsapp] = useState("");
  const [sendInvite, setSendInvite] = useState(true);

  const [reactivateEmail, setReactivateEmail] = useState("");
  const [reactivateModalVisible, setReactivateModalVisible] = useState(false);

  const loadUsers = async () => {
    try {
      setLoadingUsers(true);
      const res = await api.get("/users");
      setUsersList(res.data.map((u: any) => ({ ...u, status: u.active !== false ? "Ativo" : "Inativo" })));
    } catch (e) {
      console.log("Error loading users:", e);
    } finally {
      setLoadingUsers(false);
    }
  };

  useEffect(() => {
    if (activeTab === "users" && user?.role !== "seller") {
      loadUsers();
    }
  }, [activeTab, user?.role]);

  const clearForm = () => {
    setFormName("");
    setFormEmail("");
    setFormPassword("");
    setFormRole("seller");
    setFormPhone("");
    setFormWhatsapp("");
    setEditingUser(null);
    setSendInvite(true);
  };

  const openEditUser = (u: any) => {
    setEditingUser(u);
    setFormName(u.name);
    setFormEmail(u.email);
    setFormPassword("");
    setFormRole(u.role === "admin" ? "admin" : "seller");
    setFormPhone(u.phone || "");
    setFormWhatsapp(u.whatsapp || "");
    setSendInvite(false);
    setUserModalVisible(true);
  };

  const handleCreateUser = async () => {
    if (!formName.trim() || !formEmail.trim() || !formPassword.trim()) {
      Alert.alert("Erro", "Preencha todos os campos obrigatórios.");
      return;
    }
    try {
      setSaving(true);
      await api.post("/users", {
        name: formName.trim(),
        email: formEmail.trim().toLowerCase(),
        password: formPassword,
        role: formRole,
        phone: formPhone.trim(),
        whatsapp: formWhatsapp.trim()
      });
      Alert.alert("Pronto!", "Usuário criado com sucesso.");
      setUserModalVisible(false);
      clearForm();
      loadUsers();
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateUser = async () => {
    if (!editingUser) return;
    if (!formName.trim() || !formEmail.trim()) {
      Alert.alert("Erro", "Preencha os campos Nome e E-mail.");
      return;
    }
    try {
      setSaving(true);
      const payload: any = {
        name: formName.trim(),
        email: formEmail.trim().toLowerCase(),
        role: formRole,
        phone: formPhone.trim(),
        whatsapp: formWhatsapp.trim()
      };
      if (formPassword.trim()) {
        payload.password = formPassword;
      }
      await api.put(`/users/${editingUser.id}`, payload);
      Alert.alert("Pronto!", "Usuário atualizado com sucesso.");
      setUserModalVisible(false);
      clearForm();
      loadUsers();
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setSaving(false);
    }
  };

  const handleInactivateUser = async (userId: string) => {
    Alert.alert(
      "Confirmar Inativação",
      "Tem certeza que deseja inativar este usuário? Ele perderá o acesso imediatamente.",
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Inativar",
          style: "destructive",
          onPress: async () => {
            try {
              setLoadingUsers(true);
              await api.delete(`/users/${userId}`);
              Alert.alert("Pronto!", "Usuário inativado.");
              setUsersList(prev => prev.map(u => u.id === userId ? { ...u, active: false, status: "Inativo" } : u));
            } catch (e) {
              Alert.alert("Erro", formatApiError(e));
            } finally {
              setLoadingUsers(false);
            }
          }
        }
      ]
    );
  };

  const handleActivateUser = async (userId: string) => {
    try {
      setLoadingUsers(true);
      await api.patch(`/users/${userId}/activate`);
      Alert.alert("Pronto!", "Usuário ativado.");
      setUsersList(prev => prev.map(u => u.id === userId ? { ...u, active: true, status: "Ativo" } : u));
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setLoadingUsers(false);
    }
  };

  const handleReactivateByEmail = async () => {
    if (!reactivateEmail.trim()) {
      Alert.alert("Erro", "Por favor, digite o e-mail.");
      return;
    }
    try {
      setLoadingUsers(true);
      const auditRes = await api.get("/audit");
      const logs = auditRes.data.data || [];
      const foundLog = logs.find((log: any) => {
        const isUser = log.entity_type === "user";
        const matchOld = log.old_value && log.old_value.email?.toLowerCase() === reactivateEmail.toLowerCase().trim();
        const matchNew = log.new_value && log.new_value.email?.toLowerCase() === reactivateEmail.toLowerCase().trim();
        return isUser && (matchOld || matchNew);
      });

      if (!foundLog) {
        Alert.alert("Não encontrado", "Não foi possível localizar nenhum usuário inativo com este e-mail nos logs de auditoria.");
        return;
      }

      const userId = foundLog.entity_id;
      await api.patch(`/users/${userId}/activate`);
      Alert.alert("Pronto!", "Usuário reativado com sucesso.");
      setReactivateEmail("");
      setReactivateModalVisible(false);
      loadUsers();
    } catch (e) {
      Alert.alert("Erro", formatApiError(e));
    } finally {
      setLoadingUsers(false);
    }
  };

  const formatRole = (role: string) => {
    return getRoleLabel(role);
  };

  const load = useCallback(
    async () => {
      try {
        setLoading(true);

        const [
          companyRes,
          subRes,
        ] = await Promise.all([
          api.get("/company"),
          api.get(
            "/subscription/me"
          ),
        ]);

        const data =
          companyRes.data;

        setCompanyName(
          data.company_name || ""
        );

        setCnpj(
          data.cnpj || ""
        );

        setPhone(
          data.phone || ""
        );

        setEmail(
          data.email || ""
        );

        setAddress(
          data.address || ""
        );

        setLogo(
          data.logo_base64 || ""
        );

        setSubscription(
          subRes.data
        );
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const pickLogo = async () => {
    const perm =
      await ImagePicker.requestMediaLibraryPermissionsAsync();

    if (!perm.granted) {
      Alert.alert(
        "Permissão",
        "Permita o acesso à galeria para adicionar a logo."
      );

      return;
    }

    const r =
      await ImagePicker.launchImageLibraryAsync(
        {
          mediaTypes:
            ImagePicker.MediaTypeOptions
              .Images,

          base64: true,

          quality: 0.8,

          allowsEditing: true,

          aspect: [1, 1],
        }
      );

    if (
      !r.canceled &&
      r.assets?.[0]?.base64
    ) {
      const a = r.assets[0];

      setLogo(
        `data:${
          a.mimeType ||
          "image/jpeg"
        };base64,${
          a.base64
        }`
      );
    }
  };

  const save = async () => {
    try {
      setSaving(true);

      await api.put(
        "/company",
        {
          company_name:
            companyName,

          cnpj,

          phone,

          email,

          address,

          logo_base64: logo,
        }
      );

      Alert.alert(
        "Pronto!",
        "Dados da empresa salvos."
      );
    } catch (e) {
      Alert.alert(
        "Erro",
        formatApiError(e)
      );
    } finally {
      setSaving(false);
    }
  };

  const renderQuotaProgress = () => {
    const isPro = subscription?.is_pro;
    const maxUsers = isPro ? 10 : 1;
    const activeCount = usersList.filter(u => u.active !== false).length;
    const percent = Math.min((activeCount / maxUsers) * 100, 100);
    
    return (
      <View style={s.quotaContainer}>
        <View style={s.quotaHeaderRow}>
          <View>
            <Text style={s.quotaPlanTitle}>{isPro ? "Plano Pro" : "Plano Free"}</Text>
            <Text style={s.quotaUsageText}>{activeCount} de {maxUsers} usuários utilizados</Text>
          </View>
          <Ionicons name="people-outline" size={24} color={theme.colors.primary} />
        </View>
        <View style={s.progressBarBackground}>
          <View style={[s.progressBarFill, { width: `${percent}%` }]} />
        </View>
      </View>
    );
  };

  const renderUsersTab = () => {
    const isOwner = user?.role === "owner";
    
    return (
      <View style={s.usersTabContainer}>
        {renderQuotaProgress()}
        
        <View style={s.usersHeaderRow}>
          <Text style={s.usersSectionTitle}>Equipe da Empresa</Text>
          {isOwner && (
            <TouchableOpacity 
              style={s.newUserBtn} 
              onPress={() => {
                clearForm();
                setUserModalVisible(true);
              }}
              testID="btn-new-user"
            >
              <Ionicons name="add" size={20} color="#fff" />
              <Text style={s.newUserBtnText}>Novo Usuário</Text>
            </TouchableOpacity>
          )}
        </View>

        {loadingUsers ? (
          <ActivityIndicator color={theme.colors.primary} style={{ marginVertical: 32 }} />
        ) : (
          <View style={s.usersListContainer}>
            {usersList.length === 0 ? (
              <Text style={s.noUsersText}>Nenhum usuário cadastrado.</Text>
            ) : (
              isDesktop ? renderUsersTable() : renderUsersCards()
            )}
          </View>
        )}

        {isOwner && (
          <TouchableOpacity
            style={s.reactivateHelpBtn}
            onPress={() => {
              setReactivateEmail("");
              setReactivateModalVisible(true);
            }}
          >
            <Ionicons name="refresh-circle-outline" size={18} color={theme.colors.primary} />
            <Text style={s.reactivateHelpText}>Reativar Usuário Inativo</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  };

  const renderUsersTable = () => {
    const isOwner = user?.role === "owner";
    return (
      <View style={s.tableContainer}>
        <View style={s.tableHeader}>
          <Text style={[s.tableHeaderCell, { flex: 2 }]}>Nome</Text>
          <Text style={[s.tableHeaderCell, { flex: 2 }]}>E-mail</Text>
          <Text style={[s.tableHeaderCell, { flex: 1 }]}>Perfil</Text>
          <Text style={[s.tableHeaderCell, { flex: 1 }]}>Status</Text>
          {isOwner && <Text style={[s.tableHeaderCell, { flex: 1, textAlign: "right" }]}>Ações</Text>}
        </View>
        {usersList.map((u) => {
          const isOwnerRow = u.role === "owner";
          
          return (
            <View key={u.id} style={s.tableRow}>
              <Text style={[s.tableCell, { flex: 2 }]} numberOfLines={1}>{u.name}</Text>
              <Text style={[s.tableCell, { flex: 2 }]} numberOfLines={1}>{u.email}</Text>
              <Text style={[s.tableCell, { flex: 1 }]}>{formatRole(u.role)}</Text>
              <View style={{ flex: 1, flexDirection: "row", alignItems: "center" }}>
                <View style={[s.statusIndicator, u.active !== false ? s.statusActive : s.statusInactive]} />
                <Text style={s.statusText}>{u.active !== false ? "Ativo" : "Inativo"}</Text>
              </View>
              {isOwner && (
                <View style={{ flex: 1, flexDirection: "row", justifyContent: "flex-end", gap: 8 }}>
                  {!isOwnerRow && (
                    <>
                      <TouchableOpacity 
                        style={s.actionIconBtn} 
                        onPress={() => openEditUser(u)}
                        testID={`edit-user-${u.id}`}
                      >
                        <Ionicons name="create-outline" size={18} color={theme.colors.primary} />
                      </TouchableOpacity>
                      {u.active !== false ? (
                        <TouchableOpacity 
                          style={s.actionIconBtn} 
                          onPress={() => handleInactivateUser(u.id)}
                          testID={`inactivate-user-${u.id}`}
                        >
                          <Ionicons name="trash-outline" size={18} color={theme.colors.danger} />
                        </TouchableOpacity>
                      ) : (
                        <TouchableOpacity 
                          style={s.actionIconBtn} 
                          onPress={() => handleActivateUser(u.id)}
                          testID={`activate-user-${u.id}`}
                        >
                          <Ionicons name="checkmark-circle-outline" size={18} color="#22C55E" />
                        </TouchableOpacity>
                      )}
                    </>
                  )}
                </View>
              )}
            </View>
          );
        })}
      </View>
    );
  };

  const renderUsersCards = () => {
    const isOwner = user?.role === "owner";
    return (
      <View style={{ gap: 12 }}>
        {usersList.map((u) => {
          const isOwnerRow = u.role === "owner";
          return (
            <View key={u.id} style={s.userCardItem}>
              <View style={s.userCardHeader}>
                <View style={{ flex: 1 }}>
                  <Text style={s.userCardName}>{u.name}</Text>
                  <Text style={s.userCardEmail}>{u.email}</Text>
                  {u.phone ? <Text style={s.userCardEmail}>Telefone: {u.phone}</Text> : null}
                  {u.whatsapp ? <Text style={s.userCardEmail}>WhatsApp: {u.whatsapp}</Text> : null}
                </View>
                <View style={[s.badgeCompact, u.active !== false ? s.badgeActive : s.badgeInactive]}>
                  <Text style={[s.badgeCompactText, u.active !== false ? s.badgeActiveText : s.badgeInactiveText]}>
                    {u.active !== false ? "Ativo" : "Inativo"}
                  </Text>
                </View>
              </View>
              <View style={s.userCardFooter}>
                <Text style={s.userCardRole}>Perfil: {formatRole(u.role)}</Text>
                {isOwner && !isOwnerRow && (
                  <View style={{ flexDirection: "row", gap: 12 }}>
                    <TouchableOpacity style={s.cardActionBtn} onPress={() => openEditUser(u)}>
                      <Ionicons name="create-outline" size={16} color={theme.colors.primary} />
                      <Text style={s.cardActionText}>Editar</Text>
                    </TouchableOpacity>
                    {u.active !== false ? (
                      <TouchableOpacity style={s.cardActionBtn} onPress={() => handleInactivateUser(u.id)}>
                        <Ionicons name="trash-outline" size={16} color={theme.colors.danger} />
                        <Text style={[s.cardActionText, { color: theme.colors.danger }]}>Inativar</Text>
                      </TouchableOpacity>
                    ) : (
                      <TouchableOpacity style={s.cardActionBtn} onPress={() => handleActivateUser(u.id)}>
                        <Ionicons name="checkmark-circle-outline" size={16} color="#22C55E" />
                        <Text style={[s.cardActionText, { color: "#22C55E" }]}>Ativar</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                )}
              </View>
            </View>
          );
        })}
      </View>
    );
  };

  const renderUserModal = () => {
    const isEditing = !!editingUser;
    return (
      <Modal visible={userModalVisible} transparent animationType="fade" onRequestClose={() => setUserModalVisible(false)}>
        <View style={s.modalOverlay}>
          <View style={s.modalCard}>
            <View style={s.modalHeader}>
              <Text style={s.modalTitle}>{isEditing ? "Editar Usuário" : "Novo Usuário"}</Text>
              <TouchableOpacity onPress={() => setUserModalVisible(false)}>
                <Ionicons name="close" size={24} color={theme.colors.textSec} />
              </TouchableOpacity>
            </View>

            <ScrollView contentContainerStyle={s.modalContent} style={{ maxHeight: 450 }}>
              <View style={{ gap: 6 }}>
                <Text style={s.modalLabel}>Nome</Text>
                <TextInput
                  style={s.modalInput}
                  placeholder="Nome do usuário"
                  value={formName}
                  onChangeText={setFormName}
                  placeholderTextColor={theme.colors.textMuted}
                  testID="user-form-name"
                />
              </View>

              <View style={{ gap: 6 }}>
                <Text style={s.modalLabel}>E-mail</Text>
                <TextInput
                  style={s.modalInput}
                  placeholder="email@empresa.com"
                  value={formEmail}
                  onChangeText={setFormEmail}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  placeholderTextColor={theme.colors.textMuted}
                  testID="user-form-email"
                />
              </View>

              <View style={{ gap: 6 }}>
                <Text style={s.modalLabel}>Telefone</Text>
                <TextInput
                  style={s.modalInput}
                  placeholder="Ex: (11) 99999-9999"
                  value={formPhone}
                  onChangeText={setFormPhone}
                  keyboardType="phone-pad"
                  placeholderTextColor={theme.colors.textMuted}
                  testID="user-form-phone"
                />
              </View>

              <View style={{ gap: 6 }}>
                <Text style={s.modalLabel}>WhatsApp (opcional)</Text>
                <TextInput
                  style={s.modalInput}
                  placeholder="Ex: (11) 99999-9999"
                  value={formWhatsapp}
                  onChangeText={setFormWhatsapp}
                  keyboardType="phone-pad"
                  placeholderTextColor={theme.colors.textMuted}
                  testID="user-form-whatsapp"
                />
              </View>

              <View style={{ gap: 6 }}>
                <Text style={s.modalLabel}>{isEditing ? "Nova Senha (opcional)" : "Senha Temporária"}</Text>
                <TextInput
                  style={s.modalInput}
                  placeholder={isEditing ? "Mantenha em branco para não alterar" : "Mínimo 6 caracteres"}
                  value={formPassword}
                  onChangeText={setFormPassword}
                  secureTextEntry
                  placeholderTextColor={theme.colors.textMuted}
                  testID="user-form-password"
                />
              </View>

              <View style={{ gap: 6 }}>
                <Text style={s.modalLabel}>Perfil</Text>
                <View style={s.roleSelectorContainer}>
                  <TouchableOpacity
                    style={[s.roleSelectorBtn, formRole === "seller" && s.roleSelectorBtnActive]}
                    onPress={() => setFormRole("seller")}
                    testID="role-seller"
                  >
                    <Ionicons name="people" size={16} color={formRole === "seller" ? "#fff" : theme.colors.textSec} />
                    <Text style={[s.roleSelectorText, formRole === "seller" && s.roleSelectorTextActive]}>Consultor Comercial</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[s.roleSelectorBtn, formRole === "admin" && s.roleSelectorBtnActive]}
                    onPress={() => setFormRole("admin")}
                    testID="role-admin"
                  >
                    <Ionicons name="shield-half" size={16} color={formRole === "admin" ? "#fff" : theme.colors.textSec} />
                    <Text style={[s.roleSelectorText, formRole === "admin" && s.roleSelectorTextActive]}>Administrador</Text>
                  </TouchableOpacity>
                </View>
              </View>

              {!isEditing && (
                <TouchableOpacity
                  style={s.checkboxContainer}
                  onPress={() => setSendInvite(!sendInvite)}
                  activeOpacity={0.8}
                >
                  <View style={[s.checkbox, sendInvite && s.checkboxChecked]}>
                    {sendInvite && <Ionicons name="checkmark" size={14} color="#fff" />}
                  </View>
                  <View>
                    <Text style={s.checkboxLabel}>Enviar convite por e-mail</Text>
                    <Text style={s.checkboxSub}>O usuário receberá os dados de acesso</Text>
                  </View>
                </TouchableOpacity>
              )}
            </ScrollView>

            <View style={s.modalFooter}>
              <TouchableOpacity style={s.btnCancel} onPress={() => setUserModalVisible(false)}>
                <Text style={s.btnCancelText}>Cancelar</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={s.btnConfirm}
                onPress={isEditing ? handleUpdateUser : handleCreateUser}
                testID="user-submit"
              >
                <Text style={s.btnConfirmText}>{isEditing ? "Salvar" : "Criar"}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    );
  };

  const renderReactivateModal = () => {
    return (
      <Modal visible={reactivateModalVisible} transparent animationType="fade" onRequestClose={() => setReactivateModalVisible(false)}>
        <View style={s.modalOverlay}>
          <View style={s.modalCard}>
            <View style={s.modalHeader}>
              <Text style={s.modalTitle}>Reativar Usuário</Text>
              <TouchableOpacity onPress={() => setReactivateModalVisible(false)}>
                <Ionicons name="close" size={24} color={theme.colors.textSec} />
              </TouchableOpacity>
            </View>

            <View style={s.modalContent}>
              <Text style={s.reactivateHelpDesc}>
                Digite o e-mail do usuário que foi anteriormente inativado para reativar seu acesso.
              </Text>
              <View style={{ gap: 6 }}>
                <Text style={s.modalLabel}>E-mail</Text>
                <TextInput
                  style={s.modalInput}
                  placeholder="email@empresa.com"
                  value={reactivateEmail}
                  onChangeText={setReactivateEmail}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  placeholderTextColor={theme.colors.textMuted}
                  testID="reactivate-email-input"
                />
              </View>
            </View>

            <View style={s.modalFooter}>
              <TouchableOpacity style={s.btnCancel} onPress={() => setReactivateModalVisible(false)}>
                <Text style={s.btnCancelText}>Cancelar</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={s.btnConfirm}
                onPress={handleReactivateByEmail}
                testID="reactivate-submit"
              >
                <Text style={s.btnConfirmText}>Reativar</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    );
  };

  const renderTrialProgress = () => {
    if (!user || user.trial_days_remaining === null || user.trial_days_remaining === undefined) {
      return null;
    }

    const days = user.trial_days_remaining;
    const totalDays = 60;
    const progress = Math.max(0, Math.min(1, days / totalDays));

    let barColor = "#22C55E"; // Green
    if (days < 10) {
      barColor = "#EF4444"; // Red
    } else if (days < 20) {
      barColor = "#EAB308"; // Yellow
    }

    return (
      <View style={s.trialCard} testID="trial-progress-card">
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <Text style={s.trialTitle}>Período de Teste</Text>
          <Text style={s.trialDaysText}>
            {user.trial_is_expired ? "Expirado" : `${days} ${days === 1 ? "dia restante" : "dias restantes"}`}
          </Text>
        </View>
        <View style={s.progressBarBackground}>
          <View style={[s.progressBarFill, { width: `${progress * 100}%`, backgroundColor: barColor }]} />
        </View>
      </View>
    );
  };

  const renderDesktop = () => (
    <ScrollView
      contentContainerStyle={s.desktopScroll}
    >
      <View style={s.desktopHeader}>
        <View>
          <Text style={s.title}>Minha empresa</Text>
          <Text style={s.subtitle}>
            Gerencie as informações da empresa e usuários
          </Text>
        </View>

        {activeTab === "empresa" && (
          <TouchableOpacity
            style={s.desktopActionButton}
            onPress={save}
            disabled={saving}
            testID="save-company-desktop"
          >
            {saving ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Ionicons
                  name="save-outline"
                  size={20}
                  color="#fff"
                />
                <Text style={s.desktopActionText}>
                  Salvar alterações
                </Text>
              </>
            )}
          </TouchableOpacity>
        )}
      </View>

      {user?.role !== "seller" && (
        <View style={s.tabBar}>
          <TouchableOpacity
            style={[s.tabButton, activeTab === "empresa" && s.tabButtonActive]}
            onPress={() => setActiveTab("empresa")}
          >
            <Text style={[s.tabButtonText, activeTab === "empresa" && s.tabButtonTextActive]}>
              Empresa
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.tabButton, activeTab === "users" && s.tabButtonActive]}
            onPress={() => setActiveTab("users")}
          >
            <Text style={[s.tabButtonText, activeTab === "users" && s.tabButtonTextActive]}>
              Usuários
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {activeTab === "empresa" ? (
        <View style={s.desktopColumns}>
          <View style={s.desktopLeft}>
            <View style={s.panelCard}>
              <Text style={s.sectionTitle}>Dados da empresa</Text>
              <Input
                testID="inp-company-name"
                label="Nome da empresa"
                value={companyName}
                onChangeText={setCompanyName}
              />
              <Input
                testID="inp-company-cnpj"
                label="CNPJ"
                value={cnpj}
                onChangeText={setCnpj}
                keyboardType="number-pad"
              />
            </View>

            <View style={s.panelCard}>
              <Text style={s.sectionTitle}>Contatos</Text>
              <Input
                testID="inp-company-phone"
                label="Telefone"
                value={phone}
                onChangeText={setPhone}
                keyboardType="phone-pad"
              />
              <Input
                testID="inp-company-email"
                label="Email"
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
              />
            </View>

            <View style={s.panelCard}>
              <Text style={s.sectionTitle}>Endereço</Text>
              <Input
                testID="inp-company-address"
                label="Endereço"
                value={address}
                onChangeText={setAddress}
                multiline
              />
            </View>
          </View>

          <View style={s.desktopRight}>
            {renderTrialProgress()}
            <View style={s.panelCard}>
              <Text style={s.sectionTitle}>Logo</Text>
              <TouchableOpacity
                style={s.logoWrap}
                onPress={pickLogo}
                testID="pick-logo"
              >
                {logo ? (
                  <Image
                    source={{ uri: logo }}
                    style={s.logo}
                  />
                ) : (
                  <View style={s.logoPh}>
                    <Ionicons
                      name="image-outline"
                      size={28}
                      color={theme.colors.textMuted}
                    />
                    <Text style={s.logoPhText}>
                      Toque para adicionar logo
                    </Text>
                  </View>
                )}
              </TouchableOpacity>
            </View>

            <View style={[s.panelCard, s.proCard]}> 
              <View style={s.proCardHeader}>
                <View style={s.proBadgeRow}>
                  <View style={[s.badge, { backgroundColor: planColor }]}> 
                    <Ionicons
                      name="sparkles"
                      size={14}
                      color="#fff"
                    />
                    <Text style={s.badgeText}>{planText}</Text>
                  </View>
                </View>
                <Ionicons
                  name="diamond"
                  size={22}
                  color="#fff"
                />
              </View>

              <Text style={s.proTitle}>
                {subscription?.is_pro
                  ? "Experiência premium desbloqueada 🚀"
                  : "Desbloqueie o modo Pro"}
              </Text>
              <Text style={s.proDesc}>{planDescription}</Text>
              {validUntil && (
                <Text style={s.proUntil}>
                  Acesso ativo até {validUntil}
                </Text>
              )}
              {!subscription?.is_pro && (
                <TouchableOpacity
                  style={s.upgradeBtn}
                  onPress={() => router.push("/subscription")}
                >
                  <Ionicons
                    name="rocket"
                    size={18}
                    color="#0F172A"
                  />
                  <Text style={s.upgradeText}>Virar Pro agora</Text>
                </TouchableOpacity>
              )}
            </View>

            <TouchableOpacity
              style={s.planCta}
              onPress={() => router.push("/subscription")}
              testID="open-subscription"
            >
              <View style={s.planIcon}>
                <Ionicons name="star" size={18} color="#fff" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.planTitle}>Plano Pro</Text>
                <Text style={s.planDesc}>
                  Propostas ilimitadas + recursos avançados
                </Text>
              </View>
              <Ionicons
                name="chevron-forward"
                size={20}
                color={theme.colors.textMuted}
              />
            </TouchableOpacity>

            <TouchableOpacity
              style={s.planCta}
              onPress={() => router.push("/referral")}
              testID="open-referral"
            >
              <View style={[s.planIcon, { backgroundColor: theme.colors.whatsapp }]}> 
                <Ionicons name="gift" size={18} color="#fff" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.planTitle}>Indique e ganhe 30 dias Pro</Text>
                <Text style={s.planDesc}>
                  Você e seu amigo ganham. Compartilhe agora 🎁
                </Text>
              </View>
              <Ionicons
                name="chevron-forward"
                size={20}
                color={theme.colors.textMuted}
              />
            </TouchableOpacity>

            <View style={s.panelCard}>
              <Text style={s.sectionTitle}>Conta</Text>
              <Text style={s.userName}>{user?.name}</Text>
              <Text style={s.userEmail}>{user?.email}</Text>
            </View>

            <TouchableOpacity
              style={s.logoutDesktop}
              onPress={logout}
              testID="logout-button"
            >
              <Ionicons
                name="log-out-outline"
                size={20}
                color={theme.colors.danger}
              />
              <Text style={s.logoutText}>Sair da conta</Text>
            </TouchableOpacity>
          </View>
        </View>
      ) : (
        renderUsersTab()
      )}
    </ScrollView>
  );

  const planText =
    subscription?.is_pro
      ? subscription?.is_trial
        ? "TRIAL PRO"
        : "PRO ATIVO"
      : "PLANO FREE";

  const planColor =
    subscription?.is_pro
      ? "#22C55E"
      : "#64748B";

  const planDescription =
    subscription?.is_pro
      ? "Você possui propostas ilimitadas e recursos premium."
      : `Você usou ${
          subscription?.month_count ||
          0
        }/${
          subscription?.month_quota ||
          10
        } propostas gratuitas este mês.`;

  const validUntil =
    subscription?.pro_until
      ? new Date(
          subscription.pro_until
        ).toLocaleDateString(
          "pt-BR"
        )
      : null;

  if (loading) {
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

  return (
    <SafeAreaView
      style={s.root}
      edges={["top"]}
      testID="profile-screen"
    >
      {isDesktop ? (
        renderDesktop()
      ) : (
        <KeyboardAvoidingView
          behavior={
            Platform.OS === "ios"
              ? "padding"
              : undefined
          }
          style={{ flex: 1 }}
        >
          <ScrollView
            contentContainerStyle={
              s.scroll
            }
            keyboardShouldPersistTaps="handled"
          >
            <View style={s.header}>
              <View>
                <Text style={s.title}>
                  Minha empresa
                </Text>

                <Text
                  style={s.subtitle}
                >
                  Gerencie as informações da empresa e usuários
                </Text>
              </View>
            </View>

            {user?.role !== "seller" && (
              <View style={s.tabBar}>
                <TouchableOpacity
                  style={[s.tabButton, activeTab === "empresa" && s.tabButtonActive]}
                  onPress={() => setActiveTab("empresa")}
                >
                  <Text style={[s.tabButtonText, activeTab === "empresa" && s.tabButtonTextActive]}>
                    Empresa
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.tabButton, activeTab === "users" && s.tabButtonActive]}
                  onPress={() => setActiveTab("users")}
                >
                  <Text style={[s.tabButtonText, activeTab === "users" && s.tabButtonTextActive]}>
                    Usuários
                  </Text>
                </TouchableOpacity>
              </View>
            )}

            {activeTab === "empresa" ? (
              <>
                {renderTrialProgress()}
                {/* PREMIUM CARD */}

                <View
                  style={[
                    s.proCard,
                    subscription?.is_pro &&
                      s.proCardActive,
                  ]}
                >
                  <View
                    style={
                      s.proCardHeader
                    }
                  >
                    <View
                      style={{
                        flexDirection:
                          "row",

                        alignItems:
                          "center",

                        gap: 8,
                      }}
                    >
                      <View
                        style={[
                          s.badge,

                          {
                            backgroundColor:
                              planColor,
                          },
                        ]}
                      >
                        <Ionicons
                          name="sparkles"
                          size={14}
                          color="#fff"
                        />

                        <Text
                          style={
                            s.badgeText
                          }
                        >
                          {planText}
                        </Text>
                      </View>
                    </View>

                    <Ionicons
                      name="diamond"
                      size={22}
                      color="#fff"
                    />
                  </View>

                  <Text
                    style={
                      s.proTitle
                    }
                  >
                    {subscription?.is_pro
                      ? "Experiência premium desbloqueada 🚀"
                      : "Desbloqueie o modo Pro"}
                  </Text>

                  <Text
                    style={s.proDesc}
                  >
                    {
                      planDescription
                    }
                  </Text>

                  {validUntil && (
                    <Text
                      style={
                        s.proUntil
                      }
                    >
                      Acesso ativo até{" "}
                      {validUntil}
                    </Text>
                  )}

                  {!subscription?.is_pro && (
                    <TouchableOpacity
                      style={
                        s.upgradeBtn
                      }
                      onPress={() =>
                        router.push(
                          "/subscription"
                        )
                      }
                    >
                      <Ionicons
                        name="rocket"
                        size={18}
                        color="#0F172A"
                      />

                      <Text
                        style={
                          s.upgradeText
                        }
                      >
                        Virar Pro agora
                      </Text>
                    </TouchableOpacity>
                  )}
                </View>

                <TouchableOpacity
                  style={s.logoWrap}
                  onPress={pickLogo}
                  testID="pick-logo"
                >
                  {logo ? (
                    <Image
                      source={{
                        uri: logo,
                      }}
                      style={s.logo}
                    />
                  ) : (
                    <View
                      style={s.logoPh}
                    >
                      <Ionicons
                        name="image-outline"
                        size={28}
                        color={
                          theme.colors
                            .textMuted
                        }
                      />

                      <Text
                        style={
                          s.logoPhText
                        }
                      >
                        Toque para adicionar
                        logo
                      </Text>
                    </View>
                  )}
                </TouchableOpacity>

                <Input
                  testID="inp-company-name"
                  label="Nome da empresa"
                  value={companyName}
                  onChangeText={
                    setCompanyName
                  }
                />

                <Input
                  testID="inp-company-cnpj"
                  label="CNPJ"
                  value={cnpj}
                  onChangeText={
                    setCnpj
                  }
                  keyboardType="number-pad"
                />

                <Input
                  testID="inp-company-phone"
                  label="Telefone"
                  value={phone}
                  onChangeText={
                    setPhone
                  }
                  keyboardType="phone-pad"
                />

                <Input
                  testID="inp-company-email"
                  label="Email"
                  value={email}
                  onChangeText={
                    setEmail
                  }
                  keyboardType="email-address"
                  autoCapitalize="none"
                />

                <Input
                  testID="inp-company-address"
                  label="Endereço"
                  value={address}
                  onChangeText={
                    setAddress
                  }
                  multiline
                />

                <TouchableOpacity
                  testID="save-company"
                  style={[
                    s.cta,

                    saving && {
                      opacity: 0.7,
                    },
                  ]}
                  onPress={save}
                  disabled={saving}
                >
                  {saving ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <>
                      <Ionicons
                        name="save-outline"
                        size={20}
                        color="#fff"
                      />

                      <Text
                        style={
                          s.ctaText
                        }
                      >
                        Salvar
                      </Text>
                    </>
                  )}
                </TouchableOpacity>

                <View style={s.divider} />

                <TouchableOpacity
                  style={s.planCta}
                  onPress={() =>
                    router.push(
                      "/subscription"
                    )
                  }
                  testID="open-subscription"
                >
                  <View
                    style={s.planIcon}
                  >
                    <Ionicons
                      name="star"
                      size={18}
                      color="#fff"
                    />
                  </View>

                  <View
                    style={{ flex: 1 }}
                  >
                    <Text
                      style={
                        s.planTitle
                      }
                    >
                      Plano Pro
                    </Text>

                    <Text
                      style={
                        s.planDesc
                      }
                    >
                      Propostas ilimitadas +
                      recursos avançados
                    </Text>
                  </View>

                  <Ionicons
                    name="chevron-forward"
                    size={20}
                    color={
                      theme.colors
                        .textMuted
                    }
                  />
                </TouchableOpacity>

                <TouchableOpacity
                  style={s.planCta}
                  onPress={() =>
                    router.push(
                      "/referral"
                    )
                  }
                  testID="open-referral"
                >
                  <View
                    style={[
                      s.planIcon,
                      {
                        backgroundColor:
                          theme.colors
                            .whatsapp,
                      },
                    ]}
                  >
                    <Ionicons
                      name="gift"
                      size={18}
                      color="#fff"
                    />
                  </View>

                  <View
                    style={{ flex: 1 }}
                  >
                    <Text
                      style={
                        s.planTitle
                      }
                    >
                      Indique e ganhe 30
                      dias Pro
                    </Text>

                    <Text
                      style={
                        s.planDesc
                      }
                    >
                      Você e seu amigo
                      ganham. Compartilhe
                      agora 🎁
                    </Text>
                  </View>

                  <Ionicons
                    name="chevron-forward"
                    size={20}
                    color={
                      theme.colors
                        .textMuted
                    }
                  />
                </TouchableOpacity>

                <View style={s.userCard}>
                  <Text
                    style={s.userLabel}
                  >
                    Conta
                  </Text>

                  <Text
                    style={s.userName}
                  >
                    {user?.name}
                  </Text>

                  <Text
                    style={s.userEmail}
                  >
                    {user?.email}
                  </Text>
                </View>

                <TouchableOpacity
                  style={s.logout}
                  onPress={logout}
                  testID="logout-button"
                >
                  <Ionicons
                    name="log-out-outline"
                    size={20}
                    color={
                      theme.colors.danger
                    }
                  />

                  <Text
                    style={
                      s.logoutText
                    }
                  >
                    Sair da conta
                  </Text>
                </TouchableOpacity>
              </>
            ) : (
              renderUsersTab()
            )}
          </ScrollView>
        </KeyboardAvoidingView>
      )}
      {renderUserModal()}
      {renderReactivateModal()}
    </SafeAreaView>
  );
}

function Input({
  label,
  testID,
  ...props
}: any) {
  return (
    <View style={{ gap: 6 }}>
      <Text style={s.label}>
        {label}
      </Text>

      <TextInput
        {...props}
        testID={testID}
        style={[
          s.input,

          props.multiline && {
            height: 80,
            paddingTop: 12,
            textAlignVertical:
              "top",
          },
        ]}
        placeholderTextColor={
          theme.colors.textMuted
        }
      />
    </View>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor:
      theme.colors.bg,
  },

  scroll: {
    padding: 24,
    paddingBottom: 50,
    gap: 12,
  },

  desktopScroll: {
    padding: 24,
    paddingBottom: 140,
    gap: 20,
  },

  desktopHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 16,
    marginBottom: 24,
  },

  desktopActionButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: theme.colors.primary,
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: 16,
    minHeight: 56,
  },

  desktopActionText: {
    color: "#fff",
    fontSize: 15,
    fontWeight: "700",
  },

  desktopColumns: {
    flexDirection: "row",
    gap: 24,
    alignItems: "flex-start",
  },

  desktopLeft: {
    flex: 1,
    gap: 24,
  },

  desktopRight: {
    width: 420,
    gap: 20,
  },

  panelCard: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 20,
    padding: 24,
    gap: 16,
  },

  sectionTitle: {
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.textSec,
    letterSpacing: 1.2,
    textTransform: "uppercase",
    marginBottom: 12,
  },

  proBadgeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },

  logoutDesktop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingVertical: 16,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: "#fff",
  },

  header: {
    marginBottom: 4,
  },

  title: {
    fontSize: 28,
    fontWeight: "800",
    color: theme.colors.text,
    letterSpacing: -0.5,
  },

  subtitle: {
    fontSize: 13,
    color:
      theme.colors.textSec,
    marginTop: 4,
  },

  proCard: {
    backgroundColor:
      "#111827",

    borderRadius: 22,

    padding: 20,

    marginVertical: 12,

    borderWidth: 1,

    borderColor:
      "rgba(255,255,255,0.08)",
  },

  proCardActive: {
    backgroundColor:
      "#0F172A",
  },

  proCardHeader: {
    flexDirection: "row",

    justifyContent:
      "space-between",

    alignItems: "center",

    marginBottom: 16,
  },

  badge: {
    flexDirection: "row",

    alignItems: "center",

    gap: 6,

    paddingHorizontal: 10,

    paddingVertical: 6,

    borderRadius: 999,
  },

  badgeText: {
    color: "#fff",

    fontWeight: "800",

    fontSize: 11,

    letterSpacing: 0.8,
  },

  proTitle: {
    color: "#fff",

    fontSize: 22,

    fontWeight: "800",

    marginBottom: 8,
  },

  proDesc: {
    color:
      "rgba(255,255,255,0.75)",

    lineHeight: 21,

    fontSize: 14,
  },

  proUntil: {
    color:
      "rgba(255,255,255,0.55)",

    marginTop: 14,

    fontSize: 12,
  },

  upgradeBtn: {
    marginTop: 18,

    backgroundColor: "#fff",

    height: 52,

    borderRadius: 14,

    alignItems: "center",

    justifyContent:
      "center",

    flexDirection: "row",

    gap: 8,
  },

  upgradeText: {
    color: "#0F172A",

    fontWeight: "800",

    fontSize: 15,
  },

  logoWrap: {
    alignItems: "center",

    marginVertical: 12,
  },

  logo: {
    width: 112,

    height: 112,

    borderRadius: 16,

    borderWidth: 1,

    borderColor:
      theme.colors.border,
  },

  logoPh: {
    width: 112,

    height: 112,

    borderRadius: 16,

    backgroundColor: "#fff",

    borderWidth: 1,

    borderColor:
      theme.colors.border,

    borderStyle: "dashed",

    alignItems: "center",

    justifyContent:
      "center",

    gap: 6,

    padding: 8,
  },

  logoPhText: {
    fontSize: 11,

    color:
      theme.colors.textMuted,

    textAlign: "center",
  },

  label: {
    fontSize: 11,

    color:
      theme.colors.textMuted,

    fontWeight: "700",

    letterSpacing: 0.5,

    textTransform:
      "uppercase",
  },

  input: {
    height: 52,

    borderRadius: 12,

    backgroundColor: "#fff",

    borderWidth: 1,

    borderColor:
      theme.colors.border,

    paddingHorizontal: 14,

    fontSize: 16,

    color: theme.colors.text,
  },

  cta: {
    height: 56,

    borderRadius: 12,

    backgroundColor:
      theme.colors.primary,

    flexDirection: "row",

    alignItems: "center",

    justifyContent:
      "center",

    gap: 8,

    marginTop: 16,
  },

  ctaText: {
    color: "#fff",

    fontSize: 16,

    fontWeight: "700",
  },

  divider: {
    height: 1,

    backgroundColor:
      theme.colors.border,

    marginVertical: 16,
  },

  userCard: {
    backgroundColor: "#fff",

    borderWidth: 1,

    borderColor:
      theme.colors.border,

    padding: 16,

    borderRadius: 14,

    gap: 2,
  },

  userLabel: {
    fontSize: 11,

    color:
      theme.colors.textMuted,

    fontWeight: "700",

    textTransform:
      "uppercase",

    letterSpacing: 1,

    marginBottom: 4,
  },

  userName: {
    fontSize: 16,

    fontWeight: "700",

    color: theme.colors.text,
  },

  userEmail: {
    fontSize: 13,

    color:
      theme.colors.textSec,
  },

  logout: {
    flexDirection: "row",

    alignItems: "center",

    justifyContent:
      "center",

    gap: 8,

    paddingVertical: 14,
  },

  logoutText: {
    color: theme.colors.danger,

    fontWeight: "700",
  },

  planCta: {
    flexDirection: "row",

    alignItems: "center",

    gap: 12,

    padding: 14,

    backgroundColor: "#fff",

    borderWidth: 1,

    borderColor:
      theme.colors.border,

    borderRadius: 14,

    marginBottom: 12,
  },

  planIcon: {
    width: 36,

    height: 36,

    borderRadius: 10,

    backgroundColor:
      theme.colors.primary,

    alignItems: "center",

    justifyContent:
      "center",
  },

  planTitle: {
    fontWeight: "700",

    color: theme.colors.text,

    fontSize: 15,
  },

  planDesc: {
    color:
      theme.colors.textSec,

    fontSize: 12,

    marginTop: 2,
  },
  tabBar: {
    flexDirection: "row",
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    marginBottom: 20,
    paddingBottom: 8,
  },
  tabButton: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 8,
  },
  tabButtonActive: {
    backgroundColor: theme.colors.primary,
  },
  tabButtonText: {
    fontSize: 14,
    fontWeight: "600",
    color: theme.colors.textSec,
  },
  tabButtonTextActive: {
    color: "#fff",
  },
  usersTabContainer: {
    gap: 16,
  },
  usersHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 8,
  },
  usersSectionTitle: {
    fontSize: 18,
    fontWeight: "800",
    color: theme.colors.text,
  },
  newUserBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: theme.colors.primary,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 10,
  },
  newUserBtnText: {
    color: "#fff",
    fontSize: 13,
    fontWeight: "700",
  },
  usersListContainer: {
    marginTop: 4,
  },
  noUsersText: {
    fontSize: 14,
    color: theme.colors.textMuted,
    textAlign: "center",
    paddingVertical: 32,
  },
  // Table styles
  tableContainer: {
    backgroundColor: "#fff",
    borderRadius: 16,
    borderWidth: 1,
    borderColor: theme.colors.border,
    overflow: "hidden",
  },
  tableHeader: {
    flexDirection: "row",
    backgroundColor: "#F8FAFC",
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    paddingVertical: 12,
    paddingHorizontal: 16,
  },
  tableHeaderCell: {
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.textSec,
    textTransform: "uppercase",
  },
  tableRow: {
    flexDirection: "row",
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    paddingVertical: 14,
    paddingHorizontal: 16,
    alignItems: "center",
  },
  tableCell: {
    fontSize: 14,
    color: theme.colors.text,
  },
  statusIndicator: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  statusActive: {
    backgroundColor: "#22C55E",
  },
  statusInactive: {
    backgroundColor: theme.colors.danger,
  },
  statusText: {
    fontSize: 14,
    color: theme.colors.text,
  },
  actionIconBtn: {
    padding: 6,
  },
  // Card styles
  userCardItem: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 16,
    padding: 16,
    gap: 12,
  },
  userCardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  userCardName: {
    fontSize: 16,
    fontWeight: "700",
    color: theme.colors.text,
  },
  userCardEmail: {
    fontSize: 13,
    color: theme.colors.textSec,
    marginTop: 2,
  },
  userCardFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    paddingTop: 12,
  },
  userCardRole: {
    fontSize: 13,
    color: theme.colors.textSec,
    fontWeight: "600",
  },
  cardActionBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  cardActionText: {
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.primary,
  },
  badgeCompact: {
    paddingVertical: 4,
    paddingHorizontal: 8,
    borderRadius: 6,
  },
  badgeCompactText: {
    fontSize: 11,
    fontWeight: "700",
  },
  badgeActive: {
    backgroundColor: "#DCFCE7",
  },
  badgeActiveText: {
    color: "#166534",
  },
  badgeInactive: {
    backgroundColor: "#FEE2E2",
  },
  badgeInactiveText: {
    color: "#991B1B",
  },
  // Quota styles
  quotaContainer: {
    backgroundColor: "#F8FAFC",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 16,
    padding: 16,
    gap: 12,
  },
  quotaHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  quotaPlanTitle: {
    fontSize: 15,
    fontWeight: "800",
    color: theme.colors.text,
  },
  quotaUsageText: {
    fontSize: 13,
    color: theme.colors.textSec,
    marginTop: 2,
  },
  progressBarBackground: {
    height: 8,
    backgroundColor: "#E2E8F0",
    borderRadius: 4,
    overflow: "hidden",
  },
  progressBarFill: {
    height: "100%",
    backgroundColor: theme.colors.primary,
    borderRadius: 4,
  },
  reactivateHelpBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 12,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: theme.colors.border,
    borderRadius: 12,
    marginTop: 8,
  },
  reactivateHelpText: {
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.primary,
  },
  reactivateHelpDesc: {
    fontSize: 14,
    color: theme.colors.textSec,
    lineHeight: 20,
    marginBottom: 8,
  },
  // Modal styles
  modalOverlay: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.5)",
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
  },
  modalCard: {
    width: "100%",
    maxWidth: 460,
    backgroundColor: "#fff",
    borderRadius: 20,
    padding: 24,
    gap: 16,
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 10,
    elevation: 6,
  },
  modalHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    paddingBottom: 12,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: "800",
    color: theme.colors.text,
  },
  modalContent: {
    gap: 16,
  },
  modalLabel: {
    fontSize: 11,
    fontWeight: "700",
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  modalInput: {
    height: 48,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: theme.colors.border,
    paddingHorizontal: 12,
    fontSize: 15,
    color: theme.colors.text,
  },
  roleSelectorContainer: {
    flexDirection: "row",
    gap: 12,
  },
  roleSelectorBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    height: 48,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: "#fff",
  },
  roleSelectorBtnActive: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  roleSelectorText: {
    fontSize: 14,
    fontWeight: "700",
    color: theme.colors.textSec,
  },
  roleSelectorTextActive: {
    color: "#fff",
  },
  checkboxContainer: {
    flexDirection: "row",
    gap: 10,
    alignItems: "center",
    marginTop: 4,
  },
  checkbox: {
    width: 20,
    height: 20,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: theme.colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  checkboxChecked: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  checkboxLabel: {
    fontSize: 14,
    fontWeight: "600",
    color: theme.colors.text,
  },
  checkboxSub: {
    fontSize: 11,
    color: theme.colors.textMuted,
    marginTop: 1,
  },
  modalFooter: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 12,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    paddingTop: 16,
    marginTop: 4,
  },
  btnCancel: {
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 10,
  },
  btnCancelText: {
    fontSize: 14,
    fontWeight: "700",
    color: theme.colors.textSec,
  },
  btnConfirm: {
    backgroundColor: theme.colors.primary,
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 10,
  },
  btnConfirmText: {
    fontSize: 14,
    fontWeight: "700",
    color: "#fff",
  },
  trialCard: {
    backgroundColor: "#F8FAFC",
    borderWidth: 1,
    borderColor: "#E2E8F0",
    padding: 16,
    borderRadius: 16,
    marginBottom: 16,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  trialTitle: {
    fontSize: 14,
    fontWeight: "700",
    color: "#1E293B",
  },
  trialDaysText: {
    fontSize: 13,
    fontWeight: "600",
    color: "#64748B",
  },
});