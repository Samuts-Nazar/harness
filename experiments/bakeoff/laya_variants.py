"""Does the state wire format change Laya's accuracy? list of strings vs one document string vs {"document":...}."""
import json, time, httpx
items = json.loads(open("experiments/bakeoff/testset/judgments.json").read())
rows = [(it, c) for it in items for c in ([it["en"], it["uk"]] if it["lang_mode"] == "both" else [it["en"]])]
for model in ("english", "multilingual"):
    for name, fmt in (("list", lambda s: s), ("string", lambda s: "\n".join(s)), ("document", lambda s: {"document": "\n".join(s)})):
        ok = n = 0
        t = time.time()
        for it, c in rows:
            body = {"model": model, "state": fmt(c["state"]),
                    "questions": {"q": {"type": "noul", "instructions": c["q"]}}}
            r = httpx.post("http://127.0.0.1:8765/v1/systemone", json=body, timeout=120)
            if r.status_code != 200:
                continue
            p = r.json()["answers"]["q"]["noul"]
            ok += (p >= 0.5) == it["gold"]; n += 1
        print(model, name, n, round(ok / max(n, 1), 3), round((time.time() - t) / max(n, 1), 3), "s/call", flush=True)
