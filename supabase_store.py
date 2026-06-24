"""
supabase_store.py — Supabase integration layer for the RapidNexTech WhatsApp bot.

This module is the bridge between the Flask bot and the Next.js dashboard.
Both read/write the SAME Supabase tables, so:
  - the dashboard can SEE live conversations the bot is having
  - clinic staff can TAKE OVER (set status='human'), and the bot goes silent
  - everything is multi-tenant: routed by Meta's phone_number_id -> clinic

It is written defensively: if Supabase is unreachable or env vars are missing,
the functions fail quietly and the bot keeps working (demo never breaks).

Tables (created by the dashboard's SQL):
  clinics(id, name, phone_number_id, display_number, system_prompt, ...)
  conversations(id, clinic_id, patient_wa_number, patient_name, status,
                booking_stage, last_message_at, created_at)
  messages(id, conversation_id, clinic_id, direction, sender, body, created_at)

status values: 'bot' (AI replies) | 'human' (staff handling, bot silent) | 'closed'
sender values: 'patient' | 'bot' | 'staff'
direction values: 'inbound' | 'outbound'
"""

import os
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL")           # e.g. https://xxxx.supabase.co
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")  # service role key (server-side only!)

_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY or "",
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY or ''}",
    "Content-Type": "application/json",
}

REST = f"{SUPABASE_URL}/rest/v1" if SUPABASE_URL else None


def _enabled():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


# ---------------------------------------------------------------------------
# Clinic resolution (multi-tenant): map Meta phone_number_id -> clinic row
# ---------------------------------------------------------------------------
_clinic_cache = {}  # phone_number_id -> clinic dict (small, rarely changes)


def get_clinic_by_phone_number_id(phone_number_id):
    """Return the clinic row for a given Meta phone_number_id, or None.
    Cached in memory to avoid a DB hit on every message."""
    if not _enabled():
        return None
    if phone_number_id in _clinic_cache:
        return _clinic_cache[phone_number_id]
    try:
        r = requests.get(
            f"{REST}/clinics",
            headers=_HEADERS,
            params={"phone_number_id": f"eq.{phone_number_id}", "select": "*", "limit": "1"},
            timeout=8,
        )
        rows = r.json()
        clinic = rows[0] if isinstance(rows, list) and rows else None
        if clinic:
            _clinic_cache[phone_number_id] = clinic
        return clinic
    except Exception as e:
        print(f"[supabase] get_clinic error: {e}")
        return None


# ---------------------------------------------------------------------------
# Conversation upsert + lookup
# ---------------------------------------------------------------------------
def get_or_create_conversation(clinic_id, patient_wa_number):
    """Return the conversation row for (clinic, patient), creating it if needed."""
    if not _enabled():
        return None
    try:
        # try existing (not closed)
        r = requests.get(
            f"{REST}/conversations",
            headers=_HEADERS,
            params={
                "clinic_id": f"eq.{clinic_id}",
                "patient_wa_number": f"eq.{patient_wa_number}",
                "order": "last_message_at.desc",
                "select": "*",
                "limit": "1",
            },
            timeout=8,
        )
        rows = r.json()
        if isinstance(rows, list) and rows:
            return rows[0]
        # create
        r = requests.post(
            f"{REST}/conversations",
            headers={**_HEADERS, "Prefer": "return=representation"},
            json={
                "clinic_id": clinic_id,
                "patient_wa_number": patient_wa_number,
                "status": "bot",
            },
            timeout=8,
        )
        rows = r.json()
        return rows[0] if isinstance(rows, list) and rows else None
    except Exception as e:
        print(f"[supabase] get_or_create_conversation error: {e}")
        return None


def conversation_is_human_controlled(clinic_id, patient_wa_number):
    """True if a human has taken over this conversation (bot must stay silent)."""
    if not _enabled():
        return False
    try:
        r = requests.get(
            f"{REST}/conversations",
            headers=_HEADERS,
            params={
                "clinic_id": f"eq.{clinic_id}",
                "patient_wa_number": f"eq.{patient_wa_number}",
                "select": "status",
                "order": "last_message_at.desc",
                "limit": "1",
            },
            timeout=6,
        )
        rows = r.json()
        if isinstance(rows, list) and rows:
            return rows[0].get("status") == "human"
        return False
    except Exception as e:
        print(f"[supabase] human-control check error: {e}")
        return False  # fail open: bot keeps working


def update_conversation(conversation_id, **fields):
    """Patch fields on a conversation (e.g. patient_name, booking_stage, last_message_at)."""
    if not _enabled() or not conversation_id:
        return
    try:
        requests.patch(
            f"{REST}/conversations",
            headers=_HEADERS,
            params={"id": f"eq.{conversation_id}"},
            json=fields,
            timeout=6,
        )
    except Exception as e:
        print(f"[supabase] update_conversation error: {e}")


# ---------------------------------------------------------------------------
# Message logging
# ---------------------------------------------------------------------------
def log_message(clinic_id, conversation_id, direction, sender, body):
    """Insert a message row so the dashboard shows the full thread."""
    if not _enabled() or not conversation_id:
        return
    try:
        requests.post(
            f"{REST}/messages",
            headers=_HEADERS,
            json={
                "clinic_id": clinic_id,
                "conversation_id": conversation_id,
                "direction": direction,
                "sender": sender,
                "body": body,
            },
            timeout=6,
        )
        # bump last_message_at on the conversation for sorting in the dashboard
        requests.patch(
            f"{REST}/conversations",
            headers=_HEADERS,
            params={"id": f"eq.{conversation_id}"},
            json={"last_message_at": "now()"},
            timeout=6,
        )
    except Exception as e:
        print(f"[supabase] log_message error: {e}")
