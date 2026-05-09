import re

# --- COMMANDS LIST ---
COMMANDS = [
    # Light commands
    {"pattern": re.compile(r"turn on (\w+\s?\w*) light", re.I), "target": "light", "action": "on"},
    {"pattern": re.compile(r"turn off (\w+\s?\w*) light", re.I), "target": "light", "action": "off"},
    {"pattern": re.compile(r"(\w+\s?\w*) light on", re.I), "target": "light", "action": "on"},
    {"pattern": re.compile(r"(\w+\s?\w*) light off", re.I), "target": "light", "action": "off"},

    # Fan commands
    {"pattern": re.compile(r"turn on (\w+\s?\w*) fan", re.I), "target": "fan", "action": "on"},
    {"pattern": re.compile(r"turn off (\w+\s?\w*) fan", re.I), "target": "fan", "action": "off"},
    {"pattern": re.compile(r"fan on", re.I), "target": "fan", "action": "on"},
    {"pattern": re.compile(r"fan off", re.I), "target": "fan", "action": "off"},

    # Music - PLAY with song name
    {"pattern": re.compile(r"play (?:the )?song (?:of |by )?(.+)", re.I), "target": "music", "action": "play"},
    {"pattern": re.compile(r"play (?:the )?music (?:of |by )?(.+)", re.I), "target": "music", "action": "play"},
    {"pattern": re.compile(r"listen to (?:the )?song (?:of |by )?(.+)", re.I), "target": "music", "action": "play"},
    {"pattern": re.compile(r"play (.+)", re.I), "target": "music", "action": "play"},

    # Music - STOP
    {"pattern": re.compile(r"stop (?:the )?(?:music|song)", re.I), "target": "music", "action": "stop"},
    {"pattern": re.compile(r"stop (?:playing)?", re.I), "target": "music", "action": "stop"},

    # Music - PAUSE
    {"pattern": re.compile(r"pause (?:the )?(?:music|song)", re.I), "target": "music", "action": "pause"},

    # Music - RESUME
    {"pattern": re.compile(r"resume (?:the )?(?:music|song)", re.I), "target": "music", "action": "resume"},
    {"pattern": re.compile(r"continue (?:the )?(?:music|song)", re.I), "target": "music", "action": "resume"},
]

ALLOWED_DEVICES = ["light", "kitchen light", "fan", "living room light", "music"]


# --- MATCH COMMAND ---
def match_command(transcript):
    print("Matching command...")
    for cmd in COMMANDS:
        match = cmd["pattern"].search(transcript)
        if match:
            result = {
                "type": "command",
                "action": cmd["action"],
                "target": cmd["target"],
            }
            # extract song name if music play command!
            if cmd["target"] == "music" and cmd["action"] == "play":
                try:
                    result["song"] = match.group(1).strip()
                except IndexError:
                    result["song"] = transcript  # fallback
            return result

    return {"type": "query", "transcript": transcript}


# --- HANDLE COMMAND ---
def handle_command(data):
    action = data.get("action")
    target = data.get("target")

    if target.lower() not in ALLOWED_DEVICES:
        return {"error": "Device not recognized"}

    if target == "music":
        return {"music": action}  # play/stop/pause/resume

    if "on" in action.lower():
        state = "on"
    elif "off" in action.lower():
        state = "off"
    else:
        return {"error": "Invalid action"}

    return {target: state}
