import os, json, time, urllib.request, urllib.parse, random
from http.server import BaseHTTPRequestHandler

def get_env(names):
    for n in names:
        v = os.environ.get(n)
        if v: return v.strip().strip('"').strip("'")
    return ""

KV_URL = get_env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL","UPSTASH_REST_URL","KV_URL"]).rstrip("/")
KV_TOKEN = get_env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN","UPSTASH_REST_TOKEN"])
if not KV_TOKEN:
    KV_TOKEN = get_env(["KV_REST_API_READ_ONLY_TOKEN"])

ADMIN_KEY = get_env(["ADMIN_KEY"]) or "venus727"
BINANCE_BASE = get_env(["BINANCE_BASE"]) or "https://api.binance.com"
if "vision" in BINANCE_BASE: BINANCE_BASE="https://api.binance.com"

STATE_KEY="VENUS_V727_9_FINAL"
LOCK_KEY="VENUS_TAB_LOCK_V9"

def kv_get(key):
    if not KV_URL or not KV_TOKEN: return None, "no kv"
    try:
        # Correct Upstash pipeline API
        body = json.dumps([["GET", key]]).encode()
        req = urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization": f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            # data = [{"result": "..."}] or [["result"]]
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict):
                    res = first.get("result")
                elif isinstance(first, list):
                    res = first[1] if len(first)>1 else None
                else:
                    res = first
            else:
                res = data.get("result") if isinstance(data, dict) else None
            if not res: return None, "empty result"
            try:
                return json.loads(res), None
            except:
                return res, None
    except Exception as e:
        return None, str(e)

def kv_set(key, obj):
    if not KV_URL or not KV_TOKEN: return False, "no kv"
    try:
        val = json.dumps(obj)
        body = json.dumps([["SET", key, val]]).encode()
        req = urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization": f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            txt = r.read().decode()
            # Success if contains OK
            if "OK" in txt:
                return True, None
            return False, txt[:200]
    except Exception as e:
        return False, str(e)

def get_binance():
    try:
        req = urllib.request.Request(f"{BINANCE_BASE}/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data=json.loads(r.read().decode())
            m={}
            for t in data:
                if t["symbol"] in ["BTCUSDT","SOLUSDT"]:
                    m[t["symbol"]]={"price":float(t["lastPrice"]),"change":float(t["priceChangePercent"]),"vol":float(t["quoteVolume"])/1e6}
            return m
    except:
        return {"BTCUSDT":{"price":60000,"change":-0.3,"vol":8553},"SOLUSDT":{"price":150,"change":-0.13,"vol":1339}}

def load_state():
    s,err = kv_get(STATE_KEY)
    if not s: s={"cap":1000.0,"bank":0.0,"daily_net":0.0,"gross":0.0,"fee_real":0.0,"wins":0,"loss":0,"total":0,"scan":0,"sharks":0,"open_trades":[],"closed":[],"btc_change":0.0,"last_scan":0}
    return s, err

def do_cron():
    state, get_err = load_state()
    now=int(time.time())
    lock,_ = kv_get(LOCK_KEY)
    locked=False
    if lock and isinstance(lock, dict):
        if now-int(lock.get("t",0))<12: locked=True
    binance=get_binance()
    state["btc_change"]=binance.get("BTCUSDT",{}).get("change",0)
    state["scan"]=state.get("scan",0)+1
    new_open=[]
    for tr in state.get("open_trades",[]):
        tr["age"]=now-tr.get("opened",now)
        sym=tr["symbol"]; entry=tr["entry"]
        if sym=="BTC": cur=binance.get("BTCUSDT",{}).get("price",entry); pct=(cur-entry)/entry*100 if entry else 0
        elif sym=="SOL": cur=binance.get("SOLUSDT",{}).get("price",entry); pct=(cur-entry)/entry*100 if entry else 0
        else: pct=tr.get("pct",0)+random.uniform(-0.6,0.6)
        tr["pct"]=pct; fee=0.002 if sym in ["BTC","SOL"] else 0.008; pos=10.0; gross=pct/100*pos; net=gross-(pos*fee*2); tr["net"]=net; tr["peak"]=max(tr.get("peak",pct),pct)
        close=False; reason=""
        if tr["age"]>=240 and net>0.02: close=True; reason="TP 240s"
        elif pct>=0.8: close=True; reason=f"TP {pct:.2f}%"
        elif pct<=-4.0: close=True; reason=f"SL {pct:.2f}%"
        elif tr["age"]>60 and pct<tr.get("peak",pct)-0.6: close=True; reason="TRAIL"
        if close:
            state["closed"].insert(0,{"symbol":sym,"net":net,"reason":reason,"pct":pct,"age":tr["age"]}); state["closed"]=state["closed"][:20]
            state["cap"]+=net; state["daily_net"]+=net; state["gross"]+=gross; state["fee_real"]+=pos*fee*2
            state["wins"]+=1 if net>0 else 0; state["loss"]+=1 if net<=0 else 0; state["total"]+=1
        else: new_open.append(tr)
    state["open_trades"]=new_open
    sharks=0
    if len(state["open_trades"])<3 and not locked:
        needed=3-len(state["open_trades"])
        cands=[{"symbol":"SOL","entry":binance.get("SOLUSDT",{}).get("price",150)},{"symbol":"BTC","entry":binance.get("BTCUSDT",{}).get("price",60000)},{"symbol":"qOMPUTE","entry":0.05}]
        for i in range(needed):
            c=cands[i%len(cands)]
            if any(t["symbol"]==c["symbol"] for t in state["open_trades"]): continue
            state["open_trades"].append({"symbol":c["symbol"],"entry":c["entry"],"pct":0.0,"peak":0.0,"net":-0.02 if c["symbol"]!="qOMPUTE" else -0.2,"opened":now,"age":0})
            sharks+=1
        kv_set(LOCK_KEY,{"t":now})
    state["sharks"]=sharks if sharks else state.get("sharks",0)
    ok, set_err = kv_set(STATE_KEY, state)
    return {"ok":ok,"cap":state["cap"],"open":len(state["open_trades"]),"scan":state["scan"],"sharks":state["sharks"],"btc":state["btc_change"],"kv_write":ok,"kv_url_exists":bool(KV_URL),"kv_token_exists":bool(KV_TOKEN),"get_err":str(get_err)[:100] if get_err else None,"set_err":str(set_err)[:200] if set_err else None}

def render(state, binance):
    btc=state.get("btc_change",0); cap=state.get("cap",1000); scan=state.get("scan",0)
    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v727.9</title>
<style>body{{background:#000;color:#0f8;font-family:monospace;margin:0}} .top{{background:#111;padding:8px;border-bottom:2px solid #0f8}} .grid{{display:grid;grid-template-columns:repeat(6,1fr);text-align:center;border-bottom:1px solid #333}} .grid div{{padding:8px 2px;border-right:1px solid #333}} .box{{background:#332200;color:#fc0;border:2px solid #fa0;padding:8px;margin:8px}}</style>
<meta http-equiv="refresh" content="10"></head><body>
<div class="top">VENUS v727.9 PIPELINE FIX - TP 0.8% | SCAN #{scan} BTC {btc:.2f}%</div>
<div class="grid"><div>CAP<br>${cap:.2f}</div><div>DAILY<br>${state.get('daily_net',0):+.2f}</div><div>GROSS<br>${state.get('gross',0):.2f}</div><div>FEE<br>${state.get('fee_real',0):.2f}</div><div>W/L/T<br>{state.get('wins',0)}W/{state.get('loss',0)}L</div><div>BANK<br>${state.get('bank',0):.2f}</div></div>
<div class="box">SCAN #{scan} - POST PIPELINE - UPSTASH_ + KV_ SUPPORTED - TAB LOCK 12s</div>
<div style="padding:10px">OPEN {len(state.get('open_trades',[]))} trades<br>"""
    for tr in state.get("open_trades",[]):
        html+=f"<div>{tr['symbol']} {tr.get('pct',0):.2f}% NET ${tr.get('net',0):.3f} AGE {tr.get('age',0)}s</div>"
    if not state.get("open_trades"): html+="<div>Waiting... CLICK CRON</div>"
    html+=f"</div><div style='text-align:center;padding:10px;color:#555'>v727.9 | KV:{'OK' if KV_URL else 'MISS'} SCAN #{scan} | <a href='/api/cron?key={ADMIN_KEY}&cron=1' style='color:#0f8'>CRON</a> | <a href='/api/reset?key={ADMIN_KEY}' style='color:#0f8'>RESET</a></div>"
    html+=f"<div style='text-align:center;padding:20px'><a href='/api/cron?key={ADMIN_KEY}&cron=1' style='background:#0f8;color:#000;padding:14px 24px;text-decoration:none;font-weight:bold'>CLICK TO START - CRON</a></div></body></html>"
    return html

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        p=urlparse(self.path); qs=parse_qs(p.query); key=qs.get("key",[""])[0]
        if p.path.startswith("/api/cron") or "cron" in qs:
            if key!=ADMIN_KEY and "cron" not in qs: self.send_response(403); self.end_headers(); return
            res=do_cron(); self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(json.dumps(res).encode()); return
        if p.path.startswith("/api/reset"):
            if key!=ADMIN_KEY: self.send_response(403); self.end_headers(); return
            st={"cap":1000.0,"bank":0.0,"daily_net":0.0,"gross":0.0,"fee_real":0.0,"wins":0,"loss":0,"total":0,"scan":0,"sharks":0,"open_trades":[],"closed":[],"btc_change":0.0,"last_scan":int(time.time())}
            ok,err = kv_set(STATE_KEY, st); kv_set(LOCK_KEY,{"t":0})
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"ok":ok,"err":err,"kv":bool(KV_URL and KV_TOKEN)}).encode()); return
        if p.path.startswith("/api/debug") or p.path.startswith("/api/state"):
            st,err = load_state(); binance=get_binance()
            dbg={"state":st,"binance":binance,"has_kv":bool(KV_URL and KV_TOKEN),"kv_url":KV_URL[:50] if KV_URL else "MISSING","get_err":str(err)[:200] if err else None}
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps(dbg).encode()); return
        st,_=load_state(); binance=get_binance(); h=render(st,binance)
        self.send_response(200); self.send_header("Content-Type","text/html"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(h.encode())
    def do_POST(self): self.do_GET()
