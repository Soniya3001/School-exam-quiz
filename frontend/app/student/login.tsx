import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, KeyboardAvoidingView, Platform, ImageBackground,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Button, Input, Card, HeaderBar, Banner, Picker } from "../../src/ui";
import { CLASSES, COLORS, RADII, SPACING, SUBJECTS } from "../../src/theme";
import { Api } from "../../src/api";

export default function StudentLogin() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [studentClass, setStudentClass] = useState("");
  const [subject, setSubject] = useState("");
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [hasHistory, setHasHistory] = useState(false);

  useEffect(() => {
    (async () => {
      const stored = await AsyncStorage.getItem("student");
      if (stored) {
        const s = JSON.parse(stored);
        setName(s.name || "");
        setStudentClass(s.student_class || "");
        setSubject(s.subject || "");
      }
    })();
  }, []);

  useEffect(() => {
    if (!name.trim() || !studentClass) { setHasHistory(false); return; }
    Api.studentHistory(name.trim(), studentClass)
      .then((h: any[]) => setHasHistory(h.length > 0))
      .catch(() => setHasHistory(false));
  }, [name, studentClass]);

  const onJoin = async () => {
    setErr("");
    if (!name.trim()) return setErr("Please enter your name.");
    if (!studentClass) return setErr("Please select your class.");
    if (!subject) return setErr("Please select your subject.");
    if (!code.trim()) return setErr("Please enter the join code.");
    setLoading(true);
    try {
      const test = await Api.findTest({
        join_code: code.trim().toUpperCase(),
        student_name: name.trim(),
        student_class: studentClass,
      });
      const session = {
        name: name.trim(),
        student_class: studentClass,
        subject,
        code: code.trim().toUpperCase(),
        test,
      };
      await AsyncStorage.setItem("student", JSON.stringify(session));
      if (test.already_attempted) {
        router.replace("/student/done");
      } else if (test.answers_revealed) {
        router.replace("/student/review");
      } else if (test.test_active) {
        router.replace("/student/test");
      } else {
        setErr("Test is not active yet.");
      }
    } catch (e: any) {
      setErr(e.message || "Failed");
    } finally { setLoading(false); }
  };

  return (
    <SafeAreaView style={s.safe}>
      <HeaderBar
        title="🎓 Join Class"
        subtitle="Enter your details to join"
        onBack={() => router.replace("/")}
        testID="student-login-header"
      />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={s.scroll}>
          <ImageBackground
            source={{ uri: "https://images.unsplash.com/photo-1709802247879-3d4241a05dc4?crop=entropy&cs=srgb&fm=jpg&q=70&w=900" }}
            style={s.hero}
            imageStyle={{ borderRadius: RADII.lg }}
          >
            <View style={s.heroOverlay}>
              <Text style={s.heroTitle}>Welcome, student!</Text>
              <Text style={s.heroSub}>Get the join code from your teacher to start.</Text>
            </View>
          </ImageBackground>

          <Card>
            <Input
              testID="student-name-input"
              placeholder="Your full name"
              value={name}
              onChangeText={setName}
              style={{ marginBottom: SPACING.md }}
            />
            <Picker label="Class" value={studentClass} onChange={setStudentClass} options={CLASSES} testID="student-class-picker" />
            <Picker label="Subject" value={subject} onChange={setSubject} options={SUBJECTS} testID="student-subject-picker" />
            <Input
              testID="student-code-input"
              placeholder="JOIN CODE"
              value={code}
              onChangeText={(v: string) => setCode(v.toUpperCase())}
              autoCapitalize="characters"
              style={{ letterSpacing: 4, fontSize: 18, fontWeight: "700", marginBottom: SPACING.md }}
            />
            {err ? <Banner kind="error" testID="student-login-error">{err}</Banner> : null}
            <Button
              title="Join & Start Test"
              onPress={onJoin}
              loading={loading}
              variant="accent"
              testID="student-join-btn"
            />
            {hasHistory && (
              <Button
                title="🗂 My Test History"
                variant="outline"
                onPress={() => router.push("/student/history")}
                testID="student-history-btn"
                style={{ marginTop: SPACING.sm }}
              />
            )}
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },
  scroll: { padding: SPACING.lg, gap: SPACING.md },
  hero: { height: 140, borderRadius: RADII.lg, overflow: "hidden", marginBottom: SPACING.md },
  heroOverlay: { backgroundColor: "rgba(217,119,87,0.78)", padding: SPACING.md, height: "100%", justifyContent: "flex-end" },
  heroTitle: { color: "#fff", fontSize: 22, fontWeight: "800" },
  heroSub: { color: "#fff", fontSize: 13, marginTop: 4 },
});
