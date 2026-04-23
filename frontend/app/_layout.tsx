import React from "react";
import { Stack, useRouter, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { AuthProvider, useAuth } from "../src/auth";
import { View, ActivityIndicator, StyleSheet } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { theme } from "../src/theme";

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
          </Stack>
        </Gate>
      </AuthProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, backgroundColor: theme.colors.bg, alignItems: "center", justifyContent: "center" },
});
card" }} />
          </Stack>
        </Gate>
      </AuthProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, backgroundColor: theme.colors.bg, alignItems: "center", justifyContent: "center" },
});
