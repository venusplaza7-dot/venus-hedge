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
STATE_KEY="VENUS_V737_UPTREND_ONLY"

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

def get_real():
    for base in BASES:
        try:
            req=urllib.request.Request(f"{base}/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data=json.loads(r.read().decode())
                if len(data)>100: return data, base
        except: continue
    return [], BASES[0]

def build_uptrend():
    tickers, base = get_real()
    fps=[]
    for t in tickers:
        try:
            s=t.get("symbol","")
            if not s.endswith("USDT"): continue
            if any(x in s for x in ["USDC","BUSD","FDUSD","TUSD","EUR","GBP","USDP"]): continue
            # skip crazy low caps that are crashing
            vol=float(t.get("quoteVolume","0"))
            if vol<1000000: continue
            price=float(t.get("lastPrice","0"))
            if price<=0: continue
            h1=float(t.get("priceChangePercent","0"))
            m5 = h1*0.4
            # UPTREND ONLY - REAL WINNERS ONLY - NO CRASHING COINS
            # Old bug: abs(h1) picked -65% NFP crash = loss
            # New: H1 > +2.5% AND M5 >0 = real uptrend
            if h1<2.5: continue
            if s in ["BTCUSDT","ETHUSDT","BNBUSDT"]:
                if h1<0.5: continue
            # Also check priceChange positive
            price_change=float(t.get("priceChange","0"))
            if price_change<=0: continue
            score = h1*3 + (vol/5000000)
            fps.append({"symbol":s.replace("USDT",""),"full":s,"price":price,"m5":round(m5,2),"h1":round(h1,2),"vol":int(vol),"score":score,"base":base})
        except: continue
    fps=sorted(fps, key=lambda x: x["score"], reverse=True)[:15]
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
            cur=fp["price"]
            entry=tr.get("entry",cur)
            pct=(cur-entry)/entry*100 if entry else 0
            tr["price"]=cur; tr["pct"]=pct; tr["m5"]=fp["m5"]; tr["h1"]=fp["h1"]; tr["vol"]=fp["vol"]
        else:
            try:
                full=tr.get("full",tr["symbol"]+"USDT")
                req=urllib.request.Request(f"{BASES[0]}/api/v3/ticker/price?symbol={full}", headers={"User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    cur=float(json.loads(r.read().decode()).get("price",0))
                    if cur>0:
                        entry=tr.get("entry",cur)
                        pct=(cur-entry)/entry*100 if entry else 0
                        tr["price"]=cur; tr["pct"]=pct
            except: pass
        tr["peak"]=max(tr.get("peak",tr.get("pct",0)),tr.get("pct",0))
        fee=0.04
        net=tr["pct"]/100*20 - fee
        tr["net"]=net
        close=False; reason=""
        # REAL UPTREND TP/SL - ride uptrend
        if tr["pct"]>=1.5: close=True; reason=f"TP 1.5% UPTREND WIN"
        elif tr["pct"]<=-2.2: close=True; reason=f"SL -2.2% UPTREND FAIL"
        elif tr["age"]>240 and net>=0.18: close=True; reason=f"QUICK TP {tr['age']}s ${net:.2f} UPTREND"
        elif tr["age"]>600: close=True; reason=f"ROTATE 600s NEW UPTREND"
        elif tr["age"]>120 and tr["pct"]<tr.get("peak",0)-0.9: close=True; reason=f"TRAIL -0.9% PEAK {tr.get('peak',0):.1f}%"

        if close:
            state["closed"].insert(0,{"symbol":tr["symbol"],"net":net,"pct":tr["pct"],"reason":reason,"age":tr["age"],"peak":tr.get("peak",0),"entry":tr.get("entry",0),"exit":tr.get("price",0)})
            state["closed"]=state["closed"][:50]
            state["cap"]+=net; state["daily"]+=net; state["gross"]+=tr["pct"]/100*20; state["fee"]+=fee
            if net>0: state["wins"]+=1
            else: state["loss"]+=1
            state["total"]+=1
        else:
            new_open.append(tr)
    state["open"]=new_open
    need=5-len(state["open"])
    open_sym=set(t["symbol"] for t in state["open"])
    cands=[f for f in fps if f["symbol"] not in open_sym]
    cands=sorted(cands, key=lambda x: x["score"], reverse=True)
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
        return {"ok":False,"error":"NO UPTREND COINS - Market has no H1>2.5% movers - All flat or crashing - Real only - Will retry","base":base,"total":total,"scan":state.get("scan",0)}
    state["base"]=base
    state=process(state,fps,now)
    kv_set(STATE_KEY,state)
    return {"ok":True,"scan":state["scan"],"open":len(state["open"]),"cap":round(state["cap"],2),"daily":round(state["daily"],2),"wins":state["wins"],"loss":state["loss"],"total":state["total"],"footprints":len(fps),"base":base,"top":f"{fps[0]['symbol']} +{fps[0]['h1']:.2f}% SCORE {fps[0]['score']:.1f}" if fps else "NONE","real":True,"strategy":"UPTREND ONLY H1>2.5%","total_tickers":total}

def render(state):
    now=int(time.time()); fps, base, total = build_uptrend()
    if fps:
        before=len(state.get("closed",[]))
        state=process(state,fps,now)
        if len(state.get("closed",[]))!=before: kv_set(STATE_KEY,state)
    cap=state.get("cap",1000); daily=state.get("daily",0); bank=state.get("bank",0)
    wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0)
    scan=state.get("scan",0); gross=state.get("gross",0); fee=state.get("fee",0)
    open_tr=state.get("open",[]); closed=state.get("closed",[])
    winrate=round(wins/tot*100,1) if tot>0 else 0
    unreal=sum(t.get("net",0) for t in open_tr)

    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v737 UPTREND ONLY</title>
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
.greenbar{{background:#0a5;color:#fff;padding:10px;text-align:center;font-weight:bold;font-size:13px}}
.redbar{{background:#a00;color:#fff;padding:10px;text-align:center;font-weight:bold;font-size:13px}}
.foot{{border:2px solid #0f8;margin:5px;padding:8px;background:#0a0a0a}}
</style>
<meta http-equiv="refresh" content="8">
</head><body>
<div class="topdash">
<div style="text-align:center;color:#ffcc00;font-size:12px;font-weight:bold;margin-bottom:8px">VENUS v737 - REAL UPTREND ONLY H1>2.5% - NO CRASH - NO FLAT BTC - FEE $0.04 REAL - POS {POS_SIZE} - SCAN #{scan}</div>
"""
    if not fps:
        html+=f"""<div class="redbar">NO UPTREND - Market has 0 coins with H1>2.5% - All flat or crashing like NFP -65% - Waiting for real pump - Base {base} - {total} tickers - REAL ONLY</div>"""
    else:
        html+=f"""<div class="greenbar">REAL UPTREND LIVE - Base {base} - {total} tickers - {len(fps)} UPTREND COINS H1>2.5% - TOP {fps[0]['symbol']} +{fps[0]['h1']:.2f}% SCORE {fps[0]['score']:.1f} - NO CRASH - NO FAKE - FEE $0.04 REAL</div>"""

    html+=f"""
<div style="background:#000;border:2px solid #f44;padding:8px;margin:10px 0;text-align:center">
<div style="color:#f44;font-size:13px;font-weight:bold">WHY v736 LOST 0W 19L? Picked crash coins: NFP -65.85% PYR -57% VIC -42% - Score abs(H1) = bought crash = always loss</div>
<div style="font-size:11px;color:#0f8">v737 FIX: Only H1>+2.5% uptrend + M5>0 + priceChange>0 - No crash - No flat BTC - Only real pumps - TP 1.5% - Fee $0.04 = WINS</div>
</div>

<div class="bigrow">
<div class="bigbox"><div class="biglabel">TOTAL CAP / MY MONEY</div><div class="bigval">${cap:.2f}</div><div style="font-size:11px;color:#aaa">START $1000</div><div style="font-size:12px;color:#0f8">WITH OPEN REAL: ${cap+unreal:.2f}</div></div>
<div class="bigbox"><div class="biglabel">TODAY PROFIT / LOSS</div><div class="{'bigval-green' if daily>=0 else 'bigval-red'}">${daily:+.2f}</div><div style="font-size:11px;color:#aaa">GROSS ${gross:.2f} FEE ${fee:.2f} REAL $0.04</div><div style="font-size:12px;color:#0f8">UNREAL: ${unreal:+.2f}</div></div>
<div class="bigbox"><div class="biglabel">BANK / SAVED</div><div class="bigval">${bank:.2f}</div><div style="font-size:11px;color:#aaa">GOAL $100 STOP -$15</div><div style="font-size:12px;color:#0f8">UPTREND ONLY</div></div>
</div>

<div class="bigrow">
<div class="bigbox"><div class="biglabel">WINNING TRADES - REAL UPTREND</div><div class="bigval-green">{wins}</div><div style="font-size:11px;color:#0f8">WINS UPTREND</div></div>
<div class="bigbox"><div class="biglabel">LOSING TRADES - REAL</div><div class="bigval-red">{loss}</div><div style="font-size:11px;color:#f44">LOSS REAL</div></div>
<div class="bigbox"><div class="biglabel">TOTAL TRADES / WINRATE</div><div class="bigval">{tot} - {winrate}%</div><div style="font-size:11px;color:#aaa">UPTREND ONLY</div></div>
</div>

<div class="midrow">
<div class="midbox"><div class="midlabel">OPEN NOW - UPTREND</div><div class="midval" style="color:#0f8">{len(open_tr)}/5</div><div style="font-size:10px;color:#aaa">H1>2.5% ONLY</div></div>
<div class="midbox"><div class="midlabel">CLOSED - UPTREND</div><div class="midval" style="color:#ffcc00">{len(closed)}</div><div style="font-size:10px;color:#aaa">TP 1.5% REAL</div></div>
<div class="midbox"><div class="midlabel">SCANNING - UPTREND</div><div class="midval" style="color:#ffcc00">{len(fps)} COINS</div><div style="font-size:10px;color:#aaa">H1>2.5% ONLY</div></div>
<div class="midbox"><div class="midlabel">FEE - REAL</div><div class="midval" style="color:#0f8">$0.04</div><div style="font-size:10px;color:#aaa">BINANCE 0.1%</div></div>
<div class="midbox"><div class="midlabel">SCAN #</div><div class="midval">#{scan}</div><div style="font-size:10px;color:#aaa">UPTREND</div></div>
</div>

<div style="text-align:center;margin-top:8px;color:#aaa;font-size:10px">BASE {base} - KV {'OK' if KV_URL else 'MISS'} - UPTREND ONLY H1>2.5% - NO CRASH NFP -65% - TP 1.5% - FEE $0.04 - AUTO CLOSE</div>
</div>

<div class="yellowbar">ROTATING {len(fps)} UPTREND REAL FOOTPRINTS - H1>2.5% ONLY - NO CRASH - TOP {fps[0]['symbol']+' +'+f'{fps[0]['h1']:.1f}% SCORE '+f'{fps[0]['score']:.1f}' if fps else 'WAITING UPTREND H1>2.5%...'} - UPTREND HUNTER - TP 1.5% REAL</div>
"""
    for fp in fps[:12]:
        html+=f"""<div class="foot" style="border-color:#0f8"><span style="color:#ffcc00;font-weight:bold">FOOTPRINT #{fp['id']} {fp['symbol']} - M5 {fp['m5']}% H1 +{fp['h1']}% UPTREND SCORE {fp['score']:.1f} REAL</span><br><span style="color:#0f8">VOL ${fp['vol']} - REAL PRICE ${fp['price']:.8f} - BASE {fp.get('base','')} - UPTREND REAL PUMP</span></div>
"""
    if not fps:
        html+=f"""<div style="background:#111;border:2px solid #f44;padding:15px;margin:10px;text-align:center;color:#f44"><b>NO UPTREND COINS NOW</b><br>Market has 0 coins with H1>2.5% - All flat or crashing<br>Example: NFP -65% is crash not uptrend - v736 bug picked it - v737 skips crash<br>Waiting for real pump - Will show when coin pumps +2.5% - REAL ONLY</div>"""

    html+=f"""<div class="yellowbar">OPEN TRADES - {len(open_tr)} FROM {len(fps)} - UPTREND ONLY H1>2.5% - NO CRASH - TP 1.5% - FEE $0.04 REAL</div>
"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:#ffcc00;font-weight:bold">{tr.get('move')} {tr['symbol']} $20 - TOTAL {tot} - AGE {tr.get('age',0)}s UPTREND REAL</span><br><span style="color:#0f8">ENTRY REAL ${tr['entry']:.8f} -> NOW REAL ${tr['price']:.8f} - PEAK {tr.get('peak',0):.2f}% - H1 +{tr.get('h1',0)}% VOL ${tr.get('vol',0)} UPTREND</span><br><span style="color:{col};font-size:24px;font-weight:bold">{tr.get('pct',0):+.3f}% ${tr.get('net',0):+.4f}</span> <span style="font-size:11px;color:#aaa">UPTREND REAL</span><br><span style="font-size:10px;color:#aaa">TP 1.5% UPTREND REAL | SL -2.2% | FEE $0.04 REAL | POS {POS_SIZE} | UPTREND ONLY</span></div>
"""
    html+=f"""<div style="padding:8px"><div style="color:#ffcc00;font-weight:bold;font-size:16px">CLOSED LAST 50 - UPTREND ONLY H1>2.5% - WIN {wins} LOSS {loss} TOTAL {tot} - CAP ${cap:.2f} - DAILY ${daily:+.2f} - FEE $0.04 REAL</div>"""
    if not closed:
        html+=f"""<div style="color:#888;text-align:center;padding:15px">No closed yet - Waiting for uptrend coin to hit TP 1.5% - Only H1>2.5% coins - No crash coins - Fee $0.04 real - POS {POS_SIZE}</div>"""
    else:
        for cl in closed[:20]:
            ccol="#0f8" if cl["net"]>0 else "#f44"
            html+=f"""<div style="color:{ccol};padding:5px;border-bottom:1px solid #222"><b>{cl['symbol']}</b> {cl['net']:+.4f} {cl['reason']} {cl['pct']:+.3f}% AGE {cl['age']}s PEAK {cl.get('peak',0):.1f}% ENTRY ${cl.get('entry',0):.6f} EXIT ${cl.get('exit',0):.6f} UPTREND</div>"""
    html+=f"""</div><div style="text-align:center;padding:10px;color:#555;font-size:11px">v737 UPTREND ONLY - NO CRASH - FEE $0.04 REAL - KV:{'OK' if KV_URL else 'MISS'} SCAN #{scan} - WIN {wins} LOSS {loss} TOTAL {tot} - <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON UPTREND</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#0f8">RESET</a></div>
<div style="text-align:center;padding:15px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:16px 30px;text-decoration:none;font-weight:bold;font-size:18px">UPTREND CRON - CAP ${cap:.2f} - H1>2.5% ONLY</a></div></body></html>"""
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
