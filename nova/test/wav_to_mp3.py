from pydub import AudioSegment

# Load your source file
audio = AudioSegment.from_file("response.mp3")

# 1. Convert to Mono (1 channel)
audio = audio.set_channels(1)

# 2. Set Sample Rate to 24000Hz
audio = audio.set_frame_rate(24000)

# 3. Set Sample Width to 2 bytes (16-bit)
audio = audio.set_sample_width(2)

# Export as WAV
audio.export("response.wav", format="wav")

print("Exported: 24kHz, 16-bit, Mono WAV")