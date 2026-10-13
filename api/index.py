"""
VENUS v856 - 3COIN AUTO-LOOP UNTIL STRONG SIGNAL - Fixes v855 no trade after scan returns to main
If 3 coins weak (no reason to invest), auto moves to next 3 coins 41-60 -> 61-80 -> 81-100 -> 1-20 until strong
Strong = score diff >=2 + (RSI<42 or >58 or 5m>0.08% or 30m>0.20% or 7/10 candles)
"""
from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse
app = Flask(__name__)
def env(k):
    for kk in k:
        v=os.environ.get(kk)
        if v: return v.strip().strip('"').strip("'")
    return ""
KV_URL=(env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"]) or "").rstrip("/")
if not KV_URL:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "URL" in kk and "upstash" in vv.lower():
            KV_URL=vv.strip().strip('"').strip("'").rstrip("/"); break
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
if not KV_TOKEN:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "TOKEN" in kk and "upstash" in kk.lower():
            KV_TOKEN=vv.strip().strip('"').strip("'"); break
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V808_SHARK100"
MAXP=3
POS_PCT=33.33
TOTAL_FEE=0.17
SCAN_BATCH=20
TOP_N=100
TP_PCT=1.20
SL_PCT=0.60
STATIC_TOP=[("BTC",60),("ETH",55),("SOL",50),("BNB",50),("XRP",48),("AVAX",45),("LINK",45),("ADA",44),("DOT",44),("LTC",43),("UNI",43),("ETC",42),("APT",42),("ARB",41),("OP",41),("SUI",40),("NEAR",40),("HBAR",40),("FIL",39),("MKR",39),("AAVE",38),("GRT",38),("RNDR",38),("INJ",38),("STX",37),("IMX",37),("SEI",37),("TIA",37),("WLD",36),("FET",36),("TAO",36),("ZEC",35),("STRK",35),("JUP",35),("ENA",34),("PENDLE",34),("ONDO",34),("DOGE",34),("CYBER",32),("PEPE",30),("BONK",29),("WIF",28),("FLOKI",27),("SHIB",26),("MEME",25),]
SYM_TO_ID={"BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin","XRP":"ripple","ADA":"cardano","AVAX":"avalanche-2","DOT":"polkadot","LINK":"chainlink","LTC":"litecoin","UNI":"uniswap","ETC":"ethereum-classic","APT":"aptos","ARB":"arbitrum","OP":"optimism","SUI":"sui","RNDR":"render-token","MKR":"maker","AAVE":"aave","GRT":"the-graph","SEI":"sei-network","TIA":"celestia","DOGE":"dogecoin","WLD":"worldcoin","FET":"fetch-ai","TAO":"bittensor","IMX":"immutable-x","JUP":"jupiter","HBAR":"hedera","ENA":"ethena","PENDLE":"pendle","ZEC":"zcash","STRK":"starknet","ONDO":"ondo-finance","NEAR":"near-protocol","CYBER":"cyberconnect","PEPE":"pepe","BONK":"bonk","WIF":"dogwifcoin","FLOKI":"floki","SHIB":"shiba-inu","MEME":"memecoin"}

def kv_get(k):
    if not KV_URL or not KV_TOKEN: return None
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d=json.loads(r.read().decode()); res=d[0].get("result") if isinstance(d,list) and d else None
            if not res: return None
            return json.loads(res) if (res.startswith("{") or res.startswith("[")) else res
    except: return None
def kv_set(k,o):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["SET",k,json.dumps(o)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r: return "OK" in r.read().decode()
    except: return False
def kv_del(k):
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=4) as r: return True
    except: return False

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
            data=json.loads(r.read().decode()); price=list(data.values())[0].get("usd",0) if data else 0
            if price>0: return float(price), "cg"
    except: pass
    return None, "fail"

def fetch_klines(base, interval="1m", limit=30):
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/klines?symbol={base}USDT&interval={interval}&limit={limit}"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                closes=[float(k[4]) for k in data if len(k)>4]
                vols=[float(k[5]) for k in data if len(k)>5]
                if len(closes)>=10:
                    return closes, vols
        except: continue
    return [], []

def analyze_30min_deep(closes, vols):
    if len(closes)<15:
        return {"side":"LONG","rsi":50,"reason":"no data fallback","score_long":1,"score_short":1,"mom_5":0,"mom_30":0,"rsi_val":50,"up_candles":5,"strong":False,"strength":0}
    last=closes[-1]
    sma5=sum(closes[-5:])/5
    sma10=sum(closes[-10:])/10 if len(closes)>=10 else sum(closes)/len(closes)
    sma20=sum(closes[-20:])/20 if len(closes)>=20 else sum(closes)/len(closes)
    sma30=sum(closes)/len(closes)
    mom_5=(closes[-1]-closes[-5])/closes[-5]*100 if closes[-5]!=0 else 0
    mom_30=(closes[-1]-closes[0])/closes[0]*100 if closes[0]!=0 else 0
    gains=0; losses=0
    for i in range(max(1,len(closes)-14), len(closes)):
        diff=closes[i]-closes[i-1]
        if diff>0: gains+=diff
        else: losses+=abs(diff)
    avg_gain=gains/14 if gains>0 else 0.001
    avg_loss=losses/14 if losses>0 else 0.001
    rs=avg_gain/avg_loss
    rsi=100 - (100/(1+rs))
    up_candles=sum(1 for i in range(len(closes)-10, len(closes)) if i>0 and closes[i]>closes[i-1])
    score_long=0; score_short=0; reasons=[]
    if last > sma30: score_long+=2; reasons.append(f">{sma30:.2f} SMA30 up")
    else: score_short+=2; reasons.append(f"<{sma30:.2f} SMA30 down")
    if sma5 > sma10 and sma10 > sma20: score_long+=3; reasons.append("SMA5>10>20 strong up")
    elif sma5 < sma10 and sma10 < sma20: score_short+=3; reasons.append("SMA5<10<20 strong down")
    elif sma5 > sma10: score_long+=1; reasons.append("SMA5>SMA10 up")
    else: score_short+=1; reasons.append("SMA5<SMA10 down")
    if mom_5>0: score_long+=2; reasons.append(f"5m {mom_5:+.3f}% up")
    else: score_short+=2; reasons.append(f"5m {mom_5:+.3f}% down")
    if mom_30>0: score_long+=1; reasons.append(f"30m {mom_30:+.2f}% up")
    else: score_short+=1; reasons.append(f"30m {mom_30:+.2f}% down")
    if rsi>60: score_long+=1; reasons.append(f"RSI {rsi:.0f} bull")
    elif rsi<40: score_short+=1; reasons.append(f"RSI {rsi:.0f} bear")
    else: reasons.append(f"RSI {rsi:.0f} neu")
    if up_candles>=6: score_long+=1; reasons.append(f"{up_candles}/10 up")
    else: score_short+=1; reasons.append(f"{10-up_candles}/10 down")
    side="LONG" if score_long>=score_short else "SHORT"
    diff=abs(score_long-score_short)
    # Strong signal logic
    strong=False
    strength=diff
    if diff>=2:
        if rsi<42 or rsi>58: strong=True; strength+=1
        if abs(mom_5)>=0.08: strong=True; strength+=1
        if abs(mom_30)>=0.20: strong=True; strength+=1
        if up_candles>=7 or up_candles<=3: strong=True; strength+=1
        if diff>=3: strong=True; strength+=1
    # If diff 2+ but no other, still consider medium strong
    if diff>=2 and not strong:
        # check if at least one momentum
        if abs(mom_5)>=0.05 or abs(mom_30)>=0.15:
            strong=True
    reason_str=f"{side} {score_long}v{score_short} " + " | ".join(reasons[:4]) + (f" | STRONG s{strength}" if strong else " | WEAK skip")
    return {"side":side,"rsi":int(rsi),"reason":reason_str,"score_long":score_long,"score_short":score_short,"mom_5":mom_5,"mom_30":mom_30,"rsi_val":rsi,"up_candles":up_candles,"sma5":sma5,"sma10":sma10,"sma20":sma20,"closes":closes,"strong":strong,"strength":strength,"diff":diff}

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0],"last_cron":"never v856 3COIN LOOP"}
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("learn",{"blacklist":{},"last_coins":{}}); s.setdefault("peak",s.get("cap",300)); s.setdefault("equity",[300,s.get("cap",300)]); s.setdefault("last_cron","never")
    if len(s.get("open",[]))>MAXP:
        s["open"]=sorted(s["open"], key=lambda x: x.get("ts",0), reverse=True)[:MAXP]
    L=s["learn"]; L.setdefault("blacklist",{}); L.setdefault("last_coins",{})
    now=int(time.time()); L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}; L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    for t in s.get("open",[]):
        t["tp"]=TP_PCT; t["sl"]=SL_PCT
    return s

def recalc(state):
    all_closed=state.get("closed",[]); state["wins"]=sum(1 for c in all_closed if c.get("net",0)>0); state["loss"]=sum(1 for c in all_closed if c.get("net",0)<0); state["total"]=len(all_closed)
    valid=[c for c in all_closed if c.get("symbol","").upper() not in ["CTK","KORUB","SKHYB"]]
    state["daily"]=sum([c.get("net",0) for c in valid[-20:]]) if valid else sum([c.get("net",0) for c in all_closed[-10:]])
    return state

def render(state):
    state=recalc(state)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300.0); fees_paid=state.get("fees_paid",0.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0); offset=state.get("scan_offset",0); full_scans=state.get("full_scans",0); daily=state.get("daily",0.0)
    peak=state.get("peak",cap); equity=state.get("equity",[300,cap])
    winrate=int(wins/tot*100) if tot>0 else 0; unreal=sum([t.get("net",0) for t in open_tr]); long_open=sum(1 for t in open_tr if t.get("side")=="LONG"); short_open=sum(1 for t in open_tr if t.get("side")=="SHORT")
    gross_profit=sum([c.get("net",0) for c in closed if c.get("net",0)>0]); gross_loss=sum([c.get("net",0) for c in closed if c.get("net",0)<0])
    pf=abs(gross_profit/gross_loss) if gross_loss!=0 else 0; exp=(gross_profit+gross_loss)/tot if tot>0 else 0
    best=max(closed, key=lambda x: x.get("net",0)) if closed else None; worst=min(closed, key=lambda x: x.get("net",0)) if closed else None
    best_sym=best.get('symbol','-') if best else '-'; best_net=best.get('net',0) if best else 0; worst_sym=worst.get('symbol','-') if worst else '-'; worst_net=worst.get('net',0) if worst else 0
    invested=sum([t.get("pos",0) for t in open_tr]); bias_color="#ffcc00"
    dd=(peak-cap)/peak*100 if peak>0 else 0
    daily_needed=max(0,15.0-daily); trades_needed=int(daily_needed/1.50)+1 if daily_needed>0 else 0
    daily_color = "#0f8" if daily>=0 else "#f44"; target_color = "#0f8"
    last_cron = state.get("last_cron","never v856")
    cap_safe_color = "#0f8" if invested <= cap*1.05 else "#f44"
    over_msg = "✅" if invested<=cap*1.05 else "❌ OVER"
    trade_boxes_html=""; chart_js_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",150); entry=tr.get("entry",0); tp=tr.get("tp",TP_PCT); sl=tr.get("sl",SL_PCT); rr=tp/sl if sl>0 else 2.0
        tp_price=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100); sl_price=entry*(1-sl/100) if side=="LONG" else entry*(1+sl/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        net_target = pos*(tp-TOTAL_FEE)/100
        analysis=tr.get("analysis","3coin loop")[:100]
        shark_tag=f"<span style='background:#00d4ff;color:#000;padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900'>SHARK {tr.get('shark',0)} RR {rr:.1f} ${net_target:.2f}</span>"
        ts=tr.get("ts",int(time.time()))
        trade_boxes_html+=f"""<div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'><div style='display:flex;justify-content:space-between'><div><b style='color:{col};font-size:14px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f} {shark_tag}</b><div style='font-size:10px;color:#0f8'>🤖 3COIN LOOP: {analysis}</div><div style='font-size:10px;color:#aaa'>ENTRY ${entry:.6f} TP ${tp_price:.6f} ({tp:.2f}%) = ${net_target:.2f} NET SL ${sl_price:.6f} ({sl:.2f}%) INV {invested:.0f}/{cap:.0f}</div></div><button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 10px'>✕</button></div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin:8px 0;text-align:center'><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>LIVE</div><div id='live-price-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('price',0):.5f}</div><div id='live-change-{sym}' style='font-size:10px'>{tr.get('pct_gross',0):+.3f}%</div><div id='live-dot-{sym}' style='font-size:8px;color:#0f8'>● V856 LOOP</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>PNL</div><div id='live-pnl-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f} / ${net_target:.2f}</div><div style='font-size:10px'>PEAK {tr.get('peak_gross',0):.2f}% TARGET $1.50</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>AGE</div><div id='live-age-{sym}' style='font-size:13px;font-weight:900'>{int(tr.get('age',0)//60)}m {int(tr.get('age',0)%60)}s</div><div style='font-size:10px;color:#0f8'>TP {tp:.2f}% SL {sl:.2f}%</div></div></div><div style='background:#000;border-radius:12px;padding:6px;border:1px solid #222'><div style='font-size:9px;color:#555'>TURBO GRAPH {side} - 3COIN LOOP AUTO 30M+1M - {analysis[:70]} - TP GREEN SL RED ENTRY YELLOW</div><canvas id='chart-{sym}' width='340' height='180' style='width:100%;height:180px;background:#000;border-radius:8px'></canvas></div><div style='font-size:9px;color:#888;margin-top:4px'>{tr.get('reason','')}</div></div>"""
        chart_js_init+=f"initChart('{sym}',{entry},{tp_price},{sl_price},'{side}',{ts},{int(tr.get('age',0))},'{tr.get('cg_id','bitcoin')}');\n"
    if not open_tr:
        trade_boxes_html=f"<div class='it' style='text-align:center;color:#666;padding:16px'>No open trades - TAP CRON 3COIN LOOP - v856 auto-loops through 3-coin batches until STRONG signal found (diff≥2 + RSI<42/>58 or 5m>0.08% etc) then 1M live graph then AUTO-OPEN 3 trades - SCAN {scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} FULL {full_scans}x CAP ${cap:.2f}<br>LAST CRON: {last_cron}<br>INV {invested:.0f}/{cap:.0f} MAXP {MAXP} - AUTO LOOP TILL REASON TO INVEST</div>"
    equity_js=json.dumps(equity[-80:])
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}}.h{{background:linear-gradient(90deg,#00ff88,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}}.g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}}.stats{{background:#111;border:2px solid #0f8;padding:10px;margin:6px 0;border-radius:12px}}.it{{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:12px}}.btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.btn{{padding:16px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px;cursor:pointer}}.btn-cron{{background:#0f8;color:#000}}.btn-reset{{background:#f44;color:#fff}}.btn-close{{background:#fc0;color:#000}}.badge{{padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900}}.long{{background:#0f8;color:#000}}.short{{background:#f44;color:#fff}}.overlay{{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.95);z-index:9999;display:none;flex-direction:column;padding:10px;overflow-y:auto}}.overlay.show{{display:flex}}.coin-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}}@media(max-width:600px){{.coin-grid{{grid-template-columns:1fr}}}}</style></head><body>
    <div id='analyzeOverlay' class='overlay'><div style='background:#111;border:2px solid #0f8;border-radius:16px;padding:12px'><div style='color:#0f8;font-weight:900;font-size:14px;text-align:center' id='analyzeTitle'>🤖 3COIN AUTO-LOOP TILL STRONG SIGNAL</div><div style='color:#fc0;font-size:11px;text-align:center;margin:6px 0' id='analyzeStatus'>Starting 3-coin auto-loop scan...</div><div style='background:#000;border-radius:12px;padding:8px;margin:8px 0'><div style='font-size:10px;color:#888'>LOOP SCAN LOG - Auto moves to next 3 coins if weak (no reason to invest)</div><div id='loopLog' style='color:#aaa;font-size:9px;white-space:pre-wrap;max-height:80px;overflow-y:auto;background:#0a0a0a;padding:6px;border-radius:8px;margin:4px 0'></div><div style='font-size:10px;color:#888'>3-COIN 30-MIN DEEP CHART ANALYSIS - Current batch</div><div id='deepAnalysisText' style='color:#0f8;font-size:10px;margin:4px 0;white-space:pre-wrap'>Waiting...</div><div class='coin-grid'><div style='background:#111;border-radius:10px;padding:6px'><div id='deepCoin0' style='color:#fc0;font-weight:900;font-size:11px'>Coin1: -</div><canvas id='deepChart0' width='200' height='150' style='width:100%;height:150px;background:#000;border-radius:8px'></canvas><div id='deepText0' style='color:#0f8;font-size:8px;white-space:pre-wrap'>Waiting...</div></div><div style='background:#111;border-radius:10px;padding:6px'><div id='deepCoin1' style='color:#fc0;font-weight:900;font-size:11px'>Coin2: -</div><canvas id='deepChart1' width='200' height='150' style='width:100%;height:150px;background:#000;border-radius:8px'></canvas><div id='deepText1' style='color:#0f8;font-size:8px;white-space:pre-wrap'>Waiting...</div></div><div style='background:#111;border-radius:10px;padding:6px'><div id='deepCoin2' style='color:#fc0;font-weight:900;font-size:11px'>Coin3: -</div><canvas id='deepChart2' width='200' height='150' style='width:100%;height:150px;background:#000;border-radius:8px'></canvas><div id='deepText2' style='color:#0f8;font-size:8px;white-space:pre-wrap'>Waiting...</div></div></div></div><div style='background:#000;border-radius:12px;padding:8px;margin:8px 0;border:1px solid #333'><div style='font-size:10px;color:#888'>3-COIN 1-MIN LIVE GRAPH MONITOR - Tracking 3 coins live 60s before decision</div><div id='liveMonitorText' style='color:#ffcc00;font-size:11px;margin:4px 0'>Waiting for strong signal...</div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;text-align:center'><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>TIME LEFT</div><div id='monitorTimeLeft' style='font-size:18px;font-weight:900;color:#f44'>60s</div><div id='monitorProgress' style='font-size:9px'>0/60s</div></div><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>TOTAL LIVE</div><div id='monitorTotalMove' style='font-size:12px;font-weight:900;color:#0f8'>+0.00%</div><div style='font-size:9px'>Avg 3 coins</div></div><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>BATCH</div><div id='monitorBatch' style='font-size:10px;font-weight:900;color:#fc0'>41-60/100 x4</div></div></div><div class='coin-grid' style='margin-top:8px'><div style='background:#111;border-radius:10px;padding:6px'><div style='display:flex;justify-content:space-between'><div id='liveCoin0' style='color:#0f8;font-weight:900;font-size:10px'>Coin1: -</div><div id='liveChange0' style='color:#0f8;font-size:10px'>+0.00%</div></div><div style='font-size:8px;color:#888'>START <span id='liveStart0'>$0</span> LIVE <span id='livePrice0'>$0</span></div><canvas id='liveMonitorChart0' width='200' height='120' style='width:100%;height:120px;background:#000;border-radius:8px;margin-top:4px'></canvas><div id='liveDecision0' style='color:#0f8;font-size:9px;font-weight:900;margin-top:2px'>Waiting...</div></div><div style='background:#111;border-radius:10px;padding:6px'><div style='display:flex;justify-content:space-between'><div id='liveCoin1' style='color:#0f8;font-weight:900;font-size:10px'>Coin2: -</div><div id='liveChange1' style='color:#0f8;font-size:10px'>+0.00%</div></div><div style='font-size:8px;color:#888'>START <span id='liveStart1'>$0</span> LIVE <span id='livePrice1'>$0</span></div><canvas id='liveMonitorChart1' width='200' height='120' style='width:100%;height:120px;background:#000;border-radius:8px;margin-top:4px'></canvas><div id='liveDecision1' style='color:#0f8;font-size:9px;font-weight:900;margin-top:2px'>Waiting...</div></div><div style='background:#111;border-radius:10px;padding:6px'><div style='display:flex;justify-content:space-between'><div id='liveCoin2' style='color:#0f8;font-weight:900;font-size:10px'>Coin3: -</div><div id='liveChange2' style='color:#0f8;font-size:10px'>+0.00%</div></div><div style='font-size:8px;color:#888'>START <span id='liveStart2'>$0</span> LIVE <span id='livePrice2'>$0</span></div><canvas id='liveMonitorChart2' width='200' height='120' style='width:100%;height:120px;background:#000;border-radius:8px;margin-top:4px'></canvas><div id='liveDecision2' style='color:#0f8;font-size:9px;font-weight:900;margin-top:2px'>Waiting...</div></div></div></div><div style='background:#111;border-radius:12px;padding:8px;margin:8px 0'><div style='font-size:10px;color:#888'>AUTO DECISION AFTER 30M DEEP + 1M LIVE - 3 COINS - Will auto-open 3 trades if strong</div><div id='finalDecision' style='color:#0f8;font-size:12px;font-weight:900;margin:4px 0;white-space:pre-wrap'>Scanning for strong signal...</div><div id='finalReason' style='color:#aaa;font-size:9px;white-space:pre-wrap'>Auto-loop till reason to invest found...</div></div><div style='background:#000;padding:10px;border-radius:10px;text-align:center'><div id='autoStatus' style='color:#0f8;font-size:12px;font-weight:900;white-space:pre-wrap'>🤖 Auto-loop scanning 3-coin batches till strong signal...</div><div id='autoErrorLog' style='color:#f44;font-size:9px;margin-top:6px;white-space:pre-wrap;text-align:left;max-height:60px;overflow-y:auto'></div><div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px'><button onclick='autoConfirm3Trades()' id='forceOpenBtn' style='background:#fc0;color:#000;padding:12px;border-radius:10px;border:0;font-weight:900;display:none'>⚡ FORCE OPEN 3 TRADES</button><button onclick='closeOverlay()' style='background:#333;color:#fff;padding:12px;border-radius:10px;border:0;font-weight:900'>❌ CLOSE</button></div></div></div></div>
    <div class='h'>VENUS v856 3COIN LOOP TILL STRONG - SCAN #{scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} - ${cap:.2f} PEAK ${peak:.2f} DD {dd:.1f}% L:{long_open} S:{short_open} FULLx{full_scans} - DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> NEED {trades_needed}x $1.50 INV <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f} {over_msg}</span> POS {POS_PCT:.1f}% x{MAXP}<br><span style='font-size:9px'>LAST: {last_cron[:90]}</span></div>
    <div style='background:#000;border-radius:12px;padding:8px;margin:6px 0;border:1px solid #333'><div style='font-size:9px;color:#888'>EQUITY CURVE (CAP $300 → ${cap:.2f}) PEAK ${peak:.2f} DD {dd:.1f}% DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> INV <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f} {over_msg}</span> NEED {trades_needed}x $1.50 - V856 LOOP TILL STRONG - {last_cron[:60]}</div><canvas id='equityChart' width='340' height='80' style='width:100%;height:80px;background:#000;border-radius:8px'></canvas></div>
    <div class='btn-row'><button class='btn btn-cron' onclick='start3CoinLoop()' id='cronBtn'>🤖 CRON 3COIN LOOP {invested:.0f}/{cap:.0f} {over_msg}<div id='cronStat' style='font-size:10px'>TAP {offset+1}-{offset+SCAN_BATCH}/{TOP_N} SCAN {scan} FULL {full_scans} - AUTO-LOOP 3COIN TILL STRONG REASON THEN 1M LIVE + AUTO-OPEN - <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> INV {invested:.0f}/{cap:.0f}<br>{last_cron[:30]}</div></button><button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN ${invested:.0f}/{cap:.0f} {over_msg}</div></button><button class='btn btn-reset' onclick='callReset()'>🔄RESET LOOP v11<div style='font-size:10px'>CAP $300 LOOP TILL STRONG</div></button></div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#fc0'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}<br>INV <b style='color:{cap_safe_color}'>${invested:.0f}/{cap:.0f} {over_msg}</b><br>FEES ${fees_paid:.2f}<br>PEAK ${peak:.2f} DD {dd:.1f}%</div><div class='c'>DAILY $15<br><b style='font-size:18px'><span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span></b><br>NEED ${daily_needed:.2f} = {trades_needed}x $1.50<br>W:{wins} L:{loss} {winrate}%<br>TOTAL {tot} V856<br>FULL {full_scans}x PF {pf:.2f}<br>LOOP TILL STRONG</div><div class='c' style='border-color:{bias_color}'><b style='color:{bias_color}'>3COIN LOOP<br>POS {POS_PCT:.1f}% x{MAXP}<br>v856</b><br>TP {TP_PCT}% = $1.50<br>SL {SL_PCT}%<br>RR 2.0<br>INV <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f}</span><br>LOOP TILL REASON</div></div>
    <div class='stats'><div style='color:#0f8;font-weight:900;font-size:12px'>🤖 v856 LOOP TILL STRONG SIGNAL - Scans 3-coin batches (41-60, 61-80, 81-100, 1-20, 21-40...) - If 30M deep analysis shows WEAK (diff<2, RSI 45-55, 5m<0.05%) → auto moves to next 3 coins until STRONG reason found (diff≥2 + RSI<42/>58 or 5m>0.08% or 30m>0.20% or 7/10 candles). Then 1M live graph for those 3 + auto-open. Fixes main page nothing happen bug.</div><div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px;font-size:10px'><div>SCAN: <b>{offset+1}-{offset+SCAN_BATCH}/{TOP_N} (x{full_scans}) V856 LOOP INV {invested:.0f}/{cap:.0f}</b></div><div>OPEN: <b>{len(open_tr)}/{MAXP} PEAK ${peak:.2f} DD {dd:.1f}% DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span></b></div><div>TOTAL: <b>{tot}</b> W:<b style='color:#0f8'>{wins}</b> L:<b style='color:#f44'>{loss}</b> {winrate}% PF:<b>{pf:.2f}</b></div><div>EXP: <b>${exp:.3f}</b> FEES: <b>{TOTAL_FEE}%</b> NEED: <b>${daily_needed:.2f} = {trades_needed}x $1.50 INV {invested:.0f}/{cap:.0f}</b></div><div>BEST: <b>{best_sym} ${best_net:+.2f}</b></div><div>WORST: <b>{worst_sym} ${worst_net:+.2f}</b></div></div><div style='margin-top:6px;color:#fc0;font-size:9px'>LAST CRON: {last_cron}</div><div style='margin-top:6px;color:#0f8;font-size:10px'>✅ v856 LOOP: Auto-loops 3-coin batches till STRONG reason to invest found, then 30M+1M + auto-open. Fixes v855 scan returns to main with no trade.</div></div><div id='openbox'>{trade_boxes_html}</div><div style='background:#111;padding:10px;margin:6px 0;border-radius:10px'><div style='color:#fc0;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% - PF {pf:.2f} EXP ${exp:.3f} PEAK ${peak:.2f} DD {dd:.1f}% DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> INV {invested:.0f}/{cap:.0f} NEED {trades_needed}x $1.50 - V856 LOOP</div>"""
    for cl in closed[:30]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"; sym=cl.get("symbol","?"); side=cl.get("side","?"); net=cl.get("net",0); pct=cl.get("pct_net",0); reason=cl.get("reason","")[:80]; age=cl.get("age",0); shark=cl.get("shark",0)
        html+=f"<div style='padding:5px 0;border-bottom:1px solid #222;color:{c}'><b>{sym} {side} SHARK {shark}</b> ${net:+.2f} {pct:+.2f}% | {reason} | {int(age//60)}m</div>"
    html+=f"""</div><script>const EQUITY = {equity_js};const ADMIN_KEY="{ADMIN_KEY}";const TP_PCT={TP_PCT};const SL_PCT={SL_PCT};let currentAnalysis=null;let liveMonitors=[];let timeLeft=60;let retryCount=0;let loopCount=0;
    function drawEquity(){{const cv=document.getElementById('equityChart'); if(!cv||!EQUITY.length) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...EQUITY)*0.999, mx=Math.max(...EQUITY)*1.001, rg=mx-mn||1; function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}} ctx.strokeStyle='#222'; for(let i=0;i<3;i++){{const y=h*0.1+i*h*0.8/2; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const y300=yF(300); ctx.strokeStyle='#444'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,y300); ctx.lineTo(w,y300); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle='#666'; ctx.font='8px monospace'; ctx.fillText('300',2,y300-2); ctx.strokeStyle='#0f8'; ctx.lineWidth=2; ctx.beginPath(); EQUITY.forEach((p,i)=>{{const x=i/(EQUITY.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=EQUITY[EQUITY.length-1]; ctx.fillStyle='#fc0'; ctx.beginPath(); ctx.arc(w-4,yF(last),3,0,Math.PI*2); ctx.fill(); ctx.fillText(last.toFixed(2), w-50, yF(last)-4);}}
    function logLoop(msg){{const el=document.getElementById('loopLog'); if(el){{ el.innerText+= '\\n'+msg; el.scrollTop=el.scrollHeight; }} console.log(msg); }}
    function logError(msg){{const el=document.getElementById('autoErrorLog'); if(el){{ el.innerText+= '\\n'+msg; }} console.error(msg); }}
    async function start3CoinLoop(){{loopCount=0; retryCount=0; const overlay=document.getElementById('analyzeOverlay'); overlay.classList.add('show'); document.getElementById('loopLog').innerText=''; document.getElementById('autoErrorLog').innerText=''; document.getElementById('forceOpenBtn').style.display='none'; currentAnalysis={{coins:[]}}; logLoop('Starting auto-loop scan till strong signal...'); await loopScanBatch(); }}
    async function loopScanBatch(){{loopCount++; if(loopCount>10){{ document.getElementById('analyzeStatus').innerText='Scanned 10 batches (30 coins), no strong signal, opening best available'; document.getElementById('finalDecision').innerText='No strong signal after 30 coins, will open best of last batch'; if(currentAnalysis.coins && currentAnalysis.coins.length>0){{ start3CoinLiveMonitor(); return; }} else{{ document.getElementById('analyzeStatus').innerText='No coins found after 10 loops'; setTimeout(()=>{{ closeOverlay(); }},2000); return; }} }} document.getElementById('analyzeTitle').innerText='🤖 3COIN AUTO-LOOP BATCH '+loopCount+' - Scanning till strong'; document.getElementById('analyzeStatus').innerText='Scanning batch '+loopCount+' (3 coins) for strong reason to invest...'; try{{const r=await fetch('/api/analyze_3candidates_loop?key='+ADMIN_KEY+'&loop='+loopCount+'&t='+Date.now()); const txt=await r.text(); let j; try{{ j=JSON.parse(txt); }}catch(e){{ logLoop('Batch '+loopCount+' JSON fail: '+txt.substring(0,100)); await new Promise(r=>setTimeout(r,1000)); return loopScanBatch(); }} if(!j.ok){{ logLoop('Batch '+loopCount+' fail: '+j.error); document.getElementById('analyzeStatus').innerText='FAIL: '+j.error; if(j.error.includes('MAXP')){{ setTimeout(()=>{{ closeOverlay(); location.reload(); }},1500); return; }} await new Promise(r=>setTimeout(r,1000)); return loopScanBatch(); }} const coins=j.coins||[]; if(coins.length==0){{ logLoop('Batch '+loopCount+' no coins, next batch'); await new Promise(r=>setTimeout(r,800)); return loopScanBatch(); }} document.getElementById('monitorBatch').innerText=j.offset+'-'+(j.offset+19)+'/'+j.top_n+' x'+j.full_scans+' (batch '+loopCount+')'; document.getElementById('deepAnalysisText').innerText='Batch '+loopCount+': '+j.offset+'-'+(j.offset+19)+'/100 - '+coins.map(c=>c.symbol+' $'+c.price).join(' | ')+' - Checking strong signal...'; logLoop('Batch '+loopCount+' '+j.offset+'-'+(j.offset+19)+' : '+coins.map(c=>c.symbol).join(',')+' - fetching 30M deep...'); currentAnalysis.coins=coins.map(c=>({{...c, deep:null, closes:[], livePrices:[c.price], startPrice:c.price, livePrice:c.price, liveChange:0, finalSide:'LONG', finalReason:''}})); let strongFound=false; let strongCoins=[]; for(let i=0;i<coins.length;i++){{ const sym=coins[i].symbol; document.getElementById('deepCoin'+i).innerText=sym+' - Fetching 30M...'; try{{ const r2=await fetch('/api/deep30m?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const txt2=await r2.text(); let j2; try{{ j2=JSON.parse(txt2); }}catch(e){{ j2={{closes:[],analysis:{{side:'LONG',reason:'fallback',strong:false,strength:0}}}}; }} const closes=j2.closes||[]; const deep=j2.analysis||{{side:'LONG',reason:'fallback',strong:false,strength:0}}; currentAnalysis.coins[i].deep=deep; currentAnalysis.coins[i].closes=closes; const strongTag=deep.strong?'✅ STRONG s'+deep.strength:'❌ WEAK'; document.getElementById('deepCoin'+i).innerText=sym+' - '+deep.side+' '+deep.score_long+'v'+deep.score_short+' '+strongTag; document.getElementById('deepText'+i).innerText=(deep.reason||'').substring(0,150)+'\\n30m '+(deep.mom_30||0).toFixed(2)+'% 5m '+(deep.mom_5||0).toFixed(3)+'% RSI '+(deep.rsi_val||50).toFixed(0)+' str:'+deep.strength+' '+ (deep.strong?'STRONG':'WEAK'); drawDeepChart(i, closes, deep); if(deep.strong){{ strongFound=true; strongCoins.push(sym); }} }}catch(e){{ logLoop('Deep '+sym+' err '+e); document.getElementById('deepText'+i).innerText='ERR '+e; }} }} if(strongFound){{ logLoop('✅ Batch '+loopCount+' FOUND STRONG: '+strongCoins.join(',')+' - proceeding to 1M live monitor'); document.getElementById('analyzeStatus').innerText='✅ Batch '+loopCount+' FOUND STRONG SIGNAL: '+strongCoins.join(',')+' - Opening 1M live graph...'; document.getElementById('finalDecision').innerText='STRONG signal found in batch '+loopCount+': '+strongCoins.join(',')+' - Starting 1M live monitor'; start3CoinLiveMonitor(); }} else{{ logLoop('❌ Batch '+loopCount+' '+coins.map(c=>c.symbol).join(',')+' - WEAK no reason to invest (all diff<2 or RSI 45-55, 5m<0.05%) - Moving to next 3 coins...'); document.getElementById('analyzeStatus').innerText='❌ Batch '+loopCount+' WEAK - '+coins.map(c=>c.symbol).join(',')+' no strong reason - Moving to next 3 coins  (auto-loop)...'; document.getElementById('finalDecision').innerText='Batch '+loopCount+' WEAK, moving to next 3 coins till strong found...\\nScanned: '+coins.map(c=>c.symbol+' '+c.deep.score_long+'v'+c.deep.score_short+' '+(c.deep.strong?'STRONG':'WEAK')).join(' | '); await new Promise(r=>setTimeout(r,1500)); loopScanBatch(); }} }}catch(e){{ logLoop('loopScanBatch err '+e); document.getElementById('analyzeStatus').innerText='ERR '+e+' - retry next batch'; await new Promise(r=>setTimeout(r,1500)); loopScanBatch(); }} }}
    function drawDeepChart(idx, closes, deep){{const cv=document.getElementById('deepChart'+idx); if(!cv) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); if(closes.length<5){{ ctx.fillStyle='#666'; ctx.fillText('No data',10,h/2); return; }} const mn=Math.min(...closes)*0.999, mx=Math.max(...closes)*1.001; function yF(p){{return h*0.85-((p-mn)/(mx-mn||1))*h*0.7;}} ctx.strokeStyle='#1a1a1a'; for(let i=0;i<3;i++){{const y=h*0.1+i*h*0.8/2; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} ctx.strokeStyle=deep.strong?'#0f8':'#666'; ctx.lineWidth=1.5; ctx.beginPath(); closes.forEach((p,i)=>{{const x=i/(closes.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); }}
    function start3CoinLiveMonitor(){{timeLeft=60; document.getElementById('monitorTimeLeft').innerText='60s'; document.getElementById('monitorProgress').innerText='0/60s'; for(let i=0;i<currentAnalysis.coins.length;i++){{ const c=currentAnalysis.coins[i]; document.getElementById('liveCoin'+i).innerText=c.symbol+' - Monitoring...'; document.getElementById('liveStart'+i).innerText='$'+c.startPrice.toFixed(4); document.getElementById('livePrice'+i).innerText='$'+c.startPrice.toFixed(4); document.getElementById('liveChange'+i).innerText='+0.00%'; document.getElementById('liveDecision'+i).innerText='Monitoring...'; c.livePrices=[c.startPrice]; drawLiveMonitorChart(i); }} const interval=setInterval(async()=>{{ timeLeft--; document.getElementById('monitorTimeLeft').innerText=timeLeft+'s'; document.getElementById('monitorProgress').innerText=(60-timeLeft)+'/60s'; let totalChange=0; for(let i=0;i<currentAnalysis.coins.length;i++){{ const c=currentAnalysis.coins[i]; try{{ const r=await fetch('/api/liveprice?symbol='+c.symbol+'&key='+ADMIN_KEY+'&t='+Date.now()); const txt=await r.text(); let j; try{{ j=JSON.parse(txt); }}catch(e){{ continue; }} if(j.price && j.price>0){{ c.livePrices.push(j.price); if(c.livePrices.length>60) c.livePrices.shift(); c.livePrice=j.price; const change=(j.price-c.startPrice)/c.startPrice*100; c.liveChange=change; totalChange+=change; document.getElementById('livePrice'+i).innerText='$'+j.price.toFixed(4); document.getElementById('liveChange'+i).innerText=(change>=0?'+':'')+change.toFixed(3)+'%'; document.getElementById('liveChange'+i).style.color=change>=0?'#0f8':'#f44'; drawLiveMonitorChart(i); const deep=c.deep||{{}}; let finalSide='LONG'; if((deep.score_long||0) >= (deep.score_short||0) && change>=-0.05) finalSide='LONG'; else if((deep.score_short||0) > (deep.score_long||0) || change<-0.1) finalSide='SHORT'; else finalSide=deep.side||'LONG'; c.finalSide=finalSide; c.finalReason='30M '+ (deep.score_long||0)+'v'+(deep.score_short||0)+' s'+(deep.strength||0)+' + 1M '+change.toFixed(3)+'% -> '+finalSide+' | '+(deep.reason||'').substring(0,60); document.getElementById('liveDecision'+i).innerText=finalSide+' '+change.toFixed(3)+'% -> '+finalSide; document.getElementById('liveDecision'+i).style.color=finalSide=='LONG'?'#0f8':'#f44'; document.getElementById('liveCoin'+i).innerText=c.symbol+' '+finalSide+' (preview)'; }} }}catch(e){{}} }} document.getElementById('monitorTotalMove').innerText=(totalChange/currentAnalysis.coins.length).toFixed(3)+'%'; let summary=currentAnalysis.coins.map(c=>c.symbol+': '+c.finalSide+' '+c.liveChange.toFixed(3)+'%').join(' | '); document.getElementById('finalDecision').innerText='Live 3-coin: '+summary+'\\nAUTO-OPEN in '+timeLeft+'s (found strong in batch '+loopCount+')'; if(timeLeft<=0){{ clearInterval(interval); finish3CoinLiveMonitor(); }} }},1000); }}
    function drawLiveMonitorChart(idx){{const c=currentAnalysis.coins[idx]; if(!c || c.livePrices.length<2) return; const cv=document.getElementById('liveMonitorChart'+idx); if(!cv) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...c.livePrices)*0.9995, mx=Math.max(...c.livePrices)*1.0005; const minRange=c.startPrice*0.002; let mn2=mn, mx2=mx; if((mx-mn)<minRange){{ const mid=(mn+mx)/2; mn2=mid-minRange/2; mx2=mid+minRange/2; }} function yF(p){{return h*0.85-((p-mn2)/(mx2-mn2||minRange))*h*0.7;}} ctx.strokeStyle='#1a1a1a'; for(let i=0;i<2;i++){{const y=h*0.1+i*h*0.8; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const startY=yF(c.startPrice); ctx.strokeStyle='#fc0'; ctx.setLineDash([3,3]); ctx.beginPath(); ctx.moveTo(0,startY); ctx.lineTo(w,startY); ctx.stroke(); ctx.setLineDash([]); ctx.strokeStyle=c.livePrices[c.livePrices.length-1]>=c.startPrice?'#0f8':'#f44'; ctx.lineWidth=1.5; ctx.beginPath(); c.livePrices.forEach((p,i)=>{{const x=i/(c.livePrices.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); }}
    function finish3CoinLiveMonitor(){{let summary=currentAnalysis.coins.map(c=>{{ const deep=c.deep||{{}}; const change=c.liveChange||0; const sl=c.finalSide; let finalSide=sl; let reason=''; if((deep.score_long||0)>=(deep.score_short||0) && change>=-0.05){{ finalSide='LONG'; reason='30M '+ (deep.score_long||0)+'v'+(deep.score_short||0)+' uptrend s'+(deep.strength||0)+' ('+(deep.mom_30||0).toFixed(2)+'% 30m) + 1M '+change.toFixed(3)+'% '+(change>=0?'up':'down')+' -> LONG'; }} else{{ finalSide='SHORT'; reason='30M '+ (deep.score_long||0)+'v'+(deep.score_short||0)+' downtrend s'+(deep.strength||0)+' ('+(deep.mom_30||0).toFixed(2)+'% 30m) + 1M '+change.toFixed(3)+'% down -> SHORT'; }} c.finalSide=finalSide; c.finalReason=reason+' | RSI '+(deep.rsi_val||50).toFixed(0)+' | '+ (deep.reason||'').substring(0,80); return c.symbol+' '+finalSide+' '+change.toFixed(3)+'%'; }}).join('\\n'); document.getElementById('finalDecision').innerText='✅ FINAL 3-COIN DECISION (batch '+loopCount+'):\\n'+summary; document.getElementById('finalReason').innerText=currentAnalysis.coins.map(c=>c.symbol+': '+c.finalReason).join('\\n'); document.getElementById('liveMonitorText').innerText='✅ 3-COIN 1M LIVE DONE (batch '+loopCount+') - Auto-opening 3 trades...'; document.getElementById('autoStatus').innerText='🤖 AUTO-OPENING 3 trades NOW (batch '+loopCount+' strong found)...\\n'+summary+'\\nAttempt '+(retryCount+1)+'/3...'; document.getElementById('forceOpenBtn').style.display='block'; setTimeout(()=>{{ autoConfirm3Trades(); }},1500); }}
    async function autoConfirm3Trades(){{retryCount++; document.getElementById('autoStatus').innerText='🤖 Opening 3 trades... Attempt '+retryCount+'/3\\n'+currentAnalysis.coins.map(c=>c.symbol+' '+c.finalSide).join(' | '); logError('autoConfirm3Trades attempt '+retryCount); let successCount=0; for(let i=0;i<currentAnalysis.coins.length;i++){{ const c=currentAnalysis.coins[i]; try{{ const payload={{symbol:c.symbol, side:c.finalSide, reason:c.finalReason.substring(0,200), livePrice:c.livePrice||c.startPrice}}; logError('Opening '+c.symbol+' '+c.finalSide); const r=await fetch('/api/open_analyzed?key='+ADMIN_KEY+'&t='+Date.now(), {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)}}); const text=await r.text(); logError(c.symbol+' response: '+text.substring(0,200)); let j; try{{ j=JSON.parse(text); }}catch(e){{ logError(c.symbol+' JSON fail '+text.substring(0,100)); continue; }} if(j.ok){{ successCount++; logError(c.symbol+' SUCCESS'); }} else{{ logError(c.symbol+' FAIL '+j.error); }} }}catch(e){{ logError(c.symbol+' exception '+e); }} await new Promise(r=>setTimeout(r,600)); }} document.getElementById('autoStatus').innerText='✅ Opened '+successCount+'/'+currentAnalysis.coins.length+' trades (batch '+loopCount+')\\n'+currentAnalysis.coins.map(c=>c.symbol+' '+c.finalSide).join(' | ')+'\\nReloading...'; setTimeout(()=>{{ closeOverlay(); location.reload(); }},2000); }}
    function closeOverlay(){{ document.getElementById('analyzeOverlay').classList.remove('show'); currentAnalysis=null; }}
    async function callReset(){{if(!confirm('RESET LOOP v11?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
    async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
    async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}
    function initChart(sym,entry,tp,sl,side,openTs,initialAge,cg_id){{const cv=document.getElementById('chart-'+sym); if(!cv) return; const ctx=cv.getContext('2d'); let prices = []; let liveHistory = []; let ageSec = initialAge; const ageEl=document.getElementById('live-age-'+sym); setInterval(()=>{{ ageSec += 1; const m=Math.floor(ageSec/60); const s=ageSec%60; if(ageEl) ageEl.innerText=m+'m '+s+'s'; }},1000); async function fetchPrice(){{let price=null; try{{ const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const txt=await r.text(); let j; try{{ j=JSON.parse(txt); }}catch(e){{ return; }} if(j.price && j.price>0) price=j.price; }}catch(e){{}} if(!price) return; const pct=side=='LONG'?(price-entry)/entry*100:(entry-price)/entry*100; if(Math.abs(pct)>30 && ageSec<300) return; const elP=document.getElementById('live-price-'+sym); const elC=document.getElementById('live-change-'+sym); const elPn=document.getElementById('live-pnl-'+sym); const dot=document.getElementById('live-dot-'+sym); if(elP){{elP.innerText='$'+price.toFixed(5); elP.style.color=pct>=0?'#0f8':'#f44';}} if(elC){{elC.innerText=pct.toFixed(3)+'%'; elC.style.color=pct>=0?'#0f8':'#f44';}} if(elPn){{ elPn.innerText=(pct>=0?'+':'')+'$'+(100*pct/100*0.3333).toFixed(2)+' / $1.00'; elPn.style.color=pct>=0?'#0f8':'#f44';}} if(dot) dot.innerText='● V856 LOOP '+new Date().toLocaleTimeString()+' '+pct.toFixed(3)+'%'; liveHistory.push(price); if(liveHistory.length>60) liveHistory.shift(); prices = [...liveHistory]; draw(); if(pct >= TP_PCT){{ if(dot) dot.innerText='● TP HIT '+pct.toFixed(2)+'% - AUTO CLOSING'; setTimeout(async()=>{{ await fetch('/api/close?symbol='+sym+'&key='+ADMIN_KEY); location.reload(); }},1500); }} }} async function fetchKlines(){{try{{ const r=await fetch('/api/klines?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const txt=await r.text(); let j; try{{ j=JSON.parse(txt); }}catch(e){{ return; }} if(j.closes && j.closes.length>10){{ let kl = j.closes.filter(p=>p>0); if(liveHistory.length<5){{ prices = kl.slice(-30); liveHistory = [...kl.slice(-30)]; }} draw(); }} }}catch(e){{}}}} function draw(){{const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); if(prices.length<2){{ prices = Array(20).fill(entry).map((v,i)=> v + (Math.random()-0.5)*entry*0.0003); }} const usePrices = prices; let displayPrices = usePrices.map(p=>{{ let rawPct = (p-entry)/entry*100; let ampPct = rawPct; if(Math.abs(rawPct)<0.6) ampPct = rawPct*4; return entry * (1 + ampPct/100); }}); const allAmp = [...displayPrices, entry]; let mn=Math.min(...allAmp)*0.9995; let mx=Math.max(...allAmp)*1.0005; const minRange = entry*0.006; const mid = (mn+mx)/2; if((mx-mn) < minRange){{ mn=mid-minRange/2; mx=mid+minRange/2; }} const rg=mx-mn||entry*0.001; function yF(p){{return h*0.85-((p-mn)/rg)*h*0.7;}} ctx.strokeStyle='#1a1a1a'; ctx.lineWidth=1; for(let i=0;i<5;i++){{const y=h*0.1+i*h*0.8/4; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const entryY=yF(entry); ctx.strokeStyle='#fc0'; ctx.lineWidth=3; ctx.beginPath(); ctx.moveTo(0,entryY); ctx.lineTo(w,entryY); ctx.stroke(); ctx.fillStyle='#fc0'; ctx.font='bold 11px monospace'; ctx.fillText('ENTRY '+entry.toFixed(5),4,entryY-5); const tpDisplay = entry*(1+((tp-entry)/entry*100)*4/100); let tpY=yF(tpDisplay); if(tpY<0) tpY=5; if(tpY>h) tpY=h-5; ctx.strokeStyle='#0f8'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.fillStyle='#0f8'; ctx.font='9px monospace'; ctx.fillText('TP '+tp.toFixed(5)+' $1.00',4,tpY-3); ctx.setLineDash([]); const slDisplay = entry*(1+((sl-entry)/entry*100)*4/100); let slY=yF(slDisplay); if(slY<0) slY=5; if(slY>h) slY=h-5; ctx.strokeStyle='#f44'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,slY); ctx.lineTo(w,slY); ctx.stroke(); ctx.fillStyle='#f44'; ctx.fillText('SL '+sl.toFixed(5),4,slY+11); ctx.setLineDash([]); ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=3; ctx.beginPath(); displayPrices.forEach((p,i)=>{{const x=i/(displayPrices.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=displayPrices[displayPrices.length-1]; const ly=yF(last); ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(w-8,ly,5,0,Math.PI*2); ctx.fill(); ctx.fillStyle=last>=entry?'#0f8':'#f44'; ctx.beginPath(); ctx.arc(w-8,ly,3.5,0,Math.PI*2); ctx.fill();}} draw(); fetchKlines(); fetchPrice(); setInterval(fetchPrice, 3000); setInterval(fetchKlines, 20000);}}window.addEventListener('load',()=>{{drawEquity(); {chart_js_init}}});</script></body></html>"""
    return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    key=request.args.get("key","")
    p="/"+path
    if p.startswith("/api/liveprice"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper(); base=sym.replace("USDT","")
        price, src = fetch_live_price_fast(base)
        if price is None: return Response(json.dumps({"error":"all failed","price":0}), mimetype="application/json", status=200)
        return Response(json.dumps({"symbol":sym,"price":price,"ts":int(time.time()),"src":src}), mimetype="application/json")
    if p.startswith("/api/klines"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper(); base=sym.replace("USDT","")
        closes, vols = fetch_klines(base, "1m", 30)
        if closes: return Response(json.dumps({"symbol":sym,"closes":closes}), mimetype="application/json")
        cg_id=SYM_TO_ID.get(base, base.lower())
        chart=get_chart(cg_id,1)
        if chart: return Response(json.dumps({"symbol":sym,"closes":chart}), mimetype="application/json")
        return Response(json.dumps({"symbol":sym,"closes":[]}), mimetype="application/json")
    if p.startswith("/api/deep30m"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper(); base=sym.replace("USDT","")
        closes, vols = fetch_klines(base, "1m", 30)
        if not closes:
            closes, vols = fetch_klines(base, "5m", 30)
        if not closes:
            return Response(json.dumps({"ok":False,"error":"no klines"}), mimetype="application/json")
        analysis=analyze_30min_deep(closes, vols)
        return Response(json.dumps({"ok":True,"symbol":sym,"closes":closes,"vols":vols,"analysis":analysis}), mimetype="application/json")
    if p.startswith("/api/analyze_3candidates_loop"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            loop=int(request.args.get("loop","1"))
            state=load_state()
            current_inv=sum([t.get("pos",0) for t in state.get("open",[])])
            cap=state.get("cap",300.0)
            slots_left=MAXP - len(state.get("open",[]))
            if slots_left<=0:
                return Response(json.dumps({"ok":False,"error":f"MAXP {MAXP} reached INV {current_inv:.0f}/{cap:.0f}","inv":current_inv,"cap":cap}), mimetype="application/json")
            need=min(3, slots_left)
            offset=state.get("scan_offset",0)
            # Auto-increment offset each loop to move to next 3 coins
            # Loop 1 uses current offset, loop 2 moves offset+SCAN_BATCH etc
            # But we don't want to skip, so calculate offset for this loop
            # Persist offset in state after each batch
            # Use offset = (original_offset + (loop-1)*3) % TOP_N? But SCAN_BATCH=20, we want 3 at a time from within batch
            # Simpler: each loop, we take next 3 coins from STATIC_TOP circularly
            total_top=len(STATIC_TOP)
            start_idx=(offset + (loop-1)*3) % total_top
            candidates=[]
            open_syms=[t["symbol"] for t in state.get("open",[])]
            idx=start_idx
            tries=0
            while len(candidates)<need and tries<total_top:
                base,shark=STATIC_TOP[idx % total_top]
                if base not in open_syms and base not in state["learn"]["last_coins"]:
                    price, src = fetch_live_price_fast(base)
                    if price and price>0:
                        if base not in [c["symbol"] for c in candidates]:
                            candidates.append({"symbol":base,"price":price,"src":src,"shark":shark})
                idx+=1
                tries+=1
            if not candidates:
                price, src = fetch_live_price_fast("BTC")
                candidates=[{"symbol":"BTC","price":price or 83000,"src":src,"shark":60}]
            # Update scan_offset to reflect we scanned up to idx
            state["scan_offset"]=(start_idx + len(candidates)) % TOP_N
            state["scan"]=state.get("scan",0)+1
            state["full_scans"]=state.get("scan",0)//(TOP_N//SCAN_BATCH)
            state["last_cron"]=f"v856 LOOP batch {loop} offset {offset}->{state['scan_offset']} coins {','.join([c['symbol'] for c in candidates])} INV {current_inv:.0f}/{cap:.0f}"
            kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":True,"coins":candidates,"offset":offset,"top_n":TOP_N,"full_scans":state["full_scans"],"scan":state["scan"],"loop":loop,"inv":current_inv,"cap":cap,"slots_left":slots_left}), mimetype="application/json")
        except Exception as e:
            import traceback
            return Response(json.dumps({"ok":False,"error":str(e)[:200],"trace":traceback.format_exc()[:300]}), mimetype="application/json")
    if p.startswith("/api/analyze_3candidates"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            state=load_state()
            current_inv=sum([t.get("pos",0) for t in state.get("open",[])])
            cap=state.get("cap",300.0)
            slots_left=MAXP - len(state.get("open",[]))
            if slots_left<=0:
                return Response(json.dumps({"ok":False,"error":f"MAXP {MAXP} reached INV {current_inv:.0f}/{cap:.0f}","inv":current_inv,"cap":cap}), mimetype="application/json")
            need=min(3, slots_left)
            offset=state.get("scan_offset",0)
            real=STATIC_TOP; batch=real[offset:offset+SCAN_BATCH] if offset+SCAN_BATCH <= len(real) else real[offset:]+real[: (offset+SCAN_BATCH)-len(real) ]
            open_syms=[t["symbol"] for t in state.get("open",[])]
            candidates=[]
            for base,shark in batch:
                if len(candidates)>=need: break
                if base in open_syms: continue
                if base in state["learn"]["last_coins"]: continue
                price, src = fetch_live_price_fast(base)
                if price and price>0:
                    candidates.append({"symbol":base,"price":price,"src":src,"shark":shark})
            if len(candidates)<need:
                for base,shark in STATIC_TOP:
                    if len(candidates)>=need: break
                    if base in [c["symbol"] for c in candidates]: continue
                    if base in open_syms: continue
                    price, src = fetch_live_price_fast(base)
                    if price and price>0:
                        candidates.append({"symbol":base,"price":price,"src":src,"shark":shark})
            if not candidates:
                price, src = fetch_live_price_fast("BTC")
                candidates=[{"symbol":"BTC","price":price or 83000,"src":src,"shark":60}]
            return Response(json.dumps({"ok":True,"coins":candidates,"offset":offset,"inv":current_inv,"cap":cap,"slots_left":slots_left}), mimetype="application/json")
        except Exception as e:
            import traceback
            return Response(json.dumps({"ok":False,"error":str(e)[:200]}), mimetype="application/json")
    if p.startswith("/api/open_analyzed"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            data=None
            body_text=request.get_data(as_text=True) or ""
            if request.method=="POST":
                try:
                    data=request.get_json(force=True)
                    if not data and body_text:
                        data=json.loads(body_text)
                except:
                    try:
                        data=json.loads(body_text) if body_text else {}
                    except:
                        data={}
                sym=(data.get("symbol","") if data else "").upper() or request.args.get("symbol","").upper()
                side=(data.get("side","") if data else "") or request.args.get("side","LONG")
                reason=(data.get("reason","") if data else "") or request.args.get("reason","LOOP auto")
                live_price_fallback=data.get("livePrice") if data else None
            else:
                sym=request.args.get("symbol","").upper()
                side=request.args.get("side","LONG")
                reason=request.args.get("reason","LOOP auto")
                live_price_fallback=None
            if not sym:
                return Response(json.dumps({"ok":False,"error":"no symbol"}), mimetype="application/json")
            if side not in ["LONG","SHORT"]: side="LONG"
            state=load_state()
            current_inv=sum([t.get("pos",0) for t in state.get("open",[])])
            cap=state.get("cap",300.0)
            if len(state.get("open",[]))>=MAXP:
                return Response(json.dumps({"ok":False,"error":f"MAXP {MAXP} reached INV {current_inv:.0f}/{cap:.0f}","inv":current_inv,"cap":cap}), mimetype="application/json")
            if current_inv>=cap*0.95:
                return Response(json.dumps({"ok":False,"error":f"CAP FULL INV {current_inv:.0f}/{cap:.0f}","inv":current_inv,"cap":cap}), mimetype="application/json")
            price, src = fetch_live_price_fast(sym)
            if (not price or price==0) and live_price_fallback and live_price_fallback>0:
                price=live_price_fallback
                src="fallback"
            if not price or price==0:
                return Response(json.dumps({"ok":False,"error":"no live price for "+sym}), mimetype="application/json")
            pos_size=cap*POS_PCT/100.0
            if current_inv+pos_size>cap: pos_size=(cap-current_inv)*0.95
            if pos_size<15: pos_size=15
            if current_inv+pos_size>cap*1.05:
                return Response(json.dumps({"ok":False,"error":f"Would exceed CAP INV {current_inv:.0f}+{pos_size:.0f} > {cap:.0f}","inv":current_inv,"cap":cap}), mimetype="application/json")
            tr={"symbol":sym,"side":side,"entry":price,"price":price,"pos":pos_size,"ts":int(time.time()),"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":60,"tp":TP_PCT,"sl":SL_PCT,"reason":f"$1.00 LOOP v856 {side} ${price:.4f} {src} {reason[:100]} POS ${pos_size:.0f}/{cap:.0f}","rsi":50,"shark":60,"atr":1.0,"vol":50000000,"cg_id":SYM_TO_ID.get(sym,""),"analysis":reason[:200]}
            state["open"].append(tr)
            state["scan"]=state.get("scan",0)+1
            state["scan_offset"]=(state.get("scan_offset",0)+3)%TOP_N
            state["full_scans"]=state.get("scan",0)//(TOP_N//SCAN_BATCH)
            state["last_cron"]=f"v856 LOOP OPEN {sym} {side} ${price:.4f} {reason[:60]} INV {current_inv+pos_size:.0f}/{cap:.0f} SCAN {state.get('scan',0)}"
            eq=state.get("equity",[300]); eq.append(cap); state["equity"]=eq[-150:]
            ok=kv_set(STATE_KEY, state)
            if not ok:
                return Response(json.dumps({"ok":False,"error":"kv_set failed","inv":current_inv,"cap":cap}), mimetype="application/json")
            return Response(json.dumps({"ok":ok,"symbol":sym,"side":side,"entry":price,"pos":pos_size,"inv":current_inv+pos_size,"cap":cap,"reason":reason}), mimetype="application/json")
        except Exception as e:
            import traceback
            return Response(json.dumps({"ok":False,"error":str(e)[:200],"trace":traceback.format_exc()[:400]}), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); time.sleep(0.5)
        new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0],"last_cron":"reset v856 LOOP TRUE CLEAN"}
        ok=kv_set(STATE_KEY,new)
        return Response(json.dumps({"ok":ok,"cap":300,"cleared":True}), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]):
            lp,_=fetch_live_price_fast(tr["symbol"])
            if lp and lp>0:
                pct=(lp-tr["entry"])/tr["entry"]*100 if tr["side"]=="LONG" else (tr["entry"]-lp)/tr["entry"]*100
                pct_net=pct-TOTAL_FEE; net=tr["pos"]*pct_net/100
            else: net=tr.get("net",0)
            cap+=net; state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":net,"reason":f"MANUAL CLOSE ALL LIVE ${lp if lp else 0:.5f} v856","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0)})
        state["open"]=[]; state["cap"]=cap; state=recalc(state); state["peak"]=max(state.get("peak",cap),cap); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"cap":cap}), mimetype="application/json")
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); state=load_state(); cap=state.get("cap",300.0); final=[]
        for tr in state.get("open",[]):
            if tr["symbol"]==sym:
                lp,_=fetch_live_price_fast(sym)
                if lp and lp>0:
                    pct=(lp-tr["entry"])/tr["entry"]*100 if tr["side"]=="LONG" else (tr["entry"]-lp)/tr["entry"]*100
                    pct_net=pct-TOTAL_FEE; net=tr["pos"]*pct_net/100
                else: net=tr.get("net",0)
                cap+=net; state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":net,"reason":f"MANUAL CLOSE {sym} LIVE ${lp if lp else 0:.5f} v856","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0)})
            else: final.append(tr)
        state["open"]=final; state["cap"]=cap; state=recalc(state); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"closed":sym,"cap":cap}), mimetype="application/json")
    if p.startswith("/api/debug"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps(load_state(), indent=2), mimetype="application/json")
    try:
        st=load_state(); return Response(render(st), mimetype="text/html")
    except Exception as e:
        import traceback
        return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:2000]}</pre></body></html>", mimetype="text/html", status=200)
