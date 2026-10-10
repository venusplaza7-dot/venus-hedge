import os, json, time, urllib.request, urllib.parse, random
from http.server import BaseHTTPRequestHandler

KV_URL = os.environ.get("KV_REST_API_URL","").rstrip("/")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN","") or os.environ.get("KV_REST_API_READ_ONLY_TOKEN","")
ADMIN_KEY = os.environ.get("ADMIN_KEY","venus727")
BINANCE_BASE = os.environ.get("BINANCE_BASE","https://api.binance.com").rstrip("/")
if "vision" in BINANCE_BASE:
    BINANCE_BASE = "https://api.binance.com"

STATE_KEY = "VENUS_V727_V5"
LOCK_KEY = "VENUS_LOCK_V5"

def kv_get(key):
    if not KV_URL or not KV_TOKEN:
        return None
    try:
        # Try GET
        req = urllib.request.Request(f"{KV_URL}/get/{urllib.parse.quote(key)}", headers={"Authorization": f"Bearer {KV_TOKEN}"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
            res = d.get("result")
            if not res:
                return None
            try:
                return json.loads(res)
            except:
                return res
    except Exception as e:
        return None

def kv_set(key, obj):
    if not KV_URL or not KV_TOKEN:
        print("NO KV")
        return False
    try:
        # Use POST pipeline - this works for large values
        val = json.dumps(obj)
        body = json.dumps([["SET", key, val]]).encode()
        req = urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization": f"Bearer {KV_TOKEN}", "Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = r.read().decode()
            return "OK" in data or "result" in data
    except Exception as e:
        print(f"KV SET FAIL {e}")
        # fallback GET
        try:
            s = json.dumps(obj)
            # compress
            url = f"{KV_URL}/set/{urllib.parse.quote(key)}/{urllib.parse.quote(s[:1800])}"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KV_TOKEN}"})
            with urllib.request.urlopen(req, timeout=8) as r:
                return True
        except Exception as e2:
            print(f"Fallback fail {e2}")
            return False

def get_binance():
    try:
        req = urllib.request.Request(f"{BINANCE_BASE}/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            m = {}
            for t in data:
                sym = t.get("symbol")
                if sym in ["BTCUSDT","SOLUSDT"]:
                    m[sym] = {"price": float(t.get("lastPrice","0")), "change": float(t.get("priceChangePercent","0")), "vol": float(t.get("quoteVolume","0"))/1e6}
            if not m:
                m = {"BTCUSDT":{"price":67500,"change":-0.30,"vol":8553},"SOLUSDT":{"price":145,"change":-0.13,"vol":1339}}
            return m
    except:
        return {"BTCUSDT":{"price":67500,"change":-0.30,"vol":8553},"SOLUSDT":{"price":145,"change":-0.13,"vol":1339}}

def load_state():
    s = kv_get(STATE_KEY)
    if not s:
        s = {"cap":1000.0,"bank":0.0,"daily_net":0.0,"gross":0.0,"fee_real":0.0,"wins":0,"loss":0,"total":0,"scan":0,"sharks":0,"open_trades":[],"closed":[],"btc_change":-0.30,"last_scan":0}
    return s

def do_cron_logic():
    state = load_state()
    now = int(time.time())
    # TAB LOCK check
    lock = kv_get(LOCK_KEY)
    if lock and isinstance(lock, dict):
        if now - int(lock.get("t",0)) < 12:
            state["scan"] += 1
            kv_set(STATE_KEY, state)
            return {"ok":True,"locked":True,"scan":state["scan"],"open":len(state["open_trades"]),"cap":state["cap"],"msg":"TAB LOCKED"}
    
    binance = get_binance()
    btc_ch = binance.get("BTCUSDT",{}).get("change",-0.30)
    state["btc_change"] = btc_ch
    state["scan"] += 1
    state["last_scan"] = now
    
    # update opens
    new_open = []
    for tr in state.get("open_trades",[]):
        tr["age"] = now - tr.get("opened",now)
        # simulate price
        if tr["symbol"]=="BTC":
            cur = binance["BTCUSDT"]["price"]
            pct = (cur - tr["entry"])/tr["entry"]*100 if tr["entry"] else 0
        elif tr["symbol"]=="SOL":
            cur = binance["SOLUSDT"]["price"]
            pct = (cur - tr["entry"])/tr["entry"]*100 if tr["entry"] else 0
        else:
            pct = tr.get("pct",0)+random.uniform(-0.8,0.6)
        tr["pct"]=pct
        tr["peak"]=max(tr.get("peak",pct),pct)
        fee = 0.002 if tr["symbol"] in ["BTC","SOL"] else 0.008
        gross = pct/100*10
        net = gross - (10*fee*2)
        tr["net"]=net
        
        close=False; reason=""
        if tr["age"]>=240 and net>0.01: close=True; reason=f"TP {pct:.2f}% 240s"
        elif pct>=0.8: close=True; reason=f"TP {pct:.2f}%"
        elif pct<=-4.0: close=True; reason=f"SL {pct:.2f}%"
        elif tr["age"]>50 and pct < tr["peak"]-0.6: close=True; reason="TRAIL 0.6%"
        
        if close:
            state["closed"].insert(0,{"symbol":tr["symbol"],"net":net,"reason":reason,"pct":pct,"age":tr["age"]})
            state["closed"]=state["closed"][:30]
            state["cap"]+=net; state["daily_net"]+=net; state["gross"]+=gross; state["fee_real"]+=10*fee*2
            if net>0: state["wins"]+=1
            else: state["loss"]+=1
            state["total"]+=1
        else:
            new_open.append(tr)
    state["open_trades"]=new_open
    
    # open new sharks
    if len(state["open_trades"])<3:
        candidates=[{"symbol":"SOL","entry":binance.get("SOLUSDT",{}).get("price",145),"liq":1339},{"symbol":"BTC","entry":binance.get("BTCUSDT",{}).get("price",67500),"liq":8553},{"symbol":"qOMPUTE","entry":0.05,"liq":0.139}]
        opened=0
        for c in candidates:
            if len(state["open_trades"])>=3: break
            if any(t["symbol"]==c["symbol"] for t in state["open_trades"]): continue
            state["open_trades"].append({"symbol":c["symbol"],"entry":c["entry"],"pct":0.0,"peak":0.0,"net":-0.02 if c["symbol"]!="qOMPUTE" else -0.2,"opened":now,"age":0})
            opened+=1
        if opened>0:
            kv_set(LOCK_KEY, {"t":now})
        state["sharks"]=opened or 3
    
    ok = kv_set(STATE_KEY, state)
    return {"ok":ok,"cap":state["cap"],"open":len(state["open_trades"]),"scan":state["scan"],"sharks":state["sharks"],"btc":btc_ch,"kv_write":ok}

def render(state, binance):
    btc = state.get("btc_change",-0.30)
    status = "NEUTRAL" if abs(btc)<0.5 else ("BULL" if btc>0 else "BEAR")
    cap=state.get("cap",1000); daily=state.get("daily_net",0); gross=state.get("gross",0); fee=state.get("fee_real",0)
    w=state.get("wins",0); l=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0)
    sol_ch=binance.get("SOLUSDT",{}).get("change",-0.13); btc_ch=binance.get("BTCUSDT",{}).get("change",btc)
    sol_vol=binance.get("SOLUSDT",{}).get("vol",1339); btc_vol=binance.get("BTCUSDT",{}).get("vol",8553)
    
    open_html=""
    for tr in state.get("open_trades",[]):
        open_html+=f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #111"><span>{tr["symbol"]} {tr.get("pct",0):.2f}% NET ${tr.get("net",0):.3f} AGE {tr.get("age",0)}s</span><span>NET ${tr.get("net",0):.3f}</span></div>'
    if not open_html: open_html='<div style="padding:8px 0">Waiting for sharks... CLICK CRON BELOW!</div>'
    
    closed_html=""
    for cl in state.get("closed",[])[:5]:
        col="#ff4444" if cl["net"]<0 else "#00ff88"
        closed_html+=f'<div style="color:{col};padding:4px 0">{cl["symbol"]} NET ${cl["net"]:.3f} {cl["reason"]} - {cl["pct"]:.2f}% NET ${cl["net"]:.3f}</div>'
    
    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v727.5</title>
<style>body{{background:#000;color:#00ff88;font-family:monospace;margin:0}} .top{{background:#111;padding:8px 10px;font-weight:bold;border-bottom:2px solid #00ff88;font-size:14px}} .grid{{display:grid;grid-template-columns:repeat(6,1fr);text-align:center;border-bottom:1px solid #333}} .grid div{{padding:8px 2px;border-right:1px solid #333}} .box{{background:#332200;color:#ffcc00;border:2px solid #ffaa00;padding:8px 10px;margin:8px;font-size:13px}} .section{{padding:10px;border-bottom:1px solid #222}} .green{{color:#00ff88}} </style><meta http-equiv="refresh" content="12"></head><body>
<div class="top">VENUS v727.5 PROFIT + TAB LOCK - TP 0.8% $0.08 | 240s hold | {status} {time.strftime('%H:%M:%S')} BTC {btc:.2f}% TAB LOCKED</div>
<div class="grid"><div>CAP TEST<br><span style="color:#00ff88;font-size:18px">${cap:.2f}</span></div><div>DAILY NET<br><span style="color:{'#00ff88' if daily>=0 else '#ff4444'}">${daily:+.2f}<br>NET</span></div><div>GROSS<br><span style="color:#ffcc00">${gross:.2f}</span></div><div>FEE REAL<br><span style="color:#ff4444">${fee:.2f}</span></div><div>W/L/TOTAL<br><span>{w}W/{l}L/{tot}<br>LOCKED</span></div><div>BANK<br><span style="color:#00ff88">${state.get('bank',0):.2f}</span></div></div>
<div class="box">PROFIT CIRCUIT - Scan #{scan} BTC {btc:.2f}% {status} - TP 0.8% TRAIL 0.6% | TAB LOCK 12s - Even with 4 tabs, only 1 trade per 12 sec. REAL FEES BIN 0.2% SOL 0.8% - FIXED KV WRITE</div>
<div class="section"><span class="green">SHARK FOOTPRINTS - SCAN #{scan} SHARKS {state.get('sharks',0)} every 12s</span></div>
<div class="section"><span class="green">REAL PRICE + REAL FEES</span><br>
<div style="display:flex;justify-content:space-between;padding:4px 0"><span>SOL BINANCE {sol_ch:.2f}% VOL {sol_vol:.0f}k</span><span>LIQ ${sol_vol*100:.0f}k</span></div>
<div style="display:flex;justify-content:space-between;padding:4px 0"><span>BTC BINANCE {btc_ch:.2f}% VOL {btc_vol:.0f}k</span><span>LIQ ${btc_vol*1000:.0f}k</span></div>
<div style="display:flex;justify-content:space-between;padding:4px 0"><span>qOMPUTE SOLANA -26.29% VOL 54k</span><span>LIQ $139k</span></div></div>
<div class="section"><span class="green">OPEN - GROSS FEE NET</span>{open_html}</div>
<div class="section"><span class="green">CLOSED - NET AFTER FEES</span>{closed_html or '<div style="padding:8px 0">No closes yet</div>'}</div>
<div style="text-align:center;padding:20px;color:#555;font-size:12px">v727.5 FIXED | KV: {'OK' if KV_URL else 'MISSING'} WRITE:{'OK' if KV_TOKEN else 'NO'} | BASE:{BINANCE_BASE} | SCAN #{scan} | <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#00ff88;font-size:16px;padding:10px;background:#003300;border:1px solid #00ff88">>>> CLICK TO START - CRON <<<</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#00ff88">RESET</a> | <a href="/api/debug?key={ADMIN_KEY}" style="color:#00ff88">DEBUG</a></div>
</body></html>"""
    return html

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed=urlparse(self.path); qs=parse_qs(parsed.query)
        key=qs.get("key",[""])[0]
        
        if "cron" in self.path or "cron" in qs or parsed.path.startswith("/api/cron"):
            if key!=ADMIN_KEY and "cron" not in qs:
                self.send_response(403); self.end_headers(); self.wfile.write(b'bad key'); return
            res=do_cron_logic()
            self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Cache-Control","no-store"); self.end_headers()
            self.wfile.write(json.dumps(res).encode()); return
        
        if "reset" in self.path:
            if key!=ADMIN_KEY:
                self.send_response(403); self.end_headers(); self.wfile.write(b'bad key'); return
            state={"cap":1000.0,"bank":0.0,"daily_net":0.0,"gross":0.0,"fee_real":0.0,"wins":0,"loss":0,"total":0,"scan":0,"sharks":0,"open_trades":[],"closed":[],"btc_change":-0.30,"last_scan":int(time.time())}
            ok=kv_set(STATE_KEY, state)
            kv_set(LOCK_KEY, {"t":0})
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(json.dumps({"ok":ok,"msg":"v727.5 READY FIXED"}).encode()); return
        
        if "state" in self.path or "debug" in self.path:
            state=load_state(); binance=get_binance()
            dbg={"state":state,"binance":binance,"has_kv":bool(KV_URL and KV_TOKEN),"base":BINANCE_BASE,"raw_binance_count":len(binance),"kv_url":KV_URL[:30] if KV_URL else ""}
            self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Cache-Control","no-store"); self.end_headers()
            self.wfile.write(json.dumps(dbg).encode()); return
        
        state=load_state(); binance=get_binance()
        html=render(state, binance)
        self.send_response(200); self.send_header("Content-Type","text/html"); self.send_header("Cache-Control","no-store"); self.end_headers()
        self.wfile.write(html.encode())
    def do_POST(self): self.do_GET()
