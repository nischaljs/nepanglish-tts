# def test_latency():
#     start_time = time.time()
#     first_token_time = None
#     full_response = ""
#     stream = client.chat.completions.create(
#         model="llama3-8b-8192",
#         messages=[
#             {"role": "user", "content": "Say hello in one short sentence."}
#         ],
#         stream=True
#     )
#     print("⏳ Request sent...")
#     for chunk in stream:
#         if chunk.choices[0].delta.content:
#             if first_token_time is None:
#                 first_token_time = time.time()
#                 print(f"⚡ First token received at: {first_token_time - start_time:.3f} sec")
#             token = chunk.choices[0].delta.content
#             full_response += token
#             print(token, end="", flush=True)
#     end_time = time.time()
#     print("\n\n📊 Results:")
#     print(f"TTFT (first token): {first_token_time - start_time:.3f} sec")
#     print(f"Total time: {end_time - start_time:.3f} sec")
#     print(f"Response length: {len(full_response)} chars")
# if __name__ == "__main__":
#     test_latency()
import time


def groqLLM(query):
    start_time = time.time()
    first_token_time = None
    token_count = 0

    completion = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "user",
                "content": query
            }
        ],
        temperature=1,
        max_completion_tokens=8192,
        top_p=1,
        reasoning_effort="low",
        stream=True,
        stop=None
    )

    full_response = ""

    for chunk in completion:
        content = chunk.choices[0].delta.content or ""

        if content:
            # First token detection
            if first_token_time is None:
                first_token_time = time.time()
                print(f"\n⚡ TTFT: {first_token_time - start_time:.3f} sec\n")

            token_count += 1
            full_response += content
            print(content, end="", flush=True)

    end_time = time.time()

    # Final stats
    print("\n\n📊 Latency Report:")
    print(f"Total time: {end_time - start_time:.3f} sec")
    print(f"Tokens received: {token_count}")
    print(f"Tokens/sec: {token_count / (end_time - start_time):.2f}")

    return full_response