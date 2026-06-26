import React from "react";
import { Stack, useRouter, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { AuthProvider, useAuth } from "../src/auth";
import { View, ActivityIndicator, StyleSheet } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { theme } from "../src/theme";
import { ensureNotificationPermission, scheduleFollowupReminder } from "../src/notifications";

function Gate({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const router = useRouter();
  const segments = useSegments();

  React.useEffect(() => {
    if (user === undefined) return;
    const segs = segments as string[];
    const inAuth = segs[0] === "(auth)";
    const isPublic = segs[0] === "p" || (segs[0] === "(auth)" && segs[1] === "accept");
    if (!user && !inAuth && !isPublic) {
      router.replace("/(auth)/login");
    } else if (user && inAuth && segs[1] !== "accept") {
      router.replace("/(tabs)");
    }
  }, [user, segments]);

  React.useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const ok = await ensureNotificationPermission();
        if (ok) await scheduleFollowupReminder();
      } catch (e) {
        console.log("notifications setup ignored:", e);
      }
    })();
  }, [user]);

  if (user === undefined) {
    return (
      <View style={styles.loading} testID="root-loading">
        <ActivityIndicator size="large" color={theme.colors.primary} />
      </View>
    );
  }
  return <>{children}</>;
}

export default function RootLayout() {
  return (
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
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, backgroundColor: theme.colors.bg, alignItems: "center", justifyContent: "center" },
});
