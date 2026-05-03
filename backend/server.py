from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json as json_module
import re
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
EMERGENT_LLM_KEY = os.environ.get('GEMINI_API_KEY', '')

app = FastAPI(title="Govt School Exam Platform API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ────────────────────────── HELPERS ──────────────────────────
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def short_id(prefix="T"):
    return prefix + str(int(datetime.now(timezone.utc).timestamp() * 1000))[-6:]


# ────────────────────────── MODELS ──────────────────────────
class AdminLoginIn(BaseModel):
    password: str

class AdminPasswordIn(BaseModel):
    new_password: str

class TeacherCreateIn(BaseModel):
    name: str
    subject: str = "General"
    password: str

class TeacherUpdateIn(BaseModel):
    name: str
    subject: str
    password: str

class TeacherLoginIn(BaseModel):
    teacher_id: str
    password: str

class GenerateIn(BaseModel):
    teacher_id: str
    lesson_text: Optional[str] = None
    image_base64: Optional[str] = None
    count: int = 10
    test_class: str
    subject: str
    language: str = "English"  # English | Hindi
    difficulty: int = 2  # 1=Easy, 2=Medium, 3=Hard

class ActivateIn(BaseModel):
    teacher_id: str
    join_code: str

class StudentSubmitIn(BaseModel):
    student_name: str
    student_class: str
    student_subject: str
    join_code: str
    answers: Dict[str, int]  # {"0": 2, "1": 1}
    auto_submit: bool = False

class FindTestIn(BaseModel):
    join_code: str
    student_name: str
    student_class: str


# ────────────────────────── DB HELPERS ──────────────────────────
async def ensure_seed():
    admin = await db.admin.find_one({"_id": "admin"})
    if not admin:
        await db.admin.insert_one({"_id": "admin", "username": "admin", "password": "Admin@8006"})
        logger.info("Seeded default admin (admin/admin123)")

async def get_teacher(tid: str):
    t = await db.teachers.find_one({"id": tid}, {"_id": 0})
    return t

async def get_active_test(tid: str):
    at = await db.active_tests.find_one({"teacher_id": tid}, {"_id": 0})
    if not at:
        at = {
            "teacher_id": tid,
            "questions": [],
            "test_active": False,
            "answers_revealed": False,
            "join_code": "",
            "results": {},
            "test_class": "",
            "subject": "",
        }
        await db.active_tests.insert_one(at)
        at.pop("_id", None)
    return at

async def upsert_active_test(tid: str, data: dict):
    data["teacher_id"] = tid
    await db.active_tests.update_one({"teacher_id": tid}, {"$set": data}, upsert=True)


# ────────────────────────── LLM ──────────────────────────
async def generate_questions_llm(
    lesson_text: Optional[str], image_b64: Optional[str], count: int,
    language: str = "English", difficulty: int = 2,
) -> List[dict]:
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        raise HTTPException(500, "GEMINI_API_KEY not configured")

    diff_map = {
        1: "EASY (basic recall, definitions, simple facts directly from the lesson)",
        2: "MEDIUM (understanding and explanation, requires comprehension of concepts)",
        3: "HARD (application and analysis, requires reasoning, comparisons, or inference)",
    }
    diff_desc = diff_map.get(int(difficulty), diff_map[2])

    if str(language).lower() == "hindi":
        lang_instruction = (
            "Write the question text and ALL four options entirely in HINDI (Devanagari script). "
            "Use clear, school-textbook-style Hindi suitable for Indian government school students. "
            "Do NOT mix English. Proper nouns may stay in English in parentheses if needed."
        )
    else:
        lang_instruction = "Write the question text and all four options in clear, simple ENGLISH suitable for Indian school students."

    system_msg = (
        "You are an expert Indian school teacher who creates clear, fair multiple-choice "
        "questions strictly from the provided lesson content. Always return ONLY valid JSON, "
        "with no markdown, no commentary, no code fences."
    )

    prompt = (
        f"Generate exactly {count} multiple choice questions based on the lesson content.\n"
        f"Difficulty level: {diff_desc}.\n"
        f"Language: {lang_instruction}\n"
        f"Each question MUST have exactly 4 options. Return ONLY a JSON object in this exact format, no other text:\n"
        f'{{"questions":[{{"q":"question text","options":["option A","option B","option C","option D"],"answer":0}}]}}\n'
        f'The "answer" field MUST be an integer 0, 1, 2, or 3 indicating the index of the correct option. '
        f"Make sure questions cover key concepts from the lesson."
    )
    if lesson_text:
        prompt += f"\n\nLesson Text:\n{lesson_text}"
    elif image_b64:
        prompt += "\n\nThe lesson is in the attached image. Read it carefully (including any printed text in English/Hindi) and base your questions on its content."

    chat = LlmChat(
        api_key=api_key,
        session_id=f"gen-{uuid.uuid4()}",
        system_message=system_msg,
    ).with_model("gemini", "gemini-2.5-flash").with_params(max_tokens=4000)

    if image_b64:
        # Strip "data:image/...;base64," prefix if present
        cleaned = re.sub(r"^data:image/[^;]+;base64,", "", image_b64).strip()
        msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=cleaned)])
    else:
        msg = UserMessage(text=prompt)

    try:
        resp = await chat.send_message(msg)
    except Exception as e:
        logger.exception("LLM call failed")
        raise HTTPException(502, f"LLM error: {e}")

    text = resp if isinstance(resp, str) else str(resp)
    # Strip code fences if any
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Find first { and last } to be safe
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]

    try:
        data = json_module.loads(text)
    except Exception as e:
        logger.error(f"Parse error. Raw: {text[:500]}")
        raise HTTPException(502, f"Could not parse AI response. Try again.")

    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise HTTPException(502, "AI returned no questions. Try again.")

    cleaned = []
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
        cleaned.append({"q": str(qtext), "options": [str(o) for o in options][:4], "answer": ans})
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
    # Add stats per teacher
    out = []
    for t in docs:
        at = await db.active_tests.find_one({"teacher_id": t["id"]}, {"_id": 0}) or {}
        history_count = await db.test_history.count_documents({"teacher_id": t["id"]})
        out.append({
            **t,
            "test_active": at.get("test_active", False),
            "join_code": at.get("join_code", ""),
            "history_count": history_count,
            "results_count": len(at.get("results", {})),
        })
    return out

@api_router.post("/admin/teachers")
async def create_teacher(body: TeacherCreateIn):
    if not body.name.strip() or not body.password.strip():
        raise HTTPException(400, "Name and password required")
    tid = short_id("T")
    teacher = {
        "id": tid,
        "name": body.name.strip(),
        "subject": (body.subject or "General").strip(),
        "password": body.password.strip(),
        "active": True,
        "created_at": now_iso(),
    }
    await db.teachers.insert_one(teacher)
    teacher.pop("_id", None)
    await get_active_test(tid)  # ensure row exists
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
    await get_active_test(tid)  # recreate empty
    return {"ok": True}

@api_router.get("/admin/students")
async def admin_students():
    # Group attempts by name||class
    attempts = await db.student_attempts.find({}, {"_id": 0}).to_list(10000)
    grouped: Dict[str, List[dict]] = {}
    for a in attempts:
        key = f"{a.get('student_name', '')}||{a.get('student_class', '')}"
        grouped.setdefault(key, []).append(a)
    return [
        {
            "key": k,
            "student_name": v[0]["student_name"],
            "student_class": v[0]["student_class"],
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


# ── TEACHER ──
@api_router.post("/teacher/login")
async def teacher_login(body: TeacherLoginIn):
    t = await get_teacher(body.teacher_id)
    if not t or t.get("password") != body.password:
        raise HTTPException(401, "Wrong password")
    if not t.get("active", True):
        raise HTTPException(403, "Account disabled by admin")
    return {"id": t["id"], "name": t["name"], "subject": t["subject"]}

@api_router.get("/teacher/public-list")
async def teacher_public_list():
    """Public list (id, name, subject, active) for teacher login picker."""
    docs = await db.teachers.find({}, {"_id": 0, "password": 0}).to_list(1000)
    return docs

@api_router.get("/teacher/{tid}/state")
async def teacher_state(tid: str):
    t = await get_teacher(tid)
    if not t:
        raise HTTPException(404, "Teacher not found")
    at = await get_active_test(tid)
    return at

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

    questions = await generate_questions_llm(
        body.lesson_text, body.image_base64, count,
        language=body.language, difficulty=body.difficulty,
    )

    await upsert_active_test(body.teacher_id, {
        "questions": questions,
        "test_active": False,
        "answers_revealed": False,
        "results": {},
        "test_class": body.test_class,
        "subject": body.subject,
        "language": body.language,
        "difficulty": body.difficulty,
    })
    at = await get_active_test(body.teacher_id)
    return at

@api_router.post("/teacher/activate")
async def teacher_activate(body: ActivateIn):
    code = (body.join_code or "").strip().upper()
    if not code:
        raise HTTPException(400, "Join code required")
    at = await get_active_test(body.teacher_id)
    if not at.get("questions"):
        raise HTTPException(400, "Generate questions first")
    await upsert_active_test(body.teacher_id, {
        "join_code": code, "test_active": True, "answers_revealed": False,
    })
    at = await get_active_test(body.teacher_id)
    return at

@api_router.post("/teacher/{tid}/reveal")
async def teacher_reveal(tid: str):
    at = await get_active_test(tid)
    if not at.get("questions"):
        raise HTTPException(400, "No questions")
    results = at.get("results", {})
    avg = (sum(r["score"] for r in results.values()) / len(results)) if results else 0
    record = {
        "id": str(uuid.uuid4()),
        "teacher_id": tid,
        "join_code": at.get("join_code", ""),
        "date": now_iso(),
        "test_class": at.get("test_class", ""),
        "subject": at.get("subject", ""),
        "questions": at.get("questions", []),
        "results": results,
        "total_students": len(results),
        "avg_score": round(avg, 1),
    }
    await db.test_history.insert_one(record)
    record.pop("_id", None)

    await upsert_active_test(tid, {"answers_revealed": True, "test_active": False})
    return {"ok": True, "record": record}

@api_router.get("/teacher/{tid}/history")
async def teacher_history(tid: str):
    docs = await db.test_history.find({"teacher_id": tid}, {"_id": 0}).sort("date", -1).to_list(500)
    return docs


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

    # Class match
    def normalize_class(c): return c.replace(" ", "").replace("-", "").lower()
    if at.get("test_class") and normalize_class(at["test_class"]) != normalize_class(body.student_class):
        raise HTTPException(400, f"This test is for {at['test_class']} students only.")

    # Already attempted
    already = await db.student_attempts.find_one({
        "student_name": body.student_name.strip(),
        "student_class": body.student_class,
        "join_code": code,
    })

    # Strip answers from questions when sending to client (only if test active and not revealed)
    qs = at.get("questions", [])
    if not at.get("answers_revealed"):
        qs_safe = [{"q": q["q"], "options": q["options"]} for q in qs]
    else:
        qs_safe = qs

    return {
        "teacher_id": at["teacher_id"],
        "teacher_name": teacher["name"],
        "join_code": at["join_code"],
        "test_class": at.get("test_class", ""),
        "subject": at.get("subject", ""),
        "test_active": at.get("test_active", False),
        "answers_revealed": at.get("answers_revealed", False),
        "questions": qs_safe,
        "already_attempted": bool(already),
        "previous_attempt": (
            {
                "score": already["score"],
                "total": already["total"],
                "answers": already.get("answers", {}),
                "auto_submit": already.get("auto_submit", False),
            } if already else None
        ),
    }

@api_router.post("/student/submit")
async def student_submit(body: StudentSubmitIn):
    code = (body.join_code or "").strip().upper()
    at = await db.active_tests.find_one({"join_code": code, "test_active": True}, {"_id": 0})
    if not at:
        raise HTTPException(404, "Test not active")

    # Class match
    def normalize_class(c): return c.replace(" ", "").replace("-", "").lower()
    if at.get("test_class") and normalize_class(at["test_class"]) != normalize_class(body.student_class):
        raise HTTPException(400, f"This test is for {at['test_class']} students only.")

    # Already attempted
    existing = await db.student_attempts.find_one({
        "student_name": body.student_name.strip(),
        "student_class": body.student_class,
        "join_code": code,
    })
    if existing:
        raise HTTPException(400, "You have already attempted this test.")

    questions = at.get("questions", [])
    score = 0
    norm_answers: Dict[str, int] = {}
    for k, v in (body.answers or {}).items():
        try:
            norm_answers[str(int(k))] = int(v)
        except Exception:
            continue
    for i, q in enumerate(questions):
        if norm_answers.get(str(i)) == q.get("answer"):
            score += 1

    attempt = {
        "id": str(uuid.uuid4()),
        "teacher_id": at["teacher_id"],
        "student_name": body.student_name.strip(),
        "student_class": body.student_class,
        "subject": at.get("subject", body.student_subject),
        "test_class": at.get("test_class", ""),
        "join_code": code,
        "answers": norm_answers,
        "score": score,
        "total": len(questions),
        "auto_submit": body.auto_submit,
        "date": now_iso(),
        "questions": questions,  # snapshot for review later
    }
    await db.student_attempts.insert_one(attempt)
    attempt.pop("_id", None)

    # Mirror to active_tests.results for teacher live view
    results = at.get("results", {})
    results[body.student_name.strip()] = {
        "score": score, "total": len(questions),
        "answers": norm_answers, "auto_submit": body.auto_submit,
    }
    await db.active_tests.update_one({"teacher_id": at["teacher_id"]}, {"$set": {"results": results}})

    return {
        "score": score,
        "total": len(questions),
        "auto_submit": body.auto_submit,
        "questions": questions,  # include answers since test submitted
        "answers": norm_answers,
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
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await ensure_seed()
    logger.info("App started")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
