import React, { useEffect, useRef, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, AppState, ActivityIndicator,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Button, Card, Banner, Pill } from "../../src/ui";
import { COLORS, RADII, SPACING } from "../../src/theme";
import { Api } from "../../src/api";

export default function StudentTest() {
  const router = useRouter();
  const [session, setSession] = useState<any>(null);
  const [answers, setAnswers] = useState<Record<string, any>>({});
  const [current, setCurrent] = useState(0);
  const [timeLeft, setTimeLeft] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");
  const submittedRef = useRef(false);
  const answersRef = useRef<Record<string, any>>({});
  const sessionRef = useRef<any>(null);
  const timerRef = useRef<any>(null);

  useEffect(() => { answersRef.current = answers; }, [answers]);

  useEffect(() => {
    (async () => {
      const stored = await AsyncStorage.getItem("student");
      if (!stored) { router.replace("/student/login"); return; }
      const s = JSON.parse(stored);
      setSession(s); sessionRef.current = s;
      const testType = s.test?.test_type || "mcq";
      // Subjective gets more time: 3 min per question
      const perQ = testType === "subjective" ? 180 : 30;
      const total = (s.test?.questions?.length || 10) * perQ;
      setTimeLeft(total);
      timerRef.current = setInterval(() => {
        setTimeLeft((p) => {
          if (p === null) return p;
          if (p <= 1) { doSubmit(false); return 0; }
          return p - 1;
        });
      }, 1000);
    })();
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  // Anti-cheat
  useEffect(() => {
    const sub = AppState.addEventListener("change", (st) => {
      if (st !== "active" && !submittedRef.current) doSubmit(true);
    });
    let visHandler: any;
    if (typeof document !== "undefined") {
      visHandler = () => { if (document.hidden && !submittedRef.current) doSubmit(true); };
      document.addEventListener("visibilitychange", visHandler);
    }
    return () => {
      sub.remove();
      if (visHandler && typeof document !== "undefined") document.removeEventListener("visibilitychange", visHandler);
    };
  }, []);

  const doSubmit = async (auto: boolean) => {
    if (submittedRef.current) return;
    submittedRef.current = true;
    if (timerRef.current) clearInterval(timerRef.current);
    const sess = sessionRef.current;
    if (!sess) return;
    setSubmitting(true);
    try {
      const res = await Api.submit({
        student_name: sess.name,
        student_class: sess.student_class,
        student_subject: sess.subject,
        join_code: sess.code,
        answers: answersRef.current,
        auto_submit: auto,
      });
      const newSess = { ...sess, result: res, autoSubmit: auto };
      await AsyncStorage.setItem("student", JSON.stringify(newSess));
      router.replace("/student/done");
    } catch (e: any) {
      submittedRef.current = false;
      setErr(e.message || "Submit failed");
      setSubmitting(false);
    }
  };

  if (!session) return <View style={s.center}><ActivityIndicator color={COLORS.primary} /></View>;

  const questions = session.test?.questions || [];
  const testType = session.test?.test_type || "mcq";
  const totalMarks = session.test?.total_marks || questions.length;
  const total = questions.length;
  const answered = Object.keys(answers).length;
  const minutes = Math.floor((timeLeft || 0) / 60);
  const seconds = String((timeLeft || 0) % 60).padStart(2, "0");
  const lowTime = (timeLeft || 0) < 60;

  if (total === 0) return (
    <SafeAreaView style={s.safe}>
      <View style={s.center}><Text style={{ color: COLORS.n600 }}>No questions found.</Text></View>
    </SafeAreaView>
  );

  // ── SUBJECTIVE: Show full question paper at once ──────
  if (testType === "subjective") {
    const sections = ["A", "B", "C"];
    const sectionLabels: Record<string, string> = {
      A: "Section A — 1 Mark Questions",
      B: "Section B — 2 Marks Questions",
      C: "Section C — 4 Marks Questions",
    };

    return (
      <SafeAreaView style={s.safe}>
        {/* Header */}
        <View style={s.topBar}>
          <View style={{ flex: 1 }}>
            <Text style={s.qLabel}>Subjective Test · {totalMarks} Marks</Text>
            <Text style={{ fontSize: 11, color: COLORS.n500 }}>{answered}/{total} answered</Text>
          </View>
          <View style={[s.timer, lowTime && { backgroundColor: COLORS.error + "1a", borderColor: COLORS.error }]}>
            <Text style={[s.timerTxt, lowTime && { color: COLORS.error }]}>⏱ {minutes}:{seconds}</Text>
          </View>
        </View>

        <ScrollView contentContainerStyle={s.scroll}>
          {/* Paper Header */}
          <Card style={{ marginBottom: SPACING.md, backgroundColor: COLORS.primary + "0d" }}>
            <Text style={{ fontWeight: "800", fontSize: 16, color: COLORS.primary, textAlign: "center" }}>
              {session.test?.subject} — {session.test?.test_class}
            </Text>
            <Text style={{ textAlign: "center", color: COLORS.n600, marginTop: 4, fontSize: 13 }}>
              Total Marks: {totalMarks} | Time: {Math.round((questions.length * 180) / 60)} minutes
            </Text>
            <Text style={{ textAlign: "center", color: COLORS.n600, fontSize: 12, marginTop: 4 }}>
              General Instructions: Answer all questions. Write clearly and concisely.
            </Text>
          </Card>

          {err ? <Banner kind="error">{err}</Banner> : null}

          {/* Render by Section */}
          {sections.map((sec) => {
            const secQs = questions.map((q: any, i: number) => ({ ...q, _idx: i })).filter((q: any) => q.section === sec);
            if (secQs.length === 0) return null;
            return (
              <View key={sec} style={{ marginBottom: SPACING.lg }}>
                <View style={s.sectionHeader}>
                  <Text style={s.sectionTitle}>{sectionLabels[sec]}</Text>
                </View>
                {secQs.map((q: any) => (
                  <Card key={q._idx} style={{ marginBottom: SPACING.md }}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: SPACING.sm }}>
                      <Text style={s.qText} testID={`q-text-${q._idx}`}>
                        <Text style={{ color: COLORS.n500 }}>Q{q._idx + 1}. </Text>
                        {q.q}
                      </Text>
                      <View style={[s.marksBadge, {
                        backgroundColor: q.marks === 1 ? COLORS.success + "20" : q.marks === 2 ? COLORS.warning + "20" : COLORS.error + "20",
                      }]}>
                        <Text style={[s.marksText, {
                          color: q.marks === 1 ? COLORS.success : q.marks === 2 ? COLORS.warning : COLORS.error,
                        }]}>[{q.marks} mark{q.marks > 1 ? "s" : ""}]</Text>
                      </View>
                    </View>
                    <TextInput
                      testID={`subj-answer-${q._idx}`}
                      value={answers[String(q._idx)] || ""}
                      onChangeText={(v) => setAnswers({ ...answers, [String(q._idx)]: v })}
                      placeholder={
                        q.marks === 1 ? "Write your answer here (1-2 sentences)…"
                        : q.marks === 2 ? "Write your answer here (3-4 sentences)…"
                        : "Write a detailed answer (one paragraph)…"
                      }
                      multiline
                      style={[s.textInput, {
                        minHeight: q.marks === 1 ? 60 : q.marks === 2 ? 100 : 160,
                      }]}
                      placeholderTextColor={COLORS.n400}
                    />
                    {answers[String(q._idx)] ? (
                      <Text style={{ fontSize: 11, color: COLORS.success, marginTop: 4 }}>✓ Answered</Text>
                    ) : (
                      <Text style={{ fontSize: 11, color: COLORS.n400, marginTop: 4 }}>Not answered yet</Text>
                    )}
                  </Card>
                ))}
              </View>
            );
          })}

          {/* Submit */}
          <Card style={{ backgroundColor: COLORS.accent + "0d", borderColor: COLORS.accent + "55", borderWidth: 1 }}>
            <Text style={{ fontWeight: "700", color: COLORS.n800, marginBottom: SPACING.sm }}>
              📝 {answered}/{total} questions answered
            </Text>
            {answered < total && (
              <Banner kind="warning" style={{ marginBottom: SPACING.sm }}>
                {total - answered} question(s) unanswered. You can still submit.
              </Banner>
            )}
            <Button
              title={submitting ? "Submitting…" : "✓ Submit Test"}
              variant="accent"
              onPress={() => doSubmit(false)}
              loading={submitting}
              testID="submit-btn"
            />
          </Card>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ── MCQ: One question at a time ───────────────────────
  const q = questions[current];
  const progress = ((current + 1) / total) * 100;

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.topBar}>
        <View style={{ flex: 1 }}>
          <Text style={s.qLabel}>Question {current + 1} / {total}</Text>
          <View style={s.progressBg}><View style={[s.progressFill, { width: `${progress}%` }]} /></View>
        </View>
        <View style={[s.timer, lowTime && { backgroundColor: COLORS.error + "1a", borderColor: COLORS.error }]} testID="timer-pill">
          <Text style={[s.timerTxt, lowTime && { color: COLORS.error }]}>⏱ {minutes}:{seconds}</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={s.scroll}>
        <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap", marginBottom: SPACING.sm }}>
          {session.test?.test_class && <Pill>{session.test.test_class}</Pill>}
          {session.test?.subject && <Pill color={COLORS.accent}>{session.test.subject}</Pill>}
          <Pill color={COLORS.n600}>{answered}/{total} answered</Pill>
        </View>

        <Card>
          <Text style={s.qText} testID={`q-text-${current}`}>{q.q}</Text>
          <View style={{ marginTop: SPACING.md, gap: SPACING.sm }}>
            {(q.options || []).map((opt: string, i: number) => {
              const selected = answers[String(current)] === i;
              return (
                <TouchableOpacity key={i} testID={`opt-${current}-${i}`} activeOpacity={0.85}
                  onPress={() => setAnswers({ ...answers, [String(current)]: i })}
                  style={[s.opt, selected && s.optActive]}>
                  <View style={[s.optBullet, selected && { backgroundColor: COLORS.primary, borderColor: COLORS.primary }]}>
                    <Text style={{ color: selected ? "#fff" : COLORS.n700, fontWeight: "700" }}>{String.fromCharCode(65 + i)}</Text>
                  </View>
                  <Text style={[s.optTxt, selected && { color: COLORS.primary, fontWeight: "600" }]}>{opt}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </Card>

        {err ? <Banner kind="error">{err}</Banner> : null}

        <View style={{ flexDirection: "row", gap: SPACING.sm, marginTop: SPACING.md }}>
          <Button title="← Prev" variant="outline" onPress={() => setCurrent(Math.max(0, current - 1))} disabled={current === 0} testID="prev-btn" style={{ flex: 1 }} />
          {current < total - 1 ? (
            <Button title="Next →" onPress={() => setCurrent(current + 1)} testID="next-btn" style={{ flex: 1.5 }} />
          ) : (
            <Button title={submitting ? "Submitting…" : "✓ Submit Test"} variant="accent" onPress={() => doSubmit(false)} loading={submitting} testID="submit-btn" style={{ flex: 1.5 }} />
          )}
        </View>

        {/* Question grid */}
        <Card style={{ marginTop: SPACING.md }}>
          <Text style={{ fontWeight: "700", marginBottom: SPACING.sm }}>Jump to question</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {questions.map((_: any, i: number) => {
              const isAns = answers[String(i)] !== undefined;
              const isCurr = current === i;
              return (
                <TouchableOpacity key={i} testID={`jump-${i}`} onPress={() => setCurrent(i)}
                  style={[s.jump, isAns && { backgroundColor: COLORS.success, borderColor: COLORS.success }, isCurr && !isAns && { borderColor: COLORS.primary }]}>
                  <Text style={{ fontWeight: "700", color: isAns ? "#fff" : COLORS.n800 }}>{i + 1}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </Card>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  topBar: { flexDirection: "row", alignItems: "center", padding: SPACING.lg, gap: SPACING.md, backgroundColor: COLORS.paper, borderBottomWidth: 1, borderColor: COLORS.n200 },
  qLabel: { fontSize: 12, color: COLORS.n600, marginBottom: 6, fontWeight: "600", letterSpacing: 1 },
  progressBg: { height: 8, backgroundColor: COLORS.n200, borderRadius: RADII.pill, overflow: "hidden" },
  progressFill: { height: 8, backgroundColor: COLORS.primary, borderRadius: RADII.pill },
  timer: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: RADII.pill, backgroundColor: COLORS.primary + "1a", borderWidth: 1, borderColor: COLORS.primary + "55" },
  timerTxt: { color: COLORS.primary, fontWeight: "800", fontSize: 14 },
  scroll: { padding: SPACING.lg, paddingBottom: SPACING.xxl },
  sectionHeader: { backgroundColor: COLORS.primary, borderRadius: RADII.md, padding: SPACING.sm, marginBottom: SPACING.sm },
  sectionTitle: { color: "#fff", fontWeight: "800", fontSize: 14, textAlign: "center" },
  qText: { fontSize: 16, fontWeight: "600", color: COLORS.n900, lineHeight: 24, flex: 1 },
  marksBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: RADII.sm, marginLeft: SPACING.sm },
  marksText: { fontSize: 11, fontWeight: "700" },
  textInput: {
    borderWidth: 1.5, borderColor: COLORS.n300, borderRadius: RADII.md,
    padding: SPACING.md, fontSize: 15, color: COLORS.n900,
    backgroundColor: "#fff", textAlignVertical: "top", marginTop: SPACING.sm,
  },
  opt: { flexDirection: "row", alignItems: "center", gap: SPACING.md, padding: SPACING.md, borderRadius: RADII.md, borderWidth: 2, borderColor: COLORS.n200, backgroundColor: "#fff" },
  optActive: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + "0d" },
  optBullet: { width: 36, height: 36, borderRadius: 18, borderWidth: 2, borderColor: COLORS.n300, alignItems: "center", justifyContent: "center" },
  optTxt: { flex: 1, color: COLORS.n800, fontSize: 15 },
  jump: { width: 40, height: 40, borderRadius: RADII.md, borderWidth: 1.5, borderColor: COLORS.n300, alignItems: "center", justifyContent: "center", backgroundColor: "#fff" },
});
