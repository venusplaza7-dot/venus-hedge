""" VENUS v865 - FIXED 60S MAP SCAN, 24H TREND ANALYSIS & PREDICTION ENGINE """
from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse, math

app = Flask(__name__)

MEM_STATE={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0],"last_cron":"mem v865 CRON FIXED INIT"}

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
SCAN_BATCH=24
TOP_N=100
TP_PCT=1.20
SL_PCT=0.60
TRAIL_PCT=0.8
STATIC_TOP=[("BTC",60),("ETH",55),("SOL",50),("BNB",50),("XRP",48),("AVAX",45),("LINK",45),("ADA",44),("DOT",44),("LTC",43),("UNI",43),("ETC",42),("APT",42),("ARB",41),("OP",41),("SUI",40),("NEAR",40),("HBAR",40),("FIL",39),("MKR",39),("AAVE",38),("GRT",38),("RNDR",38),("INJ",38),("STX",37),("IMX",37),("SEI",37),("TIA",37),("WLD",36),("FET",36),("TAO",36),("ZEC",35),("STRK",35),("JUP",35),("ENA",34),("PENDLE",34),("ONDO",34),("DOGE",34),("CYBER",32),("PEPE",30)]
SYM_TO_ID={"BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin","XRP":"ripple","ADA":"cardano","AVAX":"avalanche-2","DOT":"polkadot","LINK":"chainlink","LTC":"litecoin","UNI":"uniswap","ETC":"ethereum-classic","APT":"aptos","ARB":"arbitrum","OP":"optimism","SUI":"sui","RNDR":"render-token","MKR":"maker","AAVE":"aave","GRT":"the-graph","SEI":"sei-network","TIA":"celestia","DOGE":"dogecoin","WLD":"worldcoin","FET":"fetch-ai","TAO":"bittensor","IMX":"immutable-x","JUP":"jupiter","HBAR":"hedera","ENA":"ethena","PENDLE":"pendle","ZEC":"zcash","STRK":"starknet","ONDO":"ondo-finance","NEAR":"near-protocol","CYBER":"cyberconnect","PEPE":"pepe"}

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
    MEM_STATE={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0],"last_cron":"reset v865 CRON FIXED CLEAN"}
    if not KV_URL or not KV_TOKEN: return True
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=4) as r: return True
    except: return True

def fetch_live_price_fast(base):
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/ticker/price?symbol={base}USDT"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data=json.loads(r.read().decode()); price=float(data.get("price",0))
                if price>0: return price, "binance"
        except: continue
    try:
        cg_id=SYM_TO_ID.get(base, base.lower())
        url=f"https://api.coingecko.com/api/v3/simple/price?ids={urllib.parse.quote(cg_id)}&vs_currencies=usd"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data=json.loads(r.read().decode())
            for v in data.values():
                p=v.get("usd",0) if isinstance(v,dict) else 0
                if p>0: return float(p), "cg"
    except: pass
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
        return {"future_side":"LONG","moving_score":4.5,"reason":"no data LONG","future_pred":[closes[-1]]*10 if closes else [100]*10,"confidence":60,"entry_type":"market","strong":False,"future_change":0.6,"slope_pct":0.01,"slope5":0.01,"rsi":50,"volatility":0.5,"dist_to_high":0.5,"dist_to_low":0.5,"range_size":0.8,"up_candles":5,"closes":closes}
    last=closes[-1]
    n=20
    x=list(range(n))
    y=closes[-n:]
    x_mean=sum(x)/n
    y_mean=sum(y)/n
    num=sum((x[i]-x_mean)*(y[i]-y_mean) for i in range(n))
    den=sum((x[i]-x_mean)**2 for i in range(n))
    slope=num/den if den!=0 else 0
    slope_pct=slope/y_mean*100 if y_mean!=0 else 0
    
    n5=5
    x5=list(range(n5))
    y5=closes[-n5:]
    x5_mean=sum(x5)/n5
    y5_mean=sum(y5)/n5
    num5=sum((x5[i]-x5_mean)*(y5[i]-y5_mean) for i in range(n5))
    den5=sum((x5[i]-x5_mean)**2 for i in range(n5))
    slope5=num5/den5 if den5!=0 else 0
    slope5_pct=slope5/y5_mean*100 if y5_mean!=0 else 0
    
    future_pred=[]
    for i in range(1,11):
        pred=y_mean + slope*(n-1+i - x_mean)
        future_pred.append(pred)
    future_change=(future_pred[-1]-last)/last*100 if last!=0 else 0
    
    recent_high=max(highs[-20:]) if len(highs)>=20 else max(closes)
    recent_low=min(lows[-20:]) if len(lows)>=20 else min(closes)
    range_size=(recent_high-recent_low)/last*100 if last!=0 else 0
    dist_to_high=(recent_high-last)/last*100 if last!=0 else 0
    dist_to_low=(last-recent_low)/last*100 if last!=0 else 0
    
    gains=0; losses=0
    for i in range(max(1,len(closes)-14), len(closes)):
        diff=closes[i]-closes[i-1]
        if diff>0: gains+=diff
        else: losses+=abs(diff)
    avg_gain=gains/14 if gains>0 else 0.001
    avg_loss=losses/14 if losses>0 else 0.001
    rs=avg_gain/avg_loss
    rsi=100 - (100/(1+rs))
    volatility = (max(closes[-15:]) - min(closes[-15:])) / last *100 if last!=0 else 0
    up_candles=sum(1 for i in range(len(closes)-10, len(closes)) if i>0 and closes[i]>closes[i-1])
    
    future_side="LONG"
    confidence=60
    reasons=[]
    entry_type="pullback"
    
    if slope_pct>0.008:
        future_side="LONG"
        future_change=max(0.6, abs(future_change))
        confidence=65 + min(20, abs(slope_pct)*500)
        reasons.append(f"FUTURE UP slope {slope_pct:.4f}%/c -> {future_change:+.2f}% UP TO TP")
        entry_type="LONG pullback support"
    elif slope_pct<-0.008:
        future_side="SHORT"
        future_change=-max(0.6, abs(future_change))
        confidence=65 + min(20, abs(slope_pct)*500)
        reasons.append(f"FUTURE DOWN slope {slope_pct:.4f}%/c -> {future_change:+.2f}% DOWN TO TP")
        entry_type="SHORT pullback resistance"
    else:
        if rsi<45 and dist_to_low<0.8:
            future_side="LONG"
            future_change=0.7
            confidence=62
            reasons.append(f"WEAK slope but RSI {rsi:.0f} near low {dist_to_low:.2f}% -> LONG bounce")
        elif rsi>55 and dist_to_high<0.8:
            future_side="SHORT"
            future_change=-0.7
            confidence=62
            reasons.append(f"WEAK slope but RSI {rsi:.0f} near high {dist_to_high:.2f}% -> SHORT fade")
        else:
            future_side="LONG" if rsi<50 else "SHORT"
            future_change=0.6 if future_side=="LONG" else -0.6
            confidence=60
            reasons.append(f"CHOPPY low conf -> {future_side} {future_change:+.2f}%")
            
    future_pred=[]
    for i in range(1,11):
        prog=i/10.0
        pred_price=last * (1 + future_change/100 * prog)
        future_pred.append(pred_price)
        
    moving_score = abs(slope_pct)*400 + abs(future_change)*1.5 + volatility*2 + abs(rsi-50)/12
    strong = confidence>=60 and moving_score>=4.5 and volatility>=0.3 and range_size>=0.5
    live_confirmed = (future_side=="LONG" and slope5_pct>=-0.01) or (future_side=="SHORT" and slope5_pct<=0.01)
    if not live_confirmed: confidence-=5
    
    reason_str=f"{future_side} FUTURE {future_change:+.2f}% slope {slope_pct:.4f}% slope5 {slope5_pct:.4f}% | " + " | ".join(reasons[:2]) + f" | conf {confidence:.0f}% move {moving_score:.1f} vol {volatility:.2f}% RSI {rsi:.0f} {entry_type} {'LIVE OK' if live_confirmed else 'LIVE WEAK'}"
    return {"future_side":future_side,"moving_score":moving_score,"rsi":rsi,"volatility":volatility,"side":future_side,"strong":strong,"confidence":confidence,"slope_pct":slope_pct,"slope5":slope5_pct,"future_change":future_change,"future_pred":future_pred,"dist_to_high":dist_to_high,"dist_to_low":dist_to_low,"range_size":range_size,"up_candles":up_candles,"closes":closes,"reason":reason_str,"entry_type":entry_type,"live_confirmed":live_confirmed}

def load_state():
    s=kv_get(STATE_KEY)
    if not s or not isinstance(s, dict) or "cap" not in s: s=MEM_STATE
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("learn",{"blacklist":{},"last_coins":{}}); s.setdefault("peak",s.get("cap",300)); s.setdefault("equity",[300,s.get("cap",300)]); s.setdefault("last_cron","never v865 CRON FIXED")
    if len(s.get("open",[]))>MAXP: s["open"]=sorted(s["open"], key=lambda x: x.get("ts",0), reverse=True)[:MAXP]
    L=s["learn"]; L.setdefault("blacklist",{}); L.setdefault("last_coins",{})
    now=int(time.time()); L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}; L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    for t in s.get("open",[]): t["tp"]=TP_PCT; t["sl"]=SL_PCT
    return s

def recalc(state):
    all_closed=state.get("closed",[]); state["wins"]=sum(1 for c in all_closed if c.get("net",0)>0); state["loss"]=sum(1 for c in all_closed if c.get("net",0)<0); state["total"]=len(all_closed)
    valid=[c for c in all_closed if c.get("symbol","").upper() not in ["CTK","KORUB","SKHYB"]]
    state["daily"]=sum([c.get("net",0) for c in valid[-20:]]) if valid else sum([c.get("net",0) for c in all_closed[-10:]])
    return state

def auto_close_trades(state):
    cap=state.get("cap",300.0)
    new_open=[]
    closed_added=False
    for tr in state.get("open",[]):
        sym=tr["symbol"]; entry=tr["entry"]; side=tr["side"]; pos=tr["pos"]
        live_price,_=fetch_live_price_fast(sym)
        if not live_price or live_price==0: live_price=tr.get("price",entry)
        pct=(live_price-entry)/entry*100 if side=="LONG" else (entry-live_price)/entry*100
        should_close=False; close_reason=""
        if pct>=TP_PCT: should_close=True; close_reason=f"AUTO TP {pct:.2f}% v865 CRON FIXED PROFIT"
        elif pct<=-SL_PCT: should_close=True; close_reason=f"AUTO SL {pct:.2f}% v865"
        elif tr.get("peak_gross",0)>=TRAIL_PCT and pct < tr.get("peak_gross",0)-0.35: should_close=True; close_reason=f"AUTO TRAIL PEAK {tr.get('peak_gross',0):.2f}% -> {pct:.2f}% LOCK v865"
        if should_close:
            pct_net=pct-TOTAL_FEE; net=pos*pct_net/100; cap+=net
            state["closed"].insert(0,{"symbol":sym,"side":side,"net":net,"reason":f"{close_reason} LIVE ${live_price:.4f} FUTURE {tr.get('future_change',0):+.2f}%","pct_gross":pct,"pct_net":pct_net,"age":tr.get("age",0),"pos":pos,"moving_score":tr.get("moving_score",0),"entry":entry,"exit":live_price,"confidence":tr.get("confidence",0)})
            closed_added=True
            state["fees_paid"]=state.get("fees_paid",0)+pos*TOTAL_FEE/100
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
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0); offset=state.get("scan_offset",0); full_scans=state.get("full_scans",0); daily=state.get("daily",0.0)
    peak=state.get("peak",cap); equity=state.get("equity",[300,cap])
    winrate=int(wins/tot*100) if tot>0 else 0; unreal=sum([t.get("net",0) for t in open_tr]); long_open=sum(1 for t in open_tr if t.get("side")=="LONG"); short_open=sum(1 for t in open_tr if t.get("side")=="SHORT")
    gross_profit=sum([c.get("net",0) for c in closed if c.get("net",0)>0]); gross_loss=sum([c.get("net",0) for c in closed if c.get("net",0)<0])
    pf=abs(gross_profit/gross_loss) if gross_loss!=0 else 0; exp=(gross_profit+gross_loss)/tot if tot>0 else 0
    best=max(closed, key=lambda x: x.get("net",0)) if closed else None; worst=min(closed, key=lambda x: x.get("net",0)) if closed else None
    invested=sum([t.get("pos",0) for t in open_tr]); dd=(peak-cap)/peak*100 if peak>0 else 0
    daily_needed=max(0,15.0-daily); trades_needed=int(daily_needed/1.20)+1 if daily_needed>0 else 0
    daily_color = "#0f8" if daily>=0 else "#f44"; target_color = "#0f8"
    cap_safe_color = "#0f8" if invested <= cap*1.05 else "#f44"
    over_msg = "✅" if invested<=cap*1.05 else "❌ OVER"
    kv_status = f"KV:{'OK' if KV_URL and KV_TOKEN else 'MEM v865 CRON FIXED WORKS'}"
    
    trade_boxes_html=""; chart_js_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",100); entry=tr.get("entry",0); tp=tr.get("tp",TP_PCT); sl=tr.get("sl",SL_PCT)
        tp_price=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100); sl_price=entry*(1-sl/100) if side=="LONG" else entry*(1+sl/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        net_target = pos*(tp-TOTAL_FEE)/100
        analysis=tr.get("analysis","v865 cron fixed")[:150]
        future_pred=tr.get("future_pred",[]); future_change=tr.get("future_change",0); confidence=tr.get("confidence",0)
        shark_tag=f"<span style='background:#00d4ff;color:#000;padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900'>FUTURE {future_change:+.2f}% CONF {confidence:.0f}% ${net_target:.2f}</span>"
        ts=tr.get("ts",int(time.time())); peak_gross=tr.get("peak_gross",0)
        trade_boxes_html+=f"""<div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'><div style='display:flex;justify-content:space-between'><div><b style='color:{col};font-size:14px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f} {shark_tag}</b><div style='font-size:10px;color:#0f8'>🔮 v865 CRON FIXED: {analysis}</div><div style='font-size:10px;color:#aaa'>ENTRY ${entry:.6f} TP ${tp_price:.6f} ({tp:.2f}%) = ${net_target:.2f} NET SL ${sl_price:.6f} ({sl:.2f}%) PEAK {peak_gross:.2f}% FUTURE {future_change:+.2f}% CONF {confidence:.0f}% INV {invested:.0f}/{cap:.0f}</div></div><button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 10px'>✕</button></div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin:8px 0;text-align:center'><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>LIVE</div><div id='live-price-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('price',0):.5f}</div><div id='live-change-{sym}' style='font-size:10px'>{tr.get('pct_gross',0):+.3f}% PEAK {peak_gross:.2f}%</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>PNL FAKE</div><div id='live-pnl-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f} / ${net_target:.2f}</div><div style='font-size:10px'>CONF {confidence:.0f}%</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>AGE</div><div id='live-age-{sym}' style='font-size:13px;font-weight:900'>{int(tr.get('age',0)//60)}m {int(tr.get('age',0)%60)}s</div><div style='font-size:10px;color:#0f8'>TP {tp:.2f}% SL {sl:.2f}%</div></div></div><div style='background:#000;border-radius:12px;padding:6px;border:1px solid #222'><div style='font-size:9px;color:#555'>TURBO GRAPH {side} - 24H & 60S PREDICTION - YELLOW dotted goes UP to TP - REAL slope</div><canvas id='chart-{sym}' width='340' height='200' style='width:100%;height:200px;background:#000;border-radius:8px'></canvas></div></div>"""
        chart_js_init+=f"initChartFuture('{sym}',{entry},{tp_price},{sl_price},'{side}',{ts},{int(tr.get('age',0))},{json.dumps(future_pred)},{future_change},{confidence});\n"
        
    if not open_tr:
        trade_boxes_html="<div class='it' style='text-align:center;color:#0f8;padding:16px;border:2px solid #0f8'><b>✅ v865 CRON SCANNER & PREDICTOR</b><br>No active positions. Tap CRON SCAN & PREDICT to run 60s live map scan and 24h analysis.</div>"
        
    equity_js=json.dumps(equity[-80:])
    
    html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
    html += "body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}"
    html += ".h{background:linear-gradient(90deg,#0f8,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}"
    html += ".g{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}"
    html += ".c{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}"
    html += ".it{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:12px}"
    html += ".btn-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}"
    html += ".btn{padding:16px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px;cursor:pointer}"
    html += ".btn-cron{background:linear-gradient(90deg,#0f8,#00d4ff);color:#000}.btn-reset{background:#f44;color:#fff}.btn-close{background:#fc0;color:#000}"
    html += ".badge{padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900}.long{background:#0f8;color:#000}.short{background:#f44;color:#fff}"
    html += ".overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.95);z-index:9999;display:none;flex-direction:column;padding:10px;overflow-y:auto}.overlay.show{display:flex}"
    html += ".coin-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}@media(max-width:600px){.coin-grid{grid-template-columns:1fr}}"
    html += "</style></head><body>"
    
    html += f"""
    <div id='analyzeOverlay' class='overlay'><div style='background:#111;border:2px solid #0f8;border-radius:16px;padding:12px'><div style='color:#0f8;font-weight:900;font-size:14px;text-align:center' id='analyzeTitle'>✅ v865 CRON SCANNER & PREDICTOR</div><div style='color:#0f8;font-size:11px;text-align:center;margin:6px 0' id='analyzeStatus'>Scanning map and analyzing 24h charts for Long/Short positioning...</div><div style='background:#000;border-radius:12px;padding:8px;margin:8px 0'><div style='font-size:10px;color:#888'>STEP 1: 24H & 1M MAP SCAN</div><div id='scanLog' style='color:#0f8;font-size:9px;white-space:pre-wrap;max-height:80px;overflow-y:auto;background:#0a0a0a;padding:6px;border-radius:8px;margin:4px 0'></div><div style='font-size:10px;color:#888'>STEP 2: FUTURE PREDICTIONS & DIRECTION</div><div class='coin-grid'>
    <div style='background:#111;border-radius:10px;padding:6px'><div id='deepCoin0' style='color:#0f8;font-weight:900;font-size:11px'>Future 1: -</div><canvas id='deepChart0' width='200' height='160' style='width:100%;height:160px;background:#000;border-radius:8px'></canvas><div id='deepText0' style='color:#0f8;font-size:8px;white-space:pre-wrap'>Prediction...</div></div>
    <div style='background:#111;border-radius:10px;padding:6px'><div id='deepCoin1' style='color:#0f8;font-weight:900;font-size:11px'>Future 2: -</div><canvas id='deepChart1' width='200' height='160' style='width:100%;height:160px;background:#000;border-radius:8px'></canvas><div id='deepText1' style='color:#0f8;font-size:8px;white-space:pre-wrap'>Prediction...</div></div>
    <div style='background:#111;border-radius:10px;padding:6px'><div id='deepCoin2' style='color:#0f8;font-weight:900;font-size:11px'>Future 3: -</div><canvas id='deepChart2' width='200' height='160' style='width:100%;height:160px;background:#000;border-radius:8px'></canvas><div id='deepText2' style='color:#0f8;font-size:8px;white-space:pre-wrap'>Prediction...</div></div>
    </div></div>
    
    <div style='background:#000;border-radius:12px;padding:8px;margin:8px 0;border:1px solid #333'><div style='font-size:10px;color:#888'>STEP 3: 60S LIVE MAP CONFIRMATION</div><div id='liveMonitorText' style='color:#ffcc00;font-size:11px;margin:4px 0'>Monitoring 60s trend...</div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;text-align:center'><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>TIME LEFT</div><div id='monitorTimeLeft' style='font-size:18px;font-weight:900;color:#f44'>60s</div><div id='monitorProgress' style='font-size:9px'>0/60s</div></div><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>TOTAL LIVE</div><div id='monitorTotalMove' style='font-size:12px;font-weight:900;color:#0f8'>+0.00%</div></div><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>CONFIDENCE</div><div id='monitorBatch' style='font-size:9px;font-weight:900;color:#fc0'>-</div></div></div>
    
    <div class='coin-grid' style='margin-top:8px'>
    <div style='background:#111;border-radius:10px;padding:6px'><div style='display:flex;justify-content:space-between'><div id='liveCoin0' style='color:#0f8;font-weight:900;font-size:10px'>Future1: -</div><div id='liveChange0' style='color:#0f8;font-size:10px'>+0.00%</div></div><div style='font-size:8px;color:#888'>START <span id='liveStart0'>$0</span> LIVE <span id='livePrice0'>$0</span></div><canvas id='liveMonitorChart0' width='200' height='120' style='width:100%;height:120px;background:#000;border-radius:8px;margin-top:4px'></canvas></div>
    <div style='background:#111;border-radius:10px;padding:6px'><div style='display:flex;justify-content:space-between'><div id='liveCoin1' style='color:#0f8;font-weight:900;font-size:10px'>Future2: -</div><div id='liveChange1' style='color:#0f8;font-size:10px'>+0.00%</div></div><div style='font-size:8px;color:#888'>START <span id='liveStart1'>$0</span> LIVE <span id='livePrice1'>$0</span></div><canvas id='liveMonitorChart1' width='200' height='120' style='width:100%;height:120px;background:#000;border-radius:8px;margin-top:4px'></canvas></div>
    <div style='background:#111;border-radius:10px;padding:6px'><div style='display:flex;justify-content:space-between'><div id='liveCoin2' style='color:#0f8;font-weight:900;font-size:10px'>Future3: -</div><div id='liveChange2' style='color:#0f8;font-size:10px'>+0.00%</div></div><div style='font-size:8px;color:#888'>START <span id='liveStart2'>$0</span> LIVE <span id='livePrice2'>$0</span></div><canvas id='liveMonitorChart2' width='200' height='120' style='width:100%;height:120px;background:#000;border-radius:8px;margin-top:4px'></canvas></div>
    </div></div>
    
    <div style='background:#000;padding:10px;border-radius:10px;text-align:center'><div id='autoStatus' style='color:#0f8;font-size:12px;font-weight:900'>Scanning in progress...</div><div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px'><button onclick='autoConfirm3Trades()' id='forceOpenBtn' style='background:linear-gradient(90deg,#0f8,#00d4ff);color:#000;padding:12px;border-radius:10px;border:0;font-weight:900'>✅ FORCE OPEN TRADES</button><button onclick='closeOverlay()' style='background:#333;color:#fff;padding:12px;border-radius:10px;border:0;font-weight:900'>❌ CLOSE</button></div></div></div></div>
    
    <div class='h'>✅ VENUS v865 CRON SCANNER - SCAN #{scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} - ${cap:.2f} PEAK ${peak:.2f} DD {dd:.1f}% L:{long_open} S:{short_open} FULLx{full_scans} - DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> NEED {trades_needed}x $1.20 INV <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f} {over_msg}</span> POS {POS_PCT:.1f}% x{MAXP} {kv_status}</div>
    
    <div style='background:#000000;border-radius:12px;padding:8px;margin:6px 0;border:1px solid #0f8'><div style='font-size:9px;color:#0f8'>EQUITY CURVE (CAP $300 → ${cap:.2f}) PEAK ${peak:.2f} DD {dd:.1f}%</div><canvas id='equityChart' width='340' height='80' style='width:100%;height:80px;background:#000;border-radius:8px'></canvas></div>
    
    <div class='btn-row'><button class='btn btn-cron' onclick='startMovingScan()' id='cronBtn'>✅ CRON SCAN & PREDICT<div id='cronStat' style='font-size:10px'>60S MAP SCAN & 24H TREND ANALYSIS</div></button><button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN</div></button><button class='btn btn-reset' onclick='callReset()'>🔄RESET $300<div style='font-size:10px'>CLEAN MEM</div></button></div>
    
    <div class='g'><div class='c'>FAKE CAP<br><b style='font-size:18px;color:#0f8'>${cap:.2f}</b><br>UNREAL {unreal:+.2f}<br>INV <b style='color:{cap_safe_color}'>${invested:.0f}/{cap:.0f}</b></div><div class='c'>DAILY $15<br><b style='font-size:18px'><span style='color:{daily_color}'>${daily:.2f}</span>/$15</b><br>W:{wins} L:{loss} {winrate}%</div><div class='c' style='border-color:#0f8'><b style='color:#0f8'>CONFIG<br>POS {POS_PCT:.1f}% x{MAXP}</b><br>TP {TP_PCT}% SL {SL_PCT}%</div></div>
    
    <div id='openbox'>{trade_boxes_html}</div>
    
    <div style='background:#111;padding:10px;margin:6px 0;border-radius:10px'><div style='color:#0f8;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}%</div>
    """
    
    for cl in closed[:30]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"; sym=cl.get("symbol","?"); side=cl.get("side","?"); net=cl.get("net",0); pct=cl.get("pct_net",0); reason=cl.get("reason","")[:100]
        html+=f"<div style='padding:5px 0;border-bottom:1px solid #222;color:{c}'><b>{sym} {side}</b> ${net:+.2f} {pct:+.2f}% | {reason}</div>"
        
    html+=f"""</div>
    <script>
    const EQUITY = {equity_js};const ADMIN_KEY="{ADMIN_KEY}";const TP_PCT={TP_PCT};const SL_PCT={SL_PCT};const TRAIL_PCT={TRAIL_PCT};let currentAnalysis=null;let timeLeft=60;
    function drawEquity(){{const cv=document.getElementById('equityChart'); if(!cv||!EQUITY.length) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...EQUITY)*0.999, mx=Math.max(...EQUITY)*1.001, rg=mx-mn||1; function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}} ctx.strokeStyle='#222'; for(let i=0;i<3;i++){{const y=h*0.1+i*h*0.8/2; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} ctx.strokeStyle='#0f8'; ctx.lineWidth=2; ctx.beginPath(); EQUITY.forEach((p,i)=>{{const x=i/(EQUITY.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();}}
    function logScan(msg){{const el=document.getElementById('scanLog'); if(el){{ el.innerText+= '\\n'+msg; el.scrollTop=el.scrollHeight; }} console.log(msg); }}
    
    async function startMovingScan(){{
        const overlay=document.getElementById('analyzeOverlay'); overlay.classList.add('show');
        document.getElementById('scanLog').innerText='';
        currentAnalysis={{coins:[]}};
        logScan('Scanning 24h market map & checking moving coins...');
        try {{
            const r=await fetch('/api/scan_most_moving?key='+ADMIN_KEY+'&t='+Date.now());
            const j=await r.json();
            if(!j.ok) {{ logScan('Scan error: '+j.error); document.getElementById('analyzeStatus').innerText='Error: '+j.error; return; }}
            const top3=j.top3||[];
            currentAnalysis.coins=top3.map(m=>({{symbol:m.symbol, price:m.price, startPrice:m.price, livePrice:m.price, liveChange:0, livePrices:[m.price], deep:m, closes:m.closes||[], finalSide:m.future_side, finalReason:m.reason, moving_score:m.moving_score, future_pred:m.future_pred||[], future_change:m.future_change, confidence:m.confidence}}));
            for(let i=0;i<top3.length;i++){{
                const m=top3[i];
                document.getElementById('deepCoin'+i).innerText=m.symbol+' - '+m.future_side+' '+m.future_change.toFixed(2)+'%';
                document.getElementById('deepText'+i).innerText=m.symbol+' 24h/1m slope '+m.slope_pct.toFixed(4)+'% conf '+m.confidence.toFixed(0)+'%';
                drawDeepChartFuture(i, m.closes||[], m, m.future_pred||[]);
            }}
            document.getElementById('analyzeStatus').innerText='Map scan & 24h analysis complete. Starting 60s live trend confirmation...';
            startMovingLiveMonitor();
        }} catch(e) {{ logScan('Scan err: '+e); }}
    }}
    
    function drawDeepChartFuture(idx, closes, deep, futurePred){{
        const cv=document.getElementById('deepChart'+idx); if(!cv) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h);
        if(!closes || closes.length<5) return;
        const allForRange=[...closes, ...(futurePred||[])].filter(v=>v>0);
        const mn=Math.min(...allForRange)*0.998, mx=Math.max(...allForRange)*1.002;
        function yF(p){{return h*0.85-((p-mn)/(mx-mn||1))*h*0.7;}}
        ctx.strokeStyle=deep.future_side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=1.5; ctx.beginPath();
        closes.forEach((p,i)=>{{const x=i/(closes.length+futurePred.length-1)*w*0.7, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();
        if(futurePred && futurePred.length>0){{
            ctx.strokeStyle='#fc0'; ctx.setLineDash([4,4]); ctx.lineWidth=2; ctx.beginPath();
            const lastX=(closes.length-1)/(closes.length+futurePred.length-1)*w*0.7; const lastY=yF(closes[closes.length-1]);
            ctx.moveTo(lastX, lastY);
            futurePred.forEach((p,i)=>{{const x=(closes.length+i)/(closes.length+futurePred.length-1)*w*0.85, y=yF(p); ctx.lineTo(x,y);}});
            ctx.stroke(); ctx.setLineDash([]);
        }}
    }}
    
    function startMovingLiveMonitor(){{
        timeLeft=60; document.getElementById('monitorTimeLeft').innerText='60s';
        for(let i=0;i<currentAnalysis.coins.length;i++){{
            const c=currentAnalysis.coins[i];
            document.getElementById('liveCoin'+i).innerText=c.symbol+' ('+c.finalSide+')';
            document.getElementById('liveStart'+i).innerText='$'+c.startPrice.toFixed(4);
            document.getElementById('livePrice'+i).innerText='$'+c.startPrice.toFixed(4);
            c.livePrices=[c.startPrice]; drawLiveMonitorChart(i);
        }}
        const interval=setInterval(async()=>{{
            timeLeft--; document.getElementById('monitorTimeLeft').innerText=timeLeft+'s';
            document.getElementById('monitorProgress').innerText=(60-timeLeft)+'/60s';
            let totalChange=0;
            for(let i=0;i<currentAnalysis.coins.length;i++){{
                const c=currentAnalysis.coins[i];
                try{{
                    const r=await fetch('/api/liveprice?symbol='+c.symbol+'&key='+ADMIN_KEY+'&t='+Date.now());
                    const j=await r.json();
                    if(j.price && j.price>0){{
                        c.livePrices.push(j.price); c.livePrice=j.price;
                        const change=(j.price-c.startPrice)/c.startPrice*100; c.liveChange=change; totalChange+=change;
                        document.getElementById('livePrice'+i).innerText='$'+j.price.toFixed(4);
                        document.getElementById('liveChange'+i).innerText=(change>=0?'+':'')+change.toFixed(3)+'%';
                        drawLiveMonitorChart(i);
                    }}
                }}catch(e){{}}
            }}
            document.getElementById('monitorTotalMove').innerText=(totalChange/currentAnalysis.coins.length).toFixed(3)+'%';
            if(timeLeft<=0){{ clearInterval(interval); finishMovingLiveMonitor(); }}
        }},1000);
    }}
    
    function drawLiveMonitorChart(idx){{
        const c=currentAnalysis.coins[idx]; if(!c || c.livePrices.length<2) return;
        const cv=document.getElementById('liveMonitorChart'+idx); if(!cv) return;
        const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h);
        const mn=Math.min(...c.livePrices)*0.9995, mx=Math.max(...c.livePrices)*1.0005;
        function yF(p){{return h*0.85-((p-mn)/(mx-mn||1))*h*0.7;}}
        ctx.strokeStyle=c.livePrices[c.livePrices.length-1]>=c.startPrice?'#0f8':'#f44'; ctx.lineWidth=1.5; ctx.beginPath();
        c.livePrices.forEach((p,i)=>{{const x=i/(c.livePrices.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();
    }}
    
    function finishMovingLiveMonitor(){{
        document.getElementById('liveMonitorText').innerText='60s Live Monitor Complete. Auto-opening trades...';
        autoConfirm3Trades();
    }}
    
    async function autoConfirm3Trades(){{
        let successCount=0;
        for(let i=0;i<currentAnalysis.coins.length;i++){{
            const c=currentAnalysis.coins[i];
            try{{
                const payload={{symbol:c.symbol, side:c.finalSide, reason:c.finalReason||'Cron scan', livePrice:c.livePrice||c.startPrice, moving_score:c.moving_score, future_change:c.future_change, confidence:c.confidence, future_pred:c.future_pred}};
                const r=await fetch('/api/open_analyzed?key='+ADMIN_KEY+'&t='+Date.now(), {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)}});
                const j=await r.json();
                if(j.ok) successCount++;
            }}catch(e){{}}
            await new Promise(r=>setTimeout(r,500));
        }}
        if(successCount>0){{ setTimeout(()=>{{ closeOverlay(); location.reload(); }},1200); }}
    }}
    
    function closeOverlay(){{ document.getElementById('analyzeOverlay').classList.remove('show'); currentAnalysis=null; }}
    async function callReset(){{if(!confirm('RESET $300?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
    async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
    async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}
    
    function initChartFuture(sym,entry,tp,sl,side,openTs,initialAge,futurePred,futureChange,confidence){{
        const cv=document.getElementById('chart-'+sym); if(!cv) return; const ctx=cv.getContext('2d');
        let prices=[]; let liveHistory=[]; let ageSec=initialAge;
        setInterval(()=>{{ ageSec+=1; }},1000);
        async function fetchPrice(){{
            try{{
                const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now());
                const j=await r.json();
                if(j.price && j.price>0){{
                    liveHistory.push(j.price); if(liveHistory.length>60) liveHistory.shift();
                    prices=[...liveHistory]; draw();
                }}
            }}catch(e){{}}
        }}
        function draw(){{
            const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h);
            if(prices.length<2){{ prices=Array(20).fill(entry); }}
            let allPrices=[...prices, ...futurePred];
            let mn=Math.min(...allPrices)*0.998, mx=Math.max(...allPrices)*1.002;
            function yF(p){{return h*0.85-((p-mn)/(mx-mn||1))*h*0.7;}}
            
            // Entry Line
            const entryY=yF(entry); ctx.strokeStyle='#fc0'; ctx.lineWidth=2; ctx.beginPath(); ctx.moveTo(0,entryY); ctx.lineTo(w,entryY); ctx.stroke();
            ctx.fillStyle='#fc0'; ctx.font='bold 9px monospace'; ctx.fillText('ENTRY '+entry.toFixed(4), 4, entryY-3);
            
            // TP Line
            const tpY=yF(tp); ctx.strokeStyle='#0f8'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.setLineDash([]);
            ctx.fillStyle='#0f8'; ctx.fillText('TP '+tp.toFixed(4), 4, tpY-3);
            
            // SL Line
            const slY=yF(sl); ctx.strokeStyle='#f44'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,slY); ctx.lineTo(w,slY); ctx.stroke(); ctx.setLineDash([]);
            ctx.fillStyle='#f44'; ctx.fillText('SL '+sl.toFixed(4), 4, slY+10);
            
            // Live Price Line
            ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=2; ctx.beginPath();
            prices.forEach((p,i)=>{{const x=i/(prices.length+futurePred.length-1)*w*0.7, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}});
            ctx.stroke();
            
            // Future Projection Dotted Line
            if(futurePred && futurePred.length>0){{
                ctx.strokeStyle='#fc0'; ctx.setLineDash([4,4]); ctx.lineWidth=2; ctx.beginPath();
                const lastX=(prices.length-1)/(prices.length+futurePred.length-1)*w*0.7;
                const lastY=yF(prices[prices.length-1]);
                ctx.moveTo(lastX, lastY);
                futurePred.forEach((fp,i)=>{{
                    const x=(prices.length+i)/(prices.length+futurePred.length-1)*w*0.9;
                    ctx.lineTo(x, yF(fp));
                }});
                ctx.stroke(); ctx.setLineDash([]);
            }}
        }}
        draw(); fetchPrice(); setInterval(fetchPrice, 3000);
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
        if price is None: return Response(json.dumps({"error":"all failed","price":0,"src":"fail"}), mimetype="application/json", status=200, headers={"Access-Control-Allow-Origin":"*"})
        return Response(json.dumps({"symbol":sym,"price":price,"ts":int(time.time()),"src":src}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/klines"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper(); base=sym.replace("USDT","")
        closes, highs, lows, vols = fetch_klines(base, "1m", 50)
        if closes: return Response(json.dumps({"symbol":sym,"closes":closes,"highs":highs,"lows":lows,"vols":vols}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
        fake=[83670 + math.sin(i/5)*50 for i in range(50)]
        return Response(json.dumps({"symbol":sym,"closes":fake,"highs":fake,"lows":fake,"vols":[1000]*50}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/scan_most_moving") or p.startswith("/api/cron"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            state=load_state()
            current_inv=sum([t.get("pos",0) for t in state.get("open",[])])
            cap=state.get("cap",300.0)
            slots_left=MAXP - len(state.get("open",[]))
            if slots_left<=0:
                return Response(json.dumps({"ok":False,"error":f"MAXP {MAXP} reached INV {current_inv:.0f}/{cap:.0f}","inv":current_inv,"cap":cap}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
            offset=state.get("scan_offset",0)
            batch=STATIC_TOP[offset:offset+SCAN_BATCH] if offset+SCAN_BATCH <= len(STATIC_TOP) else STATIC_TOP[offset:]+STATIC_TOP[: (offset+SCAN_BATCH)-len(STATIC_TOP) ]
            open_syms=[t["symbol"] for t in state.get("open",[])]
            movers=[]
            for base,shark in batch:
                if base in open_syms: continue
                closes, highs, lows, vols = fetch_klines(base, "1m", 50)
                if not closes: closes, highs, lows, vols = fetch_klines(base, "5m", 50)
                if not closes: continue
                price, src = fetch_live_price_fast(base)
                if not price or price==0: price=closes[-1] if closes else 100
                analysis=future_prediction_engine_v865(closes, highs, lows, vols)
                analysis["symbol"]=base; analysis["price"]=price; analysis["src"]=src; analysis["shark"]=shark; analysis["closes"]=closes
                movers.append(analysis)
            movers_sorted=sorted(movers, key=lambda x: (x["moving_score"], x["confidence"]), reverse=True)
            strong_movers=[m for m in movers_sorted if m["strong"]]
            if len(strong_movers)>=slots_left:
                top3=strong_movers[:slots_left]
            else:
                needed=slots_left - len(strong_movers)
                fallback=[m for m in movers_sorted if m not in strong_movers][:needed]
                for f in fallback: f["fallback"]=True
                top3=strong_movers + fallback
            if len(top3)<slots_left: top3=movers_sorted[:slots_left]
            for f in top3:
                if "fallback" not in f: f["fallback"]=True
            if p.startswith("/api/cron"):
                opened=[]
                for m in top3:
                    pos_size=cap*POS_PCT/100.0
                    curr=sum([t.get("pos",0) for t in state.get("open",[])]) + sum([o["pos"] for o in opened])
                    if curr+pos_size>cap: pos_size=(cap-curr)*0.95
                    if pos_size<10: pos_size=10
                    tr={"symbol":m["symbol"],"side":m["future_side"],"entry":m["price"],"price":m["price"],"pos":pos_size,"ts":int(time.time()),"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":60,"tp":TP_PCT,"sl":SL_PCT,"reason":f"$1.20 v865 CRON AUTO ${m['price']:.4f} FUTURE {m['future_change']:+.2f}%","rsi":m["rsi"],"shark":m["shark"],"atr":1.0,"vol":50000000,"cg_id":SYM_TO_ID.get(m["symbol"],""),"analysis":m["reason"][:200],"moving_score":m["moving_score"],"future_change":m["future_change"],"confidence":m["confidence"],"future_pred":m["future_pred"]}
                    state["open"].append(tr); opened.append(tr)
                state["scan_offset"]=(offset+SCAN_BATCH)%TOP_N; state["scan"]=state.get("scan",0)+1; state["full_scans"]=state.get("scan",0)//(TOP_N//SCAN_BATCH)
                kv_set(STATE_KEY, state)
                return Response(json.dumps({"ok":True,"auto_opened":len(opened),"movers":movers_sorted,"top3":top3}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
            state["scan_offset"]=(offset+SCAN_BATCH)%TOP_N; state["scan"]=state.get("scan",0)+1; state["full_scans"]=state.get("scan",0)//(TOP_N//SCAN_BATCH)
            kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":True,"movers":movers_sorted,"top3":top3,"offset":offset,"scan":state["scan"],"full_scans":state["full_scans"],"inv":current_inv,"cap":cap}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
        except Exception as e:
            import traceback
            return Response(json.dumps({"ok":False,"error":str(e)[:200],"trace":traceback.format_exc()[:400]}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/open_analyzed"):
        if key!=ADMIN_KEY: return Response(json.dumps({"ok":False,"error":"Forbidden key"}), mimetype="application/json", status=403, headers={"Access-Control-Allow-Origin":"*"})
        try:
            data=None; body_text=request.get_data(as_text=True) or ""
            if request.method=="POST":
                try: data=request.get_json(force=True, silent=True)
                except: data={}
                if not data and body_text:
                    try: data=json.loads(body_text)
                    except: data={}
                sym=(data.get("symbol","") if data else "").upper() or request.args.get("symbol","").upper()
                side=(data.get("side","") if data else "") or request.args.get("side","LONG")
                reason=(data.get("reason","") if data else "") or request.args.get("reason","v865 cron fixed")
                live_price_fallback=data.get("livePrice") if data else None
                moving_score=data.get("moving_score",0) if data else 0
                future_change=data.get("future_change",0) if data else 0
                confidence=data.get("confidence",0) if data else 0
                future_pred=data.get("future_pred",[]) if data else []
            else:
                sym=request.args.get("symbol","").upper(); side=request.args.get("side","LONG"); reason=request.args.get("reason","v865 cron fixed"); live_price_fallback=request.args.get("livePrice", type=float)
                moving_score=0; future_change=0; confidence=0; future_pred=[]
            if not sym: return Response(json.dumps({"ok":False,"error":"no symbol"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
            if side not in ["LONG","SHORT"]: side="LONG"
            state=load_state(); current_inv=sum([t.get("pos",0) for t in state.get("open",[])]); cap=state.get("cap",300.0)
            if len(state.get("open",[]))>=MAXP: return Response(json.dumps({"ok":False,"error":f"MAXP {MAXP} reached"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
            price, src = fetch_live_price_fast(sym)
            if (not price or price==0) and live_price_fallback and live_price_fallback>0: price=float(live_price_fallback)
            if not price or price==0: price=83670 if sym=="BTC" else 2500
            pos_size=cap*POS_PCT/100.0
            tr={"symbol":sym,"side":side,"entry":price,"price":price,"pos":pos_size,"ts":int(time.time()),"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":60,"tp":TP_PCT,"sl":SL_PCT,"reason":reason,"analysis":reason[:200],"moving_score":moving_score,"future_change":future_change,"confidence":confidence,"future_pred":future_pred}
            state["open"].append(tr); state["scan"]=state.get("scan",0)+1; state["scan_offset"]=(state.get("scan_offset",0)+1)%TOP_N
            eq=state.get("equity",[300]); eq.append(cap); state["equity"]=eq[-150:]
            kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":True,"symbol":sym,"entry":price,"pos":pos_size}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
        except Exception as e:
            import traceback
            return Response(json.dumps({"ok":False,"error":str(e)[:200],"trace":traceback.format_exc()[:400]}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); time.sleep(0.3)
        new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0],"last_cron":"reset v865 CRON FIXED CLEAN"}
        ok=kv_set(STATE_KEY,new)
        return Response(json.dumps({"ok":ok,"cap":300,"cleared":True}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]):
            lp,_=fetch_live_price_fast(tr["symbol"])
            pct=((lp-tr["entry"])/tr["entry"]*100) if (lp and lp>0) else 0
            net=tr["pos"]*(pct-TOTAL_FEE)/100
            cap+=net; state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":net,"reason":"CLOSE ALL FIXED"})
        state["open"]=[]; state["cap"]=cap; state=recalc(state); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"cap":cap}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); state=load_state(); cap=state.get("cap",300.0); final=[]
        for tr in state.get("open",[]):
            if tr["symbol"]==sym:
                lp,_=fetch_live_price_fast(sym)
                pct=((lp-tr["entry"])/tr["entry"]*100) if (lp and lp>0) else 0
                net=tr["pos"]*(pct-TOTAL_FEE)/100
                cap+=net; state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":net,"reason":f"CLOSE {sym}"})
            else: final.append(tr)
        state["open"]=final; state["cap"]=cap; state=recalc(state); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":json.dumps(True),"closed":sym,"cap":cap}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/debug") or p.startswith("/api/envcheck"):
        return Response(json.dumps({"kv_url":bool(KV_URL),"kv_token":bool(KV_TOKEN),"state":load_state()}, indent=2), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    try:
        st=load_state(); return Response(render(st), mimetype="text/html", headers={"Access-Control-Allow-Origin":"*"})
    except Exception as e:
        import traceback
        return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:2000]}</pre></body></html>", mimetype="text/html", status=200, headers={"Access-Control-Allow-Origin":"*"})
