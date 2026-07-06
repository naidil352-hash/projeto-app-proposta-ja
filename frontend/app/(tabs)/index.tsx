import React, { useCallback, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  useWindowDimensions,
} from "react-native";

import { SafeAreaView } from "react-native-safe-area-context";

import { Ionicons } from "@expo/vector-icons";

import {
  useFocusEffect,
  useRouter,
} from "expo-router";

import {
  api,
  formatApiError,
} from "../../src/api";

import { useAuth } from "../../src/auth";

import {
  theme,
  formatCurrency,
} from "../../src/theme";

type Stats = {
  open_count: number;
  won_count: number;
  lost_count: number;
  open_value: number;
  month_won_value: number;
  stale_count: number;
  is_pro?: boolean;
  month_count?: number;
  month_quota?: number | null;
  pro_until?: string | null;
  ticket_average?: number;
  total_revenue?: number;
  clients_count?: number;
  clients_active?: number;
  clients_lost?: number;
  negotiation_count?: number;
  conversion_rate?: number;
  acceptance_pending_count?: number;
  acceptance_accepted_count?: number;
  acceptance_rejected_count?: number;
  acceptance_rate?: number;
  is_trial?: boolean;
  trial_days_remaining?: number | null;
  trial_is_expired?: boolean;
  followup_count?: number;
  overdue_count?: number;
  viewed_today_count?: number;
  waiting_count?: number;
  users_stats?: any[];
};

export default function Dashboard() {
  const { user, logout } =
    useAuth();

  const router = useRouter();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;

  const [stats, setStats] =
    useState<Stats | null>(null);
  const [subscription, setSubscription] = useState<any>(null);
  const [proposals, setProposals] = useState<any[]>([]);

  const [
    refreshing,
    setRefreshing,
  ] = useState(false);

  const [err, setErr] =
    useState<string | null>(
      null
    );

  const load = useCallback(
    async () => {
      try {
        setErr(null);

        const [statsRes, subRes, propRes] = await Promise.all([
          api.get("/stats"),
          api.get("/subscription/me"),
          api.get("/proposals")
        ]);

        const subData = subRes.data;
        if (subData) {
          subData.days_remaining = subData.trial_days_remaining;
        }

        setStats(statsRes.data);
        setSubscription(subData);
        setProposals(propRes.data || []);
      } catch (e) {
        setErr(
          formatApiError(e)
        );
      }
    },
    []
  );

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onRefresh =
    async () => {
      setRefreshing(true);

      await load();

      setRefreshing(false);
    };

  const totalProposals = proposals.length;
  const viewedProposals = proposals.filter((p: any) => p.proposal_viewed_at).length;
  const acceptedProposals = proposals.filter((p: any) => p.acceptance_status === "accepted" || p.status === "accepted" || p.status === "aprovado").length;
  const conversionRate = totalProposals > 0 ? Math.round((acceptedProposals / totalProposals) * 100) : 0;

  const renderDesktop = () => (
    <ScrollView
      contentContainerStyle={
        s.desktopScroll
      }
      refreshControl={
        <RefreshControl
          refreshing={
            refreshing
          }
          onRefresh={
            onRefresh
          }
        />
      }
    >
      <View style={s.desktopHeader}>
        <View>
          <Text style={s.hello}>
            Olá,{" "}
            {user?.name?.split(
              " "
            )[0] || ""}{" "}
            👋
          </Text>

          <Text style={s.title}>
            Painel
          </Text>
        </View>

        <TouchableOpacity
          style={s.quickActionCard}
          onPress={() =>
            router.push(
              "/(tabs)/new"
            )
          }
          testID="create-new-card"
        >
          <View style={s.quickActionIcon}>
            <Ionicons
              name="add"
              size={20}
              color="#fff"
            />
          </View>

          <View style={s.quickActionText}>
            <Text style={s.quickActionTitle}>
              Criar nova proposta
            </Text>
            <Text style={s.quickActionSubtitle}>
              Acesso rápido
            </Text>
          </View>
        </TouchableOpacity>
      </View>

      {err && (
        <Text style={s.error}>
          {err}
        </Text>
      )}

      <View style={s.kpiRow}>
        <MetricCard
          testID="card-open"
          icon="time-outline"
          label="Abertas"
          value={String(stats?.open_count ?? 0)}
          sub="propostas"
          accent={theme.colors.statusOpenText}
        />
        <MetricCard
          testID="card-followup"
          icon="alert-circle-outline"
          label="Precisam follow-up"
          value={String(stats?.followup_count ?? 0)}
          sub="> 3 dias sem ação"
          accent={theme.colors.warn}
        />
        <MetricCard
          testID="card-overdue"
          icon="calendar-outline"
          label="Atrasadas"
          value={String(stats?.overdue_count ?? 0)}
          sub="ação agendada < hoje"
          accent={theme.colors.danger}
        />
        <MetricCard
          testID="card-viewed-today"
          icon="eye-outline"
          label="Visualizadas hoje"
          value={String(stats?.viewed_today_count ?? 0)}
          sub="acessos hoje"
          accent="#8B5CF6"
        />
      </View>

      <View style={s.kpiRow}>
        <MetricCard
          testID="card-waiting"
          icon="hourglass-outline"
          label="Aguardando retorno"
          value={String(stats?.waiting_count ?? 0)}
          sub="último evento waiting"
          accent="#64748B"
        />
        <MetricCard
          testID="card-conversion"
          icon="trending-up-outline"
          label={user?.role === "owner" ? "Conversão Geral" : "Minha Conversão"}
          value={`${stats?.conversion_rate ?? 0}%`}
          sub="taxa de fechamento"
          accent="#10B981"
        />
        <View style={{ flex: 1, minWidth: 200 }} />
        <View style={{ flex: 1, minWidth: 200 }} />
      </View>

      {/* Dashboard Gestão para Desktop */}
      {user?.role === "owner" && stats?.users_stats && stats.users_stats.length > 0 && (
        <View style={s.card} testID="dashboard-gestao-section">
          <Text style={s.sectionTitle}>Dashboard Gestão</Text>
          <View style={{ marginTop: 12 }}>
            <View style={{ flexDirection: "row", borderBottomWidth: 1, borderBottomColor: "#CBD5E1", paddingVertical: 8, backgroundColor: "#F8FAFC" }}>
              <Text style={{ flex: 2, fontWeight: "700", fontSize: 13, color: "#475569" }}>Usuário</Text>
              <Text style={{ flex: 1, fontWeight: "700", fontSize: 13, color: "#475569", textAlign: "center" }}>Enviadas</Text>
              <Text style={{ flex: 1, fontWeight: "700", fontSize: 13, color: "#475569", textAlign: "center" }}>Visualizadas</Text>
              <Text style={{ flex: 1, fontWeight: "700", fontSize: 13, color: "#475569", textAlign: "center" }}>Aceitas</Text>
              <Text style={{ flex: 1.2, fontWeight: "700", fontSize: 13, color: "#475569", textAlign: "right" }}>Conversão</Text>
            </View>
            {stats.users_stats.map((u: any, idx: number) => (
              <View key={u.user_id || idx} style={{ flexDirection: "row", borderBottomWidth: 1, borderBottomColor: "#E2E8F0", paddingVertical: 10, alignItems: "center" }} testID={`user-row-${idx}`}>
                <Text style={{ flex: 2, fontSize: 13, fontWeight: "600", color: theme.colors.text }}>{u.name}</Text>
                <Text style={{ flex: 1, fontSize: 13, color: theme.colors.text, textAlign: "center" }}>{u.enviadas}</Text>
                <Text style={{ flex: 1, fontSize: 13, color: theme.colors.text, textAlign: "center" }}>{u.visualizadas}</Text>
                <Text style={{ flex: 1, fontSize: 13, color: theme.colors.text, textAlign: "center" }}>{u.aceitas}</Text>
                <Text style={{ flex: 1.2, fontSize: 13, fontWeight: "700", color: "#10B981", textAlign: "right" }}>{u.conversao}%</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      <View style={s.analyticsRow}>
        <TouchableOpacity
          style={s.analyticsBtn}
          onPress={() => router.push("/analytics/products")}
          testID="btn-ranking-products"
        >
          <Ionicons name="bar-chart-outline" size={16} color="#fff" />
          <Text style={s.analyticsBtnText}>Ranking de Produtos</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={s.analyticsBtn}
          onPress={() => router.push("/analytics/sellers")}
          testID="btn-ranking-sellers"
        >
          <Ionicons name="people-circle-outline" size={16} color="#fff" />
          <Text style={s.analyticsBtnText}>Ranking de Vendedores</Text>
        </TouchableOpacity>
      </View>

      <View style={s.desktopMainRow}>
        <View style={s.desktopPrimary}>
          <View
            style={s.bigCard}
            testID="card-month-won"
          >
            <Text style={s.bigLabel}>
              Ganho este mês
            </Text>

            <Text style={s.bigValue}>
              {formatCurrency(
                stats?.month_won_value ||
                  0
              )}
            </Text>

            <View style={s.row}>
              <View style={s.pill}>
                <Ionicons
                  name="checkmark-circle"
                  size={14}
                  color="#fff"
                />

                <Text
                  style={
                    s.pillText
                  }
                >
                  {stats?.won_count ||
                    0}{" "}
                  realizados
                </Text>
              </View>
            </View>
          </View>
        </View>

        <View style={s.desktopSecondary}>
          <View style={s.sideCard}>
            <Text style={s.sideCardLabel}>
              {stats?.is_pro ? "Assinatura" : "Dias de teste"}
            </Text>
            <Text style={s.sideCardValue}>
              {stats?.is_pro
                ? "Acesso Ilimitado"
                : `${stats?.trial_days_remaining ?? 0} / 60 dias`}
            </Text>
            <View style={s.bar}>
              <View
                style={[
                  s.barFill,
                  {
                    width: `${stats?.is_pro
                      ? 100
                      : stats?.trial_is_expired
                      ? 0
                      : Math.min(100, Math.round(((stats?.trial_days_remaining ?? 0) / 60) * 100))}%`,
                  },
                ]}
              />
            </View>
            <Text
              style={
                s.usageHint
              }
            >
              {stats?.is_pro
                ? "Plano Pro Ativo"
                : stats?.trial_is_expired
                ? "Avaliação expirada"
                : "Período de teste ativo"}
            </Text>
          </View>

          <View style={s.sideCard}>
            <Text style={s.sideCardLabel}>
              Plano Pro
            </Text>
            <View
              style={
                s.proBannerRow
              }
            >
              <Ionicons
                name="star"
                size={18}
                color={
                  stats?.is_pro
                    ? "#fff"
                    : theme.colors.primary
                }
              />
              <Text
                style={
                  s.sideCardText
                }
              >
                {stats?.is_pro
                  ? "Plano ativo"
                  : "Pro disponível"}
              </Text>
            </View>
            <Text
              style={
                s.sideCardValue
              }
            >
              {stats?.is_pro
                ? stats.pro_until
                  ? "Renove até " +
                    new Date(
                      stats.pro_until
                    ).toLocaleDateString(
                      "pt-BR"
                    )
                  : "Ativo"
                : "Toque para conhecer"}
            </Text>
            {!stats?.is_pro && (
              <TouchableOpacity
                onPress={() =>
                  router.push(
                    "/subscription"
                  )
                }
              >
                <Text
                  style={s.upgradeLink}
                >
                  Melhorar para Pro
                </Text>
              </TouchableOpacity>
            )}
          </View>

          <TouchableOpacity
            style={s.sideCard}
            onPress={() =>
              router.push(
                "/(tabs)/proposals"
              )
            }
            testID="follow-up-card"
          >
            <Text style={s.sideCardLabel}>
              Follow-up pendente
            </Text>
            <Text style={s.sideCardValue}>
              {stats?.stale_count ||
                0}
            </Text>
            <Text style={s.sideCardHint}>
              Propostas abertas há 3+ dias
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  );

  return (
    <SafeAreaView
      style={s.root}
      testID="dashboard-screen"
      edges={["top"]}
    >
      {isDesktop ? (
        renderDesktop()
      ) : (
        <ScrollView
          contentContainerStyle={
            s.scroll
          }
          refreshControl={
            <RefreshControl
              refreshing={
                refreshing
              }
              onRefresh={
                onRefresh
              }
            />
          }
        >
          <View style={s.header}>
            <View>
              <Text style={s.hello}>
                Olá,{" "}
                {user?.name?.split(
                  " "
                )[0] || ""}{" "}
                👋
              </Text>

              <Text style={s.title}>
                Painel
              </Text>
            </View>

            <TouchableOpacity
              style={s.logout}
              onPress={logout}
              testID="logout-btn"
            >
              <Ionicons
                name="log-out-outline"
                size={22}
                color={
                  theme.colors.text
                }
              />
            </TouchableOpacity>
          </View>

          {err && (
            <Text style={s.error}>
              {err}
            </Text>
          )}

          {!stats?.is_pro && stats && (
              <TouchableOpacity
                style={s.usageCard}
                onPress={() =>
                  router.push(
                    "/subscription"
                  )
                }
                testID="usage-banner"
              >
                <View
                  style={
                    s.usageHead
                  }
                >
                  <Text
                    style={
                      s.usageTitle
                    }
                  >
                    {stats.trial_is_expired
                      ? "Período de teste expirado"
                      : `${stats.trial_days_remaining ?? 0} dias de teste restantes`}
                  </Text>

                  <View
                    style={
                      s.upBadge
                    }
                  >
                    <Ionicons
                      name="star"
                      size={12}
                      color="#fff"
                    />

                    <Text
                      style={
                        s.upBadgeText
                      }
                    >
                      Upgrade
                    </Text>
                  </View>
                </View>

                <View style={s.bar}>
                  <View
                    style={[
                      s.barFill,
                      {
                        width: `${stats.trial_is_expired
                          ? 0
                          : Math.min(100, Math.round(((stats.trial_days_remaining ?? 0) / 60) * 100))}%`,
                      },
                    ]}
                  />
                </View>

                <Text
                  style={
                    s.usageHint
                  }
                >
                  {stats.trial_is_expired
                    ? "Toque para assinar o plano Pro e liberar acesso"
                    : "Toque para conhecer o plano Pro · ilimitado"}
                </Text>
              </TouchableOpacity>
            )}

          {stats?.is_pro && (
            <View
              style={s.proBanner}
              testID="pro-active-banner"
            >
              <Ionicons
                name="star"
                size={18}
                color="#fff"
              />

              <Text
                style={
                  s.proBannerText
                }
              >
                {stats.is_trial || stats.trial_days_remaining !== null
                  ? `Plano Pro • ${subscription?.days_remaining ?? stats?.trial_days_remaining ?? 60} ${(subscription?.days_remaining ?? stats?.trial_days_remaining ?? 60) === 1 ? "dia restante" : "dias restantes"}`
                  : `Plano Pro ativo · renove até ${stats.pro_until ? new Date(stats.pro_until).toLocaleDateString("pt-BR") : ""}`}
              </Text>
            </View>
          )}

          {stats?.stale_count ? (
            <TouchableOpacity
              style={s.alert}
              onPress={() =>
                router.push(
                  "/(tabs)/proposals"
                )
              }
              testID="stale-alert"
            >
              <Ionicons
                name="alert-circle"
                size={24}
                color={
                  theme.colors.warn
                }
              />

              <View
                style={{
                  flex: 1,
                }}
              >
                <Text
                  style={
                    s.alertTitle
                  }
                >
                  {
                    stats.stale_count
                  }{" "}
                  proposta(s)
                  precisam de
                  follow-up
                </Text>

                <Text
                  style={
                    s.alertSub
                  }
                >
                  Abertas há 3+
                  dias · toque
                  para revisar
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
          ) : null}

          <View
            style={s.bigCard}
            testID="card-month-won"
          >
            <Text style={s.bigLabel}>
              Ganho este mês
            </Text>

            <Text style={s.bigValue}>
              {formatCurrency(
                stats?.month_won_value ||
                  0
              )}
            </Text>

            <View style={s.row}>
              <View style={s.pill}>
                <Ionicons
                  name="checkmark-circle"
                  size={14}
                  color="#fff"
                />

                <Text
                  style={
                    s.pillText
                  }
                >
                  {stats?.won_count ||
                    0}{" "}
                  realizados
                </Text>
              </View>
            </View>
          </View>

          <View style={s.grid}>
            <MetricCard
              testID="card-open"
              icon="time-outline"
              label="Abertas"
              value={String(stats?.open_count ?? 0)}
              sub="propostas"
              accent={theme.colors.statusOpenText}
            />
            <MetricCard
              testID="card-followup"
              icon="alert-circle-outline"
              label="Precisam follow-up"
              value={String(stats?.followup_count ?? 0)}
              sub="> 3 dias sem ação"
              accent={theme.colors.warn}
            />
          </View>

          <View style={s.gridRow}>
            <MetricCard
              testID="card-overdue"
              icon="calendar-outline"
              label="Atrasadas"
              value={String(stats?.overdue_count ?? 0)}
              sub="ação agendada < hoje"
              accent={theme.colors.danger}
            />
            <MetricCard
              testID="card-viewed-today"
              icon="eye-outline"
              label="Visualizadas hoje"
              value={String(stats?.viewed_today_count ?? 0)}
              sub="acessos hoje"
              accent="#8B5CF6"
            />
          </View>

          <View style={s.gridRow}>
            <MetricCard
              testID="card-waiting"
              icon="hourglass-outline"
              label="Aguardando retorno"
              value={String(stats?.waiting_count ?? 0)}
              sub="último evento waiting"
              accent="#64748B"
            />
            <MetricCard
              testID="card-conversion"
              icon="trending-up-outline"
              label={user?.role === "owner" ? "Conversão Geral" : "Minha Conversão"}
              value={`${stats?.conversion_rate ?? 0}%`}
              sub="taxa de fechamento"
              accent="#10B981"
            />
          </View>

          {/* Dashboard Gestão para Celular */}
          {user?.role === "owner" && stats?.users_stats && stats.users_stats.length > 0 && (
            <View style={s.card} testID="dashboard-gestao-section">
              <Text style={s.sectionTitle}>Dashboard Gestão</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 8 }}>
                <View style={{ minWidth: 500 }}>
                  <View style={{ flexDirection: "row", borderBottomWidth: 1, borderBottomColor: "#CBD5E1", paddingVertical: 8, backgroundColor: "#F8FAFC" }}>
                    <Text style={{ flex: 2, fontWeight: "700", fontSize: 13, color: "#475569" }}>Usuário</Text>
                    <Text style={{ flex: 1, fontWeight: "700", fontSize: 13, color: "#475569", textAlign: "center" }}>Enviadas</Text>
                    <Text style={{ flex: 1, fontWeight: "700", fontSize: 13, color: "#475569", textAlign: "center" }}>Visualizadas</Text>
                    <Text style={{ flex: 1, fontWeight: "700", fontSize: 13, color: "#475569", textAlign: "center" }}>Aceitas</Text>
                    <Text style={{ flex: 1.2, fontWeight: "700", fontSize: 13, color: "#475569", textAlign: "right" }}>Conversão</Text>
                  </View>
                  {stats.users_stats.map((u: any, idx: number) => (
                    <View key={u.user_id || idx} style={{ flexDirection: "row", borderBottomWidth: 1, borderBottomColor: "#E2E8F0", paddingVertical: 10, alignItems: "center" }} testID={`user-row-${idx}`}>
                      <Text style={{ flex: 2, fontSize: 13, fontWeight: "600", color: theme.colors.text }}>{u.name}</Text>
                      <Text style={{ flex: 1, fontSize: 13, color: theme.colors.text, textAlign: "center" }}>{u.enviadas}</Text>
                      <Text style={{ flex: 1, fontSize: 13, color: theme.colors.text, textAlign: "center" }}>{u.visualizadas}</Text>
                      <Text style={{ flex: 1, fontSize: 13, color: theme.colors.text, textAlign: "center" }}>{u.aceitas}</Text>
                      <Text style={{ flex: 1.2, fontSize: 13, fontWeight: "700", color: "#10B981", textAlign: "right" }}>{u.conversao}%</Text>
                    </View>
                  ))}
                </View>
              </ScrollView>
            </View>
          )}

          <View style={s.analyticsRow}>
            <TouchableOpacity
              style={s.analyticsBtn}
              onPress={() => router.push("/analytics/products")}
              testID="btn-ranking-products"
            >
              <Ionicons name="bar-chart-outline" size={16} color="#fff" />
              <Text style={s.analyticsBtnText}>Ranking de Produtos</Text>
            </TouchableOpacity>
            
            <TouchableOpacity
              style={s.analyticsBtn}
              onPress={() => router.push("/analytics/sellers")}
              testID="btn-ranking-sellers"
            >
              <Ionicons name="people-circle-outline" size={16} color="#fff" />
              <Text style={s.analyticsBtnText}>Ranking de Vendedores</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            style={s.newBtn}
            onPress={() =>
              router.push(
                "/(tabs)/new"
              )
            }
            testID="create-new-btn"
          >
            <Ionicons
              name="add-circle"
              size={22}
              color="#fff"
            />

            <Text
              style={s.newBtnText}
            >
              Criar nova
              proposta
            </Text>
          </TouchableOpacity>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function MetricCard({
  icon,
  label,
  value,
  sub,
  accent,
  testID,
}: {
  icon: any;
  label: string;
  value: string;
  sub: string;
  accent: string;
  testID?: string;
}) {
  return (
    <View
      style={s.metric}
      testID={testID}
    >
      <View
        style={[
          s.metricIcon,
          {
            backgroundColor:
              accent + "18",
          },
        ]}
      >
        <Ionicons
          name={icon}
          size={18}
          color={accent}
        />
      </View>

      <Text
        style={s.metricLabel}
      >
        {label}
      </Text>

      <Text
        style={s.metricValue}
      >
        {value}
      </Text>

      <Text style={s.metricSub}>
        {sub}
      </Text>
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

    gap: 16,

    paddingBottom: 140,
  },

  header: {
    flexDirection: "row",

    justifyContent:
      "space-between",

    alignItems: "center",
  },

  hello: {
    color:
      theme.colors.textSec,

    fontSize: 14,
  },

  title: {
    color: theme.colors.text,

    fontSize: 28,

    fontWeight: "800",

    letterSpacing: -0.5,
  },

  logout: {
    width: 44,

    height: 44,

    borderRadius: 12,

    backgroundColor: "#fff",

    borderWidth: 1,

    borderColor:
      theme.colors.border,

    alignItems: "center",

    justifyContent:
      "center",
  },

  error: {
    color:
      theme.colors.danger,

    fontSize: 14,
  },

  alert: {
    flexDirection: "row",

    alignItems: "center",

    gap: 12,

    backgroundColor:
      "#FFFBEB",

    borderWidth: 1,

    borderColor:
      "#FDE68A",

    padding: 16,

    borderRadius: 12,
  },

  alertTitle: {
    fontWeight: "700",

    color: theme.colors.text,

    fontSize: 15,
  },

  alertSub: {
    fontSize: 12,

    color:
      theme.colors.textSec,

    marginTop: 2,
  },

  bigCard: {
    backgroundColor:
      theme.colors.primary,

    borderRadius: 20,

    padding: 24,
  },

  bigLabel: {
    color: "#94A3B8",

    fontSize: 12,

    fontWeight: "700",

    letterSpacing: 1.5,

    textTransform:
      "uppercase",
  },

  bigValue: {
    color: "#fff",

    fontSize: 36,

    fontWeight: "800",

    letterSpacing: -1,

    marginTop: 8,
  },

  row: {
    flexDirection: "row",

    marginTop: 14,

    gap: 8,
  },

  pill: {
    flexDirection: "row",

    alignItems: "center",

    gap: 6,

    paddingHorizontal: 10,

    paddingVertical: 6,

    backgroundColor:
      "rgba(255,255,255,0.15)",

    borderRadius: 999,
  },

  pillText: {
    color: "#fff",

    fontSize: 12,

    fontWeight: "600",
  },

  grid: {
    flexDirection: "row",

    gap: 12,
  },

  metric: {
    flex: 1,

    backgroundColor: "#fff",

    borderWidth: 1,

    borderColor:
      theme.colors.border,

    padding: 16,

    borderRadius: 16,

    gap: 6,
  },

  metricIcon: {
    width: 32,

    height: 32,

    borderRadius: 10,

    alignItems: "center",

    justifyContent:
      "center",

    marginBottom: 6,
  },

  metricLabel: {
    fontSize: 12,

    color:
      theme.colors.textSec,

    fontWeight: "600",
  },

  metricValue: {
    fontSize: 28,

    color: theme.colors.text,

    fontWeight: "800",

    letterSpacing: -0.5,
  },

  metricSub: {
    fontSize: 12,

    color:
      theme.colors.textMuted,
  },

  newBtn: {
    marginTop: 8,

    height: 56,

    borderRadius: 12,

    backgroundColor:
      theme.colors.primary,

    flexDirection: "row",

    alignItems: "center",

    justifyContent:
      "center",

    gap: 8,
  },

  newBtnText: {
    color: "#fff",

    fontSize: 16,

    fontWeight: "700",
  },

  usageCard: {
    backgroundColor: "#fff",

    borderWidth: 1,

    borderColor:
      theme.colors.border,

    padding: 16,

    borderRadius: 14,

    gap: 8,
  },

  usageHead: {
    flexDirection: "row",

    justifyContent:
      "space-between",

    alignItems: "center",
  },

  usageTitle: {
    fontSize: 14,

    color: theme.colors.text,

    fontWeight: "700",
  },

  upBadge: {
    flexDirection: "row",

    alignItems: "center",

    gap: 4,

    backgroundColor:
      theme.colors.primary,

    paddingHorizontal: 8,

    paddingVertical: 4,

    borderRadius: 999,
  },

  upBadgeText: {
    color: "#fff",

    fontSize: 11,

    fontWeight: "700",
  },

  bar: {
    height: 8,

    backgroundColor:
      theme.colors.surfaceAlt,

    borderRadius: 4,
  },

  barFill: {
    height: 8,

    backgroundColor:
      theme.colors.primary,

    borderRadius: 4,
  },

  usageHint: {
    fontSize: 12,

    color:
      theme.colors.textSec,
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
    marginBottom: 20,
  },

  quickActionCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    backgroundColor: theme.colors.primary,
    padding: 18,
    borderRadius: 18,
    minWidth: 280,
  },

  quickActionIcon: {
    width: 38,
    height: 38,
    borderRadius: 12,
    backgroundColor: "#fff",
    alignItems: "center",
    justifyContent: "center",
  },

  quickActionText: {
    flex: 1,
  },

  quickActionTitle: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
  },

  quickActionSubtitle: {
    color: "rgba(255,255,255,0.85)",
    fontSize: 12,
  },

  kpiRow: {
    flexDirection: "row",
    gap: 12,
    marginBottom: 20,
  },

  desktopMainRow: {
    flexDirection: "row",
    gap: 20,
    alignItems: "flex-start",
  },

  desktopPrimary: {
    flex: 1,
  },

  desktopSecondary: {
    width: 380,
    gap: 20,
  },

  sideCard: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 20,
    padding: 18,
    gap: 10,
  },

  sideCardLabel: {
    fontSize: 12,
    color: theme.colors.textSec,
    fontWeight: "700",
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },

  sideCardValue: {
    fontSize: 18,
    fontWeight: "700",
    color: theme.colors.text,
    marginTop: 6,
  },

  sideCardText: {
    fontSize: 14,
    color: theme.colors.text,
  },

  sideCardHint: {
    fontSize: 12,
    color: theme.colors.textSec,
    marginTop: 8,
  },

  proBannerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 8,
  },

  upgradeLink: {
    color: theme.colors.primary,
    fontSize: 13,
    fontWeight: "700",
    marginTop: 10,
  },

  proBanner: {
    flexDirection: "row",

    gap: 8,

    alignItems: "center",

    padding: 14,

    backgroundColor:
      theme.colors.primary,

    borderRadius: 12,
  },

  proBannerText: {
    color: "#fff",

    fontWeight: "700",
  },

  sectionTitle: {
    fontSize: 18,
    fontWeight: "800",
    color: theme.colors.text,
    marginTop: 16,
    marginBottom: 4,
  },

  analyticsRow: {
    flexDirection: "row",
    gap: 12,
    marginTop: 8,
    marginBottom: 8,
  },

  analyticsBtn: {
    flex: 1,
    height: 48,
    borderRadius: 12,
    backgroundColor: theme.colors.primary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },

  analyticsBtnText: {
    color: "#fff",
    fontSize: 13,
    fontWeight: "700",
  },

  gridRow: {
    flexDirection: "row",
    gap: 12,
    width: "100%",
  },
  card: {
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: 20,
    padding: 18,
    marginTop: 20,
  },
});