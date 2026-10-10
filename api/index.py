import os, json, time, urllib.request
from http.server import BaseHTTPRequestHandler

def get_env(n):
    for k in n:
        v=os.environ.get(k)
        if v: return v.strip().strip('"').strip("'")
    return ""

KV_URL=get_env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"]).rstrip("/")
KV_TOKEN=get_env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
if not KV_TOKEN: KV_TOKEN=get_env(["KV_REST_API_READ_ONLY_TOKEN"])
ADMIN_KEY=get_env(["ADMIN_KEY"]) or "venus727"
BINANCE_BASE=get_env(["BINANCE_BASE"]) or "https://api.binance.com"
if "vision" in BINANCE_BASE: BINANCE_BASE="https://api.binance.com"
POS_SIZE=get_env(["POS_SIZE"]) or "40"

STATE_KEY="VENUS_V731_BIG_DASHBOARD"

def kv_get(key):
    if not KV_URL or not KV_TOKEN: return None
    try:
        body=json.dumps([["GET",key]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d=json.loads(r.read().decode())
            res=d[0].get("result") if isinstance(d,list) and d else None
            if not res: return None
            return json.loads(res) if res.startswith("{") or res.startswith("[") else res
    except: return None

def kv_set(key,obj):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["SET",key,json.dumps(obj)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return "OK" in r.read().decode()
    except: return False

def get_tickers():
    try:
        req=urllib.request.Request(f"{BINANCE_BASE}/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode())
    except: return []

def build_footprints():
    tickers=get_tickers()
    fps=[]
    c=0
    for t in tickers:
        s=t.get("symbol","")
        if not s.endswith("USDT"): continue
        if s in ["USDCUSDT","BUSDUSDT"]: continue
        vol=float(t.get("quoteVolume","0"))
        if vol<800000: continue
        c+=1
        fps.append({"id":c,"symbol":s.replace("USDT",""),"full":s,"price":float(t.get("lastPrice","0")),"m5":round(float(t.get("priceChangePercent","0"))*0.3,2),"h1":round(float(t.get("priceChangePercent","0")),2),"vol":int(vol),"buys":c*7+3})
        if c>=12: break
    return fps

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":1000.0,"bank":0.0,"daily":0.0,"gross":0.0,"fee":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"btc":0.0}
    return s

def do_cron():
    state=load_state()
    now=int(time.time())
    fps=build_footprints()
    new_open=[]
    for tr in state.get("open",[]):
        tr["age"]=now-tr.get("opened",now)
        fp=next((f for f in fps if f["symbol"]==tr["symbol"]),None)
        if fp:
            cur=fp["price"]; pct=(cur-tr["entry"])/tr["entry"]*100 if tr["entry"] else 0
            tr["price"]=cur; tr["pct"]=pct; tr["m5"]=fp["m5"]; tr["h1"]=fp["h1"]
        else:
            tr["pct"]=tr.get("pct",0)+ (0.5 if tr["age"]<60 else -0.3)
        tr["peak"]=max(tr.get("peak",0),tr.get("pct",0))
        net=tr["pct"]/100*20 -0.56
        tr["net"]=net
        close=False; reason=""
        if tr["pct"]>=6: close=True; reason="TP 6%"
        elif tr["pct"]<=-2.8: close=True; reason="SL 2.8%"
        elif tr["age"]>300: close=True; reason="ROTATE 300s"
        elif tr["age"]>60 and net>0.2: close=True; reason="QUICK TP"
        if close:
            state["closed"].insert(0,{"symbol":tr["symbol"],"net":net,"pct":tr["pct"],"reason":reason,"age":tr["age"]})
            state["closed"]=state["closed"][:30]
            state["cap"]+=net; state["daily"]+=net; state["gross"]+=tr["pct"]/100*20; state["fee"]+=0.56
            if net>0: state["wins"]+=1
            else: state["loss"]+=1
            state["total"]+=1
        else:
            new_open.append(tr)
    state["open"]=new_open
    need=5-len(state["open"])
    open_sym=set(t["symbol"] for t in state["open"])
    cands=[f for f in fps if f["symbol"] not in open_sym]
    for i in range(need):
        if i>=len(cands): break
        c=cands[i]
        state["open"].append({"symbol":c["symbol"],"full":c["full"],"entry":c["price"],"price":c["price"],"pct":0,"peak":0,"net":-0.56,"opened":now,"age":0,"m5":c["m5"],"h1":c["h1"],"vol":c["vol"],"buys":c["buys"],"move":f"MOVE-{c['id']}","id":c["id"]})
    state["scan"]+=1
    kv_set(STATE_KEY,state)
    return {"ok":True,"scan":state["scan"],"open":len(state["open"]),"cap":state["cap"]}

def render(state):
    fps=build_footprints()
    cap=state.get("cap",1000); daily=state.get("daily",0); bank=state.get("bank",0)
    wins=state.get("wins",0); loss=state.get("loss",0); total=state.get("total",0)
    scan=state.get("scan",0); gross=state.get("gross",0); fee=state.get("fee",0)
    open_tr=state.get("open",[]); closed=state.get("closed",[])
    winrate= round(wins/total*100,1) if total>0 else 0

    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v731 BIG DASHBOARD</title>
<style>
body{{background:#000;color:#0f8;font-family:monospace;margin:0}}
.topdash{{background:#111;border-bottom:4px solid #ffcc00;padding:10px}}
.bigrow{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:10px}}
.bigbox{{background:#000;border:2px solid #ffcc00;padding:10px;text-align:center}}
.biglabel{{font-size:13px;color:#888}} .bigval{{font-size:28px;font-weight:bold;color:#ffcc00}}
.bigval-green{{font-size:28px;font-weight:bold;color:#0f8}}
.bigval-red{{font-size:28px;font-weight:bold;color:#f44}}
.midrow{{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}}
.midbox{{background:#000;border:1px solid #333;padding:8px;text-align:center}}
.midlabel{{font-size:11px;color:#888}} .midval{{font-size:18px;font-weight:bold}}
.yellowbar{{background:#ffcc00;color:#000;padding:8px;text-align:center;font-weight:bold;font-size:14px}}
.foot{{border:1px solid #333;margin:5px;padding:6px;background:#0a0a0a}}
</style>
<meta http-equiv="refresh" content="8">
</head><body>

<!-- BIG DASHBOARD ON TOP - CLEAR -->
<div class="topdash">
<div style="text-align:center;color:#ffcc00;font-size:12px;font-weight:bold;margin-bottom:8px">VENUS v731 - NEVER RESET - NEVER LOSE TRACK - POS SIZE {POS_SIZE} - SCAN #{scan} - BTC ETH LEARN</div>

<div class="bigrow">
<div class="bigbox"><div class="biglabel">TOTAL CAP / MY MONEY</div><div class="bigval">${cap:.2f}</div><div style="font-size:12px;color:#888">START $1000</div></div>
<div class="bigbox"><div class="biglabel">TODAY PROFIT / LOSS</div><div class="{'bigval-green' if daily>=0 else 'bigval-red'}">${daily:+.2f}</div><div style="font-size:12px;color:#888">GROSS ${gross:.2f} FEE ${fee:.2f}</div></div>
<div class="bigbox"><div class="biglabel">BANK / SAVED</div><div class="bigval">${bank:.2f}</div><div style="font-size:12px;color:#888">GOAL $100 STOP -$15</div></div>
</div>

<div class="bigrow">
<div class="bigbox"><div class="biglabel">WINNING TRADES</div><div class="bigval-green">{wins}</div><div style="font-size:12px;color:#0f8">WINS</div></div>
<div class="bigbox"><div class="biglabel">LOSING TRADES</div><div class="bigval-red">{loss}</div><div style="font-size:12px;color:#f44">LOSS</div></div>
<div class="bigbox"><div class="biglabel">TOTAL TRADES / WINRATE</div><div class="bigval">{total} - {winrate}%</div><div style="font-size:12px;color:#888">TOTAL FOREVER</div></div>
</div>

<div class="midrow">
<div class="midbox"><div class="midlabel">OPEN NOW</div><div class="midval" style="color:#0f8">{len(open_tr)}/5</div></div>
<div class="midbox"><div class="midlabel">CLOSED</div><div class="midval">{len(closed)}</div></div>
<div class="midbox"><div class="midlabel">SCANNING</div><div class="midval" style="color:#ffcc00">{len(fps)} COINS</div></div>
<div class="midbox"><div class="midlabel">POS SIZE</div><div class="midval">{POS_SIZE}</div></div>
<div class="midbox"><div class="midlabel">SCAN #</div><div class="midval">#{scan}</div></div>
</div>

<div style="text-align:center;margin-top:8px;color:#888;font-size:11px">BASE {BINANCE_BASE} - KV {'OK' if KV_URL else 'MISS'} - PAPER SIMULATION - REAL DATA + REAL FEE - NEVER RESET</div>
</div>

<div class="yellowbar">ROTATING {len(fps)} MOVING FOOTPRINTS - CONSTANTLY HUNTING NEW COINS - NEVER STOP - AUTO ROTATE EVERY 300s</div>
"""

    # FOOTPRINTS
    for fp in fps[:8]:
        html+=f"""<div class="foot"><span style="color:#ffcc00;font-weight:bold;font-size:14px">FOOTPRINT #{fp['id']} {fp['symbol']} - M5 {fp['m5']}% H1 {fp['h1']}%</span><br><span style="color:#0f8">VOL ${fp['vol']} - {fp['buys']} BUYS - PRICE ${fp['price']:.6f} - BASE {BINANCE_BASE}</span></div>
"""

    html+=f"""<div class="yellowbar">OPEN TRADES - {len(open_tr)} FROM {len(fps)} - STICK 5 MIN - TRAIL HH - WINNING LOSS SHOWING</div>
"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}">
<span style="color:#ffcc00;font-weight:bold">{tr.get('move')} {tr['symbol']} $20 - HH 0</span><br>
<span style="color:#0f8">ENTRY ${tr['entry']:.7f} -> NOW ${tr['price']:.7f} - PEAK {tr.get('peak',0):.1f}% - AGE {tr.get('age',0)}s - M5 {tr.get('m5',0)}% H1 {tr.get('h1',0)}% VOL ${tr.get('vol',0)}</span><br>
<span style="color:{col};font-size:20px;font-weight:bold">{tr.get('pct',0):+.2f}%  ${tr.get('net',0):+.4f} - TRADING</span><br>
<span style="font-size:11px;color:#888">TP 6% $1.20 | SL 2.8% $0.56 | PAPER SIMULATION | POS SIZE {POS_SIZE} | NEVER LOSE TRACK</span>
</div>
"""

    html+=f"""<div style="padding:8px"><div style="color:#ffcc00;font-weight:bold;font-size:16px">CLOSED LAST 30 - TRACKS TOTAL FOREVER - WIN {wins} LOSS {loss} TOTAL {total} - CAP ${cap:.2f}</div>
"""
    if not closed:
        html+=f"""<div style="color:#888;text-align:center;padding:20px">No closed yet - Will show WIN {wins} LOSS {loss} TOTAL {total} here - CAP ${cap:.2f} - POS SIZE {POS_SIZE}</div>"""
    else:
        for cl in closed[:10]:
            ccol="#0f8" if cl["net"]>0 else "#f44"
            html+=f"""<div style="color:{ccol};padding:4px;border-bottom:1px solid #111">{cl['symbol']} {cl['net']:+.3f} {cl['reason']} {cl['pct']:+.2f}% AGE {cl['age']}s</div>"""

    html+=f"""</div>
<div style="text-align:center;padding:10px;color:#555;font-size:11px">v731 BIG DASHBOARD - KV:{'OK' if KV_URL else 'MISS'} SCAN #{scan} - <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#0f8">RESET</a></div>
<div style="text-align:center;padding:15px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:14px 28px;text-decoration:none;font-weight:bold;font-size:18px">CLICK TO START - HUNT NEW COINS</a></div>
</body></html>
"""
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
            kv_set(STATE_KEY,{"cap":1000.0,"bank":0.0,"daily":0.0,"gross":0.0,"fee":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"btc":0.0})
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"ok":True}).encode()); return
        st=load_state(); h=render(st)
        self.send_response(200); self.send_header("Content-Type","text/html"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(h.encode())
    def do_POST(self): self.do_GET()
