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
BASES=["https://data-api.binance.vision","https://api.binance.com","https://api1.binance.com"]
POS_SIZE=get_env(["POS_SIZE"]) or "40"
STATE_KEY="VENUS_V738_REAL_PROFIT"

def kv_get(k):
    if not KV_URL or not KV_TOKEN: return None
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d=json.loads(r.read().decode())
            res=d[0].get("result") if isinstance(d,list) and d else None
            if not res: return None
            return json.loads(res) if res.startswith("{") or res.startswith("[") else res
    except: return None

def kv_set(k,obj):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["SET",k,json.dumps(obj)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return "OK" in r.read().decode()
    except: return False

def fetch_json(url):
    try:
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode())
    except: return None

def get_real_tickers():
    for base in BASES:
        data = fetch_json(f"{base}/api/v3/ticker/24hr")
        if data and len(data)>100:
            return data, base
    return [], BASES[0]

def get_klines(base, symbol, interval, limit=24):
    return fetch_json(f"{base}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}")

def build_uptrend():
    tickers, base = get_real_tickers()
    if not tickers: return [], base, 0
    pre=[]
    for t in tickers:
        s=t.get("symbol","")
        if not s.endswith("USDT"): continue
        if any(x in s for x in ["USDC","BUSD","FDUSD","TUSD","EUR","GBP","USDP","UP","DOWN"]): continue
        vol=float(t.get("quoteVolume","0"))
        if vol < 5000000: continue
        h1=float(t.get("priceChangePercent","0"))
        if not (2.5 <= h1 <= 15): continue
        if float(t.get("priceChange","0")) <=0: continue
        pre.append(t)
    pre = sorted(pre, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:35]

    fps=[]
    for t in pre:
        s=t.get("symbol")
        try:
            k5 = get_klines(base, s, "5m", 12)
            k1 = get_klines(base, s, "1h", 24)
            if not k5 or not k1 or len(k5)<6 or len(k1)<20: continue
            m5_last=float(k5[-1][4]); m5_prev=float(k5[-2][4])
            m5_pct=(m5_last-m5_prev)/m5_prev*100 if m5_prev else 0
            h1_last=float(k1[-1][4]); h1_prev=float(k1[-2][4])
            h1_pct=(h1_last-h1_prev)/h1_prev*100 if h1_prev else 0

            if not (0.15 <= m5_pct <= 2.2): continue
            if not (2.5 <= h1_pct <= 9.0): continue

            closes_1h=[float(x[4]) for x in k1[-20:]]
            ema20=sum(closes_1h)/len(closes_1h)
            if h1_last < ema20: continue

            vols_1h=[float(x[5]) for x in k1[-20:-1]]
            avg_vol=sum(vols_1h)/len(vols_1h) if vols_1h else 0
            last_vol=float(k1[-1][5])
            if avg_vol>0 and last_vol < avg_vol*1.15: continue

            high_5m=float(k5[-1][2])
            dist=(high_5m-m5_last)/m5_last*100
            if dist > 0.8: continue

            price=m5_last
            score=h1_pct*2 + m5_pct*3 + (last_vol/(avg_vol+1))*2
            fps.append({"symbol":s.replace("USDT",""),"full":s,"price":price,"m5":round(m5_pct,2),"h1":round(h1_pct,2),"vol":int(float(t.get("quoteVolume","0"))),"score":score,"base":base})
            time.sleep(0.08)
        except: continue

    fps=sorted(fps, key=lambda x: x["score"], reverse=True)[:10]
    for i,f in enumerate(fps): f["id"]=i+1
    return fps, base, len(tickers)

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":1000.0,"bank":0.0,"daily":0.0,"gross":0.0,"fee":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"base":""}
    return s

def process(state,fps,now):
    new_open=[]
    for tr in state.get("open",[]):
        tr["age"]=now-tr.get("opened",now)
        fp=next((f for f in fps if f["symbol"]==tr["symbol"]),None)
        if fp:
            cur=fp["price"]; entry=tr.get("entry",cur)
            tr["price"]=cur; tr["pct"]=(cur-entry)/entry*100 if entry else 0
            tr["m5"]=fp["m5"]; tr["h1"]=fp["h1"]
        tr["peak"]=max(tr.get("peak",tr.get("pct",0)),tr.get("pct",0))
        net=tr["pct"]/100*20 - 0.04
        tr["net"]=net
        close=False; reason=""
        if tr["pct"]>=1.1: close=True; reason=f"TP 1.1% REAL WIN"
        elif tr["pct"]<=-1.1: close=True; reason=f"SL -1.1% REAL"
        elif tr["age"]>180 and net>=0.12: close=True; reason=f"QUICK TP {tr['age']}s"
        elif tr["age"]>450: close=True; reason=f"ROTATE 450s"
        elif tr["age"]>90 and tr["pct"]<tr.get("peak",0)-0.6: close=True; reason=f"TRAIL -0.6% PEAK {tr.get('peak',0):.1f}%"
        if close:
            state["closed"].insert(0,{"symbol":tr["symbol"],"net":net,"pct":tr["pct"],"reason":reason,"age":tr["age"],"peak":tr.get("peak",0),"entry":tr.get("entry",0),"exit":tr.get("price",0)})
            state["closed"]=state["closed"][:50]
            state["cap"]+=net; state["daily"]+=net; state["gross"]+=tr["pct"]/100*20; state["fee"]+=0.04
            if net>0: state["wins"]+=1
            else: state["loss"]+=1
            state["total"]+=1
        else:
            new_open.append(tr)
    state["open"]=new_open
    if state["daily"] <= -12:
        return state
    need=3-len(state["open"])
    open_sym=set(t["symbol"] for t in state["open"])
    cands=[f for f in fps if f["symbol"] not in open_sym]
    for i in range(need):
        if i>=len(cands): break
        c=cands[i]
        state["open"].append({"symbol":c["symbol"],"full":c["full"],"entry":c["price"],"price":c["price"],"pct":0,"peak":0,"net":-0.04,"opened":now,"age":0,"m5":c["m5"],"h1":c["h1"],"vol":c["vol"],"move":f"MOVE-{c['id']}","id":c["id"]})
    state["scan"]=state.get("scan",0)+1
    return state

def do_cron():
    state=load_state(); now=int(time.time())
    fps, base, total = build_uptrend()
    if not fps:
        return {"ok":False,"error":"NO REAL UPTREND - Waiting for M5 0.15-2.2% + H1 2.5-9% + VOL spike - No chase","base":base,"total":total,"scan":state.get("scan",0)}
    state["base"]=base
    state=process(state,fps,now)
    kv_set(STATE_KEY,state)
    return {"ok":True,"scan":state["scan"],"open":len(state["open"]),"cap":round(state["cap"],2),"daily":round(state["daily"],2),"wins":state["wins"],"loss":state["loss"],"footprints":len(fps),"top":f"{fps[0]['symbol']} M5 {fps[0]['m5']}% H1 {fps[0]['h1']}%" if fps else "NONE","real":True}

def render(state):
    now=int(time.time()); fps, base, total = build_uptrend()
    if fps:
        before=len(state.get("closed",[]))
        state=process(state,fps,now)
        if len(state.get("closed",[]))!=before: kv_set(STATE_KEY,state)
    cap=state.get("cap",1000); daily=state.get("daily",0); bank=state.get("bank",0)
    wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0)
    scan=state.get("scan",0); unreal=sum(t.get("net",0) for t in state.get("open",[]))
    open_tr=state.get("open",[]); closed=state.get("closed",[])
    winrate=round(wins/tot*100,1) if tot>0 else 0
    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v738 REAL PROFIT</title>
<style>body{{background:#000;color:#0f8;font-family:monospace;margin:0}}.topdash{{background:#111;border-bottom:4px solid #ffcc00;padding:10px}}.bigrow{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:10px}}.bigbox{{background:#000;border:2px solid #ffcc00;padding:14px;text-align:center}}.biglabel{{font-size:12px;color:#aaa}}.bigval{{font-size:34px;font-weight:bold;color:#ffcc00}}.bigval-green{{font-size:34px;font-weight:bold;color:#0f8}}.bigval-red{{font-size:34px;font-weight:bold;color:#f44}}.midrow{{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}}.midbox{{background:#000;border:1px solid #555;padding:8px;text-align:center}}.yellowbar{{background:#ffcc00;color:#000;padding:10px;text-align:center;font-weight:bold}}.greenbar{{background:#0a5;color:#fff;padding:10px;text-align:center;font-weight:bold}}.redbar{{background:#a00;color:#fff;padding:10px;text-align:center;font-weight:bold}}.foot{{border:2px solid #0f8;margin:5px;padding:8px;background:#0a0a0a}}</style><meta http-equiv="refresh" content="15"></head><body>
<div class="topdash"><div style="text-align:center;color:#ffcc00;font-size:12px;font-weight:bold">VENUS v738 - REAL PROFIT M5 0.15-2.2% H1 2.5-9% VOL SPIKE - POS 40 - SCAN #{scan}</div>
"""
    if not fps: html+=f"""<div class="redbar">NO REAL ENTRY - Waiting for early uptrend, not top chase like MBL +51% - Base {base}</div>"""
    else: html+=f"""<div class="greenbar">REAL ENTRY LIVE - {len(fps)} coins pass REAL filters - TOP {fps[0]['symbol']} M5 {fps[0]['m5']}% H1 {fps[0]['h1']}% - No top chase</div>"""
    html+=f"""
<div class="bigrow">
<div class="bigbox"><div class="biglabel">TOTAL CAP</div><div class="bigval">${cap:.2f}</div><div style="font-size:11px">START $1000 | WITH OPEN ${cap+unreal:.2f}</div></div>
<div class="bigbox"><div class="biglabel">TODAY</div><div class="{'bigval-green' if daily>=0 else 'bigval-red'}">${daily:+.2f}</div><div style="font-size:11px">UNREAL ${unreal:+.2f} | STOP -$12</div></div>
<div class="bigbox"><div class="biglabel">WINRATE</div><div class="bigval">{wins}W {loss}L {winrate}%</div><div style="font-size:11px">TOTAL {tot} | 3 POS MAX</div></div>
</div>
<div class="yellowbar">FOOTPRINTS {len(fps)} - REAL M5 0.15-2.2% - NOT 11% FAKE PUMP</div>
"""
    for fp in fps[:10]:
        html+=f"""<div class="foot">#{fp['id']} {fp['symbol']} - M5 {fp['m5']}% H1 {fp['h1']}% SCORE {fp['score']:.1f} VOL ${fp['vol']} PRICE ${fp['price']}</div>"""
    html+=f"""<div class="yellowbar">OPEN {len(open_tr)}/3</div>"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}">{tr['symbol']} {tr.get('pct',0):+.3f}% ${tr.get('net',0):+.4f} AGE {tr.get('age',0)}s M5 {tr.get('m5')}% H1 {tr.get('h1')}%</div>"""
    html+=f"""<div style="padding:8px;color:#ffcc00">CLOSED LAST 20</div>"""
    for cl in closed[:20]:
        ccol="#0f8" if cl["net"]>0 else "#f44"
        html+=f"""<div style="color:{ccol};padding:4px;border-bottom:1px solid #222">{cl['symbol']} {cl['net']:+.4f} {cl['reason']} {cl['pct']:+.2f}%</div>"""
    html+=f"""<div style="text-align:center;padding:10px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:12px 20px;text-decoration:none;font-weight:bold">CRON - CAP ${cap:.2f}</a> <a href="/api/reset?key={ADMIN_KEY}" style="color:#0f8;margin-left:10px">RESET</a></div></body></html>"""
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
            kv_set(STATE_KEY,{"cap":1000.0,"bank":0.0,"daily":0.0,"gross":0.0,"fee":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"base":""})
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"ok":True}).encode()); return
        st=load_state(); h=render(st)
        self.send_response(200); self.send_header("Content-Type","text/html"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(h.encode())
    def do_POST(self): self.do_GET()
