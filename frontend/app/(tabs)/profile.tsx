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

import { theme } from "../../src/theme";

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

  const renderDesktop = () => (
    <ScrollView
      contentContainerStyle={s.desktopScroll}
    >
      <View style={s.desktopHeader}>
        <View>
          <Text style={s.title}>Minha empresa</Text>
          <Text style={s.subtitle}>
            A identidade da sua marca aparece nos PDFs
          </Text>
        </View>

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
      </View>

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
                A identidade da sua
                marca aparece nos PDFs
              </Text>
            </View>
          </View>

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
        </ScrollView>
      </KeyboardAvoidingView>
    )}
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
});