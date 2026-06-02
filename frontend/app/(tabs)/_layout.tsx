import React from "react";
import { Tabs, useRouter, useSegments } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import {
  View,
  Text,
  StyleSheet,
  Platform,
  TouchableOpacity,
  useWindowDimensions,
} from "react-native";

import { theme } from "../../src/theme";

const NAV_ITEMS = [
  { name: "index", label: "Início" },
  { name: "proposals", label: "Propostas" },
  { name: "new", label: "Nova" },
  { name: "clients", label: "Clientes" },
  { name: "profile", label: "Empresa" },
];

export default function TabsLayout() {
  const router = useRouter();
  const segments = useSegments();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;
  const activeTab = segments[segments.length - 1] || "index";

  return (
    <View style={s.container}>
      {isDesktop && (
        <View style={s.desktopNav}>
          {NAV_ITEMS.map((item) => {
            const active = activeTab === item.name;
            return (
              <TouchableOpacity
                key={item.name}
                style={[s.desktopNavItem, active && s.desktopNavItemActive]}
                onPress={() => router.push(item.name === "index" ? "/(tabs)" : `/(tabs)/${item.name}`)}
              >
                <Text style={[s.desktopNavText, active && s.desktopNavTextActive]}>
                  {item.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>
      )}

      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: theme.colors.text,
          tabBarInactiveTintColor: theme.colors.textMuted,
          tabBarStyle: {
            display: isDesktop ? "none" : "flex",
            backgroundColor: "#fff",
            borderTopColor: theme.colors.border,
            borderTopWidth: 1,
            height: Platform.OS === "android" ? 84 : 78,
            paddingTop: 8,
            paddingBottom: Platform.OS === "android" ? 18 : 10,
          },
          tabBarLabelStyle: {
            fontSize: 11,
            fontWeight: "600",
            marginBottom: 2,
          },
        }}
      >
        <Tabs.Screen
          name="index"
          options={{
            title: "Início",
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="home-outline" size={size} color={color} />
            ),
          }}
        />

        <Tabs.Screen
          name="proposals"
          options={{
            title: "Propostas",
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="document-text-outline" size={size} color={color} />
            ),
          }}
        />

        <Tabs.Screen
          name="new"
          options={{
            title: "Nova",
            tabBarIcon: () => (
              <View style={s.fab}>
                <Ionicons name="add" size={28} color="#fff" />
              </View>
            ),
          }}
        />

        <Tabs.Screen
          name="clients"
          options={{
            title: "Clientes",
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="people-outline" size={size} color={color} />
            ),
          }}
        />

        <Tabs.Screen
          name="profile"
          options={{
            title: "Empresa",
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="business-outline" size={size} color={color} />
            ),
          }}
        />
      </Tabs>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1 },
  desktopNav: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "flex-start",
    backgroundColor: "#fff",
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    paddingHorizontal: 24,
    paddingVertical: 12,
    gap: 12,
  },
  desktopNavItem: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 12,
    backgroundColor: "#fff",
    borderWidth: 1,
    borderColor: "transparent",
  },
  desktopNavItemActive: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  desktopNavText: {
    fontSize: 14,
    fontWeight: "700",
    color: theme.colors.textMuted,
  },
  desktopNavTextActive: {
    color: "#fff",
  },
  fab: {
    width: 52,
    height: 52,
    borderRadius: 18,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
    marginTop: -16,
    shadowColor: "#000",
    shadowOpacity: 0.18,
    shadowRadius: 10,
    shadowOffset: {
      width: 0,
      height: 4,
    },
    elevation: 8,
  },
});