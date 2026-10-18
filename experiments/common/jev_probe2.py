import os,httpx,json,time
from dotenv import load_dotenv
load_dotenv()
h={"Authorization":"Bearer "+os.environ['OPENROUTER_API_KEY']}
body={"model":"typesafe/jev-1.14","state":["Ґеральт убив дракона у Бруґе. Йому заплатили."],
 "questions":{"a":{"type":"noul","instructions":"Чи отримав Ґеральт гроші?"},
 "b":{"type":"score","criteria":["worse","unchanged","better"],"instructions":"Як змінилось ставлення?"},
 "c":{"type":"choice","criteria":{"yes":"так","no":"ні"},"instructions":"Чи вбив він дракона?"}}}
t=time.time()
r=httpx.post("https://openrouter.ai/api/alpha/decisions",headers=h,json=body,timeout=60)
print(r.status_code,round(time.time()-t,2),r.text[:1500])
