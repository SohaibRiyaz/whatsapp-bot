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

# ---------------------------------------------------------------------------
# LANGUAGE MIRRORING — the model decides, based on the patient's own message.
# Roman Urdu is written in English letters, so a unicode check won't catch it.
# We instruct the model to mirror whatever the patient uses.
# ---------------------------------------------------------------------------
LANGUAGE_RULES = """
LANGUAGE MIRRORING — CRITICAL:
- Detect the language of EACH patient message and reply in the SAME language.
- If the patient writes in English, reply in clean, natural English.
- If the patient writes in Roman Urdu (Urdu written in English letters, e.g. "ap k pas botox available hai? kitne ka hai?"), reply in natural, warm Roman Urdu — the way a real Lahore clinic coordinator would chat on WhatsApp.
- If the patient mixes English and Roman Urdu (very common in Lahore), mirror that same mix naturally.
- NEVER reply in Urdu script (اردو). Always use Roman Urdu (English letters) so it reads naturally on WhatsApp, matching how Lahore clinics actually message.
- Match their tone: formal patient -> polite and respectful ("ji", "aap"); casual patient -> warm and friendly, but always professional.
- Roman Urdu example (casual): "Ji bilkul! Botox available hai. Aap kis area k liye soch rahay hain? 😊"
- Roman Urdu example (polite): "Jee aap behtareen jagah aaye hain. Aap apni skin concern bata dein, main aap ko guide kar deti hoon."
- English example: "Yes, of course! We offer Botox. Which area were you considering? 😊"
- Keep it WhatsApp-natural in BOTH languages: short, warm, human. Never robotic, never a wall of text.
"""

# ---------------------------------------------------------------------------
# SINGLE NICHE: Lahore aesthetic / skin / laser clinic
# ---------------------------------------------------------------------------
CLINIC_NAME = "Lumière Skin & Laser"
CLINIC_LOCATION = "DHA Lahore"
COORDINATOR_NAME = "Hina"

SYSTEM_PROMPT = f"""You are {COORDINATOR_NAME}, a patient care coordinator at {CLINIC_NAME}, a premium aesthetic, skin & laser clinic in {CLINIC_LOCATION}, Pakistan.

YOUR GOAL: Guide every patient toward booking a consultation. You are not just answering questions — you are leading a warm conversation toward a booking.

PERSONALITY: Warm, confident, knowledgeable. You speak like a trusted friend who happens to be a skincare expert. Never robotic. Never pushy. Never salesy.

RESPONSE LENGTH — THIS IS CRITICAL:
- Maximum 2 short sentences per reply. Non-negotiable.
- Never list multiple treatments in one message.
- Never explain and ask a question in the same message — pick one.
- Think WhatsApp chat, not email. Short. Conversational. Human.
- If you have more to say, save it for the next message after they reply.

TONE — IMPORTANT FOR LAHORE:
- Be warm and friendly, like a modern, approachable clinic coordinator — NOT stiff or overly formal.
- Do NOT add "ji" after the patient's name in every message. Using the name occasionally is fine, but "Sohaib ji" on every line sounds old-fashioned and deferential. Sound like a friendly professional in their 20s-30s, not a formal secretary.
- Use the patient's name sparingly — once or twice in a whole conversation at most, not every message.

GREETING RULE — CRITICAL:
- You greet the patient EXACTLY ONCE, at the very start. After that, NEVER greet again.
- NEVER say "Assalam o Alaikum", "Hello", "Hi", or any greeting in the middle of a conversation — not even when the patient tells you their name. When they give their name, simply acknowledge it warmly and continue ("Thanks! ..." / "Shukriya! ...") — do NOT re-greet.

CONVERSATION RULES:
- Never just answer and stop. Always end with ONE relevant follow-up question.
- CRITICAL — your follow-up question must be something the PATIENT can actually answer. NEVER ask the patient clinical questions that only a doctor could answer, such as "how many sessions will you need?", "what dosage is right for you?", or "which treatment is best for your skin?". Those are decisions the doctor makes during consultation. Instead, ask things the patient knows: their concern, the area they want treated, whether it's their first time, or whether they'd like to book a consultation.
- When a patient asks something clinical (e.g. "how many sessions?", "which is best for me?", "what will it cost for my case?"), the correct answer is: it depends on their skin and is decided by the doctor at a consultation — then offer to book one. Do NOT turn that question back onto the patient.
- Ask ONE qualifying question before giving full pricing. Example: "Which area were you considering?" or "Is this your first time getting this treatment?"
- Detect intent: price questions = high intent, treat seriously. General questions = educate briefly, then qualify.
- If the patient hesitates, build trust: mention experienced doctors, safe FDA-approved products, natural results, personalized plans.
- When the patient shows interest, transition naturally toward a consultation: "Based on what you're describing, a quick consultation would be the best next step — shall I have our team confirm a slot for you?"
- Never force a fixed booking sentence. Make it feel like a natural next step.

TREATMENTS & PRICING (share AFTER asking 1 qualifying question; prices in PKR):
- Botox: PKR 25,000 - 60,000 depending on area
- Dermal Fillers: PKR 45,000 - 90,000 per syringe
- Laser Hair Removal: PKR 8,000 - 25,000 per session (varies by area)
- HydraFacial: PKR 12,000 - 22,000 per session
- Carbon Laser / Skin Glow: PKR 10,000 - 18,000 per session
- Chemical Peels: PKR 8,000 - 20,000 per session
- PRP (Hair & Skin): PKR 15,000 - 30,000 per session
- Acne / Acne-Scar Treatment: PKR 10,000 - 25,000 per session
- Microneedling: PKR 12,000 - 20,000 per session

MICRO-PERSUASION (use naturally, never forcefully):
- "Our doctors customize every treatment plan — no two skins are the same."
- "Most of our patients start seeing results within a couple of weeks."
- "This is one of our most requested treatments right now."
- "It's a very quick procedure — most patients are in and out within their lunch break."
- "We only use FDA-approved products and certified doctors."

BOOKING: When the patient is ready, DO NOT send any link. Instead say something natural like:
"Perfect — I'll have our team confirm a slot for you and message you the available timings shortly. May I take your name?"
(In Roman Urdu: "Bilkul! Main team se aap k liye slot confirm karwa deti hoon, timings abhi bhej dete hain. Aap apna naam bata dein?")
The booking is always confirmed by "our team" — never a self-service link.

{LANGUAGE_RULES}

IDENTITY: You are {COORDINATOR_NAME}, patient coordinator at {CLINIC_NAME} {CLINIC_LOCATION}. If asked whether you are AI/a bot, say warmly: "I'm an AI assistant representing {CLINIC_NAME} — but all consultations and treatments are with our certified doctors." (Roman Urdu: "Main {CLINIC_NAME} ka AI assistant hoon — lekin saari consultations aur treatments hamaray certified doctors k saath hoti hain.")
Never diagnose a condition. For any specific skin concern, always recommend an in-clinic consultation with the doctor.
"""

# ---------------------------------------------------------------------------
# Welcome + buttons (buttons always English — they are tap targets, kept consistent)
# ---------------------------------------------------------------------------
WELCOME_FRAMING = (
    "👋 *Imagine a patient messaging your clinic at 11PM, asking about laser or Botox...*\n\n"
    "This is exactly how RapidNexTech's AI handles that conversation — it answers instantly, "
    "qualifies the patient, and moves them toward a booking. Automatically, 24/7.\n\n"
    "*Go ahead — message below as if you were a patient, and watch how it replies.* 👇"
)

CLINIC_FIRST_MESSAGE = (
    f"Assalam o Alaikum! 🌸 Welcome to *{CLINIC_NAME}, {CLINIC_LOCATION}*.\n\n"
    f"I'm {COORDINATOR_NAME}. How can I help you today?"
)

WELCOME_BUTTONS = [
    {"id": "menu_treatments", "title": "✨ Our Treatments"},
    {"id": "menu_pricing", "title": "💰 See Pricing"},
    {"id": "menu_book", "title": "📅 Book Consultation"},
]

TREATMENTS_TEXT = (
    "Here are some of our most requested treatments:\n\n"
    "💉 Botox\n"
    "✨ Dermal Fillers\n"
    "🔆 Laser Hair Removal\n"
    "💧 HydraFacial\n"
    "🌟 Carbon Laser / Skin Glow\n"
    "🧖 Chemical Peels\n"
    "💫 PRP (Hair & Skin)\n"
    "🌿 Acne & Acne-Scar Treatment\n\n"
    "Which one would you like to know more about?"
)

PRICING_TEXT = (
    "Quick pricing overview (PKR):\n\n"
    "💉 Botox — 25,000–60,000\n"
    "✨ Fillers — 45,000–90,000 / syringe\n"
    "🔆 Laser Hair Removal — 8,000–25,000 / session\n"
    "💧 HydraFacial — 12,000–22,000\n"
    "🌟 Carbon Laser — 10,000–18,000\n"
    "💫 PRP — 15,000–30,000\n\n"
    "Exact pricing depends on your skin and the area. Shall I have our team set up a quick consultation for you?"
)


def get_followup_message(session):
    booking_sent = session.get("booking_sent", False)
    history = session.get("history", [])
    msg_count = len(history) // 2
    roman = session.get("roman_urdu_mode", False)

    if booking_sent:
        if roman:
            return "Bas check kar rahi thi — aap ko hamari team ne timings bhej di hain na? Hum aap ka slot confirm karne k liye tayyar hain 😊"
        return "Just checking — did our team's message reach you okay? We're ready to confirm your slot whenever you are 😊"

    if msg_count <= 2:
        if roman:
            return f"Main yahin hoon agar aap k koi aur sawal hon {CLINIC_NAME} k baare mein 😊"
        return f"Still here if you have any questions about {CLINIC_NAME} — happy to help whenever you're ready 😊"

    if msg_count <= 5:
        if roman:
            return "Koi aur sawal treatments ya pricing k baare mein? Main yahin hoon jab aap tayyar hon 😊"
        return "Any other questions about our treatments or pricing? I'm here whenever you're ready to take the next step 😊"

    if roman:
        return "Lagta hai aap booking k kareeb thay — main aap k liye abhi slot confirm karwa doon? 😊"
    return "It looks like you were close to booking — would you like me to have our team confirm a slot now? 😊"


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
    """Schedule a 5-minute follow-up after every bot message."""
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


def send_email_notification(from_number, user_text):
    def _send():
        try:
            if not RESEND_API_KEY or not NOTIFY_EMAIL:
                print("Email notification not configured")
                return
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
                    "text": (
                        f"New prospect on your RapidNexTech WhatsApp demo (Lahore aesthetic).\n\n"
                        f"WhatsApp Number: +{from_number}\n"
                        f"Reply on WhatsApp: {wa_link}\n"
                        f"Their Message: {user_text}\n\n"
                        f"---\nOpen WhatsApp and message them now while they are active."
                    )
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
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
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
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    button_list = [{"type": "reply", "reply": {"id": b["id"], "title": b["title"]}} for b in buttons]
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


def send_welcome_sequence(to):
    """First-touch: framing message, then the clinic's own first message + service buttons."""
    send_text_message(to, WELCOME_FRAMING)
    send_button_message(to, CLINIC_FIRST_MESSAGE, WELCOME_BUTTONS)


def send_booking_prompt(to, roman=False):
    # Body text mirrors language (it's conversation), but BUTTONS are always
    # English — buttons are fixed tap-targets and must look consistent/professional.
    body = "Aap consultation book karna chahenge?" if roman else "Would you like to book a consultation?"
    buttons = [
        {"id": "action_book", "title": "📅 Book Now"},
        {"id": "action_more", "title": "💬 Ask a Question"}
    ]
    send_button_message(to, body, buttons)


def get_groq_response(user_message, conversation_history):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "max_tokens": 200,
        "temperature": 0.7
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        if not content:
            raise ValueError("Empty content from Groq")
        return content
    except Exception as e:
        print(f"Groq error: {e}")
        # Graceful, on-brand fallback so the demo never goes silent.
        if looks_roman_urdu(user_message):
            return "Maazrat, thoda technical issue aa gaya 😅 Aap dobara bata dein, main yahin hoon — ya 'Book Consultation' dabaa dein."
        return "Sorry, I had a brief hiccup 😅 Could you say that again? I'm right here — or tap 'Book Consultation' and our team will reach out."


# ---------------------------------------------------------------------------
# Lightweight Roman Urdu heuristic — ONLY used to pick the language of the
# fixed follow-up / booking-prompt strings (NOT for the AI reply itself,
# which mirrors language on its own via the system prompt).
# ---------------------------------------------------------------------------
ROMAN_URDU_MARKERS = {
    "ap", "aap", "kya", "kia", "hai", "hain", "kitna", "kitnay", "kitne", "krna",
    "karna", "chahiye", "chahye", "mujhe", "mujhay", "nahi", "nhi", "han", "haan",
    "ji", "jee", "acha", "theek", "thik", "kab", "kaise", "kaise", "kaisay",
    "available", "btao", "batao", "bata", "price", "rate", "krwana", "karwana",
    "skin", "ka", "ki", "ke", "ko", "se", "mein", "main", "lia", "liye", "k"
}


def looks_roman_urdu(text):
    if not text:
        return False
    words = [w.strip("?.!,").lower() for w in text.split()]
    if not words:
        return False
    hits = sum(1 for w in words if w in ROMAN_URDU_MARKERS)
    # require at least 2 markers, or 1 marker in a short message, to avoid
    # false positives on plain English ("ok", "hi", single words).
    return hits >= 2 or (hits >= 1 and len(words) <= 4)


import re

def extract_phone(text):
    """Return a cleaned phone number if the text looks like one, else None."""
    if not text:
        return None
    digits = re.sub(r"[^\d+]", "", text)
    # Pakistani numbers: 03xxxxxxxxx (11) or +923xxxxxxxxx / 00923... 
    only_digits = re.sub(r"\D", "", digits)
    if len(only_digits) >= 10:
        return text.strip()
    return None


def start_booking(from_number, session, roman):
    """Enter the structured booking flow. If we already have a name from the
    conversation, skip straight to asking for the phone number."""
    session["booking_stage"] = "awaiting_name"
    session["booking_sent"] = True
    if roman:
        msg = "Bohat khoob! Slot confirm karne k liye aap apna naam bata dein."
    else:
        msg = "Wonderful! To confirm your slot, may I have your name please?"
    send_text_message(from_number, msg)
    schedule_followup_after_bot_message(from_number)


def handle_booking_step(from_number, session, user_text, roman):
    """Drive the booking state machine. Returns True if the message was handled
    as part of booking (so the caller should NOT pass it to the open-ended AI)."""
    stage = session.get("booking_stage")

    if stage == "awaiting_name":
        name = user_text.strip()
        session["booking_name"] = name
        session["booking_stage"] = "awaiting_phone"
        first = name.split()[0] if name else ""
        if roman:
            msg = f"Shukriya{(' ' + first) if first else ''}! Aap apna contact number share kar dein, hamari team aap ko available timings bhej degi."
        else:
            msg = f"Thanks{(' ' + first) if first else ''}! Please share your contact number and our team will send you the available timings."
        send_text_message(from_number, msg)
        schedule_followup_after_bot_message(from_number)
        return True

    if stage == "awaiting_phone":
        phone = extract_phone(user_text)
        if not phone:
            # didn't look like a number — ask once more, gently
            if roman:
                msg = "Bas aap ka contact number chahiye taake team timings bhej sakay — aap number likh dein?"
            else:
                msg = "I just need a contact number so our team can send timings — could you type it here?"
            send_text_message(from_number, msg)
            schedule_followup_after_bot_message(from_number)
            return True
        session["booking_phone"] = phone
        session["booking_stage"] = "done"
        first = (session.get("booking_name") or "").split()[0] if session.get("booking_name") else ""
        # Single clean confirmation + close. No more questions, no loop.
        if roman:
            msg = (
                f"Perfect{(', ' + first) if first else ''}! Aap ki request note ho gayi hai. ✅\n\n"
                "Hamari team thori dair mein aap ko available timings bhej degi, aur consultation "
                "humare doctor k saath hogi jo aap ko personalized plan denge.\n\nMilte hain jald! 🌸"
            )
        else:
            msg = (
                f"Perfect{(', ' + first) if first else ''}! Your request is noted. ✅\n\n"
                "Our team will message you the available timings shortly, and your consultation "
                "will be with our doctor who'll prepare a personalized plan for you.\n\nSee you soon! 🌸"
            )
        send_text_message(from_number, msg)
        # Email the captured lead details
        send_booking_lead_email(from_number, session)
        return True

    return False


def send_booking_lead_email(from_number, session):
    def _send():
        try:
            if not RESEND_API_KEY or not NOTIFY_EMAIL:
                return
            requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                json={
                    "from": "RapidNexTech Bot <onboarding@resend.dev>",
                    "to": [NOTIFY_EMAIL],
                    "subject": f"✅ BOOKING REQUEST — {session.get('booking_name') or 'Unknown'}",
                    "text": (
                        f"A demo prospect completed the booking flow.\n\n"
                        f"Name: {session.get('booking_name')}\n"
                        f"Phone given: {session.get('booking_phone')}\n"
                        f"WhatsApp: +{from_number} (https://wa.me/{from_number})\n"
                    )
                }
            )
        except Exception as e:
            print(f"Booking lead email failed: {e}")
    t = threading.Thread(target=_send); t.daemon = True; t.start()


def handle_message(from_number, user_text, button_id=None):
    is_new_user = from_number not in conversation_store

    if is_new_user:
        conversation_store[from_number] = {
            "history": [],
            "notified": False,
            "welcomed": False,
            "last_user_message_time": datetime.now(timezone.utc).timestamp(),
            "last_followup_time": 0,
            "booking_sent": False,
            "roman_urdu_mode": False,
            # Structured booking flow: None -> "awaiting_name" -> "awaiting_phone" -> "done"
            "booking_stage": None,
            "booking_name": None,
            "booking_phone": None,
            "pending_book_ask": False,
        }

    session = conversation_store[from_number]
    session["last_user_message_time"] = datetime.now(timezone.utc).timestamp()

    # Update Roman-Urdu flag from the latest user text (sticky once set, but
    # re-checked each message so a switch back to English is also honored).
    if user_text:
        session["roman_urdu_mode"] = looks_roman_urdu(user_text)
    roman = session.get("roman_urdu_mode", False)

    # Email notification on first contact
    if is_new_user and not session["notified"]:
        send_email_notification(from_number, user_text or "Started demo")
        session["notified"] = True

    # First touch (no niche selector anymore — straight into the clinic).
    # ALWAYS stop after the welcome on the very first message. The patient's
    # NEXT message is where the AI conversation begins. This prevents a third
    # message (the AI answering "hello") from firing on the welcome turn.
    if not session["welcomed"]:
        session["welcomed"] = True
        send_welcome_sequence(from_number)
        schedule_followup_after_bot_message(from_number)
        return

    # Handle button presses
    if button_id:
        if button_id == "menu_treatments":
            send_text_message(from_number, TREATMENTS_TEXT)
            schedule_followup_after_bot_message(from_number)
            return
        elif button_id == "menu_pricing":
            send_text_message(from_number, PRICING_TEXT)
            schedule_followup_after_bot_message(from_number)
            return
        elif button_id == "menu_book":
            start_booking(from_number, session, roman)
            return
        elif button_id == "action_book":
            start_booking(from_number, session, roman)
            return
        elif button_id == "action_more":
            if roman:
                msg = "Bilkul! Aap kya jaanna chahenge? Treatments ya pricing — main yahin hoon 😊"
            else:
                msg = "Of course! What would you like to know — treatments or pricing? I'm right here 😊"
            send_text_message(from_number, msg)
            schedule_followup_after_bot_message(from_number)
            return

    # No text to process (e.g. only the welcome was just sent)
    if not user_text:
        return

    # If a structured booking is in progress, drive it and DO NOT pass the
    # message to the open-ended AI (this is what stops the re-qualifying loop).
    stage = session.get("booking_stage")
    if stage in ("awaiting_name", "awaiting_phone"):
        handle_booking_step(from_number, session, user_text, roman)
        return
    if stage == "done":
        low = user_text.lower()
        if any(w in low for w in ["no", "nahi", "nhi", "that's all", "thats all", "thanks", "thank you", "shukriya", "ok", "theek", "done"]):
            return
        ai_response = get_groq_response(user_text, session["history"])
        session["history"].append({"role": "user", "content": user_text})
        session["history"].append({"role": "assistant", "content": ai_response})
        if len(session["history"]) > 10:
            session["history"] = session["history"][-10:]
        send_text_message(from_number, ai_response)
        return

    # If the PREVIOUS bot turn asked to book a slot, and the patient is now
    # confirming ("yes"/"haan"), enter the structured booking flow directly —
    # BEFORE calling the open-ended AI (which would otherwise freelance it).
    if session.get("pending_book_ask"):
        session["pending_book_ask"] = False
        patient_confirming = (
            user_text.strip().lower() in [
                "yes", "yeah", "yep", "sure", "ok", "okay", "haan", "han", "ji", "jee",
                "g", "bilkul", "yes please", "ji haan", "han ji", "haan ji",
            ]
            or any(p in user_text.lower() for p in ["yes book", "book me", "let's book", "lets book", "book kar", "kar dein", "kardo", "kar do"])
        )
        if patient_confirming and session.get("booking_stage") is None:
            start_booking(from_number, session, roman)
            return

    # AI response (language mirroring handled inside the system prompt)
    ai_response = get_groq_response(user_text, session["history"])

    session["history"].append({"role": "user", "content": user_text})
    session["history"].append({"role": "assistant", "content": ai_response})
    if len(session["history"]) > 10:
        session["history"] = session["history"][-10:]

    send_text_message(from_number, ai_response)

    schedule_followup_after_bot_message(from_number)

    # If the AI's reply asked to book/confirm a slot, remember it so the NEXT
    # patient message ("yes") enters the structured booking flow.
    ai_asked_to_book = any(kw in ai_response.lower() for kw in [
        "shall i have our team", "shall i book", "book a slot", "confirm a slot",
        "may i have your name", "may i take your name", "slot confirm", "naam bata",
        "slot book kar", "consultation book kar",
    ])
    session["pending_book_ask"] = ai_asked_to_book

    # Offer booking buttons ONLY on genuine high-intent in the PATIENT's own
    # message (not on every mention of "consultation").
    booking_already_sent = session.get("booking_sent", False)
    strong_intent_phrases = [
        "book", "appointment", "schedule", "i want to", "i'd like to",
        "ready to", "sign me up", "let's do", "lets do",
        "book karna", "appointment chahiye", "kab a", "kab aaun",
    ]
    patient_strong_intent = any(p in user_text.lower() for p in strong_intent_phrases)
    if patient_strong_intent and not booking_already_sent and session.get("booking_stage") is None and not ai_asked_to_book:
        send_booking_prompt(from_number, roman)


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
    return "RapidNexTech WhatsApp Bot (Lahore Aesthetic) is running 🚀", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
