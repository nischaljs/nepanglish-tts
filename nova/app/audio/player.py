import os
import subprocess
import asyncio
from app.tts.tts_engine import play_audio

# Paths relative to the project root
MUSIC_DIR = "assets/music"
SONG_MP3 = os.path.join(MUSIC_DIR, "song.mp3")
SONG_WAV = os.path.join(MUSIC_DIR, "song.wav")

COOKIES = r"C:\Users\yubra\OneDrive\Documents\Development\Voice-assitance-py\cookies.txt"

async def download_and_play(query):
    if not query:
        print("No song specified")
        return

    # Ensure directory exists
    os.makedirs(MUSIC_DIR, exist_ok=True)

    if os.path.exists(SONG_MP3):
        try:
            os.remove(SONG_MP3)
        except Exception as e:
            print(f"Error removing old mp3: {e}")

    print(f"Searching: {query}")
    search_query = f'ytsearch1:"{query.strip()}"'

    result = subprocess.run([
        "yt-dlp",
        "-f", "bestaudio/best",
        "-x",
        "--audio-format", "mp3",
        "-o", SONG_MP3,
        search_query
    ])

    if result.returncode != 0:
        print("Download failed! Trying fallback...")
        fallback_query = f'ytsearch1:{query.strip()}'
        fallback_result = subprocess.run([
            "yt-dlp",
            "-f", "bestaudio/best",
            "-x",
            "--audio-format", "mp3",
            "-o", SONG_MP3,
            fallback_query
        ])
        if fallback_result.returncode != 0:
            print("Fallback failed. Song could not be downloaded.")
            return

    print("Downloaded! Converting to WAV...")
    from pydub import AudioSegment

    try:
        # Load your source file
        audio = AudioSegment.from_file(SONG_MP3)

        # Convert to Mono, 24kHz, 16-bit for ESP32/Player
        audio = audio.set_channels(1).set_frame_rate(24000).set_sample_width(2)

        # Export as WAV
        audio.export(SONG_WAV, format="wav")
        print(f"Exported: {SONG_WAV} (24kHz, 16-bit, Mono)")

        # Play locally
        await play_audio(SONG_WAV)
    except Exception as e:
        print(f"Error during audio conversion/playback: {e}")

async def main():
    print("🎵 Music test starting...")
    query = "majbooor"
    await download_and_play(query)
    print("✅ Done playing song")

if __name__ == "__main__":
    # If running as a script, ensure we can import 'app'
    # This is a fallback for users running 'python player.py' from app/audio
    import sys
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root_dir not in sys.path:
        sys.path.append(root_dir)
    
    asyncio.run(main())