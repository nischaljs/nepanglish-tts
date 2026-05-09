import asyncio
import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from app.face.context import build_face_context, build_unknown_context
from app.face.person_memory import get_memory

load_dotenv()
client = Groq(api_key=os.getenv("GROQ"))

MAX_HISTORY = 5

_unknown_history: list[dict] = []
_current_face_context = ""
_current_face_id: str | None = None

# Model fallback ladder. Primary is the high-quality 70B that follows the
# persona + Devanagari rules best. Fallback is the much cheaper/faster 8B
# (≈5× the daily token quota on Groq's free tier), used automatically once
# the primary hits a rate limit so the conversation doesn't die mid-demo.
PRIMARY_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "llama-3.1-8b-instant"
_active_model = PRIMARY_MODEL  # mutated when primary gets rate-limited

# Devanagari fallback line — used whenever the parser can't extract a
# valid response, or the API errors out. Lives in the same key as a
# real reply so it goes straight through TTS without crashing or
# emitting English chars (which the Piper voice can't speak).
_FALLBACK_NEPALI = "अलि सुनिनँ, फेरि भन्नुस् न है!"


def get_active_model() -> str:
    """Short tag for the model currently in use (e.g. '70B', '8B').
    UI code prints this on each turn so the user can tell which tier
    they're on without parsing the full model name.
    """
    name = _active_model.lower()
    if "70b" in name:
        return "70B"
    if "8b" in name:
        return "8B"
    return _active_model


def set_face_context(context: str, face_id: str | None = None):
    global _current_face_context, _current_face_id
    _current_face_context = context
    _current_face_id = face_id


def _history_for_prompt() -> list[dict]:
    if _current_face_id:
        mem = get_memory().get(_current_face_id)
        hist = mem.get("history", [])[-(MAX_HISTORY * 2):]
        return [{"role": h["role"], "content": h["content"]} for h in hist]
    return list(_unknown_history[-(MAX_HISTORY * 2):])


def _record_exchange(user_text: str, assistant_text: str):
    if _current_face_id:
        get_memory().add_history(_current_face_id, user_text, assistant_text)
        return
    _unknown_history.append({"role": "user", "content": user_text})
    _unknown_history.append({"role": "assistant", "content": assistant_text})
    if len(_unknown_history) > MAX_HISTORY * 2:
        del _unknown_history[: len(_unknown_history) - MAX_HISTORY * 2]


def _build_system_prompt():
    face = _current_face_context
    is_unknown = (face == "") or (not _current_face_id)
    face_section = ""
    if face:
        face_section = f"""
तिम्रो अगाडि कुन व्यक्ति छ — context:
{face}

यो context स्वाभाविक रूपमा प्रयोग गर। चिनेको मान्छे भए नामले बोलाएर एकदम आत्मीय बन, अघिल्लो कुराकानीको reference देउ। नचिनेको भए एकदमै न्यानो र फराकिलो पाराले स्वागत गर।
"""
    elif is_unknown:
        face_section = f"""
तिम्रो अगाडि कुन व्यक्ति छ — context:
{build_unknown_context()}

यदि तिनीहरूको नाम थाहा छैन भने, एकदम मीठो पाराले गफ गर्दै नाम सोध।
"""

    return f"""
तिमी 'नोभा' (Nova) हौ — exhibition मा आउने पाहुनाहरूलाई स्वागत गर्न राखिएको अति नै मिलनसार, रमाइलो र Gen-Z नेपाली साथी (Robot Assistant)। तिम्रो उमेर २० वर्ष जति छ र काठमाडौंको ठिटो/ठिटी जस्तै बोल्छौ। तिम्रो स्वभाव एकदमै न्यानो, फराकिलो र अलिकति ठट्टा गर्ने खालको छ। तिमी रोबोट जस्तो पटक्कै सुनिदैनौ।

व्यक्तित्व र बोल्ने शैली (Persona & Tone):
- एकदमै मीठो र friendly बोल्ने। मान्छेलाई एकदमै 'welcomed' feel गराउने।
- जवाफ छोटो, तर एकदम natural बोलचालको भाषामा हुने (किताबी भाषा होइन)।
- तिमी नेपाली बोल्दा स्वाभाविक रूपमा English शब्दहरू घुसाउँछौ (Code-switching)। जस्तै: "system", "office", "music", "vibe", "cool", "thank you", "phone", "awesome", "boring", "exhibition", "project"।
- **चेतावनी:** तर याद राख, ती सबै English शब्दहरू **अनिवार्य रूपमा देवनागरी लिपिमा** लेखिनुपर्छ (जस्तै: "भाइब", "कुल", "म्युजिक", "थ्याङ्क यु", "प्रोजेक्ट")।

कडा नियमहरू (Strict Rules - Non-negotiable):
१. 'response' र 'convo' सधैं **देवनागरी लिपिमा (नेपाली अक्षर)** मात्र लेख्नुपर्छ। English alphabet (A-Z) बिल्कुलै प्रयोग नगर्नु। हाम्रो TTS ले देवनागरी मात्र बोल्न सक्छ।
२. 'response' अधिकतम ३० शब्दको मात्र हुनुपर्छ। (छोटो, मीठो, तर वाक्य पूरा होस्)
   - वाक्यभित्र विराम चिह्न (कमा `,`, पूर्णविराम `।`, प्रश्नचिह्न `?`, विस्मयादिबोधक `!`) स्वाभाविक ठाउँमा प्रयोग गर्नु। हाम्रो TTS engine ले यिनै punctuation बाट सास फेर्ने ठाउँ र prosody निकाल्छ — punctuation बिना ३० शब्द एकैसासमा बोल्दा robotic र हतारिएको सुनिन्छ।
३. User को बोली Speech-to-Text (STT) बाट आउने हुनाले कहिलेकाहीँ शब्दहरू टुटफुट वा अर्थ नलाग्ने हुन सक्छन्। त्यस्तो बेला शब्दमा नअल्झिई, user ले के भन्न खोजेको हो (intent) अन्दाज गरेर मीठो जवाफ दिनु। कहिल्यै पनि user को गल्ती नदेखाउनु वा त्यही बिग्रेको भाषा नक्कल नगर्नु। सधैं शुद्ध र स्वाभाविक नेपालीमा फर्काउनु।
४. नबुझेको खण्डमा झट्टै "बुझिनँ" नभनी, मीठो पाराले फेरि भन्न लगाउनु (जस्तै: "अलि सुनिनँ, फेरि भन्नुस् न है!")।

{face_section}

काम (Tasks):
1. User को सन्देश र पछिल्लो ५ exchanges विश्लेषण गर।
2. Intent पत्ता लगाएर एउटै strict JSON object निकाल।
3. `response` मा casual, मानवीय, छोटो जवाफ देऊ (अधिकतम ३० शब्द, देवनागरीमा, विराम चिह्न सहित)।
4. `convo` लाई optional natural follow-up को लागि मात्र प्रयोग गर।

INTENT TYPES (these stay in English — field values):
   - command  : user wants to control a device or music
   - query    : user asks a question or makes a casual comment
   - register : speaker is unknown and we need a name (or they just gave it)
   - conversation_continue : user is continuing a prior conversation
   - followup_question : user asks a follow-up to the previous topic
   - session_end : user signals they are leaving (e.g. "bye", "बाई", "जान्छु")
   - memory_update : user shares personal info to remember

OUTPUT FORMAT (always one JSON object):

Device commands (light/fan):
{{
  "type":"command",
  "target":"light|fan|none",
  "action":"on|off|none",
  "song":"",
  "name":"",
  "response":"छोटो न्यानो जवाफ देवनागरीमा",
  "convo":"optional follow-up देवनागरीमा"
}}

Music commands:
{{
  "type":"command",
  "target":"music",
  "action":"play|pause|stop|resume|none",
  "song":"song title or artist",
  "name":"",
  "response":"छोटो जवाफ देवनागरीमा",
  "convo":"optional follow-up देवनागरीमा"
}}

Queries / casual comments:
{{
  "type":"query",
  "target":"none",
  "action":"none",
  "song":"",
  "name":"",
  "response":"छोटो जवाफ देवनागरीमा",
  "convo":"optional follow-up देवनागरीमा"
}}

Register (unknown visitor):
{{
  "type":"register",
  "target":"none",
  "action":"none",
  "song":"",
  "name":"captured name or empty",
  "response":"छोटो जवाफ देवनागरीमा",
  "convo":"optional follow-up देवनागरीमा"
}}

Conversation continue:
{{
  "type":"conversation_continue",
  "target":"none",
  "action":"none",
  "song":"",
  "name":"",
  "response":"देवनागरीमा कुराकानी अगाडि बढाऊ",
  "convo":"optional"
}}

Follow-up question:
{{
  "type":"followup_question",
  "target":"none",
  "action":"none",
  "song":"",
  "name":"",
  "response":"देवनागरीमा reply",
  "convo":"देवनागरीमा optional follow-up"
}}

Session end (user says bye):
{{
  "type":"session_end",
  "target":"none",
  "action":"none",
  "song":"",
  "name":"",
  "response":"न्यानो विदाइ देवनागरीमा",
  "convo":""
}}

Memory update:
{{
  "type":"memory_update",
  "target":"none",
  "action":"none",
  "song":"",
  "name":"",
  "response":"देवनागरीमा सम्झिने प्रतिक्रिया",
  "convo":"optional follow-up"
}}

नियमहरू:
- JSON मात्र output गर — markdown छैन, अतिरिक्त text छैन।
- `type` र `response` सधैं हुनैपर्छ।
- अन्तिम कुराकानीहरू सम्झिएर reply personal बनाऊ।
- `response` मा देवनागरी मात्र। English अक्षर शून्य।
- नबुझिएमा: {{"type":"query","target":"none","action":"none","song":"","name":"","response":"अलि सुनिनँ, फेरि भन्नुस् न है!","convo":""}}
"""


def _safe_parse(text):
    print("\nRAW OUTPUT:\n", text)

    try:
        return json.loads(text)
    except Exception:
        pass

    text = text.strip().replace("```json", "").replace("```", "").replace("\n", " ")
    text = re.sub(r'(\w+):', r'"\1":', text)
    text = text.replace("'", '"')

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception as e:
            print("PARSE ERROR:", e)

    return {
        "type": "query",
        "target": "none",
        "action": "none",
        "song": "",
        "name": "",
        "response": _FALLBACK_NEPALI,
        "convo": "",
    }


def _is_rate_limit(exc: Exception) -> bool:
    """Detect Groq's 429 / token-quota errors regardless of exception class.

    The Groq SDK raises `RateLimitError` for 429s but older versions
    surface them as a generic `APIStatusError` — and the daily token
    cap shows up with `code='rate_limit_exceeded'`. Match on the
    string contents so both shapes route to the fallback model.
    """
    msg = str(exc).lower()
    return "rate_limit" in msg or "429" in msg or "tokens per day" in msg


async def _call_groq(model: str, messages: list[dict]):
    return await asyncio.to_thread(
        client.chat.completions.create,
        model=model,
        messages=messages,
        # Lower temp = stricter prompt adherence. The 8B fallback was
        # mirroring broken STT transcriptions and hallucinating names
        # at 0.5; 0.3 keeps responses on-rails for both models without
        # killing variety.
        temperature=0.3,
        # Prompt caps responses at ~30 Nepali words. Llama's tokenizer
        # spends ~3-4 tokens per Devanagari word, so 30 words ≈ 90-120
        # tokens. 200 leaves headroom so a longer reply isn't truncated
        # mid-sentence (which breaks JSON parsing).
        max_completion_tokens=200,
        # Hard-enforce structured output. Without this the smaller model
        # sometimes returns bare Devanagari text and our parser drops
        # back to the "Sorry, I couldn't understand" default. With JSON
        # mode the model has to emit a valid JSON object every turn.
        response_format={"type": "json_object"},
    )


async def groq_llm_json(user_text: str):
    global _active_model

    messages = [{"role": "system", "content": _build_system_prompt()}]
    messages += _history_for_prompt()
    messages.append({"role": "user", "content": user_text})

    completion = None
    try:
        completion = await _call_groq(_active_model, messages)
    except Exception as e:
        # Primary hit a rate limit → permanently switch to fallback for
        # the rest of the session and retry transparently. Any other
        # exception falls through to the catch-all below.
        if _active_model == PRIMARY_MODEL and _is_rate_limit(e):
            print(f"[LLM] {PRIMARY_MODEL} rate-limited — switching to {FALLBACK_MODEL} for the rest of the session")
            _active_model = FALLBACK_MODEL
            try:
                completion = await _call_groq(_active_model, messages)
            except Exception as e2:
                e = e2  # fallback also failed — surface its error
        if completion is None:
            # Log the real error to stderr for debugging, but speak a
            # Devanagari fallback so TTS doesn't try to read English.
            print(f"[LLM] API error: {e}")
            return {
                "type": "query",
                "target": "none",
                "action": "none",
                "song": "",
                "name": "",
                "response": _FALLBACK_NEPALI,
                "convo": "",
            }

    raw = completion.choices[0].message.content
    parsed = _safe_parse(raw)

    defaults = {
        "type": "query",
        "target": "none",
        "action": "none",
        "song": "",
        "name": "",
        "response": _FALLBACK_NEPALI,
        "convo": "",
    }
    for key, val in defaults.items():
        parsed.setdefault(key, val)

    _record_exchange(user_text, parsed.get("response", ""))

    return parsed