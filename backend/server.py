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
async def call_groq(prompt: str, system_msg: str) -> str:
    """Groq fallback using llama-3.3-70b-versatile"""
    from groq import Groq
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise Exception("GROQ_API_KEY not configured")
    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        max_tokens=8000,
        temperature=0.3,
    )
    return completion.choices[0].message.content


async def generate_questions_llm(
    lesson_text: Optional[str], image_b64: Optional[str], count: int,
    test_class: str, subject: str,
    language: str = "English", difficulty: int = 2,
) -> List[dict]:

    api_key = os.environ.get('GEMINI_API_KEY', '')

    diff_map = {
        1: {
            "tag": "KNOWLEDGE",
            "desc": "Direct facts and definitions from NCERT textbooks."
        },
        2: {
            "tag": "UNDERSTANDING",
            "desc": "Conceptual clarity and application of rules/formulas."
        },
        3: {
            "tag": "HOTS",
            "desc": "Higher Order Thinking Skills; multi-step logic and analysis."
        }
    }

    diff_info = diff_map.get(int(difficulty), diff_map[2])

    system_msg = (
        f"You are a Senior CBSE Paper Setter for {subject}, Class {test_class}. "
        "Create high-quality academic MCQs strictly following the NCERT curriculum. "
        "Avoid meta-questions about the document; focus only on the subject matter."
    )

    prompt = (
        f"Generate exactly {count} academic MCQs for Class {test_class} {subject} based on the attached content.\n"
        f"Difficulty: {diff_info['tag']} ({diff_info['desc']}).\n"
        f"Language: {language}.\n\n"
        "STRICT RULES:\n"
        "1. NO 'meta' questions (e.g., 'What is the title?', 'What is this lesson about?').\n"
        "2. Focus on key terms, definitions, laws, and facts mentioned in the text.\n"
        "3. Ensure all 4 options are plausible; only 1 must be correct.\n"
        "4. Return ONLY a JSON object in this format:\n"
        '{"questions":[{"q":"question text","options":["A","B","C","D"],"answer":0}]}'
    )
    
    text = None

    if api_key:
        try:
            chat = LlmChat(
                api_key=api_key,
                session_id=f"gen-{uuid.uuid4()}",
                system_message=system_msg,
            ).with_model("gemini", "gemini-2.5-flash-lite").with_params(max_tokens=8000)

            if image_b64:
                cleaned_img = re.sub(r"^data:image/[^;]+;base64,", "", image_b64).strip()
                msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=cleaned_img)])
            else:
                msg = UserMessage(text=prompt)

            resp = await chat.send_message(msg)
            text = resp if isinstance(resp, str) else str(resp)
            logger.info("Questions generated via Gemini")
        except Exception as e:
            logger.warning(f"Gemini failed: {e}. Trying Groq fallback...")
            text = None

    if text is None:
        try:
            groq_prompt = prompt
            if image_b64:
                groq_prompt = prompt.replace(
                    "\n\nThe lesson is in the attached image.",
                    f"\n\nNote: An image was provided but could not be processed."
                )
            text = await call_groq(groq_prompt, system_msg)
            logger.info("Questions generated via Groq fallback")
        except Exception as e:
            logger.exception("Both Gemini and Groq failed")
            raise HTTPException(502, f"Both AI providers failed. Error: {e}")

    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]

    try:
        data = json_module.loads(text)
    except Exception:
        raise HTTPException(502, "Could not parse AI response.")

    questions = data.get("questions", [])
    cleaned = []
    for q in questions:
        qtext = q.get("q") or q.get("question")
        options = q.get("options") or []
        ans = q.get("answer", 0)
        if qtext and isinstance(options, list) and len(options) >= 2:
            cleaned.append({"q": str(qtext), "options": [str(o) for o in options][:4], "answer": int(ans)})
    
    return cleaned


# ────────────────────────── ROUTES ──────────────────────────
@api_router.get("/")
async def root():
    return {"message": "Govt School Exam Platform API", "ok": True}

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
    tid = short_id("T")
    teacher = {
        "id": tid,
        "name": body.name.strip(),
        "subject": body.subject.strip(),
        "password": body.password.strip(),
        "active": True,
        "created_at": now_iso(),
    }
    await db.teachers.insert_one(teacher)
    return teacher

@api_router.put("/admin/teachers/{tid}")
async def update_teacher(tid: str, body: TeacherUpdateIn):
    await db.teachers.update_one({"id": tid}, {"$set": body.dict()})
    return {"ok": True}

@api_router.post("/teacher/generate")
async def teacher_generate(body: GenerateIn):
    t = await get_teacher(body.teacher_id)
    if not t: raise HTTPException(404, "Teacher not found")
    
    count = max(3, min(20, int(body.count or 10)))
    questions = await generate_questions_llm(
        body.lesson_text, body.image_base64, count,
        test_class=body.test_class,
        subject=body.subject,
        language=body.language,
        difficulty=body.difficulty,
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
    return await get_active_test(body.teacher_id)

@api_router.post("/student/submit")
async def student_submit(body: StudentSubmitIn):
    code = body.join_code.strip().upper()
    at = await db.active_tests.find_one({"join_code": code, "test_active": True})
    if not at: raise HTTPException(404, "Test not active")

    questions = at.get("questions", [])
    score = sum(1 for i, q in enumerate(questions) if body.answers.get(str(i)) == q.get("answer"))

    attempt = {
        "teacher_id": at["teacher_id"],
        "student_name": body.student_name,
        "score": score,
        "total": len(questions),
        "date": now_iso()
    }
    await db.student_attempts.insert_one(attempt)
    return {"score": score, "total": len(questions)}

# ... (rest of routes maintained as per original logic)

app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def on_startup():
    await ensure_seed()

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
