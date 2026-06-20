import os
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

conversation_store = {}
scheduler = BackgroundScheduler()
scheduler.start()

ARABIC_LANGUAGE_RULES = """
ARABIC LANGUAGE RULES — CRITICAL:
- If the patient writes in Arabic, respond ONLY in Arabic. Never mix English and Arabic.
- Use Saudi Gulf dialect naturally, not formal Modern Standard Arabic.
- Common Saudi greetings: "هلا" (Hala) for casual, "السلام عليكم" for formal.
- Never use "مرحبا" (Marhaba) — this sounds Lebanese/Syrian, not Saudi.
- Detect the patient's tone: if they write casually, respond casually. If they write formally, respond formally.
- Formal patients (using السلام عليكم, long sentences): Use respectful titles like "حضرتك" or "سيدي/سيدتي". Keep tone polished.
- Casual patients (using هلا, short messages): Match their energy. Be warm and friendly, like a trusted friend.
- Never sound pushy. Arabs value relationship and trust before transaction.
- Example casual response: "هلا! بالتأكيد، عندنا خيارات كثيرة 😊 وش تبي تعرف؟"
- Example formal response: "وعليكم السلام، أهلاً وسهلاً. يسعدني أساعدك. تفضل، وش تحتاج؟"
"""

SYSTEM_PROMPTS = {
    "medspa": """You are Nour, a patient coordinator at Glow Aesthetic Clinic, a premium medical aesthetic clinic in Dubai, UAE.

YOUR GOAL: Guide every patient toward booking a consultation. You are not just answering questions — you are leading a conversation toward a booking.

PERSONALITY: Warm, confident, knowledgeable. You speak like a trusted friend who happens to be an expert. Never robotic. Never salesy.

RESPONSE LENGTH — THIS IS CRITICAL:
- Maximum 2 short sentences per reply. Non-negotiable.
- Never list multiple treatments in one message.
- Never explain and ask a question in the same message — pick one.
- Think WhatsApp chat, not email. Short. Conversational. Human.
- If you have more to say, save it for the next message after they reply.

IMPORTANT: Never introduce yourself or greet the patient. They have already been welcomed. Jump straight into helping them with their inquiry.

CONVERSATION RULES:
- Never just answer and stop. Always end with ONE relevant follow-up question.
- Ask qualifying questions before giving full pricing. Example: "Which area are you considering?" or "Is this your first time trying Botox?"
- Detect intent: price questions = high intent, treat seriously. General questions = educate then qualify.
- If patient hesitates, build trust: mention safety, personalization, natural results, experienced doctors.
- When patient shows interest, transition naturally: "Based on what you're describing, a quick consultation would be the best next step — I can send you the booking link if you're ready."
- Never force a fixed booking sentence. Make it feel like a natural next step.

TREATMENTS & PRICING (share AFTER asking 1 qualifying question):
- Botox: AED 800-1,500 depending on area
- Dermal Fillers: AED 1,500-3,000 per syringe
- HydraFacial: AED 400-700 per session
- Laser Hair Removal: AED 500-1,500 per session
- Skin Boosters (Profhilo, Restylane): AED 1,200-2,500
- PRP Hair & Skin: AED 1,000-2,000
- Chemical Peels: AED 300-600

MICRO-PERSUASION (use naturally, never forcefully):
- "Our doctors customize every treatment plan — no two patients are the same."
- "Most of our patients see results within 48 hours."
- "This is one of our most requested treatments right now."
- "It's a very quick procedure, most patients come in during their lunch break."

BOOKING: When patient is ready, say something natural like:
"Perfect — I'll send you our booking link now. Our team usually confirms within a few hours: https://rapidnextech.com/book/medspa"

LANGUAGE: English by default. """ + ARABIC_LANGUAGE_RULES + """

IDENTITY: You are Nour, patient coordinator at Glow Aesthetic Clinic Dubai. If asked if you are AI, say: "I'm an AI assistant representing Glow Aesthetic Clinic — but all consultations and treatments are with our certified medical team." In Arabic: "أنا مساعد ذكي اصطناعي يمثل العيادة — لكن جميع الاستشارات والعلاجات مع فريقنا الطبي المعتمد."
Never diagnose. Always recommend consultation for specific concerns.""",

    "aesthetic": """You are Layla, a patient care specialist at Elite Skin & Laser Centre, a premium aesthetic clinic in Doha, Qatar.

YOUR GOAL: Guide every patient toward booking a consultation. You are not just answering questions — you are leading a conversation toward a booking.

PERSONALITY: Warm, confident, knowledgeable. You speak like a trusted friend who happens to be an expert. Never robotic. Never salesy.

RESPONSE LENGTH — THIS IS CRITICAL:
- Maximum 2 short sentences per reply. Non-negotiable.
- Never list multiple treatments in one message.
- Never explain and ask a question in the same message — pick one.
- Think WhatsApp chat, not email. Short. Conversational. Human.
- If you have more to say, save it for the next message after they reply.

IMPORTANT: Never introduce yourself or greet the patient. They have already been welcomed. Jump straight into helping them with their inquiry.

CONVERSATION RULES:
- Never just answer and stop. Always end with ONE relevant follow-up question.
- Ask qualifying questions before giving full pricing. Example: "Which concern are you looking to address?" or "Have you had this treatment before?"
- Detect intent: price questions = high intent, treat seriously. General questions = educate then qualify.
- If patient hesitates, build trust: mention safety, personalization, natural results, experienced doctors.
- When patient shows interest, transition naturally: "Based on what you're describing, a quick consultation would really help us understand your goals — I can send the booking link if you'd like."
- Never force a fixed booking sentence. Make it feel like a natural next step.

TREATMENTS & PRICING (share AFTER asking 1 qualifying question):
- Botox: QAR 800-1,500 depending on area
- Dermal Fillers: QAR 1,500-3,000 per syringe
- Laser Hair Removal: QAR 500-1,500 per session
- HydraFacial: QAR 400-800 per session
- Skin Boosters: QAR 1,200-2,500 per session
- Thread Lift: QAR 3,000-6,000
- Ultherapy: QAR 4,000-8,000

MICRO-PERSUASION (use naturally, never forcefully):
- "Our specialists design every plan around your skin type and goals."
- "This treatment has been incredibly popular this season."
- "Most patients are back to their routine the same day."
- "We use only FDA-approved products and protocols."

BOOKING: When patient is ready, say something natural like:
"Great — here's our booking link, our coordinator will confirm your slot within a few hours: https://rapidnextech.com/book/aesthetic"

LANGUAGE: English by default. """ + ARABIC_LANGUAGE_RULES + """

IDENTITY: You are Layla, patient care specialist at Elite Skin & Laser Centre Doha. If asked if you are AI, say: "I'm an AI assistant representing Elite Skin & Laser Centre — all consultations and treatments are with our certified specialists." In Arabic: "أنا مساعد ذكي اصطناعي — جميع الاستشارات والعلاجات مع متخصصينا المعتمدين."
Never diagnose. Always recommend consultation for specific concerns.""",

    "dental": """You are Sara, a patient coordinator at Pearl Dental Clinic, a modern dental practice in Abu Dhabi, UAE.

YOUR GOAL: Guide every patient toward booking an appointment. You are not just answering questions — you are leading a conversation toward a booking.

PERSONALITY: Warm, reassuring, professional. Many patients have dental anxiety — your tone should make them feel safe and comfortable. Never robotic. Never salesy.

RESPONSE LENGTH — THIS IS CRITICAL:
- Maximum 2 short sentences per reply. Non-negotiable.
- Never list multiple treatments in one message.
- Never explain and ask a question in the same message — pick one.
- Think WhatsApp chat, not email. Short. Conversational. Human.
- If you have more to say, save it for the next message after they reply.

IMPORTANT: Never introduce yourself or greet the patient. They have already been welcomed. Jump straight into helping them with their inquiry.

CONVERSATION RULES:
- Never just answer and stop. Always end with ONE relevant follow-up question.
- Ask qualifying questions before giving full pricing. Example: "Is this something you have been thinking about for a while?" or "Are you experiencing any discomfort currently?"
- Detect intent: price questions = high intent, treat seriously. Pain or emergency questions = prioritize urgency and booking immediately.
- If patient hesitates, build trust: mention painless procedures, experienced team, modern equipment.
- When patient shows interest, transition naturally: "It sounds like a consultation would be the perfect first step — I can send you our booking link right now if you'd like."
- Never force a fixed booking sentence. Make it feel like a natural next step.

TREATMENTS & PRICING (share AFTER asking 1 qualifying question):
- Teeth Whitening: AED 800-1,500
- Invisalign: AED 12,000-20,000
- Regular Cleaning & Checkup: AED 300-500
- Dental Veneers: AED 1,500-3,000 per tooth
- Dental Implants: AED 8,000-15,000 per implant
- Root Canal: AED 1,500-3,000
- Emergency Dental: AED 400-800

MICRO-PERSUASION (use naturally, never forcefully):
- "Our procedures are completely painless — most patients are surprised by how comfortable it is."
- "We use the latest technology to make every visit as quick as possible."
- "Invisalign is one of our most popular treatments — patients love that it is invisible."
- "Early treatment always saves time and cost in the long run."

BOOKING: When patient is ready, say something natural like:
"Perfect — here is our booking link, we will confirm your appointment shortly: https://rapidnextech.com/book/dental"

LANGUAGE: English by default. """ + ARABIC_LANGUAGE_RULES + """

IDENTITY: You are Sara, patient coordinator at Pearl Dental Clinic Abu Dhabi. If asked if you are AI, say: "I'm an AI assistant representing Pearl Dental Clinic — all consultations and treatments are with our certified dental team." In Arabic: "أنا مساعد ذكي اصطناعي يمثل العيادة — جميع الاستشارات والعلاجات مع فريقنا الطبي المعتمد."
Never diagnose. Always recommend in-person exam for specific concerns."""
}

WELCOME_BUTTONS = {
    "medspa": [
        {"id": "menu_treatments", "title": "💉 View Treatments"},
        {"id": "menu_pricing", "title": "💰 See Pricing"},
        {"id": "menu_book", "title": "📅 Book Consultation"}
    ],
    "aesthetic": [
        {"id": "menu_treatments", "title": "💉 View Treatments"},
        {"id": "menu_pricing", "title": "💰 See Pricing"},
        {"id": "menu_book", "title": "📅 Book Consultation"}
    ],
    "dental": [
        {"id": "menu_treatments", "title": "🦷 View Treatments"},
        {"id": "menu_pricing", "title": "💰 See Pricing"},
        {"id": "menu_book", "title": "📅 Book Appointment"}
    ]
}

TREATMENTS_TEXT = {
    "medspa": "Our most popular treatments:\n\n💉 Botox\n✨ Dermal Fillers\n💧 HydraFacial\n🔆 Laser Hair Removal\n🌿 Skin Boosters\n💫 PRP\n🧖 Chemical Peels\n\nWhich one interests you most?",
    "aesthetic": "Our most popular treatments:\n\n💉 Botox\n✨ Dermal Fillers\n🔆 Laser Hair Removal\n💧 HydraFacial\n🌿 Skin Boosters\n🧵 Thread Lift\n⚡ Ultherapy\n\nWhich one interests you most?",
    "dental": "Our most popular services:\n\n🦷 Teeth Whitening\n😁 Invisalign\n🔬 Regular Cleaning\n✨ Dental Veneers\n🔩 Dental Implants\n🩺 Root Canal\n🚨 Emergency Dental\n\nWhich one would you like to know more about?"
}

PRICING_TEXT = {
    "medspa": "Quick pricing overview:\n\n💉 Botox — AED 800-1,500\n✨ Fillers — AED 1,500-3,000\n💧 HydraFacial — AED 400-700\n🔆 Laser — AED 500-1,500\n🌿 Skin Boosters — AED 1,200-2,500\n\nPricing varies by treatment plan. Shall I help you book a consultation?",
    "aesthetic": "Quick pricing overview:\n\n💉 Botox — QAR 800-1,500\n✨ Fillers — QAR 1,500-3,000\n🔆 Laser — QAR 500-1,500\n💧 HydraFacial — QAR 400-800\n🌿 Skin Boosters — QAR 1,200-2,500\n🧵 Thread Lift — QAR 3,000-6,000\n\nShall I help you book a consultation to get an exact quote?",
    "dental": "Quick pricing overview:\n\n🦷 Whitening — AED 800-1,500\n😁 Invisalign — AED 12,000-20,000\n🔬 Cleaning — AED 300-500\n✨ Veneers — AED 1,500-3,000/tooth\n🔩 Implants — AED 8,000-15,000\n\nShall I help you book a consultation for an exact assessment?"
}


def is_arabic(text):
    """Check if text contains Arabic characters."""
    return any('\u0600' <= char <= '\u06FF' for char in text)


def get_followup_message(session):
    niche = session.get("niche")
    history = session.get("history", [])
    booking_sent = session.get("booking_sent", False)
    msg_count = len(history) // 2
    in_arabic = session.get("arabic_mode", False)

    if booking_sent:
        if in_arabic:
            return "هلا، تأكدت إن رابط الحجز وصلك؟ فريقنا جاهز يأكد موعدك 😊"
        return "Just checking — did the booking link come through okay? Our team is ready to confirm your slot whenever you are 😊"

    if not niche:
        if in_arabic:
            return "هلا، لو مستعد اختار نوع العيادة وأبدأ أوريك كيف يشتغل 😊"
        return "Still there? Whenever you're ready, just pick a clinic type and I'll show you how it works 😊"

    if msg_count <= 2:
        niche_names = {
            "medspa": "Glow Aesthetic Clinic",
            "aesthetic": "Elite Skin & Laser Centre",
            "dental": "Pearl Dental Clinic"
        }
        name = niche_names.get(niche, "our clinic")
        if in_arabic:
            return f"هلا، أنا هنا لو عندك أي سؤال عن العيادة 😊"
        return f"Still here if you have any questions about {name} — happy to help whenever you're ready 😊"

    if msg_count <= 5:
        if in_arabic:
            return "عندك أسئلة ثانية عن العلاجات أو الأسعار؟ أنا هنا 😊"
        return "Any other questions about our treatments or pricing? I'm here whenever you're ready to take the next step 😊"

    if in_arabic:
        return "يبدو إنك قريب من الحجز — تبي أرسلك رابط الحجز الحين؟ 😊"
    return "It looks like you were close to booking — would you like me to send the booking link now? Takes just a second 😊"


def check_and_send_followup(from_number, scheduled_at):
    session = conversation_store.get(from_number)
    if not session:
        return

    last_user_msg = session.get("last_user_message_time", 0)

    if last_user_msg > scheduled_at:
        print(f"Skipping follow-up for {from_number} — user replied")
        return

    last_followup = session.get("last_followup_time", 0)
    now = datetime.now(timezone.utc).timestamp()
    if now - last_followup < 600:
        print(f"Skipping follow-up for {from_number} — too soon")
        return

    message = get_followup_message(session)
    send_text_message(from_number, message)
    session["last_followup_time"] = now
    print(f"Follow-up sent to {from_number}")


def schedule_followup_after_bot_message(from_number):
    """Schedule a 5-minute follow-up after EVERY bot message."""
    now = datetime.now(timezone.utc).timestamp()
    job_id = f"followup_{from_number}_{int(now)}"
    scheduler.add_job(
        check_and_send_followup,
        'date',
        run_date=datetime.fromtimestamp(now + 300, tz=timezone.utc),
        args=[from_number, now],
        id=job_id,
        replace_existing=False
    )
    print(f"Follow-up scheduled for {from_number} in 5 min")


def send_email_notification(from_number, user_text, niche=None):
    def _send():
        try:
            if not RESEND_API_KEY or not NOTIFY_EMAIL:
                print("Email notification not configured")
                return

            niche_label = {
                "medspa": "Med Spa",
                "aesthetic": "Aesthetic Clinic",
                "dental": "Dental Clinic"
            }.get(niche, "Not selected yet")

            wa_link = f"https://wa.me/{from_number}"

            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": "RapidNexTech Bot <onboarding@resend.dev>",
                    "to": [NOTIFY_EMAIL],
                    "subject": f"New Demo Lead — +{from_number}",
                    "text": f"New prospect on your RapidNexTech WhatsApp demo.\n\nWhatsApp Number: +{from_number}\nReply on WhatsApp: {wa_link}\nNiche Selected: {niche_label}\nTheir Message: {user_text}\n\n---\nOpen WhatsApp and message them now while they are active."
                }
            )
            print(f"Email sent: {response.status_code}")

        except Exception as e:
            print(f"Email notification failed: {e}")

    thread = threading.Thread(target=_send)
    thread.daemon = True
    thread.start()


def send_text_message(to, message):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"Send text response: {response.status_code} - {response.text}")
    return response.json()


def send_button_message(to, body_text, buttons):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    button_list = []
    for btn in buttons:
        button_list.append({
            "type": "reply",
            "reply": {"id": btn["id"], "title": btn["title"]}
        })
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {"buttons": button_list}
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"Send button response: {response.status_code} - {response.text}")
    return response.json()


def send_niche_selector(to, in_arabic=False):
    if in_arabic:
        body = "👋 *تخيل مريض يرسل لعيادتك الساعة 11 بالليل...*\n\nهذا بالضبط كيف يتعامل ذكاء RapidNexTech الاصطناعي مع الاستفسارات — يؤهل المريض، يجاوب أسئلته، ويوجهه للحجز. تلقائياً.\n\n*وش نوع العيادة اللي تبي تجربها كمريض؟*"
    else:
        body = "👋 *Imagine a patient messaging your clinic at 11PM...*\n\nThis is exactly how RapidNexTech's AI handles that conversation — qualifying them, answering their questions, and moving them toward booking. Automatically.\n\n*Which clinic type would you like to experience as a patient?*"

    send_button_message(
        to,
        body,
        [
            {"id": "niche_medspa", "title": "💆 Med Spa"},
            {"id": "niche_aesthetic", "title": "✨ Aesthetic Clinic"},
            {"id": "niche_dental", "title": "🦷 Dental Clinic"}
        ]
    )


def send_welcome_menu(to, niche, in_arabic=False):
    buttons = WELCOME_BUTTONS.get(niche, WELCOME_BUTTONS["medspa"])
    body = "وش تبي تعرف؟" if in_arabic else "What would you like to know?"
    send_button_message(to, body, buttons)


def send_booking_prompt(to, in_arabic=False):
    if in_arabic:
        body = "تبي تحجز موعد؟"
        buttons = [
            {"id": "action_book", "title": "📅 احجز الحين"},
            {"id": "action_more", "title": "💬 عندي أسئلة"}
        ]
    else:
        body = "Would you like to book a consultation?"
        buttons = [
            {"id": "action_book", "title": "📅 Book Now"},
            {"id": "action_more", "title": "💬 Ask More Questions"}
        ]
    send_button_message(to, body, buttons)


def get_groq_response(user_message, niche, conversation_history):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    messages = [{"role": "system", "content": SYSTEM_PROMPTS[niche]}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "max_tokens": 150,
        "temperature": 0.7
    }
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()
    return data["choices"][0]["message"]["content"]


def handle_message(from_number, user_text, button_id=None):
    is_new_user = from_number not in conversation_store

    if is_new_user:
        conversation_store[from_number] = {
            "niche": None,
            "history": [],
            "notified": False,
            "last_user_message_time": datetime.now(timezone.utc).timestamp(),
            "last_followup_time": 0,
            "booking_sent": False,
            "arabic_mode": False
        }

    session = conversation_store[from_number]
    session["last_user_message_time"] = datetime.now(timezone.utc).timestamp()

    # Detect Arabic from user text and update session
    if user_text and is_arabic(user_text):
        session["arabic_mode"] = True

    in_arabic = session.get("arabic_mode", False)

    # Email on first message
    if is_new_user and not session["notified"]:
        send_email_notification(from_number, user_text or "Started demo", niche=None)
        session["notified"] = True

    # Handle button presses
    if button_id:

        if button_id == "niche_medspa":
            session["niche"] = "medspa"
            if in_arabic:
                send_text_message(from_number, "الحين تجرب تجربة *Glow Aesthetic Clinic دبي* 💆\n\nهلا! أنا نور. بماذا أقدر أساعدك اليوم؟")
            else:
                send_text_message(from_number, "You are now experiencing *Glow Aesthetic Clinic Dubai* 💆\n\nHi! I'm Nour. What brings you in today?")
            send_welcome_menu(from_number, "medspa", in_arabic)
            schedule_followup_after_bot_message(from_number)
            return

        elif button_id == "niche_aesthetic":
            session["niche"] = "aesthetic"
            if in_arabic:
                send_text_message(from_number, "الحين تجرب تجربة *Elite Skin & Laser Centre الدوحة* ✨\n\nهلا! أنا ليلى. كيف أقدر أساعدك؟")
            else:
                send_text_message(from_number, "You are now experiencing *Elite Skin & Laser Centre Doha* ✨\n\nHi! I'm Layla. How can I help you today?")
            send_welcome_menu(from_number, "aesthetic", in_arabic)
            schedule_followup_after_bot_message(from_number)
            return

        elif button_id == "niche_dental":
            session["niche"] = "dental"
            if in_arabic:
                send_text_message(from_number, "الحين تجرب تجربة *Pearl Dental Clinic أبوظبي* 🦷\n\nهلا! أنا سارة. بماذا أقدر أساعدك؟")
            else:
                send_text_message(from_number, "You are now experiencing *Pearl Dental Clinic Abu Dhabi* 🦷\n\nHi! I'm Sara. What can I help you with today?")
            send_welcome_menu(from_number, "dental", in_arabic)
            schedule_followup_after_bot_message(from_number)
            return

        elif button_id == "menu_treatments":
            niche = session.get("niche", "medspa")
            text = TREATMENTS_TEXT.get(niche, "We offer a wide range of treatments. Which area are you interested in?")
            send_text_message(from_number, text)
            schedule_followup_after_bot_message(from_number)
            return

        elif button_id == "menu_pricing":
            niche = session.get("niche", "medspa")
            text = PRICING_TEXT.get(niche, "Our pricing varies by treatment. Would you like to book a consultation for an exact quote?")
            send_text_message(from_number, text)
            schedule_followup_after_bot_message(from_number)
            return

        elif button_id == "menu_book":
            niche = session.get("niche", "medspa")
            booking_links = {
                "medspa": "https://rapidnextech.com/book/medspa",
                "aesthetic": "https://rapidnextech.com/book/aesthetic",
                "dental": "https://rapidnextech.com/book/dental"
            }
            link = booking_links.get(niche, "https://rapidnextech.com/contact")
            if in_arabic:
                send_text_message(from_number, f"تفضل رابط الحجز: {link}\n\nفريقنا راح يأكد موعدك خلال ساعات. في شي ثاني أقدر أساعدك فيه؟")
            else:
                send_text_message(from_number, f"Here's your booking link: {link}\n\nOur team will confirm your appointment within a few hours. Is there anything else I can help you with?")
            session["booking_sent"] = True
            schedule_followup_after_bot_message(from_number)
            return

        elif button_id == "action_book":
            niche = session.get("niche", "medspa")
            booking_links = {
                "medspa": "https://rapidnextech.com/book/medspa",
                "aesthetic": "https://rapidnextech.com/book/aesthetic",
                "dental": "https://rapidnextech.com/book/dental"
            }
            link = booking_links.get(niche, "https://rapidnextech.com/contact")
            if in_arabic:
                send_text_message(from_number, f"تفضل رابط الحجز: {link}\n\nفريقنا راح يأكد موعدك خلال ساعات. في شي ثاني أقدر أساعدك فيه؟")
            else:
                send_text_message(from_number, f"Here's your booking link: {link}\n\nOur team will confirm your appointment within a few hours. Is there anything else I can help you with?")
            session["booking_sent"] = True
            schedule_followup_after_bot_message(from_number)
            return

        elif button_id == "action_more":
            if in_arabic:
                send_text_message(from_number, "بالتأكيد! وش تبي تعرف؟ أنا هنا أجاوب أي سؤال عن العلاجات أو الأسعار.")
            else:
                send_text_message(from_number, "Of course! What would you like to know? Happy to answer anything about treatments, pricing, or procedures.")
            schedule_followup_after_bot_message(from_number)
            return

    # No niche selected yet
    if session["niche"] is None:
        send_niche_selector(from_number, in_arabic)
        schedule_followup_after_bot_message(from_number)
        return

    # Email when they start actual conversation
    if len(session["history"]) == 0 and session["niche"]:
        send_email_notification(from_number, user_text, niche=session["niche"])

    # Get AI response
    ai_response = get_groq_response(user_text, session["niche"], session["history"])

    session["history"].append({"role": "user", "content": user_text})
    session["history"].append({"role": "assistant", "content": ai_response})

    if len(session["history"]) > 10:
        session["history"] = session["history"][-10:]

    send_text_message(from_number, ai_response)

    # Track if booking link was sent by AI
    if any(keyword in ai_response.lower() for keyword in [
        "rapidnextech.com/book", "booking link", "confirm your slot",
        "confirm your appointment", "رابط الحجز"
    ]):
        session["booking_sent"] = True

    # Schedule follow-up after EVERY bot message
    schedule_followup_after_bot_message(from_number)

    # Show booking button on intent
    booking_already_sent = session.get("booking_sent", False)

    ai_signals = any(keyword in ai_response.lower() for keyword in [
        "booking link", "book a consultation", "schedule a consultation",
        "send you the link", "ready to book", "book now", "رابط الحجز", "احجز"
    ])

    booking_intent_signals = [
        "book", "appointment", "schedule", "consultation", "reserve",
        "available", "availability", "when can", "how do i", "sign up",
        "interested", "ready", "yes", "sure", "okay", "let's do", "i want",
        "حجز", "موعد", "أبي أحجز", "كيف أحجز", "أبي", "نعم", "زين", "هلا"
    ]
    patient_showing_intent = any(signal in user_text.lower() for signal in booking_intent_signals)

    if (patient_showing_intent or ai_signals) and not booking_already_sent:
        send_booking_prompt(from_number, in_arabic)


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    print(f"Webhook verify: mode={mode}, token={token}")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    print(f"Incoming: {json.dumps(data)}")

    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return jsonify({"status": "ok"}), 200

        message = value["messages"][0]
        from_number = message["from"]
        msg_type = message["type"]

        print(f"Message from: {from_number}, type: {msg_type}")

        if msg_type == "interactive":
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                button_id = interactive["button_reply"]["id"]
                print(f"Button pressed: {button_id}")
                handle_message(from_number, "", button_id=button_id)
                return jsonify({"status": "ok"}), 200

        if msg_type == "text":
            user_text = message["text"]["body"].strip()
            print(f"User text: {user_text}")
            handle_message(from_number, user_text)
            return jsonify({"status": "ok"}), 200

        send_text_message(from_number, "Please send a text message so I can assist you! 😊")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def home():
    return "RapidNexTech WhatsApp Bot is running 🚀", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
