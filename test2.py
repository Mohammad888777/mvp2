from openai import OpenAI

client = OpenAI(
    base_url="https://api.gapgpt.app/v1",
    api_key="DlNlz3icgBGsHO9vGk0QUNUpXn5eHDIZ9pkfp3XCe1eZKRnA",
    # timeout=180.0,
    max_retries=0
)

try:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "سلام"}],
        max_tokens=50
    )
    print(resp)
except Exception as e:
    print(type(e).__name__, e)
