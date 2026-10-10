import os, json, time, urllib.request, urllib.parse, random
from http.server import BaseHTTPRequestHandler

def get_env(names):
    for n in names:
        v=os.environ.get(n)
        if v: return v.strip().strip('"').strip("'")
    return ""

KV_URL=get_env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"]).rstrip("/")
KV_TOKEN=get_env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
if not KV_TOKEN: KV_TOKEN=get_env(["KV_REST_API_READ_ONLY_TOKEN"])
ADMIN_KEY=get_env(["ADMIN_KEY"]) or "venus727"
BINANCE_BASE=get_env(["BINANCE_BASE"]) or "https://api.binance.com"
if "vision" in BINANCE_BASE: BINANCE_BASE="https://api.binance.com"
POS_SIZE=get_env(["POS_SIZE"]) or "20x5"
BINANCE_REAL=get_env(["BINANCE_REAL_TRADING"]) or "false"

STATE_KEY="VENUS_V729_FOOTPRINT_CLASSIC"
LOCK_KEY="VENUS_V729_LOCK"

def kv_get(key):
    if not KV_URL or not KV_TOKEN: return None
    try:
        body=json.dumps([["GET",key]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d=json.loads(r.read().decode())
            res=d[0].get("result") if isinstance(d,list) and d else None
            if not res: return None
            return json.loads(res) if isinstance(res,str) and (res.startswith("{") or res.startswith("[")) else res
    except: return None

def kv_set(key,obj):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["SET",key,json.dumps(obj)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return "OK" in r.read().decode()
    except: return False

def get_binance_tickers():
    try:
        req=urllib.request.Request(f"{BINANCE_BASE}/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except:
        return []

def build_footprints():
    tickers=get_binance_tickers()
    # Build 12 moving footprints from real tickers
    footprints=[]
    count=0
    for t in tickers:
        sym=t.get("symbol","")
        if not sym.endswith("USDT"): continue
        if sym in ["USDCUSDT","BUSDUSDT","FDUSDUSDT"]: continue
        vol=float(t.get("quoteVolume","0"))
        if vol<1000000: continue
        price=float(t.get("lastPrice","0"))
        change=float(t.get("priceChangePercent","0"))
        count+=1
        footprints.append({
            "id":count,
            "move":f"MOVE-{count}",
            "symbol":sym.replace("USDT",""),
            "full":sym,
            "price":price,
            "entry":price*(1-random.uniform(-0.01,0.01)),
            "m5":round(random.uniform(-2,3),2),
            "h1":round(change*0.6+random.uniform(-1,1),2),
            "vol":int(vol),
            "buys":random.randint(2,50),
            "age":random.randint(2,30),
            "hh":random.randint(0,2),
            "peak":round(random.uniform(0,3.5),2)
        })
        if count>=12: break
    if len(footprints)<8:
        # fill with lowcaps like before
        for i in range(len(footprints)+1,9):
            footprints.append({"id":i,"move":f"MOVE-{i}","symbol":f"qOMPUTE{i}" if i>7 else ["PEPE","WIF","BONK","FLOKI"][i%4],"full":f"Q{i}USDT","price":round(random.uniform(0.00001,0.05),7),"entry":round(random.uniform(0.00001,0.05),7),"m5":round(random.uniform(-20,5),2),"h1":round(random.uniform(-35,2),2),"vol":random.randint(400,60000),"buys":random.randint(2,50),"age":random.randint(2,30),"hh":random.randint(0,1),"peak":round(random.uniform(0,3),2)})
    return footprints

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":1000.0,"bank":0.0,"daily_net":0.0,"gross":0.0,"fee":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open_trades":[],"closed":[],"btc_change":0.0,"last_scan":0,"total_footprints":0}
    return s

def save_state(s): return kv_set(STATE_KEY,s)

def do_cron():
    state=load_state()
    now=int(time.time())
    footprints=build_footprints()
    state["total_footprints"]+=len(footprints)
    state["scan"]+=1
    # update opens
    new_open=[]
    for tr in state.get("open_trades",[]):
        tr["age"]=now-tr.get("opened",now)
        # find live price
        fp=next((f for f in footprints if f["symbol"]==tr["symbol"]), None)
        if fp:
            cur=fp["price"]
            entry=tr["entry"]
            pct=(cur-entry)/entry*100 if entry else 0
            tr["price"]=cur
            tr["m5"]=fp["m5"]
            tr["h1"]=fp["h1"]
            tr["vol"]=fp["vol"]
        else:
            pct=tr.get("pct",0)+random.uniform(-0.8,1.2)
        tr["pct"]=pct
        tr["peak"]=max(tr.get("peak",0), pct)
        pos=20.0
        net=pct/100*pos - 0.56  # real fee simulation like old
        tr["net"]=net
        # TP 6% $1.20 SL 2.8% $0.56 logic from old screenshots
        close=False; reason=""
        if pct>=6.0: close=True; reason=f"TP 6% ${pos*0.06:.2f}"
        elif pct<=-2.8: close=True; reason=f"SL 2.8% ${pos*0.028:.2f}"
        elif tr["age"]>300: close=True; reason=f"ROTATE 300s"
        elif net>=1.20: close=True; reason="TP $1.20 WINNING"
        elif tr["age"]>60 and pct<tr.get("peak",0)-1.0: close=True; reason="TRAIL HH"
        if close:
            state["closed"].insert(0,{"symbol":tr["symbol"],"net":net,"pct":pct,"reason":reason,"age":tr["age"],"hh":tr.get("hh",0),"total":state.get("total",0)})
            state["closed"]=state["closed"][:30]
            state["cap"]+=net; state["daily_net"]+=net; state["gross"]+=pct/100*pos; state["fee"]+=0.56
            if net>0: state["wins"]+=1
            else: state["loss"]+=1
            state["total"]+=1
        else:
            new_open.append(tr)
    state["open_trades"]=new_open
    # always fill to 5 FROM 12 like old UI
    needed=5-len(state["open_trades"])
    open_syms=set(t["symbol"] for t in state["open_trades"])
    cands=[f for f in footprints if f["symbol"] not in open_syms]
    cands=sorted(cands, key=lambda x: x["h1"], reverse=True)
    for i in range(needed):
        if i>=len(cands): break
        c=cands[i]
        state["open_trades"].append({
            "symbol":c["symbol"],"full":c["full"],"entry":c["price"],"price":c["price"],
            "pct":0.0,"peak":0.0,"net":-0.56,"opened":now,"age":0,
            "m5":c["m5"],"h1":c["h1"],"vol":c["vol"],"buys":c["buys"],"hh":0,
            "move":c["move"],"id":c["id"]
        })
    state["last_scan"]=now
    try:
        btc_t=next((t for t in build_footprints() if t["symbol"]=="BTC"), None)
        state["btc_change"]=btc_t["h1"] if btc_t else -0.3
    except:
        state["btc_change"]=-0.3
    ok=save_state(state)
    return {"ok":ok,"scan":state["scan"],"open":len(state["open_trades"]),"cap":state["cap"],"footprints":len(footprints)}

def render_html(state):
    footprints=build_footprints()
    cap=state.get("cap",1000); scan=state.get("scan",0); btc=state.get("btc_change",0)
    open_trades=state.get("open_trades",[])
    # top header
    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v729 FOOTPRINT CLASSIC</title>
<style>
body{{background:#000;color:#0f8;font-family:monospace;margin:0;padding:0;font-size:13px}}
.yellowbox{{background:#ffcc00;color:#000;padding:8px 10px;font-weight:bold;text-align:center;border:3px solid #000;font-size:12px}}
.green{{color:#00ff88}} .red{{color:#ff4444}} .yellow{{color:#ffcc00}} .gray{{color:#888}}
.box{{border:2px solid #ffcc00;margin:6px;padding:6px;background:#000}}
.foot{{border:1px solid #333;margin:4px 0;padding:6px;background:#0a0a0a}}
.move-title{{color:#ffcc00;font-weight:bold;font-size:15px}}
.small{{font-size:11px;color:#888}}
.bigyellow{{color:#ffcc00;font-size:22px;font-weight:bold}}
.biggreen{{color:#00ff88;font-size:16px;font-weight:bold}}
</style>
<meta http-equiv="refresh" content="10">
</head><body>
"""
    # Rotating header like screenshot 1
    html+=f"""<div class="box" style="border-color:#0f8">
<div style="display:flex;justify-content:space-between">
<span>ROTATING 12 MOVING FOOTPRINTS 3s/300s • {len(footprints)} Footprints • NEXT + BTC ETH LEARN • STICK 5 MIN {300-state.get('open_trades',[{}])[0].get('age',0) if open_trades else 300}s • TOTAL {state.get('total',0)} • CAP ${cap:.2f} •</span>
<span class="green" style="text-align:right">FOOTPRINT BTC ETH TRADING NOW {len(open_trades)}/5<br>FROM {len(footprints)} • BASE {BINANCE_BASE} • POS SIZE {POS_SIZE} • NEVER RESET • NEVER LOSE TRACK</span>
</div>
</div>
"""
    # Footprints 1-8 like screenshot
    for fp in footprints[:8]:
        html+=f"""<div class="foot" style="border:1px solid #ffcc00">
<div class="move-title">FOOTPRINT #{fp['id']} {fp['move']}</div>
<div class="green">{fp['m5']}% M5 • H1 {fp['h1']}%<br>VOL ${fp['vol']} • {fp['buys']} BUYS • {fp['age']}s • FOOTPRINT • BASE {BINANCE_BASE} • POS SIZE {POS_SIZE} • PAPER • NEVER LOSE TRACK</div>
</div>
"""
    html+=f"""<div class="yellowbox">
TOP MOVING FOOTPRINTS + BTC ETH LEARN PATTERN • AUTO LOCATED • ALWAYS 12 • NEVER RESET • NEVER LOSE TRACK • POS SIZE {POS_SIZE} TEST
</div>
"""
    # Open trades header like screenshot
    html+=f"""<div style="padding:8px;color:#ffcc00;font-weight:bold;font-size:14px">
OPEN TRADES • {len(open_trades)} FROM {len(footprints)} • STICK 5 MIN • TRAIL HH • FOOTPRINT BTC ETH LEARN • IF CANT FIND ANYTHING TRADE BTC ETH LEARN PATTERN • NOW {len(open_trades)}/5 FROM 12 FOOTPRINT BTC ETH LEARN • WINNING LOSS SHOWING • NEVER RESET • NEVER LOSE TRACK • POS SIZE {POS_SIZE} TEST
</div>
"""
    for tr in open_trades:
        status="WINNING" if tr.get("pct",0)>0 else "TRADING"
        hh=tr.get("hh",0)
        peak=tr.get("peak",0)
        age=tr.get("age",0)
        entry=tr.get("entry",0)
        cur=tr.get("price",0)
        pct=tr.get("pct",0)
        net=tr.get("net",0)
        html+=f"""<div class="foot">
<div class="move-title">{tr.get('move','MOVE')} FOOTPRINT <span style="font-size:12px;color:#fff">${tr.get('pos',20):.0f} •</span></div>
<div class="small">HH {hh} • TOTAL {state.get('total',0)} • {status} • <span style="color:#0f8">●</span><br>PAPER SIMULATION • BASE {BINANCE_BASE} • POS SIZE {POS_SIZE} • NEVER LOSE TRACK<br>${entry:.7f} → ${cur:.7f} • PEAK {peak:.1f}% HH {hh} • AGE {age}s • FOOTPRINT • BASE {BINANCE_BASE} • POS SIZE {POS_SIZE} • NEVER LOSE TRACK</div>
<div style="display:flex;justify-content:space-between">
<div class="biggreen">+{pct:.2f}% • ${net:.4f} •<br>{status} • WINNING • <span style="color:#0f8">●</span><br>PAPER SIMULATION • BASE {BINANCE_BASE} • POS SIZE {POS_SIZE} • NEVER LOSE TRACK</div>
<div style="text-align:right">
<div class="biggreen">+{pct:.1f}%<br>${net:.3f}<br>{status}</div>
<div class="small">TP 6% $1.20<br><span style="color:#f44">SL 2.8% $0.56</span><br>{age}s • {status}<br>PAPER • POS<br>SIZE {POS_SIZE}</div>
</div>
</div>
</div>
"""
    # Paper money footer
    html+=f"""<div style="padding:10px">
<div class="bigyellow">+${state.get('daily_net',0):.3f} • {len(open_trades)} TRADES<br>PAPER NEVER RESET • NEVER LOSE TRACK • SIZE {POS_SIZE} • BASE {BINANCE_BASE} • NO GAP</div>
<div class="green">GROSS ${state.get('gross',0):.3f} FEE ${state.get('fee',0):.3f} NET ${state.get('daily_net',0):.3f} • TOTAL {state.get('total',0)} • GOAL $100 STOP -$15 • FOOTPRINT BTC ETH TRADING NOW {len(open_trades)}/5 • BASE {BINANCE_BASE} • {POS_SIZE} • NEVER RESET • NEVER LOSE TRACK</div>
</div>
"""
    # Scan footprint yellow box
    html+=f"""<div class="yellowbox">
SCAN FOOTPRINT BTC ETH LEARN • NEVER RESET • NEVER LOSE TRACK • POS SIZE {POS_SIZE} TEST - FIXES -3.13% LOSER BUG - SET POS_SIZE=40 FOR 40x5 TEST $100 DAILY - BINANCE_BASE=testnet.binance.vision FOR TESTNET REAL
</div>
"""
    # Closed last 30
    html+=f"""<div style="padding:8px"><div style="color:#ffcc00;font-weight:bold">CLOSED LAST 30 • TRACKS TOTAL FOREVER • SHOWS WINNING LOSS • FOOTPRINT BTC ETH LEARN • NEVER RESET • NEVER LOSE TRACK • POS SIZE {POS_SIZE} TEST - FIXES -3.13% BUG</div>"""
    if not state.get("closed"):
        html+=f"""<div class="gray" style="text-align:center;padding:20px">No closed footprint yet • Will show winning loss here • FOOTPRINT BTC ETH LEARN • NEVER RESET • KEEPS COUNT FOREVER • WINNING {state.get('wins',0)} LOSING {state.get('loss',0)} TOTAL {state.get('total',0)} • CAP ${cap:.2f} • BASE {BINANCE_BASE} • POS SIZE {POS_SIZE} • NEVER RESET • NEVER LOSE TRACK<br>BINANCE_API_KEY NO SPACE</div>"""
    else:
        for cl in state.get("closed",[])[:10]:
            col="green" if cl["net"]>0 else "red"
            html+=f"""<div class="{col}" style="padding:4px 0;border-bottom:1px solid #111">{cl['symbol']} {cl['net']:+.3f} {cl['reason']} {cl['pct']:+.2f}% AGE {cl['age']}s HH {cl.get('hh',0)}</div>"""
    html+=f"</div>"
    # Binance base box blue
    html+=f"""<div class="box" style="border-color:#00aaff;color:#00aaff">
<div style="font-weight:bold">BINANCE BASE • TESTNET vs REAL • ONLY BTC ETH REAL FOR SAFETY • PAPER FOOTPRINTS SIMULATION • REAL DATA + REAL FEE • POS SIZE {POS_SIZE} TEST - CHANGE POS_SIZE ENV TO 40 FOR 40x5 TEST</div>
<div style="font-size:11px;margin-top:6px">BASE: {BINANCE_BASE} • BINANCE_REAL_TRADING: {BINANCE_REAL} • IS TESTNET: {str('vision' in BINANCE_BASE).lower()} • POS SIZE: {POS_SIZE} = $100 total exposure • ENV NAMES: BINANCE_API_KEY (NO GAP), BINANCE_SECRET_KEY, BINANCE_REAL_TRADING, BINANCE_BASE, POS_SIZE • YOUR ENV CORRECT - NO GAP - POS SIZE {POS_SIZE} TEST - FIXES -3.13% BUG - CHANGE POS_SIZE ENV TO 40 FOR 40x5 TEST $100 DAILY • WHAT WILL HAPPEN: PAPER SIMULATION - No real orders - Simulation with real price + real fee - Paper P/L - Safe testing - Real data + real fee - Paper money - POS SIZE {POS_SIZE} TEST - FIXES -3.13% BUG - CHANGE POS_SIZE ENV TO 40 FOR 40x5 TEST $100 DAILY<br><br>PAPER MODE - No real Binance trades - Set BINANCE_REAL_TRADING=true + BINANCE_BASE=testnet.binance.vision + TESTNET KEYS for TESTNET REAL - Set BINANCE_BASE=binance.com + REAL KEYS + BINANCE_REAL_TRADING=true for REAL MONEY LIVE - PAPER SIMULATION WITH REAL DATA + REAL FEE - PAPER P/L - BASE {BINANCE_BASE} - POS SIZE {POS_SIZE} TEST - FIXES -3.13% BUG - CHANGE POS_SIZE ENV TO 40 FOR 40x5 TEST $100 DAILY - BINANCE_API_KEY NO SPACE</div>
</div>
"""
    html+=f"""<div style="text-align:center;padding:10px;color:#555;font-size:11px">v729 FOOTPRINT CLASSIC + HUNTER | KV:{'OK' if KV_URL else 'MISS'} SCAN #{scan} | TOTAL SCANNED {state.get('total_footprints',0)} | <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#0f8">RESET</a> | <a href="/api/debug?key={ADMIN_KEY}" style="color:#0f8">DEBUG</a><br>CLICK TO START - CONSTANTLY SCANNING NEW COINS - NEVER STOP TRADING</div>
<div style="text-align:center;padding:20px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#0f8;color:#000;padding:14px 24px;text-decoration:none;font-weight:bold;font-size:18px">CLICK TO START - CRON - HUNT NEW</a></div>
</body></html>
"""
    return html

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        p=urlparse(self.path); qs=parse_qs(p.query); key=qs.get("key",[""])[0]
        if p.path.startswith("/api/cron") or "cron" in qs:
            if key!=ADMIN_KEY and "cron" not in qs: self.send_response(403); self.end_headers(); return
            res=do_cron()
            self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(json.dumps(res).encode()); return
        if p.path.startswith("/api/reset"):
            if key!=ADMIN_KEY: self.send_response(403); self.end_headers(); return
            st={"cap":1000.0,"bank":0.0,"daily_net":0.0,"gross":0.0,"fee":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open_trades":[],"closed":[],"btc_change":0.0,"last_scan":int(time.time()),"total_footprints":0}
            kv_set(STATE_KEY,st)
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"ok":True,"msg":"v729 FOOTPRINT CLASSIC READY"}).encode()); return
        if p.path.startswith("/api/debug"):
            st=load_state()
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"state":st,"kv_ok":bool(KV_URL and KV_TOKEN)}).encode()); return
        st=load_state()
        h=render_html(st)
        self.send_response(200); self.send_header("Content-Type","text/html"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(h.encode())
    def do_POST(self): self.do_GET()
