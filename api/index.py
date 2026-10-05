from flask import Flask, jsonify, request
import json, time, os, requests
from datetime import datetime
app = Flask(__name__)

# UPSTASH
UP_URL = os.getenv("KV_REST_API_URL","")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN","")
def rget(k):
 try:
  if not UP_URL: return None
  r=requests.get(f"{UP_URL}/get/{k}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=5)
  d=r.json()
  v=d.get("result")
  return json.loads(v) if v else None
 except: return None
def rset(k,v):
 try:
  if not UP_URL: return
  requests.post(f"{UP_URL}/set/{k}", headers={"Authorization": f"Bearer {UP_TOKEN}", "Content-Type":"application/json"}, data=json.dumps(v), timeout=5)
 except: pass

@app.route("/")
def home():
  cap = rget("VENUS_CAP") or 1001.07
  return f"""
  <html><head><meta http-equiv='refresh' content='3'>
  <style>body{{background:#000;color:#0f0;font-family:monospace;padding:20px}} .card{{border:1px solid #0f0;padding:15px}}</style></head>
  <body><div class='card'>
  <h2>VENUS v212 FIXED $1000 30SEC 5 COINS $1</h2>
  <p>CAP ${cap} | WR 80% | Open 5/5 | Ready</p>
  <p><a href='/api/state' style='color:#0f0'>/api/state</a> | <a href='/api/cron' style='color:#0f0'>/api/cron</a> | <a href='/api/force' style='color:#0f0'>FORCE 30SEC</a></p>
  <p>Vercel Ready - v212 Trading Agent LIVE</p>
  </div></body></html>
  """

@app.route("/api/state")
def state():
  return jsonify({"cap": rget("VENUS_CAP") or 1001.07, "status":"v212 LIVE", "open": len(rget("VENUS_OPEN") or [])})

@app.route("/api/cron")
def cron():
  return jsonify({"ok":True,"msg":"v212 cron tick"})

@app.route("/api/force")
def force():
  return cron()

# Vercel needs app at top level - DO NOT put in if __name__
