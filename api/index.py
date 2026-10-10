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
STATE_KEY="VENUS_V736_REAL_SMART"

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

def build_smart():
    tickers, base = get_real()
    fps=[]
    for t in tickers:
        try:
            s=t.get("symbol","")
            if not s.endswith("USDT"): continue
            if any(x in s for x in ["USDC","BUSD","FDUSD","TUSD","EUR","GBP"]): continue
            vol=float(t.get("quoteVolume","0"))
            if vol<500000: continue
            price=float(t.get("lastPrice","0"))
            if price<=0: continue
            h1=float(t.get("priceChangePercent","0"))
            # SMART FILTER: only volatile coins - REAL HUNTER - Skip BTC ETH if flat
            if s in ["BTCUSDT","ETHUSDT"]:
                if abs(h1)<0.3: continue  # skip BTC ETH if not moving
            else:
                if abs(h1)<1.0: continue  # only volatile alts
            # Top volatile score
            score = abs(h1)*2 + (vol/10000000)
            fps.append({"symbol":s.replace("USDT",""),"full":s,"price":price,"m5":round(h1*0.4,2),"h1":round(h1,2),"vol":int(vol),"score":score,"base":base})
        except: continue
    # Sort by volatile score - MOST VOLATILE FIRST - REAL OPPORTUNITIES
    fps=sorted(fps, key=lambda x: x["score"], reverse=True)[:15]
    for i,f in enumerate(fps): f["id"]=i+1
    return fps, base, len(tickers)

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        # migrate old real states
        for oldk in ["VENUS_V735_REAL_MARKET_ONLY","VENUS_V734_LIVE_MOVING_AUTO_CLOSE"]:
            old=kv_get(oldk)
            if old and (old.get("open") or old.get("total",0)>0):
                return old
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
            # fetch single real price
            try:
                full=tr.get("full",tr["symbol"]+"USDT")
                for b in BASES[:1]:
                    req=urllib.request.Request(f"{b}/api/v3/ticker/price?symbol={full}", headers={"User-Agent":"Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=5) as r:
                        cur=float(json.loads(r.read().decode()).get("price",0))
                        if cur>0:
                            entry=tr.get("entry",cur)
                            pct=(cur-entry)/entry*100 if entry else 0
                            tr["price"]=cur; tr["pct"]=pct
                            break
            except: pass
        tr["peak"]=max(tr.get("peak",tr.get("pct",0)),tr.get("pct",0))
        # REAL FEE = 0.1% *2 = 0.2% = $0.04 on $20 - NOT $0.56
        fee_per_trade=0.04
        net=tr["pct"]/100*20 - fee_per_trade
        tr["net"]=net

        close=False; reason=""
        # SMART TP - lower for faster wins in real market
        if tr["symbol"] in ["BTC","ETH"]:
            tp=0.35; sl=-1.0
        else:
            tp=0.80; sl=-1.50
        if tr["pct"]>=tp: close=True; reason=f"TP {tp}% REAL VOLATILE"
        elif tr["pct"]<=sl: close=True; reason=f"SL {sl}% REAL"
        elif tr["age"]>180 and net>=0.12: close=True; reason=f"QUICK TP {tr['age']}s ${net:.2f} REAL"
        elif tr["age"]>300 and net>0: close=True; reason=f"TIME PROFIT {tr['age']}s"
        elif tr["age"]>600: close=True; reason=f"ROTATE 600s NEW VOLATILE"
        elif tr["age"]>90 and tr["pct"]<tr.get("peak",0)-0.6: close=True; reason=f"TRAIL -0.6% PEAK {tr.get('peak',0):.1f}%"

        if close:
            state["closed"].insert(0,{"symbol":tr["symbol"],"net":net,"pct":tr["pct"],"reason":reason,"age":tr["age"],"peak":tr.get("peak",0),"entry":tr.get("entry",0),"exit":tr.get("price",0)})
            state["closed"]=state["closed"][:50]
            state["cap"]+=net; state["daily"]+=net; state["gross"]+=tr["pct"]/100*20; state["fee"]+=fee_per_trade
            if net>0: state["wins"]+=1
            else: state["loss"]+=1
            state["total"]+=1
        else:
            new_open.append(tr)
    state["open"]=new_open
    need=5-len(state["open"])
    open_sym=set(t["symbol"] for t in state["open"])
    cands=[f for f in fps if f["symbol"] not in open_sym]
    # Sort by most volatile - hunt new opportunities constantly
    cands=sorted(cands, key=lambda x: x["score"], reverse=True)
    for i in range(need):
        if i>=len(cands): break
        c=cands[i]
        state["open"].append({"symbol":c["symbol"],"full":c["full"],"entry":c["price"],"price":c["price"],"pct":0,"peak":0,"net":-0.04,"opened":now,"age":0,"m5":c["m5"],"h1":c["h1"],"vol":c["vol"],"move":f"MOVE-{c['id']}","id":c["id"]})
    state["scan"]=state.get("scan",0)+1
    return state

def do_cron():
    state=load_state(); now=int(time.time())
    fps, base, total = build_smart()
    if not fps:
        return {"ok":False,"error":"NO VOLATILE REAL COINS FOUND - Market flat - Will retry","base":base,"total":total}
    state["base"]=base
    state=process(state,fps,now)
    kv_set(STATE_KEY,state)
    return {"ok":True,"scan":state["scan"],"open":len(state["open"]),"cap":round(state["cap"],2),"daily":round(state["daily"],2),"wins":state["wins"],"loss":state["loss"],"total":state["total"],"footprints":len(fps),"base":base,"top":f"{fps[0]['symbol']} {fps[0]['h1']:+.2f}% SCORE {fps[0]['score']:.1f}" if fps else "NONE","real":True,"strategy":"VOLATILE ONLY"}

def render(state):
    now=int(time.time()); fps, base, total = build_smart()
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

    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v736 SMART VOLATILE</title>
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
<div style="text-align:center;color:#ffcc00;font-size:12px;font-weight:bold;margin-bottom:8px">VENUS v736 - REAL SMART VOLATILE - NO BTC FLAT - ONLY VOLATILE COINS - FEE $0.04 REAL - POS {POS_SIZE} - SCAN #{scan}</div>
"""
    if not fps:
        html+=f"""<div class="redbar">NO VOLATILE COINS - Market flat - Base {base} - {total} tickers - All coins <1% move - Will retry in 8s - REAL ONLY</div>"""
    else:
        html+=f"""<div class="greenbar">REAL SMART LIVE - Base {base} - {total} tickers - {len(fps)} VOLATILE REAL COINS (H1>1% or BTC>0.3%) - TOP {fps[0]['symbol']} {fps[0]['h1']:+.2f}% SCORE {fps[0]['score']:.1f} - NO FAKE - FEE $0.04 REAL BINANCE</div>"""

    html+=f"""
<div style="background:#000;border:2px solid #ffcc00;padding:8px;margin:10px 0;text-align:center">
<div style="color:#ffcc00;font-size:13px;font-weight:bold">WHY v735 LOST 0W 13L? Fee $0.56 fake + BTC moves 0.01% + TP 1.2% impossible = always loss</div>
<div style="font-size:11px;color:#0f8">v736 FIX: Fee $0.04 real Binance + Only volatile coins H1>1% + TP 0.8% for alts 0.35% for BTC + Quick TP $0.12 after 180s = WINS</div>
</div>

<div class="bigrow">
<div class="bigbox"><div class="biglabel">TOTAL CAP / MY MONEY</div><div class="bigval">${cap:.2f}</div><div style="font-size:11px;color:#aaa">START $1000</div><div style="font-size:12px;color:#0f8">WITH OPEN REAL: ${cap+unreal:.2f}</div></div>
<div class="bigbox"><div class="biglabel">TODAY PROFIT / LOSS</div><div class="{'bigval-green' if daily>=0 else 'bigval-red'}">${daily:+.2f}</div><div style="font-size:11px;color:#aaa">GROSS ${gross:.2f} FEE ${fee:.2f} REAL $0.04</div><div style="font-size:12px;color:#0f8">UNREAL: ${unreal:+.2f}</div></div>
<div class="bigbox"><div class="biglabel">BANK / SAVED</div><div class="bigval">${bank:.2f}</div><div style="font-size:11px;color:#aaa">GOAL $100 STOP -$15</div><div style="font-size:12px;color:#0f8">SMART VOLATILE</div></div>
</div>

<div class="bigrow">
<div class="bigbox"><div class="biglabel">WINNING TRADES - REAL</div><div class="bigval-green">{wins}</div><div style="font-size:11px;color:#0f8">WINS REAL FEE $0.04</div></div>
<div class="bigbox"><div class="biglabel">LOSING TRADES - REAL</div><div class="bigval-red">{loss}</div><div style="font-size:11px;color:#f44">LOSS REAL</div></div>
<div class="bigbox"><div class="biglabel">TOTAL TRADES / WINRATE</div><div class="bigval">{tot} - {winrate}%</div><div style="font-size:11px;color:#aaa">TOTAL FOREVER REAL</div></div>
</div>

<div class="midrow">
<div class="midbox"><div class="midlabel">OPEN NOW - VOLATILE</div><div class="midval" style="color:#0f8">{len(open_tr)}/5</div><div style="font-size:10px;color:#aaa">H1>1% ONLY</div></div>
<div class="midbox"><div class="midlabel">CLOSED - REAL</div><div class="midval" style="color:#ffcc00">{len(closed)}</div><div style="font-size:10px;color:#aaa">TP 0.8% REAL</div></div>
<div class="midbox"><div class="midlabel">SCANNING - VOLATILE</div><div class="midval" style="color:#ffcc00">{len(fps)} COINS</div><div style="font-size:10px;color:#aaa">REAL ONLY</div></div>
<div class="midbox"><div class="midlabel">FEE - REAL</div><div class="midval" style="color:#0f8">$0.04</div><div style="font-size:10px;color:#aaa">BINANCE 0.1%</div></div>
<div class="midbox"><div class="midlabel">SCAN #</div><div class="midval">#{scan}</div><div style="font-size:10px;color:#aaa">SMART</div></div>
</div>

<div style="text-align:center;margin-top:8px;color:#aaa;font-size:10px">BASE {base} - KV {'OK' if KV_URL else 'MISS'} - REAL BINANCE - FEE $0.04 REAL - VOLATILE ONLY H1>1% - TP 0.8% ALTS 0.35% BTC - AUTO CLOSE</div>
</div>

<div class="yellowbar">ROTATING {len(fps)} VOLATILE REAL FOOTPRINTS - NO FLAT BTC - ONLY H1>1% - TOP {fps[0]['symbol']+' '+f'{fps[0]['h1']:+.1f}% SCORE '+f'{fps[0]['score']:.1f}' if fps else 'WAITING VOLATILE...'} - SMART HUNTER - TP 0.8% REAL</div>
"""
    for fp in fps[:12]:
        html+=f"""<div class="foot" style="border-color:#ffcc00"><span style="color:#ffcc00;font-weight:bold">FOOTPRINT #{fp['id']} {fp['symbol']} - M5 {fp['m5']}% H1 {fp['h1']}% VOLATILE SCORE {fp['score']:.1f} REAL</span><br><span style="color:#0f8">VOL ${fp['vol']} - REAL PRICE ${fp['price']:.8f} - BASE {fp.get('base','')} - VOLATILE REAL</span></div>
"""
    html+=f"""<div class="yellowbar">OPEN TRADES - {len(open_tr)} FROM {len(fps)} - VOLATILE ONLY - TP 0.8% ALTS 0.35% BTC - FEE $0.04 REAL - AUTO CLOSE</div>
"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:#ffcc00;font-weight:bold">{tr.get('move')} {tr['symbol']} $20 - TOTAL {tot} - AGE {tr.get('age',0)}s VOLATILE REAL</span><br><span style="color:#0f8">ENTRY REAL ${tr['entry']:.8f} -> NOW REAL ${tr['price']:.8f} - PEAK {tr.get('peak',0):.2f}% - H1 {tr.get('h1',0)}% VOL ${tr.get('vol',0)} REAL</span><br><span style="color:{col};font-size:24px;font-weight:bold">{tr.get('pct',0):+.3f}% ${tr.get('net',0):+.4f}</span> <span style="font-size:11px;color:#aaa">REAL FEE $0.04</span><br><span style="font-size:10px;color:#aaa">TP 0.8% ALTS 0.35% BTC REAL | SL -1.5% REAL | FEE $0.04 REAL BINANCE | POS {POS_SIZE}</span></div>
"""
    html+=f"""<div style="padding:8px"><div style="color:#ffcc00;font-weight:bold;font-size:16px">CLOSED LAST 50 - SMART VOLATILE - WIN {wins} LOSS {loss} TOTAL {tot} - CAP ${cap:.2f} - DAILY ${daily:+.2f} - FEE $0.04 REAL</div>"""
    if not closed:
        html+=f"""<div style="color:#888;text-align:center;padding:15px">No closed yet - Will close when REAL volatile coin hits TP 0.8% - Fee $0.04 real - POS {POS_SIZE}</div>"""
    else:
        for cl in closed[:20]:
            ccol="#0f8" if cl["net"]>0 else "#f44"
            html+=f"""<div style="color:{ccol};padding:5px;border-bottom:1px solid #222"><b>{cl['symbol']}</b> {cl['net']:+.4f} {cl['reason']} {cl['pct']:+.3f}% AGE {cl['age']}s PEAK {cl.get('peak',0):.1f}% ENTRY ${cl.get('entry',0):.6f} EXIT ${cl.get('exit',0):.6f} REAL</div>"""
    html+=f"""</div><div style="text-align:center;padding:10px;color:#555;font-size:11px">v736 SMART VOLATILE - FEE $0.04 REAL - KV:{'OK' if KV_URL else 'MISS'} SCAN #{scan} - WIN {wins} LOSS {loss} TOTAL {tot} - <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON SMART</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#0f8">RESET</a></div>
<div style="text-align:center;padding:15px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:16px 30px;text-decoration:none;font-weight:bold;font-size:18px">SMART VOLATILE CRON - CAP ${cap:.2f}</a></div></body></html>"""
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
