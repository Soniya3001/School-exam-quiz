import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Share, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter, useLocalSearchParams } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Button, Card, HeaderBar, SectionTitle } from "../../src/ui";
import { COLORS, SPACING, RADII } from "../../src/theme";
import { Api } from "../../src/api";

export default function QuestionPaper() {
  const router = useRouter();
  const params = useLocalSearchParams();
  const testClass = (params.test_class as string || "").replace(/_/g, " ");
  const [teacher, setTeacher] = useState<any>(null);
  const [test, setTest] = useState<any>(null);

  useEffect(() => {
    (async () => {
      const stored = await AsyncStorage.getItem("teacher");
      if (!stored) { router.replace("/teacher/login"); return; }
      const t = JSON.parse(stored);
      setTeacher(t);
      const res = await Api.teacherState(t.id);
      const allTests = res.tests || [];
      const found = allTests.find((x: any) => x.test_class === testClass) || allTests[0];
      setTest(found);
    })();
  }, []);

  const sharePaper = async () => {
    if (!test) return;
    const lines: string[] = [];
    lines.push(`===========================`);
    lines.push(`GOVERNMENT SCHOOL EXAM PLATFORM`);
    lines.push(`===========================`);
    lines.push(`Class: ${test.test_class}`);
    lines.push(`Subject: ${test.subject}`);
    lines.push(`Teacher: ${teacher?.name}`);
    lines.push(`Total Marks: ${test.total_marks || test.questions?.length}`);
    lines.push(`Join Code: ${test.join_code}`);
    lines.push(`Date: ${new Date().toLocaleDateString()}`);
    lines.push(`===========================\n`);

    if (test.test_type === "subjective") {
      const sections = ["A", "B", "C"];
      const labels: Record<string, string> = {
        A: "SECTION A (1 Mark Each)",
        B: "SECTION B (2 Marks Each)",
        C: "SECTION C (4 Marks Each)",
      };
      sections.forEach((sec) => {
        const qs = test.questions.filter((q: any) => q.section === sec);
        if (qs.length === 0) return;
        lines.push(`\n${labels[sec]}`);
        lines.push(`${"─".repeat(40)}`);
        qs.forEach((q: any, i: number) => {
          const globalIdx = test.questions.indexOf(q) + 1;
          lines.push(`Q${globalIdx}. ${q.q}`);
          lines.push(`   [${q.marks} mark${q.marks > 1 ? "s" : ""}]\n`);
        });
      });
    } else {
      test.questions.forEach((q: any, i: number) => {
        lines.push(`Q${i + 1}. ${q.q}`);
        q.options.forEach((opt: string, j: number) => {
          lines.push(`   ${String.fromCharCode(65 + j)}. ${opt}`);
        });
        lines.push("");
      });
    }

    lines.push(`\n===========================`);
    lines.push(`Developed by Ankur Malik`);
    lines.push(`===========================`);

    try {
      await Share.share({ message: lines.join("\n"), title: `${test.test_class} ${test.subject} Question Paper` });
    } catch (e) {}
  };

  if (!test || !teacher) return (
    <SafeAreaView style={s.safe}>
      <View style={s.center}><Text style={{ color: COLORS.n600 }}>Loading…</Text></View>
    </SafeAreaView>
  );

  const isSubjective = test.test_type === "subjective";

  return (
    <SafeAreaView style={s.safe}>
      <HeaderBar
        title="📄 Question Paper"
        subtitle={`${test.test_class} — ${test.subject}`}
        onBack={() => router.back()}
        right={
          <Button title="📤 Share" variant="outline" onPress={sharePaper} testID="share-paper-btn" />
        }
        testID="paper-header"
      />
      <ScrollView contentContainerStyle={s.scroll}>
        {/* Paper Header */}
        <Card style={s.paperHeader}>
          <Text style={s.schoolName}>GOVERNMENT SCHOOL EXAM PLATFORM</Text>
          <View style={s.divider} />
          <View style={s.metaRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.metaLabel}>Class</Text>
              <Text style={s.metaValue}>{test.test_class}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.metaLabel}>Subject</Text>
              <Text style={s.metaValue}>{test.subject}</Text>
            </View>
          </View>
          <View style={s.metaRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.metaLabel}>Total Marks</Text>
              <Text style={s.metaValue}>{test.total_marks || test.questions?.length}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.metaLabel}>Join Code</Text>
              <Text style={[s.metaValue, { color: COLORS.primary, letterSpacing: 3 }]}>{test.join_code}</Text>
            </View>
          </View>
          <View style={s.metaRow}>
            <View style={{ flex: 1 }}>
              <Text style={s.metaLabel}>Teacher</Text>
              <Text style={s.metaValue}>{teacher.name}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.metaLabel}>Date</Text>
              <Text style={s.metaValue}>{new Date().toLocaleDateString()}</Text>
            </View>
          </View>
          {isSubjective && (
            <View style={s.instructionsBox}>
              <Text style={s.instructionsTitle}>General Instructions:</Text>
              <Text style={s.instructionItem}>• Answer all questions.</Text>
              <Text style={s.instructionItem}>• Section A: Very short answers (1-2 sentences)</Text>
              <Text style={s.instructionItem}>• Section B: Short answers (3-4 sentences)</Text>
              <Text style={s.instructionItem}>• Section C: Long answers (detailed paragraph)</Text>
            </View>
          )}
        </Card>

        {/* Questions */}
        {isSubjective ? (
          ["A", "B", "C"].map((sec) => {
            const secQs = test.questions.map((q: any, i: number) => ({ ...q, _idx: i })).filter((q: any) => q.section === sec);
            if (secQs.length === 0) return null;
            const marks = secQs[0].marks;
            return (
              <View key={sec}>
                <View style={s.sectionBanner}>
                  <Text style={s.sectionBannerTxt}>
                    SECTION {sec} — {marks} Mark{marks > 1 ? "s" : ""} Each ({secQs.length} Questions × {marks} = {secQs.length * marks} Marks)
                  </Text>
                </View>
                {secQs.map((q: any) => (
                  <Card key={q._idx} style={s.qCard}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <Text style={s.qNum}>Q{q._idx + 1}.</Text>
                      <Text style={[s.qBody, { flex: 1 }]}>{q.q}</Text>
                      <View style={[s.marksBadge, {
                        backgroundColor: marks === 1 ? COLORS.success + "20" : marks === 2 ? COLORS.warning + "20" : COLORS.error + "20"
                      }]}>
                        <Text style={[s.marksText, {
                          color: marks === 1 ? COLORS.success : marks === 2 ? COLORS.warning : COLORS.error
                        }]}>[{marks}]</Text>
                      </View>
                    </View>
                    {/* Answer space lines */}
                    {Array.from({ length: marks === 1 ? 2 : marks === 2 ? 4 : 8 }).map((_, i) => (
                      <View key={i} style={s.answerLine} />
                    ))}
                  </Card>
                ))}
              </View>
            );
          })
        ) : (
          <View>
            <View style={s.sectionBanner}>
              <Text style={s.sectionBannerTxt}>MCQ — Choose the correct answer ({test.questions.length} Questions)</Text>
            </View>
            {test.questions.map((q: any, i: number) => (
              <Card key={i} style={s.qCard}>
                <View style={{ flexDirection: "row" }}>
                  <Text style={s.qNum}>Q{i + 1}.</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={s.qBody}>{q.q}</Text>
                    <View style={s.optionsGrid}>
                      {q.options.map((opt: string, j: number) => (
                        <View key={j} style={s.optionRow}>
                          <Text style={s.optLetter}>{String.fromCharCode(65 + j)}.</Text>
                          <Text style={s.optText}>{opt}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                </View>
              </Card>
            ))}
          </View>
        )}

        {/* Answer Key (for teacher only) */}
        <Card style={[s.answerKeyCard]}>
          <Text style={s.answerKeyTitle}>🔑 ANSWER KEY (Teacher Copy)</Text>
          <View style={s.divider} />
          {isSubjective ? (
            test.questions.map((q: any, i: number) => (
              <View key={i} style={{ marginBottom: SPACING.md }}>
                <Text style={{ fontWeight: "700", color: COLORS.n800 }}>Q{i + 1}. [{q.marks} marks]</Text>
                <Text style={{ color: COLORS.n700, marginTop: 4, lineHeight: 20 }}>{q.expected_answer}</Text>
                {q.keywords?.length > 0 && (
                  <Text style={{ color: COLORS.primary, fontSize: 12, marginTop: 4 }}>
                    Key concepts: {q.keywords.join(", ")}
                  </Text>
                )}
              </View>
            ))
          ) : (
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              {test.questions.map((q: any, i: number) => (
                <View key={i} style={s.ansKeyChip}>
                  <Text style={{ fontSize: 12, fontWeight: "700", color: COLORS.n700 }}>Q{i + 1}: </Text>
                  <Text style={{ fontSize: 12, fontWeight: "800", color: COLORS.success }}>
                    {String.fromCharCode(65 + q.answer)}
                  </Text>
                </View>
              ))}
            </View>
          )}
        </Card>

        <Text style={s.footer}>Developed by Ankur Malik · Govt School Exam Platform</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  scroll: { padding: SPACING.lg, paddingBottom: SPACING.xxl, gap: SPACING.md },
  paperHeader: { backgroundColor: "#fff", borderWidth: 2, borderColor: COLORS.primary + "44" },
  schoolName: { fontSize: 15, fontWeight: "900", color: COLORS.primary, textAlign: "center", letterSpacing: 1 },
  divider: { height: 1, backgroundColor: COLORS.n200, marginVertical: SPACING.md },
  metaRow: { flexDirection: "row", gap: SPACING.md, marginBottom: SPACING.sm },
  metaLabel: { fontSize: 11, color: COLORS.n500, textTransform: "uppercase", letterSpacing: 1 },
  metaValue: { fontSize: 15, fontWeight: "700", color: COLORS.n900, marginTop: 2 },
  instructionsBox: { backgroundColor: COLORS.muted, borderRadius: RADII.sm, padding: SPACING.md, marginTop: SPACING.sm },
  instructionsTitle: { fontWeight: "700", color: COLORS.n800, marginBottom: 6 },
  instructionItem: { color: COLORS.n700, fontSize: 13, lineHeight: 20 },
  sectionBanner: { backgroundColor: COLORS.primary, borderRadius: RADII.md, padding: SPACING.sm, marginBottom: SPACING.sm, marginTop: SPACING.sm },
  sectionBannerTxt: { color: "#fff", fontWeight: "800", fontSize: 13, textAlign: "center" },
  qCard: { marginBottom: SPACING.sm, borderWidth: 1, borderColor: COLORS.n200 },
  qNum: { fontWeight: "800", color: COLORS.n800, marginRight: 6, fontSize: 15, minWidth: 28 },
  qBody: { fontSize: 15, color: COLORS.n900, lineHeight: 22, fontWeight: "600" },
  optionsGrid: { marginTop: SPACING.sm, gap: 6 },
  optionRow: { flexDirection: "row", gap: 6 },
  optLetter: { fontWeight: "700", color: COLORS.n600, minWidth: 20 },
  optText: { color: COLORS.n800, flex: 1 },
  answerLine: { borderBottomWidth: 1, borderColor: COLORS.n300, marginTop: 14, marginBottom: 2 },
  marksBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: RADII.sm, marginLeft: SPACING.sm },
  marksText: { fontSize: 12, fontWeight: "800" },
  answerKeyCard: { backgroundColor: "#fffbeb", borderWidth: 2, borderColor: COLORS.warning + "55" },
  answerKeyTitle: { fontWeight: "900", fontSize: 15, color: COLORS.warning, textAlign: "center" },
  ansKeyChip: { flexDirection: "row", backgroundColor: COLORS.muted, borderRadius: RADII.sm, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: COLORS.n200 },
  footer: { textAlign: "center", color: COLORS.n400, fontSize: 11, marginTop: SPACING.md, fontStyle: "italic" },
});
