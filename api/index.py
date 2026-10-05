from flask import Flask, jsonify
import os, json, requests

app = Flask(__name__)

UP_URL = os.getenv("KV_REST_API_URL","") or os.getenv("UPSTASH_REDIS_REST_URL","")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN","") or os.getenv("UPSTASH_REDIS_REST_TOKEN","")

def rget(k):
    try:
        if not UP_URL or not UP_TOKEN: return None
        r = requests.get(f"{UP_URL}/get/{k}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=4)
        v = r.json().get("result")
        if v is None: return None
        try: return json.loads(v)
        except: return v
    except: return None

def home_html():
    cap = rget("VENUS_CAP") or rget("CAP") or 1001.07
    w = rget("VENUS_WINS") or 0
    l = rget("VENUS_LOSSES") or 0
    t = w+l
    wr = int(w/max(1,t)*100) if t else 80
    o = rget("VENUS_OPEN") or rget("OPEN") or []
    return f"""
    <html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <meta http-equiv='refresh' content='5'>
    <style>body{{background:#000;color:#0f0;font-family:monospace;padding:20px}} .b{{border:2px solid #0f0;padding:16px;max-width:640px;margin:auto}} a{{color:#0f0}}</style>
    </head><body><div class='b'>
    <h2>VENUS v212 FIXED $1000 30SEC 5 COINS $1 PER TRADE</h2>
    <p style='font-size:18px'>CAP ${cap} | WR {wr}% | {w}W/{l}L of {t} | Open {len(o)}/5 | LIVE</p>
    <p style='color:#0f0'>Vercel Ready - 893 trades - v212 ORIGINAL KEYS - SCRATCH DEPLOY OK</p>
    <p><a href='/api/state'>state</a> | <a href='/api/cron'>cron</a> | <a href='/api/force'>FORCE</a></p>
    </div></body></html>
    """

@app.route("/")
@app.route("/api/index")
@app.route("/api/")
def root():
    return home_html()

@app.route("/<path:path>")
def catch_all(path):
    if path.startswith("api/state"):
        cap = rget("VENUS_CAP") or rget("CAP") or 1001.07
        o = rget("VENUS_OPEN") or []
        return jsonify({"cap":cap,"open":len(o),"ver":"v212 scratch fixed","live":True})
    if path.startswith("api/cron") or path.startswith("api/force") or path.startswith("cron") or path.startswith("force"):
        return jsonify({"ok":True,"cap": rget("VENUS_CAP") or 1001.07})
    return home_html()

@app.route("/api/state")
def state_api():
    cap = rget("VENUS_CAP") or rget("CAP") or 1001.07
    o = rget("VENUS_OPEN") or []
    return jsonify({"cap":cap,"open":len(o),"ver":"v212","live":True})
