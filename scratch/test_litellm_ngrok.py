import litellm

print("Testing litellm with ngrok bypass...")
try:
    response = litellm.completion(
        model="ollama/llama3.1:8b",
        messages=[{"role": "user", "content": "Hello"}],
        api_base="https://hummingly-athetoid-wanita.ngrok-free.dev",
        extra_headers={"ngrok-skip-browser-warning": "true"},
        timeout=10
    )
    print("Success:", response)
except Exception as e:
    print("Error:", e)
