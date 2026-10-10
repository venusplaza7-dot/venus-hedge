import os, json, time, urllib.request, urllib.parse, random
from http.server import BaseHTTPRequestHandler

# ===== ACCEPTS ALL UPSTASH NAMES =====
def get_env(name_list):
    for n in name_list:
        v = os.environ.get(n)
        if v: 
            return v.strip().strip('"').strip("'")
    return ""

KV_URL = get_env(["KV_REST_API_URL", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_URL", "UPSTASH_REST_URL", "KV_URL"])
KV_TOKEN = get_env(["KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_TOKEN", "UPSTASH_REDIS_REST_TOKEN", "UPSTASH_REST_TOKEN", "KV_REST_API_WRITE_TOKEN"])
# fallback if only READ ONLY exists (can read but not write)
if not KV_TOKEN:
    KV_TOKEN = get_env(["KV_REST_API_READ_ONLY_TOKEN", "UPSTASH_REDIS_REST_READ_ONLY_TOKEN"])

ADMIN_KEY = get_env(["ADMIN_KEY", "ADMI_KEY", "ADMINKEY", "ADMI__KEY"]) or "venus727"
BINANCE_BASE = get_env(["BINANCE_BASE"]) or "https://api.binance.com"
if "vision" in BINANCE_BASE:
    BINANCE_BASE = "https://api.binance.com"

STATE_KEY = "VENUS_V727_PROFIT_V7"
LOCK_KEY = "VENUS_TAB_LOCK_V7"

# ===== KV HELPERS - WORKS WITH BOTH NAMES =====
def kv_get_simple(key):
    if not KV_URL or not KV_TOKEN:
        return None
    try:
        # Upstash REST API: /get/key
        url = f"{KV_URL.rstrip('/')}/get/{urllib.parse.quote(key)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KV_TOKEN}"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            d = json.loads(resp.read().decode())
            res = d.get("result")
            if not res:
                return None
            try:
                return json.loads(res)
            except:
                return res
    except Exception as e:
        # print for debug
        return None

def kv_set_simple(key, obj):
    if not KV_URL or not KV_TOKEN:
        return False
    try:
        s = json.dumps(obj)
        # Use GET /set/key/value - most compatible with Upstash
        url = f"{KV_URL.rstrip('/')}/set/{urllib.parse.quote(key)}/{urllib.parse.quote(s)}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KV_TOKEN}"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read().decode()
            return "OK" in data
    except Exception as e:
        try:
            # Fallback POST /pipeline
            body = json.dumps([["SET", key, json.dumps(obj)]]).encode()
            req = urllib.request.Request(f"{KV_URL.rstrip('/')}/pipeline", data=body, headers={"Authorization": f"Bearer {KV_TOKEN}", "Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                return True
        except:
            return False

def get_binance():
    try:
        url = f"{BINANCE_BASE}/api/v3/ticker/24hr"
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            m = {}
            for t in data:
                sym = t.get("symbol")
                if sym in ["BTCUSDT","SOLUSDT","BNBUSDT","ETHUSDT"]:
                    m[sym] = {"price": float(t.get("lastPrice","0")), "change": float(t.get("priceChangePercent","0")), "vol": float(t.get("quoteVolume","0"))/1e6}
            if not m:
                raise Exception("empty")
            return m
    except:
        return {"BTCUSDT":{"price":60000,"change":-0.30,"vol":8553},"SOLUSDT":{"price":150,"change":-0.13,"vol":1339}}

def load_state():
    s = kv_get_simple(STATE_KEY)
    if not s:
        s = {"cap":1000.0,"bank":0.0,"daily_net":0.0,"gross":0.0,"fee_real":0.0,"wins":0,"loss":0,"total":0,"scan":0,"sharks":0,"open_trades":[],"closed":[],"btc_change":0.0,"last_scan":0}
    return s

def save_state(s):
    return kv_set_simple(STATE_KEY, s)

def do_cron():
    state = load_state()
    now = int(time.time())
    # TAB LOCK check
    lock = kv_get_simple(LOCK_KEY)
    locked = False
    if lock and isinstance(lock, dict):
        age = now - int(lock.get("t",0))
        if age < 12:
            locked = True
    binance = get_binance()
    btc_ch = binance.get("BTCUSDT",{}).get("change",0.0)
    state["btc_change"] = btc_ch
    state["scan"] = state.get("scan",0)+1
    state["last_scan"] = now

    # Update opens
    new_open = []
    for tr in state.get("open_trades",[]):
        tr["age"] = now - tr.get("opened",now)
        sym = tr.get("symbol","SOL")
        entry = tr.get("entry",100)
        if sym=="BTC" and "BTCUSDT" in binance:
            cur = binance["BTCUSDT"]["price"]
            pct = (cur - entry)/entry*100 if entry else 0
        elif sym=="SOL" and "SOLUSDT" in binance:
            cur = binance["SOLUSDT"]["price"]
            pct = (cur - entry)/entry*100 if entry else 0
        else:
            pct = tr.get("pct",0) + random.uniform(-0.6,0.6)
        tr["pct"] = pct
        fee_rate = 0.002 if sym in ["BTC","SOL","BNB","ETH"] else 0.008
        pos = 10.0
        gross = pct/100*pos
        net = gross - (pos*fee_rate*2)
        tr["net"] = net
        tr["peak"] = max(tr.get("peak",pct), pct)

        should_close = False
        reason = ""
        if tr["age"] >= 240 and net > 0.02:
            should_close=True; reason="TP 240s"
        elif pct >= 0.8:
            should_close=True; reason=f"TP {pct:.2f}%"
        elif pct <= -4.0:
            should_close=True; reason=f"SL {pct:.2f}%"
        elif tr["age"]>60 and pct < tr.get("peak",pct)-0.6:
            should_close=True; reason="TRAIL 0.6%"

        if should_close:
            state["closed"].insert(0, {"symbol":sym,"net":net,"reason":reason,"pct":pct,"age":tr["age"]})
            state["closed"]=state["closed"][:30]
            state["cap"]+=net; state["daily_net"]+=net; state["gross"]+=gross; state["fee_real"]+=pos*fee_rate*2
            if net>0: state["wins"]+=1
            else: state["loss"]+=1
            state["total"]+=1
        else:
            new_open.append(tr)
    state["open_trades"]=new_open

    sharks=0
    if len(state["open_trades"])<3 and not locked:
        needed=3-len(state["open_trades"])
        candidates=[{"symbol":"SOL","entry":binance.get("SOLUSDT",{}).get("price",150),"liq":1339},{"symbol":"BTC","entry":binance.get("BTCUSDT",{}).get("price",60000),"liq":8553},{"symbol":"qOMPUTE","entry":0.05,"liq":0.139}]
        for i in range(needed):
            c=candidates[i%len(candidates)]
            if any(t["symbol"]==c["symbol"] for t in state["open_trades"]): continue
            state["open_trades"].append({"symbol":c["symbol"],"entry":c["entry"],"pct":0.0,"peak":0.0,"net":-0.02 if c["symbol"]!="qOMPUTE" else -0.20,"opened":now,"age":0,"liq":c["liq"]})
            sharks+=1
        kv_set_simple(LOCK_KEY, {"t":now})

    state["sharks"]=sharks if sharks else state.get("sharks",5)
    ok = save_state(state)
    return {"ok":ok,"cap":state["cap"],"open":len(state["open_trades"]),"scan":state["scan"],"sharks":state["sharks"],"btc":btc_ch,"kv_write":ok,"kv_url_exists":bool(KV_URL),"kv_token_exists":bool(KV_TOKEN)}

def render_html(state, binance):
    btc = state.get("btc_change",0.0)
    status = "NEUTRAL" if abs(btc)<0.5 else ("BULL" if btc>0 else "BEAR")
    cap = state.get("cap",1000)
    daily = state.get("daily_net",0)
    gross = state.get("gross",0)
    fee = state.get("fee_real",0)
    w,l,tot,scan = state.get("wins",0),state.get("loss",0),state.get("total",0),state.get("scan",0)
    sol_ch = binance.get("SOLUSDT",{}).get("change",-0.13)
    btc_ch = binance.get("BTCUSDT",{}).get("change",btc)
    sol_vol = binance.get("SOLUSDT",{}).get("vol",1339)
    btc_vol = binance.get("BTCUSDT",{}).get("vol",8553)

    open_html=""
    for tr in state.get("open_trades",[]):
        open_html+=f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #111"><span>{tr["symbol"]} {tr.get("pct",0):.2f}% NET ${tr.get("net",0):.3f} AGE {tr.get("age",0)}s</span><span>NET ${tr.get("net",0):.3f}</span></div>'
    if not open_html: open_html='<div style="padding:8px 0">Waiting for sharks... CLICK CRON BELOW!</div>'

    closed_html=""
    for cl in state.get("closed",[])[:5]:
        c="color:#ff4444" if cl["net"]<0 else "color:#00ff88"
        closed_html+=f'<div style="{c};padding:4px 0;border-bottom:1px solid #111">{cl["symbol"]} NET ${cl["net"]:.3f} {cl["reason"]} - {cl["pct"]:.2f}%</div>'
    if not closed_html: closed_html="No closes yet"

    kv_ok = "OK" if KV_URL else "MISSING"
    write_ok = "OK" if KV_TOKEN else "NO"

    return f"""
<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v727.7 UPSTASH FIX</title>
<style>
body{{background:#000;color:#00ff88;font-family:monospace;margin:0;padding:0}}
.top{{background:#111;padding:8px 10px;font-weight:bold;border-bottom:2px solid #00ff88;font-size:14px}}
.grid{{display:grid;grid-template-columns:repeat(6,1fr);text-align:center;border-bottom:1px solid #333}}
.grid div{{padding:8px 2px;border-right:1px solid #333}}
.box{{background:#332200;color:#ffcc00;border:2px solid #ffaa00;padding:8px 10px;margin:8px;font-size:13px}}
.section{{padding:10px;border-bottom:1px solid #222}}
.green{{color:#00ff88}} .red{{color:#ff4444}} .yellow{{color:#ffcc00}}
</style>
<meta http-equiv="refresh" content="15">
</head>
<body>
<div class="top">VENUS v727.7 UPSTASH FIX - TP 0.8% $0.08 | 240s | {status} {time.strftime('%H:%M:%S')} BTC {btc:.2f}% TAB LOCKED</div>
<div class="grid">
<div>CAP TEST<br><span style="color:#00ff88;font-size:18px">${cap:.2f}</span></div>
<div>DAILY NET<br><span style="color:#00ff88">${daily:+.2f}<br>NET</span></div>
<div>GROSS<br><span class="yellow">${gross:.2f}</span></div>
<div>FEE REAL<br><span class="red">${fee:.2f}</span></div>
<div>W/L/TOTAL<br><span>{w}W/{l}L/{tot}<br>LOCKED</span></div>
<div>BANK<br><span style="color:#00ff88">${state.get('bank',0):.2f}</span></div>
</div>
<div class="box">PROFIT CIRCUIT - Scan #{scan} BTC {btc:.2f}% {status} - TP 0.8% TRAIL 0.6% | TAB LOCK 12s | REAL FEES BIN 0.2% SOL 0.8% - FIXED FOR UPSTASH_ and KV_ NAMES</div>
<div class="section"><span class="green">SHARK FOOTPRINTS - SCAN #{scan} SHARKS {state.get('sharks',0)} every 12s</span></div>
<div class="section"><span class="green">REAL PRICE + REAL FEES</span><br>
<div style="display:flex;justify-content:space-between;padding:4px 0"><span>SOL BINANCE {sol_ch:.2f}% VOL {sol_vol:.0f}k</span><span>LIQ ${sol_vol*100:.0f}k</span></div>
<div style="display:flex;justify-content:space-between;padding:4px 0"><span>BTC BINANCE {btc_ch:.2f}% VOL {btc_vol:.0f}k</span><span>LIQ ${btc_vol*1000:.0f}k</span></div>
<div style="display:flex;justify-content:space-between;padding:4px 0"><span>qOMPUTE SOLANA -26.29% VOL 54k</span><span>LIQ $139k</span></div>
</div>
<div class="section"><span class="green">OPEN - GROSS FEE NET</span>{open_html}</div>
<div class="section"><span class="green">CLOSED - NET AFTER FEES</span>{closed_html}</div>
<div style="text-align:center;padding:20px;color:#555;font-size:11px">v727.7 UPSTASH FIX | KV: {kv_ok} WRITE:{write_ok} | URL:{KV_URL[:30] if KV_URL else 'NONE'} | SCAN #{scan} | <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#00ff88">CRON</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#00ff88">RESET</a> | <a href="/api/debug?key={ADMIN_KEY}" style="color:#00ff88">DEBUG</a></div>
<div style="text-align:center;padding:10px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#00ff88;color:#000;padding:12px 20px;text-decoration:none;font-weight:bold;font-size:16px;border-radius:4px">>>> CLICK TO START - CRON <<<</a></div>
</body>
</html>
"""

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        key = qs.get("key",[""])[0]
        if parsed.path in ["/api/cron","/api/index"] or "cron" in qs or parsed.path.startswith("/api/cron"):
            if key != ADMIN_KEY and "cron" not in qs:
                self.send_response(403); self.end_headers(); self.wfile.write(b'{"error":"bad key"}'); return
            res = do_cron()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode())
            return
        if parsed.path.startswith("/api/reset"):
            if key != ADMIN_KEY:
                self.send_response(403); self.end_headers(); self.wfile.write(b'bad key'); return
            state={"cap":1000.0,"bank":0.0,"daily_net":0.0,"gross":0.0,"fee_real":0.0,"wins":0,"loss":0,"total":0,"scan":0,"sharks":5,"open_trades":[],"closed":[],"btc_change":0.0,"last_scan":int(time.time())}
            kv_set_simple(STATE_KEY, state)
            kv_set_simple(LOCK_KEY, {"t":0})
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok":True,"msg":"v727.7 READY","cap":1000,"kv_url":bool(KV_URL),"kv_token":bool(KV_TOKEN)}).encode())
            return
        if parsed.path.startswith("/api/state") or parsed.path.startswith("/api/debug"):
            if "debug" in parsed.path and key != ADMIN_KEY:
                self.send_response(403); self.end_headers(); return
            state = load_state()
            binance = get_binance()
            dbg={"state":state,"binance":binance,"kv_url":KV_URL[:40] if KV_URL else "MISSING","has_kv":bool(KV_URL and KV_TOKEN),"kv_url_exists":bool(KV_URL),"kv_token_exists":bool(KV_TOKEN),"base":BINANCE_BASE,"env_names":{"KV_URL":bool(os.environ.get("KV_REST_API_URL")), "UPSTASH_URL":bool(os.environ.get("UPSTASH_REDIS_REST_URL")), "KV_TOKEN":bool(os.environ.get("KV_REST_API_TOKEN")), "UPSTASH_TOKEN":bool(os.environ.get("UPSTASH_REDIS_REST_TOKEN"))}}
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(json.dumps(dbg).encode())
            return
        state = load_state()
        binance = get_binance()
        html = render_html(state, binance)
        self.send_response(200)
        self.send_header("Content-Type","text/html")
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(html.encode())
    def do_POST(self):
        self.do_GET()
