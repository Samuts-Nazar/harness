import os, httpx
from dotenv import load_dotenv
load_dotenv()
h = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
m = httpx.get("https://openrouter.ai/api/v1/models", headers=h, timeout=30)
k = httpx.get("https://openrouter.ai/api/v1/auth/key", headers=h, timeout=30)
print("models:", m.status_code, len(m.json().get("data", [])), "| auth/key:", k.status_code, {x: v for x, v in k.json().get("data", {}).items() if x in ("limit", "limit_remaining", "usage", "is_free_tier")})
