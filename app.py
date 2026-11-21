import os
import re
import json
import requests
import threading
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "WhatsApp_DEMo_ToKen_786")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "sohaibriaz201@gmail.com")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
# Use the verified Resend sender on rapidnextech.com (better deliverability than resend.dev)
FROM_EMAIL = os.environ.get("FROM_EMAIL", "RapidNexTech <notifications@rapidnextech.com>")

conversation_store = {}
scheduler = BackgroundScheduler()
scheduler.start()

# ---------------------------------------------------------------------------
# DEMO CLINIC: Dubai aesthetic / skin / laser clinic (GCC market)
# Matches the example clinic used on rapidnextech.com/clinics
# ---------------------------------------------------------------------------
CLINIC_NAME = "Lumière Aesthetic Clinic"
CLINIC_NAME_AR = "عيادة لوميير للتجميل"
CLINIC_LOCATION = "Jumeirah, Dubai"
CLINIC_LOCATION_AR = "جميرا، دبي"
COORDINATOR_NAME = "Sara"
COORDINATOR_NAME_AR = "سارة"
CLINIC_HOURS = "Saturday to Thursday 10 AM – 9 PM, Friday 2 PM – 9 PM"

# ---------------------------------------------------------------------------
# LANGUAGE MIRRORING — the model mirrors the patient's language.
# ---------------------------------------------------------------------------
LANGUAGE_RULES = """
LANGUAGE MIRRORING — CRITICAL:
- Detect the language of EACH patient message and reply in the SAME language.
- If the patient writes in English, reply in clean, natural English.
- If the patient writes in Arabic, reply in natural, warm Arabic written in Arabic script — the friendly, simple Arabic a Dubai clinic coordinator uses on WhatsApp (light Gulf / "white" Arabic that every Arab patient understands). Not stiff classical Arabic, not heavy slang.
- If the patient writes Arabic in Latin letters (Arabizi, e.g. "kam si3r el botox?"), reply in simple Arabic script.
- If the patient switches language mid-conversation, switch with them.
- Use Western digits (0-9) for prices and times in both languages, and write currency as AED / درهم.
- Match their tone: formal patient -> polite and respectful; casual patient -> warm and friendly, always professional.
- Arabic example: "أكيد! البوتوكس متوفر عندنا. أي منطقة تفكرين فيها؟ 😊"
- English example: "Yes, of course! We offer Botox. Which area were you considering? 😊"
- Keep it WhatsApp-natural in BOTH languages: short, warm, human. Never robotic, never a wall of text.
"""

SYSTEM_PROMPT = f"""You are {COORDINATOR_NAME} ({COORDINATOR_NAME_AR}), a patient care coordinator at {CLINIC_NAME}, a premium aesthetic, skin & laser clinic in {CLINIC_LOCATION}, UAE.

YOUR GOAL: Answer patients' questions using ONLY the clinic information below, and guide interested patients toward a consultation. The clinic's front desk confirms every appointment — you collect the request, you never confirm a time yourself.

PERSONALITY: Warm, confident, knowledgeable. You speak like a trusted friend who happens to be a skincare expert. Never robotic. Never pushy. Never salesy.

RESPONSE LENGTH — THIS IS CRITICAL:
- Maximum 2 short sentences per reply. Non-negotiable.
- Never list multiple treatments in one message.
- Never explain and ask a question in the same message — pick one.
- Think WhatsApp chat, not email. Short. Conversational. Human.

TONE:
- Warm, modern and approachable — not stiff or overly formal.
- Use the patient's name sparingly — once or twice in a whole conversation at most.

GREETING RULE — CRITICAL:
- The clinic already greeted the patient. NEVER greet again ("Hello", "Hi", "مرحبا", "أهلا", "السلام عليكم") — not even when the patient tells you their name. Just acknowledge warmly and continue ("Thanks! ..." / "شكراً! ...").
- If the patient greets you with "السلام عليكم", reply "وعليكم السلام" briefly and continue — this is the only exception.

CONVERSATION RULES:
- Never just answer and stop. Always end with ONE relevant follow-up question.
- Your follow-up question must be something the PATIENT can answer: their concern, the area, whether it's their first time, or whether they'd like a consultation. NEVER ask clinical questions only a doctor can answer (number of sessions, dosage, which treatment suits their skin).
- When a patient asks something clinical ("how many sessions?", "which is best for me?", "what will my case cost exactly?"), explain it depends on their skin and is decided by the doctor at a consultation — then offer to request one.
- Ask ONE qualifying question before giving full pricing (e.g. "Which area were you considering?").
- If the patient hesitates, build trust: experienced, DHA-licensed doctors, approved products, natural results, personalised plans.
- When the patient shows interest, move naturally toward a consultation: "A quick consultation with our doctor would be the best next step — shall I have our team confirm a slot for you?"

CLINIC INFORMATION (never invent anything beyond this):
- Location: {CLINIC_LOCATION} (free parking available).
- Opening hours: {CLINIC_HOURS}.
- Consultation with the doctor: AED 300, deducted from the treatment if the patient goes ahead.
- Payment: cash and all major cards. Tabby instalments available on packages.

TREATMENTS & PRICING (share AFTER one qualifying question; ranges only, the doctor confirms the final price):
- Botox: AED 1,200 – 2,500 depending on area
- Dermal Fillers: AED 1,800 – 3,000 per syringe
- Laser Hair Removal: AED 300 – 1,500 per session (varies by area)
- HydraFacial: AED 450 – 900 per session
- Skin Boosters (e.g. Profhilo): AED 1,800 – 2,500 per session
- Chemical Peels: AED 500 – 1,200 per session
- PRP (Hair & Skin): AED 800 – 1,500 per session
- Microneedling: AED 600 – 1,200 per session
- Acne / Acne-Scar Treatment: AED 600 – 1,500 per session

MICRO-PERSUASION (use naturally, never forcefully):
- "Our doctors customise every treatment plan — no two skins are the same."
- "This is one of our most requested treatments right now."
- "It's a quick procedure — many patients come in on their lunch break."
- "All treatments are done by DHA-licensed doctors using approved products."

URGENT / AFTER-TREATMENT CONCERNS — ALWAYS FIRST:
- If a patient describes a problem after a treatment (strong pain, swelling that keeps getting worse, skin turning white, grey or blue after filler, blurred vision, fever, signs of infection) or any medical emergency: stay calm, tell them this needs attention right away, ask them to call the clinic now, and if it's severe (vision changes, difficulty breathing, severe pain) to call 998 (UAE ambulance) or go to the nearest emergency department. Tell them you've alerted the medical team. Do NOT diagnose and do NOT give treatment advice.

BOOKING: When the patient is ready, DO NOT send any link. Say something natural like:
"Perfect — I'll have our team confirm a slot for you and message you the available timings. May I take your name?"
(Arabic: "تمام! راح أخلي الفريق يأكد لك موعد ويرسل لك الأوقات المتاحة. ممكن اسمك الكريم؟")
The booking is always confirmed by "our team".

{LANGUAGE_RULES}

IDENTITY: If asked whether you are AI or a bot, say warmly: "I'm an AI assistant for {CLINIC_NAME} — all consultations and treatments are with our licensed doctors." (Arabic: "أنا مساعدة ذكية تابعة لـ{CLINIC_NAME_AR} — وكل الاستشارات والعلاجات تكون مع أطبائنا المرخّصين.")
Never diagnose a condition. For any specific skin concern, recommend a consultation with the doctor.
"""

# ---------------------------------------------------------------------------
# Welcome + buttons (buttons stay English: fixed tap targets, max 20 chars)
# ---------------------------------------------------------------------------
WELCOME_FRAMING = (
    "👋 *Imagine a patient messaging your clinic at 11 PM, asking about Botox or laser...*\n\n"
    "This is how RapidNexTech's AI receptionist handles that conversation — it replies instantly, "
    "in English or Arabic, answers questions from the clinic's own information, and passes the "
    "booking request to the front desk. 24/7.\n\n"
    "*Message below as if you were a patient — in English or Arabic — and watch how it replies.* 👇\n\n"
    "تخيّل مريض يراسل عيادتك الساعة 11 بالليل. جرّب تكتب كأنك مريض، بالعربي أو بالإنجليزي 👇"
)

CLINIC_FIRST_MESSAGE = (
    f"Welcome to *{CLINIC_NAME}, {CLINIC_LOCATION}* 🌸\n"
    f"أهلاً وسهلاً في *{CLINIC_NAME_AR}* 🌸\n\n"
    f"I'm {COORDINATOR_NAME}. How can I help you today?\n"
    f"معك {COORDINATOR_NAME_AR}، كيف أقدر أساعدك؟"
)

# Shown ONCE after a booking request completes — breaks the demo "fourth wall"
DEMO_REVEAL_MESSAGE = (
    "— — — — —\n\n"
    "👀 *That was a live demo.*\n\n"
    "Sohaib here, founder of *RapidNexTech*. What you just saw is how this would handle "
    "*your* clinic's WhatsApp enquiries — replying instantly in English or Arabic, answering "
    "questions, and passing every booking request to your front desk, 24/7.\n\n"
    "Here's what happens next:\n"
    "1️⃣ I'll message you within 24 hours to understand your clinic's setup.\n"
    "2️⃣ A quick 15-minute call where I show you how it works on *your* WhatsApp number.\n"
    "3️⃣ If it's a fit, a 14-day free pilot — no card, no contract.\n\n"
    "Just reply *DEMO* and I'll take it from there. 🚀"
)

WELCOME_BUTTONS = [
    {"id": "menu_treatments", "title": "✨ Our Treatments"},
    {"id": "menu_pricing", "title": "💰 See Pricing"},
    {"id": "menu_book", "title": "📅 Book Consultation"},
]

TREATMENTS_TEXT_EN = (
    "Here are some of our most requested treatments:\n\n"
    "💉 Botox\n"
    "✨ Dermal Fillers\n"
    "🔆 Laser Hair Removal\n"
    "💧 HydraFacial\n"
    "🌟 Skin Boosters (Profhilo)\n"
    "🧖 Chemical Peels\n"
    "💫 PRP (Hair & Skin)\n"
    "🌿 Acne & Acne-Scar Treatment\n\n"
    "Which one would you like to know more about?"
)

TREATMENTS_TEXT_AR = (
    "هذي من أكثر العلاجات المطلوبة عندنا:\n\n"
    "💉 بوتوكس\n"
    "✨ فيلر\n"
    "🔆 إزالة الشعر بالليزر\n"
    "💧 هيدرافيشل\n"
    "🌟 معززات البشرة (بروفايلو)\n"
    "🧖 التقشير الكيميائي\n"
    "💫 البلازما (للشعر والبشرة)\n"
    "🌿 علاج حب الشباب وآثاره\n\n"
    "أي علاج حابة تعرفين عنه أكثر؟"
)

PRICING_TEXT_EN = (
    "Quick pricing overview (AED):\n\n"
    "💉 Botox — 1,200–2,500\n"
    "✨ Fillers — 1,800–3,000 / syringe\n"
    "🔆 Laser Hair Removal — 300–1,500 / session\n"
    "💧 HydraFacial — 450–900\n"
    "🌟 Skin Boosters — 1,800–2,500\n"
    "💫 PRP — 800–1,500\n\n"
    "The exact price depends on your skin and the area. Shall I have our team set up a quick consultation for you?"
)

PRICING_TEXT_AR = (
    "نظرة سريعة على الأسعار (درهم):\n\n"
    "💉 بوتوكس — 1,200–2,500\n"
    "✨ فيلر — 1,800–3,000 للحقنة\n"
    "🔆 إزالة الشعر بالليزر — 300–1,500 للجلسة\n"
    "💧 هيدرافيشل — 450–900\n"
    "🌟 معززات البشرة — 1,800–2,500\n"
    "💫 البلازما — 800–1,500\n\n"
    "السعر النهائي يعتمد على البشرة والمنطقة. تحبين أخلي الفريق يرتب لك استشارة سريعة؟"
)


# ---------------------------------------------------------------------------
# Language detection for the FIXED strings (the AI mirrors language itself)
# ---------------------------------------------------------------------------
ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
ARABIZI_MARKERS = {
    "kam", "kem", "si3r", "se3r", "s3r", "3ndkom", "3indkom", "andkom", "abi", "abgha", "abga",
    "ana", "inta", "enta", "inti", "enti", "shlonik", "shlonich", "shlon", "wain", "wen", "mata",
    "yalla", "inshallah", "mashallah", "habibi", "habibti", "ma3", "7ag", "7aq", "mumkin", "momken",
    "ahlan", "marhaba", "shukran", "zain", "zen", "tamam", "ay", "eh", "la2",
}


def detect_arabic(text):
    """True if the patient wrote in Arabic script or Arabizi."""
    if not text:
        return False
    if ARABIC_RE.search(text):
        return True
    words = [w.strip("?.!,").lower() for w in text.split()]
    hits = sum(1 for w in words if w in ARABIZI_MARKERS or re.search(r"[a-z][2375][a-z]", w))
    return hits >= 2 or (hits >= 1 and len(words) <= 3)


def t(session, en, ar):
    """Pick the English or Arabic version of a fixed string."""
    return ar if session.get("arabic_mode") else en


# ---------------------------------------------------------------------------
# Follow-ups
# ---------------------------------------------------------------------------
def get_followup_message(session):
    booking_sent = session.get("booking_sent", False)
    msg_count = len(session.get("history", [])) // 2

    if booking_sent:
        return t(session,
                 "Just checking — did our team's message reach you okay? We're ready to confirm your slot whenever you are 😊",
                 "حبيت أتأكد — وصلتك رسالة الفريق؟ جاهزين نأكد موعدك متى ما ناسبك 😊")
    if msg_count <= 2:
        return t(session,
                 f"Still here if you have any questions about {CLINIC_NAME} — happy to help whenever you're ready 😊",
                 "موجودة إذا عندك أي سؤال — حاضرين متى ما كنتِ جاهزة 😊")
    if msg_count <= 5:
        return t(session,
                 "Any other questions about our treatments or pricing? I'm here whenever you're ready to take the next step 😊",
                 "عندك أي سؤال ثاني عن العلاجات أو الأسعار؟ أنا موجودة 😊")
    return t(session,
             "It looks like you were close to booking — would you like me to have our team confirm a slot now? 😊",
             "يبين إنك قريبة تحجزين — تحبين أخلي الفريق يأكد لك موعد الحين؟ 😊")


def check_and_send_followup(from_number, scheduled_at):
    session = conversation_store.get(from_number)
    if not session:
        return
    if session.get("last_user_message_time", 0) > scheduled_at:
        print(f"Skipping follow-up for {from_number} — user replied")
        return
    if session.get("booking_stage") in ("done", "hot_lead"):
        return
    now = datetime.now(timezone.utc).timestamp()
    if now - session.get("last_followup_time", 0) < 600:
        print(f"Skipping follow-up for {from_number} — too soon")
        return
    send_text_message(from_number, get_followup_message(session))
    session["last_followup_time"] = now
    print(f"Follow-up sent to {from_number}")


def schedule_followup_after_bot_message(from_number):
    """Schedule a 5-minute follow-up after a bot message."""
    now = datetime.now(timezone.utc).timestamp()
    scheduler.add_job(
        check_and_send_followup,
        "date",
        run_date=datetime.fromtimestamp(now + 300, tz=timezone.utc),
        args=[from_number, now],
        id=f"followup_{from_number}_{int(now)}",
        replace_existing=False,
    )
    print(f"Follow-up scheduled for {from_number} in 5 min")


# ---------------------------------------------------------------------------
# Email (Resend)
# ---------------------------------------------------------------------------
def _send_email_async(subject, text):
    def _send():
        try:
            if not RESEND_API_KEY or not NOTIFY_EMAIL:
                print("Email notification not configured")
                return
            r = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={"from": FROM_EMAIL, "to": [NOTIFY_EMAIL], "subject": subject, "text": text},
                timeout=20,
            )
            print(f"Email sent: {r.status_code} {r.text}")
        except Exception as e:
            print(f"Email failed: {e}")

    th = threading.Thread(target=_send)
    th.daemon = True
    th.start()


def format_transcript(session, limit=12):
    lines = []
    for m in session.get("history", [])[-limit:]:
        who = "Patient" if m["role"] == "user" else COORDINATOR_NAME
        lines.append(f"{who}: {m['content']}")
    return "\n".join(lines) if lines else "(no AI conversation yet)"


def send_email_notification(from_number, user_text):
    _send_email_async(
        f"New Demo Lead (GCC clinic demo) — +{from_number}",
        f"New prospect on your RapidNexTech WhatsApp demo (Dubai clinic, EN/AR).\n\n"
        f"WhatsApp Number: +{from_number}\n"
        f"Reply on WhatsApp: https://wa.me/{from_number}\n"
        f"Their Message: {user_text}\n\n"
        f"---\nOpen WhatsApp and message them while they are active.",
    )


def send_booking_lead_email(from_number, session):
    _send_email_async(
        f"✅ BOOKING REQUEST — {session.get('booking_name') or 'Unknown'}",
        f"A demo prospect completed the booking flow.\n\n"
        f"Name: {session.get('booking_name')}\n"
        f"Phone given: {session.get('booking_phone')}\n"
        f"WhatsApp: +{from_number} (https://wa.me/{from_number})\n"
        f"Language: {'Arabic' if session.get('arabic_mode') else 'English'}\n\n"
        f"Conversation:\n{format_transcript(session)}\n",
    )


def send_urgent_email(from_number, session, user_text):
    _send_email_async(
        f"🚨 URGENT — patient reported a concern (+{from_number})",
        f"A patient described a possible complication or urgent concern.\n\n"
        f"WhatsApp: +{from_number} (https://wa.me/{from_number})\n"
        f"Their message: {user_text}\n\n"
        f"Conversation:\n{format_transcript(session)}\n\n"
        f"---\nIn a real clinic this alert goes to the on-call team.",
    )


def send_hot_lead_email(from_number, user_text):
    _send_email_async(
        f"🔥 HOT LEAD — clinic owner replied after demo (+{from_number})",
        f"A prospect completed the demo booking AND replied to the founder reveal.\n"
        f"This is very likely a real clinic owner.\n\n"
        f"WhatsApp: +{from_number} (https://wa.me/{from_number})\n"
        f"Their message: {user_text}\n\n"
        f"---\nMessage them personally now while they're warm.",
    )


# ---------------------------------------------------------------------------
# WhatsApp Cloud API
# ---------------------------------------------------------------------------
def send_text_message(to, message):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        print(f"Send text response: {response.status_code} - {response.text}")
        return response.json()
    except Exception as e:
        print(f"Send text failed: {e}")
        return {}


def send_button_message(to, body_text, buttons):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    button_list = [{"type": "reply", "reply": {"id": b["id"], "title": b["title"]}} for b in buttons]
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {"type": "button", "body": {"text": body_text}, "action": {"buttons": button_list}},
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        print(f"Send button response: {response.status_code} - {response.text}")
        return response.json()
    except Exception as e:
        print(f"Send button failed: {e}")
        return {}


def send_welcome_sequence(to):
    send_text_message(to, WELCOME_FRAMING)
    send_button_message(to, CLINIC_FIRST_MESSAGE, WELCOME_BUTTONS)


def send_booking_prompt(to, session):
    body = t(session, "Would you like to book a consultation?", "تحبين نحجز لك استشارة؟")
    buttons = [
        {"id": "action_book", "title": "📅 Book Now"},
        {"id": "action_more", "title": "💬 Ask a Question"},
    ]
    send_button_message(to, body, buttons)


# ---------------------------------------------------------------------------
# Groq LLM
# ---------------------------------------------------------------------------
def get_groq_response(user_message, conversation_history, arabic=False):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})
    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": messages,
        "max_completion_tokens": 500,
        "temperature": 0.6,
        "reasoning_effort": "low",
        "include_reasoning": False,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"Groq HTTP status: {response.status_code}")
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise ValueError(f"Groq returned no choices: {data}")
        content = (choices[0].get("message", {}).get("content") or "").strip()
        if not content:
            raise ValueError(f"Groq returned empty content: {data}")
        return content
    except requests.exceptions.Timeout:
        print("Groq error: request timed out")
    except requests.exceptions.RequestException as e:
        print(f"Groq HTTP error: {e}")
    except Exception as e:
        print(f"Groq processing error: {e}")

    if arabic:
        return "عذراً، صار خلل بسيط 😅 ممكن تعيدين رسالتك؟ أنا موجودة."
    return "Sorry, I had a brief hiccup 😅 Could you say that again? I'm right here."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_digits(text):
    return (text or "").translate(ARABIC_DIGITS)


def message_has_booking_ask(text):
    """True if a bot message offers to book / confirm a consultation."""
    if not text:
        return False
    low = text.lower()
    en = (
        any(kw in low for kw in [
            "shall i have our team", "shall i book", "book a slot", "confirm a slot",
            "may i have your name", "may i take your name", "set up a quick consultation",
            "set up a consultation", "would you like to book", "would you like me to book",
            "book a consultation", "book your consultation",
        ])
        or ("book" in low and ("consultation" in low or "appointment" in low or "slot" in low))
        or ("would you like" in low and ("consultation" in low or "appointment" in low))
        or ("consultation" in low and ("set up" in low or "arrange" in low or "shall i" in low))
    )
    ar = any(kw in text for kw in [
        "أحجز", "نحجز", "احجز", "موعد", "استشارة", "اسمك", "يأكد", "أأكد", "نأكد", "يرتب",
    ]) and any(q in text for q in ["?", "؟", "تحب", "تبين", "تبغين", "ممكن", "أخلي"])
    return en or ar


def extract_phone(text):
    """Return a phone number if the text looks like one (UAE/GCC/international), else None."""
    if not text:
        return None
    only_digits = re.sub(r"\D", "", normalize_digits(text))
    if 8 <= len(only_digits) <= 15:
        return normalize_digits(text).strip()
    return None


def extract_inline_name(text):
    """Pull a name from 'my name is Sara', 'I'm Ali', 'اسمي سارة', 'انا محمد'."""
    if not text:
        return None
    s = text.strip()
    low = s.lower()
    patterns_en = [
        r"my name is\s+([a-zÀ-ſ\.\s]+)$",
        r"i am\s+([a-zÀ-ſ\.\s]+)$",
        r"i'?m\s+([a-zÀ-ſ\.\s]+)$",
        r"this is\s+([a-zÀ-ſ\.\s]+)$",
        r"name\s*[:\-]?\s*([a-zÀ-ſ\.\s]+)$",
    ]
    for pat in patterns_en:
        m = re.search(pat, low)
        if m:
            span = m.span(1)
            name = s[span[0]:span[1]].strip(" ,.")
            words = name.split()
            if 1 <= len(words) <= 3 and all(w.replace(".", "").isalpha() for w in words):
                return name.title()
    m = re.search(r"(?:اسمي|إسمي|انا|أنا)\s+([؀-ۿ\s]{2,40})", s)
    if m:
        words = m.group(1).strip().split()
        if 1 <= len(words) <= 3:
            return " ".join(words)
    return None


URGENT_MARKERS_EN = [
    "swelling", "swollen", "bruise getting worse", "turning white", "turned white", "blue skin", "grey skin",
    "blurred vision", "blurry vision", "can't see", "cant see", "vision", "severe pain", "very painful",
    "infection", "pus", "fever", "allergic reaction", "can't breathe", "cant breathe", "emergency",
    "bleeding", "lump", "hard lump",
]
URGENT_MARKERS_AR = [
    "تورم", "انتفاخ", "منتفخ", "ألم شديد", "الم شديد", "وجع شديد", "رؤية", "زغللة", "ما أشوف", "ما اشوف",
    "التهاب", "صديد", "حرارة", "حساسية", "ما أقدر أتنفس", "طوارئ", "نزيف", "لونه أبيض", "ازرق", "أزرق",
]


def looks_urgent(text):
    if not text:
        return False
    low = text.lower()
    return any(k in low for k in URGENT_MARKERS_EN) or any(k in text for k in URGENT_MARKERS_AR)


GREETING_PREFIXES = [
    "hello", "hi there", "hi!", "hi,", "hey", "welcome to", "welcome back",
    "مرحبا", "مرحباً", "أهلا", "اهلا", "أهلاً", "هلا", "السلام عليكم",
]


def strip_repeat_greeting(ai_text):
    """Strip a leading re-greeting if the model adds one despite the prompt rule."""
    if not ai_text:
        return ai_text
    stripped = ai_text.lstrip()
    low = stripped.lower()
    if low.startswith("وعليكم السلام"):
        return ai_text
    for g in GREETING_PREFIXES:
        if low.startswith(g):
            for sep in [". ", "! ", "? ", "، ", "؟ ", "\n"]:
                idx = stripped.find(sep)
                if 0 <= idx <= 60:
                    cleaned = stripped[idx + len(sep):].strip()
                    return cleaned if cleaned else ai_text
            break
    return ai_text


ACK_WORDS = {
    "ok", "okay", "okk", "k", "kk", "thanks", "thank", "thankyou", "thx", "ty", "done", "noted",
    "got", "it", "cool", "great", "nice", "good", "perfect", "yes", "alright", "fine", "awesome",
    "شكرا", "شكراً", "مشكورة", "مشكور", "تمام", "اوكي", "أوكي", "طيب", "زين", "ماشي", "حلو", "تسلمين", "يعطيك",
    "العافية", "👍", "🙏", "❤", "❤️", "😊", "ok.", "great.",
}
QUESTION_MARKERS = {
    "how", "what", "when", "where", "why", "which", "can", "do", "does", "is", "are",
    "كم", "متى", "وين", "أين", "كيف", "ليش", "هل", "ايش", "شو", "وش",
}


def is_pure_ack(text):
    """True if the message is just 'ok' / 'thanks' / 'تمام' with no question."""
    if not text:
        return True
    low = text.strip().lower()
    if "?" in low or "؟" in low:
        return False
    tokens = set(re.sub(r"[,.!،]", " ", low).split())
    if tokens & QUESTION_MARKERS:
        return False
    return bool(tokens) and tokens.issubset(ACK_WORDS)


CONFIRM_WORDS = {
    "yes", "yeah", "yep", "sure", "ok", "okay", "please", "definitely", "absolutely",
    "نعم", "ايوه", "إيوه", "ايه", "اي", "أكيد", "اكيد", "تمام", "اوكي", "أوكي", "يلا", "ياليت", "طيب", "زين", "ماشي",
}
CONFIRM_PHRASES = [
    "yes book", "book me", "let's book", "lets book", "yes please", "go ahead", "sounds good",
    "احجزي لي", "احجز لي", "ابي احجز", "أبي أحجز", "ابغى احجز", "أبغى أحجز", "نعم من فضلك", "اكيد ياليت",
]


def is_confirming(text):
    low = text.strip().lower()
    tokens = set(re.sub(r"[,.!،]", " ", low).split())
    return bool(tokens & CONFIRM_WORDS) or any(p in low for p in CONFIRM_PHRASES)


# ---------------------------------------------------------------------------
# Booking flow (name -> phone -> done)
# ---------------------------------------------------------------------------
def start_booking(from_number, session, prefilled_name=None):
    session["booking_sent"] = True
    if prefilled_name:
        session["booking_name"] = prefilled_name
        session["booking_stage"] = "awaiting_phone"
        first = prefilled_name.split()[0]
        send_text_message(from_number, t(
            session,
            f"Thanks {first}! Please share your contact number and our team will send you the available timings.",
            f"شكراً {first}! ممكن رقم التواصل؟ والفريق راح يرسل لك الأوقات المتاحة.",
        ))
        schedule_followup_after_bot_message(from_number)
        return
    session["booking_stage"] = "awaiting_name"
    send_text_message(from_number, t(
        session,
        "Wonderful! To request your slot, may I have your name please?",
        "ممتاز! عشان نطلب لك موعد، ممكن اسمك الكريم؟",
    ))
    schedule_followup_after_bot_message(from_number)


def handle_booking_step(from_number, session, user_text):
    stage = session.get("booking_stage")

    if stage == "awaiting_name":
        extracted = extract_inline_name(user_text)
        name = extracted if extracted else user_text.strip()
        if len(name.split()) > 4:
            name = name.split()[0]
        session["booking_name"] = name
        session["booking_stage"] = "awaiting_phone"
        first = name.split()[0] if name else ""
        send_text_message(from_number, t(
            session,
            f"Thanks{(' ' + first) if first else ''}! Please share your contact number and our team will send you the available timings.",
            f"شكراً{(' ' + first) if first else ''}! ممكن رقم التواصل؟ والفريق راح يرسل لك الأوقات المتاحة.",
        ))
        schedule_followup_after_bot_message(from_number)
        return True

    if stage == "awaiting_phone":
        phone = extract_phone(user_text)
        if not phone:
            send_text_message(from_number, t(
                session,
                "I just need a contact number so our team can send the timings — could you type it here?",
                "بس نحتاج رقم التواصل عشان الفريق يرسل لك الأوقات — ممكن تكتبينه هنا؟",
            ))
            schedule_followup_after_bot_message(from_number)
            return True
        session["booking_phone"] = phone
        session["booking_stage"] = "done"
        first = (session.get("booking_name") or "").split()[0] if session.get("booking_name") else ""
        send_text_message(from_number, t(
            session,
            f"Perfect{(', ' + first) if first else ''}! Your request is noted. ✅\n\n"
            "Our front desk will message you the available timings to confirm your appointment, "
            "and your consultation will be with our doctor, who'll prepare a personalised plan for you.\n\nSee you soon! 🌸",
            f"تمام{(' ' + first) if first else ''}! تم تسجيل طلبك ✅\n\n"
            "فريق الاستقبال راح يرسل لك الأوقات المتاحة لتأكيد الموعد، والاستشارة تكون مع الدكتورة "
            "اللي راح تجهز لك خطة تناسبك.\n\nنشوفك قريب! 🌸",
        ))
        send_booking_lead_email(from_number, session)
        if not session.get("reveal_sent"):
            session["reveal_sent"] = True
            send_text_message(from_number, DEMO_REVEAL_MESSAGE)
        return True

    return False


# ---------------------------------------------------------------------------
# Main message handler
# ---------------------------------------------------------------------------
def new_session():
    return {
        "history": [],
        "notified": False,
        "welcomed": False,
        "last_user_message_time": datetime.now(timezone.utc).timestamp(),
        "last_followup_time": 0,
        "booking_sent": False,
        "arabic_mode": False,
        "booking_stage": None,  # None -> awaiting_name -> awaiting_phone -> done -> hot_lead
        "booking_name": None,
        "booking_phone": None,
        "pending_book_ask": False,
        "reveal_sent": False,
        "urgent_alerted": False,
    }


def remember(session, user_text, ai_response):
    session["history"].append({"role": "user", "content": user_text})
    session["history"].append({"role": "assistant", "content": ai_response})
    if len(session["history"]) > 12:
        session["history"] = session["history"][-12:]


def handle_message(from_number, user_text, button_id=None):
    is_new_user = from_number not in conversation_store
    if is_new_user:
        conversation_store[from_number] = new_session()

    session = conversation_store[from_number]
    session["last_user_message_time"] = datetime.now(timezone.utc).timestamp()

    if user_text:
        session["arabic_mode"] = detect_arabic(user_text)

    if is_new_user and not session["notified"]:
        send_email_notification(from_number, user_text or "Started demo")
        session["notified"] = True

    # First touch: welcome only. The AI conversation starts with the next message.
    if not session["welcomed"]:
        session["welcomed"] = True
        send_welcome_sequence(from_number)
        schedule_followup_after_bot_message(from_number)
        return

    # Buttons
    if button_id:
        if button_id == "menu_treatments":
            send_text_message(from_number, t(session, TREATMENTS_TEXT_EN, TREATMENTS_TEXT_AR))
            schedule_followup_after_bot_message(from_number)
            return
        if button_id == "menu_pricing":
            send_text_message(from_number, t(session, PRICING_TEXT_EN, PRICING_TEXT_AR))
            session["pending_book_ask"] = True
            schedule_followup_after_bot_message(from_number)
            return
        if button_id in ("menu_book", "action_book"):
            if session.get("booking_stage") in (None,):
                start_booking(from_number, session)
            return
        if button_id == "action_more":
            send_text_message(from_number, t(
                session,
                "Of course! What would you like to know — treatments or pricing? I'm right here 😊",
                "أكيد! وش حابة تعرفين — العلاجات ولا الأسعار؟ أنا موجودة 😊",
            ))
            schedule_followup_after_bot_message(from_number)
            return

    if not user_text:
        return

    # Urgent / after-treatment concerns always go to the AI (safety-first prompt)
    # and trigger an alert email, even in the middle of booking.
    if looks_urgent(user_text):
        ai_response = get_groq_response(user_text, session["history"], session.get("arabic_mode"))
        ai_response = strip_repeat_greeting(ai_response)
        remember(session, user_text, ai_response)
        send_text_message(from_number, ai_response)
        if not session.get("urgent_alerted"):
            session["urgent_alerted"] = True
            send_urgent_email(from_number, session, user_text)
        return

    stage = session.get("booking_stage")
    if stage in ("awaiting_name", "awaiting_phone"):
        handle_booking_step(from_number, session, user_text)
        return

    if stage == "done":
        if session.get("reveal_sent") and "demo" in user_text.lower():
            send_text_message(
                from_number,
                "🙌 Perfect — thanks for reaching out! This is Sohaib. "
                "I'll personally message you shortly to set up a quick call. "
                "Mind sharing your *clinic's name* and city so I can prep before we talk?",
            )
            send_hot_lead_email(from_number, user_text)
            session["booking_stage"] = "hot_lead"
            return
        if is_pure_ack(user_text):
            return
        ai_response = strip_repeat_greeting(get_groq_response(user_text, session["history"], session.get("arabic_mode")))
        remember(session, user_text, ai_response)
        send_text_message(from_number, ai_response)
        return

    if stage == "hot_lead":
        if not session.get("hot_lead_detail_sent"):
            session["hot_lead_detail_sent"] = True
            send_text_message(
                from_number,
                "Got it — thank you! 🙏 I'll be in touch very soon to show you "
                "exactly how this works on your own WhatsApp number. Talk soon! — Sohaib",
            )
            send_hot_lead_email(from_number, "Clinic detail: " + user_text)
        return

    # Previous bot turn offered booking and the patient is confirming -> booking flow
    if session.get("pending_book_ask"):
        session["pending_book_ask"] = False
        if is_confirming(user_text) and session.get("booking_stage") is None:
            start_booking(from_number, session, prefilled_name=extract_inline_name(user_text))
            return

    # Open conversation with the AI (language mirroring handled in the prompt)
    ai_response = strip_repeat_greeting(get_groq_response(user_text, session["history"], session.get("arabic_mode")))
    remember(session, user_text, ai_response)
    send_text_message(from_number, ai_response)
    schedule_followup_after_bot_message(from_number)

    ai_asked_to_book = message_has_booking_ask(ai_response)
    session["pending_book_ask"] = ai_asked_to_book

    # Offer booking buttons only on clear intent in the patient's own message
    strong_intent = [
        "book", "appointment", "schedule", "i want to", "i'd like to", "ready to", "sign me up",
        "احجز", "أحجز", "موعد", "ابي", "أبي", "ابغى", "أبغى", "حجز",
    ]
    patient_strong_intent = any(p in user_text.lower() for p in strong_intent)
    if (patient_strong_intent and not session.get("booking_sent")
            and session.get("booking_stage") is None and not ai_asked_to_book):
        send_booking_prompt(from_number, session)


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    print(f"Webhook verify: mode={mode}")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json(silent=True) or {}
    print(f"Incoming: {json.dumps(data)[:2000]}")
    try:
        value = data["entry"][0]["changes"][0]["value"]
        if "messages" not in value:
            return jsonify({"status": "ok"}), 200

        message = value["messages"][0]
        from_number = message["from"]
        msg_type = message["type"]
        print(f"Message from: {from_number}, type: {msg_type}")

        if msg_type == "interactive":
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                handle_message(from_number, "", button_id=interactive["button_reply"]["id"])
                return jsonify({"status": "ok"}), 200

        if msg_type == "text":
            handle_message(from_number, message["text"]["body"].strip())
            return jsonify({"status": "ok"}), 200

        # Voice notes, images, stickers etc. (voice-note support comes later)
        session = conversation_store.get(from_number, {})
        if session.get("arabic_mode"):
            send_text_message(from_number, "حالياً أقدر أرد على الرسائل المكتوبة فقط — ممكن تكتبين سؤالك؟ 😊")
        else:
            send_text_message(from_number, "For now I can only reply to text messages — could you type your question? 😊")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def home():
    return "RapidNexTech WhatsApp Bot (Dubai clinic demo, EN/AR) is running 🚀", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
