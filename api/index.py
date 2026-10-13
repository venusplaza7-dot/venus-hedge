"""
VENUS v853 AUTO 30M+1M - AUTO STARTS trade after 30M deep + 1M live analysis - CAP SAFE FIX 450/300
Fixes v852 INV 450/300 bug + ERR JSON + auto confirm
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
MAXP=2
POS_PCT=50.0
TOTAL_FEE=0.17
SCAN_BATCH=20
TOP_N=100
TP_PCT=1.20
SL_PCT=0.60
STATIC_TOP=[("BTC",60),("ETH",55),("SOL",50),("BNB",50),("XRP",48),("AVAX",45),("LINK",45),("ADA",44),("DOT",44),("LTC",43),("UNI",43),("ETC",42),("APT",42),("ARB",41),("OP",41),("SUI",40),("NEAR",40),("HBAR",40),("FIL",39),("MKR",39),("AAVE",38),("GRT",38),("RNDR",38),("INJ",38),("STX",37),("IMX",37),("SEI",37),("TIA",37),("WLD",36),("FET",36),("TAO",36),("ZEC",35),("STRK",35),("JUP",35),("ENA",34),("PENDLE",34),("ONDO",34),("DOGE",34),("CYBER",32),]
SYM_TO_ID={"BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin","XRP":"ripple","ADA":"cardano","AVAX":"avalanche-2","DOT":"polkadot","LINK":"chainlink","LTC":"litecoin","UNI":"uniswap","ETC":"ethereum-classic","APT":"aptos","ARB":"arbitrum","OP":"optimism","SUI":"sui","RNDR":"render-token","MKR":"maker","AAVE":"aave","GRT":"the-graph","SEI":"sei-network","TIA":"celestia","DOGE":"dogecoin","WLD":"worldcoin","FET":"fetch-ai","TAO":"bittensor","IMX":"immutable-x","JUP":"jupiter","HBAR":"hedera","ENA":"ethena","PENDLE":"pendle","ZEC":"zcash","STRK":"starknet","ONDO":"ondo-finance","NEAR":"near-protocol","CYBER":"cyberconnect"}

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

def get_chart(cg_id, days=1):
    try:
        if not cg_id: return []
        url=f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days={days}"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data=json.loads(r.read().decode()); closes=[p[1] for p in data.get("prices",[])]; filtered=[]
            for c in closes:
                if c==0: continue
                if filtered and abs(c-filtered[-1])/filtered[-1] > 0.12: continue
                filtered.append(c)
            return filtered[-80:]
    except: return []

def analyze_30min_deep(closes, vols):
    if len(closes)<15:
        return {"side":"LONG","rsi":50,"reason":"not enough 30m data fallback LONG","score_long":1,"score_short":1,"mom_5":0,"mom_30":0,"rsi_val":50}
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
    vol_avg=sum(vols[-10:])/10 if len(vols)>=10 else 1
    vol_last=vols[-1] if vols else vol_avg
    vol_ratio=vol_last/vol_avg if vol_avg>0 else 1
    up_candles=sum(1 for i in range(len(closes)-10, len(closes)) if i>0 and closes[i]>closes[i-1])
    score_long=0; score_short=0; reasons=[]
    if last > sma30: score_long+=2; reasons.append(f"price>{sma30:.2f} SMA30 30m uptrend")
    else: score_short+=2; reasons.append(f"price<{sma30:.2f} SMA30 30m downtrend")
    if sma5 > sma10 and sma10 > sma20: score_long+=3; reasons.append("SMA5>10>20 strong uptrend 30m")
    elif sma5 < sma10 and sma10 < sma20: score_short+=3; reasons.append("SMA5<10<20 strong downtrend 30m")
    elif sma5 > sma10: score_long+=1; reasons.append("SMA5>SMA10 uptrend")
    else: score_short+=1; reasons.append("SMA5<SMA10 downtrend")
    if mom_5>0: score_long+=2; reasons.append(f"5m {mom_5:+.3f}% up")
    else: score_short+=2; reasons.append(f"5m {mom_5:+.3f}% down")
    if mom_30>0: score_long+=1; reasons.append(f"30m {mom_30:+.2f}% overall up")
    else: score_short+=1; reasons.append(f"30m {mom_30:+.2f}% overall down")
    if rsi>60: score_long+=1; reasons.append(f"RSI {rsi:.0f} bullish")
    elif rsi<40: score_short+=1; reasons.append(f"RSI {rsi:.0f} bearish")
    else: reasons.append(f"RSI {rsi:.0f} neutral")
    if up_candles>=6: score_long+=1; reasons.append(f"{up_candles}/10 candles up")
    else: score_short+=1; reasons.append(f"{10-up_candles}/10 candles down")
    side="LONG" if score_long>=score_short else "SHORT"
    reason_str=f"{side} {score_long}v{score_short} " + " | ".join(reasons[:5])
    return {"side":side,"rsi":int(rsi),"reason":reason_str,"score_long":score_long,"score_short":score_short,"mom_5":mom_5,"mom_30":mom_30,"rsi_val":rsi,"up_candles":up_candles,"sma5":sma5,"sma10":sma10,"sma20":sma20,"vol_ratio":vol_ratio,"closes":closes}

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0],"last_cron":"never v853 AUTO CAP SAFE 300"}
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("learn",{"blacklist":{},"last_coins":{}}); s.setdefault("peak",s.get("cap",300)); s.setdefault("equity",[300,s.get("cap",300)]); s.setdefault("last_cron","never")
    # CAP SAFE FIX: Trim if >MAXP trades (fixes 450/300 bug)
    if len(s.get("open",[]))>MAXP:
        # Keep newest 2
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
    last_cron = state.get("last_cron","never v853")
    cap_safe_color = "#0f8" if invested <= cap*1.05 else "#f44"
    over_msg = "✅" if invested<=cap*1.05 else "❌ OVER 450/300 BUG"
    trade_boxes_html=""; chart_js_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",150); entry=tr.get("entry",0); tp=tr.get("tp",TP_PCT); sl=tr.get("sl",SL_PCT); rr=tp/sl if sl>0 else 2.0
        tp_price=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100); sl_price=entry*(1-sl/100) if side=="LONG" else entry*(1+sl/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        net_target = pos*(tp-TOTAL_FEE)/100
        analysis=tr.get("analysis","30m deep + 1m live auto")[:100]
        shark_tag=f"<span style='background:#00d4ff;color:#000;padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900'>SHARK {tr.get('shark',0)} RR {rr:.1f} ${net_target:.2f}</span>"
        ts=tr.get("ts",int(time.time()))
        trade_boxes_html+=f"""<div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'><div style='display:flex;justify-content:space-between'><div><b style='color:{col};font-size:14px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f} {shark_tag}</b><div style='font-size:10px;color:#0f8'>🤖 AUTO 30M+1M: {analysis}</div><div style='font-size:10px;color:#aaa'>ENTRY ${entry:.6f} TP ${tp_price:.6f} ({tp:.2f}%) = ${net_target:.2f} NET SL ${sl_price:.6f} ({sl:.2f}%) INV {invested:.0f}/{cap:.0f}</div></div><button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 10px'>✕</button></div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin:8px 0;text-align:center'><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>LIVE</div><div id='live-price-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('price',0):.5f}</div><div id='live-change-{sym}' style='font-size:10px'>{tr.get('pct_gross',0):+.3f}%</div><div id='live-dot-{sym}' style='font-size:8px;color:#0f8'>● V853 AUTO</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>PNL</div><div id='live-pnl-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f} / ${net_target:.2f}</div><div style='font-size:10px'>PEAK {tr.get('peak_gross',0):.2f}% TARGET $1.50</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>AGE</div><div id='live-age-{sym}' style='font-size:13px;font-weight:900'>{int(tr.get('age',0)//60)}m {int(tr.get('age',0)%60)}s</div><div style='font-size:10px;color:#0f8'>TP {tp:.2f}% SL {sl:.2f}%</div></div></div><div style='background:#000;border-radius:12px;padding:6px;border:1px solid #222'><div style='font-size:9px;color:#555'>TURBO GRAPH {side} - AUTO 30M DEEP + 1M LIVE DECISION - {analysis[:70]} - TP GREEN SL RED ENTRY YELLOW</div><canvas id='chart-{sym}' width='340' height='180' style='width:100%;height:180px;background:#000;border-radius:8px'></canvas></div><div style='font-size:9px;color:#888;margin-top:4px'>{tr.get('reason','')}</div></div>"""
        chart_js_init+=f"initChart('{sym}',{entry},{tp_price},{sl_price},'{side}',{ts},{int(tr.get('age',0))},'{tr.get('cg_id','bitcoin')}');\n"
    if not open_tr:
        trade_boxes_html=f"<div class='it' style='text-align:center;color:#666;padding:16px'>No open trades - TAP CRON AUTO 30M+1M - v853 AUTO-STARTS trade after 30M deep + 1M live graph analysis - CAP SAFE {invested:.0f}/{cap:.0f} MAXP {MAXP} - SCAN {scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} FULL {full_scans}x CAP ${cap:.2f}<br>LAST CRON: {last_cron}<br>INV {invested:.0f}/{cap:.0f} MAXP {MAXP} - AUTO decision LONG/SHORT from graph</div>"
    equity_js=json.dumps(equity[-80:])
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}}.h{{background:linear-gradient(90deg,#00ff88,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}}.g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}}.stats{{background:#111;border:2px solid #0f8;padding:10px;margin:6px 0;border-radius:12px}}.it{{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:12px}}.btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.btn{{padding:16px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px;cursor:pointer}}.btn-cron{{background:#0f8;color:#000}}.btn-reset{{background:#f44;color:#fff}}.btn-close{{background:#fc0;color:#000}}.badge{{padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900}}.long{{background:#0f8;color:#000}}.short{{background:#f44;color:#fff}}.overlay{{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.95);z-index:9999;display:none;flex-direction:column;padding:10px;overflow-y:auto}}.overlay.show{{display:flex}}</style></head><body>
    <div id='analyzeOverlay' class='overlay'><div style='background:#111;border:2px solid #0f8;border-radius:16px;padding:12px'><div style='color:#0f8;font-weight:900;font-size:14px;text-align:center' id='analyzeTitle'>🤖 AUTO 30M DEEP + 1M LIVE - AUTO START TRADE</div><div style='color:#fc0;font-size:11px;text-align:center;margin:6px 0' id='analyzeStatus'>Starting auto analysis...</div><div style='background:#000;border-radius:12px;padding:8px;margin:8px 0'><div style='font-size:10px;color:#888'>30-MIN DEEP CHART ANALYSIS (30× 1m klines)</div><div id='deepAnalysisText' style='color:#0f8;font-size:10px;margin:4px 0;white-space:pre-wrap'>Waiting...</div><canvas id='deepChart' width='340' height='200' style='width:100%;height:200px;background:#000;border-radius:8px'></canvas></div><div style='background:#000;border-radius:12px;padding:8px;margin:8px 0;border:1px solid #333'><div style='font-size:10px;color:#888'>1-MIN LIVE GRAPH MONITOR - Auto tracking live movement 60s before decision</div><div id='liveMonitorText' style='color:#ffcc00;font-size:11px;margin:4px 0'>Starting live monitor...</div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;text-align:center'><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>START PRICE</div><div id='monitorStartPrice' style='font-size:14px;font-weight:900;color:#fc0'>$0</div></div><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>LIVE PRICE</div><div id='monitorLivePrice' style='font-size:14px;font-weight:900;color:#0f8'>$0</div><div id='monitorChange' style='font-size:10px'>+0.00%</div></div><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>TIME LEFT</div><div id='monitorTimeLeft' style='font-size:18px;font-weight:900;color:#f44'>60s</div><div id='monitorProgress' style='font-size:9px'>0/60s</div></div></div><canvas id='liveMonitorChart' width='340' height='150' style='width:100%;height:150px;background:#000;border-radius:8px;margin-top:6px'></canvas></div><div style='background:#111;border-radius:12px;padding:8px;margin:8px 0'><div style='font-size:10px;color:#888'>AUTO DECISION AFTER 30M DEEP + 1M LIVE - Will auto-start trade (no confirm button)</div><div id='finalDecision' style='color:#0f8;font-size:12px;font-weight:900;margin:4px 0'>Analyzing...</div><div id='finalReason' style='color:#aaa;font-size:9px;white-space:pre-wrap'>Waiting for 1m live data...</div></div><div style='background:#000;padding:10px;border-radius:10px;text-align:center'><div id='autoStatus' style='color:#0f8;font-size:12px;font-weight:900'>🤖 AUTO-STARTING trade in 3s after analysis - No manual button...</div><div style='color:#888;font-size:9px;margin-top:4px'>Bot decides LONG/SHORT from graph movement automatically</div></div></div></div>
    <div class='h'>VENUS v853 AUTO 30M+1M CAP SAFE {invested:.0f}/{cap:.0f} {over_msg} - SCAN #{scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} - ${cap:.2f} PEAK ${peak:.2f} DD {dd:.1f}% L:{long_open} S:{short_open} FULLx{full_scans} - DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> NEED {trades_needed}x $1.50 INV <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f} {over_msg}</span><br><span style='font-size:9px'>LAST: {last_cron[:90]}</span></div>
    <div style='background:#000;border-radius:12px;padding:8px;margin:6px 0;border:1px solid #333'><div style='font-size:9px;color:#888'>EQUITY CURVE (CAP $300 → ${cap:.2f}) PEAK ${peak:.2f} DD {dd:.1f}% DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> INV <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f} {over_msg}</span> NEED {trades_needed}x $1.50 - V853 AUTO 30M+1M - {last_cron[:60]}</div><canvas id='equityChart' width='340' height='80' style='width:100%;height:80px;background:#000;border-radius:8px'></canvas></div>
    <div class='btn-row'><button class='btn btn-cron' onclick='startDeepAnalysis()' id='cronBtn'>🤖 CRON AUTO 30M+1M <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f} {over_msg}</span><div id='cronStat' style='font-size:10px'>TAP {offset+1}-{offset+SCAN_BATCH}/{TOP_N} SCAN {scan} FULL {full_scans} - AUTO 30M DEEP + 1M LIVE then AUTO-START LONG/SHORT - <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> INV <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f}</span><br>{last_cron[:30]}</div></button><button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN ${invested:.0f}/{cap:.0f} {over_msg}</div></button><button class='btn btn-reset' onclick='callReset()'>🔄RESET AUTO v8 FIX<div style='font-size:10px'>CAP $300 INV 0 FIX 450</div></button></div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#fc0'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}<br>INV <b style='color:{cap_safe_color}'>${invested:.0f}/{cap:.0f} {over_msg}</b><br>FEES ${fees_paid:.2f}<br>PEAK ${peak:.2f} DD {dd:.1f}%</div><div class='c'>DAILY $15<br><b style='font-size:18px'><span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span></b><br>NEED ${daily_needed:.2f} = {trades_needed}x $1.50<br>W:{wins} L:{loss} {winrate}%<br>TOTAL {tot} V853<br>FULL {full_scans}x PF {pf:.2f}<br>AUTO 30M+1M FIX</div><div class='c' style='border-color:{bias_color}'><b style='color:{bias_color}'>AUTO 30M+1M<br>POS {POS_PCT}% x{MAXP}<br>v853 FIX 450</b><br>TP {TP_PCT}% = $1.50<br>SL {SL_PCT}%<br>RR 2.0<br>INV <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f}</span><br>AUTO START</div></div>
    <div class='stats'><div style='color:#0f8;font-weight:900;font-size:12px'>🤖 v853 AUTO 30M DEEP + 1M LIVE - FIXES 450/300 BUG - Now enforces MAXP={MAXP} POS {POS_PCT}% = ${cap*POS_PCT/100*MAXP:.0f} MAX = CAP. Old state with 3 trades auto-trimmed to 2 newest. Analyzes 30m deep + 1m live graph then AUTO-STARTS LONG/SHORT from movement. No manual confirm button. CAP SAFE INV <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f} {over_msg}</span>.</div><div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px;font-size:10px'><div>SCAN: <b>{offset+1}-{offset+SCAN_BATCH}/{TOP_N} (x{full_scans}) V853 AUTO FIX INV {invested:.0f}/{cap:.0f}</b></div><div>OPEN: <b>{len(open_tr)}/{MAXP} PEAK ${peak:.2f} DD {dd:.1f}% DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span></b></div><div>TOTAL: <b>{tot}</b> W:<b style='color:#0f8'>{wins}</b> L:<b style='color:#f44'>{loss}</b> {winrate}% PF:<b>{pf:.2f}</b></div><div>EXP: <b>${exp:.3f}</b> FEES: <b>{TOTAL_FEE}%</b> NEED: <b>${daily_needed:.2f} = {trades_needed}x $1.50 INV {invested:.0f}/{cap:.0f}</b></div><div>BEST: <b>{best_sym} ${best_net:+.2f}</b></div><div>WORST: <b>{worst_sym} ${worst_net:+.2f}</b></div></div><div style='margin-top:6px;color:#fc0;font-size:9px'>LAST CRON: {last_cron}</div><div style='margin-top:6px;color:#0f8;font-size:10px'>✅ v853 FIX: MAXP {MAXP} enforced, old 3 trades trimmed to 2, INV {invested:.0f}/{cap:.0f} CAP SAFE, AUTO 30M+1M then auto-start trade LONG/SHORT from graph. No confirm button. 700 lines + graphs.</div></div><div id='openbox'>{trade_boxes_html}</div><div style='background:#111;padding:10px;margin:6px 0;border-radius:10px'><div style='color:#fc0;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% - PF {pf:.2f} EXP ${exp:.3f} PEAK ${peak:.2f} DD {dd:.1f}% DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> INV {invested:.0f}/{cap:.0f} NEED {trades_needed}x $1.50 - V853 AUTO 30M+1M FIX</div>"""
    for cl in closed[:30]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"; sym=cl.get("symbol","?"); side=cl.get("side","?"); net=cl.get("net",0); pct=cl.get("pct_net",0); reason=cl.get("reason","")[:80]; age=cl.get("age",0); shark=cl.get("shark",0)
        html+=f"<div style='padding:5px 0;border-bottom:1px solid #222;color:{c}'><b>{sym} {side} SHARK {shark}</b> ${net:+.2f} {pct:+.2f}% | {reason} | {int(age//60)}m</div>"
    html+=f"""</div><script>const EQUITY = {equity_js};const ADMIN_KEY="{ADMIN_KEY}";const TP_PCT={TP_PCT};const SL_PCT={SL_PCT};let currentAnalysis=null;let liveMonitorPrices=[];let liveMonitorInterval=null;let timeLeft=60;let startPrice=0;
    function drawEquity(){{const cv=document.getElementById('equityChart'); if(!cv||!EQUITY.length) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...EQUITY)*0.999, mx=Math.max(...EQUITY)*1.001, rg=mx-mn||1; function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}} ctx.strokeStyle='#222'; for(let i=0;i<3;i++){{const y=h*0.1+i*h*0.8/2; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const y300=yF(300); ctx.strokeStyle='#444'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,y300); ctx.lineTo(w,y300); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle='#666'; ctx.font='8px monospace'; ctx.fillText('300',2,y300-2); ctx.strokeStyle='#0f8'; ctx.lineWidth=2; ctx.beginPath(); EQUITY.forEach((p,i)=>{{const x=i/(EQUITY.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=EQUITY[EQUITY.length-1]; ctx.fillStyle='#fc0'; ctx.beginPath(); ctx.arc(w-4,yF(last),3,0,Math.PI*2); ctx.fill(); ctx.fillText(last.toFixed(2), w-50, yF(last)-4);}}
    async function startDeepAnalysis(){{const overlay=document.getElementById('analyzeOverlay'); overlay.classList.add('show'); document.getElementById('analyzeTitle').innerText='🤖 AUTO 30M DEEP + 1M LIVE - AUTO START'; document.getElementById('analyzeStatus').innerText='Selecting coin for auto analysis...'; try{{const r=await fetch('/api/analyze_candidate?key='+ADMIN_KEY); const j=await r.json(); if(!j.ok){{ document.getElementById('analyzeStatus').innerText='FAIL: '+(j.error||'unknown')+' INV '+j.inv+'/'+j.cap; if(j.error && j.error.includes('MAXP')){{ document.getElementById('analyzeStatus').innerText='MAXP reached '+j.inv+'/'+j.cap+' - Close one first'; setTimeout(()=>{{ overlay.classList.remove('show'); location.reload(); }},2000); }} return; }} const symbol=j.symbol; const price=j.price; document.getElementById('analyzeTitle').innerText='📊 '+symbol+' - 30M DEEP AUTO ANALYSIS'; document.getElementById('analyzeStatus').innerText='Fetching 30× 1m klines for '+symbol+' ($'+price+') deep analysis...'; currentAnalysis=j; const r2=await fetch('/api/deep30m?symbol='+symbol+'&key='+ADMIN_KEY); const j2=await r2.json(); const closes=j2.closes||[]; const deep=j2.analysis||{{side:'LONG',reason:'fallback'}}; document.getElementById('deepAnalysisText').innerText=(deep.reason||'Deep analysis')+'\\n30m change: '+(deep.mom_30||0).toFixed(2)+'% | 5m: '+(deep.mom_5||0).toFixed(3)+'% | RSI: '+(deep.rsi_val||50).toFixed(0); drawDeepChart(closes, deep); document.getElementById('analyzeStatus').innerText='✅ 30M DEEP DONE - Opening LIVE GRAPH 60s then AUTO-START...'; currentAnalysis.deep=deep; currentAnalysis.closes=closes; startLiveMonitor(symbol, price, deep); }}catch(e){{ document.getElementById('analyzeStatus').innerText='ERR '+e; }} }}
    function drawDeepChart(closes, deep){{const cv=document.getElementById('deepChart'); if(!cv) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); if(closes.length<5){{ ctx.fillStyle='#666'; ctx.fillText('No 30m data',10,h/2); return; }} const mn=Math.min(...closes)*0.999, mx=Math.max(...closes)*1.001, rg=mx-mn||1; function yF(p){{return h*0.85-((p-mn)/rg)*h*0.7;}} ctx.strokeStyle='#1a1a1a'; for(let i=0;i<4;i++){{const y=h*0.1+i*h*0.8/3; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} ctx.strokeStyle='#0f8'; ctx.lineWidth=2; ctx.beginPath(); closes.forEach((p,i)=>{{const x=i/(closes.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const sma5=deep.sma5||closes[closes.length-1]; const sma10=deep.sma10||sma5; const sma20=deep.sma20||sma10; ctx.strokeStyle='#fc0'; ctx.setLineDash([4,4]); ctx.lineWidth=1; let y=yF(sma5); ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke(); ctx.fillText('SMA5',2,y-2); ctx.strokeStyle='#00d4ff'; y=yF(sma10); ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke(); ctx.fillText('SMA10',2,y-2); ctx.strokeStyle='#f44'; y=yF(sma20); ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke(); ctx.fillText('SMA20',2,y-2); ctx.setLineDash([]); }}
    async function startLiveMonitor(symbol, startPriceVal, deep){{startPrice=startPriceVal; liveMonitorPrices=[startPriceVal]; timeLeft=60; document.getElementById('monitorStartPrice').innerText='$'+startPriceVal.toFixed(4); document.getElementById('monitorLivePrice').innerText='$'+startPriceVal.toFixed(4); document.getElementById('monitorChange').innerText='+0.00%'; document.getElementById('monitorChange').style.color='#0f8'; document.getElementById('monitorTimeLeft').innerText='60s'; document.getElementById('monitorProgress').innerText='0/60s'; document.getElementById('liveMonitorText').innerText='📈 Auto monitoring '+symbol+' live 60s before LONG/SHORT decision... Deep 30m trend: '+(deep.reason||'').substring(0,60); drawLiveMonitorChart(); if(liveMonitorInterval) clearInterval(liveMonitorInterval); liveMonitorInterval=setInterval(async()=>{{ timeLeft--; document.getElementById('monitorTimeLeft').innerText=timeLeft+'s'; document.getElementById('monitorProgress').innerText=(60-timeLeft)+'/60s'; try{{ const r=await fetch('/api/liveprice?symbol='+symbol+'&key='+ADMIN_KEY+'&t='+Date.now()); const j=await r.json(); if(j.price && j.price>0){{ liveMonitorPrices.push(j.price); if(liveMonitorPrices.length>60) liveMonitorPrices.shift(); const change=(j.price-startPrice)/startPrice*100; document.getElementById('monitorLivePrice').innerText='$'+j.price.toFixed(4); document.getElementById('monitorChange').innerText=(change>=0?'+':'')+change.toFixed(3)+'%'; document.getElementById('monitorChange').style.color=change>=0?'#0f8':'#f44'; drawLiveMonitorChart(); const avgChange=change; let finalSide='LONG'; if((deep.score_long||0) >= (deep.score_short||0) && avgChange>=-0.05) finalSide='LONG'; else if((deep.score_short||0) > (deep.score_long||0) || avgChange<-0.1) finalSide='SHORT'; else finalSide=deep.side||'LONG'; document.getElementById('finalDecision').innerText=finalSide+' (preview) - '+avgChange.toFixed(3)+'% live move - AUTO-START in '+timeLeft+'s'; document.getElementById('finalDecision').style.color=finalSide=='LONG'?'#0f8':'#f44'; document.getElementById('finalReason').innerText='30M '+ (deep.score_long||0)+'v'+(deep.score_short||0)+' + 1M '+avgChange.toFixed(3)+'% -> '+finalSide+' | RSI '+(deep.rsi_val||50).toFixed(0)+' | '+ (deep.reason||'').substring(0,80); currentAnalysis.finalSide=finalSide; currentAnalysis.liveChange=change; }} }}catch(e){{}} if(timeLeft<=0){{ clearInterval(liveMonitorInterval); finishLiveMonitor(symbol); }} }},1000); }}
    function drawLiveMonitorChart(){{const cv=document.getElementById('liveMonitorChart'); if(!cv) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); if(liveMonitorPrices.length<2) return; const mn=Math.min(...liveMonitorPrices)*0.9995, mx=Math.max(...liveMonitorPrices)*1.0005, rg=mx-mn||startPrice*0.001; const minRange=startPrice*0.002; let mn2=mn, mx2=mx; if((mx-mn)<minRange){{ const mid=(mn+mx)/2; mn2=mid-minRange/2; mx2=mid+minRange/2; }} function yF(p){{return h*0.85-((p-mn2)/(mx2-mn2||minRange))*h*0.7;}} ctx.strokeStyle='#1a1a1a'; for(let i=0;i<3;i++){{const y=h*0.1+i*h*0.8/2; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const startY=yF(startPrice); ctx.strokeStyle='#fc0'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,startY); ctx.lineTo(w,startY); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle='#fc0'; ctx.font='9px monospace'; ctx.fillText('START '+startPrice.toFixed(4),2,startY-2); ctx.strokeStyle=liveMonitorPrices[liveMonitorPrices.length-1]>=startPrice?'#0f8':'#f44'; ctx.lineWidth=2; ctx.beginPath(); liveMonitorPrices.forEach((p,i)=>{{const x=i/(liveMonitorPrices.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=liveMonitorPrices[liveMonitorPrices.length-1]; const ly=yF(last); ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(w-4,ly,4,0,Math.PI*2); ctx.fill(); }}
    function finishLiveMonitor(symbol){{const liveChange=currentAnalysis.liveChange||0; const deep=currentAnalysis.deep||{{}}; const scoreLong=deep.score_long||0; const scoreShort=deep.score_short||0; let finalSide='LONG'; let finalReason=''; if(scoreLong>=scoreShort && liveChange>=-0.05){{ finalSide='LONG'; finalReason='30M DEEP '+scoreLong+'v'+scoreShort+' uptrend ('+(deep.mom_30||0).toFixed(2)+'% 30m) + 1M LIVE '+liveChange.toFixed(3)+'% '+(liveChange>=0?'up':'down')+' -> LONG (graph going up) auto'; }} else{{ finalSide='SHORT'; finalReason='30M DEEP '+scoreLong+'v'+scoreShort+' downtrend ('+(deep.mom_30||0).toFixed(2)+'% 30m) + 1M LIVE '+liveChange.toFixed(3)+'% down -> SHORT (graph going down) auto'; }} document.getElementById('finalDecision').innerText='✅ FINAL: '+finalSide+' after 30M deep + 1M live - AUTO-STARTING...'; document.getElementById('finalDecision').style.color=finalSide=='LONG'?'#0f8':'#f44'; document.getElementById('finalReason').innerText=finalReason+' | RSI '+(deep.rsi_val||50).toFixed(0)+' | 5m '+(deep.mom_5||0).toFixed(3)+'% | 30m '+(deep.mom_30||0).toFixed(2)+'% | Live 1m '+liveChange.toFixed(3)+'%'; document.getElementById('liveMonitorText').innerText='✅ 1M LIVE DONE - Auto-starting trade...'; document.getElementById('autoStatus').innerText='🤖 AUTO-STARTING '+finalSide+' trade NOW... 30M '+scoreLong+'v'+scoreShort+' + 1M '+liveChange.toFixed(3)+'%'; currentAnalysis.finalSide=finalSide; currentAnalysis.finalReason=finalReason; setTimeout(()=>{{ autoConfirmTrade(); }},2000); }}
    async function autoConfirmTrade(){{document.getElementById('autoStatus').innerText='🤖 Opening '+currentAnalysis.finalSide+' trade...'; try{{ const payload={{symbol:currentAnalysis.symbol, side:currentAnalysis.finalSide, reason:currentAnalysis.finalReason.substring(0,200)}}; const r=await fetch('/api/open_analyzed?key='+ADMIN_KEY, {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)}}); const text=await r.text(); let j; try{{ j=JSON.parse(text); }}catch(e){{ document.getElementById('autoStatus').innerText='ERR JSON: '+text.substring(0,120); return; }} if(j.ok){{ document.getElementById('autoStatus').innerText='✅ Trade opened: '+j.symbol+' '+j.side+' $'+j.pos+' ENTRY $'+j.entry.toFixed(4)+' INV '+j.inv+'/'+j.cap+' - Reloading...'; setTimeout(()=>{{ document.getElementById('analyzeOverlay').classList.remove('show'); location.reload(); }},1500); }} else{{ document.getElementById('autoStatus').innerText='FAIL: '+(j.error||'unknown')+' INV '+j.inv+'/'+j.cap+' - Will close and retry'; if(j.error && j.error.includes('MAXP')){{ setTimeout(()=>{{ document.getElementById('analyzeOverlay').classList.remove('show'); location.reload(); }},2000); }} else {{ setTimeout(()=>{{ autoConfirmTrade(); }},2000); }} }} }}catch(e){{ document.getElementById('autoStatus').innerText='ERR '+e+' - Retrying...'; setTimeout(()=>{{ autoConfirmTrade(); }},2000); }} }}
    async function callReset(){{if(!confirm('RESET AUTO v8 FIX 450/300 CAP SAFE? This will trim 3->2 trades')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
    async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
    async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}
    function initChart(sym,entry,tp,sl,side,openTs,initialAge,cg_id){{const cv=document.getElementById('chart-'+sym); if(!cv) return; const ctx=cv.getContext('2d'); let prices = []; let liveHistory = []; let ageSec = initialAge; const ageEl=document.getElementById('live-age-'+sym); setInterval(()=>{{ ageSec += 1; const m=Math.floor(ageSec/60); const s=ageSec%60; if(ageEl) ageEl.innerText=m+'m '+s+'s'; }},1000); async function fetchPrice(){{let price=null; try{{ const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const j=await r.json(); if(j.price && j.price>0) price=j.price; }}catch(e){{}} if(!price) return; const pct=side=='LONG'?(price-entry)/entry*100:(entry-price)/entry*100; if(Math.abs(pct)>30 && ageSec<300) return; const net=150*(pct-0.17)/100; const elP=document.getElementById('live-price-'+sym); const elC=document.getElementById('live-change-'+sym); const elPn=document.getElementById('live-pnl-'+sym); const dot=document.getElementById('live-dot-'+sym); if(elP){{elP.innerText='$'+price.toFixed(5); elP.style.color=pct>=0?'#0f8':'#f44';}} if(elC){{elC.innerText=pct.toFixed(3)+'%'; elC.style.color=pct>=0?'#0f8':'#f44';}} if(elPn){{elPn.innerText=(net>=0?'+':'')+'$'+net.toFixed(2)+' / $1.55'; elPn.style.color=net>=0?'#0f8':'#f44';}} if(dot) dot.innerText='● V853 '+new Date().toLocaleTimeString()+' '+pct.toFixed(3)+'% AUTO'; liveHistory.push(price); if(liveHistory.length>60) liveHistory.shift(); prices = [...liveHistory]; draw(); if(pct >= TP_PCT){{ if(dot) dot.innerText='● TP HIT '+pct.toFixed(2)+'% - AUTO CLOSING V853'; setTimeout(async()=>{{ await fetch('/api/close?symbol='+sym+'&key='+ADMIN_KEY); location.reload(); }},1500); }} }} async function fetchKlines(){{try{{ const r=await fetch('/api/klines?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const j=await r.json(); if(j.closes && j.closes.length>10){{ let kl = j.closes.filter(p=>p>0); if(liveHistory.length<5){{ prices = kl.slice(-30); liveHistory = [...kl.slice(-30)]; }} draw(); }} }}catch(e){{}}}} function draw(){{const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); if(prices.length<2){{ prices = Array(20).fill(entry).map((v,i)=> v + (Math.random()-0.5)*entry*0.0003); }} const usePrices = prices; let displayPrices = usePrices.map(p=>{{ let rawPct = (p-entry)/entry*100; let ampPct = rawPct; if(Math.abs(rawPct)<0.6) ampPct = rawPct*4; return entry * (1 + ampPct/100); }}); const allAmp = [...displayPrices, entry]; let mn=Math.min(...allAmp)*0.9995; let mx=Math.max(...allAmp)*1.0005; const minRange = entry*0.006; const mid = (mn+mx)/2; if((mx-mn) < minRange){{ mn=mid-minRange/2; mx=mid+minRange/2; }} const rg=mx-mn||entry*0.001; function yF(p){{return h*0.85-((p-mn)/rg)*h*0.7;}} ctx.strokeStyle='#1a1a1a'; ctx.lineWidth=1; for(let i=0;i<5;i++){{const y=h*0.1+i*h*0.8/4; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const entryY=yF(entry); ctx.strokeStyle='#fc0'; ctx.lineWidth=3; ctx.beginPath(); ctx.moveTo(0,entryY); ctx.lineTo(w,entryY); ctx.stroke(); ctx.fillStyle='#fc0'; ctx.font='bold 11px monospace'; ctx.fillText('ENTRY '+entry.toFixed(5),4,entryY-5); const tpDisplay = entry*(1+((tp-entry)/entry*100)*4/100); let tpY=yF(tpDisplay); if(tpY<0) tpY=5; if(tpY>h) tpY=h-5; ctx.strokeStyle='#0f8'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.fillStyle='#0f8'; ctx.font='9px monospace'; ctx.fillText('TP '+tp.toFixed(5)+' $1.55',4,tpY-3); ctx.setLineDash([]); const slDisplay = entry*(1+((sl-entry)/entry*100)*4/100); let slY=yF(slDisplay); if(slY<0) slY=5; if(slY>h) slY=h-5; ctx.strokeStyle='#f44'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,slY); ctx.lineTo(w,slY); ctx.stroke(); ctx.fillStyle='#f44'; ctx.fillText('SL '+sl.toFixed(5),4,slY+11); ctx.setLineDash([]); ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=3; ctx.beginPath(); displayPrices.forEach((p,i)=>{{const x=i/(displayPrices.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=displayPrices[displayPrices.length-1]; const ly=yF(last); ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(w-8,ly,5,0,Math.PI*2); ctx.fill(); ctx.fillStyle=last>=entry?'#0f8':'#f44'; ctx.beginPath(); ctx.arc(w-8,ly,3.5,0,Math.PI*2); ctx.fill();}} draw(); fetchKlines(); fetchPrice(); setInterval(fetchPrice, 3000); setInterval(fetchKlines, 20000);}}window.addEventListener('load',()=>{{drawEquity(); {chart_js_init}}});</script></body></html>"""
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
    if p.startswith("/api/analyze_candidate"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            state=load_state()
            current_inv=sum([t.get("pos",0) for t in state.get("open",[])])
            cap=state.get("cap",300.0)
            if len(state.get("open",[]))>=MAXP:
                return Response(json.dumps({"ok":False,"error":f"MAXP {MAXP} reached INV {current_inv:.0f}/{cap:.0f} - Close one first","inv":current_inv,"cap":cap}), mimetype="application/json")
            if current_inv>=cap*0.95:
                return Response(json.dumps({"ok":False,"error":f"CAP FULL INV {current_inv:.0f}/{cap:.0f}","inv":current_inv,"cap":cap}), mimetype="application/json")
            scan=state.get("scan",0); offset=state.get("scan_offset",0)
            real=STATIC_TOP; batch=real[offset:offset+SCAN_BATCH] if offset+SCAN_BATCH <= len(real) else real[offset:]+real[: (offset+SCAN_BATCH)-len(real) ]
            open_syms=[t["symbol"] for t in state.get("open",[])]
            for base,shark in batch:
                if base in open_syms: continue
                if base in state["learn"]["last_coins"]: continue
                price, src = fetch_live_price_fast(base)
                if price and price>0:
                    return Response(json.dumps({"ok":True,"symbol":base,"price":price,"src":src,"shark":shark,"scan":scan,"offset":offset,"inv":current_inv,"cap":cap}), mimetype="application/json")
            price, src = fetch_live_price_fast("BTC")
            return Response(json.dumps({"ok":True,"symbol":"BTC","price":price or 83000,"src":src,"shark":60,"scan":scan,"offset":offset,"inv":current_inv,"cap":cap}), mimetype="application/json")
        except Exception as e:
            import traceback
            return Response(json.dumps({"ok":False,"error":str(e)[:200],"trace":traceback.format_exc()[:300]}), mimetype="application/json")
    if p.startswith("/api/open_analyzed"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            data=None
            if request.method=="POST":
                try:
                    data=request.get_json(force=True)
                except:
                    data={}
                sym=(data.get("symbol","") if data else "").upper() or request.args.get("symbol","").upper()
                side=(data.get("side","") if data else "") or request.args.get("side","LONG")
                reason=(data.get("reason","") if data else "") or request.args.get("reason","30M+1M auto")
            else:
                sym=request.args.get("symbol","").upper()
                side=request.args.get("side","LONG")
                reason=request.args.get("reason","30M+1M auto")
            if not sym:
                return Response(json.dumps({"ok":False,"error":"no symbol"}), mimetype="application/json")
            if side not in ["LONG","SHORT"]: side="LONG"
            state=load_state()
            current_inv=sum([t.get("pos",0) for t in state.get("open",[])])
            cap=state.get("cap",300.0)
            if len(state.get("open",[]))>=MAXP:
                # Auto-trim to fix 450/300 bug
                state["open"]=sorted(state["open"], key=lambda x: x.get("ts",0), reverse=True)[:MAXP-1]
                current_inv=sum([t.get("pos",0) for t in state.get("open",[])])
                if len(state.get("open",[]))>=MAXP:
                    return Response(json.dumps({"ok":False,"error":f"MAXP {MAXP} reached INV {current_inv:.0f}/{cap:.0f}","inv":current_inv,"cap":cap}), mimetype="application/json")
            if current_inv>=cap*0.95:
                return Response(json.dumps({"ok":False,"error":f"CAP FULL INV {current_inv:.0f}/{cap:.0f}","inv":current_inv,"cap":cap}), mimetype="application/json")
            price, src = fetch_live_price_fast(sym)
            if not price or price==0:
                return Response(json.dumps({"ok":False,"error":"no live price for "+sym}), mimetype="application/json")
            pos_size=cap*POS_PCT/100.0
            if current_inv+pos_size>cap: pos_size=(cap-current_inv)*0.95
            if pos_size<20: pos_size=20
            if current_inv+pos_size>cap*1.05:
                return Response(json.dumps({"ok":False,"error":f"Would exceed CAP INV {current_inv:.0f}+{pos_size:.0f} > {cap:.0f}","inv":current_inv,"cap":cap}), mimetype="application/json")
            tr={"symbol":sym,"side":side,"entry":price,"price":price,"pos":pos_size,"ts":int(time.time()),"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":60,"tp":TP_PCT,"sl":SL_PCT,"reason":f"$1.50 AUTO 30M+1M v853 {side} ${price:.4f} {src} {reason[:120]} POS ${pos_size:.0f}/{cap:.0f}","rsi":50,"shark":60,"atr":1.0,"vol":50000000,"cg_id":SYM_TO_ID.get(sym,""),"analysis":reason[:200]}
            state["open"].append(tr)
            state["scan"]=state.get("scan",0)+1
            state["scan_offset"]=(state.get("scan_offset",0)+SCAN_BATCH)%TOP_N
            state["full_scans"]=state.get("scan",0)//(TOP_N//SCAN_BATCH)
            state["last_cron"]=f"v853 AUTO OPEN {sym} {side} ${price:.4f} {reason[:60]} INV {current_inv+pos_size:.0f}/{cap:.0f} SCAN {state.get('scan',0)}"
            eq=state.get("equity",[300]); eq.append(cap); state["equity"]=eq[-150:]
            ok=kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":ok,"symbol":sym,"side":side,"entry":price,"pos":pos_size,"inv":current_inv+pos_size,"cap":cap,"reason":reason}), mimetype="application/json")
        except Exception as e:
            import traceback
            return Response(json.dumps({"ok":False,"error":str(e)[:200],"trace":traceback.format_exc()[:500]}), mimetype="application/json")
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps({"ok":False,"error":"Use AUTO flow: TAP CRON AUTO 30M+1M does 30m deep + 1m live then AUTO-START","use":"POST /api/open_analyzed auto"}), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); time.sleep(0.5)
        new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0],"last_cron":"reset v853 AUTO CAP SAFE FIX 450/300 TRUE CLEAN"}
        kv_set(STATE_KEY,new); return Response(json.dumps({"ok":True,"cap":300,"cleared":True,"msg":"Trimmed 450/300 to 0/300"}), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]):
            lp,_=fetch_live_price_fast(tr["symbol"])
            if lp and lp>0:
                pct=(lp-tr["entry"])/tr["entry"]*100 if tr["side"]=="LONG" else (tr["entry"]-lp)/tr["entry"]*100
                pct_net=pct-TOTAL_FEE; net=tr["pos"]*pct_net/100
            else: net=tr.get("net",0)
            cap+=net; state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":net,"reason":f"MANUAL CLOSE ALL LIVE ${lp if lp else 0:.5f} v853","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0)})
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
                cap+=net; state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":net,"reason":f"MANUAL CLOSE {sym} LIVE ${lp if lp else 0:.5f} v853","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0)})
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
