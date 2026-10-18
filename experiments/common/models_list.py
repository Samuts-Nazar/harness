import os,re,httpx
from dotenv import load_dotenv
load_dotenv()
h={"Authorization":"Bearer "+os.environ['OPENROUTER_API_KEY']}
d=httpx.get("https://openrouter.ai/api/v1/models",headers=h,timeout=30).json()['data']
for m in sorted(d,key=lambda m:m['id']):
    p=m['pricing']
    try: pi=float(p['prompt'])*1e6; po=float(p['completion'])*1e6
    except: continue
    if re.search(r'jev|typesafe|claude|gpt-5|gpt-4\.1|gpt-4o|gemini|llama|qwen|gemma|mistral|deepseek|glm|grok|ministral',m['id']) :
        print(f"{m['id']:50s} {pi:7.3f} {po:7.3f} {m.get('context_length')}")
