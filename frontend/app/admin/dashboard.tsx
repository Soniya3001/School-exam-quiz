import React, { useEffect, useState, useCallback } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Button, Input, Card, HeaderBar, Banner, Pill, SectionTitle } from "../../src/ui";
import { COLORS, SPACING, RADII } from "../../src/theme";
import { Api } from "../../src/api";

type Tab = "teachers" | "pending" | "students" | "data";

export default function AdminDashboard() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("teachers");
  const [teachers, setTeachers] = useState<any[]>([]);
  const [pending, setPending] = useState<any[]>([]);
  const [students, setStudents] = useState<any[]>([]);
  const [editing, setEditing] = useState<any | null>(null);
  const [newT, setNewT] = useState({ name: "", subject: "", password: "", school_id: "" });
  const [adminPwd, setAdminPwd] = useState("");
  const [status, setStatus] = useState("");
  const [err, setErr] = useState("");

  const flash = (m: string) => { setStatus(m); setTimeout(() => setStatus(""), 2200); };

  const loadTeachers = useCallback(async () => {
    try { setTeachers(await Api.listTeachers()); } catch (e: any) { setErr(e.message); }
  }, []);
  const loadPending = useCallback(async () => {
    try { setPending(await Api.pendingTeachers()); } catch (e: any) { setErr(e.message); }
  }, []);
  const loadStudents = useCallback(async () => {
    try { setStudents(await Api.adminStudents()); } catch (e: any) { setErr(e.message); }
  }, []);

  useEffect(() => { loadTeachers(); loadPending(); loadStudents(); }, []);

  const confirm = (msg: string, onYes: () => void) => {
    if (Platform.OS === "web") { if (window.confirm(msg)) onYes(); return; }
    Alert.alert("Confirm", msg, [{ text: "Cancel", style: "cancel" }, { text: "Yes", onPress: onYes, style: "destructive" }]);
  };

  const approve = async (t: any) => {
    try { await Api.approveTeacher(t.id); flash(`✅ ${t.name} approved`); loadTeachers(); loadPending(); }
    catch (e: any) { setErr(e.message); }
  };
  const reject = async (t: any) => confirm(`Reject ${t.name}?`, async () => {
    await Api.rejectTeacher(t.id); flash(`🗑 ${t.name} rejected`); loadPending();
  });
  const addTeacher = async () => {
    setErr("");
    if (!newT.name.trim() || !newT.password.trim()) return setErr("Name and password required.");
    try {
      await Api.createTeacher({ name: newT.name, subject: newT.subject || "General", password: newT.password, school_id: newT.school_id });
      setNewT({ name: "", subject: "", password: "", school_id: "" });
      flash("✅ Teacher added"); loadTeachers();
    } catch (e: any) { setErr(e.message); }
  };
  const saveEdit = async () => {
    if (!editing.name.trim() || !editing.password.trim()) return setErr("Name and password required.");
    try {
      await Api.updateTeacher(editing.id, { name: editing.name, subject: editing.subject, password: editing.password });
      setEditing(null); flash("✅ Teacher updated"); loadTeachers();
    } catch (e: any) { setErr(e.message); }
  };
  const toggle = async (id: string) => { await Api.toggleTeacher(id); flash("Updated"); loadTeachers(); };
  const remove = async (t: any) => confirm(`Remove ${t.name} and all their data?`, async () => {
    await Api.deleteTeacher(t.id); flash("🗑 Teacher removed"); loadTeachers();
  });
  const clearTeacherData = async (t: any) => confirm(`Clear all test data for ${t.name}?`, async () => {
    await Api.clearTeacherData(t.id); flash(`🗑 ${t.name} data cleared`); loadTeachers();
  });
  const updatePwd = async () => {
    setErr("");
    if (adminPwd.length < 6) return setErr("Min 6 characters.");
    try { await Api.adminPassword(adminPwd); setAdminPwd(""); flash("✅ Password updated"); }
    catch (e: any) { setErr(e.message); }
  };
  const clearAll = () => confirm("DELETE ALL data?", async () => {
    await Api.clearAll(); flash("🗑 All data cleared"); loadTeachers(); loadStudents();
  });
  const removeStudent = (s: any) => confirm(`Delete history for ${s.student_name}?`, async () => {
    await Api.deleteStudent(s.key); flash("🗑 Deleted"); loadStudents();
  });

  const TABS: { key: Tab; label: string; badge?: number }[] = [
    { key: "teachers", label: "👩‍🏫 Teachers" },
    { key: "pending", label: "⏳ Pending", badge: pending.length },
    { key: "students", label: "🎓 Students" },
    { key: "data", label: "🗄️ Data" },
  ];

  return (
    <SafeAreaView style={s.safe}>
      <HeaderBar
        title="🛡️ Admin Panel"
        subtitle="Full platform management"
        onBack={() => router.replace("/")}
        right={<Button title="🏠" onPress={() => router.replace("/")} variant="ghost" testID="admin-home-btn" />}
        testID="admin-dashboard-header"
      />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
        <ScrollView contentContainerStyle={s.scroll}>
          {status ? <Banner kind="success" testID="admin-status">{status}</Banner> : null}
          {err ? <Banner kind="error" testID="admin-error">{err}</Banner> : null}

          {/* Tab bar */}
          <View style={s.tabs}>
            {TABS.map((t) => (
              <TouchableOpacity key={t.key} testID={`admin-tab-${t.key}`}
                onPress={() => { setTab(t.key); setEditing(null); setErr(""); }}
                style={[s.tab, tab === t.key && s.tabActive]}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                  <Text style={[s.tabTxt, tab === t.key && s.tabTxtActive]}>{t.label}</Text>
                  {t.badge ? (
                    <View style={s.badge}><Text style={s.badgeTxt}>{t.badge}</Text></View>
                  ) : null}
                </View>
              </TouchableOpacity>
            ))}
          </View>

          {/* TEACHERS TAB */}
          {tab === "teachers" && (
            <View style={{ gap: SPACING.md }}>
              <View style={s.statRow}>
                <StatTile label="Total" value={teachers.length} />
                <StatTile label="Active" value={teachers.filter((t) => t.active && t.status === "active").length} color={COLORS.success} />
                <StatTile label="Disabled" value={teachers.filter((t) => !t.active).length} color={COLORS.error} />
              </View>

              {editing ? (
                <Card>
                  <SectionTitle>✏️ Edit Teacher</SectionTitle>
                  <Input testID="edit-teacher-name" placeholder="Name" value={editing.name} onChangeText={(v: string) => setEditing({ ...editing, name: v })} style={{ marginBottom: SPACING.sm }} />
                  <Input testID="edit-teacher-subject" placeholder="Subject" value={editing.subject} onChangeText={(v: string) => setEditing({ ...editing, subject: v })} style={{ marginBottom: SPACING.sm }} />
                  <Input testID="edit-teacher-password" placeholder="Password" value={editing.password} onChangeText={(v: string) => setEditing({ ...editing, password: v })} style={{ marginBottom: SPACING.md }} />
                  <View style={{ flexDirection: "row", gap: SPACING.sm }}>
                    <Button title="Save" onPress={saveEdit} testID="edit-teacher-save-btn" style={{ flex: 1 }} />
                    <Button title="Cancel" variant="ghost" onPress={() => setEditing(null)} testID="edit-teacher-cancel-btn" style={{ flex: 1 }} />
                  </View>
                </Card>
              ) : (
                <>
                  {teachers.filter(t => t.status === "active").map((t) => (
                    <Card key={t.id} testID={`teacher-row-${t.id}`}>
                      <View style={{ flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
                        <Text style={{ fontWeight: "700", fontSize: 16, color: COLORS.n900 }}>{t.name}</Text>
                        <Pill>{t.subject}</Pill>
                        {t.school_id ? <Pill color={COLORS.primary}>🏫 {t.school_id}</Pill> : null}
                        {!t.active && <Pill color={COLORS.error}>DISABLED</Pill>}
                        {t.active_tests_count > 0 && <Pill color={COLORS.success}>🟢 {t.active_tests_count} LIVE</Pill>}
                      </View>
                      <Text style={s.meta}>ID: {t.id} · Pass: <Text style={{ fontWeight: "700" }}>{t.password}</Text></Text>
                      <Text style={s.meta}>Tests run: {t.history_count}</Text>
                      <View style={{ flexDirection: "row", gap: SPACING.sm, marginTop: SPACING.md }}>
                        <Button title="✏️" variant="outline" onPress={() => setEditing({ ...t })} testID={`teacher-edit-${t.id}`} style={{ flex: 1 }} />
                        <Button title={t.active ? "⛔" : "✅"} variant="outline" onPress={() => toggle(t.id)} testID={`teacher-toggle-${t.id}`} style={{ flex: 1 }} />
                        <Button title="🗑" variant="danger" onPress={() => remove(t)} testID={`teacher-remove-${t.id}`} style={{ flex: 1 }} />
                      </View>
                    </Card>
                  ))}
                </>
              )}

              {!editing && (
                <Card>
                  <SectionTitle>➕ Add New Teacher</SectionTitle>
                  <Input testID="new-teacher-name" placeholder="Name" value={newT.name} onChangeText={(v: string) => setNewT({ ...newT, name: v })} style={{ marginBottom: SPACING.sm }} />
                  <Input testID="new-teacher-subject" placeholder="Subject (default: General)" value={newT.subject} onChangeText={(v: string) => setNewT({ ...newT, subject: v })} style={{ marginBottom: SPACING.sm }} />
                  <Input testID="new-teacher-school" placeholder="School ID (e.g. GSBV1003)" value={newT.school_id} onChangeText={(v: string) => setNewT({ ...newT, school_id: v.toUpperCase() })} autoCapitalize="characters" style={{ marginBottom: SPACING.sm }} />
                  <Input testID="new-teacher-password" placeholder="Password" value={newT.password} onChangeText={(v: string) => setNewT({ ...newT, password: v })} style={{ marginBottom: SPACING.md }} />
                  <Button title="➕ Add Teacher" onPress={addTeacher} testID="add-teacher-btn" />
                </Card>
              )}
            </View>
          )}

          {/* PENDING TAB */}
          {tab === "pending" && (
            <View style={{ gap: SPACING.md }}>
              {pending.length === 0 ? (
                <Banner kind="success">No pending registrations! 🎉</Banner>
              ) : (
                <>
                  <Banner kind="warning">{pending.length} teacher(s) waiting for approval</Banner>
                  {pending.map((t) => (
                    <Card key={t.id} testID={`pending-row-${t.id}`} style={{ borderColor: COLORS.warning + "55", borderWidth: 2 }}>
                      <View style={{ flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 6, marginBottom: SPACING.sm }}>
                        <Text style={{ fontWeight: "700", fontSize: 16 }}>{t.name}</Text>
                        <Pill color={COLORS.warning}>⏳ PENDING</Pill>
                        {t.school_id ? <Pill color={COLORS.primary}>🏫 {t.school_id}</Pill> : null}
                      </View>
                      <Text style={s.meta}>Subject: {t.subject}</Text>
                      <Text style={s.meta}>ID: {t.id} · Registered: {new Date(t.created_at).toLocaleDateString()}</Text>
                      <View style={{ flexDirection: "row", gap: SPACING.sm, marginTop: SPACING.md }}>
                        <Button title="✅ Approve" onPress={() => approve(t)} testID={`approve-${t.id}`} style={{ flex: 1 }} />
                        <Button title="❌ Reject" variant="danger" onPress={() => reject(t)} testID={`reject-${t.id}`} style={{ flex: 1 }} />
                      </View>
                    </Card>
                  ))}
                </>
              )}
            </View>
          )}

          {/* STUDENTS TAB */}
          {tab === "students" && (
            <View style={{ gap: SPACING.md }}>
              <View style={s.statRow}>
                <StatTile label="Students" value={students.length} />
                <StatTile label="Attempts" value={students.reduce((sum, x) => sum + x.attempts, 0)} color={COLORS.accent} />
              </View>
              {students.length === 0 && <Banner>No student data yet.</Banner>}
              {students.map((st) => (
                <Card key={st.key} testID={`student-row-${st.key}`}>
                  <View style={{ flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
                    <Text style={{ fontWeight: "700", fontSize: 16 }}>{st.student_name}</Text>
                    {st.student_class ? <Pill>{st.student_class}</Pill> : null}
                    {st.school_id ? <Pill color={COLORS.primary}>🏫 {st.school_id}</Pill> : null}
                    {st.subjects.map((sub: string) => <Pill key={sub} color={COLORS.accent}>{sub}</Pill>)}
                  </View>
                  <Text style={s.meta}>{st.attempts} attempt(s) · Avg: {st.avg_pct}%</Text>
                  <Button title="🗑 Delete History" variant="danger" onPress={() => removeStudent(st)} testID={`student-delete-${st.key}`} style={{ marginTop: SPACING.sm }} />
                </Card>
              ))}
            </View>
          )}

          {/* DATA TAB */}
          {tab === "data" && (
            <View style={{ gap: SPACING.md }}>
              <SectionTitle>🗄️ Database Overview</SectionTitle>
              {teachers.map((t) => (
                <Card key={t.id}>
                  <View style={{ flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
                    <Text style={{ fontWeight: "700" }}>{t.name}</Text>
                    {t.school_id ? <Pill color={COLORS.primary}>🏫 {t.school_id}</Pill> : null}
                    {t.active_tests_count > 0 ? <Pill color={COLORS.success}>🟢 {t.active_tests_count} LIVE</Pill> : <Pill color={COLORS.n500}>Idle</Pill>}
                  </View>
                  <Text style={s.meta}>Tests: {t.history_count}</Text>
                  <Button title="🗑 Clear test data" variant="outline" onPress={() => clearTeacherData(t)} testID={`clear-teacher-${t.id}`} style={{ marginTop: SPACING.sm }} />
                </Card>
              ))}
              <Card>
                <SectionTitle>🔑 Change Admin Password</SectionTitle>
                <Input testID="admin-new-password" placeholder="New password (min 6)" secureTextEntry value={adminPwd} onChangeText={setAdminPwd} style={{ marginBottom: SPACING.md }} />
                <Button title="Update Password" onPress={updatePwd} testID="update-admin-password-btn" />
              </Card>
              <Card style={{ borderColor: COLORS.error + "55" }}>
                <SectionTitle style={{ color: COLORS.error }}>⚠️ Danger Zone</SectionTitle>
                <Text style={{ color: COLORS.n700, marginBottom: SPACING.md }}>Delete ALL platform data.</Text>
                <Button title="🗑 Clear ALL Platform Data" variant="danger" onPress={clearAll} testID="clear-all-btn" />
              </Card>
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function StatTile({ label, value, color = COLORS.primary }: { label: string; value: number; color?: string }) {
  return (
    <View style={[s.stat, { borderColor: color + "55", backgroundColor: color + "0d" }]}>
      <Text style={[s.statValue, { color }]}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },
  scroll: { padding: SPACING.lg, paddingBottom: SPACING.xxl, gap: SPACING.md },
  tabs: { flexDirection: "row", backgroundColor: COLORS.muted, borderRadius: RADII.md, padding: 4, marginBottom: SPACING.sm },
  tab: { flex: 1, paddingVertical: 10, alignItems: "center", borderRadius: RADII.sm },
  tabActive: { backgroundColor: COLORS.paper, shadowColor: "#000", shadowOpacity: 0.05, shadowRadius: 4, elevation: 1 },
  tabTxt: { color: COLORS.n600, fontWeight: "600", fontSize: 11 },
  tabTxtActive: { color: COLORS.primary },
  badge: { backgroundColor: COLORS.error, borderRadius: 10, paddingHorizontal: 5, paddingVertical: 1 },
  badgeTxt: { color: "#fff", fontSize: 10, fontWeight: "700" },
  statRow: { flexDirection: "row", gap: SPACING.sm },
  stat: { flex: 1, padding: SPACING.md, borderRadius: RADII.md, borderWidth: 1, alignItems: "center" },
  statValue: { fontSize: 24, fontWeight: "800" },
  statLabel: { fontSize: 11, color: COLORS.n600, textTransform: "uppercase", letterSpacing: 1, marginTop: 2 },
  meta: { color: COLORS.n600, fontSize: 13, marginTop: 4 },
});
