import React, { useState } from "react";
import { View, Text, StyleSheet, ScrollView, KeyboardAvoidingView, Platform } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Button, Input, Card, HeaderBar, Banner } from "../../src/ui";
import { COLORS, SPACING } from "../../src/theme";
import { Api } from "../../src/api";

export default function AdminLogin() {
  const router = useRouter();
  const [pwd, setPwd] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  const onLogin = async () => {
    setErr(""); setLoading(true);
    try {
      await Api.adminLogin(pwd);
      router.replace("/admin/dashboard");
    } catch (e: any) {
      setErr(e.message || "Wrong password");
    } finally { setLoading(false); }
  };

  return (
    <SafeAreaView style={s.safe}>
      <HeaderBar title="Admin Login" subtitle="Platform Management" onBack={() => router.replace("/")} testID="admin-login-header" />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={s.scroll}>
          <Card>
            <Text style={s.icon}>🛡️</Text>
            <Text style={s.title}>Welcome back, Admin</Text>
            <Text style={s.sub}>Enter your password to manage the platform.</Text>

            <Input
              testID="admin-password-input"
              placeholder="Admin password"
              secureTextEntry
              value={pwd}
              onChangeText={setPwd}
              onSubmitEditing={onLogin}
            />
            {err ? <Banner kind="error" testID="admin-login-error">{err}</Banner> : null}
            <Button title="Login as Admin" onPress={onLogin} loading={loading} testID="admin-login-btn" style={{ marginTop: SPACING.md }} />
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },
  scroll: { padding: SPACING.lg, paddingTop: SPACING.xl },
  icon: { fontSize: 40, marginBottom: 8 },
  title: { fontSize: 22, fontWeight: "700", color: COLORS.n900 },
  sub: { fontSize: 14, color: COLORS.n600, marginBottom: SPACING.lg, marginTop: 4 },
});
