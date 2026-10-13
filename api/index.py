""" VENUS v865 - BULLETPROOF SHARK VOLUME SCANNER & PREDICTOR """
from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse, math

app = Flask(__name__)

MEM_STATE={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"peak":300.0,"equity":[300.0],"last_cron":"mem v865 BULLETPROOF SHARK VOLUME"}

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
SCAN_BATCH=15
TP_PCT=1.20
SL_PCT=0.60
TRAIL_PCT=0.8

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

def fetch_top_volume_coins():
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/ticker/24hr"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                pairs=[]
                for item in data:
                    sym=item.get("symbol","")
                    if sym.endswith("USDT") and not any(x in sym for x in ["UP","DOWN","BULL","BEAR"]):
                        base=sym[:-4]
                        vol=float(item.get("quoteVolume",0))
                        pairs.append((base, vol))
                pairs=sorted(pairs, key=lambda x: x[1], reverse=True)
                if len(pairs)>10:
                    return [p[0] for p in pairs[:60]]
        except: continue
    return ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","SUI","NEAR","PEPE","RENDER","INJ","OP","ARB","APT","JUP","PENDLE","CYBER"]

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

def fetch_klines(base, interval="1m", limit=50):
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/klines?symbol={base}USDT&interval={interval}&limit={limit}"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                closes=[float(k[4]) for k in data if len(k)>4]
                highs=[float(k[2]) for k in data if len(k)>2]
                lows=[float(k[3]) for k in data if len(k)>3]
                vols=[float(k[5]) for k in data if len(k)>5]
                if len(closes)>=10: return closes, highs, lows, vols
        except: continue
    return [], [], [], []

def future_prediction_engine_v865(closes, highs, lows, vols):
    if len(closes)<20:
        closes = closes if closes else [100.0]*20
        return {"future_side":"LONG","moving_score":5.0,"future_pred":[closes[-1]]*10,"confidence":80,"future_change":0.8,"slope_pct":0.05,"closes":closes}
    last=closes[-1]; n=20; x=list(range(n)); y=closes[-n:]
    x_mean=sum(x)/n; y_mean=sum(y)/n
    num=sum((x[i]-x_mean)*(y[i]-y_mean) for i in range(n))
    den=sum((x[i]-x_mean)**2 for i in range(n))
    slope=num/den if den!=0 else 0; slope_pct=slope/y_mean*100 if y_mean!=0 else 0
    
    future_change=slope_pct * 20
    if future_change > 1.5: future_change = 1.5
    if future_change < -1.5: future_change = -1.5
    if abs(future_change) < 0.6:
        future_change = 0.8 if slope_pct >= 0 else -0.8
        
    future_side="LONG" if slope_pct >= 0 else "SHORT"
    confidence=80 + min(15, abs(slope_pct)*300)
    
    future_pred=[]
    for i in range(1,11):
        prog=i/10.0
        pred_price=last * (1 + (future_change/100)*prog)
        future_pred.append(pred_price)
        
    moving_score = abs(slope_pct)*400 + abs(future_change)*2.5
    reason_str=f"{future_side} SHARK VOLUME FUTURE {future_change:+.2f}% slope {slope_pct:.4f}% | conf {confidence:.0f}%"
    return {"future_side":future_side,"moving_score":moving_score,"future_change":future_change,"future_pred":future_pred,"closes":closes,"reason":reason_str,"confidence":confidence,"slope_pct":slope_pct}

def load_state():
    s=kv_get(STATE_KEY)
    if not s or not isinstance(s, dict) or "cap" not in s: s=MEM_STATE
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("peak",300); s.setdefault("equity",[300])
    if len(s.get("open",[]))>MAXP: s["open"]=sorted(s["open"], key=lambda x: x.get("ts",0), reverse=True)[:MAXP]
    for t in s.get("open",[]): t["tp"]=TP_PCT; t["sl"]=SL_PCT
    return s

def recalc(state):
    all_closed=state.get("closed",[]); state["wins"]=sum(1 for c in all_closed if c.get("net",0)>0); state["loss"]=sum(1 for c in all_closed if c.get("net",0)<0); state["total"]=len(all_closed)
    state["daily"]=sum([c.get("net",0) for c in all_closed[-20:]]) if all_closed else 0.0
    return state

def auto_close_trades(state):
    cap=state.get("cap",300.0); new_open=[]; closed_added=False
    for tr in state.get("open",[]):
        sym=tr["symbol"]; entry=tr["entry"]; side=tr["side"]; pos=tr["pos"]
        live_price,_=fetch_live_price_fast(sym)
        if not live_price or live_price==0: live_price=tr.get("price",entry)
        pct=(live_price-entry)/entry*100 if side=="LONG" else (entry-live_price)/entry*100
        should_close=False; close_reason=""
        if pct>=TP_PCT: should_close=True; close_reason=f"AUTO TP {pct:.2f}%"
        elif pct<=-SL_PCT: should_close=True; close_reason=f"AUTO SL {pct:.2f}%"
        if should_close:
            pct_net=pct-TOTAL_FEE; net=pos*pct_net/100; cap+=net
            state["closed"].insert(0,{"symbol":sym,"side":side,"net":net,"reason":f"{close_reason} LIVE ${live_price:.4f}","pct_gross":pct,"pct_net":pct_net,"age":tr.get("age",0),"pos":pos,"entry":entry,"exit":live_price})
            closed_added=True
        else:
            tr["peak_gross"]=max(tr.get("peak_gross",0), pct)
            tr["pct_gross"]=pct; tr["pct"]=pct-TOTAL_FEE; tr["net"]=pos*(pct-TOTAL_FEE)/100; tr["price"]=live_price; tr["age"]=int(time.time())-tr.get("ts",int(time.time()))
            new_open.append(tr)
    if closed_added:
        state["open"]=new_open; state["cap"]=cap; state["peak"]=max(state.get("peak",cap), cap)
        state["equity"]=state.get("equity",[300])[-100:] + [cap]; state=recalc(state); kv_set(STATE_KEY, state)
    return state

def render(state):
    state=auto_close_trades(state); state=recalc(state)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0); offset=state.get("scan_offset",0); daily=state.get("daily",0.0)
    peak=state.get("peak",cap); equity=state.get("equity",[300,cap])
    invested=sum([t.get("pos",0) for t in open_tr]); dd=(peak-cap)/peak*100 if peak>0 else 0
    daily_color = "#0f8" if daily>=0 else "#f44"
    
    trade_boxes_html=""; chart_js_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",100); entry=tr.get("entry",0); tp=tr.get("tp",TP_PCT); sl=tr.get("sl",SL_PCT)
        tp_price=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100); sl_price=entry*(1-sl/100) if side=="LONG" else entry*(1+sl/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"; net_target=pos*(tp-TOTAL_FEE)/100
        analysis=tr.get("analysis","v865")[:150]; future_change=tr.get("future_change",0); confidence=tr.get("confidence",0)
        ts=tr.get("ts",int(time.time())); peak_gross=tr.get("peak_gross",0); future_pred=tr.get("future_pred",[])
        trade_boxes_html+=f"""<div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'><div style='display:flex;justify-content:space-between'><div><b style='color:{col};font-size:14px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f}</b><div style='font-size:10px;color:#0f8'>🔮 {analysis}</div><div style='font-size:10px;color:#aaa'>ENTRY ${entry:.6f} TP ${tp_price:.6f} (${net_target:.2f}) SL ${sl_price:.6f}</div></div><button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 10px'>✕</button></div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin:8px 0;text-align:center'><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>LIVE</div><div id='live-price-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('price',0):.5f}</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>PNL</div><div id='live-pnl-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f}</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>AGE</div><div id='live-age-{sym}' style='font-size:13px;font-weight:900'>{int(tr.get('age',0)//60)}m {int(tr.get('age',0)%60)}s</div></div></div><div style='background:#000;border-radius:12px;padding:6px;border:1px solid #222'><canvas id='chart-{sym}' width='340' height='200' style='width:100%;height:200px;background:#000;border-radius:8px'></canvas></div></div>"""
        chart_js_init+=f"initChartFuture('{sym}',{entry},{tp_price},{sl_price},'{side}',{ts},{int(tr.get('age',0))},{json.dumps(future_pred)},{future_change},{confidence});\n"
        
    if not open_tr:
        trade_boxes_html="<div class='it' style='text-align:center;color:#0f8;padding:16px;border:2px solid #0f8'><b>✅ SHARK VOLUME SCANNER READY</b><br>No active positions. Tap CRON SCAN to scan highest volume institutional coins.</div>"
        
    equity_js=json.dumps(equity[-80:])
    
    html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
    html += "body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}"
    html += ".h{background:linear-gradient(90deg,#0f8,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}"
    html += ".btn-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}"
    html += ".btn{padding:16px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px;cursor:pointer}"
    html += ".btn-cron{background:linear-gradient(90deg,#0f8,#00d4ff);color:#000}.btn-reset{background:#f44;color:#fff}.btn-close{background:#fc0;color:#000}"
    html += ".badge{padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900}.long{background:#0f8;color:#000}.short{background:#f44;color:#fff}"
    html += ".overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.95);z-index:9999;display:none;flex-direction:column;padding:10px;overflow-y:auto}.overlay.show{display:flex}"
    html += ".coin-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}@media(max-width:600px){.coin-grid{grid-template-columns:1fr}}"
    html += "</style></head><body>"
    
    html += f"""
    <div id='analyzeOverlay' class='overlay'><div style='background:#111;border:2px solid #0f8;border-radius:16px;padding:12px'><div style='color:#0f8;font-weight:900;font-size:14px;text-align:center'>🦈 SHARK VOLUME SCANNER & PREDICTOR</div><div style='color:#0f8;font-size:11px;text-align:center;margin:6px 0' id='analyzeStatus'>Scanning highest volume institutional coins...</div><div style='background:#000000;border-radius:12px;padding:8px;margin:8px 0'><div style='font-size:10px;color:#888'>STEP 1: SHARK FOOTPRINT VOLUME SCAN</div><div id='scanLog' style='color:#0f8;font-size:9px;white-space:pre-wrap;max-height:80px;overflow-y:auto;background:#0a0a0a;padding:6px;border-radius:8px;margin:4px 0'></div><div class='coin-grid'>
    <div style='background:#111;border-radius:10px;padding:6px'><div id='deepCoin0' style='color:#0f8;font-weight:900;font-size:11px'>Future 1: -</div><canvas id='deepChart0' width='200' height='160' style='width:100%;height:160px;background:#000;border-radius:8px'></canvas><div id='deepText0' style='color:#0f8;font-size:8px'>-</div></div>
    <div style='background:#111;border-radius:10px;padding:6px'><div id='deepCoin1' style='color:#0f8;font-weight:900;font-size:11px'>Future 2: -</div><canvas id='deepChart1' width='200' height='160' style='width:100%;height:160px;background:#000;border-radius:8px'></canvas><div id='deepText1' style='color:#0f8;font-size:8px'>-</div></div>
    <div style='background:#111;border-radius:10px;padding:6px'><div id='deepCoin2' style='color:#0f8;font-weight:900;font-size:11px'>Future 3: -</div><canvas id='deepChart2' width='200' height='160' style='width:100%;height:160px;background:#000;border-radius:8px'></canvas><div id='deepText2' style='color:#0f8;font-size:8px'>-</div></div>
    </div></div>
    
    <div style='background:#000000;border-radius:12px;padding:8px;margin:8px 0;border:1px solid #333'><div style='font-size:10px;color:#888'>STEP 2: 60S LIVE TREND CONFIRMATION</div><div id='liveMonitorText' style='color:#ffcc00;font-size:11px;margin:4px 0'>Monitoring 60s trend...</div><div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;text-align:center'><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>TIME LEFT</div><div id='monitorTimeLeft' style='font-size:18px;font-weight:900;color:#f44'>60s</div></div><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>TOTAL LIVE</div><div id='monitorTotalMove' style='font-size:12px;font-weight:900;color:#0f8'>+0.00%</div></div></div>
    <div class='coin-grid' style='margin-top:8px'>
    <div style='background:#111;border-radius:10px;padding:6px'><div style='display:flex;justify-content:space-between'><div id='liveCoin0' style='color:#0f8;font-weight:900;font-size:10px'>-</div><div id='liveChange0' style='color:#0f8;font-size:10px'>+0.00%</div></div><canvas id='liveMonitorChart0' width='200' height='120' style='width:100%;height:120px;background:#000;border-radius:8px;margin-top:4px'></canvas></div>
    <div style='background:#111;border-radius:10px;padding:6px'><div style='display:flex;justify-content:space-between'><div id='liveCoin1' style='color:#0f8;font-weight:900;font-size:10px'>-</div><div id='liveChange1' style='color:#0f8;font-size:10px'>+0.00%</div></div><canvas id='liveMonitorChart1' width='200' height='120' style='width:100%;height:120px;background:#000;border-radius:8px;margin-top:4px'></canvas></div>
    <div style='background:#111;border-radius:10px;padding:6px'><div style='display:flex;justify-content:space-between'><div id='liveCoin2' style='color:#0f8;font-weight:900;font-size:10px'>-</div><div id='liveChange2' style='color:#0f8;font-size:10px'>+0.00%</div></div><canvas id='liveMonitorChart2' width='200' height='120' style='width:100%;height:120px;background:#000;border-radius:8px;margin-top:4px'></canvas></div>
    </div></div>
    
    <div style='background:#000;padding:10px;border-radius:10px;text-align:center'><div id='autoStatus' style='color:#0f8;font-size:12px;font-weight:900'>Ready</div><div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px'><button onclick='autoConfirm3Trades()' id='forceOpenBtn' style='background:linear-gradient(90deg,#0f8,#00d4ff);color:#000;padding:12px;border-radius:10px;border:0;font-weight:900'>✅ FORCE OPEN TRADES</button><button onclick='closeOverlay()' style='background:#333;color:#fff;padding:12px;border-radius:10px;border:0;font-weight:900'>❌ CLOSE</button></div></div></div></div>
    
    <div class='h'>🦈 SHARK VOLUME SCANNER - SCAN #{scan} OFFSET {offset+1} - ${cap:.2f} PEAK ${peak:.2f} DAILY <span style='color:{daily_color}'>${daily:.2f}</span></div>
    
    <div style='background:#000000;border-radius:12px;padding:8px;margin:6px 0;border:1px solid #0f8'><canvas id='equityChart' width='340' height='80' style='width:100%;height:80px;background:#000;border-radius:8px'></canvas></div>
    
    <div class='btn-row'><button class='btn btn-cron' onclick='startMovingScan()'>✅ CRON SCAN & PREDICT<div style='font-size:10px'>SCAN HIGHEST VOLUME COINS</div></button><button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN</div></button><button class='btn btn-reset' onclick='callReset()'>🔄RESET $300<div style='font-size:10px'>CLEAN MEM</div></button></div>
    
    <div id='openbox'>{trade_boxes_html}</div>
    
    <script>
    const EQUITY = {equity_js};const ADMIN_KEY="{ADMIN_KEY}";let currentAnalysis=null;let timeLeft=60;
    function drawEquity(){{const cv=document.getElementById('equityChart'); if(!cv||!EQUITY.length) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...EQUITY)*0.999, mx=Math.max(...EQUITY)*1.001, rg=mx-mn||1; function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}} ctx.strokeStyle='#0f8'; ctx.lineWidth=2; ctx.beginPath(); EQUITY.forEach((p,i)=>{{const x=i/(EQUITY.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();}}
    function logScan(msg){{const el=document.getElementById('scanLog'); if(el){{ el.innerText+='\\n'+msg; el.scrollTop=el.scrollHeight; }} }}
    
    async function startMovingScan(){{
        const overlay=document.getElementById('analyzeOverlay'); overlay.classList.add('show');
        document.getElementById('scanLog').innerText=''; currentAnalysis={{coins:[]}};
        logScan('Scanning top volume coins (Shark Footprint)...');
        try {{
            const r=await fetch('/api/scan_most_moving?key='+ADMIN_KEY+'&t='+Date.now());
            const j=await r.json();
            if(!j.ok) {{ logScan('Error: '+j.error); return; }}
            const top3=j.top3||[];
            currentAnalysis.coins=top3.map(m=>({{symbol:m.symbol, price:m.price, startPrice:m.price, livePrice:m.price, livePrices:[m.price], finalSide:m.future_side, finalReason:m.reason, moving_score:m.moving_score, future_change:m.future_change, confidence:m.confidence, future_pred:m.future_pred||[], closes:m.closes||[]}}));
            for(let i=0;i<top3.length;i++){{
                const m=top3[i];
                document.getElementById('deepCoin'+i).innerText=m.symbol+' - '+m.future_side+' '+(m.future_change||0).toFixed(2)+'%';
                document.getElementById('deepText'+i).innerText='Slope '+(m.slope_pct||0).toFixed(4)+'%';
                drawDeepChart(i, m.closes||[], m.future_pred||[], m.future_side);
            }}
            document.getElementById('analyzeStatus').innerText='Scan complete. Starting 60s confirmation...';
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
        timeLeft=60; document.getElementById('monitorTimeLeft').innerText='60s';
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
        document.getElementById('autoStatus').innerText='Opening trades safely...';
        for(let i=0;i<currentAnalysis.coins.length;i++){{
            let c=currentAnalysis.coins[i];
            try{{
                let payload={{symbol:c.symbol, side:c.finalSide, reason:c.finalReason, livePrice:c.livePrice||c.startPrice, moving_score:c.moving_score, future_change:c.future_change, confidence:c.confidence, future_pred:c.future_pred}};
                await fetch('/api/open_analyzed?key='+ADMIN_KEY+'&t='+Date.now(), {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)}});
            }}catch(e){{}}
            await new Promise(r=>setTimeout(r,300));
        }}
        closeOverlay(); location.reload();
    }}
    
    function closeOverlay(){{ document.getElementById('analyzeOverlay').classList.remove('show'); }}
    async function callReset(){{if(!confirm('RESET $300?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
    async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
    async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}
    
    function initChartFuture(sym,entry,tp,sl,side,ts,age,futurePred,futureChange,conf){{
        let cv=document.getElementById('chart-'+sym); if(!cv) return; let ctx=cv.getContext('2d'); let prices=[]; let live=[];
        async function fetchP(){{
            try{{
                let r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now());
                let j=await r.json();
                if(j.price>0){{ live.push(j.price); if(live.length>60)live.shift(); prices=[...live]; draw(); }}
            }}catch(e){{}}
        }}
        function draw(){{
            let w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h);
            if(prices.length<2) prices=Array(20).fill(entry);
            let all=[...prices, ...(futurePred || [])]; let mn=Math.min(...all)*0.998, mx=Math.max(...all)*1.002;
            function yF(p){{return h*0.85-((p-mn)/(mx-mn||1))*h*0.7;}}
            let ey=yF(entry); ctx.strokeStyle='#fc0'; ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(0,ey); ctx.lineTo(w,ey); ctx.stroke();
            let tpy=yF(tp); ctx.strokeStyle='#0f8'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,tpy); ctx.lineTo(w,tpy); ctx.stroke(); ctx.setLineDash([]);
            let sly=yF(sl); ctx.strokeStyle='#f44'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,sly); ctx.lineTo(w,sly); ctx.stroke(); ctx.setLineDash([]);
            ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=2; ctx.beginPath();
            prices.forEach((p,i)=>{{let x=i/(prices.length+(futurePred||[]).length-1)*w*0.7, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();
            if(futurePred && futurePred.length>0){{
                ctx.strokeStyle='#fc0'; ctx.setLineDash([4,4]); ctx.beginPath();
                let lx=(prices.length-1)/(prices.length+futurePred.length-1)*w*0.7, ly=yF(prices[prices.length-1]);
                ctx.moveTo(lx,ly);
                futurePred.forEach((fp,i)=>{{let x=(prices.length+i)/(prices.length+futurePred.length-1)*w*0.9; ctx.lineTo(x, yF(fp));}});
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
            state=load_state(); offset=state.get("scan_offset",0)
            all_top_coins = fetch_top_volume_coins()
            batch=all_top_coins[offset:offset+SCAN_BATCH] if offset+SCAN_BATCH <= len(all_top_coins) else all_top_coins[offset:]+all_top_coins[: (offset+SCAN_BATCH)-len(all_top_coins) ]
            open_syms=[t["symbol"] for t in state.get("open",[])]; movers=[]
            for base in batch:
                if base in open_syms: continue
                closes, highs, lows, vols = fetch_klines(base, "1m", 50)
                if not closes: closes, highs, lows, vols = fetch_klines(base, "5m", 50)
                if not closes: continue
                price, src = fetch_live_price_fast(base)
                if not price or price==0: price=closes[-1] if closes else 100
                analysis=future_prediction_engine_v865(closes, highs, lows, vols)
                analysis["symbol"]=base; analysis["price"]=price; analysis["src"]=src; analysis["closes"]=closes
                movers.append(analysis)
            movers_sorted=sorted(movers, key=lambda x: (x["moving_score"], x["confidence"]), reverse=True)
            
            # GUARANTEE 3 COINS (Fallback padding if fewer than 3 are returned)
            top3=movers_sorted[:3]
            while len(top3) < 3:
                fallback_sym = "BTC" if len(top3)==0 else ("ETH" if len(top3)==1 else "SOL")
                c_price, _ = fetch_live_price_fast(fallback_sym)
                closes = [c_price*0.99, c_price*1.01]*15
                dummy = future_prediction_engine_v865(closes, closes, closes, [100]*30)
                dummy["symbol"] = fallback_sym; dummy["price"] = c_price or 100; dummy["closes"] = closes
                top3.append(dummy)
                
            state["scan_offset"]=(offset+SCAN_BATCH)%len(all_top_coins)
            state["scan"]=state.get("scan",0)+1
            kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":True,"movers":movers_sorted,"top3":top3,"offset":state["scan_offset"]}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/open_analyzed"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            data=request.get_json(force=True, silent=True) or {}
            sym=data.get("symbol","").upper(); side=data.get("side","LONG"); reason=data.get("reason","v865")
            price=data.get("livePrice", 100); state=load_state(); cap=state.get("cap",300.0)
            if len(state.get("open",[]))>=MAXP: return Response(json.dumps({"ok":True,"msg":"max positions"}))
            pos_size=cap*POS_PCT/100.0
            tr={"symbol":sym,"side":side,"entry":price,"price":price,"pos":pos_size,"ts":int(time.time()),"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"tp":TP_PCT,"sl":SL_PCT,"reason":reason,"analysis":reason[:200],"future_pred":data.get("future_pred",[]),"future_change":data.get("future_change",0),"confidence":data.get("confidence",0)}
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
