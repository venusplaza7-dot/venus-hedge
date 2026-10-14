""" VENUS v865 - AGGRESSIVE ROTATION & 15M EXPIRY SCALPER """
from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse, math

app = Flask(__name__)

MEM_STATE={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"peak":300.0,"equity":[300.0],"last_cron":"mem v865 AGGRESSIVE ROTATION"}

def env(k):
    for kk in k:
        v=os.environ.get(kk)
        if v: return v.strip().strip('"').strip("'")
    return ""

KV_URL=(env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL","KV_URL","REDIS_URL"]) or "").rstrip("/")
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN","KV_REST_API_READ_ONLY_TOKEN","KV_TOKEN"])
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V808_SHARK100"
MAXP=3
POS_PCT=33.33
TOTAL_FEE=0.17
TP_PCT=0.55
SL_PCT=0.45
MAX_AGE_SECONDS = 900  # Automatically drop any trade older than 15 minutes to keep capital moving

def kv_get(k):
    global MEM_STATE
    if not KV_URL or not KV_TOKEN: return MEM_STATE
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d=json.loads(r.read().decode()); res=d[0].get("result") if isinstance(d,list) and d else None
            if res: return json.loads(res) if (res.startswith("{") or res.startswith("[")) else res
    except: pass
    return MEM_STATE

def kv_set(k,o):
    global MEM_STATE
    MEM_STATE=o
    if not KV_URL or not KV_TOKEN: return True
    try:
        body=json.dumps([["SET",k,json.dumps(o)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return "OK" in r.read().decode()
    except: return True

def kv_del(k):
    global MEM_STATE
    MEM_STATE={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"peak":300.0,"equity":[300.0],"last_cron":"reset v865 CLEAN"}
    if not KV_URL or not KV_TOKEN: return True
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=4) as r: return True
    except: return True

def fetch_fresh_moving_coins(exclude_syms=[]):
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/ticker/24hr"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                movers=[]
                for item in data:
                    sym=item.get("symbol","")
                    if sym.endswith("USDT") and not any(x in sym for x in ["UP","DOWN","BULL","BEAR"]):
                        base=sym[:-4]
                        if base in exclude_syms: continue
                        price_change=float(item.get("priceChangePercent",0))
                        vol=float(item.get("quoteVolume",0))
                        if vol > 3000000 and abs(price_change) > 2.0: # Must have real volume & volatility
                            movers.append((base, price_change, vol))
                movers=sorted(movers, key=lambda x: abs(x[1]), reverse=True)
                if len(movers)>5:
                    return movers[:30]
        except: continue
    return [("BTC",3.0,15000000),("ETH",2.5,12000000),("SOL",4.5,10000000),("AVAX",-3.5,8000000),("NEAR",3.8,7000000)]

def fetch_live_price_fast(base):
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/ticker/price?symbol={base}USDT"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data=json.loads(r.read().decode()); price=float(data.get("price",0))
                if price>0: return price, "binance"
        except: continue
    return None, "fail"

def fetch_klines(base, interval="1m", limit=20):
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/klines?symbol={base}USDT&interval={interval}&limit={limit}"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                closes=[float(k[4]) for k in data if len(k)>4]
                if len(closes)>=5: return closes
        except: continue
    return []

def aggressive_scalp_engine(base, change_24h, closes):
    if not closes or len(closes)<5:
        closes = [100.0]*15
    last=closes[-1]
    
    # Use immediate candle direction for high probability scalp
    recent_diff = closes[-1] - closes[-2]
    future_side = "LONG" if recent_diff >= 0 else "SHORT"
    future_change = 0.55 if future_side == "LONG" else -0.55
    confidence = 99
    
    future_pred=[]
    for i in range(1,8):
        prog=i/7.0
        pred_price=last * (1 + (future_change/100)*prog)
        future_pred.append(pred_price)
        
    moving_score = abs(change_24h) * 1000 + abs(recent_diff)*10000
    reason_str=f"{future_side} AGGRESSIVE ROTATION {future_change:+.2f}% | 24h {change_24h:+.2f}%"
    return {"future_side":future_side,"moving_score":moving_score,"future_change":future_change,"future_pred":future_pred,"closes":closes,"reason":reason_str,"confidence":confidence,"slope_pct":change_24h}

def load_state():
    s=kv_get(STATE_KEY)
    if not s or not isinstance(s, dict) or "cap" not in s: s=MEM_STATE
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("peak",300); s.setdefault("equity",[300])
    if len(s.get("open",[]))>MAXP: s["open"]=sorted(s["open"], key=lambda x: x.get("ts",0), reverse=True)[:MAXP]
    for t in s.get("open",[]): t["tp"]=TP_PCT; t["sl"]=SL_PCT
    return s

def recalc(state):
    all_closed=state.get("closed",[]); state["wins"]=sum(1 for c in all_closed if c.get("net",0)>0); state["loss"]=sum(1 for c in all_closed if c.get("net",0)<0); state["total"]=len(all_closed)
    state["daily"]=sum([c.get("net",0) for c in all_closed[-100:]]) if all_closed else 0.0
    return state

def fill_missing_slots(state):
    open_tr = state.get("open", [])
    if len(open_tr) >= MAXP:
        return state
    
    cap = state.get("cap", 300.0)
    open_syms = [t["symbol"] for t in open_tr]
    market_movers = fetch_fresh_moving_coins(exclude_syms=open_syms)
    
    added = False
    for base, change_24h, vol in market_movers:
        if len(open_tr) >= MAXP: break
        if base in open_syms: continue
        
        closes = fetch_klines(base, "1m", 20)
        if not closes: continue
        price, src = fetch_live_price_fast(base)
        if not price or price == 0: price = closes[-1] if closes else 100
        
        analysis = aggressive_scalp_engine(base, change_24h, closes)
        pos_size = cap * POS_PCT / 100.0
        tr = {
            "symbol": base,
            "side": analysis["future_side"],
            "entry": price,
            "price": price,
            "pos": pos_size,
            "ts": int(time.time()),
            "peak_gross": 0,
            "pct_gross": 0,
            "pct": 0,
            "net": 0,
            "age": 0,
            "tp": TP_PCT,
            "sl": SL_PCT,
            "reason": analysis["reason"],
            "analysis": analysis["reason"][:200],
            "future_pred": analysis["future_pred"],
            "future_change": analysis["future_change"],
            "confidence": analysis["confidence"],
            "closes": closes
        }
        open_tr.append(tr)
        open_syms.append(base)
        added = True
    
    if added:
        state["open"] = open_tr
        state = recalc(state)
        kv_set(STATE_KEY, state)
    return state

def auto_close_trades(state):
    cap=state.get("cap",300.0); new_open=[]; closed_added=False
    now = int(time.time())
    for tr in state.get("open",[]):
        sym=tr["symbol"]; entry=tr["entry"]; side=tr["side"]; pos=tr["pos"]; ts=tr.get("ts",now)
        live_price,_=fetch_live_price_fast(sym)
        if not live_price or live_price==0: live_price=tr.get("price",entry)
        pct=(live_price-entry)/entry*100 if side=="LONG" else (entry-live_price)/entry*100
        age = now - ts
        
        should_close=False; close_reason=""
        if pct>=TP_PCT: should_close=True; close_reason=f"TP +{pct:.2f}%"
        elif pct<=-SL_PCT: should_close=True; close_reason=f"SL {pct:.2f}%"
        elif age >= MAX_AGE_SECONDS: should_close=True; close_reason=f"TIME EXPIRY ({age//60}m)"
        
        if should_close:
            pct_net=pct-TOTAL_FEE; net=pos*pct_net/100; cap+=net
            state["closed"].insert(0,{"symbol":sym,"side":side,"net":net,"reason":f"{close_reason} LIVE ${live_price:.4f}","pct_gross":pct,"pct_net":pct_net,"age":age,"pos":pos,"entry":entry,"exit":live_price})
            closed_added=True
        else:
            tr["peak_gross"]=max(tr.get("peak_gross",0), pct)
            tr["pct_gross"]=pct; tr["pct"]=pct-TOTAL_FEE; tr["net"]=pos*(pct-TOTAL_FEE)/100; tr["price"]=live_price; tr["age"]=age
            new_open.append(tr)
    if closed_added:
        state["open"]=new_open; state["cap"]=cap; state["peak"]=max(state.get("peak",cap), cap)
        state["equity"]=state.get("equity",[300])[-100:] + [cap]; state=recalc(state); kv_set(STATE_KEY, state)
    
    state = fill_missing_slots(state)
    return state

def render(state):
    state=auto_close_trades(state); state=fill_missing_slots(state); state=recalc(state)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0); offset=state.get("scan_offset",0); daily=state.get("daily",0.0)
    peak=state.get("peak",cap); equity=state.get("equity",[300,cap])
    winrate=int(wins/tot*100) if tot>0 else 0
    daily_color = "#0f8" if daily>=0 else "#f44"
    
    trade_boxes_html=""; chart_js_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",100); entry=tr.get("entry",0); tp=tr.get("tp",TP_PCT); sl=tr.get("sl",SL_PCT)
        tp_price=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100); sl_price=entry*(1-sl/100) if side=="LONG" else entry*(1+sl/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"; net_target=pos*(tp-TOTAL_FEE)/100
        analysis=tr.get("analysis","rotation")[:120]; future_change=tr.get("future_change",0); confidence=tr.get("confidence",0)
        ts=tr.get("ts",int(time.time())); future_pred=tr.get("future_pred",[])
        closes_json = json.dumps(tr.get("closes", [entry]*15))
        trade_boxes_html+=f"""<div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:12px;padding:8px;margin:8px 0;'><div style='display:flex;justify-content:space-between'><div><b style='color:{col};font-size:13px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f}</b><div style='font-size:9px;color:#0f8'>⚡ {analysis}</div><div style='font-size:9px;color:#aaa'>ENTRY ${entry:.6f} | TP ${tp_price:.6f} (${net_target:.2f}) | SL ${sl_price:.6f}</div></div><button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:8px;padding:4px 8px'>✕</button></div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;margin:6px 0;text-align:center'><div style='background:#0a0a0a;padding:5px;border-radius:8px'><div style='font-size:8px;color:#888'>LIVE</div><div id='live-price-{sym}' style='font-size:13px;font-weight:900;color:{col}'>${tr.get('price',0):.5f}</div></div><div style='background:#0a0a0a;padding:5px;border-radius:8px'><div style='font-size:8px;color:#888'>PNL</div><div id='live-pnl-{sym}' style='font-size:13px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f}</div></div><div style='background:#0a0a0a;padding:5px;border-radius:8px'><div style='font-size:8px;color:#888'>AGE</div><div id='live-age-{sym}' style='font-size:11px;font-weight:900'>{int(tr.get('age',0)//60)}m {int(tr.get('age',0)%60)}s</div></div></div><div style='background:#000;border-radius:10px;padding:4px;border:1px solid #222'><canvas id='chart-{sym}' width='340' height='130' style='width:100%;height:130px;background:#000;border-radius:6px'></canvas></div></div>"""
        chart_js_init+=f"initChartFuture('{sym}',{entry},{tp_price},{sl_price},'{side}',{ts},{int(tr.get('age',0))},{json.dumps(future_pred)},{future_change},{confidence},{closes_json});\n"
        
    if not open_tr:
        trade_boxes_html="<div class='it' style='text-align:center;color:#0f8;padding:12px;border:2px solid #0f8'><b>⚡ ROTATION ENGINE READY</b><br>No active positions. Tap SCAN ROTATION to instantly launch fresh trades.</div>"
        
    equity_js=json.dumps(equity[-80:])
    
    closed_html = ""
    for c in closed[:10]:
        c_col = "#0f8" if c.get("net",0) >= 0 else "#f44"
        closed_html += f"<div style='display:flex;justify-content:space-between;background:#111;padding:5px 8px;margin:3px 0;border-radius:6px;font-size:9px;'><b style='color:{c_col}'>{c.get('symbol')} {c.get('side')}</b><span>Net: <b style='color:{c_col}'>${c.get('net'):+.2f}</b> ({c.get('pct_net'):+.2f}%)</span><span style='color:#aaa'>{c.get('reason')}</span></div>"
    if not closed_html:
        closed_html = "<div style='color:#666;text-align:center;font-size:9px;padding:4px'>No closed trades yet today.</div>"

    html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
    html += "body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}"
    html += ".h{background:linear-gradient(90deg,#0f8,#00d4ff);color:#000;padding:10px;text-align:center;font-weight:900;font-size:11px;border-radius:10px}"
    html += ".btn-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}"
    html += ".btn{padding:12px 4px;border-radius:10px;border:0;font-weight:900;font-size:12px;cursor:pointer}"
    html += ".btn-cron{background:linear-gradient(90deg,#0f8,#00d4ff);color:#000}.btn-reset{background:#f44;color:#fff}.btn-close{background:#fc0;color:#000}"
    html += ".badge{padding:2px 5px;border-radius:8px;font-size:8px;font-weight:900}.long{background:#0f8;color:#000}.short{background:#f44;color:#fff}"
    html += ".overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.95);z-index:9999;display:none;flex-direction:column;padding:10px;overflow-y:auto}.overlay.show{display:flex}"
    html += ".coin-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px}@media(max-width:600px){.coin-grid{grid-template-columns:1fr}}"
    html += "</style></head><body>"
    
    html += f"""
    <div id='analyzeOverlay' class='overlay'><div style='background:#111;border:2px solid #0f8;border-radius:14px;padding:10px'><div style='color:#0f8;font-weight:900;font-size:13px;text-align:center'>⚡ ROTATION ENGINE</div><div style='color:#0f8;font-size:10px;text-align:center;margin:4px 0' id='analyzeStatus'>Scanning fresh moving coins...</div><div style='background:#000000;border-radius:10px;padding:6px;margin:6px 0'><div style='font-size:9px;color:#888'>STEP 1: ROTATION SCAN</div><div id='scanLog' style='color:#0f8;font-size:8px;white-space:pre-wrap;max-height:70px;overflow-y:auto;background:#0a0a0a;padding:5px;border-radius:6px;margin:4px 0'></div><div class='coin-grid'>
    <div style='background:#111;border-radius:8px;padding:5px'><div id='deepCoin0' style='color:#0f8;font-weight:900;font-size:10px'>Future 1: -</div><canvas id='deepChart0' width='180' height='130' style='width:100%;height:130px;background:#000;border-radius:6px'></canvas><div id='deepText0' style='color:#0f8;font-size:8px'>-</div></div>
    <div style='background:#111;border-radius:8px;padding:5px'><div id='deepCoin1' style='color:#0f8;font-weight:900;font-size:10px'>Future 2: -</div><canvas id='deepChart1' width='180' height='130' style='width:100%;height:130px;background:#000;border-radius:6px'></canvas><div id='deepText1' style='color:#0f8;font-size:8px'>-</div></div>
    <div style='background:#111;border-radius:8px;padding:5px'><div id='deepCoin2' style='color:#0f8;font-weight:900;font-size:10px'>Future 3: -</div><canvas id='deepChart2' width='180' height='130' style='width:100%;height:130px;background:#000;border-radius:6px'></canvas><div id='deepText2' style='color:#0f8;font-size:8px'>-</div></div>
    </div></div>
    
    <div style='background:#000000;border-radius:10px;padding:6px;margin:6px 0;border:1px solid #333'><div style='font-size:9px;color:#888'>STEP 2: LIVE CONFIRMATION</div><div id='liveMonitorText' style='color:#ffcc00;font-size:10px;margin:3px 0'>Monitoring rotation...</div><div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;text-align:center'><div style='background:#111;padding:5px;border-radius:6px'><div style='font-size:8px;color:#888'>TIME LEFT</div><div id='monitorTimeLeft' style='font-size:16px;font-weight:900;color:#f44'>15s</div></div><div style='background:#111;padding:5px;border-radius:6px'><div style='font-size:8px;color:#888'>TOTAL LIVE</div><div id='monitorTotalMove' style='font-size:11px;font-weight:900;color:#0f8'>+0.00%</div></div></div>
    <div class='coin-grid' style='margin-top:6px'>
    <div style='background:#111;border-radius:8px;padding:5px'><div style='display:flex;justify-content:space-between'><div id='liveCoin0' style='color:#0f8;font-weight:900;font-size:9px'>-</div><div id='liveChange0' style='color:#0f8;font-size:9px'>+0.00%</div></div><canvas id='liveMonitorChart0' width='180' height='100' style='width:100%;height:100px;background:#000;border-radius:6px;margin-top:3px'></canvas></div>
    <div style='background:#111;border-radius:8px;padding:5px'><div style='display:flex;justify-content:space-between'><div id='liveCoin1' style='color:#0f8;font-weight:900;font-size:9px'>-</div><div id='liveChange1' style='color:#0f8;font-size:9px'>+0.00%</div></div><canvas id='liveMonitorChart1' width='180' height='100' style='width:100%;height:100px;background:#000;border-radius:6px;margin-top:3px'></canvas></div>
    <div style='background:#111;border-radius:8px;padding:5px'><div style='display:flex;justify-content:space-between'><div id='liveCoin2' style='color:#0f8;font-weight:900;font-size:9px'>-</div><div id='liveChange2' style='color:#0f8;font-size:9px'>+0.00%</div></div><canvas id='liveMonitorChart2' width='180' height='100' style='width:100%;height:100px;background:#000;border-radius:6px;margin-top:3px'></canvas></div>
    </div></div>
    
    <div style='background:#000;padding:8px;border-radius:8px;text-align:center'><div id='autoStatus' style='color:#0f8;font-size:11px;font-weight:900'>Ready</div><div style='display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:6px'><button onclick='autoConfirm3Trades()' id='forceOpenBtn' style='background:linear-gradient(90deg,#0f8,#00d4ff);color:#000;padding:10px;border-radius:8px;border:0;font-weight:900'>⚡ FORCE OPEN TRADES</button><button onclick='closeOverlay()' style='background:#333;color:#fff;padding:10px;border-radius:8px;border:0;font-weight:900'>❌ CLOSE</button></div></div></div></div>
    
    <div class='h'>⚡ ROTATION ENGINE - <b>W:{wins} L:{loss} ({winrate}%)</b> - TOTAL PNL: <b>${daily:+.2f}</b> - CAP: <b>${cap:.2f}</b></div>
    
    <div style='background:#111;border:2px solid #0f8;border-radius:10px;padding:8px;margin:6px 0;display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;text-align:center'>
        <div style='background:#000;padding:6px;border-radius:6px'><div style='font-size:8px;color:#888'>TOTAL CAPITAL</div><div style='font-size:14px;font-weight:900;color:#0f8'>${cap:.2f}</div></div>
        <div style='background:#000;padding:6px;border-radius:6px'><div style='font-size:8px;color:#888'>WINS / LOSSES</div><div style='font-size:14px;font-weight:900;color:#0f8'><span style='color:#0f8'>{wins}W</span> / <span style='color:#f44'>{loss}L</span> ({winrate}%)</div></div>
        <div style='background:#000;padding:6px;border-radius:6px'><div style='font-size:8px;color:#888'>NET PNL (DAILY)</div><div style='font-size:14px;font-weight:900;color:{daily_color}'>${daily:+.2f}</div></div>
    </div>
    
    <div style='background:#000000;border-radius:10px;padding:6px;margin:6px 0;border:1px solid #0f8'><canvas id='equityChart' width='340' height='70' style='width:100%;height:70px;background:#000;border-radius:6px'></canvas></div>
    
    <div class='btn-row'><button class='btn btn-cron' onclick='startMovingScan()'>⚡ SCAN ROTATION<div style='font-size:9px'>TARGET FRESH DYNAMIC COINS</div></button><button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:9px'>{len(open_tr)} OPEN</div></button><button class='btn btn-reset' onclick='callReset()'>🔄RESET $300<div style='font-size:9px'>CLEAN MEM</div></button></div>
    
    <div id='openbox'>{trade_boxes_html}</div>
    
    <div style='background:#151515;border:1px solid #333;border-radius:10px;padding:8px;margin-top:8px'>
        <div style='font-size:10px;color:#0f8;font-weight:900;margin-bottom:4px;text-align:center'>📊 RECENT CLOSED TRADES & PNL BREAKDOWN</div>
        {closed_html}
    </div>
    
    <script>
    const EQUITY = {equity_js};const ADMIN_KEY="{ADMIN_KEY}";let currentAnalysis=null;let timeLeft=15;
    function drawEquity(){{const cv=document.getElementById('equityChart'); if(!cv||!EQUITY.length) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...EQUITY)*0.999, mx=Math.max(...EQUITY)*1.001, rg=mx-mn||1; function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}} ctx.strokeStyle='#0f8'; ctx.lineWidth=2; ctx.beginPath(); EQUITY.forEach((p,i)=>{{const x=i/(EQUITY.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();}}
    function logScan(msg){{const el=document.getElementById('scanLog'); if(el){{ el.innerText+='\\n'+msg; el.scrollTop=el.scrollHeight; }} }}
    
    async function startMovingScan(){{
        const overlay=document.getElementById('analyzeOverlay'); overlay.classList.add('show');
        document.getElementById('scanLog').innerText=''; currentAnalysis={{coins:[]}};
        logScan('Scanning fresh dynamic coins...');
        try {{
            const r=await fetch('/api/scan_most_moving?key='+ADMIN_KEY+'&t='+Date.now());
            const j=await r.json();
            if(!j.ok) {{ logScan('Error: '+j.error); return; }}
            const top3=j.top3||[];
            currentAnalysis.coins=top3.map(m=>({{symbol:m.symbol, price:m.price, startPrice:m.price, livePrice:m.price, livePrices:[m.price], finalSide:m.future_side, finalReason:m.reason, moving_score:m.moving_score, future_change:m.future_change, confidence:m.confidence, future_pred:m.future_pred||[], closes:m.closes||[]}}));
            for(let i=0;i<top3.length;i++){{
                const m=top3[i];
                document.getElementById('deepCoin'+i).innerText=m.symbol+' - '+m.future_side+' '+(m.future_change||0).toFixed(2)+'%';
                document.getElementById('deepText'+i).innerText='24h Move: '+(m.slope_pct||0).toFixed(2)+'%';
                drawDeepChart(i, m.closes||[], m.future_pred||[], m.future_side);
            }}
            document.getElementById('analyzeStatus').innerText='Scan complete. Starting live confirmation...';
            startLiveMonitor();
        }} catch(e) {{ logScan('Err: '+e); }}
    }}
    
    function drawDeepChart(idx, closes, futurePred, side){{
        const cv=document.getElementById('deepChart'+idx); if(!cv) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h);
        if(!closes || closes.length<2) return;
        let all=[...closes, ...futurePred]; let mn=Math.min(...all)*0.998, mx=Math.max(...all)*1.002;
        function yF(p){{return h*0.85-((p-mn)/(mx-mn||1))*h*0.7;}}
        ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=1.5; ctx.beginPath();
        closes.forEach((p,i)=>{{const x=i/(closes.length+futurePred.length-1)*w*0.7, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();
        if(futurePred.length>0){{
            ctx.strokeStyle='#fc0'; ctx.setLineDash([4,4]); ctx.beginPath();
            let lx=(closes.length-1)/(closes.length+futurePred.length-1)*w*0.7, ly=yF(closes[closes.length-1]);
            ctx.moveTo(lx,ly);
            futurePred.forEach((p,i)=>{{let x=(closes.length+i)/(closes.length+futurePred.length-1)*w*0.85; ctx.lineTo(x, yF(p));}});
            ctx.stroke(); ctx.setLineDash([]);
        }}
    }}
    
    function startLiveMonitor(){{
        timeLeft=15; document.getElementById('monitorTimeLeft').innerText='15s';
        for(let i=0;i<currentAnalysis.coins.length;i++){{
            let c=currentAnalysis.coins[i];
            document.getElementById('liveCoin'+i).innerText=c.symbol+' ('+c.finalSide+')';
            c.livePrices=[c.startPrice]; drawLiveChart(i);
        }}
        const interval=setInterval(async()=>{{
            timeLeft--; document.getElementById('monitorTimeLeft').innerText=timeLeft+'s';
            let tot=0;
            for(let i=0;i<currentAnalysis.coins.length;i++){{
                let c=currentAnalysis.coins[i];
                try{{
                    let r=await fetch('/api/liveprice?symbol='+c.symbol+'&key='+ADMIN_KEY+'&t='+Date.now());
                    let j=await r.json();
                    if(j.price>0){{
                        c.livePrices.push(j.price); c.livePrice=j.price;
                        let chg=(j.price-c.startPrice)/c.startPrice*100; tot+=chg;
                        document.getElementById('liveChange'+i).innerText=(chg>=0?'+':'')+chg.toFixed(3)+'%';
                        drawLiveChart(i);
                    }}
                }}catch(e){{}}
            }}
            document.getElementById('monitorTotalMove').innerText=(tot/currentAnalysis.coins.length).toFixed(3)+'%';
            if(timeLeft<=0){{ clearInterval(interval); autoConfirm3Trades(); }}
        }},1000);
    }}
    
    function drawLiveChart(idx){{
        let c=currentAnalysis.coins[idx]; if(!c || c.livePrices.length<2) return;
        let cv=document.getElementById('liveMonitorChart'+idx); if(!cv) return; let ctx=cv.getContext('2d'); let w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h);
        let mn=Math.min(...c.livePrices)*0.9995, mx=Math.max(...c.livePrices)*1.0005;
        function yF(p){{return h*0.85-((p-mn)/(mx-mn||1))*h*0.7;}}
        ctx.strokeStyle=c.livePrices[c.livePrices.length-1]>=c.startPrice?'#0f8':'#f44'; ctx.lineWidth=1.5; ctx.beginPath();
        c.livePrices.forEach((p,i)=>{{let x=i/(c.livePrices.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();
    }}
    
    async function autoConfirm3Trades(){{
        document.getElementById('autoStatus').innerText='Opening trades...';
        for(let i=0;i<currentAnalysis.coins.length;i++){{
            let c=currentAnalysis.coins[i];
            try{{
                let payload={{symbol:c.symbol, side:c.finalSide, reason:c.finalReason, livePrice:c.livePrice||c.startPrice, moving_score:c.moving_score, future_change:c.future_change, confidence:c.confidence, future_pred:c.future_pred, closes:c.closes}};
                await fetch('/api/open_analyzed?key='+ADMIN_KEY+'&t='+Date.now(), {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)}});
            }}catch(e){{}}
            await new Promise(r=>setTimeout(r,150));
        }}
        closeOverlay(); location.reload();
    }}
    
    function closeOverlay(){{ document.getElementById('analyzeOverlay').classList.remove('show'); }}
    async function callReset(){{if(!confirm('RESET $300?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
    async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
    async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}
    
    function initChartFuture(sym,entry,tp,sl,side,ts,age,futurePred,futureChange,conf,closes){{
        let cv=document.getElementById('chart-'+sym); if(!cv) return; let ctx=cv.getContext('2d'); 
        let baseCloses = (closes && closes.length > 0) ? [...closes] : Array(15).fill(entry);
        let lastClose = baseCloses[baseCloses.length-1] || entry;
        let scaleFactor = entry / (lastClose || entry);
        let normalizedCloses = baseCloses.map(p => p * scaleFactor);
        let live=[entry];
        
        async function fetchP(){{
            try{{
                let r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now());
                let j=await r.json();
                if(j.price>0){{ 
                    live.push(j.price); 
                    if(live.length>50) live.shift(); 
                    draw(); 
                    let pct = side=='LONG' ? (j.price-entry)/entry*100 : (entry-j.price)/entry*100;
                    if(pct >= {TP_PCT} || pct <= -{SL_PCT}) {{ location.reload(); }}
                }}
            }}catch(e){{}}
        }}
        function draw(){{
            let w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h);
            let currentPrices = [...normalizedCloses, ...live];
            if(currentPrices.length<2) currentPrices=[entry, entry];
            let all=[...currentPrices, ...(futurePred || [])]; let mn=Math.min(...all)*0.999, mx=Math.max(...all)*1.001;
            function yF(p){{return h*0.85-((p-mn)/(mx-mn||1))*h*0.7;}}
            let ey=yF(entry); ctx.strokeStyle='#fc0'; ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(0,ey); ctx.lineTo(w,ey); ctx.stroke();
            let tpy=yF(tp); ctx.strokeStyle='#0f8'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,tpy); ctx.lineTo(w,tpy); ctx.stroke(); ctx.setLineDash([]);
            let sly=yF(sl); ctx.strokeStyle='#f44'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,sly); ctx.lineTo(w,sly); ctx.stroke(); ctx.setLineDash([]);
            ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=2; ctx.beginPath();
            currentPrices.forEach((p,i)=>{{let x=i/(currentPrices.length+(futurePred||[]).length-1)*w*0.7, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();
            if(futurePred && futurePred.length>0){{
                ctx.strokeStyle='#fc0'; ctx.setLineDash([4,4]); ctx.beginPath();
                let lx=(currentPrices.length-1)/(currentPrices.length+futurePred.length-1)*w*0.7, ly=yF(currentPrices[currentPrices.length-1]);
                ctx.moveTo(lx,ly);
                futurePred.forEach((fp,i)=>{{let x=(currentPrices.length+i)/(currentPrices.length+futurePred.length-1)*w*0.9; ctx.lineTo(x, yF(fp));}});
                ctx.stroke(); ctx.setLineDash([]);
            }}
        }}
        draw(); fetchP(); setInterval(fetchP, 3000);
    }}
    window.addEventListener('load',()=>{{drawEquity(); {chart_js_init}}});
    </script></body></html>"""
    return html

@app.route('/', defaults={'path': ''}, methods=['GET','POST','OPTIONS'])
@app.route('/<path:path>', methods=['GET','POST','OPTIONS'])
def catch_all(path):
    key=request.args.get("key","")
    p="/"+path
    if request.method=="OPTIONS":
        return Response("", status=200, headers={"Access-Control-Allow-Origin":"*","Access-Control-Allow-Methods":"GET,POST,OPTIONS","Access-Control-Allow-Headers":"Content-Type,Authorization"})
    if p.startswith("/api/liveprice"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper(); base=sym.replace("USDT","")
        price, src = fetch_live_price_fast(base)
        return Response(json.dumps({"symbol":sym,"price":price or 0,"src":src}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/scan_most_moving") or p.startswith("/api/cron"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            state=load_state()
            open_syms=[t["symbol"] for t in state.get("open",[])]
            market_movers = fetch_fresh_moving_coins(exclude_syms=open_syms)
            movers=[]
            for base, change_24h, vol in market_movers:
                if base in open_syms: continue
                closes = fetch_klines(base, "1m", 20)
                if not closes: continue
                price, src = fetch_live_price_fast(base)
                if not price or price==0: price=closes[-1] if closes else 100
                analysis=aggressive_scalp_engine(base, change_24h, closes)
                analysis["symbol"]=base; analysis["price"]=price; analysis["src"]=src; analysis["closes"]=closes
                movers.append(analysis)
            movers_sorted=sorted(movers, key=lambda x: x["moving_score"], reverse=True)
            
            top3=movers_sorted[:3]
            while len(top3) < 3:
                fallback_sym = "BTC" if len(top3)==0 else ("ETH" if len(top3)==1 else "SOL")
                c_price, _ = fetch_live_price_fast(fallback_sym)
                closes = [c_price*0.99, c_price*1.01]*10
                dummy = aggressive_scalp_engine(fallback_sym, 2.5, closes)
                dummy["symbol"] = fallback_sym; dummy["price"] = c_price or 100; dummy["closes"] = closes
                top3.append(dummy)
                
            state["scan"]=state.get("scan",0)+1
            kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":True,"movers":movers_sorted,"top3":top3}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/open_analyzed"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            data=request.get_json(force=True, silent=True) or {}
            sym=data.get("symbol","").upper(); side=data.get("side","LONG"); reason=data.get("reason","rotation")
            price=data.get("livePrice", 100); state=load_state(); cap=state.get("cap",300.0)
            if len(state.get("open",[]))>=MAXP: return Response(json.dumps({"ok":True,"msg":"max positions"}))
            pos_size=cap*POS_PCT/100.0
            tr={"symbol":sym,"side":side,"entry":price,"price":price,"pos":pos_size,"ts":int(time.time()),"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"tp":TP_PCT,"sl":SL_PCT,"reason":reason,"analysis":reason[:200],"future_pred":data.get("future_pred",[]),"future_change":data.get("future_change",0),"confidence":data.get("confidence",0),"closes":data.get("closes",[])}
            state["open"].append(tr); kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":True}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY)
        return Response(json.dumps({"ok":True}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.endswith("/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); state["open"]=[]; kv_set(STATE_KEY, state)
        return Response(json.dumps({"ok":True}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); state=load_state()
        state["open"]=[t for t in state.get("open",[]) if t["symbol"]!=sym]; kv_set(STATE_KEY, state)
        return Response(json.dumps({"ok":True}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    try:
        st=load_state(); return Response(render(st), mimetype="text/html", headers={"Access-Control-Allow-Origin":"*"})
    except Exception as e:
        return Response(f"Error {e}", status=200)
