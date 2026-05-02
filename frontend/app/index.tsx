import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, ImageBackground,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { COLORS, RADII, SPACING, SHADOW_SM } from "../src/theme";
import { Api } from "../src/api";

const ROLES = [
  {
    key: "teacher",
    title: "Teacher",
    subtitle: "Create AI-powered tests",
    icon: "👩‍🏫",
    href: "/teacher/login",
    color: COLORS.primary,
  },
  {
    key: "student",
    title: "Student",
    subtitle: "Join class & take exam",
    icon: "🎓",
    href: "/student/login",
    color: COLORS.accent,
  },
  {
    key: "admin",
    title: "Admin",
    subtitle: "Manage platform",
    icon: "🛡️",
    href: "/admin/login",
    color: COLORS.n800,
  },
] as const;

export default function Index() {
  const router = useRouter();
  const [activeCount, setActiveCount] = useState<number | null>(null);

  useEffect(() => {
    Api.teacherPublicList()
      .then((list: any[]) => setActiveCount(list.filter((t) => t.active).length))
      .catch(() => setActiveCount(0));
  }, []);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <ImageBackground
          source={{
            uri:
              "https://images.unsplash.com/photo-1709802247879-3d4241a05dc4?crop=entropy&cs=srgb&fm=jpg&q=70&w=1200",
          }}
          style={styles.hero}
          imageStyle={{ borderRadius: RADII.xl }}
        >
          <View style={styles.heroOverlay}>
            <Text style={styles.eyebrow}>GOVT SCHOOL</Text>
            <Text style={styles.heroTitle}>Exam Platform</Text>
            <Text style={styles.heroSub}>
              AI-powered classroom tests for every Indian school.
            </Text>
          </View>
        </ImageBackground>

        <Text style={styles.sectionLabel}>Select your role</Text>

        <View style={{ gap: SPACING.md }}>
          {ROLES.map((r) => (
            <TouchableOpacity
              key={r.key}
              testID={`role-${r.key}-btn`}
              activeOpacity={0.85}
              onPress={() => router.push(r.href as any)}
              style={[styles.roleCard, { borderLeftColor: r.color }]}
            >
              <View style={[styles.roleIcon, { backgroundColor: r.color + "1a" }]}>
                <Text style={{ fontSize: 28 }}>{r.icon}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.roleTitle}>{r.title}</Text>
                <Text style={styles.roleSub}>{r.subtitle}</Text>
              </View>
              <Text style={[styles.chev, { color: r.color }]}>›</Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>
            🟢 {activeCount === null ? "…" : activeCount} active teacher{activeCount === 1 ? "" : "s"} ·
            Powered by Gemini 2.5 Flash
          </Text>
          <Text style={styles.devText}>Developed by Ankur Malik</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },
  scroll: { padding: SPACING.lg, paddingBottom: SPACING.xxl },
  hero: {
    height: 220,
    borderRadius: RADII.xl,
    overflow: "hidden",
    marginBottom: SPACING.xl,
    justifyContent: "flex-end",
  },
  heroOverlay: {
    backgroundColor: "rgba(27,67,50,0.78)",
    padding: SPACING.lg,
    height: "100%",
    justifyContent: "flex-end",
  },
  eyebrow: {
    color: "#FFFFFFcc",
    fontSize: 11,
    letterSpacing: 3,
    fontWeight: "700",
    marginBottom: 4,
  },
  heroTitle: { color: "#fff", fontSize: 34, fontWeight: "800", lineHeight: 38 },
  heroSub: { color: "#FFFFFFdd", fontSize: 14, marginTop: 6 },
  sectionLabel: {
    color: COLORS.n700,
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 2,
    textTransform: "uppercase",
    marginBottom: SPACING.md,
  },
  roleCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: SPACING.md,
    backgroundColor: COLORS.paper,
    padding: SPACING.lg,
    borderRadius: RADII.lg,
    borderWidth: 1,
    borderColor: COLORS.n200,
    borderLeftWidth: 6,
    ...SHADOW_SM,
  },
  roleIcon: {
    width: 52, height: 52, borderRadius: RADII.md,
    alignItems: "center", justifyContent: "center",
  },
  roleTitle: { fontSize: 18, fontWeight: "700", color: COLORS.n900 },
  roleSub: { fontSize: 13, color: COLORS.n600, marginTop: 2 },
  chev: { fontSize: 28, fontWeight: "300" },
  footer: { marginTop: SPACING.xl, alignItems: "center" },
  footerText: { color: COLORS.n600, fontSize: 12 },
  devText: { color: COLORS.n500, fontSize: 11, marginTop: 4, fontStyle: "italic" },
});
