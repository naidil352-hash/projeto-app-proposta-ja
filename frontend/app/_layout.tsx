import React from "react";
import { Stack, useRouter, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { AuthProvider, useAuth } from "../src/auth";
import { View, Text, ActivityIndicator, StyleSheet, TouchableOpacity } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { theme } from "../src/theme";

// Top-level error boundary: never let a JS crash leave the user with a blank screen
class RootErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: any }> {
  state = { error: null as any };
  static getDerivedStateFromError(error: any) {
    return { error };
  }
  componentDidCatch(error: any, info: any) {
    console.log("Root error:", error, info);
  }
  render() {
    if (this.state.error) {
      const msg = String(this.state.error?.message || this.state.error);
      return (
        <View style={styles.errRoot}>
          <Text style={styles.errTitle}>Algo deu errado</Text>
          <Text style={styles.errMsg}>{msg}</Text>
          <TouchableOpacity style={styles.errBtn} onPress={() => this.setState({ error: null })}>
            <Text style={styles.errBtnText}>Tentar novamente</Text>
          </TouchableOpacity>
        </View>
      );
    }
    return this.props.children;
  }
}

function Gate({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const router = useRouter();
  const segments = useSegments();

  React.useEffect(() => {
    if (user === undefined) return;
    const inAuth = segments[0] === "(auth)";
    if (!user && !inAuth) {
      router.replace("/(auth)/login");
    } else if (user && inAuth) {
      router.replace("/(tabs)");
    }
  }, [user, segments]);

  // Schedule notifications lazily, only after user is logged in.
  // Wrapped + dynamic-imported so any failure never blocks the boot path.
  React.useEffect(() => {
    if (!user) return;
    const t = setTimeout(async () => {
      try {
        const mod = await import("../src/notifications");
        const ok = await mod.ensureNotificationPermission();
        if (ok) await mod.scheduleFollowupReminder();
      } catch (e) {
        console.log("notifications setup ignored:", e);
      }
    }, 3000);
    return () => clearTimeout(t);
  }, [user]);

  if (user === undefined) {
    return (
      <View style={styles.loading} testID="root-loading">
        <ActivityIndicator size="large" color={theme.colors.primary} />
        <Text style={styles.loadingText}>Carregando PROPOSTA JÁ...</Text>
      </View>
    );
  }
  return <>{children}</>;
}

export default function RootLayout() {
  return (
    <RootErrorBoundary>
      <SafeAreaProvider>
        <AuthProvider>
          <Gate>
            <StatusBar style="dark" />
            <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: theme.colors.bg } }}>
              <Stack.Screen name="(auth)" />
              <Stack.Screen name="(tabs)" />
              <Stack.Screen name="proposal/[id]" options={{ headerShown: false, presentation: "card" }} />
              <Stack.Screen name="subscription" options={{ headerShown: false, presentation: "modal" }} />
              <Stack.Screen name="referral" options={{ headerShown: false, presentation: "modal" }} />
            </Stack>
          </Gate>
        </AuthProvider>
      </SafeAreaProvider>
    </RootErrorBoundary>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, backgroundColor: theme.colors.bg, alignItems: "center", justifyContent: "center" },
  loadingText: { marginTop: 16, color: theme.colors.textSec, fontSize: 14 },
  errRoot: {
    flex: 1,
    backgroundColor: theme.colors.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: 32,
  },
  errTitle: { fontSize: 22, fontWeight: "800", color: theme.colors.text, marginBottom: 8 },
  errMsg: { color: theme.colors.textSec, textAlign: "center", marginBottom: 24 },
  errBtn: {
    backgroundColor: theme.colors.primary,
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 12,
  },
  errBtnText: { color: "#fff", fontWeight: "700" },
});
