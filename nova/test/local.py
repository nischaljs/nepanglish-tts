
# nova_local.py

import asyncio
import time
import ollama


# -------------------------------
# Core Function (SYNC)
# -------------------------------
def generate_local(text):
    print("⚡ Testing Ollama response...")

    start = time.perf_counter()

    try:
        response = ollama.chat(
            model="llama3.2:1b",   # small model for testing
            messages=[
                {"role": "user", "content": text}
            ]
        )

        latency = time.perf_counter() - start

        return {
            "success": True,
            "response": response.message.content.strip(),
            "latency": round(latency, 2)
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "latency": 0
        }


# -------------------------------
# Async Wrapper
# -------------------------------
async def generate_local_async(text):
    return await asyncio.to_thread(generate_local, text)


# -------------------------------
# Main Test Runner
# -------------------------------
if __name__ == "__main__":

    async def main():
        messages = [
           
            "do you know about ebola in a sentence"
        ]

        for msg in messages:
            result = await generate_local_async(msg)

            print("\n-----------------------------")
            print(f"User: {msg}")

            if result["success"]:
                print(f"Nova: {result['response']}")
                print(f"Latency: {result['latency']}s")
            else:
                print(f"Error: {result['error']}")

    asyncio.run(main())
    