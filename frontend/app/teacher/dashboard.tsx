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

const DIFF_OPTIONS = [
  { d: 1 as const, label: "Easy", emoji: "🟢", desc: "Basic recall", color: COLORS.success },
  { d: 2 as const, label: "Medium", emoji: "🟡", desc: "Understanding", color: COLORS.warning },
  { d: 3 as const, label: "Hard", emoji: "🔴", desc: "Analysis", color: COLORS.error },
];

export default function TeacherDashboard() {
  const router = useRouter();
  const [teacher, setTeacher] = useState<any>(null);
  const [allTests, setAllTests] = useState<any[]>([]);
  const [selectedTest, setSelectedTest] = useState<any>(null);
  const [testClass, setTestClass] = useState("");
  const [subject, setSubject] = useState("");
  const [mode, setMode] = useState<"text" | "image">("text");
  const [lessonText, setLessonText] = useState("");
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [count, setCount] = useState("10");
  const [language, setLanguage] = useState<"English" | "Hindi">("English");
  const [difficulty, setDifficulty] = useState<1 | 2 | 3>(2);
  const [testType, setTestType] = useState<"mcq" | "subjective">("mcq");
  const [generating, setGenerating] = useState(false);
  const [activating, setActivating] = useState(false);
  const [revealing, setRevealing] = useState(false);
  const [err, setErr] = useState("");
  const [status, setStatus] = useState("");
  const [historyCount, setHistoryCount] = useState(0);

  const flash = (m: string) => { setStatus(m); setTimeout(() => setStatus(""), 2200); };

  const refresh = useCallback(async (tid?: string) => {
    const id = tid || teacher?.id;
    if (!id) return;
    try {
      const res = await Api.teacherState(id);
      const tests = res.tests || [];
      setAllTests(tests);
      if (selectedTest) {
        const updated = tests.find((t: any) => t.test_class === selectedTest.test_class);
        setSelectedTest(updated || tests[0] || null);
      } else if (tests.length > 0) {
        setSelectedTest(tests[0]);
      }
      const h = await Api.teacherHistory(id);
      setHistoryCount(h.length);
    } catch (e: any) { setErr(e.message); }
  }, [teacher, selectedTest]);

  useEffect(() => {
    (async () => {
      const stored = await AsyncStorage.getItem("teacher");
      if (!stored) { router.replace("/teacher/login"); return; }
      const t = JSON.parse(stored);
      setTeacher(t);
      refresh(t.id);
    })();
  }, []);

  useFocusEffect(useCallback(() => { if (teacher) refresh(teacher.id); }, [teacher, refresh]));

  const logout = async () => { await AsyncStorage.removeItem("teacher"); router.replace("/"); };

  const pickImage = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return setErr("Permission denied.");
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"], allowsEditing: false, base64: true, quality: 0.8,
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
      const res = await Api.teacherGenerate({
        teacher_id: teacher.id,
        lesson_text: mode === "text" ? lessonText : undefined,
        image_base64: mode === "image" ? imageBase64! : undefined,
        count: Math.max(3, Math.min(20, parseInt(count) || 10)),
        test_class: testClass,
        subject, language, difficulty,
        test_type: testType,
      });
      flash(`✅ Questions generated | Code: ${res.join_code}`);
      refresh();
    } catch (e: any) { setErr(`Failed: ${e.message}`); }
    setGenerating(false);
  };

  const onActivate = async (test: any) => {
    setErr("");
    if (!test?.join_code) return setErr("No join code found.");
    setActivating(true);
    try {
      await Api.teacherActivate(teacher.id, test.join_code);
      flash("✅ Test activated");
      refresh();
    } catch (e: any) { setErr(e.message); }
    setActivating(false);
  };

  const onReveal = async (test: any) => {
    setRevealing(true);
    try {
      await Api.teacherReveal(teacher.id, test.test_class);
      flash("🔒 Test locked & saved");
      refresh();
    } catch (e: any) { setErr(e.message); }
    setRevealing(false);
  };

  if (!teacher) return (
    <SafeAreaView style={s.safe}><View style={s.center}><ActivityIndicator color={COLORS.primary} /></View></SafeAreaView>
  );

  return (
    <SafeAreaView style={s.safe}>
      <HeaderBar
        title="📝 Dashboard"
        subtitle={`${teacher.name} · ${teacher.subject}${teacher.school_id ? ` · 🏫 ${teacher.school_id}` : ""}`}
        right={
          <View style={{ flexDirection: "row", gap: 6 }}>
            {historyCount > 0 && <Button title={`🗂 ${historyCount}`} variant="ghost" onPress={() => router.push("/teacher/history")} testID="teacher-history-btn" />}
            <Button title="🚪" variant="ghost" onPress={logout} testID="teacher-logout-btn" />
          </View>
        }
        testID="teacher-dashboard-header"
      />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={s.scroll}>
          {status ? <Banner kind="success" testID="teacher-status">{status}</Banner> : null}
          {err ? <Banner kind="error" testID="teacher-error">{err}</Banner> : null}

          {/* Active Tests Summary */}
          {allTests.length > 0 && (
            <Card>
              <SectionTitle>📋 Your Active Tests</SectionTitle>
              {allTests.map((test: any, i: number) => (
                <TouchableOpacity key={i} onPress={() => setSelectedTest(test)}
                  style={[s.testRow, selectedTest?.test_class === test.test_class && s.testRowActive]}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontWeight: "700", color: COLORS.n900 }}>{test.test_class}</Text>
                    <Text style={{ fontSize: 12, color: COLORS.n600 }}>{test.subject} · {test.test_type?.toUpperCase()} · Code: <Text style={{ fontWeight: "700", color: COLORS.primary }}>{test.join_code}</Text></Text>
                    <Text style={{ fontSize: 11, color: COLORS.n500 }}>{Object.keys(test.results || {}).length} students submitted</Text>
                  </View>
                  <View style={{ alignItems: "flex-end", gap: 4 }}>
                    {test.test_active && <Pill color={COLORS.success}>LIVE</Pill>}
                    {test.answers_revealed && <Pill color={COLORS.warning}>LOCKED</Pill>}
                    {!test.test_active && !test.answers_revealed && test.questions?.length > 0 && <Pill color={COLORS.n500}>READY</Pill>}
                  </View>
                </TouchableOpacity>
              ))}
            </Card>
          )}

          {/* Generate New Test */}
          <Card>
            <SectionTitle>1️⃣ Class & Subject</SectionTitle>
            <Picker label="Class" value={testClass} onChange={setTestClass} options={CLASSES} testID="teacher-class-picker" />
            <Picker label="Subject" value={subject} onChange={setSubject} options={SUBJECTS} testID="teacher-subject-picker" />

            {/* Test Type */}
            <Text style={s.fieldLabel}>Test Type</Text>
            <View style={s.typeRow}>
              <TouchableOpacity testID="type-mcq-btn" onPress={() => setTestType("mcq")}
                style={[s.typeBtn, testType === "mcq" && { borderColor: COLORS.primary, backgroundColor: COLORS.primary + "15" }]}>
                <Text style={{ fontSize: 24 }}>📝</Text>
                <Text style={[s.typeTxt, testType === "mcq" && { color: COLORS.primary, fontWeight: "700" }]}>MCQ</Text>
                <Text style={s.typeDesc}>Multiple Choice</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="type-subjective-btn" onPress={() => setTestType("subjective")}
                style={[s.typeBtn, testType === "subjective" && { borderColor: COLORS.accent, backgroundColor: COLORS.accent + "15" }]}>
                <Text style={{ fontSize: 24 }}>✍️</Text>
                <Text style={[s.typeTxt, testType === "subjective" && { color: COLORS.accent, fontWeight: "700" }]}>Subjective</Text>
                <Text style={s.typeDesc}>20 marks · CBSE</Text>
              </TouchableOpacity>
            </View>

            {testType === "subjective" && (
              <Banner kind="warning">
                📋 Subjective test: 4×1 + 4×2 + 2×4 = 20 marks total (CBSE/NCERT pattern)
              </Banner>
            )}

            {/* Language */}
            <Text style={[s.fieldLabel, { marginTop: SPACING.md }]}>Language</Text>
            <View style={s.langRow}>
              {(["English", "Hindi"] as const).map((l) => (
                <TouchableOpacity key={l} testID={`lang-${l.toLowerCase()}-btn`} onPress={() => setLanguage(l)}
                  style={[s.langBtn, language === l && s.langActive]}>
                  <Text style={[s.langTxt, language === l && s.langTxtActive]}>
                    {l === "Hindi" ? "🇮🇳 हिंदी" : "🇬🇧 English"}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Difficulty (MCQ only) */}
            {testType === "mcq" && (
              <>
                <Text style={[s.fieldLabel, { marginTop: SPACING.md }]}>Difficulty</Text>
                <View style={s.diffRow}>
                  {DIFF_OPTIONS.map(({ d, label, emoji, desc, color }) => (
                    <TouchableOpacity key={d} testID={`diff-${d}-btn`} onPress={() => setDifficulty(d)}
                      style={[s.diffBtn, difficulty === d && { borderColor: color, backgroundColor: color + "15" }]}>
                      <Text style={s.diffEmoji}>{emoji}</Text>
                      <Text style={[s.diffLabel, difficulty === d && { color }]}>{label}</Text>
                      <Text style={s.diffDesc}>{desc}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </>
            )}
          </Card>

          {/* Lesson Source */}
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
              <Input testID="lesson-text-input" placeholder="Paste your lesson content here…"
                value={lessonText} onChangeText={setLessonText} multiline
                style={{ minHeight: 140, paddingVertical: 12, textAlignVertical: "top" }} />
            ) : (
              <View>
                <Button title={imagePreview ? "📷 Change Image" : "📷 Upload Lesson Image"} variant="outline" onPress={pickImage} testID="upload-image-btn" />
                {imagePreview && <Image source={{ uri: imagePreview }} style={s.preview} resizeMode="contain" />}
              </View>
            )}
            {testType === "mcq" && (
              <View style={{ flexDirection: "row", alignItems: "center", gap: SPACING.md, marginTop: SPACING.md }}>
                <Text style={{ color: COLORS.n700, fontWeight: "600" }}>Questions:</Text>
                <Input testID="question-count-input" value={count}
                  onChangeText={(v: string) => setCount(v.replace(/[^0-9]/g, ""))}
                  keyboardType="number-pad" style={{ width: 80, textAlign: "center" }} />
              </View>
            )}
            {err ? <Banner kind="error">{err}</Banner> : null}
            <Button
              title={generating ? "🤖 Generating…" : "🤖 Generate Questions with AI"}
              onPress={onGenerate} loading={generating} variant="accent"
              testID="generate-questions-btn" style={{ marginTop: SPACING.md }} />
          </Card>

          {/* Selected Test Details */}
          {selectedTest && selectedTest.questions?.length > 0 && (
            <Card>
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: SPACING.sm }}>
                <SectionTitle>{selectedTest.test_class} — {selectedTest.subject}</SectionTitle>
                <View style={{ flexDirection: "row", gap: 4 }}>
                  <Pill color={COLORS.primary}>{selectedTest.test_type?.toUpperCase()}</Pill>
                  {selectedTest.test_active && <Pill color={COLORS.success}>LIVE</Pill>}
                  {selectedTest.answers_revealed && <Pill color={COLORS.warning}>LOCKED</Pill>}
                </View>
              </View>

              {/* Auto Join Code */}
              <View style={s.codeBox}>
                <Text style={{ fontSize: 12, color: COLORS.n600, marginBottom: 4 }}>🔑 Auto-generated Join Code:</Text>
                <Text style={s.codeText}>{selectedTest.join_code}</Text>
                <Text style={{ fontSize: 11, color: COLORS.n500, marginTop: 4 }}>Share this code with your {selectedTest.test_class} students only</Text>
              </View>

              {/* Questions Preview */}
              <Text style={{ fontWeight: "700", color: COLORS.n700, marginBottom: SPACING.sm }}>
                Questions ({selectedTest.questions.length}) {selectedTest.test_type === "subjective" ? `· ${selectedTest.total_marks} marks` : ""}:
              </Text>
              {selectedTest.questions.slice(0, 3).map((q: any, i: number) => (
                <View key={i} style={s.qPreview} testID={`q-preview-${i}`}>
                  {selectedTest.test_type === "subjective" && (
                    <Pill color={q.marks === 1 ? COLORS.success : q.marks === 2 ? COLORS.warning : COLORS.error} style={{ marginBottom: 4 }}>
                      Section {q.section} · {q.marks} marks
                    </Pill>
                  )}
                  <Text style={{ fontWeight: "700", color: COLORS.n900 }}>Q{i + 1}. {q.q}</Text>
                  {selectedTest.test_type === "mcq" && q.options?.map((o: string, idx: number) => (
                    <Text key={idx} style={{ color: idx === q.answer ? COLORS.success : COLORS.n700, marginTop: 4 }}>
                      {idx === q.answer ? "✓ " : "○ "}{o}
                    </Text>
                  ))}
                </View>
              ))}
              {selectedTest.questions.length > 3 && (
                <Text style={{ color: COLORS.n600, fontStyle: "italic" }}>…and {selectedTest.questions.length - 3} more</Text>
              )}

              {/* Actions */}
              <View style={{ flexDirection: "row", gap: SPACING.sm, marginTop: SPACING.md }}>
                <Button
                  title={selectedTest.test_active ? "🟢 LIVE" : "🚀 Activate"}
                  onPress={() => onActivate(selectedTest)}
                  loading={activating}
                  disabled={selectedTest.test_active}
                  testID="activate-test-btn"
                  style={{ flex: 1 }}
                />
                <Button
                  title="🔒 Lock"
                  variant="outline"
                  onPress={() => onReveal(selectedTest)}
                  loading={revealing}
                  disabled={!selectedTest.test_active}
                  testID="reveal-answers-btn"
                  style={{ flex: 1 }}
                />
              </View>

              {/* Results */}
              {Object.entries(selectedTest.results || {}).length > 0 && (
                <>
                  <SectionTitle style={{ marginTop: SPACING.md }}>👥 Results ({Object.entries(selectedTest.results).length})</SectionTitle>
                  {Object.entries(selectedTest.results).map(([name, r]: any) => {
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
                </>
              )}
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
  testRow: {
    flexDirection: "row", alignItems: "center", padding: SPACING.md,
    borderRadius: RADII.md, borderWidth: 2, borderColor: COLORS.n200,
    backgroundColor: COLORS.muted, marginBottom: SPACING.sm,
  },
  testRowActive: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + "0d" },
  typeRow: { flexDirection: "row", gap: SPACING.sm, marginBottom: SPACING.sm },
  typeBtn: {
    flex: 1, padding: SPACING.md, borderRadius: RADII.md, borderWidth: 2,
    borderColor: COLORS.n200, backgroundColor: COLORS.muted, alignItems: "center",
  },
  typeTxt: { color: COLORS.n700, fontWeight: "600", fontSize: 14, marginTop: 4 },
  typeDesc: { color: COLORS.n500, fontSize: 11, marginTop: 2 },
  langRow: { flexDirection: "row", gap: SPACING.sm },
  langBtn: {
    flex: 1, paddingVertical: 14, borderRadius: RADII.md, borderWidth: 2,
    borderColor: COLORS.n200, backgroundColor: COLORS.muted, alignItems: "center",
  },
  langActive: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + "15" },
  langTxt: { color: COLORS.n600, fontWeight: "600", fontSize: 14 },
  langTxtActive: { color: COLORS.primary, fontWeight: "700" },
  diffRow: { flexDirection: "row", gap: SPACING.sm },
  diffBtn: {
    flex: 1, paddingVertical: 16, borderRadius: RADII.md, borderWidth: 2,
    borderColor: COLORS.n200, backgroundColor: COLORS.muted, alignItems: "center",
  },
  diffEmoji: { fontSize: 22, marginBottom: 4 },
  diffLabel: { color: COLORS.n700, fontWeight: "700", fontSize: 14 },
  diffDesc: { color: COLORS.n500, fontSize: 10, marginTop: 2, textAlign: "center" },
  toggle: { flexDirection: "row", backgroundColor: COLORS.muted, padding: 4, borderRadius: RADII.md, marginBottom: SPACING.md },
  toggleBtn: { flex: 1, padding: 10, alignItems: "center", borderRadius: RADII.sm },
  toggleActive: { backgroundColor: "#fff" },
  toggleTxt: { color: COLORS.n600, fontWeight: "600" },
  toggleTxtActive: { color: COLORS.primary },
  preview: { width: "100%", height: 220, marginTop: SPACING.md, borderRadius: RADII.md, backgroundColor: COLORS.muted },
  codeBox: {
    backgroundColor: COLORS.primary + "0d", borderRadius: RADII.md,
    padding: SPACING.md, marginBottom: SPACING.md, alignItems: "center",
  },
  codeText: { fontSize: 28, fontWeight: "900", letterSpacing: 6, color: COLORS.primary },
  qPreview: { padding: SPACING.md, backgroundColor: COLORS.muted, borderRadius: RADII.md, marginTop: SPACING.sm },
  resultRow: { flexDirection: "row", alignItems: "center", paddingVertical: 10, borderBottomWidth: 1, borderColor: COLORS.n100 },
});
