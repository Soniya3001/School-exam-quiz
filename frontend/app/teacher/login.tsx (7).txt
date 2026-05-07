import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Button, Input, Card, HeaderBar, Banner } from "../../src/ui";
import { COLORS, SPACING, RADII, SHADOW_SM, SUBJECTS } from "../../src/theme";
import { Api } from "../../src/api";

export default function TeacherLogin() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [list, setList] = useState<any[]>([]);
  const [selected, setSelected] = useState("");
  const [pwd, setPwd] = useState("");
  const [schoolId, setSchoolId] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  // Register fields
  const [regName, setRegName] = useState("");
  const [regSubject, setRegSubject] = useState("");
  const [regPwd, setRegPwd] = useState("");
  const [regSchoolId, setRegSchoolId] = useState("");
  const [regSuccess, setRegSuccess] = useState(false);

  useEffect(() => {
    Api.teacherPublicList()
      .then((l: any[]) => setList(l.filter((t) => t.active && t.status === "active")))
      .catch(() => {});
  }, []);

  const onLogin = async () => {
    setErr("");
    if (!selected) return setErr("Please select your account.");
    if (!schoolId.trim()) return setErr("Please enter your School ID.");
    setLoading(true);
    try {
      const res = await Api.teacherLogin(selected, pwd, schoolId);
      await AsyncStorage.setItem("teacher", JSON.stringify(res));
      router.replace("/teacher/dashboard");
    } catch (e: any) {
      setErr(e.message || "Login failed");
    } finally { setLoading(false); }
  };

  const onRegister = async () => {
    setErr("");
    if (!regName.trim()) return setErr("Name required.");
    if (!regPwd.trim() || regPwd.length < 6) return setErr("Password min 6 characters.");
    if (!regSchoolId.trim()) return setErr("School ID required.");
    setLoading(true);
    try {
      await Api.teacherRegister({
        name: regName.trim(), subject: regSubject || "General",
        password: regPwd, school_id: regSchoolId.trim().toUpperCase(),
      });
      setRegSuccess(true);
    } catch (e: any) {
      setErr(e.message || "Registration failed");
    } finally { setLoading(false); }
  };

  if (regSuccess) return (
    <SafeAreaView style={s.safe}>
      <HeaderBar title="👩‍🏫 Registration" onBack={() => router.replace("/")} testID="teacher-reg-header" />
      <View style={s.center}>
        <Card>
          <Text style={{ fontSize: 48, textAlign: "center" }}>✅</Text>
          <Text style={{ fontSize: 18, fontWeight: "800", textAlign: "center", marginTop: 12, color: COLORS.primary }}>
            Registration Submitted!
          </Text>
          <Text style={{ color: COLORS.n600, textAlign: "center", marginTop: 8, lineHeight: 20 }}>
            Your account is pending admin approval.{"\n"}You will be able to login once approved.
          </Text>
          <Button title="Back to Login" onPress={() => { setMode("login"); setRegSuccess(false); }}
            style={{ marginTop: SPACING.lg }} testID="back-to-login-btn" />
        </Card>
      </View>
    </SafeAreaView>
  );

  return (
    <SafeAreaView style={s.safe}>
      <HeaderBar
        title={mode === "login" ? "👩‍🏫 Teacher Login" : "👩‍🏫 Register"}
        subtitle={mode === "login" ? "Select your account" : "Create your account"}
        onBack={() => router.replace("/")}
        testID="teacher-login-header"
      />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={s.scroll}>

          {/* Mode Toggle */}
          <View style={s.toggle}>
            <TouchableOpacity style={[s.toggleBtn, mode === "login" && s.toggleActive]} onPress={() => { setMode("login"); setErr(""); }}>
              <Text style={[s.toggleTxt, mode === "login" && s.toggleTxtActive]}>Login</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[s.toggleBtn, mode === "register" && s.toggleActive]} onPress={() => { setMode("register"); setErr(""); }}>
              <Text style={[s.toggleTxt, mode === "register" && s.toggleTxtActive]}>Register</Text>
            </TouchableOpacity>
          </View>

          {mode === "login" ? (
            <>
              {list.length === 0 ? (
                <Banner kind="warning" testID="no-teachers-banner">No active teachers yet.</Banner>
              ) : (
                <View style={{ gap: SPACING.sm }}>
                  {list.map((t) => (
                    <TouchableOpacity key={t.id} testID={`teacher-option-${t.id}`}
                      onPress={() => setSelected(t.id)} activeOpacity={0.85}
                      style={[s.option, selected === t.id && s.optionActive]}>
                      <View style={[s.avatar, selected === t.id && { backgroundColor: COLORS.primary }]}>
                        <Text style={{ fontSize: 22, color: selected === t.id ? "#fff" : COLORS.primary }}>👩‍🏫</Text>
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 16, fontWeight: "700", color: COLORS.n900 }}>{t.name}</Text>
                        <Text style={{ fontSize: 13, color: COLORS.n600 }}>{t.subject} · {t.id}</Text>
                        {t.school_id ? <Text style={{ fontSize: 11, color: COLORS.n500 }}>🏫 {t.school_id}</Text> : null}
                      </View>
                      {selected === t.id && <Text style={{ color: COLORS.primary, fontSize: 20, fontWeight: "800" }}>✓</Text>}
                    </TouchableOpacity>
                  ))}
                </View>
              )}
              <Card style={{ marginTop: SPACING.lg }}>
                <Input testID="school-id-input" placeholder="School ID (e.g. GSBV1003)"
                  value={schoolId} onChangeText={(v: string) => setSchoolId(v.toUpperCase())}
                  autoCapitalize="characters" style={{ marginBottom: SPACING.md }} />
                <Input testID="teacher-password-input" placeholder="Your password"
                  secureTextEntry value={pwd} onChangeText={setPwd}
                  onSubmitEditing={onLogin} style={{ marginBottom: SPACING.md }} />
                {err ? <Banner kind="error" testID="teacher-login-error">{err}</Banner> : null}
                <Button title="Login" onPress={onLogin} loading={loading} testID="teacher-login-btn" />
              </Card>
            </>
          ) : (
            <Card>
              <Input testID="reg-name-input" placeholder="Full name *" value={regName} onChangeText={setRegName} style={{ marginBottom: SPACING.md }} />
              <Input testID="reg-subject-input" placeholder="Subject (e.g. Mathematics)" value={regSubject} onChangeText={setRegSubject} style={{ marginBottom: SPACING.md }} />
              <Input testID="reg-school-id-input" placeholder="School ID * (e.g. GSBV1003)"
                value={regSchoolId} onChangeText={(v: string) => setRegSchoolId(v.toUpperCase())}
                autoCapitalize="characters" style={{ marginBottom: SPACING.md }} />
              <Input testID="reg-password-input" placeholder="Password * (min 6 chars)"
                secureTextEntry value={regPwd} onChangeText={setRegPwd} style={{ marginBottom: SPACING.md }} />
              {err ? <Banner kind="error" testID="teacher-reg-error">{err}</Banner> : null}
              <Banner kind="warning">Your account will be active after admin approval.</Banner>
              <Button title="Submit Registration" onPress={onRegister} loading={loading}
                variant="accent" testID="teacher-register-btn" style={{ marginTop: SPACING.md }} />
            </Card>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },
  scroll: { padding: SPACING.lg, gap: SPACING.md },
  center: { flex: 1, padding: SPACING.lg, justifyContent: "center" },
  toggle: { flexDirection: "row", backgroundColor: COLORS.muted, padding: 4, borderRadius: RADII.md },
  toggleBtn: { flex: 1, padding: 10, alignItems: "center", borderRadius: RADII.sm },
  toggleActive: { backgroundColor: "#fff" },
  toggleTxt: { color: COLORS.n600, fontWeight: "600" },
  toggleTxtActive: { color: COLORS.primary, fontWeight: "700" },
  option: {
    flexDirection: "row", alignItems: "center", gap: SPACING.md,
    backgroundColor: COLORS.paper, padding: SPACING.md, borderRadius: RADII.md,
    borderWidth: 2, borderColor: COLORS.n200, ...SHADOW_SM,
  },
  optionActive: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + "0d" },
  avatar: {
    width: 48, height: 48, borderRadius: RADII.md,
    backgroundColor: COLORS.primary + "1a",
    alignItems: "center", justifyContent: "center",
  },
});
