""" VENUS v1050 - BTC & ETH EXCLUSIVE SNIPER """
from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse, math

app = Flask(__name__)

MEM_STATE={"cap":266.22,"daily":-33.78,"fees_paid":0.0,"wins":2,"loss":0,"total":2,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"peak":300.0,"equity":[300.0, 261.03, 262.68, 266.22],"daily_target_reached":False,"last_cron":"mem v1050 BTC ETH ONLY"}

def env(k):
    for kk in k:
        v=os.environ.get(kk)
        if v: return v.strip().strip('"').strip("'")
    return ""

KV_URL=(env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL","KV_URL","REDIS_URL"]) or "").rstrip("/")
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN","KV_REST_API_READ_ONLY_TOKEN","KV_TOKEN"])
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V1050_BTC_ETH_STATE"
MAXP=1  
POS_PCT=100.0 
TOTAL_FEE=0.17

TP_PCT=0.60       # Step-up profit target (~$1.30 net win)
SL_PCT=3.85       # Wide ~$10 risk buffer breathing room
DAILY_PROFIT_GOAL = 10.0 
MAX_AGE_SECONDS = 86400 # 24 hours (unlimited time)

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
    MEM_STATE={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"peak":300.0,"equity":[300.0],"daily_target_reached":False,"last_cron":"reset v1050 CLEAN"}
    if not KV_URL or not KV_TOKEN: return True
    try:
        body=json.dumps([["SET",k,json.dumps(MEM_STATE)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=4) as r: return True
    except: return True

def fetch_exclusive_targets(exclude_syms=[]):
    """Restricts target assets strictly to BTC and ETH for fast-moving liquidity."""
    all_targets = ["BTC", "ETH"]
    return [t for t in all_targets if t not in exclude_syms]

def fetch_live_price_fast(base):
    if base in ["PUMP", "TEST", "DUMMY"]: return None, "blocked"
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/ticker/price?symbol={base}USDT"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data=json.loads(r.read().decode()); price=float(data.get("price",0))
                if price > 0: return price, "binance"
        except: continue
    return None, "fail"

def fetch_klines(base, interval="5m", limit=30):
    if base in ["PUMP", "TEST", "DUMMY"]: return []
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/klines?symbol={base}USDT&interval={interval}&limit={limit}"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                closes=[float(k[4]) for k in data if len(k)>4]
                if len(closes)>=15: return closes
        except: continue
    return []

def analyze_signal(closes):
    """Deep chart analysis across historical candlesticks and moving averages."""
    if not closes or len(closes) < 15:
        return "SKIP", 0.0
    ma_short = sum(closes[-5:]) / 5
    ma_mid = sum(closes[-10:]) / 10
    ma_long = sum(closes[-15:]) / 15
    momentum_delta = ((closes[-1] - closes[-5]) / closes[-5]) * 100
    
    if ma_short > ma_mid and ma_mid > ma_long and momentum_delta > 0.15:
        return "LONG", momentum_delta
    elif ma_short < ma_mid and ma_mid < ma_long and momentum_delta < -0.15:
        return "SHORT", momentum_delta
    return "SKIP", momentum_delta

def load_state():
    s=kv_get(STATE_KEY)
    if not s or not isinstance(s, dict) or "cap" not in s: s=MEM_STATE
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("peak",300); s.setdefault("equity",[300])
    s.setdefault("daily_target_reached", False)
    
    unique_open=[]
    seen_syms=set()
    for tr in s.get("open",[]):
        sym = tr.get("symbol")
        if sym and sym not in seen_syms and sym not in ["PUMP", "TEST"]:
            seen_syms.add(sym)
            unique_open.append(tr)
    s["open"] = unique_open[:MAXP]
    for t in s.get("open",[]): 
        t.setdefault("peak_gross", 0.0)
        t["tp"]=TP_PCT; t["sl"]=SL_PCT
    return s

def recalc(state):
    all_closed=state.get("closed",[]); state["wins"]=sum(1 for c in all_closed if c.get("net",0)>0); state["loss"]=sum(1 for c in all_closed if c.get("net",0)<0); state["total"]=len(all_closed)
    state["daily"]=sum([c.get("net",0) for c in all_closed[-100:]]) if all_closed else 0.0
    if state["daily"] >= DAILY_PROFIT_GOAL:
        state["daily_target_reached"] = True
    return state

def fill_missing_slots(state):
    if state.get("daily_target_reached", False): return state
    open_tr = state.get("open", [])
    if len(open_tr) >= MAXP: return state
    
    cap = state.get("cap", 266.22)
    open_syms = [t["symbol"] for t in open_tr]
    recent_closed = [c["symbol"] for c in state.get("closed", [])[:3]]
    excluded = list(set(open_syms + recent_closed))
    
    targets = fetch_exclusive_targets(exclude_syms=excluded)
    added = False
    
    for base in targets:
        if len(open_tr) >= MAXP: break
        if base in open_syms: continue
        
        closes = fetch_klines(base, "5m", 30)
        if not closes: continue
        
        side, trend_strength = analyze_signal(closes)
        if side == "SKIP": continue
            
        price, src = fetch_live_price_fast(base)
        if not price or price <= 0: continue
        
        future_change = TP_PCT if side == "LONG" else -TP_PCT
        future_pred = []
        for i in range(1, 8):
            prog = i / 7.0
            future_pred.append(price * (1 + (future_change / 100) * prog))
            
        pos_size = cap * (POS_PCT / 100.0)
        tr = {
            "symbol": base,
            "side": side,
            "entry": price,
            "price": price,
            "pos": pos_size,
            "ts": int(time.time()),
            "peak_gross": 0.0,
            "pct_gross": 0,
            "pct": 0,
            "net": 0,
            "age": 0,
            "tp": TP_PCT,
            "sl": SL_PCT,
            "reason": f"BTC/ETH EXCLUSIVE {base} 5M {side} ({trend_strength:+.2f}%)",
            "analysis": f"Major Asset Analyzer (~$1.30 Net Win / -$10 Risk)",
            "future_pred": future_pred,
            "future_change": future_change,
            "confidence": 99,
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
    cap=state.get("cap",266.22); new_open=[]; closed_added=False
    now = int(time.time())
    for tr in state.get("open",[]):
        sym=tr["symbol"]; entry=tr["entry"]; side=tr["side"]; pos=tr["pos"]; ts=tr.get("ts",now)
        live_price,_=fetch_live_price_fast(sym)
        if not live_price or live_price<=0: 
            new_open.append(tr)
            continue
        pct=(live_price-entry)/entry*100 if side=="LONG" else (entry-live_price)/entry*100
        age = now - ts
        
        peak = max(tr.get("peak_gross", 0.0), pct)
        tr["peak_gross"] = peak
        
        should_close=False; close_reason=""
        if pct >= TP_PCT: 
            should_close=True; close_reason=f"TP HIT +{pct:.2f}% (~$1.30)"
        elif pct <= -SL_PCT: 
            should_close=True; close_reason=f"SL BUFFER HIT (-$10 / {pct:.2f}%)"
        elif age >= MAX_AGE_SECONDS: 
            should_close=True; close_reason=f"EXPIRY (24h reached)"
        
        if should_close:
            pct_net=pct-TOTAL_FEE; net=pos*pct_net/100; cap+=net
            state["closed"].insert(0,{"symbol":sym,"side":side,"net":net,"reason":f"{close_reason} LIVE ${live_price:.2f}","pct_gross":pct,"pct_net":pct_net,"age":age,"pos":pos,"entry":entry,"exit":live_price})
            closed_added=True
        else:
            tr["pct_gross"]=pct; tr["pct"]=pct-TOTAL_FEE; tr["net"]=pos*(pct-TOTAL_FEE)/100; tr["price"]=live_price; tr["age"]=age
            new_open.append(tr)
    if closed_added:
        state["open"]=new_open; state["cap"]=cap; state["peak"]=max(state.get("peak",cap), cap)
        state["equity"]=state.get("equity",[300])[-100:] + [cap]; state=recalc(state); kv_set(STATE_KEY, state)
    
    state = fill_missing_slots(state)
    return state

def render(state):
    state=auto_close_trades(state); state=fill_missing_slots(state); state=recalc(state)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",266.22); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); daily=state.get("daily",0.0)
    equity=state.get("equity",[300,cap])
    winrate=int(wins/tot*100) if tot>0 else 0
    daily_color = "#0f8" if daily>=0 else "#f44"
    target_reached = state.get("daily_target_reached", False)
    
    trade_boxes_html=""; chart_js_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",266); entry=tr.get("entry",0); tp=tr.get("tp",TP_PCT); sl=tr.get("sl",SL_PCT)
        tp_price=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100); sl_price=entry*(1-sl/100) if side=="LONG" else entry*(1+sl/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"; net_target=pos*(tp-TOTAL_FEE)/100
        analysis=tr.get("analysis","btc eth focus")[:120]; future_change=tr.get("future_change",0); confidence=tr.get("confidence",0)
        ts=tr.get("ts",int(time.time())); future_pred=tr.get("future_pred",[])
        closes_json = json.dumps(tr.get("closes", [entry]*15))
        trade_boxes_html+=f"""<div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:12px;padding:8px;margin:8px 0;'><div style='display:flex;justify-content:space-between'><div><b style='color:{col};font-size:13px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f}</b><div style='font-size:9px;color:#0f8'>⚡ {analysis}</div><div style='font-size:9px;color:#aaa'>ENTRY ${entry:.2f} | TP ${tp_price:.2f} (${net_target:.2f}) | SL ${sl_price:.2f}</div></div><button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:8px;padding:4px 8px;cursor:pointer'>✕</button></div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;margin:6px 0;text-align:center'><div style='background:#0a0a0a;padding:5px;border-radius:8px'><div style='font-size:8px;color:#888'>LIVE</div><div id='live-price-{sym}' style='font-size:13px;font-weight:900;color:{col}'>${tr.get('price',0):.2f}</div></div><div style='background:#0a0a0a;padding:5px;border-radius:8px'><div style='font-size:8px;color:#888'>PNL</div><div id='live-pnl-{sym}' style='font-size:13px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f}</div></div><div style='background:#0a0a0a;padding:5px;border-radius:8px'><div style='font-size:8px;color:#888'>AGE</div><div id='live-age-{sym}' style='font-size:11px;font-weight:900' data-ts='{ts}'>0m 0s</div></div></div><div style='background:#000;border-radius:10px;padding:4px;border:1px solid #222'><canvas id='chart-{sym}' width='340' height='130' style='width:100%;height:130px;background:#000;border-radius:6px'></canvas></div></div>"""
        chart_js_init+=f"initChartFuture('{sym}',{entry},{tp_price},{sl_price},'{side}',{ts},{int(tr.get('age',0))},{json.dumps(future_pred)},{future_change},{confidence},{closes_json},'{pos}','{TOTAL_FEE}');\n"
        
    if not open_tr:
        if target_reached:
            trade_boxes_html="<div class='it' style='text-align:center;color:#0f8;padding:12px;border:2px solid #0f8'><b>🎯 DAILY PROFIT TARGET REACHED</b><br>Session locked and unplugged for today. Great job!</div>"
        else:
            trade_boxes_html="<div class='it' style='text-align:center;color:#0f8;padding:12px;border:2px solid #0f8'><b>🚀 BTC & ETH EXCLUSIVE SNIPER READY</b><br>Scanning Bitcoin and Ethereum for optimal setups...</div>"
        
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
    html += "</style></head><body>"
    
    html += f"""
    <div class='h'>🚀 BTC & ETH EXCLUSIVE SNIPER - <b>W:{wins} L:{loss} ({winrate}%)</b> - CAP: <b>${cap:.2f}</b></div>
    
    <div style='background:#111;border:2px solid #0f8;border-radius:10px;padding:8px;margin:6px 0;display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;text-align:center'>
        <div style='background:#000;padding:6px;border-radius:6px'><div style='font-size:8px;color:#888'>TOTAL CAPITAL</div><div style='font-size:14px;font-weight:900;color:#0f8'>${cap:.2f}</div></div>
        <div style='background:#000;padding:6px;border-radius:6px'><div style='font-size:8px;color:#888'>WINS / LOSSES</div><div style='font-size:14px;font-weight:900;color:#0f8'><span style='color:#0f8'>{wins}W</span> / <span style='color:#f44'>{loss}L</span> ({winrate}%)</div></div>
        <div style='background:#000;padding:6px;border-radius:6px'><div style='font-size:8px;color:#888'>NET PNL (DAILY)</div><div style='font-size:14px;font-weight:900;color:{daily_color}'>${daily:+.2f}</div></div>
    </div>
    
    <div style='background:#000000;border-radius:10px;padding:6px;margin:6px 0;border:1px solid #0f8'><canvas id='equityChart' width='340' height='70' style='width:100%;height:70px;background:#000;border-radius:6px'></canvas></div>
    
    <div class='btn-row'><button class='btn btn-cron' onclick='location.reload()'>⚡ REFRESH<div style='font-size:9px'>SYNC STATE</div></button><button class='btn btn-close' onclick='callCloseAll()'>💰 CLOSE ALL<div style='font-size:9px'>{len(open_tr)} OPEN</div></button><button class='btn btn-reset' onclick='callReset()'>🔄 RESET $300<div style='font-size:9px'>WIPE DATA</div></button></div>
    
    <div id='openbox'>{trade_boxes_html}</div>
    
    <div style='background:#151515;border:1px solid #333;border-radius:10px;padding:8px;margin-top:8px'>
        <div style='font-size:10px;color:#0f8;font-weight:900;margin-bottom:4px;text-align:center'>📊 CLOSED TRADES & PNL BREAKDOWN</div>
        {closed_html}
    </div>
    
    <script>
    const EQUITY = {equity_js};const ADMIN_KEY="{ADMIN_KEY}";
    function drawEquity(){{const cv=document.getElementById('equityChart'); if(!cv||!EQUITY.length) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...EQUITY)*0.999, mx=Math.max(...EQUITY)*1.001, rg=mx-mn||1; function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}} ctx.strokeStyle='#0f8'; ctx.lineWidth=2; ctx.beginPath(); EQUITY.forEach((p,i)=>{{const x=i/(EQUITY.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();}}
    
    setInterval(()=>{{
        document.querySelectorAll('[data-ts]').forEach(el=>{{
            let ts = parseInt(el.getAttribute('data-ts'));
            let diff = Math.floor(Date.now()/1000) - ts;
            if(diff<0) diff=0;
            let m = Math.floor(diff/60);
            let s = diff%60;
            el.innerText = m+'m '+s+'s';
        }});
    }}, 1000);
    
    async function callReset(){{
        if(!confirm('Reset account balance to $300 and clear cloud storage?')) return;
        try {{
            let res = await fetch('/api/reset?key='+ADMIN_KEY);
            let j = await res.json();
            if(j.ok) {{ location.reload(); }} else {{ alert('Reset failed'); }}
        }} catch(e) {{ location.reload(); }}
    }}
    
    async function callCloseAll(){{
        if(!confirm('Close all open positions immediately?')) return;
        try {{
            let res = await fetch('/api/closeall?key='+ADMIN_KEY);
            let j = await res.json();
            if(j.ok) {{ location.reload(); }} else {{ alert('Close all failed'); }}
        }} catch(e) {{ location.reload(); }}
    }}
    
    async function closeOne(s){{
        if(!confirm('Close '+s+'?')) return;
        try {{
            let res = await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY);
            let j = await res.json();
            if(j.ok) {{ location.reload(); }}
        }} catch(e) {{ location.reload(); }}
    }}
    
    function initChartFuture(sym,entry,tp,sl,side,ts,age,futurePred,futureChange,conf,closes,posStr,feeStr){{
        let cv=document.getElementById('chart-'+sym); if(!cv) return; let ctx=cv.getContext('2d'); 
        let baseCloses = (closes && closes.length > 0) ? [...closes] : Array(15).fill(entry);
        let lastClose = baseCloses[baseCloses.length-1] || entry;
        let scaleFactor = entry / (lastClose || entry);
        let normalizedCloses = baseCloses.map(p => p * scaleFactor);
        let live=[entry];
        let pos = parseFloat(posStr)||266;
        let fee = parseFloat(feeStr)||0.17;
        
        async function fetchP(){{
            try{{
                let r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now());
                let j=await r.json();
                if(j.price>0){{ 
                    live.push(j.price); 
                    if(live.length>50) live.shift(); 
                    draw(); 
                    let pct = side=='LONG' ? (j.price-entry)/entry*100 : (entry-j.price)/entry*100;
                    let pctNet = pct - fee;
                    let netVal = pos * pctNet / 100;
                    
                    let pnlEl = document.getElementById('live-pnl-'+sym);
                    let priceEl = document.getElementById('live-price-'+sym);
                    if(pnlEl) {{
                        pnlEl.innerText = (netVal>=0?'+$':'-$')+Math.abs(netVal).toFixed(2);
                        pnlEl.style.color = netVal>=0 ? '#0f8' : '#f44';
                    }}
                    if(priceEl) {{
                        priceEl.innerText = '$'+j.price.toFixed(2);
                        priceEl.style.color = pct>=0 ? '#0f8' : '#f44';
                    }}
                    
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
        draw(); fetchP(); setInterval(fetchP, 6000);
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
    if p.startswith("/api/reset") or p == "/reset":
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY)
        return Response(json.dumps({"ok":True}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/closeall") or p == "/closeall":
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
