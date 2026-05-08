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
    selected_topic: str = ""  # specific chapter/topic

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


# NCERT/CBSE Syllabus 2026-27 — Class 6 to 10 (remaining classes to be added)

NCERT_SYLLABUS = {
    "10|English": "Directorate of Education, GNCT of Delhi English Language And Literature (Subject Code- 184) Annual Syllabus (2026 – 27) Class – X FIRST FLIGHT FOOTPRINTS WITHOUT FEET READING SKILL, WRITING SKILL & GRAMMAR PROSE Ch 1: A Triumph of Surgery READING SKILL Ch 1: A Letter to God Ch 2: The Thief’s Story 1. Discursive Passage Ch 2: Nelson Mandela : Ch 3: The Midnight Visitor 2. Case – based factual passage (with Long walk to Ch 4: A Question of Trust visual input-statistical data, chart freedom Ch 5: Footprints Without Feet etc.) Ch 3: Two Stories about Flying Multiple Choice Ch 4: From the Diary of Questions/Objective Type Anne Frank Questions and Short Answer Ch 5: Glimpses of India Questions (to be answered in 30 – 40 words) will be asked to assess POEMS comprehension, inference, analysis, P 1: Dust Of Snow interpretation, evaluation, and P 2: Fire And Ice vocabulary. P 3: A Tiger in the Zoo P 4: How to tell Wild WRITING SKILL Animals 1. Formal Letter based on a given P 5: The Ball Poem situation. 2. Analytical Paragraph on a given Map / Chart / Graph /Cue (s) GRAMMAR 1. Determiners 2. Tenses 3. Modals 4. Subject – Verb Concord 5. Reported Speech a. Commands and requests b. Statements c. Questions Accurate use of spelling, punctuation and grammar in context will be assessed through Gap filling/ Editing/ Transformation exercises. WORDS AND EXPRESSION – II (Workbook for Class X) --- Units 1 to 4 Note: Teachers are suggested to: i. Encourage interaction among peers, students and teachers through activities such as Role play, discussion, group work etc. ii. Reduce teacher-talking time and keep it to the minimum. iii. Take up questions for discussion to encourage pupils to participate and to marshal their ideas and express and defend their views, and iv. Follow the Speaking and Listening activities given in the NCERT books. Note: Completion of the above syllabus by 05 September 2026 Mid -Term Exam FIRST FLIGHT FOOTPRINTS WITHOUT FEET READING SKILL, WRITING SKILL & GRAMMAR PROSE Ch 6: The making of a READING SKILL Ch 6: Mijbil the Otter Scientist 1. Discursive Passage Ch 7: Madam Rides the Ch 7: The Necklace 2. Case – based factual passage (with Bus Ch 8: Bholi visual input-statistical data, chart Ch 8: The Sermon at Ch 9: The Book that Saved the etc.) Benares Earth Multiple Choice Questions/ Ch 9: The Proposal (Play) Objective Type Questions and Short Answers Questions (to be POEMS answered in 30 – 40 words) will be P 6: Amanda! asked to assess comprehension, P 7: ",
    "10|Hindi": "िश#ा िनदेशालय, रा-.ीय राजधानी #े2, िद3ली वािष6क पाठ्य;म [स2: 2026-27] क#ा - 10, िवषय - िहंदी (अ), िवषय कोड – 002 ि\"ितज भाग 2 अपिठत बोध 0याकरण एवं रचना:मक लेखन का0य खंड • अपिठत गSांश एवं • रचना के आधार पर वा`य भदे व रचनांतरण 1. पद (सरू दास) काUयांश पर िचतं न • वाaय, वाaय पbरवतcन Mमता एवं अिभUयिV • पद पbरचय 2. राम-ल0मण-परशरु ाम संवाद (तलु सीदास) कौशल परक • अलंकार (अथाcलंकार – उपमा, gपक, उ:?ेMा, 3. आ:मक<य (जयशकं र ?साद) बहYिवकZपीय, अितशयोिV, मानवीकरण) अितलघ]ू रा:मक एवं • संकेत िबंदओु ं के आधार पर समसामियक एवं ग@ खंड लघ]ू रा:मक ?^ Uयावहाbरक जीवन से जड़ु े िवषयk पर अनaु छेद 7. नेताजी का चDमा (Eवयं ?काश) लेखन (लगभग 120 शnदk म)o • औपचाbरक पq लेखन (लगभग 100 शnदk म)o 8. बालगोिबन भगत (रामवMृ बेनीपरु ी) • अनौपचाbरक पq लेखन (लगभग 100 शnदk म)o 9. लखनवी अदं ाज़ (यशपाल) • Eवव]ृ लेखन (लगभग 80 शnदk म)o • ई-मले लेखन (लगभग 80 शnदk म)o कृितका, भाग 2 • िवsापन लेखन (लगभग 40 शnदk म)o 1. माता का अचँ ल (िशवपजू न सहाय) • संदशे लेखन (लगभग 40 शnदk म)o 2. साना-साना हाथ जोिड़ (मध ुकांकbरया) नोट:- • उपयcVु पाठ्यwम 05 िसतंबर, 2026 तक परू ा कर िलया जाए। • मyयाविध परीMा हते ुपनु राविृ] करवाई जाए। पनु राविृत मyयाविध परीMा ि\"ितज भाग 2 अपिठत बोध 0याकरण एवं रचना:मक लेखन का0य खंड • अपिठत गSांश एवं • रचना के आधार पर वा`य भदे व रचनांतरण काUयांश पर िचतं न अ‡यास 4. उ:साह, Mमता एवं अिभUयिV • वाaय, वाaय पbरवतcन अ‡यास अट नह{ रही ह ै(सयू cकांत िqपाठी ‘िनराला’) कौशल परक • पद पbरचय सोदाहरण अ‡यास 5. यह दतं bु रत मसु कान, फसल (नागाजcनु ) बहYिवकZपीय, • अलंकार (अथाcलंकार – उपमा, gपक, उ:?ेMा, 6. संगतकार (मगं लेश डबराल) अितलघ]ू रा:मक एवं अितशयोिV, मानवीकरण) सोदाहरण अ‡यास लघ]ू रा:मक ?^ • संकेत िबƒदओु ंके आधार पर समसामियक एवं ग@ खंड Uयावहाbरक जीवन से जड़ु े िवषयk पर अनaु छेद लेखन (लगभग 120 शnदk म)o 10. एक कहानी यह भी (मƒन ूभडं ारी) • औपचाbरक पq लेखन (लगभग 100 शnदk म)o 11. नौबतखाने म o इबादत (यत{… िम†) • अनौपचाbरक पq लेखन (लगभग 100 शnदk म)o 12. संEकृित (भदतं आनंद कौसZयायन) • Eवव]ृ लेखन (लगभग 80 शnदk म)o • ई-मले लेखन (लगभग 80 शnदk म)o कृितका, भाग 2 • िवsापन लेखन (लगभग 40 शnदk म)o • संदशे लेखन (लगभग 40 शnदk म)o 3. म ˆ `यk िलखता ह‰ ँ(अsेय) सपं ूणK पाठ्यMम को 5 िदसबं र 2026 तक पूणK कर िलया जाए। समPत पाठ्यMम कQ पुनराविृ त वािषKक परी\"ा मU हटाए गए पाठW को छोड़कर सपं ूणK पाठ्यMम से Z[ पूछे जाएगँ े l नोट: सी. बी. एस. ई. के नवीनतम (स^ : 2026-27) िनदश‹ ानसु ार िनŒनिलिखत पाठk से ?^ नह` पछू े जाएगँ े :- ि\"ितज, भाग 2 का0य खंड कृितका, भाग 2 Ø सवैया, किव] – दवे Ø जॉजc पंचम क(cid:143) नाक – कमले(cid:144)र Ø छाया मत छूना – िगbरजा कुमार माथरु Ø एही ठैयाँ झलु नी हरे ानी हो रामा! –िशव ?साद िम† g… Ø कƒयादान – ऋतरु ाज ि\"ितज, भाग 2 ग@ खंड Ø ",
    "10|Mathematics": "DIRECTORATE OF EDUCATION, GNCT of DELHI ANNUAL SYLLABUS CLASS: X (2026-2027) SUBJECT: MATHEMATICS (Code: 041 & 241) Course Structure Units Unit Name Marks I Number Systems 06 II Algebra 20 III Coordinate Geometry 06 IV Geometry 15 V Trigonometry 12 VI Mensuration 10 VII Statistics & Probability 11 Total 80 Internal Assessment 20 Grand Total 100 Chapter No. & name Competencies Explanation 1. REAL NUMBERS The learner:  Describes Fundamental  Develops understanding of Theorem of Arithmetic with  Fundamental Theorem of Arithmetic - statements after numbers, including the set of real examples reviewing work done earlier and after illustrating and numbers and its properties.  Prove algebraically the motivating through examples  Extends the understanding of Irrationality of numbers √2, powers (radical powers) and √3, √5, 3 + 2 √5 etc.  Proofs of irrationality of √2, √3, √5 etc. exponents.  Applies Fundamental Theorem of arithmetic to solve problems related to real life contexts. 3. PAIR OF LINEAR EQUATIONS IN TWO VARIABLES The learner:  Find the solution of pair of  Describes plotting a pair of linear linear equations in two  Pair of linear equations in two variables and graphical equations and graphically finding variables graphically and method of their solution, consistency /inconsistency. the solution. algebraically (substitution  Models and solves and elimination method)  Algebraic conditions for number of solutions. contextualized problems using  Solution of a pair of linear equations in two variables equations (e.g., simultaneous algebraically - by substitution, by elimination. linear equations in two variables). Simple situational problems. 5. ARITHMETIC PROGRESSIONS The learner:  Applies concepts of AP to  Develops strategies to apply the find the nth term and sum  Motivation for studying Arithmetic Progression concept of A.P. to daily life of n terms. situations.  Application of AP in real  Derivation of the nth term and sum of the first n terms of AP life problems and their application in solving daily life problems. 6. TRIANGLES The learner:  Prove Basic Proportionality  works out ways to differentiate theorem and applies the Definitions, examples, counter examples of similar triangles. between congruent and similar theorem and its converse in  (Prove) If a line is drawn parallel to one side of a triangle to figures. solving questions intersect the other two sides in distinct points, the other two  establishes properties for simi",
    "10|Science": "DIRECTORATE OF EDUCATION, GNCT of Delhi ANNUAL SYLLABUS (2026-27) ))) ) CLASS-10, SUBJECT: SCIENCE (086) Unit No. Unit Marks I Chemical Substances - Nature & Behaviour 25 II World of Living 25 III Natural Phenomena 12 IV Effects of Current 13 V Natural Resources 05 Total 80 Internal assessment 20 Grand total 100 Content Unit –I Chemical Substances – Nature and Behaviour Chapter-1: Chemical Reactions and Equations- Chemical reactions, Chemical equation, Balanced chemical equation, types of chemical reactions: combination, decomposition, displacement, double displacement, precipitation, endothermic exothermic reactions, oxidation and reduction. Practical: Performing and observing the following reactions and classifying them into: a)Combination reaction b) Decomposition reaction c)Displacement reaction d)Double displacement reaction (i) Action of water on quicklime (calcium oxide) (ii) Action of heat on Ferrous sulphate crystals (iii) Iron nails kept in Copper sulphate solution (iv) Reaction between Sodium sulphate and Barium chloride solutions The following topics are included in the syllabus but will be assessed only formatively to reinforce understanding without adding to summative assessments. This reduces academic stress while ensuring meaningful learning. Schools can integrate these with existing chapters as they align well. Relevant NCERT textual material is enclosed for reference. Periodic Classification of Elements: Döbereiner’s Triads, Newlands’ Law of Octaves, Mendeléev’s Periodic Table, Modern Periodic Table and the Modern, Metallic and Non metallic P roperties. Chapter-2: Acids, Bases and Salts-definitions in terms of furnishing of H+ and OH– ions, identification using indicators, chemical properties, examples and uses, neutralization, concept of pH scale (Definition relating to logarithm not required), importance of pH in everyday life; preparation and uses of Sodium Hydroxide, Bleaching powder, Baking soda, Washing soda and Plaster of Paris. Practical :A)Finding the pH of the following samples by using pH paper / universal Indicator: a)Dilute Hydrochloric acid b)Dilute NaOH solution c)Dilute Ethanoic Acid Solution d)Lemon juice e)Water f) Dilute hydrogen carbonate solution B)Studying the properties of acids and bases (HCl & NaOH) by their reaction with: a) Litmus solution (Blue/Red) b) Zinc metal c)Solid sodium carbonate Chapter-3: Metals and Non-Metals- Properties of metals and non-metals; Reactivity series; Formation and properties of ionic c",
    "6|English": "DIRECTORATE OF EDUCATION, GNCT OF DELHI ANNUAL SYLLABUS SESSION: 2026-27 CLASS: VI Subject: English Textbook- Theme Activities- Grammar & Writing Literary Curricular Goal/ Learning Outcomes Poorvi Listening/Speaking/Re Skills Devices Curricular Lesson/Poem ading/Exploration Competency Importance 1. Listening: Students listen 1.Homophones: CG-3 Students Students LESSON 1- A of hard work. to what Madhumati does to Students learn new develop the capacity BOTTLE OF Importance her bananas from her words from the story for effective 1.Understand the DEW of plantation and number the and choose four pairs communication using writer’s message on perseverance. events in the correct order in of homophones and language skills for hard-work and which they happen. (Let us write sentences. description, analysis, perseverance. Rules to listen, p.10) 2.Connecting Words: and response. achieve Students match the 2.Appreciate the success. 2. Speaking: (i) Students learn phrases in column A with C-3.2 Writes different importance of and practice the sound of letter the phrases in column B kinds of letters and choosing the right ‘S’ in different words. (Let us (page 9). essays in appropriate path to achieve success speak, p.10) style and registers for in life. Writing: Students form different media for pairs and complete the different audiences and 3.Develop 2. Speaking: (ii) Students description of a banana purposes. language through discuss the following and use the information to different activities. questions: write a few sentences CG-5 Students • What does hard work about the fruit. (Let us develop the ability to mean to you? write, p.11) recognize basic • Give three reasons linguistic aspects why you think hard (vocabulary and work is important. sentence structure) and • Share three ideas you use them in oral and would give to someone written expression. who needs to work hard. (p.11) 3. Exploration: Students find C-5.1 Identifies the 1 out the different varieties of basic linguistic bananas.(Let us explore, p.12)) aspects such as sentence style, punctuation, tense, gender, and parts of speech while reading different forms of literature. POEM 1- 1. Reading 1. Listening: students 1. Rhyming Personificati CG-1 Students develop Students THE RAVEN a folk tale listen to what the crow did Words- on, Rhyme independent reading AND THE for fun - A after he lost his food and Students write Scheme, and comprehension and 1. Recite poems with proper pronunciation FOX tale which mark t",
    "6|Hindi": "!श#ा &नदेशालय, रा./0य राजधानी #े4, 5द6ल0 वा8षक: पा=य>म 2026-27 क#ा-6, 8वषय-5हदं 0 !. (म(हार) 6वषयव:त ु <याकरण और रचना?मक अDधगम उGदेIय पाJयचयाK लLय ग3त6वDध/Q!याकलाप सं. पाठ का नाम, लेखन एवं दNताएँ रच3यता, 6वधा 1 पाठ-1. यह क*वता ● क*वता कF रचना - लय • भारत कF भौगो8लक CG-1: C-1.1, ● मेर. समझ से - समहू म[ चचा,C मातभृ Wू म भारत के और सIदय C को बढ़ाने के संदु रता का वणनC कर C-1.3 ● 8मलकर कर[ 8मलान – पाठ के शRदS सोहनलाल भौगो8लक, 8लए ‘यमनु ’ का :योग, सक[गे। का सह. अथt या संदभt से 8मलान, )*ववेद. :ाकृ<तक ● शRदS के Tप - शRदकोश, • देश-:ेम कF भावना को CG-2: C-2.1, ● पंिgतयS पर चचा C - समहू म[ चचा,C (क*वता) सां>कृ<तक 8शVक और साWथयS कF आdमसात कर सक[गे। C-2.2, C-2.3 ● सोच-*वचार के 8लए – क*वता पर और सहायता से शRदS से जड़ु [ • भारत कF सं>कृ<त से आधा`रत :\\नS के उwर का लेखन, CG-3: C-3.1 ऐ<तहा8सक :\\नS को हल करना, प`रWचत हो सक[गे। ● 8मलान - क*वता कF पंिgतयS का वभै व का ● थोड़ा 8भ]न, थोड़ा समान - • भावानकु ूल स>वर वाचन CG-4: C-4.1, भावाथ C से 8मलान, वणनC करती एक मा^ा के अतं र से शRद म[ सVम हSगे। C-4.2 ● अनमु ान या कyपना से - समहू म[ है। के अथ C म[ प`रवतनC , • पाठांतगतC :यgु त नए 8मलकर चचा,C ● *वशषे ण और उसके भेद शRदS से प`रWचत होत े हुए CG-5: C-5.1, ● आपकF बात - समहू म[ चचा C और उनका :योग कर सक[गे। C-5.2, C-5.3 लेखन, • पाठांतगतC :यgु त ● वंशी से - वा)य-यं^S के Wच^ देखकर hयाकरiणक jबदं ओु ं से शRद-जाल से नाम खोजना, अवगत होत े हुए उनका ● आज कF पहेल., भा*षक :योग करने म[ ● झरोखे से, समथ C हो सक[गे। ● साझी समझ, ● खोजबीन के 8लए प_ु प क` केवल पढ़ने कुछ पाठ केवल पढ़ने के 8लए अWभलाषा के 8लए |दए गए ह} जो कह.ं पाठ के माखनलाल *वषय को पो*षत करत े ह} तो चतवु zद. कह.ं रचना कF *व*वधता (क*वता) :>ततु कर *व)याथ~ कF (cid:127)Wच का *व>तार करत े ह}। 2 पाठ-2. गोल यह सं>मरण ● सं>मरण कF रचना - • सं>मरण *वधा से प`रWचत CG-1: C-1.1, • मेर. समझ से - समहू म[ चचा,C मेजर €यानचंद :8स)ध सं>मरण कF *वशषे ताओ ं कF हो सक[गे। C-1.3, C-1.4, • 8मलकर कर[ 8मलान – पाठ के शRदS (सं>मरण) भारतीय सचू ी बनाना और साझा • हॉकF खेल के बारे म[ जान C-1.5 का सह. अथt या संदभt से 8मलान, iखलाड़ी करना सक[गे। • पंिgतयS पर चचा C - समहू म[ चचा,C मेजर ● शRदS के जोड़,े *व8भ]न • खेल-भावना का महƒव CG-2: C-2.1, • सोच-*वचार के 8लए – सं>मरण पर C-2.3 €यानचंद के :कार के - शRद-य„ु म, समझकर, खेल-भावना आधा`रत :\\नS के उwर का लेखन, जीवन से योजक Wच…नS का :योग, *वक8सत कर सक[गे। CG-3: C-3.1, • आपकF बात - समहू म[ चचा C और जड़ु ा है। ● बात पर बल देना -‘ह.’, • भारत के महान हॉकF C-3.2 लेखन, :>ततु पाठ ‘भी’, ‘तो’ आ|द का :योग, iखलाड़ी मेजर €यानचंद • समाचार-प^ से - खेल समाचार का म[ उ]हSने ● डायर. लेखन के 8लए के बारे म[ जान सक[गे। CG-4: C-4.1, लेखन, खेल-संवाददाता के Tप म[ अपने ",
    "6|Mathematics": "DIRECTORATE OF EDUCATION, GNCT of Delhi ANNUAL SYLLABUS CLASS: VI (2026-2027) SUBJECT: MATHEMATICS Chapter Curricular Suggestive Learning Suggestive Name Content Goal & Curricular Competency Outcomes Activities Chapter – 5 Common multiples and CG-1 The learner:  Prepare sieve of common factors, Prime Understands numbers and sets of numbers (Whole  finds common multiples and Eratosthenes Prime Time numbers, Co-prime numbers, Fractions, Integers, and Rational numbers) looks common factors  Puzzles and Riddles numbers for for patterns, and appreciates relationships between  differentiates between prime based on safekeeping treasure, numbers. and co-prime numbers  common factors and Prime factorization,  expresses numbers as its prime common multiples C-1.1 Develops a sense for and an ability to manipulate Divisibility tests, Fun factorization  Even & odd numbers (e.g., read, write, form, compare, estimate, and apply with numbers  checks the divisibility of the  Prime & composite operations) large whole numbers of up to 10 digits and given number by 2,4,5,8,10 numbers expresses them in scientific notation using exponents and  Calendar activity etc. powers. Chapter – 3 Numbers can tell us The learner:  Check if your birth year things, Supercells, C-1.2 Discovers, identifies, and explores patterns in  marks numbers on number or your father/mother Number Patterns of numbers on numbers and describes rules for their formation (e.g., line mobile number is a Play the number line, prime numbers, powers of 3, etc.) and explain relations  identifies and create palindrome. Playing with digits, between different patterns. palindromic numbers  Find Kaprekar constant Pretty Palindromic  formulates strategies in for 3-digit numbers C-1.3 Explores and understands sets of numbers such as patterns, The magic everyday numbers  Magic Square activity whole numbers, fractions, integers, and rational numbers, number of Kaprekar, and their properties. Clock & calendar numbers, Mental math, C-1.4 Represents rational numbers in decimal form as an Playing with number extension of the Indian system of numeration `past the patterns, the Collatz decimal point’. conjecture, Simple Estimation, Games and C-1.5 Explores the idea of percentage and apply it in winning strategies solving problems. Chapter – 1 Patterns in numbers, C-1.6 Explores and applies fractions (both as ratios and in The learner:  Observe the patterns in Visualising number decimal form) in daily life situati",
    "6|Science": "DIRECTORATE OF EDUCATION, GNCT of Delhi ANNUAL SYLLABUS (2026-27) CLASS: 6, SUBJECT: SCIENCE BOOK: CURIOSITY Science Education aims to achieve Scientific understanding of the natural and physical world; Capacities for scientific inquiry; Understanding the evolution of scientific knowledge; Interdisciplinary understanding between science and other curricular areas; Understanding of the relationship between Science, Technology and, Society; Scientific temper and Creativity. The present syllabus has been designed around seven broad themes viz. Food; Materials; The World of the Living; How Things Work; Moving Things, People and Ideas; Natural Phenomenon and Natural Resources. In the Middle Stage, Science is taught using integrated approach. This integrated approach develops fundamental capacities related to the disciplines of Biology, Chemistry, Physics, and Earth Science while the use of connections across them helps students appreciate the interrelations between these subjects and make sense of their observations and experiences. At all Stages, along with conceptual understanding, the capacities of scientific inquiry are developed as age appropriate. These concepts and capacities are chosen both from a disciplinary perspective and in terms of what is useful and necessary in their everyday lives. Students thereby understand the world around them with increasing depth, explore scientific questions at different levels through discussion and experimentation, and learn to communicate this understanding in different ways. The Learning Standards (Curricular Goals and Competencies) for Science as an integrated curricular area, in alignment with the National Curriculum Framework 2023 are as follows: 1 Curricular Competencies Curricular Competencies Goals Goals C-1.1 Classifies matter based on observable C-2.1 Describes one-dimensional motion physical (solid, liquid, gas, shape, volume, (uniform, non-uniform, horizontal, vertical) using density, transparent, opaque, translucent, physical measurements (position, speed, and magnetic, non-magnetic, conducting, non- changes in speed) through mathematical and conducting) and chemical (pure, impure; acid, diagrammatic representations base; metal, non-metal; element, compound) characteristics C-2.2 Describes how electricity works through manipulating different elements in simple circuits CG-2: CG-1: C-1.2 Describes changes in matter (physical and and demonstrates the heating and magnetic chemical) and uses particulate nature",
    "6|Social Science": "Directorate of Education, GNCT of Delhi ANNUAL SYLLABUS SESSION: 2026-2027 SUBJECT: SOCIAL SCIENCE CLASS-VI (Middle Stage) TEXTBOOK- Exploring Society: India and Beyond Chapter Curricular Goal (CG) Competency (C) Number Learning Outcome Suggestive activities as per NCF –SE-2023 as per NCF–SE-2023 and Name CG-1: Comprehends and C-1.2: Represents and analyses  Explain the concept of  Observe and study models of the Chapter 1: interprets sources related to data related to various aspects of directions on maps, globe in the classroom. Locating different aspects of human life human life given in the form of Latitude, Longitude, co-  Practice identifying latitudes and places on and makes meaningful text, tables, charts, diagrams, and ordinates, Time Zones and longitudes on a globe. the Earth interpretations. maps. International Date Line.  Engage in the activity/game provided on pages 12–13 under the section “Let’s Explore.”  Calculate the time difference between two places based on their longitudinal positions. CG-6: Understands the spatial C-6.1: Explains key natural  Identifies continents,  Observe and study globe models in the distribution of resources (from phenomena, such as, climate, oceans, and islands, and classroom. local to global), their weather, ocean cycles, soil describes the forms of life  Engage in activities given on pages 36 Chapter 2: conservation, the formation, the flow of rivers, and found in these regions. and 40 under the section “Let’s Oceans and interdependence between how they are spatially  Locate and label Explore.” Continents natural phenomena and human distributed. continents, oceans, and  Undertake map-based activities to life, and their environmental islands on the world map. locate continents, oceans, and islands. and other implications. C-6.2: Correlates the existence of different pattern of livelihoods with different types of landforms, availability of resources, and climatic conditions and changes (in local, regional, national and global contexts.) CG- 2: Explores the process of C-2.1 Explains and analyses  Applies timelines to  Engage in the activities provided on Chapter 4: continuity and changes in major changes in the past their measure historical time pages 63 and 66 under the section Timeline human civilisations through impact on society. and uses different “Let’s Explore.” and sources specific examples from their historical sources to  Organise a visit to a nearby museum to of History context and a few hi",
    "7|English": "Directorate of Education, GNCT of Delhi Annual Syllabus: Session:2026-27 Class: VII Subject: English Textbook- Theme Activities (Listening / Grammar & Writing Literary Curricular Goals (CG) Learning Outcomes Poorvi Speaking / Skills Devices and Lesson/Poem Exploration) Competencies Lesson 1: The Importance of Listening – Students Grammar – CG-1: Develops Students Day the River education, listen to five speakers Nouns: Students independent reading  interpret Spoke gender share their views on identify nouns and comprehension and narrative texts, equality, school life and match sound words from the summarising skills by curiosity about each statement to the text and use them engaging with a variety  express ideas nature and correct speaker. (Let correctly in sentences of texts (stories, poems, orally through dreams us listen, p.12). extracts of plays, essays, discussions and Prepositions: Fill the articles, news reports) role-plays Speaking – Students blank with suitable and shows interest in perform a role-play in prepositions – at , in, reading books  write which they ask for and on, outside, above, descriptive give advice in between, among , C1.1: Applies varied paragraphs using different situations, from, for, about, comprehension strategies appropriate such as school, sports, towards, over, down, (inference, prediction vocabulary and and studies. (Let us up , off etc.) to understand grammar speak, p.13). different texts Adverbs: Fill the  interpret Reading – Students blank with suitable CG-2: Attains the ability thecultural read the story and adverbs. to write about thoughts, significance of discuss Jahnavi’s feelings, and experiences rivers in Indian dream of going to Writing Skill – of social events (e.g., traditions(IKS) school and how the Descriptive village fairs, festivals, and express river encourages her paragraph: Eg: occasions) ecological to pursue education. Students observe awareness (Let us discuss, p.3). nature around them C2.1: Uses writing through language and write a descriptive strategies, such as skills Exploration – paragraph highlighting sequencing ideas, Students discuss why colours, shapes and identifying headings/sub- rivers in India are movements they headings and forming considered sacred and notice. (Let us write, clear beginning, ending, share opinions about p.14) and paragraphs languages spoken in CG-3: Develops the their classroom. (Let capacity for effective us explore, p.14). communication using language skills for que",
    "7|Hindi": "शिक्षा निदेिालय, राष्ट्रीय राजधािी क्षेत्र, ददल्ली वार्षकि पाठ्यक्रम (2026-27) कक्षा- 7, र्वषय- द दिं ी क्र. (मल् ार) र्वषयवस्तु व्याकरण और अधधगम उद्देश्य पाठ्यचयाि गनतर्वधध/क्रक्रयाकलाप सिं. पाठ का िाम, रचिात्मक लेखि लक्ष्य र्वधा, एविं रचनयता दक्षताएँ 1. प्रस्तुत कविता में • कर्वता में र्वराम धचह्ि– कविता • कविता के िािानुकूल सस्िर • CG-1: • मेरी समझ स-े समूह ििाथ। माँ, क एक पुत्र राहुल द्िारा के अंश में उथित विराम थिह्नों का C-1.1, • शमलकर करें शमलाि– कविता में आए पात्रों िािन में सक्षम होंगे। क ािी अपनी मााँ स े प्रयोग करना। C-1.3 का उनके सलए प्रयोग में आए शब्दों से (कविता, कहानी सुनने के समलान। • कविता का सार अपन े शब्दों में मैथिलीशरण हठ और ससद्धाि थ • िब्द स े जुड़े िब्द - विसिन्न शब्दों • CG-2: • पिंक्ततयों पर चचा-ि िािाि थ पर ििाथ। सलखने में समि थ होंगे। गुप्त) (गौतम बुद्ध) के से जुडे शब्दों की सिू ी बनाना। C-2.1, • सोच-र्वचार के शलए- कविता आधाररत जीिन की करुणा प्रश्नों पर ििा थ ि लेखन। C-2.2 • अहहसं ा और जीि-दया के मूल्यों एिं न्याय से जुडी • रूप बदलकर- कविता के ककसी एक • अिुमाि और कल्पिा स-े समूह ििाथ। को समझ सकेंग।े घटना का पद को अनुच्छेद के रूप में • CG-3: • सिंवाद- कविता के पात्रों के संिादों का मासमकथ िणनथ सलखना। िगीकरण करना। • पाठांतगतथ प्रयक्ु त व्याकरणणक C-3.2 ककया गया है। • पिंक्तत स े पिंक्तत-समलती जुलती पंक्क्तयों स े बबदं ओु ं से अिगत होते हुए उनका • कर्वता की रचिा: संिादात्मक और समलान। • CG-4: िावषक प्रयोग करने में समिथ िणनथ ात्मक शैली की विशषे ताओं • आपकी बात- समूह ििाथ। C-4.1 हो सकेंगे। को पहिानकर सलखना। • निणयि करें- तकथ प्रस्तुतत • सुिी क ािी- लोककिा पठन • CG-5: • पुिरावनृत- सज्ञं ा ि िेद अभ्यास। • पाठांतगतथ प्रयक्ु त नए शब्दों स े • आज की प ेली- पहेली का उत्तर खोजना। C-5.2 पररथित होते हुए उनका प्रयोग • खोजबीि के शलए- QR कोड/सलकं से ‘हंस कर सकेंग।े ककसका’ कहानी की िीडडयो देखना। 2. तीि प्रस्तुत लोककिा • कारक– िाक्यों में उथित स्िान पर • कहानी को ध्यानपूिकथ सनु कर • CG-1: • मेरी समझ स-े समूह ििाथ। बुद्धधमाि तीव्र बुद्थध, कारक प्रयोग कर सलखना। उसके मुख्य बबदं ओु ं की पहिान • पिंक्ततयों पर चचा-ि अि थ ििाथ ि लेखन। C-1.1, (लोककिा) सूक्ष्म दृक्टट और • वातयािंि के शलए एक िब्द- पाठ में और सारांश प्रस्तुत करने में • शमलकर करें शमलाि- िाक्यों का अि थ स े C-1.3 तकथशक्क्त के आए िाक्यांशों के सलए एक शब्द समि थ होंगे। समलान। महत्त्ि को छााँटकर सलखना। • सोच र्वचार के शलए- पाठ आधाररत प्रश्नों प्रस्तुत करती है, • िब्द से जुड़े िब्द – ‘बुद्थध’ शब्द • पररिेश के सूक्ष्म अिलोकन और • CG-2: के उत्तर लेखन। जहााँ छोटे-छोटे के पयाथय और उसस े संबंथधत शब्दों साक्ष्यों के आधार पर ताककथक C-2.1, • अिुमाि और कल्पिा स-े समूह ििाथ संकेतों के आधार की सूिी बनाना। तनटकष",
    "7|Mathematics": "Directorate of Education, GNCT of Delhi Annual Syllabus Class-VII (2026-27) Subject: Mathematics Book Chapter No. Content Curricular Goals and Competencies Learning Outcomes Suggested Activities and Name Part-I Chapter – 1 A Lakh Varieties, CG-1 The learner will be able to: • The \"Lakh\" Step Count: Students Large Land of Tens, Of Understands numbers and sets of numbers (Whole • solve problems estimate the number of steps they take from Numbers Crores and Crores, numbers, Fractions, Integers, and Rational numbers) involving large numbers the school gate to their classroom and use Around Us Exact and looks for patterns, and appreciates relationships by applying appropriate \"Pattern Boxes\" to calculate how many Approximate Value, between numbers. operations (addition, days of school it would take to reach one Patterns in Products, subtraction, lakh (1,00,000) steps. Did You Ever C-1.1 Develops a sense for and an ability to manipulate multiplication and • Matchstick Digit Swap: Using used Wonder…? (e.g., read, write, form, compare, estimate, and apply division) matchsticks or drawing lines on slates, operations) large whole numbers of up to 10 digits and students represent a 5-digit number (like expresses them in scientific notation using exponents 63,890) and compete to create the largest and powers. possible number by moving only two C-1.2 Discovers, identifies, and explores patterns in sticks. Part-I Chapter – 2 Simple Expressions, numbers and describes rules for their formation (e.g., The learner will be able to: • Favorite Number \"Expression Arithmetic Reading and prime numbers, powers of 3, etc.) and explain relations • Identify and forms Challenge\": Each student picks a \"favorite Expressions Evaluating Complex between different patterns. arithmetic expressions number\" and competes to write the most Expressions C-1.3 Explores and understands sets of numbers such using the four basic diverse arithmetic expressions (using +, -, as whole numbers, fractions, integers, and rational operations (+, −, ×, ÷) to ×, ÷) that evaluate to that number within numbers, and their properties. represent real-life two minutes. C-1.4 Represents rational numbers in decimal form as situations. • Expression Engineer! (The 4-Fours an extension of the Indian system of numeration `past • Evaluate complex Game): Using exactly four 4’s and any the decimal point’. expressions correctly by arithmetic operations or brackets, students C-1.5 Explores the idea of percentage and apply it i",
    "7|Science": "DIRECTORATE OF EDUCATION, GNCT of Delhi ANNUAL SYLLABUS (2026-27) CLASS: 7, SUBJECT: SCIENCE BOOK: CURIOSITY Science Education aims to achieve Scientific understanding of the natural and physical world; Capacities for scientific inquiry; Understanding the evolution of scientific knowledge; Interdisciplinary understanding between science and other curricular areas; Understanding of the relationship between Science, Technology and, Society; Scientific temper and Creativity. The present syllabus has been designed around seven broad themes viz. Food; Materials; The World of the Living; How Things Work; Moving Things, People and Ideas; Natural Phenomenon and Natural Resources. In the Middle Stage, Science is taught using integrated approach. This integrated approach develops fundamental capacities related to the disciplines of Biology, Chemistry, Physics, and Earth Science while the use of connections across them helps students appreciate the interrelations between these subjects and make sense of their observations and experiences. At all Stages, along with conceptual understanding, the capacities of scientific inquiry are developed as age appropriate. These concepts and capacities are chosen both from a disciplinary perspective and in terms of what is useful and necessary in their everyday lives. Students thereby understand the world around them with increasing depth, explore scientific questions at different levels through discussion and experimentation, and learn to communicate this understanding in different ways. The Learning Standards (Curricular Goals and Competencies) for Science as an integrated curricular area, in alignment with the National Curriculum Framework 2023 are as follows: 1 Curricular Competencies Curricular Competencies Goals Goals C-1.1 Classifies matter based on observable C-2.1 Describes one-dimensional motion physical (solid, liquid, gas, shape, volume, (uniform, non-uniform, horizontal, vertical) using density, transparent, opaque, translucent, physical measurements (position, speed, and magnetic, non-magnetic, conducting, non- changes in speed) through mathematical and conducting) and chemical (pure, impure; acid, diagrammatic representations base; metal, non-metal; element, compound) characteristics C-2.2 Describes how electricity works through manipulating different elements in simple circuits CG-2: CG-1: C-1.2 Describes changes in matter (physical and and demonstrates the heating and magnetic chemical) and uses particulate nature",
    "7|Social Science": "Directorate of Education, GNCT of Delhi ANNUAL SYLLABUS SESSION: 2026-2027 SUBJECT: SOCIAL SCIENCE CLASS-VII (Middle Stage) TEXTBOOK-Exploring Society: India and Beyond Part I Chapter No. Curricular Goal (CG) Competency(C) Learning Outcome Suggestive Activities and Name (as per NCF-SE-2023) (as per NCF –SE-2023) CG-6: Understands the C-6.2: Identifies the  Identifies major physical  Facilitate a classroom discussion on the use Chapter 1: spatial distribution of distribution of resources features of India. and significance of key resources in India. Geographical resources (from local to such as water, agriculture,  Locate the key geographical  Conduct map-based activities to enhance Diversity of global), their raw materials, and services features of India on political geographical understanding. India conservation, the across geographies. and physical outline map of  Assign a project to explore different food interdependence between India. preservation techniques practiced across natural phenomena and  Explains how resource various regions of the country. human life, and their distribution affects human environmental and other life. implications CG-6: Understands the C-6.1: Explains key natural  Explains key elements of  Maintain a daily record of weather Chapter 2 spatial distribution of phenomena such as climate, weather. conditions for one month and calculate Understanding resources (from local to weather, ocean cycles, soil  Describe the impact of averages for temperature, rainfall, and wind the Weather global), their formation, the flow of rivers, weather on daily life and speed. conservation, the and how they are spatially environment.  Prepare and present (individually or in interdependence between distributed. groups) on the topic: “How does weather natural phenomena and impact our daily life?” human life, and their  Engage in pair discussions on the usefulness environmental and other of weather predictions and present the implications findings in class. CG-7: Appreciates the C-7.2: Discovers the  Describes climatic regions  Develop a group presentation on disasters Chapter 3 importance and meaning topographical diversity of of India and their influence discussed in the chapter, highlighting their Climates of of being Indian the Indian landmass – from on vegetation and lifestyle. natural and human causes, along with India (Bharatiya) by the semi-arid zone in the  Explains the factors preventive and safety measures. understanding (a) In",
    "8|English": "Annual Syllabus: Session : 2026-27 Class: VIII Subject : English Textbook - THEME ACTIVITIES (Listening, GRAMMAR & LITERARY CURRICULAR LEARNING POORVI Speaking and Exploration) WRITING SKILLS DEVICES GOALS/ OUTCOMES Lesson/Poem COMPETENCIES Lesson 1 - Wisdom, wit Listening – Students listen to the Grammar – CG-3 Students: The Wit and humour transcript and - Adjectives: Exercises Students develop the that Won help resolve Fill the blanks in the given based on use of adjectives. capacity for effective Participate in Hearts misundersta sentences by selecting the correct communication using small ndings and options Sound Words – Words language skills for discussions restore used to indicate the sound description, analysis, about the relationships Number the events of the story in produced e.g. murmur, and response. importance of the correct order of occurrence. sighed, mumble, gasped wit, empathy (Let us Listen - page 12) etc. C-3.1 and wisdom. Listens critically and Importance Speaking – raises probing of empathy, Students work in pairs and mark Compound Words - questions about social clear the intonation in the given When two or more words experiences communicati questions. They take turns to are combined to create a on and practice by saying them aloud new word with a distinct C-3.2 Use newly emotional with the correct intonation. meaning. Practice Writes different kinds learnt intelligence exercises based on it. of letters and essays in vocabulary in human Using ‘Question Words’ like, appropriate style and while speaking interactions. ‘What’, ‘Why’, ‘When’, ‘How’, registers for different and writing ‘Where’, and ‘Who’, to make Tenses & Clauses (Main media for different correct words. some questions. and Subordinate) - audiences and purposes (Let us Speak - page 13,14) Practice exercises based on it. Exploration – Students read and enjoy the Limericks and create one on their your own. Visit the library and read a story Writing Skills – of their choice. Share its theme Narrative Essay written and the interesting parts of the on a personal experience story with the classmates and or an imagined experience Understand the teacher. e.g. A Lesson in importance Responsibility empathy, Make a list of the stories (of wit, communication humour, and wisdom) that they have read and each student shall read out at least one new story from the list. (Let us Explore - page 16) Poem 1 – Humorous, Listening – Students listen to the Grammar – Rhyme CG-3 Students: A Concrete l",
    "8|Hindi": "शिक्षा निदेिालय, राष्ट्रीय राजधािी क्षेत्र, ददल्ली वार्षकि पाठ्यक्रम (2026-27) कक्षा: 8, र्वषय: द दिं ी क्र (मल् ार) र्वषयवस्तु व्याकरण और रचिात्मक अधधगम उद्देश्य पाठ्यचयाि लक्ष्य सुझावात्मक गनतर्वधध/क्रक्रयाकलाप . पाठ का लेखि एविं दक्षताए ँ सिं िाम, र्वधा, . रचनयता 1. स्वदेश प्रस्तुत कववता • भाषा की बात • भावानुकूल सस्वर वािन CG-1: C-1.1, • मेरी समझ से - समूह में ििा ा (कववता) बहुत ही -स्वदेश से जुडे शब्द में सक्षम होंगे। C-1.3, C-1.5 • ममलकर करें ममलान – कववता की गयाप्रसाद -ववराम चिह्न (पुनराववृ ि) • देश-प्रेम की भावना को पंक्क्तयों का सही अर्थ ा या संदभ ा से प्रभावशाली शुक्ल -‘है’ पहले आने से आत्मसात कर सकेंगे। ममलान ढंग से देश- ‘सनेही’ लयात्मकता • देश-प्रेम के महत्त्व को CG-2: C-2.2, • पंक्क्तयों पर ििाा – पंक्क्तयों पर समूह- प्रेम की -समानार्थी शब्द अमभव्यक्त कर सकेंगे। C-2.3 ििा ा और लेखन भावना जागतृ (पुनराववृ ि) • कववता का सार अपने • सोि-वविार के मलए – कववता पर करती है। • संज्ञा एवं उसके भेद शब्दों में मलख सकेंगे। आधाररत प्रश्नों के उिर का लेखन (पुनराववृ ि) • पाठांतगता प्रयुक्त नये CG-3: C-3.2 • अनुमान और कल्पना से – समूह-ििाा • ववशेषण एवं भेद शब्दों से पररचित होते और लेखन (पुनराववृ ि) हुए उनका प्रयोग कर • कववता का शीषका – एक पंक्क्त को • कववता की रिना – तुक सकेंगे। CG-4: C-4.2 िुनकर नया शीषका देना ममलाना और उसके • पाठांतगता प्रयुक्त • आपकी बात – ‘स्वदेश-प्रेम’ को दशााते प्रभाव पर ििाा व्याकरणणक बबदं ओु ं से चित्रों पर ननशान लगाना • आपकी कववता – देश- अवगत होते हुए उनका CG-5: C-5.1, • हमारे अस्त्र-शस्त्र प्रेम के वविार पर भावषक प्रयोग करने में C-5.2 • अपनी भाषा अपने गीत कववता का ववस्तार समर्थ ा हो सकेंगे। • नतरंगा झंडा – कब प्रसन्न और कब उदास • झरोखे से • साझी समझ • खोजबीन के मलए 2. दो गौरैया प्रस्तुत कहानी • सवना ाम एवं उसके भेद • सस्वर वािन में सक्षम CG-1: C-1.1, • मेरी समझ से - समूह में ििाा (कहानी) में दो गौरैया (पुनराववृ ि) होंगे। C-1.3 • ममलकर करें ममलान – पाठाधाररत वाक्यों भीष्म के माध्यम से • कहने का ढंग/ किया • कहानी का सार अपने का सही अर्थों से ममलान साहनी यह दशााया ववशेषण और उसके भेद शब्दों में मलख सकेंगे। • पंक्क्तयों पर ििाा - समूह में ििाा और गया है कक (पुनराववृ ि) • ववद्यार्थी सभी जीवों के CG-2: C-2.3 लेखन छोटी-सी जीव – रेखांककत किया प्रनत प्रेम की • सोि-वविार के मलए – पाठ पर आधाररत की िहिहाहट ववशेषणों से वाक्य- आवश्यकता को समझकर प्रश्नों के उिरों का लेखन से व्यक्क्त का ननमााण उसे अपने व्यवहार में CG-3: C-3.1, • अनुमान और कल्पना से – कल्पना एवं कठोर हृदय • बदली कहानी – कहानी अपना सकेंगे। C-3.2 ववश्लेषण भी वपघल का अंत बदल देने पर • ववद्यार्थी पशु-पक्षक्षयों की • संवाद और अमभनय – दी गई क्स्र्थनतयों जाता है। बदली हुई कहानी का सुरक्षा के प",
    "8|Mathematics": "DIRECTORATE OF EDUCATION, GNCT of Delhi ANNUAL SYLLABUS CLASS: VIII (2026-2027) SUBJECT: MATHEMATICS For Term I, refer to class VIII Mathematics NCERT textbook, Part I Curricular Goal & Curricular Suggestive Learning Chapter Name Content Suggestive Activities Competency Outcomes Chapter 1 Introduction, Square CG-1 The learner :  Ask students to stand in Numbers, Cubic Understands numbers and sets of numbers  identifies and differentiates the form of square and A SQUARE AND A Numbers, A Pinch of (Whole numbers, Fractions, Integers, and square numbers and cubic cube for any given CUBE History Rational numbers) looks for patterns, and numbers number appreciates relationships between  identifies patterns in  Ask them to find cube numbers. square numbers and cubic root and square root y C-1.1 Develops a sense for and an ability numbers and relates them counting sides to manipulate (e.g., read, write, form, with odd numbers compare, estimate, and apply operations)  find square roots and cube large whole numbers of up to 10 digits and roots of numbers expresses them in scientific notation using Chapter 2 Experiencing the Power The learner :  Express using exponent exponents and powers. Play, Exponential  Uses laws of exponents  your age in seconds POWER PLAY Notation and C-1.3 Explores and understands sets of  Express numbers in  population & area of Operations, The Other numbers such as whole numbers, standard form your country Side of Powers, Powers fractions, integers, and rational numbers,  solve problem based on  number of red blood of 10, Did You Ever and their properties. exponents and powers cells in human body Wonder?, A Pinch of C-1.4 Represents rational numbers in History decimal form as an extension of the Indian system of numeration `past the decimal point’. Chapter 3 Reema’s Curiosity, The learner :  Analyze notion of base C-1.5 Explores the idea of percentage and Some Early Number  Collects knowledge about used in different number apply it in solving problems. A STORY OF Systems, The Idea of a origin of numbers systems NUMBERS Base, Place Value C-1.6 Explores and applies fractions (both  Identifies different number  Card games to identify Representation as ratios and in decimal form) in daily life systems across the globe numbers in different situations  Applies mathematical number systems operations on different CG-2 number systems Understands the concepts of variable, Chapter 4 Rectangles and Squares, The learner :  Identify dif",
    "8|Science": "DIRECTORATE OF EDUCATION, GNCT of Delhi ANNUAL SYLLABUS (2026-27) CLASS: 8, SUBJECT: SCIENCE BOOK: CURIOSITY Science Education aims to achieve Scientific understanding of the natural and physical world; Capacities for scientific inquiry; Understanding the evolution of scientific knowledge; Interdisciplinary understanding between science and other curricular areas; Understanding of the relationship between Science, Technology and, Society; Scientific temper and Creativity. The present syllabus has been designed around seven broad themes viz. Food; Materials; The World of the Living; How Things Work; Moving Things, People and Ideas; Natural Phenomenon and Natural Resources. In the Middle Stage, Science is taught using integrated approach. This integrated approach develops fundamental capacities related to the disciplines of Biology, Chemistry, Physics, and Earth Science while the use of connections across them helps students appreciate the interrelations between these subjects and make sense of their observations and experiences. At all Stages, along with conceptual understanding, the capacities of scientific inquiry are developed as age appropriate. These concepts and capacities are chosen both from a disciplinary perspective and in terms of what is useful and necessary in their everyday lives. Students thereby understand the world around them with increasing depth, explore scientific questions at different levels through discussion and experimentation, and learn to communicate this understanding in different ways. The Learning Standards (Curricular Goals and Competencies) for Science as an integrated curricular area, in alignment with the National Curriculum Framework 2023 are as follows: 1 Curricular Competencies Curricular Competencies Goals Goals C-1.1 Classifies matter based on observable C-2.1 Describes one-dimensional motion physical (solid, liquid, gas, shape, volume, (uniform, non-uniform, horizontal, vertical) using density, transparent, opaque, translucent, physical measurements (position, speed, and magnetic, non-magnetic, conducting, non- changes in speed) through mathematical and conducting) and chemical (pure, impure; acid, diagrammatic representations base; metal, non-metal; element, compound) characteristics C-2.2 Describes how electricity works through manipulating different elements in simple circuits CG-2: CG-1: C-1.2 Describes changes in matter (physical and and demonstrates the heating and magnetic chemical) and uses particulate nature",
    "9|English": "Annual Syllabus English Language and Literature (CodeNo.184) Class IX (2025-26) Textbook- Supplementary Reading Skills, Writing Skills & Beehive Reader - Grammar Moments PROSE PROSE READING SKILL Ch 1. The Fun Ch1. The Lost 1. Discursive passage (400-450 They Had Child words) 2. Case based Factual passage (with Ch 2. The Sound Ch 2. The visual input/statistical data/ chart of Music adventures of etc.200-250 words) Toto Ch 3.The Multiple Choice Questions / Objective Little Girl Ch 3. Iswaran the Type Questions will be asked to assess Storyteller inference, analysis, interpretation, Ch 4. A Truly evaluation and vocabulary Beautiful Mind Ch 4. In the kingdom of WRITING SKILL Ch 5.The Snake fools and the Mirror 1. Descriptive Paragraph (word limit 100- 120 words) on a person/event/situation POEMS based on visual or verbal cue/s. 2. Diary Entry/ Story Writing on a P1. The Road Not given title/cue in 100-120 words. taken GRAMMAR:- P2.Wind 1. Tenses P3.Rain on The 2. Modals Roof 3. Subject – verb concord 4. Determiners P4.The Lake Isle 5. Reported speech ● Commands and requests of Innisfree ● Statements ● Questions Accurate use of spelling, punctuation and grammar will be assessed through Gap Filling/ Editing/ Transformation exercises based on these Grammar items. WORDS AND EXPRESSION – I (Workbook for class IX) --- Units 1 to 5 Note: Teachers are advised to: i. Encourage interaction among peers, students and teachers through activities such as Role play, discussion, group work etc. ii. Reduce teacher-talking time and keep it to the minimum. iii. Take up questions for discussion to encourage pupils to participate and to express their ideas and defend their views, and Follow the Speaking and Listening activities given in the NCERT books. Note: Completion of the above syllabus by 06th September 2025 Mid– Term Examination Textbook- Supplementary Reading Skills, Writing Skills & Grammar Beehive Reader- Moments PROSE PROSE READING SKILLS Ch 6. My Ch 5. The 1. Discursive passage (400-450 words) Childhood Happy Prince 2. Case based Factual passage (with visual input/statistical data/ chart etc.200- Ch 7. Reach For Ch 6.The Last 250words) The Top Leaf Multiple Choice Questions / Objective Ch 8. Ch 7. A House Type Questions to assess inference, Kathmandu is not a Home analysis, interpretation, evaluation and vocabulary. Ch 9. If I were Ch 8.The Beggar You WRITINGSKILL POEMS 1. Descriptive Paragraph (word limit 100- 120 words) on a person/ event/ situation P 5. A Legend ba",
    "9|Hindi": "वािष%क पाठ्य,म, स/ : 2025-26 क6ा : 9, िवषय: िहंदी (अ), कोड 002 ि\"ितज भाग -1 कृितका भाग-1 -यावहा1रक -याकरण एवं रचना8मक लेखन ग= खंड : 1. फणीSर नाथ रेण-ु -यावहा1रक -याकरण 1. $ेमचदं - इस जल $लय म V • शXद िनमाYण: उपसग,Y $:यय दो बैल/ क1 कथा • शXद िनमाYण: समास एवं भदे • अथY क1 ^ि_ स ेवा`य भदे 2. राह7ल सांकृ:यायन- =हासा क1 ओर • अलंकार: शXदालंकार: अन$ु ास, यमक, aेष 3.@यामाचरण दबु े- उपभोFावाद क1 संHकृित रचना8मक लेखन • संकेत िबंदओु ंके आधार पर समसामियक एवं eयवहाfरक का-य खंड : जीवन स ेजड़ु े िवषय/ पर अनhु छेद लेखन (लगभग 120 9. कबीर- शXद/ म)V सािखयाँ एव ंसबद • पl लेखन :औपचाfरक पl एवं अनौपचाfरक पl लगभग 100 शXद/ म)V 10. ललQद- • लघकु था लेखन (लगभग 100 शXद/ म)V वाख • ई-मले लेखन (लगभग 100 शXद/ म)V 11. रसखान- • संवाद लेखन (लगभग 80 शXद/ म)V सवैये • सचू ना लेखन (लगभग 80 शXद/ म)V • अपिठत/पिठत गQांश एवं काeयांश पर िचतं न uमता एव ं अिभeयिF कौशलपरक बह7िवक=पीय $v/ का अwयास • 6 िसतंबर 2025 तक उपयIुJ पाठ्यMम को पूरा कर िलया जाए। पुनराविृ Q मRयाविध परी\"ा ि\"ितज भाग-1 कृितका भाग-1 -यावहा1रक -याकरण एवं रचना8मक लेखन ग= खंड: 2. मदृ लु ा गग-Y -यावहा1रक -याकरण 4. जािबर ह7सैन- मरे े संग क1 औरतV • शXद िनमाYण : उपसग,Y $:यय क1 पनु राविृ† साँवल ेसपन/ क1 याद • शXद िनमाYण: समास एवं भदे क1 पनु राविृ† 3. जगदीश च(cid:129)‚ माथरु - • अथY क1 ^ि_ स ेवा`य भदे क1 पनु राविृ† 6. हfरशकं र परसाई- रीढ़ क1 हड्डी $ेमचदं के फटे जतू े • अलंकार क1 पनु राविृ†:- शXदालंकार : अन$ु ास, यमक, aेष क1 पनु राविृ† 7. महादवे ी वमाY- मरे े बचपन के िदन रचना8मक लेखन का-य खंड : • संकेत िबंदओु ंके आधार पर समसामियक एवं eयवहाfरक जीवन 12. माखनलाल चतवु |दी- स ेजड़ु े िवषय/ पर अनhु छेद लेखन का अwयास (लगभग 120 कैदी और कोिकला शXद/ म)V • पl लेखन : औपचाfरक पl एवं अनौपचाfरक पl का अwयास 13. सिुमlानंदन पंत- (लगभग 100 शXद/ म)V }ाम ~ी • लघकु था लेखन का अwयास (लगभग 100 शXद/ म)V 15. सव|Sरदयाल स`सेना- • ई-मले लेखन का अwयास (लगभग 100 शXद/ म)V मघे आए • संवाद लेखन का अwयास (लगभग 80 शXद/ म)V • सचू ना लेखन का अwयास (लगभग 80 शXद/ म)V 17. राजेश जोशी- • अपिठत/पिठत गQांश एव ंकाeयांश पर िचतं न uमता एव ं बhच ेकाम पर जा रह ेह € अिभeयिF कौशलपरक बह7िवक=पीय $v/ का अwयास • समUत पाठ्यMम को 31 जनवरी 2026 तक पूरा कर िलया जाए। • वािषIक परी\"ा मX हटाए गए पाठ अथवा पाठ के अंश] को छोड़कर समUत पाठ्यMम से `a पूछे जाएगँ े। समUत पाठ्यMम कc पुनराविृ Q वािषIक परी\"ा नोट- सी.बी.एस.ई. के नवीनतम (सg 2025-26) िनदjशानुसार िनkनिलिखत पाठ] से `a नहl पूछे जाएगँ े:- ि\"ितज भाग-1 ग= खंड: • चपला दवे ी- नाना साहब क1 पlु ी दवे ी मनै ा को भHम कर िदया गया (परू ा पाठ), • हजारी $साद ि‡वेदी- एक कु†ा और एक मनै ा (परू ा पाठ) पाठ्यMम सबं ंधी अिधक जानकारी हेतु ि\"ितज भाग-1 का-य खंड: सी.बी.एस.ई. का पाठ्यMम िव",
    "9|Mathematics": "Annual Syllabus (2025-26) Class – IX Subject: Mathematics (Code: 041) Course Structure Units Unit Name Marks I Number Systems 10 II Algebra 20 III Coordinate Geometry 04 IV Geometry 27 V Mensuration 13 VI Statistics 06 Total 80 Internal Assessment 20 Grand Total 100 Chapter No. & Name Competencies Chapter 1 : Number Systems  Review of representation of natural numbers, integers and rational The learner: numbers on the number line. Rational numbers as recurring/ terminating decimals. Operations on real numbers.  Develops a deeper  Examples of non-recurring/non-terminating decimals. Existence of understanding of non-rational numbers (irrational numbers) such as √2, √3 and their numbers, including the representation on the number line. Explaining that every real number set of real numbers and is represented by a unique point on the number line and conversely, viz. its properties. every point on the number line represents a unique real number.  Definition of nth root of a real number.  Recognizes and  Rationalization (with precise meaning) of real numbers of the type appropriately uses (cid:2869) and (cid:2869) (and their combinations) where x and y are powers and (cid:3028)(cid:2878)(cid:3029)√(cid:3051) √(cid:3051)(cid:2878)√(cid:3052) exponents. natural number and a and b are integers.  Recall of laws of exponents with integral powers. Rational  Computes powers and exponents with positive real bases (to be done by particular cases, roots and applies them allowing learner to arrive at the general laws. to solve problems. Chapter 2 : Polynomials  Definition of a polynomial in one variable with examples and The learner: counter examples. Coefficients of a polynomial, terms of a  Learns the art of polynomial and zero polynomial. factoring polynomials.  Degree of a polynomial.  Constant, linear, quadratic and cubic polynomials. Monomials, binomials, trinomials. Factors and multiples.  Zeroes of a polynomial.  Motivate and State the Remainder Theorem with examples.  Statement and proof of the Factor Theorem.  Factorization of ax2 + bx + c, a ≠ 0 where a, b and c are real 1 numbers and of cubic polynomials using the Factor Theorem.  Recall of algebraic expressions and identities. Verification of identities: (x + y + z )2 = x2 + y2 + z2 + 2xy + 2yz + 2zx (x ± y)3 = x3 ± y3 ± 3xy(x ± y) x3 ± y3 = (x ± y)(x2∓xy + y2) x3 + y3 + z3 – 3xyz = (x + y + z) (x2 + y2 + z2 – xy – yz – zx) and their use in factorization of polynomials. Chapter 3: Coordinate Ge",
    "9|Science": "ANNUAL SYLLABUS (2025-26) CLASS-9, SUBJECT: SCIENCE (086) Unit No. Unit Marks I Matter - Its Nature and Behaviour 25 II Organization in the Living World 22 III Motion, Force and Work 27 IV Food; Food Production 06 Total 80 Internal assessment 20 Grand Total 100 Content UNIT-I Matter-Nature and Behaviour Chapter -1:Matter in our surroundings Definition of Matter; Particulate nature of matter; States of matter: Solid, liquid and gas and their Characteristics,change of state – melting (Absorption of heat), freezing, evaporation (Cooling by evaporation), Condensation, Sublimation. Practical: Determine the melting point of ice and boiling point of water. Chapter-2: Is Matter Around Us Pure Elements, compound and mixtures. Heterogeneous and homogeneous mixtures, colloids and suspensions. Physical and chemical changes (excluding separating the components of a mixture). Practical : Preparation of a) A true solution of common salt, sugar and alum. b) A suspension of soil, chalk powder and fine sand in water. c) A colloidal solution of starch in water and egg albumin/ milk in water and distinction between these on the basis of • transparency • filtration criterion • stability Practical: Preparation of a) Mixture and b) A Compound, using iron filings and Sulphur powder and distinction between these on the basis of – i) appearance i.e. homogeneity and heterogeneity ii) behavior towards a magnet iii) behavior towards Carbon disulphide as a solvent iv) effect of heat Practical: Performing the following reactions and classifying them as physical or chemical changes: a) Iron with Copper Sulphate solution in water b) Burning of magnesium ribbon in air c) Zinc with dilute Sulphuric Acid d) Heating of Copper Sulphate Crystals e) Sodium Sulphate with Barium Chloride in the form of their Solution in water. UNIT-II -Organization in the Living World: Chapter-5:The Fundamental Unit of Life Cell as a basic unit of life; Prokaryotic and Eukaryotic cells, multicellular organisms, cell membrane and cell wall, cell organelles and cell inclusions; chloroplast, mitochondria, vacuoles, endoplasmic reticulum, Golgi apparatus; nucleus, chromosomes – basic structure, number. Practical : Preparation of stained temporary mounts of a) Onion peel ; b) Human Cheek Cells and to record observations and draw their labeled diagrams. Page 1 Chapter- 6: Tissues Structure and functions of animal and plant tissues (only four types of tissues in animals, Meristematic and Permanent tissues in plants) Prac",
    "9|Social Science": "SESSION: 2025-26 ANNUAL COURSE STRUCTURE CLASS: IX Subject: SOCIAL SCIENCE (SUB Code: 087) No. Book Marks I India and the Contemporary World – I 18+ 2(Map Pointing) =20 II Contemporary India – I 17 + 3(Map Pointing) =20 III Democratic Politics – I 20 IV Economics 20 Total 80 Internal Assessment 20 Grand Total 100 Book Chapter No and Name Learning Outcome India and the Chapter-1: The French The students will be able to Contemporary Revolution  Infer how the French Revolution had an impact on the European countries in the World – I making of nation states in Europe and elsewhere.  Illustrate that, the quest for imperialism triggered the First World War.  Examine various sources to address imbalances that may lead to revolutions. India and the Chapter-5: Pastoralists in The students will be able to Contemporary the Modern world  Examine the situations that have created nomadic societies highlighting the key factors World – I (To be assessed in Periodic played by the climatic conditions and Assessment/ Mid Term topography. Exam only)  Analyse varying patterns of developments within pastoral societies in different places in India.  Comprehend the impact of colonialism on Pastoralists in India and Africa. Democratic Chapter-1: The students will be able to Politics – I What is Democracy? Why  Examine the concept structural components Democracy? of democracy and its forms/ features.  Compare and Contrast working of democracies of India and North Korea and infer on their differences and significance in each country.  Analyse and infer on the different historical processes and forces that have contributed for the promotion of democracy Democratic Chapter-2: The students will be able to Politics – I Constitutional Design  Discuss and describe the situation that led to creation of Indian Constitution  Enumerate the essential features that need to be kept in mind while drafting a constitution.  Examine the guiding values that created the Indian constitution  Comprehend the roles and responsibilities as citizens of India. Contemporary Chapter-1: India - Size and The students will be able to India – I Location  Examine how the location of an area impacts its climate and time with reference to longitude and latitude.  Explore and analyses the trading and cultural relationships of India with its neighbouring countries.  Evaluate the situation & reasons that made 82.50 E longitude as Time meridian of India.  Examine how location of India enables its positio",
}

def get_syllabus(test_class: str, subject: str) -> str:
    """Get NCERT syllabus for given class and subject."""
    # Extract class number from "Class 9A", "Class 10B" etc
    import re as _re
    m = _re.search(r'(\d+)', test_class)
    if not m:
        return ""
    cls_num = m.group(1)
    # Normalize subject
    subj_map = {
        "mathematics": "Mathematics", "maths": "Mathematics", "math": "Mathematics",
        "science": "Science", "english": "English", "hindi": "Hindi",
        "social science": "Social Science", "social studies": "Social Science",
        "history": "Social Science", "geography": "Social Science",
        "physics": "Physics", "chemistry": "Chemistry", "biology": "Biology",
        "computer science": "Computer Science",
    }
    subj_norm = subj_map.get(subject.lower().strip(), subject.strip())
    key = f"{cls_num}|{subj_norm}"
    return NCERT_SYLLABUS.get(key, "")


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


async def generate_mcq(lesson_text, image_b64, count, test_class, subject, language, difficulty, api_key, system_msg, selected_topic: str = '') -> str:
    diff_map = {
        1: "Easy — direct recall of facts and definitions from NCERT.",
        2: "Medium — application of concepts and formulas.",
        3: "Hard — higher order thinking, analysis and multi-step problems.",
    }
    diff_desc = diff_map.get(int(difficulty), diff_map[2])
    topic_line = f" Topic: {selected_topic}." if selected_topic else ""

    # Subject-specific hints
    subject_hints = {
        "Mathematics": "Include calculation-based, theorem-based, and formula-based options.",
        "Science": "Include concept-based, experiment-based, and application questions.",
        "Physics": "Include formula-based and numerical MCQs.",
        "Chemistry": "Include reaction-based, property-based, and equation MCQs.",
        "Biology": "Include process-based, structure-based, and function MCQs.",
        "English": "Include vocabulary, grammar, and comprehension MCQs.",
        "Hindi": "Include व्याकरण, शब्दार्थ, और पठन बोध MCQs।",
        "Social Science": "Include event-based, geography-based, and civics MCQs.",
        "History": "Include date-based, person-based, and event MCQs.",
        "Geography": "Include map-based, climate, and resource MCQs.",
        "Computer Science": "Include programming, concept, and application MCQs.",
    }
    hint = subject_hints.get(subject, "")

    lesson_line = ""
    if lesson_text:
        lesson_line = f"\n\nBase questions on this lesson:\n{lesson_text}"
    elif image_b64:
        lesson_line = "\n\nBase questions on the lesson content in the attached image."

    prompt = (
        f"Create exactly {count} CBSE standard MCQ questions for Class {test_class} {subject}.\n"
        f"Difficulty: {diff_desc}\n"
        f"Language: {language}\n"
        f"{topic_line} {hint}\n\n"
        "Rules:\n"
        "1. All questions must be from the specified topic only.\n"
        "2. Each question must have exactly 4 options, only 1 correct.\n"
        "3. All options must be plausible, no obviously wrong answers.\n"
        "4. Follow CBSE board exam standard and style.\n\n"
        "Return ONLY valid JSON (no markdown):\n"
        '{"questions":[{"q":"question text","options":["A","B","C","D"],"answer":0}]}'
        "\nThe answer field is the index (0,1,2,3) of the correct option."
        f"{lesson_line}"
    )
    return prompt, system_msg



async def generate_subjective(lesson_text, image_b64, test_class, subject, language, api_key, system_msg, selected_topic: str = '') -> str:
    topic_line = f" Topic: {selected_topic}." if selected_topic else ""
    
    # Subject-specific instruction hints
    subject_hints = {
        "Mathematics": "Include numerical problems, proofs, and calculations.",
        "Science": "Include diagram-based questions, experiments, and concept explanations.",
        "Physics": "Include numerical problems, derivations, and law-based questions.",
        "Chemistry": "Include equations, reactions, and property-based questions.",
        "Biology": "Include diagram labeling, life processes, and definition questions.",
        "English": "Include comprehension, grammar, and writing-based questions.",
        "Hindi": "Include गद्यांश, व्याकरण, और लेखन आधारित प्रश्न।",
        "Social Science": "Include map-based, timeline, and cause-effect questions.",
        "History": "Include event-based, cause-effect, and significance questions.",
        "Geography": "Include map-based, climate, and resource questions.",
        "Computer Science": "Include code snippets, definitions, and application questions.",
    }
    hint = subject_hints.get(subject, "Include definition, application, and analytical questions.")
    
    lesson_line = ""
    if lesson_text:
        lesson_line = f"\n\nBase questions on this lesson content:\n{lesson_text}"
    elif image_b64:
        lesson_line = "\n\nBase questions on the lesson content in the attached image."

    prompt = (
        f"Create a 20 marks CBSE standard subjective question paper for Class {test_class} {subject}.\n"
        f"{topic_line}\n"
        f"Language: {language}\n"
        f"{hint}\n\n"
        "Question distribution (CBSE pattern):\n"
        "- Section A: 4 questions x 1 mark (Very Short Answer — 1-2 lines)\n"
        "- Section B: 4 questions x 2 marks (Short Answer — 3-5 lines)\n"
        "- Section C: 2 questions x 4 marks (Long Answer — detailed)\n\n"
        "Rules:\n"
        "1. All questions must be from the specified topic only.\n"
        "2. Questions must match CBSE board exam style and difficulty.\n"
        "3. Section A: definitions, state theorems, one-word answers.\n"
        "4. Section B: explain concepts, short calculations, examples.\n"
        "5. Section C: detailed proofs, long explanations, complex problems.\n\n"
        "Return ONLY valid JSON (no markdown, no extra text):\n"
        '{"questions":['
        '{"q":"question text","marks":1,"section":"A","expected_answer":"model answer","keywords":["k1","k2"]},'
        '{"q":"question text","marks":2,"section":"B","expected_answer":"model answer","keywords":["k1","k2"]},'
        '{"q":"question text","marks":4,"section":"C","expected_answer":"detailed model answer","keywords":["k1","k2","k3"]}'
        ']}\n'
        "IMPORTANT: Return exactly 4 questions with marks=1 section=A, 4 questions with marks=2 section=B, 2 questions with marks=4 section=C."
        f"{lesson_line}"
    )
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


async def call_claude(prompt: str, system_msg: str) -> str:
    """Claude API for high-quality CBSE question generation."""
    import httpx
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise Exception("ANTHROPIC_API_KEY not configured")
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 8000,
                "system": system_msg,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


async def generate_questions_llm(
    lesson_text, image_b64, count, test_class, subject,
    language="English", difficulty=2, test_type="mcq", selected_topic=""
) -> List[dict]:
    gemini_key = os.environ.get('GEMINI_API_KEY', '')
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
    system_msg = (
        f"You are a Senior CBSE Paper Setter for {subject}, Class {test_class}. "
        "Create high-quality academic questions strictly following the NCERT curriculum. "
        "Always return ONLY valid JSON with no markdown, no commentary, no code fences."
    )

    if test_type == "subjective":
        prompt, system_msg = await generate_subjective(lesson_text, image_b64, test_class, subject, language, gemini_key, system_msg, selected_topic=selected_topic)
    else:
        prompt, system_msg = await generate_mcq(lesson_text, image_b64, count, test_class, subject, language, difficulty, gemini_key, system_msg, selected_topic=selected_topic)

    text = None

    # ── Try Claude first (best quality) ─────────────────
    if anthropic_key:
        try:
            # Claude doesn't support image in this flow, use text only
            claude_prompt = prompt
            if image_b64:
                claude_prompt = prompt + f"\n\n[Note: Lesson image was provided. Generate questions based on the topic and syllabus context above.]"
            text = await call_claude(claude_prompt, system_msg)
            logger.info("Questions generated via Claude (primary)")
        except Exception as e:
            logger.warning(f"Claude failed: {e}. Trying Gemini...")
            text = None

    # ── Gemini fallback (supports images) ───────────────
    if text is None and gemini_key:
        try:
            chat = LlmChat(api_key=gemini_key, session_id=f"gen-{uuid.uuid4()}", system_message=system_msg)\
                .with_model("gemini", "gemini-2.0-flash").with_params(max_tokens=8000)
            if image_b64:
                cleaned_img = re.sub(r"^data:image/[^;]+;base64,", "", image_b64).strip()
                msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=cleaned_img)])
            else:
                msg = UserMessage(text=prompt)
            resp = await chat.send_message(msg)
            text = resp if isinstance(resp, str) else str(resp)
            logger.info("Questions generated via Gemini fallback")
        except Exception as e:
            logger.warning(f"Gemini failed: {e}. Trying Groq...")
            text = None

    # ── Groq last resort ─────────────────────────────────
    if text is None:
        try:
            groq_prompt = prompt
            if image_b64:
                groq_prompt = prompt.replace(
                    "\nChapter content is in the attached image.",
                    f"\nGenerate questions based on standard {subject} Class {test_class} NCERT curriculum."
                )
            text = await call_groq(groq_prompt, system_msg)
            logger.info("Questions generated via Groq last resort")
        except Exception as e:
            logger.exception("All AI providers failed")
            raise HTTPException(502, f"All AI providers failed. Please try again.")


# ────────────────────────── ROUTES ──────────────────────────

@api_router.get("/topics")
async def get_topics_api(test_class: str, subject: str):
    """Get chapter/topic list for a given class and subject."""
    topics = get_topics(test_class, subject)
    return {"topics": topics}

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
        test_type=test_type, selected_topic=body.selected_topic or '',
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
        "selected_topic": body.selected_topic or "",
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
