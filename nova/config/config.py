import os

from dotenv import load_dotenv

load_dotenv()

PORT_API = 3000
PORT_WS = 8080
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
GEMINI_API_KEY = os.getenv("GEN_API_KEY")
AUDIO_PATH = "data/output_audio/response.wav"
