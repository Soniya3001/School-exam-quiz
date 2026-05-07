from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json as json_module
import re
import random
import string
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime, timezone

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Govt School Exam Platform API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ────────────────────────── HELPERS ──────────────────────────
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def short_id(prefix="T"):
    return prefix + str(int(datetime.now(timezone.utc).timestamp() * 1000))[-6:]

def gen_join_code(school_id: str) -> str:
    """Generate 6-char join code: first 3 of school_id + 3 random alphanumeric"""
    prefix = re.sub(r'[^A-Z0-9]', '', school_id.upper())[:3].ljust(3, 'X')
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return prefix + suffix


# ────────────────────────── MODELS ──────────────────────────
class AdminLoginIn(BaseModel):
    password: str

class AdminPasswordIn(BaseModel):
    new_password: str

class TeacherCreateIn(BaseModel):
    name: str
    subject: str = "General"
    password: str
    school_id: str = ""

class TeacherUpdateIn(BaseModel):
    name: str
    subject: str
    password: str

class TeacherRegisterIn(BaseModel):
    name: str
    subject: str = "General"
    password: str
    school_id: str

class TeacherLoginIn(BaseModel):
    teacher_id: str
    password: str
    school_id: str = ""

class GenerateIn(BaseModel):
    teacher_id: str
    lesson_text: Optional[str] = None
    image_base64: Optional[str] = None
    count: int = 10
    test_class: str
    subject: str
    language: str = "English"
    difficulty: int = 2
    test_type: str = "mcq"  # "mcq" | "subjective"

class ActivateIn(BaseModel):
    teacher_id: str
    join_code: str

class StudentSubmitIn(BaseModel):
    student_name: str
    student_class: str
    student_subject: str
    join_code: str
    answers: Dict[str, Any]  # MCQ: {0: 2}, Subjective: {0: "answer text"}
    auto_submit: bool = False

class FindTestIn(BaseModel):
    join_code: str
    student_name: str
    student_class: str
    school_id: str = ""

class SubjectiveGradeIn(BaseModel):
    teacher_id: str
    join_code: str
    student_name: str
    marks: Dict[str, float]  # {question_index: marks_awarded}


# ────────────────────────── DB HELPERS ──────────────────────────
async def ensure_seed():
    admin = await db.admin.find_one({"_id": "admin"})
    if not admin:
        await db.admin.insert_one({"_id": "admin", "username": "admin", "password": "Admin@8006"})
        logger.info("Seeded default admin")

async def get_teacher(tid: str):
    return await db.teachers.find_one({"id": tid}, {"_id": 0})

async def get_active_test(tid: str, test_class: str = None):
    """Get active test for teacher. If test_class given, get class-specific test."""
    query = {"teacher_id": tid}
    if test_class:
        query["test_class"] = test_class
    at = await db.active_tests.find_one(query, {"_id": 0})
    if not at and not test_class:
        at = {
            "teacher_id": tid, "questions": [], "test_active": False,
            "answers_revealed": False, "join_code": "", "results": {},
            "test_class": "", "subject": "", "test_type": "mcq",
        }
        await db.active_tests.insert_one(at)
        at.pop("_id", None)
    return at

async def get_all_active_tests(tid: str):
    """Get all active tests for a teacher (one per class)."""
    docs = await db.active_tests.find({"teacher_id": tid}, {"_id": 0}).to_list(100)
    return docs

async def upsert_active_test(tid: str, test_class: str, data: dict):
    """Upsert active test for specific teacher+class combination."""
    data["teacher_id"] = tid
    data["test_class"] = test_class
    await db.active_tests.update_one(
        {"teacher_id": tid, "test_class": test_class},
        {"$set": data},
        upsert=True
    )


# ────────────────────────── LLM ──────────────────────────
async def call_groq(prompt: str, system_msg: str) -> str:
    from groq import Groq
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise Exception("GROQ_API_KEY not configured")
    groq_client = Groq(api_key=api_key)
    completion = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        max_tokens=8000,
        temperature=0.3,
    )
    return completion.choices[0].message.content


async def generate_mcq(lesson_text, image_b64, count, test_class, subject, language, difficulty, api_key, system_msg) -> str:
    diff_map = {
        1: {"tag": "EASY", "desc": "Direct facts and definitions from NCERT textbooks."},
        2: {"tag": "MEDIUM", "desc": "Conceptual clarity and application of rules/formulas."},
        3: {"tag": "HARD", "desc": "Higher Order Thinking Skills; multi-step logic and analysis."},
    }
    diff_info = diff_map.get(int(difficulty), diff_map[2])
    prompt = (
        f"Generate exactly {count} academic MCQs for Class {test_class} {subject} based on the attached content.\n"
        f"Difficulty: {diff_info['tag']} ({diff_info['desc']}).\n"
        f"Language: {language}.\n\n"
        "STRICT RULES:\n"
        "1. NO meta questions (e.g., 'What is the title?').\n"
        "2. Focus on key terms, definitions, laws, and facts.\n"
        "3. Ensure all 4 options are plausible; only 1 must be correct.\n"
        "4. Return ONLY a JSON object:\n"
        '{"questions":[{"q":"question text","options":["A","B","C","D"],"answer":0}]}'
    )
    if lesson_text:
        prompt += f"\n\nLesson Text:\n{lesson_text}"
    elif image_b64:
        prompt += "\n\nLesson is in the attached image."
    return prompt, system_msg


async def generate_subjective(lesson_text, image_b64, test_class, subject, language, api_key, system_msg) -> str:
    """
    Subjective test: 20 marks total
    - 4 questions × 1 mark = 4 marks
    - 4 questions × 2 marks = 8 marks
    - 2 questions × 4 marks = 8 marks
    Total = 20 marks
    """
    prompt = (
        f"Generate a subjective test for Class {test_class} {subject} based on CBSE/NCERT syllabus.\n"
        f"Language: {language}.\n\n"
        "EXACT FORMAT REQUIRED - 10 questions total (20 marks):\n"
        "- Section A: 4 questions worth 1 mark each (very short answer)\n"
        "- Section B: 4 questions worth 2 marks each (short answer)\n"
        "- Section C: 2 questions worth 4 marks each (long answer)\n\n"
        "Return ONLY this JSON format, no other text:\n"
        '{"questions":['
        '{"q":"question","marks":1,"section":"A","expected_answer":"brief expected answer","keywords":["key1","key2"]},'
        '{"q":"question","marks":2,"section":"B","expected_answer":"expected answer","keywords":["key1","key2"]},'
        '{"q":"question","marks":4,"section":"C","expected_answer":"detailed expected answer","keywords":["key1","key2","key3"]}'
        ']}\n\n'
        "RULES:\n"
        "1. Section A questions: very short (1-2 sentences answer expected)\n"
        "2. Section B questions: short (3-4 sentences answer expected)\n"
        "3. Section C questions: long (paragraph answer expected)\n"
        "4. Follow NCERT/CBSE curriculum strictly\n"
        "5. Include expected_answer and keywords for AI auto-grading\n"
    )
    if lesson_text:
        prompt += f"\n\nLesson Text:\n{lesson_text}"
    elif image_b64:
        prompt += "\n\nLesson is in the attached image."
    return prompt, system_msg


async def grade_subjective_answer(question: str, expected: str, keywords: list, student_answer: str, max_marks: float) -> dict:
    """Use AI to grade a subjective answer."""
    api_key = os.environ.get('GEMINI_API_KEY', '')
    system_msg = "You are a strict but fair CBSE examiner. Grade student answers objectively."
    prompt = (
        f"Grade this student answer for a {max_marks}-mark question.\n\n"
        f"Question: {question}\n"
        f"Expected Answer: {expected}\n"
        f"Key concepts to check: {', '.join(keywords)}\n"
        f"Student Answer: {student_answer}\n\n"
        f"Award marks out of {max_marks}. Be fair but strict.\n"
        "Return ONLY JSON: {\"marks\": <number>, \"feedback\": \"brief feedback\"}"
    )
    text = None
    if api_key:
        try:
            chat = LlmChat(api_key=api_key, session_id=f"grade-{uuid.uuid4()}", system_message=system_msg)\
                .with_model("gemini", "gemini-2.5-flash").with_params(max_tokens=500)
            resp = await chat.send_message(UserMessage(text=prompt))
            text = resp if isinstance(resp, str) else str(resp)
        except Exception as e:
            logger.warning(f"Gemini grading failed: {e}")
    if text is None:
        try:
            text = await call_groq(prompt, system_msg)
        except Exception as e:
            return {"marks": 0, "feedback": "Auto-grading failed"}
    
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end+1]
    try:
        result = json_module.loads(text)
        marks = min(float(result.get("marks", 0)), max_marks)
        return {"marks": marks, "feedback": result.get("feedback", "")}
    except:
        return {"marks": 0, "feedback": "Could not parse grading response"}


async def generate_questions_llm(
    lesson_text, image_b64, count, test_class, subject,
    language="English", difficulty=2, test_type="mcq"
) -> List[dict]:
    api_key = os.environ.get('GEMINI_API_KEY', '')
    system_msg = (
        f"You are a Senior CBSE Paper Setter for {subject}, Class {test_class}. "
        "Create high-quality academic questions strictly following the NCERT curriculum. "
        "Always return ONLY valid JSON with no markdown, no commentary, no code fences."
    )

    if test_type == "subjective":
        prompt, system_msg = await generate_subjective(lesson_text, image_b64, test_class, subject, language, api_key, system_msg)
    else:
        prompt, system_msg = await generate_mcq(lesson_text, image_b64, count, test_class, subject, language, difficulty, api_key, system_msg)

    text = None

    # Try Gemini first
    if api_key:
        try:
            chat = LlmChat(api_key=api_key, session_id=f"gen-{uuid.uuid4()}", system_message=system_msg)\
                .with_model("gemini", "gemini-2.5-flash").with_params(max_tokens=8000)
            if image_b64:
                cleaned_img = re.sub(r"^data:image/[^;]+;base64,", "", image_b64).strip()
                msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=cleaned_img)])
            else:
                msg = UserMessage(text=prompt)
            resp = await chat.send_message(msg)
            text = resp if isinstance(resp, str) else str(resp)
            logger.info("Questions generated via Gemini")
        except Exception as e:
            logger.warning(f"Gemini failed: {e}. Trying Groq...")
            text = None

    # Groq fallback
    if text is None:
        try:
            groq_prompt = prompt
            if image_b64:
                groq_prompt = prompt.replace(
                    "\n\nLesson is in the attached image.",
                    f"\n\nNote: Image could not be processed. Generate questions based on standard {subject} Class {test_class} NCERT curriculum."
                )
            text = await call_groq(groq_prompt, system_msg)
            logger.info("Questions generated via Groq fallback")
        except Exception as e:
            logger.exception("Both Gemini and Groq failed")
            raise HTTPException(502, f"Both AI providers failed: {e}")

    # Parse response
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end+1]

    try:
        data = json_module.loads(text)
    except Exception:
        raise HTTPException(502, "Could not parse AI response. Try again.")

    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise HTTPException(502, "AI returned no questions. Try again.")

    cleaned = []
    if test_type == "subjective":
        for q in questions:
            if not isinstance(q, dict):
                continue
            qtext = q.get("q") or q.get("question")
            marks = q.get("marks", 1)
            section = q.get("section", "A")
            expected = q.get("expected_answer", "")
            keywords = q.get("keywords", [])
            if not qtext:
                continue
            cleaned.append({
                "q": str(qtext), "marks": float(marks), "section": str(section),
                "expected_answer": str(expected), "keywords": keywords,
                "type": "subjective"
            })
    else:
        for q in questions:
            if not isinstance(q, dict):
                continue
            qtext = q.get("q") or q.get("question")
            options = q.get("options") or []
            ans = q.get("answer")
            if not qtext or not isinstance(options, list) or len(options) < 2:
                continue
            try:
                ans = int(ans)
            except Exception:
                ans = 0
            if ans < 0 or ans >= len(options):
                ans = 0
            cleaned.append({"q": str(qtext), "options": [str(o) for o in options][:4], "answer": ans, "type": "mcq"})

    if not cleaned:
        raise HTTPException(502, "AI response had no valid questions.")
    return cleaned


# ────────────────────────── ROUTES ──────────────────────────
@api_router.get("/")
async def root():
    return {"message": "Govt School Exam Platform API", "ok": True}


# ── ADMIN ──
@api_router.post("/admin/login")
async def admin_login(body: AdminLoginIn):
    admin = await db.admin.find_one({"_id": "admin"}, {"_id": 0})
    if not admin or admin.get("password") != body.password:
        raise HTTPException(401, "Wrong password")
    return {"ok": True}

@api_router.post("/admin/password")
async def admin_password(body: AdminPasswordIn):
    if len(body.new_password) < 6:
        raise HTTPException(400, "Min 6 characters")
    await db.admin.update_one({"_id": "admin"}, {"$set": {"password": body.new_password}})
    return {"ok": True}

@api_router.get("/admin/teachers")
async def list_teachers():
    docs = await db.teachers.find({}, {"_id": 0}).to_list(1000)
    out = []
    for t in docs:
        active_tests = await db.active_tests.find({"teacher_id": t["id"]}, {"_id": 0}).to_list(100)
        history_count = await db.test_history.count_documents({"teacher_id": t["id"]})
        out.append({
            **t,
            "active_tests_count": len([x for x in active_tests if x.get("test_active")]),
            "history_count": history_count,
        })
    return out

@api_router.get("/admin/pending-teachers")
async def pending_teachers():
    docs = await db.teachers.find({"status": "pending"}, {"_id": 0}).to_list(1000)
    return docs

@api_router.post("/admin/teachers/{tid}/approve")
async def approve_teacher(tid: str):
    res = await db.teachers.update_one({"id": tid}, {"$set": {"status": "active", "active": True}})
    if res.matched_count == 0:
        raise HTTPException(404, "Teacher not found")
    return {"ok": True}

@api_router.post("/admin/teachers/{tid}/reject")
async def reject_teacher(tid: str):
    await db.teachers.delete_one({"id": tid})
    return {"ok": True}

@api_router.post("/admin/teachers")
async def create_teacher(body: TeacherCreateIn):
    if not body.name.strip() or not body.password.strip():
        raise HTTPException(400, "Name and password required")
    tid = short_id("T")
    teacher = {
        "id": tid, "name": body.name.strip(),
        "subject": (body.subject or "General").strip(),
        "password": body.password.strip(),
        "school_id": (body.school_id or "").strip().upper(),
        "active": True, "status": "active",
        "created_at": now_iso(),
    }
    await db.teachers.insert_one(teacher)
    teacher.pop("_id", None)
    return teacher

@api_router.put("/admin/teachers/{tid}")
async def update_teacher(tid: str, body: TeacherUpdateIn):
    res = await db.teachers.update_one(
        {"id": tid},
        {"$set": {"name": body.name.strip(), "subject": body.subject.strip(), "password": body.password.strip()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Teacher not found")
    return {"ok": True}

@api_router.post("/admin/teachers/{tid}/toggle")
async def toggle_teacher(tid: str):
    t = await get_teacher(tid)
    if not t:
        raise HTTPException(404, "Teacher not found")
    new_state = not t.get("active", True)
    await db.teachers.update_one({"id": tid}, {"$set": {"active": new_state}})
    return {"ok": True, "active": new_state}

@api_router.delete("/admin/teachers/{tid}")
async def delete_teacher(tid: str):
    await db.teachers.delete_one({"id": tid})
    await db.active_tests.delete_many({"teacher_id": tid})
    await db.test_history.delete_many({"teacher_id": tid})
    return {"ok": True}

@api_router.delete("/admin/teachers/{tid}/data")
async def clear_teacher_data(tid: str):
    await db.active_tests.delete_many({"teacher_id": tid})
    await db.test_history.delete_many({"teacher_id": tid})
    return {"ok": True}

@api_router.get("/admin/students")
async def admin_students():
    attempts = await db.student_attempts.find({}, {"_id": 0}).to_list(10000)
    grouped: Dict[str, List[dict]] = {}
    for a in attempts:
        key = f"{a.get('student_name', '')}||{a.get('student_class', '')}"
        grouped.setdefault(key, []).append(a)
    return [
        {
            "key": k, "student_name": v[0]["student_name"],
            "student_class": v[0]["student_class"],
            "school_id": v[0].get("school_id", ""),
            "subjects": list({x.get("subject") for x in v if x.get("subject")}),
            "attempts": len(v),
            "avg_pct": round(sum((x["score"] / x["total"]) * 100 for x in v if x.get("total")) / len(v)) if v else 0,
        }
        for k, v in grouped.items()
    ]

@api_router.delete("/admin/students/{key}")
async def delete_student(key: str):
    name, cls = (key.split("||") + [""])[:2]
    await db.student_attempts.delete_many({"student_name": name, "student_class": cls})
    return {"ok": True}

@api_router.post("/admin/clear-all")
async def clear_all():
    await db.teachers.delete_many({})
    await db.active_tests.delete_many({})
    await db.test_history.delete_many({})
    await db.student_attempts.delete_many({})
    return {"ok": True}


# ── TEACHER REGISTRATION ──
@api_router.post("/teacher/register")
async def teacher_register(body: TeacherRegisterIn):
    if not body.name.strip() or not body.password.strip():
        raise HTTPException(400, "Name and password required")
    if not body.school_id.strip():
        raise HTTPException(400, "School ID required")
    tid = short_id("T")
    teacher = {
        "id": tid, "name": body.name.strip(),
        "subject": (body.subject or "General").strip(),
        "password": body.password.strip(),
        "school_id": body.school_id.strip().upper(),
        "active": False, "status": "pending",
        "created_at": now_iso(),
    }
    await db.teachers.insert_one(teacher)
    teacher.pop("_id", None)
    return {"ok": True, "id": tid, "message": "Registration submitted. Wait for admin approval."}


# ── TEACHER ──
@api_router.post("/teacher/login")
async def teacher_login(body: TeacherLoginIn):
    t = await get_teacher(body.teacher_id)
    if not t or t.get("password") != body.password:
        raise HTTPException(401, "Wrong ID or password")
    if t.get("status") == "pending":
        raise HTTPException(403, "Account pending admin approval")
    if not t.get("active", True):
        raise HTTPException(403, "Account disabled by admin")
    # School ID check if provided
    if body.school_id and t.get("school_id") and t["school_id"] != body.school_id.strip().upper():
        raise HTTPException(403, "Wrong School ID")
    return {"id": t["id"], "name": t["name"], "subject": t["subject"], "school_id": t.get("school_id", "")}

@api_router.get("/teacher/public-list")
async def teacher_public_list():
    docs = await db.teachers.find({"status": "active", "active": True}, {"_id": 0, "password": 0}).to_list(1000)
    return docs

@api_router.get("/teacher/{tid}/state")
async def teacher_state(tid: str):
    """Get all active tests for teacher."""
    tests = await get_all_active_tests(tid)
    # Return most recently updated test as primary + all tests
    return {"tests": tests, "primary": tests[0] if tests else {}}

@api_router.post("/teacher/generate")
async def teacher_generate(body: GenerateIn):
    t = await get_teacher(body.teacher_id)
    if not t:
        raise HTTPException(404, "Teacher not found")
    if not body.lesson_text and not body.image_base64:
        raise HTTPException(400, "Provide lesson_text or image_base64")
    if not body.test_class:
        raise HTTPException(400, "Class is required")
    if not body.subject:
        raise HTTPException(400, "Subject is required")

    count = max(3, min(20, int(body.count or 10)))
    test_type = body.test_type or "mcq"

    questions = await generate_questions_llm(
        body.lesson_text, body.image_base64, count,
        test_class=body.test_class, subject=body.subject,
        language=body.language, difficulty=body.difficulty,
        test_type=test_type,
    )

    # Auto-generate join code
    school_id = t.get("school_id", "GEN")
    join_code = gen_join_code(school_id)
    # Ensure unique
    while await db.active_tests.find_one({"join_code": join_code, "test_active": True}):
        join_code = gen_join_code(school_id)

    await upsert_active_test(body.teacher_id, body.test_class, {
        "questions": questions,
        "test_active": False,
        "answers_revealed": False,
        "results": {},
        "subject": body.subject,
        "language": body.language,
        "difficulty": body.difficulty,
        "test_type": test_type,
        "join_code": join_code,
        "school_id": t.get("school_id", ""),
        "total_marks": sum(q.get("marks", 1) for q in questions) if test_type == "subjective" else len(questions),
    })

    at = await db.active_tests.find_one({"teacher_id": body.teacher_id, "test_class": body.test_class}, {"_id": 0})
    return at

@api_router.post("/teacher/activate")
async def teacher_activate(body: ActivateIn):
    # Find the active test for the given join_code under this teacher
    at = await db.active_tests.find_one({"teacher_id": body.teacher_id, "join_code": body.join_code}, {"_id": 0})
    if not at:
        # Activate the most recent test
        tests = await get_all_active_tests(body.teacher_id)
        if not tests:
            raise HTTPException(404, "No tests found")
        at = tests[0]

    if not at.get("questions"):
        raise HTTPException(400, "Generate questions first")

    test_class = at.get("test_class", "")
    await upsert_active_test(body.teacher_id, test_class, {
        "join_code": body.join_code, "test_active": True, "answers_revealed": False,
    })
    return await db.active_tests.find_one({"teacher_id": body.teacher_id, "test_class": test_class}, {"_id": 0})

@api_router.post("/teacher/{tid}/reveal/{test_class}")
async def teacher_reveal(tid: str, test_class: str):
    test_class_decoded = test_class.replace("_", " ")
    at = await db.active_tests.find_one({"teacher_id": tid, "test_class": test_class_decoded}, {"_id": 0})
    if not at:
        raise HTTPException(404, "Test not found")
    results = at.get("results", {})
    total_marks = at.get("total_marks", len(at.get("questions", [])))
    avg = (sum(r.get("score", 0) for r in results.values()) / len(results)) if results else 0
    record = {
        "id": str(uuid.uuid4()), "teacher_id": tid,
        "join_code": at.get("join_code", ""), "date": now_iso(),
        "test_class": at.get("test_class", ""), "subject": at.get("subject", ""),
        "test_type": at.get("test_type", "mcq"),
        "questions": at.get("questions", []), "results": results,
        "total_students": len(results), "avg_score": round(avg, 1),
        "total_marks": total_marks,
    }
    await db.test_history.insert_one(record)
    record.pop("_id", None)
    await upsert_active_test(tid, test_class_decoded, {"answers_revealed": True, "test_active": False})
    return {"ok": True, "record": record}

@api_router.get("/teacher/{tid}/history")
async def teacher_history(tid: str):
    docs = await db.test_history.find({"teacher_id": tid}, {"_id": 0}).sort("date", -1).to_list(500)
    return docs

@api_router.post("/teacher/grade-subjective")
async def grade_subjective(body: SubjectiveGradeIn):
    """Teacher manually grades subjective answers or triggers auto-grading."""
    at = await db.active_tests.find_one({"teacher_id": body.teacher_id, "join_code": body.join_code}, {"_id": 0})
    if not at:
        raise HTTPException(404, "Test not found")
    results = at.get("results", {})
    student_result = results.get(body.student_name)
    if not student_result:
        raise HTTPException(404, "Student result not found")
    
    # Update marks for each question
    total_score = 0
    for q_idx, marks in body.marks.items():
        student_result["question_marks"] = student_result.get("question_marks", {})
        student_result["question_marks"][str(q_idx)] = marks
        total_score += marks
    
    student_result["score"] = total_score
    results[body.student_name] = student_result
    
    await db.active_tests.update_one(
        {"teacher_id": body.teacher_id, "join_code": body.join_code},
        {"$set": {"results": results}}
    )
    return {"ok": True, "score": total_score}


# ── STUDENT ──
@api_router.post("/student/find-test")
async def student_find_test(body: FindTestIn):
    code = (body.join_code or "").strip().upper()
    at = await db.active_tests.find_one(
        {"join_code": code, "$or": [{"test_active": True}, {"answers_revealed": True}]},
        {"_id": 0},
    )
    if not at:
        raise HTTPException(404, "Invalid code or no active test")

    teacher = await get_teacher(at["teacher_id"])
    if not teacher:
        raise HTTPException(404, "Teacher not found")

    # School ID check
    if body.school_id and at.get("school_id") and at["school_id"] != body.school_id.strip().upper():
        raise HTTPException(400, "This test is not from your school.")

    # Class match
    def _norm(c): return c.replace(" ", "").replace("-", "").lower()
    if at.get("test_class") and _norm(at["test_class"]) != _norm(body.student_class):
        raise HTTPException(400, f"This test is for {at['test_class']} students only.")

    # Already attempted
    already = await db.student_attempts.find_one({
        "student_name": body.student_name.strip(),
        "student_class": body.student_class,
        "join_code": code,
    })

    # Strip answers from questions if test active
    qs = at.get("questions", [])
    test_type = at.get("test_type", "mcq")
    if not at.get("answers_revealed"):
        if test_type == "mcq":
            qs_safe = [{"q": q["q"], "options": q["options"], "type": "mcq"} for q in qs]
        else:
            qs_safe = [{"q": q["q"], "marks": q["marks"], "section": q["section"], "type": "subjective"} for q in qs]
    else:
        qs_safe = qs

    return {
        "teacher_id": at["teacher_id"], "teacher_name": teacher["name"],
        "join_code": at["join_code"], "test_class": at.get("test_class", ""),
        "subject": at.get("subject", ""), "test_active": at.get("test_active", False),
        "answers_revealed": at.get("answers_revealed", False),
        "test_type": test_type, "total_marks": at.get("total_marks", len(qs)),
        "questions": qs_safe, "already_attempted": bool(already),
        "previous_attempt": (
            {"score": already["score"], "total": already["total"],
             "answers": already.get("answers", {}), "auto_submit": already.get("auto_submit", False)}
            if already else None
        ),
    }

@api_router.post("/student/submit")
async def student_submit(body: StudentSubmitIn):
    code = (body.join_code or "").strip().upper()
    at = await db.active_tests.find_one({"join_code": code, "test_active": True}, {"_id": 0})
    if not at:
        raise HTTPException(404, "Test not active")

    def _norm(c): return c.replace(" ", "").replace("-", "").lower()
    if at.get("test_class") and _norm(at["test_class"]) != _norm(body.student_class):
        raise HTTPException(400, f"This test is for {at['test_class']} students only.")

    existing = await db.student_attempts.find_one({
        "student_name": body.student_name.strip(),
        "student_class": body.student_class, "join_code": code,
    })
    if existing:
        raise HTTPException(400, "You have already attempted this test.")

    questions = at.get("questions", [])
    test_type = at.get("test_type", "mcq")
    score = 0
    total = at.get("total_marks", len(questions))
    norm_answers: Dict[str, Any] = {}

    if test_type == "mcq":
        for k, v in (body.answers or {}).items():
            try:
                norm_answers[str(int(k))] = int(v)
            except Exception:
                continue
        for i, q in enumerate(questions):
            if norm_answers.get(str(i)) == q.get("answer"):
                score += 1
        # Auto-grade subjective with AI
        grading_results = {}
    else:
        # Subjective: store answers, AI auto-grade
        for k, v in (body.answers or {}).items():
            norm_answers[str(k)] = str(v)
        
        # Auto-grade with AI
        grading_results = {}
        for i, q in enumerate(questions):
            student_ans = norm_answers.get(str(i), "")
            if student_ans.strip():
                grade = await grade_subjective_answer(
                    q.get("q", ""), q.get("expected_answer", ""),
                    q.get("keywords", []), student_ans, q.get("marks", 1)
                )
                grading_results[str(i)] = grade
                score += grade["marks"]
            else:
                grading_results[str(i)] = {"marks": 0, "feedback": "No answer provided"}

    attempt = {
        "id": str(uuid.uuid4()), "teacher_id": at["teacher_id"],
        "student_name": body.student_name.strip(), "student_class": body.student_class,
        "school_id": at.get("school_id", ""),
        "subject": at.get("subject", body.student_subject),
        "test_class": at.get("test_class", ""), "join_code": code,
        "answers": norm_answers, "score": score, "total": total,
        "test_type": test_type, "auto_submit": body.auto_submit,
        "date": now_iso(), "questions": questions,
        "grading": grading_results,
    }
    await db.student_attempts.insert_one(attempt)
    attempt.pop("_id", None)

    # Update teacher live results
    results = at.get("results", {})
    results[body.student_name.strip()] = {
        "score": score, "total": total, "answers": norm_answers,
        "auto_submit": body.auto_submit, "test_type": test_type,
        "grading": grading_results,
    }
    await db.active_tests.update_one({"teacher_id": at["teacher_id"], "join_code": code}, {"$set": {"results": results}})

    return {
        "score": score, "total": total, "auto_submit": body.auto_submit,
        "questions": questions, "answers": norm_answers,
        "test_type": test_type, "grading": grading_results,
    }

@api_router.get("/student/history")
async def student_history(name: str, student_class: str):
    docs = await db.student_attempts.find(
        {"student_name": name, "student_class": student_class}, {"_id": 0}
    ).sort("date", -1).to_list(500)
    return docs


# ────────────────────────── SETUP ──────────────────────────
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware, allow_credentials=True,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    await ensure_seed()
    logger.info("App started")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
