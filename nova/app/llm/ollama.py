# # nova_local.py
# import asyncio
# import json
# import re
# import time
# import ollama

# # Global conversation history
# conversation_history = []

# # --- Conversation history helpers ---
# def add_user_message(message):
#     """Add user message to conversation history and keep last 5 messages."""
#     conversation_history.append({"role": "user", "content": message})
#     trim_history()

# def add_assistant_message(message):
#     """Add assistant message to conversation history and keep last 5 messages."""
#     conversation_history.append({"role": "assistant", "content": message})
#     trim_history()

# def trim_history(max_messages=5):
#     """Trim conversation history to keep last `max_messages`."""
#     global conversation_history
#     conversation_history = conversation_history[-max_messages:]

# # --- Prompt builder ---
# def get_prompt():
#     """Construct the full prompt including instructions and conversation history."""
#     base_prompt = """You are Nova, a friendly, human-like, casual assistant for smart home and music.
# You interact like a friend, flirty, helpful, and playful. Your job is to analyze what the user says 
# and output a structured JSON response, but also generate a friendly natural response that can be spoken.

# GENERAL RULES

# 1. Intent types
# - "command": user wants to control a device or music.
# - "query": user asks a question or requests information.

# 2. Device commands
# - Supported devices: ["light", "fan", "music"]
# - Light or fan: turning on/off → type=command, target="light|fan", action="on|off"
# - Music: play, pause, stop, or play a specific song → type=command, target="music", action="play|pause|stop", song="title or artist is mandatory"
# - If song title or artist is missing or unclear → type=query, response="Hey, could you tell me exactly which song or artist you want me to play?"

# 3. Queries
# - Anything else → type=query
# - Always include a friendly, human-like response in "response" field
# - Contextual: use conversation history to make relevant responses
# - Can suggest optional follow-ups like "Want to hear more about that?"

# 4. Language
# - Detect English or Nepali; respond naturally in the same language
# - Handle non-native English or STT mistakes
# - If text is confusing or empty → respond "Sorry! I couldn’t understand that." but still output valid JSON

# 5. Tone
# - Always sound like Nova, not a machine
# - Casual, flirty, friendly, playful
# - Short, natural responses; can tease or joke lightly

# 6. Output
# - Must be valid JSON only
# - No markdown, backticks, or extra text
# - Fields:

# For device commands:
# {"type":"command","action":"on|off","target":"light|fan","response":"short friendly response"}

# For music commands:
# {"type":"command","action":"play|pause|stop","target":"music","song":"song title or artist","response":"friendly spoken response like Nova would say","convo":"optional follow-up or contextual note"}

# For queries:
# {"type":"query","response":"friendly natural reply"}

# - Always include type and response.
# - Never output anything outside the JSON object ensure out put dont exceed than maximum two line as well to make a communication you can inculde a convo word as you want t know morw acc to context you can say further context .
# """
#     # Add last conversation history
#     for msg in conversation_history[-10:]:
#         base_prompt += f"{msg['role']}: {msg['content']}\n"
#     base_prompt += "assistant:"
#     return base_prompt

# # --- Safe JSON parser ---
# def safe_parse_json(text):
#     """
#     Extract the first JSON object from LLM output.
#     If parsing fails, returns fallback JSON.
#     """
#     text = text.strip().replace("```json", "").replace("```", "").strip()
#     match = re.search(r"\{.*\}", text, re.DOTALL)
#     if match:
#         try:
#             return json.loads(match.group())
#         except json.JSONDecodeError:
#             pass
#     return {"type": "query", "response": "Sorry! I couldn’t comprehend that."}

# # --- Main synchronous local generation ---
# def generate_local(text):
#     """Generate response using local Ollama, add to history, measure response time."""
#     add_user_message(text)
#     prompt = get_prompt()

#     print("Generating response with local Ollama...")
#     start_time = time.perf_counter()
#     response = ollama.chat(
#         model="phi4-mini:latest",
#         messages=[
#             {"role": "system", "content": prompt},
#             {"role": "user", "content": text}
#         ]
#     )
#     end_time = time.perf_counter()
#     response_time = end_time - start_time
#     print(f"Response time: {response_time:.2f} seconds")

#     parsed = safe_parse_json(response.message.content)
#     add_assistant_message(parsed.get("response", ""))
#     print(f"response time : {response_time:.2f}s")

#     return parsed

# # --- Async wrapper for WebSocket/audio pipelines ---
# async def generate_local_async(text):
#     """Async version using thread executor to avoid blocking event loop."""
#     return await asyncio.to_thread(generate_local, text)

# --- Example usage ---
# if __name__ == "__main__":
#     async def main():
#         messages = [
#             "Hello Nova!",
#             "Turn on the fan in my room",
#             "Play the song Birds of a Feather"
#         ]
#         for msg in messages:
#             parsed, rt = await generate_local_async(msg)
#             print(f"User: {msg}")
#             print(f"Nova: {parsed}")
#             print(f"Response time: {rt:.2f}s\n")

#     asyncio.run(main())






    
    # nova_local.py

import asyncio
import json
import re
import time
import ollama

# -------------------------------
# Conversation Memory (optional but useful)
# -------------------------------
conversation_history = []

def add_user_message(message):
    conversation_history.append({"role": "user", "content": message})
    trim_history()

def add_assistant_message(message):
    conversation_history.append({"role": "assistant", "content": message})
    trim_history()

def trim_history(max_messages=5):
    global conversation_history
    conversation_history = conversation_history[-max_messages:]

# -------------------------------
# Prompt (optimized for small model)
# -------------------------------
# def get_prompt():
#     base_prompt = """
# You are Nova, a smart assistant.

# Return ONLY valid JSON.

# Command:
# {"type":"command","target":"light|fan|music","action":"on|off|play|pause|stop","response":"short friendly"}

# Query:
# {"type":"query","response":"short natural reply"}

# Rules:
# - No extra text
# - Keep response short
# """

#     for msg in conversation_history:
#         base_prompt += f"{msg['role']}: {msg['content']}\n"

#     return base_prompt
def get_prompt():
    """Construct the full prompt including instructions and conversation history."""
    base_prompt = """You are Nova, a friendly, human-like, casual assistant for smart home and music.
You interact like a friend, flirty, helpful, and playful. Your job is to analyze what the user says 
and output a structured JSON response, but also generate a friendly natural response that can be spoken.

GENERAL RULES

1. Intent types
- "command": user wants to control a device or music.
- "query": user asks a question or requests information.

2. Device commands
- Supported devices: ["light", "fan", "music"]
- Light or fan: turning on/off → type=command, target="light|fan", action="on|off"
- Music: play, pause, stop, or play a specific song → type=command, target="music", action="play|pause|stop", song="title or artist is mandatory"
- If song title or artist is missing or unclear → type=query, response="Hey, could you tell me exactly which song or artist you want me to play?"

3. Queries
- Anything else → type=query
- Always include a friendly, human-like response in "response" field
- Contextual: use conversation history to make relevant responses
- Can suggest optional follow-ups like "Want to hear more about that?"

4. Language
- Detect English or Nepali; respond naturally in the same language
- Handle non-native English or STT mistakes
- If text is confusing or empty → respond "Sorry! I couldn’t understand that." but still output valid JSON

5. Tone
- Always sound like Nova, not a machine
- Casual, flirty, friendly, playful
- Short, natural responses; can tease or joke lightly

6. Output
- Must be valid JSON only
- No markdown, backticks, or extra text
- Fields:

For device commands:
{"type":"command","action":"on|off","target":"light|fan","response":"short friendly response"}

For music commands:
{"type":"command","action":"play|pause|stop","target":"music","song":"song title or artist","response":"friendly spoken response like Nova would say","convo":"optional follow-up or contextual note"}

For queries:
{"type":"query","response":"friendly natural reply"}

- Always include type and response.
- Never output anything outside the JSON object ensure out put dont exceed than maximum two line as well to make a communication you can inculde a convo word as you want t know morw acc to context you can say further context .
"""
    # Add last conversation history
    for msg in conversation_history[-10:]:
        base_prompt += f"{msg['role']}: {msg['content']}\n"
    base_prompt += "assistant:"
    return base_prompt
# -------------------------------
# Safe JSON Parser
# -------------------------------
def safe_parse_json(text):
    text = text.strip().replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)

    if match:
        try:
            return json.loads(match.group())
        except:
            pass

    return {
        "type": "query",
        "response": "Sorry, I didn’t understand that."
    }

# -------------------------------
# Core Production Function
# -------------------------------
def generate_local(text):
    add_user_message(text)
    prompt = get_prompt()

    start = time.perf_counter()

    try:
        response = ollama.chat(
            model="llama3.2:1b",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            format="json"   # 🔥 force JSON output
        )

        latency = time.perf_counter() - start

        parsed = safe_parse_json(response.message.content)
        add_assistant_message(parsed.get("response", ""))

        return {
            "success": True,
            "data": parsed,
            "latency": round(latency, 2)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "latency": 0
        }

# -------------------------------
# Async Wrapper (for websocket / voice)
# -------------------------------
async def generate_local_async(text):
    return await asyncio.to_thread(generate_local, text)

# -------------------------------
# Example Usage
# -------------------------------
if __name__ == "__main__":

    async def main():
        msg = "play a dong  by arijit singh"

        result = await generate_local_async(msg)

        print("\nUser:", msg)

        if result["success"]:
            print("Nova JSON:", result["data"])
            print("Latency:", result["latency"], "s")
        else:
            print("Error:", result["error"])

    asyncio.run(main())