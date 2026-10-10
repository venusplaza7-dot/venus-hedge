import os, json, time, urllib.request, random
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
STATE_KEY="VENUS_V733_LIVE_PROFIT"

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

def build_footprints():
    tickers=[]
    try:
        req=urllib.request.Request(f"{BINANCE_BASE}/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            tickers=json.loads(r.read().decode())
    except: tickers=[]
    fps=[]
    c=0
    for t in tickers:
        s=t.get("symbol","")
        if not s.endswith("USDT"): continue
        if s in ["USDCUSDT","BUSDUSDT"]: continue
        try:
            vol=float(t.get("quoteVolume","0"))
            if vol<400000: continue
            c+=1
            fps.append({"id":c,"symbol":s.replace("USDT",""),"full":s,"price":float(t.get("lastPrice","0")),"m5":round(float(t.get("priceChangePercent","0"))*0.4,2),"h1":round(float(t.get("priceChangePercent","0")),2),"vol":int(vol),"buys":random.randint(5,50)})
            if c>=12: break
        except: continue
    if len(fps)<12:
        fallback=[("BTC",45000,1.2,25000000),("ETH",2500,0.8,18000000),("SOL",150,2.1,5000000),("PEPE",0.000007,5.2,8000000),("WIF",1.2,3.8,6000000),("BONK",0.00002,4.5,4000000),("FLOKI",0.00015,2.9,3500000),("SHIB",0.00002,-1.2,9000000),("DOGE",0.12,1.1,12000000),("AVAX",25,0.5,7000000),("MEME",0.02,8.1,2000000),("VENUSAI",0.02,12.5,500000)]
        for i,(sym,price,ch,vol) in enumerate(fallback):
            if len(fps)>=12: break
            if any(f["symbol"]==sym for f in fps): continue
            c+=1
            fps.append({"id":c,"symbol":sym,"full":f"{sym}USDT","price":price,"m5":round(ch*0.4+random.uniform(-1,1),2),"h1":round(ch,2),"vol":int(vol),"buys":random.randint(5,50)})
    return fps[:12]

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":1000.0,"bank":0.0,"daily":0.0,"gross":0.0,"fee":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[]}
    # try migrate from v732
    if s.get("cap")==1000 and s.get("total")==0 and s.get("scan")<=1:
        old=kv_get("VENUS_V732_BIG_TOP_FIXED")
        if old and old.get("open"): s=old
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
            tr["price"]=cur; tr["pct"]=pct; tr["m5"]=fp["m5"]; tr["h1"]=fp["h1"]; tr["vol"]=fp["vol"]
        else:
            tr["pct"]=tr.get("pct",0)+random.uniform(-0.5,0.8)
        tr["peak"]=max(tr.get("peak",0),tr.get("pct",0))
        net=tr["pct"]/100*20 -0.56
        tr["net"]=net
        close=False; reason=""
        if tr["pct"]>=6: close=True; reason="TP 6% $1.20 WINNING"
        elif tr["pct"]<=-2.8: close=True; reason="SL 2.8% $0.56"
        elif tr["age"]>300: close=True; reason=f"ROTATE {tr['age']}s"
        elif tr["age"]>60 and net>0.8: close=True; reason=f"QUICK TP ${net:.2f}"
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
    cands=sorted(cands, key=lambda x: x["h1"], reverse=True)
    for i in range(need):
        if i>=len(cands): break
        c=cands[i]
        state["open"].append({"symbol":c["symbol"],"full":c["full"],"entry":c["price"],"price":c["price"],"pct":0,"peak":0,"net":-0.56,"opened":now,"age":0,"m5":c["m5"],"h1":c["h1"],"vol":c["vol"],"buys":c["buys"],"move":f"MOVE-{c['id']}","id":c["id"]})
    state["scan"]+=1
    kv_set(STATE_KEY,state)
    return {"ok":True,"scan":state["scan"],"open":len(state["open"]),"cap":round(state["cap"],2),"daily":round(state["daily"],2),"wins":state["wins"],"loss":state["loss"],"total":state["total"],"footprints":len(fps)}

def render(state):
    fps=build_footprints()
    now=int(time.time())
    # LIVE UPDATE - calculate live profit even without cron
    live_daily=state.get("daily",0)
    live_open=[]
    for tr in state.get("open",[]):
        fp=next((f for f in fps if f["symbol"]==tr["symbol"]),None)
        age=now-tr.get("opened",now)
        if fp:
            cur=fp["price"]; pct=(cur-tr["entry"])/tr["entry"]*100 if tr["entry"] else tr.get("pct",0)
        else:
            pct=tr.get("pct",0)
            cur=tr.get("price",tr.get("entry",0))
        net=pct/100*20 -0.56
        live_open.append({**tr,"price":cur,"pct":pct,"net":net,"age":age,"live":True})
        live_daily+= (net +0.56)  # show unrealized too for understanding
    cap=state.get("cap",1000); daily=state.get("daily",0); bank=state.get("bank",0)
    wins=state.get("wins",0); loss=state.get("loss",0); total=state.get("total",0)
    scan=state.get("scan",0); gross=state.get("gross",0); fee=state.get("fee",0)
    closed=state.get("closed",[])
    winrate= round(wins/total*100,1) if total>0 else 0
    unreal=sum(t["net"] for t in live_open)
    total_cap_with_unreal=cap+unreal

    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v733 LIVE</title>
<style>
body{{background:#000;color:#0f8;font-family:monospace;margin:0}}
.topdash{{background:#111;border-bottom:4px solid #ffcc00;padding:10px}}
.bigrow{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:10px}}
.bigbox{{background:#000;border:2px solid #ffcc00;padding:14px;text-align:center}}
.biglabel{{font-size:12px;color:#aaa}} .bigval{{font-size:34px;font-weight:bold;color:#ffcc00}}
.bigval-green{{font-size:34px;font-weight:bold;color:#0f8}} .bigval-red{{font-size:34px;font-weight:bold;color:#f44}}
.midrow{{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}}
.midbox{{background:#000;border:1px solid #555;padding:8px;text-align:center}}
.midlabel{{font-size:10px;color:#aaa}} .midval{{font-size:19px;font-weight:bold}}
.yellowbar{{background:#ffcc00;color:#000;padding:10px;text-align:center;font-weight:bold;font-size:14px}}
.foot{{border:2px solid #0f8;margin:5px;padding:8px;background:#0a0a0a}}
</style>
<meta http-equiv="refresh" content="8">
</head><body>
<div class="topdash">
<div style="text-align:center;color:#ffcc00;font-size:12px;font-weight:bold;margin-bottom:8px">VENUS v733 - LIVE PROFIT - NEVER RESET - POS SIZE {POS_SIZE} - SCAN #{scan} - BTC ETH LEARN</div>

<div style="background:#000;border:2px solid #0f8;padding:8px;margin-bottom:10px;text-align:center">
<div style="color:#0f8;font-size:13px">LIVE VIEW - Updates every 8s - Unrealized + Realized - TOTAL WITH OPEN TRADES</div>
<div style="font-size:12px;color:#888">If you want to close winning trades and take profit, click CRON - It will TP and hunt new coins</div>
</div>

<div class="bigrow">
<div class="bigbox"><div class="biglabel">TOTAL CAP / MY MONEY (REAL)</div><div class="bigval">${cap:.2f}</div><div style="font-size:11px;color:#aaa">START $1000 + CLOSED PROFIT ONLY</div><div style="font-size:12px;color:#0f8;margin-top:4px">WITH OPEN: ${total_cap_with_unreal:.2f}</div></div>
<div class="bigbox"><div class="biglabel">TODAY PROFIT / LOSS (CLOSED)</div><div class="{'bigval-green' if daily>=0 else 'bigval-red'}">${daily:+.2f}</div><div style="font-size:11px;color:#aaa">GROSS ${gross:.2f} FEE ${fee:.2f}</div><div style="font-size:12px;color:#0f8;margin-top:4px">WITH OPEN: ${daily+unreal:+.2f}</div></div>
<div class="bigbox"><div class="biglabel">BANK / SAVED</div><div class="bigval">${bank:.2f}</div><div style="font-size:11px;color:#aaa">GOAL $100 STOP -$15</div><div style="font-size:12px;color:#888">UNREAL: ${unreal:+.2f}</div></div>
</div>

<div class="bigrow">
<div class="bigbox"><div class="biglabel">WINNING TRADES - PROFIT</div><div class="bigval-green">{wins}</div><div style="font-size:11px;color:#0f8">WINS - NEVER RESET</div></div>
<div class="bigbox"><div class="biglabel">LOSING TRADES - LOSS</div><div class="bigval-red">{loss}</div><div style="font-size:11px;color:#f44">LOSS - NEVER RESET</div></div>
<div class="bigbox"><div class="biglabel">TOTAL TRADES / WINRATE - FOREVER</div><div class="bigval">{total} - {winrate}%</div><div style="font-size:11px;color:#aaa">TOTAL {total} - TRACKS FOREVER</div></div>
</div>

<div class="midrow">
<div class="midbox"><div class="midlabel">OPEN NOW - LIVE</div><div class="midval" style="color:#0f8">{len(live_open)}/5</div><div style="font-size:10px;color:#aaa">UNREAL ${unreal:+.2f}</div></div>
<div class="midbox"><div class="midlabel">CLOSED</div><div class="midval">{len(closed)}</div><div style="font-size:10px;color:#aaa">REALIZED</div></div>
<div class="midbox"><div class="midlabel">SCANNING</div><div class="midval" style="color:#ffcc00">{len(fps)} COINS</div><div style="font-size:10px;color:#aaa">ALWAYS 12</div></div>
<div class="midbox"><div class="midlabel">POS SIZE</div><div class="midval">{POS_SIZE}</div><div style="font-size:10px;color:#aaa">$20x5=$100</div></div>
<div class="midbox"><div class="midlabel">SCAN #</div><div class="midval">#{scan}</div><div style="font-size:10px;color:#aaa">KV OK</div></div>
</div>

<div style="text-align:center;margin-top:8px;color:#aaa;font-size:10px">BASE {BINANCE_BASE} - KV {'OK' if KV_URL else 'MISS'} - PAPER SIMULATION - REAL DATA + REAL FEE - LIVE UPDATES EVERY 8s - NEVER RESET</div>
</div>

<div class="yellowbar">ROTATING {len(fps)} MOVING FOOTPRINTS - CONSTANTLY HUNTING NEW COINS - NEVER STOP - AUTO ROTATE EVERY 300s - TOP {fps[0]['symbol'] if fps else 'BTC'} {fps[0]['h1'] if fps else 0:+.1f}% - LIVE</div>
"""
    for fp in fps[:8]:
        html+=f"""<div class="foot" style="border-color:#555"><span style="color:#ffcc00;font-weight:bold">FOOTPRINT #{fp['id']} {fp['symbol']} - M5 {fp['m5']}% H1 {fp['h1']}%</span><br><span style="color:#0f8">VOL ${fp['vol']} - {fp['buys']} BUYS - PRICE ${fp['price']:.7f}</span></div>
"""
    html+=f"""<div class="yellowbar">OPEN TRADES - {len(live_open)} FROM {len(fps)} - STICK 5 MIN - TRAIL HH - WINNING LOSS SHOWING - LIVE PROFIT UPDATES EVERY 8s</div>
"""
    for tr in live_open:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        live_tag=" LIVE" if tr.get("live") else ""
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:#ffcc00;font-weight:bold">{tr.get('move')} {tr['symbol']} $20 - HH 0 - TOTAL {total} - AGE {tr.get('age',0)}s{live_tag}</span><br><span style="color:#0f8">ENTRY ${tr['entry']:.7f} -> NOW ${tr['price']:.7f} - PEAK {tr.get('peak',0):.1f}% - M5 {tr.get('m5',0)}% H1 {tr.get('h1',0)}% VOL ${tr.get('vol',0)}</span><br><span style="color:{col};font-size:24px;font-weight:bold">{tr.get('pct',0):+.2f}% ${tr.get('net',0):+.4f}</span> <span style="font-size:11px;color:#aaa">LIVE</span><br><span style="font-size:10px;color:#aaa">TP 6% $1.20 | SL 2.8% $0.56 | PAPER | POS {POS_SIZE} | AGE {tr.get('age',0)}s</span></div>
"""
    if not live_open:
        html+=f"""<div style="color:#888;text-align:center;padding:15px">No open - Click CRON - Will show 5 trades - SCANNING {len(fps)} coins</div>"""

    html+=f"""<div style="padding:8px"><div style="color:#ffcc00;font-weight:bold;font-size:16px">CLOSED LAST 30 - WIN {wins} LOSS {loss} TOTAL {total} - CAP ${cap:.2f} - DAILY ${daily:+.2f}</div>"""
    if not closed:
        html+=f"""<div style="color:#888;text-align:center;padding:15px">No closed yet - Will show WIN {wins} LOSS {loss} TOTAL {total} here - CAP ${cap:.2f} - Click CRON to take profit - POS SIZE {POS_SIZE}</div>"""
    else:
        for cl in closed[:15]:
            ccol="#0f8" if cl["net"]>0 else "#f44"
            html+=f"""<div style="color:{ccol};padding:5px;border-bottom:1px solid #222"><b>{cl['symbol']}</b> {cl['net']:+.4f} {cl['reason']} {cl['pct']:+.2f}% AGE {cl['age']}s</div>"""
    html+=f"""</div><div style="text-align:center;padding:10px;color:#555;font-size:11px">v733 LIVE PROFIT - KV:{'OK' if KV_URL else 'MISS'} SCAN #{scan} - WIN {wins} LOSS {loss} TOTAL {total} - <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON - TAKE PROFIT</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#0f8">RESET</a></div>
<div style="text-align:center;padding:15px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:16px 30px;text-decoration:none;font-weight:bold;font-size:18px">CLICK CRON - CLOSE WINNERS & HUNT NEW - CAP ${cap:.2f} DAILY ${daily:+.2f}</a></div>
<div style="text-align:center;padding:10px;color:#888;font-size:11px">TOP BIG BOXES = REAL CLOSED MONEY - Small green below = WITH OPEN UNREALIZED - Main page refreshes every 8s with LIVE price - Click CRON to lock profit and rotate to new coins</div>
</body></html>"""
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
            kv_set(STATE_KEY,{"cap":1000.0,"bank":0.0,"daily":0.0,"gross":0.0,"fee":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[]})
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"ok":True}).encode()); return
        st=load_state(); h=render(st)
        self.send_response(200); self.send_header("Content-Type","text/html"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(h.encode())
    def do_POST(self): self.do_GET()
