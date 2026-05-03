import React, { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Image,
  KeyboardAvoidingView, Platform, ActivityIndicator,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter, useFocusEffect } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Button, Input, Card, HeaderBar, Banner, Pill, Picker, SectionTitle } from "../../src/ui";
import { CLASSES, COLORS, RADII, SPACING, SUBJECTS } from "../../src/theme";
import { Api } from "../../src/api";

export default function TeacherDashboard() {
  const router = useRouter();
  const [teacher, setTeacher] = useState<any>(null);
  const [tState, setTState] = useState<any>(null);
  const [code, setCode] = useState("");
  const [testClass, setTestClass] = useState("");
  const [subject, setSubject] = useState("");
  const [mode, setMode] = useState<"text" | "image">("text");
  const [lessonText, setLessonText] = useState("");
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [count, setCount] = useState("10");
  const [language, setLanguage] = useState<"English" | "Hindi">("English");
  const [difficulty, setDifficulty] = useState<1 | 2 | 3>(2);
  const [generating, setGenerating] = useState(false);
  const [activating, setActivating] = useState(false);
  const [revealing, setRevealing] = useState(false);
  const [err, setErr] = useState("");
  const [status, setStatus] = useState("");
  const [historyCount, setHistoryCount] = useState(0);

  const flash = (m: string) => { setStatus(m); setTimeout(() => setStatus(""), 2200); };

  const refresh = useCallback(async (tid?: string) => {
    const id = tid || teacher?.id; if (!id) return;
    try {
      const at = await Api.teacherState(id);
      setTState(at);
      setCode(at.join_code || "");
      setTestClass(at.test_class || "");
      setSubject(at.subject || "");
      const h = await Api.teacherHistory(id);
      setHistoryCount(h.length);
    } catch (e: any) { setErr(e.message); }
  }, [teacher]);

  useEffect(() => {
    (async () => {
      const stored = await AsyncStorage.getItem("teacher");
      if (!stored) { router.replace("/teacher/login"); return; }
      const t = JSON.parse(stored); setTeacher(t); refresh(t.id);
    })();
  }, []);

  useFocusEffect(useCallback(() => { if (teacher) refresh(teacher.id); }, [teacher, refresh]));

  const logout = async () => { await AsyncStorage.removeItem("teacher"); router.replace("/"); };

  const pickImage = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return setErr("Permission denied for media library.");
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      allowsEditing: false,
      base64: true,
      quality: 0.8,
    });
    if (res.canceled || !res.assets?.[0]) return;
    const a = res.assets[0];
    setImageBase64(a.base64 || null);
    setImagePreview(a.uri);
    setMode("image");
  };

  const onGenerate = async () => {
    setErr("");
    if (!testClass) return setErr("Please select a class.");
    if (!subject) return setErr("Please select a subject.");
    if (mode === "text" && !lessonText.trim()) return setErr("Please paste your lesson first.");
    if (mode === "image" && !imageBase64) return setErr("Please upload a lesson image.");
    setGenerating(true);
    try {
      await Api.teacherGenerate({
        teacher_id: teacher.id,
        lesson_text: mode === "text" ? lessonText : undefined,
        image_base64: mode === "image" ? imageBase64! : undefined,
        count: Math.max(3, Math.min(20, parseInt(count) || 10)),
        test_class: testClass,
        subject,
        language,
        difficulty,
      });
      flash("✅ Questions generated"); refresh();
    } catch (e: any) { setErr(`Failed: ${e.message}`); }
    setGenerating(false);
  };

  const onActivate = async () => {
    setErr(""); if (!code.trim()) return setErr("Set a join code first.");
    setActivating(true);
    try { await Api.teacherActivate(teacher.id, code.trim().toUpperCase()); flash("✅ Test activated"); refresh(); }
    catch (e: any) { setErr(e.message); }
    setActivating(false);
  };

  const onReveal = async () => {
    setRevealing(true);
    try { await Api.teacherReveal(teacher.id); flash("🔒 Test locked & saved"); refresh(); }
    catch (e: any) { setErr(e.message); }
    setRevealing(false);
  };

  if (!teacher || !tState) return (
    <SafeAreaView style={s.safe}><View style={s.center}><ActivityIndicator color={COLORS.primary} /></View></SafeAreaView>
  );

  const results = Object.entries(tState.results || {});

  const DIFF_OPTIONS = [
    { d: 1 as const, label: "Easy", emoji: "🟢", desc: "Basic recall", color: COLORS.success },
    { d: 2 as const, label: "Medium", emoji: "🟡", desc: "Understanding", color: COLORS.warning },
    { d: 3 as const, label: "Hard", emoji: "🔴", desc: "Analysis", color: COLORS.error },
  ];

  return (
    <SafeAreaView style={s.safe}>
      <HeaderBar
        title="📝 Teacher Dashboard"
        subtitle={`${teacher.name} · ${teacher.subject}`}
        right={
          <View style={{ flexDirection: "row", gap: 6 }}>
            {historyCount > 0 ? (
              <Button title={`🗂 ${historyCount}`} variant="ghost" onPress={() => router.push("/teacher/history")} testID="teacher-history-btn" />
            ) : null}
            <Button title="🚪" variant="ghost" onPress={logout} testID="teacher-logout-btn" />
          </View>
        }
        testID="teacher-dashboard-header"
      />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={s.scroll}>
          {status ? <Banner kind="success" testID="teacher-status">{status}</Banner> : null}
          {err ? <Banner kind="error" testID="teacher-error">{err}</Banner> : null}

          {/* Step 1: Class, Section & Subject */}
          <Card>
            <SectionTitle>1️⃣ Class & Subject</SectionTitle>
            <Picker label="Class" value={testClass} onChange={setTestClass} options={CLASSES} testID="teacher-class-picker" />
            <Picker label="Subject" value={subject} onChange={setSubject} options={SUBJECTS} testID="teacher-subject-picker" />

            {/* Language */}
            <Text style={s.fieldLabel}>Language</Text>
            <View style={s.langRow}>
              {(["English", "Hindi"] as const).map((l) => (
                <TouchableOpacity
                  key={l}
                  testID={`lang-${l.toLowerCase()}-btn`}
                  onPress={() => setLanguage(l)}
                  style={[s.langBtn, language === l && s.langActive]}
                >
                  <Text style={[s.langTxt, language === l && s.langTxtActive]}>
                    {l === "Hindi" ? "🇮🇳 हिंदी" : "🇬🇧 English"}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Difficulty */}
            <Text style={[s.fieldLabel, { marginTop: SPACING.md }]}>Difficulty Level</Text>
            <View style={s.diffRow}>
              {DIFF_OPTIONS.map(({ d, label, emoji, desc, color }) => (
                <TouchableOpacity
                  key={d}
                  testID={`diff-${d}-btn`}
                  onPress={() => setDifficulty(d)}
                  style={[
                    s.diffBtn,
                    difficulty === d && { borderColor: color, backgroundColor: color + "15" },
                  ]}
                >
                  <Text style={s.diffEmoji}>{emoji}</Text>
                  <Text style={[s.diffLabel, difficulty === d && { color }]}>{label}</Text>
                  <Text style={s.diffDesc}>{desc}</Text>
                </TouchableOpacity>
              ))}
            </View>

            {testClass && subject && (
              <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap", marginTop: SPACING.md }}>
                <Pill>{testClass}</Pill>
                <Pill color={COLORS.primary}>{subject}</Pill>
                <Pill color={COLORS.n700}>{language === "Hindi" ? "हिंदी" : "English"}</Pill>
                <Pill color={difficulty === 1 ? COLORS.success : difficulty === 3 ? COLORS.error : COLORS.warning}>
                  {["", "Easy", "Medium", "Hard"][difficulty]}
                </Pill>
              </View>
            )}
          </Card>

          {/* Step 2: Lesson input */}
          <Card>
            <SectionTitle>2️⃣ Lesson Source</SectionTitle>
            <View style={s.toggle}>
              <TouchableOpacity testID="mode-text-btn" style={[s.toggleBtn, mode === "text" && s.toggleActive]} onPress={() => setMode("text")}>
                <Text style={[s.toggleTxt, mode === "text" && s.toggleTxtActive]}>📝 Text</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="mode-image-btn" style={[s.toggleBtn, mode === "image" && s.toggleActive]} onPress={() => setMode("image")}>
                <Text style={[s.toggleTxt, mode === "image" && s.toggleTxtActive]}>📷 Image</Text>
              </TouchableOpacity>
            </View>

            {mode === "text" ? (
              <Input
                testID="lesson-text-input"
                placeholder="Paste your lesson content here…"
                value={lessonText}
                onChangeText={setLessonText}
                multiline
                style={{ minHeight: 140, paddingVertical: 12, textAlignVertical: "top" }}
              />
            ) : (
              <View>
                <Button title={imagePreview ? "📷 Change Image" : "📷 Upload Lesson Image"} variant="outline" onPress={pickImage} testID="upload-image-btn" />
                {imagePreview && (
                  <Image source={{ uri: imagePreview }} style={s.preview} resizeMode="contain" />
                )}
              </View>
            )}

            <View style={{ flexDirection: "row", alignItems: "center", gap: SPACING.md, marginTop: SPACING.md }}>
              <Text style={{ color: COLORS.n700, fontWeight: "600" }}>Questions:</Text>
              <Input
                testID="question-count-input"
                value={count}
                onChangeText={(v: string) => setCount(v.replace(/[^0-9]/g, ""))}
                keyboardType="number-pad"
                style={{ width: 80, textAlign: "center" }}
              />
            </View>
            <Button
              title={generating ? "🤖 Generating with Gemini…" : "🤖 Generate Questions"}
              onPress={onGenerate}
              loading={generating}
              variant="accent"
              testID="generate-questions-btn"
              style={{ marginTop: SPACING.md }}
            />
          </Card>

          {/* Step 3: Join code */}
          <Card>
            <SectionTitle>3️⃣ Join Code</SectionTitle>
            <Text style={{ color: COLORS.n600, marginBottom: SPACING.sm }}>
              Set a secret code that students will use to join your test.
            </Text>
            <Input
              testID="join-code-input"
              placeholder="e.g. MATHQUIZ"
              value={code}
              onChangeText={(v: string) => setCode(v.toUpperCase())}
              autoCapitalize="characters"
              style={{ letterSpacing: 3, fontSize: 18, fontWeight: "700" }}
            />
            {tState.join_code ? (
              <Banner kind="success" testID="active-code-banner">✅ Active code: {tState.join_code}</Banner>
            ) : null}
            <View style={{ flexDirection: "row", gap: SPACING.sm, marginTop: SPACING.md }}>
              <Button
                title={tState.test_active ? "🟢 LIVE" : "🚀 Activate Test"}
                onPress={onActivate}
                loading={activating}
                disabled={!tState.questions?.length || tState.test_active}
                testID="activate-test-btn"
                style={{ flex: 2 }}
              />
              <Button
                title={revealing ? "…" : "🔒 Reveal & Lock"}
                variant="outline"
                onPress={onReveal}
                loading={revealing}
                disabled={!tState.test_active && !tState.questions?.length}
                testID="reveal-answers-btn"
                style={{ flex: 1.4 }}
              />
            </View>
          </Card>

          {/* Questions Preview */}
          {tState.questions?.length > 0 && (
            <Card>
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                <SectionTitle>📊 Generated Questions ({tState.questions.length})</SectionTitle>
                {tState.answers_revealed && <Pill color={COLORS.warning}>LOCKED</Pill>}
              </View>
              {tState.questions.slice(0, 3).map((q: any, i: number) => (
                <View key={i} style={s.qPreview} testID={`q-preview-${i}`}>
                  <Text style={{ fontWeight: "700", color: COLORS.n900 }}>Q{i + 1}. {q.q}</Text>
                  {q.options.map((o: string, idx: number) => (
                    <Text key={idx} style={{ color: idx === q.answer ? COLORS.success : COLORS.n700, marginTop: 4 }}>
                      {idx === q.answer ? "✓ " : "○ "}{o}
                    </Text>
                  ))}
                </View>
              ))}
              {tState.questions.length > 3 && (
                <Text style={{ color: COLORS.n600, fontStyle: "italic" }}>…and {tState.questions.length - 3} more</Text>
              )}
            </Card>
          )}

          {/* Live Results */}
          {results.length > 0 && (
            <Card>
              <SectionTitle>👥 Student Results ({results.length})</SectionTitle>
              {results.map(([name, r]: any) => {
                const pct = Math.round((r.score / r.total) * 100);
                return (
                  <View key={name} style={s.resultRow} testID={`result-${name}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontWeight: "700" }}>{name}</Text>
                      {r.auto_submit && <Text style={{ color: COLORS.warning, fontSize: 11 }}>auto-submitted</Text>}
                    </View>
                    <Text style={{ color: pct >= 60 ? COLORS.success : COLORS.error, fontWeight: "800" }}>
                      {r.score}/{r.total} ({pct}%)
                    </Text>
                  </View>
                );
              })}
            </Card>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  scroll: { padding: SPACING.lg, paddingBottom: SPACING.xxl, gap: SPACING.md },
  fieldLabel: { color: COLORS.n700, fontWeight: "700", fontSize: 13, marginBottom: SPACING.sm },

  // Language
  langRow: { flexDirection: "row", gap: SPACING.sm },
  langBtn: {
    flex: 1, paddingVertical: 14, paddingHorizontal: 10,
    borderRadius: RADII.md, borderWidth: 2, borderColor: COLORS.n200,
    backgroundColor: COLORS.muted, alignItems: "center",
  },
  langActive: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + "15" },
  langTxt: { color: COLORS.n600, fontWeight: "600", fontSize: 14 },
  langTxtActive: { color: COLORS.primary, fontWeight: "700" },

  // Difficulty
  diffRow: { flexDirection: "row", gap: SPACING.sm },
  diffBtn: {
    flex: 1, paddingVertical: 16, paddingHorizontal: 8,
    borderRadius: RADII.md, borderWidth: 2, borderColor: COLORS.n200,
    backgroundColor: COLORS.muted, alignItems: "center",
  },
  diffEmoji: { fontSize: 22, marginBottom: 4 },
  diffLabel: { color: COLORS.n700, fontWeight: "700", fontSize: 14 },
  diffDesc: { color: COLORS.n500, fontSize: 10, marginTop: 2, textAlign: "center" },

  // Toggle
  toggle: { flexDirection: "row", backgroundColor: COLORS.muted, padding: 4, borderRadius: RADII.md, marginBottom: SPACING.md },
  toggleBtn: { flex: 1, padding: 10, alignItems: "center", borderRadius: RADII.sm },
  toggleActive: { backgroundColor: "#fff" },
  toggleTxt: { color: COLORS.n600, fontWeight: "600" },
  toggleTxtActive: { color: COLORS.primary },

  preview: { width: "100%", height: 220, marginTop: SPACING.md, borderRadius: RADII.md, backgroundColor: COLORS.muted },
  qPreview: { padding: SPACING.md, backgroundColor: COLORS.muted, borderRadius: RADII.md, marginTop: SPACING.sm },
  resultRow: { flexDirection: "row", alignItems: "center", paddingVertical: 10, borderBottomWidth: 1, borderColor: COLORS.n100 },
});
