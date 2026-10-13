"""
VENUS v859 - MOST MOVING SCANNER + GRAPH SENSE LONG/SHORT - 3 DISTINCT COINS
Scans top movers by volatility, predicts LONG/SHORT from graph movement sense, no duplicate BTC
"""
from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse
app = Flask(__name__)
MEM_STATE={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0],"last_cron":"mem v859 MOVING"}

def env(k):
    for kk in k:
        v=os.environ.get(kk)
        if v: return v.strip().strip('"').strip("'")
    return ""
KV_URL=(env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL","KV_URL","REDIS_URL"]) or "").rstrip("/")
if not KV_URL:
    for kk,vv in os.environ.items():
        if ("REDIS" in kk or "KV" in kk) and "URL" in kk and ("upstash" in vv.lower() or "vercel" in vv.lower() or "redis" in vv.lower()):
            KV_URL=vv.strip().strip('"').strip("'").rstrip("/"); break
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN","KV_REST_API_READ_ONLY_TOKEN","KV_TOKEN"])
if not KV_TOKEN:
    for kk,vv in os.environ.items():
        if ("REDIS" in kk or "KV" in kk) and "TOKEN" in kk and ("upstash" in kk.lower() or "vercel" in kk.lower()):
            KV_TOKEN=vv.strip().strip('"').strip("'"); break
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V808_SHARK100"
MAXP=3
POS_PCT=33.33
TOTAL_FEE=0.17
SCAN_BATCH=24
TOP_N=100
TP_PCT=1.20
SL_PCT=0.60
STATIC_TOP=[("BTC",60),("ETH",55),("SOL",50),("BNB",50),("XRP",48),("AVAX",45),("LINK",45),("ADA",44),("DOT",44),("LTC",43),("UNI",43),("ETC",42),("APT",42),("ARB",41),("OP",41),("SUI",40),("NEAR",40),("HBAR",40),("FIL",39),("MKR",39),("AAVE",38),("GRT",38),("RNDR",38),("INJ",38),("STX",37),("IMX",37),("SEI",37),("TIA",37),("WLD",36),("FET",36),("TAO",36),("ZEC",35),("STRK",35),("JUP",35),("ENA",34),("PENDLE",34),("ONDO",34),("DOGE",34),("CYBER",32),("PEPE",30),("BONK",29),("WIF",28),("FLOKI",27),]
SYM_TO_ID={"BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin","XRP":"ripple","ADA":"cardano","AVAX":"avalanche-2","DOT":"polkadot","LINK":"chainlink","LTC":"litecoin","UNI":"uniswap","ETC":"ethereum-classic","APT":"aptos","ARB":"arbitrum","OP":"optimism","SUI":"sui","RNDR":"render-token","MKR":"maker","AAVE":"aave","GRT":"the-graph","SEI":"sei-network","TIA":"celestia","DOGE":"dogecoin","WLD":"worldcoin","FET":"fetch-ai","TAO":"bittensor","IMX":"immutable-x","JUP":"jupiter","HBAR":"hedera","ENA":"ethena","PENDLE":"pendle","ZEC":"zcash","STRK":"starknet","ONDO":"ondo-finance","NEAR":"near-protocol","CYBER":"cyberconnect","PEPE":"pepe","BONK":"bonk","WIF":"dogwifcoin","FLOKI":"floki"}

def kv_get(k):
    global MEM_STATE
    if not KV_URL or not KV_TOKEN:
        return MEM_STATE
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d=json.loads(r.read().decode()); res=d[0].get("result") if isinstance(d,list) and d else None
            if res:
                return json.loads(res) if (res.startswith("{") or res.startswith("[")) else res
    except:
        pass
    return MEM_STATE

def kv_set(k,o):
    global MEM_STATE
    MEM_STATE=o
    if not KV_URL or not KV_TOKEN:
        return True
    try:
        body=json.dumps([["SET",k,json.dumps(o)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return "OK" in r.read().decode()
    except:
        return True

def kv_del(k):
    global MEM_STATE
    MEM_STATE={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0],"last_cron":"reset v859 MOVING"}
    if not KV_URL or not KV_TOKEN:
        return True
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

def analyze_most_moving(closes, vols):
    if len(closes)<15:
        return {"moving_score":0,"mom_5":0,"mom_30":0,"rsi":50,"volatility":0,"side":"LONG","strong":False}
    last=closes[-1]
    sma5=sum(closes[-5:])/5
    sma10=sum(closes[-10:])/10 if len(closes)>=10 else sum(closes)/len(closes)
    sma20=sum(closes[-20:])/20 if len(closes)>=20 else sum(closes)/len(closes)
    sma30=sum(closes)/len(closes)
    mom_5=(closes[-1]-closes[-5])/closes[-5]*100 if closes[-5]!=0 else 0
    mom_30=(closes[-1]-closes[0])/closes[0]*100 if closes[0]!=0 else 0
    # Volatility = avg true range approximated by high-low of closes
    volatility = (max(closes[-10:]) - min(closes[-10:])) / last *100 if last!=0 else 0
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
    score_long=0; score_short=0
    if last > sma30: score_long+=2
    else: score_short+=2
    if sma5 > sma10 and sma10 > sma20: score_long+=3
    elif sma5 < sma10 and sma10 < sma20: score_short+=3
    elif sma5 > sma10: score_long+=1
    else: score_short+=1
    if mom_5>0: score_long+=2
    else: score_short+=2
    if mom_30>0: score_long+=1
    else: score_short+=1
    if rsi>60: score_long+=1
    elif rsi<40: score_short+=1
    if up_candles>=6: score_long+=1
    else: score_short+=1
    side="LONG" if score_long>=score_short else "SHORT"
    diff=abs(score_long-score_short)
    # MOVING SCORE = how much it moves = abs mom + volatility + RSI extreme + diff
    moving_score = abs(mom_5)*2 + abs(mom_30) + volatility*1.5 + abs(rsi-50)/10 + diff
    strong = diff>=2 and (abs(mom_5)>=0.05 or abs(mom_30)>=0.15 or volatility>=0.3 or rsi<42 or rsi>58)
    if diff>=1 and moving_score>=3:  # Lower threshold for most moving
        strong=True
    return {"moving_score":moving_score,"mom_5":mom_5,"mom_30":mom_30,"rsi":rsi,"volatility":volatility,"side":side,"score_long":score_long,"score_short":score_short,"diff":diff,"up_candles":up_candles,"strong":strong,"sma5":sma5,"sma10":sma10,"sma20":sma20,"closes":closes,"strength":diff}

def load_state():
    s=kv_get(STATE_KEY)
    if not s or not isinstance(s, dict) or "cap" not in s:
        s=MEM_STATE
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("learn",{"blacklist":{},"last_coins":{}}); s.setdefault("peak",s.get("cap",300)); s.setdefault("equity",[300,s.get("cap",300)]); s.setdefault("last_cron","never v859 MOVING")
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
    invested=sum([t.get("pos",0) for t in open_tr])
    dd=(peak-cap)/peak*100 if peak>0 else 0
    daily_needed=max(0,15.0-daily); trades_needed=int(daily_needed/1.50)+1 if daily_needed>0 else 0
    daily_color = "#0f8" if daily>=0 else "#f44"; target_color = "#0f8"
    last_cron = state.get("last_cron","never v859")
    cap_safe_color = "#0f8" if invested <= cap*1.05 else "#f44"
    over_msg = "✅" if invested<=cap*1.05 else "❌ OVER"
    kv_status = f"KV:{'OK' if KV_URL and KV_TOKEN else 'MEM'} MOVING SENSE v859"
    trade_boxes_html=""; chart_js_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",100); entry=tr.get("entry",0); tp=tr.get("tp",TP_PCT); sl=tr.get("sl",SL_PCT); rr=tp/sl if sl>0 else 2.0
        tp_price=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100); sl_price=entry*(1-sl/100) if side=="LONG" else entry*(1+sl/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        net_target = pos*(tp-TOTAL_FEE)/100
        analysis=tr.get("analysis","v859 moving sense")[:120]
        shark_tag=f"<span style='background:#00d4ff;color:#000;padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900'>SHARK {tr.get('shark',0)} RR {rr:.1f} ${net_target:.2f}</span>"
        ts=tr.get("ts",int(time.time()))
        trade_boxes_html+=f"""<div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'><div style='display:flex;justify-content:space-between'><div><b style='color:{col};font-size:14px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f} {shark_tag}</b><div style='font-size:10px;color:#0f8'>🤖 v859 MOVING SENSE: {analysis}</div><div style='font-size:10px;color:#aaa'>ENTRY ${entry:.6f} TP ${tp_price:.6f} ({tp:.2f}%) = ${net_target:.2f} NET SL ${sl_price:.6f} ({sl:.2f}%) INV {invested:.0f}/{cap:.0f} MOVE {tr.get('moving_score',0):.2f}</div></div><button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 10px'>✕</button></div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin:8px 0;text-align:center'><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>LIVE</div><div id='live-price-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('price',0):.5f}</div><div id='live-change-{sym}' style='font-size:10px'>{tr.get('pct_gross',0):+.3f}%</div><div id='live-dot-{sym}' style='font-size:8px;color:#0f8'>● V859 MOVING</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>PNL</div><div id='live-pnl-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f} / ${net_target:.2f}</div><div style='font-size:10px'>PEAK {tr.get('peak_gross',0):.2f}% TARGET $1.50</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>AGE</div><div id='live-age-{sym}' style='font-size:13px;font-weight:900'>{int(tr.get('age',0)//60)}m {int(tr.get('age',0)%60)}s</div><div style='font-size:10px;color:#0f8'>TP {tp:.2f}% SL {sl:.2f}% MOVE {tr.get('moving_score',0):.1f}</div></div></div><div style='background:#000;border-radius:12px;padding:6px;border:1px solid #222'><div style='font-size:9px;color:#555'>TURBO GRAPH {side} - v859 MOVING SENSE - {analysis[:80]} - TP GREEN SL RED ENTRY YELLOW - GRAPH PREDICTION</div><canvas id='chart-{sym}' width='340' height='180' style='width:100%;height:180px;background:#000;border-radius:8px'></canvas></div><div style='font-size:9px;color:#888;margin-top:4px'>{tr.get('reason','')}</div></div>"""
        chart_js_init+=f"initChart('{sym}',{entry},{tp_price},{sl_price},'{side}',{ts},{int(tr.get('age',0))},'{tr.get('cg_id','bitcoin')}');\n"
    if not open_tr:
        trade_boxes_html=f"<div class='it' style='text-align:center;color:#666;padding:16px'>No open trades - v859 MOST MOVING SCANNER - Scans 24 coins, ranks by moving_score = |5m|*2 + |30m| + volatility*1.5 + |RSI-50|/10 + diff, picks TOP 3 MOST MOVING distinct coins, predicts LONG/SHORT from graph movement sense: SMA5>10>20 + momentum + RSI + 10 candles + live 1M confirmation - SCAN {scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} FULL {full_scans}x CAP ${cap:.2f}<br>LAST CRON: {last_cron}<br>INV {invested:.0f}/{cap:.0f} MAXP {MAXP} - {kv_status}<br>FIXED: No duplicate BTC, 3 distinct most moving coins</div>"
    equity_js=json.dumps(equity[-80:])
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}}.h{{background:linear-gradient(90deg,#00ff88,#ffcc00);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}}.g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}}.stats{{background:#111;border:2px solid #0f8;padding:10px;margin:6px 0;border-radius:12px}}.it{{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:12px}}.btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.btn{{padding:16px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px;cursor:pointer}}.btn-cron{{background:#0f8;color:#000}}.btn-reset{{background:#f44;color:#fff}}.btn-close{{background:#fc0;color:#000}}.badge{{padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900}}.long{{background:#0f8;color:#000}}.short{{background:#f44;color:#fff}}.overlay{{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.95);z-index:9999;display:none;flex-direction:column;padding:10px;overflow-y:auto}}.overlay.show{{display:flex}}.coin-grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}}@media(max-width:600px){{.coin-grid{{grid-template-columns:1fr}}}}</style></head><body>
    <div id='analyzeOverlay' class='overlay'><div style='background:#111;border:2px solid #fc0;border-radius:16px;padding:12px'><div style='color:#fc0;font-weight:900;font-size:14px;text-align:center' id='analyzeTitle'>🤖 v859 MOST MOVING SCANNER + GRAPH SENSE</div><div style='color:#0f8;font-size:11px;text-align:center;margin:6px 0' id='analyzeStatus'>Scanning most moving coins...</div><div style='background:#000;border-radius:12px;padding:8px;margin:8px 0'><div style='font-size:10px;color:#888'>STEP 1: SCAN 24 COINS FOR MOST MOVING - Ranking by |5m|*2 + |30m| + volatility*1.5 + |RSI-50|/10</div><div id='scanLog' style='color:#ffcc00;font-size:9px;white-space:pre-wrap;max-height:100px;overflow-y:auto;background:#0a0a0a;padding:6px;border-radius:8px;margin:4px 0'></div><div style='font-size:10px;color:#888'>STEP 2: 3 MOST MOVING - 30M DEEP + GRAPH SENSE PREDICTION (SMA, RSI, momentum, candles)</div><div id='deepAnalysisText' style='color:#0f8;font-size:10px;margin:4px 0;white-space:pre-wrap'>Waiting...</div><div class='coin-grid'><div style='background:#111;border-radius:10px;padding:6px'><div id='deepCoin0' style='color:#fc0;font-weight:900;font-size:11px'>Most Moving 1: -</div><canvas id='deepChart0' width='200' height='150' style='width:100%;height:150px;background:#000;border-radius:8px'></canvas><div id='deepText0' style='color:#0f8;font-size:8px;white-space:pre-wrap'>Waiting...</div></div><div style='background:#111;border-radius:10px;padding:6px'><div id='deepCoin1' style='color:#fc0;font-weight:900;font-size:11px'>Most Moving 2: -</div><canvas id='deepChart1' width='200' height='150' style='width:100%;height:150px;background:#000;border-radius:8px'></canvas><div id='deepText1' style='color:#0f8;font-size:8px;white-space:pre-wrap'>Waiting...</div></div><div style='background:#111;border-radius:10px;padding:6px'><div id='deepCoin2' style='color:#fc0;font-weight:900;font-size:11px'>Most Moving 3: -</div><canvas id='deepChart2' width='200' height='150' style='width:100%;height:150px;background:#000;border-radius:8px'></canvas><div id='deepText2' style='color:#0f8;font-size:8px;white-space:pre-wrap'>Waiting...</div></div></div></div><div style='background:#000;border-radius:12px;padding:8px;margin:8px 0;border:1px solid #333'><div style='font-size:10px;color:#888'>STEP 3: 1M LIVE GRAPH SENSE - Confirm prediction with live movement (60s)</div><div id='liveMonitorText' style='color:#ffcc00;font-size:11px;margin:4px 0'>Waiting for top movers...</div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;text-align:center'><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>TIME LEFT</div><div id='monitorTimeLeft' style='font-size:18px;font-weight:900;color:#f44'>60s</div><div id='monitorProgress' style='font-size:9px'>0/60s</div></div><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>TOTAL LIVE</div><div id='monitorTotalMove' style='font-size:12px;font-weight:900;color:#0f8'>+0.00%</div></div><div style='background:#111;padding:6px;border-radius:8px'><div style='font-size:8px;color:#888'>GRAPH SENSE</div><div id='monitorBatch' style='font-size:9px;font-weight:900;color:#fc0'>Scanning movers...</div></div></div><div class='coin-grid' style='margin-top:8px'><div style='background:#111;border-radius:10px;padding:6px'><div style='display:flex;justify-content:space-between'><div id='liveCoin0' style='color:#0f8;font-weight:900;font-size:10px'>Mover1: -</div><div id='liveChange0' style='color:#0f8;font-size:10px'>+0.00%</div></div><div style='font-size:8px;color:#888'>START <span id='liveStart0'>$0</span> LIVE <span id='livePrice0'>$0</span></div><canvas id='liveMonitorChart0' width='200' height='120' style='width:100%;height:120px;background:#000;border-radius:8px;margin-top:4px'></canvas><div id='liveDecision0' style='color:#0f8;font-size:9px;font-weight:900;margin-top:2px'>Graph sense...</div></div><div style='background:#111;border-radius:10px;padding:6px'><div style='display:flex;justify-content:space-between'><div id='liveCoin1' style='color:#0f8;font-weight:900;font-size:10px'>Mover2: -</div><div id='liveChange1' style='color:#0f8;font-size:10px'>+0.00%</div></div><div style='font-size:8px;color:#888'>START <span id='liveStart1'>$0</span> LIVE <span id='livePrice1'>$0</span></div><canvas id='liveMonitorChart1' width='200' height='120' style='width:100%;height:120px;background:#000;border-radius:8px;margin-top:4px'></canvas><div id='liveDecision1' style='color:#0f8;font-size:9px;font-weight:900;margin-top:2px'>Graph sense...</div></div><div style='background:#111;border-radius:10px;padding:6px'><div style='display:flex;justify-content:space-between'><div id='liveCoin2' style='color:#0f8;font-weight:900;font-size:10px'>Mover3: -</div><div id='liveChange2' style='color:#0f8;font-size:10px'>+0.00%</div></div><div style='font-size:8px;color:#888'>START <span id='liveStart2'>$0</span> LIVE <span id='livePrice2'>$0</span></div><canvas id='liveMonitorChart2' width='200' height='120' style='width:100%;height:120px;background:#000;border-radius:8px;margin-top:4px'></canvas><div id='liveDecision2' style='color:#0f8;font-size:9px;font-weight:900;margin-top:2px'>Graph sense...</div></div></div></div><div style='background:#111;border-radius:12px;padding:8px;margin:8px 0'><div style='font-size:10px;color:#888'>GRAPH SENSE FINAL PREDICTION - LONG/SHORT based on SMA trend + RSI + momentum + live confirmation</div><div id='finalDecision' style='color:#0f8;font-size:12px;font-weight:900;margin:4px 0;white-space:pre-wrap'>Scanning most moving...</div><div id='finalReason' style='color:#aaa;font-size:9px;white-space:pre-wrap'>Graph movement sense...</div></div><div style='background:#000;padding:10px;border-radius:10px;text-align:center'><div id='autoStatus' style='color:#fc0;font-size:12px;font-weight:900;white-space:pre-wrap'>🤖 v859 MOST MOVING + GRAPH SENSE - Scans 24 coins for biggest movers, predicts LONG/SHORT from graph</div><div id='autoErrorLog' style='color:#f44;font-size:9px;margin-top:6px;white-space:pre-wrap;text-align:left;max-height:60px;overflow-y:auto'></div><div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px'><button onclick='autoConfirm3Trades()' id='forceOpenBtn' style='background:#fc0;color:#000;padding:12px;border-radius:10px;border:0;font-weight:900'>⚡ FORCE OPEN 3 MOST MOVING</button><button onclick='closeOverlay()' style='background:#333;color:#fff;padding:12px;border-radius:10px;border:0;font-weight:900'>❌ CLOSE</button></div></div></div></div>
    <div class='h'>VENUS v859 MOST MOVING + GRAPH SENSE - SCAN #{scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} - ${cap:.2f} PEAK ${peak:.2f} DD {dd:.1f}% L:{long_open} S:{short_open} FULLx{full_scans} - DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> NEED {trades_needed}x $1.50 INV <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f} {over_msg}</span> POS {POS_PCT:.1f}% x{MAXP} {kv_status}<br><span style='font-size:9px'>LAST: {last_cron[:90]}</span></div>
    <div style='background:#000;border-radius:12px;padding:8px;margin:6px 0;border:1px solid #333'><div style='font-size:9px;color:#888'>EQUITY CURVE (CAP $300 → ${cap:.2f}) PEAK ${peak:.2f} DD {dd:.1f}% DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> INV <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f} {over_msg}</span> NEED {trades_needed}x $1.50 - V859 MOST MOVING GRAPH SENSE - {last_cron[:60]} - {kv_status}</div><canvas id='equityChart' width='340' height='80' style='width:100%;height:80px;background:#000;border-radius:8px'></canvas></div>
    <div class='btn-row'><button class='btn btn-cron' onclick='startMovingScan()' id='cronBtn'>🤖 CRON MOST MOVING {invested:.0f}/{cap:.0f} {over_msg}<div id='cronStat' style='font-size:10px'>TAP {offset+1}-{offset+SCAN_BATCH}/{TOP_N} SCAN {scan} FULL {full_scans} - SCAN 24 COINS MOST MOVING + GRAPH SENSE LONG/SHORT - <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> INV {invested:.0f}/{cap:.0f}<br>{last_cron[:30]}</div></button><button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN ${invested:.0f}/{cap:.0f} {over_msg}</div></button><button class='btn btn-reset' onclick='callReset()'>🔄RESET MOVING v13<div style='font-size:10px'>CAP $300 MOVING SENSE</div></button></div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#fc0'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}<br>INV <b style='color:{cap_safe_color}'>${invested:.0f}/{cap:.0f} {over_msg}</b><br>FEES ${fees_paid:.2f}<br>PEAK ${peak:.2f} DD {dd:.1f}%<br>{kv_status}</div><div class='c'>DAILY $15<br><b style='font-size:18px'><span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span></b><br>NEED ${daily_needed:.2f} = {trades_needed}x $1.50<br>W:{wins} L:{loss} {winrate}%<br>TOTAL {tot} V859<br>FULL {full_scans}x PF {pf:.2f}<br>MOVING SENSE</div><div class='c' style='border-color:#fc0'><b style='color:#fc0'>MOST MOVING<br>POS {POS_PCT:.1f}% x{MAXP}<br>v859 GRAPH SENSE</b><br>TP {TP_PCT}% = $1.50<br>SL {SL_PCT}%<br>RR 2.0<br>INV <span style='color:{cap_safe_color}'>{invested:.0f}/{cap:.0f}</span><br>SCAN MOVERS</div></div>
    <div class='stats'><div style='color:#fc0;font-weight:900;font-size:12px'>🤖 v859 MOST MOVING + GRAPH SENSE - Fixes v858 3x same BTC bug, now scans 24 coins for most moving by |5m|*2 + |30m| + volatility*1.5 + |RSI-50|/10, picks TOP 3 DISTINCT most moving, predicts LONG/SHORT from graph sense: SMA5>10>20 uptrend + mom + RSI + 7/10 candles + live 1M confirmation. No duplicate coins.</div><div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px;font-size:10px'><div>SCAN: <b>{offset+1}-{offset+SCAN_BATCH}/{TOP_N} (x{full_scans}) V859 MOVING INV {invested:.0f}/{cap:.0f} {kv_status}</b></div><div>OPEN: <b>{len(open_tr)}/{MAXP} PEAK ${peak:.2f} DD {dd:.1f}% DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span></b></div><div>TOTAL: <b>{tot}</b> W:<b style='color:#0f8'>{wins}</b> L:<b style='color:#f44'>{loss}</b> {winrate}% PF:<b>{pf:.2f}</b></div><div>EXP: <b>${exp:.3f}</b> FEES: <b>{TOTAL_FEE}%</b> NEED: <b>${daily_needed:.2f} = {trades_needed}x $1.50 INV {invested:.0f}/{cap:.0f}</b></div><div>BEST: <b>{best_sym} ${best_net:+.2f}</b></div><div>WORST: <b>{worst_sym} ${worst_net:+.2f}</b></div></div><div style='margin-top:6px;color:#fc0;font-size:9px'>LAST CRON: {last_cron}</div><div style='margin-top:6px;color:#0f8;font-size:10px'>✅ v859 MOVING SENSE: Scans most moving coins, predicts LONG/SHORT from graph movement, 3 distinct coins, fixes duplicate BTC bug.</div></div><div id='openbox'>{trade_boxes_html}</div><div style='background:#111;padding:10px;margin:6px 0;border-radius:10px'><div style='color:#fc0;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% - PF {pf:.2f} EXP ${exp:.3f} PEAK ${peak:.2f} DD {dd:.1f}% DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> INV {invested:.0f}/{cap:.0f} NEED {trades_needed}x $1.50 - V859 MOVING SENSE</div>"""
    for cl in closed[:30]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"; sym=cl.get("symbol","?"); side=cl.get("side","?"); net=cl.get("net",0); pct=cl.get("pct_net",0); reason=cl.get("reason","")[:80]; age=cl.get("age",0); shark=cl.get("shark",0)
        html+=f"<div style='padding:5px 0;border-bottom:1px solid #222;color:{c}'><b>{sym} {side} SHARK {shark}</b> ${net:+.2f} {pct:+.2f}% | {reason} | {int(age//60)}m</div>"
    html+=f"""</div><script>const EQUITY = {equity_js};const ADMIN_KEY="{ADMIN_KEY}";const TP_PCT={TP_PCT};const SL_PCT={SL_PCT};let currentAnalysis=null;let timeLeft=60;let retryCount=0;let scanData=[];
    function drawEquity(){{const cv=document.getElementById('equityChart'); if(!cv||!EQUITY.length) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...EQUITY)*0.999, mx=Math.max(...EQUITY)*1.001, rg=mx-mn||1; function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}} ctx.strokeStyle='#222'; for(let i=0;i<3;i++){{const y=h*0.1+i*h*0.8/2; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const y300=yF(300); ctx.strokeStyle='#444'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,y300); ctx.lineTo(w,y300); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle='#666'; ctx.font='8px monospace'; ctx.fillText('300',2,y300-2); ctx.strokeStyle='#fc0'; ctx.lineWidth=2; ctx.beginPath(); EQUITY.forEach((p,i)=>{{const x=i/(EQUITY.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=EQUITY[EQUITY.length-1]; ctx.fillStyle='#0f8'; ctx.beginPath(); ctx.arc(w-4,yF(last),3,0,Math.PI*2); ctx.fill(); ctx.fillText(last.toFixed(2), w-50, yF(last)-4);}}
    function logScan(msg){{const el=document.getElementById('scanLog'); if(el){{ el.innerText+= '\\n'+msg; el.scrollTop=el.scrollHeight; }} console.log(msg); }}
    function logError(msg){{const el=document.getElementById('autoErrorLog'); if(el){{ el.innerText+= '\\n'+msg; }} console.error(msg); }}
    async function startMovingScan(){{const overlay=document.getElementById('analyzeOverlay'); overlay.classList.add('show'); document.getElementById('scanLog').innerText=''; document.getElementById('autoErrorLog').innerText=''; document.getElementById('forceOpenBtn').style.display='block'; currentAnalysis={{coins:[]}}; scanData=[]; logScan('v859 MOST MOVING SCANNER + GRAPH SENSE - Scanning 24 coins for most moving...'); document.getElementById('analyzeTitle').innerText='🤖 v859 SCANNING MOST MOVING COINS...'; document.getElementById('analyzeStatus').innerText='Step 1: Scanning 24 coins for volatility & movement...'; try{{ const r=await fetch('/api/scan_most_moving?key='+ADMIN_KEY+'&t='+Date.now()); const txt=await r.text(); let j; try{{ j=JSON.parse(txt); }}catch(e){{ logScan('Scan moving JSON fail: '+txt.substring(0,200)); document.getElementById('analyzeStatus').innerText='Scan fail: '+txt.substring(0,80); return; }} if(!j.ok){{ logScan('Scan moving fail: '+j.error); document.getElementById('analyzeStatus').innerText='FAIL: '+j.error; return; }} const movers=j.movers||[]; if(movers.length==0){{ logScan('No movers found'); document.getElementById('analyzeStatus').innerText='No movers, retry'; return; }} logScan('Found '+movers.length+' coins ranked by moving_score:'); movers.slice(0,10).forEach((m,i)=>{{ logScan((i+1)+'. '+m.symbol+' move='+m.moving_score.toFixed(2)+' 5m='+m.mom_5.toFixed(3)+'% 30m='+m.mom_30.toFixed(2)+'% vol='+m.volatility.toFixed(2)+'% RSI='+m.rsi.toFixed(0)+' '+m.side+' '+m.score_long+'v'+m.score_short); }}); const top3=movers.slice(0,3); logScan('\\n✅ TOP 3 MOST MOVING DISTINCT: '+top3.map(m=>m.symbol+' '+m.side+' move='+m.moving_score.toFixed(2)).join(' | ')); document.getElementById('deepAnalysisText').innerText='TOP 3 MOST MOVING (distinct, highest volatility):\\n'+top3.map(m=>m.symbol+' $'+m.price.toFixed(4)+' move='+m.moving_score.toFixed(2)+' 5m='+m.mom_5.toFixed(3)+'% 30m='+m.mom_30.toFixed(2)+'% vol='+m.volatility.toFixed(2)+'% RSI='+m.rsi.toFixed(0)+' '+m.side+' '+m.score_long+'v'+m.score_short+' '+(m.strong?'STRONG':'WEAK')).join('\\n')+'\\n\\nGraph sense prediction based on SMA trend + momentum + RSI...'; document.getElementById('monitorBatch').innerText='Most moving: '+top3.map(m=>m.symbol).join(',')+' - Graph sense'; document.getElementById('analyzeTitle').innerText='📊 '+top3.map(m=>m.symbol).join(' + ')+' - MOST MOVING GRAPH SENSE'; currentAnalysis.coins=top3.map(m=>({{symbol:m.symbol, price:m.price, startPrice:m.price, livePrice:m.price, liveChange:0, livePrices:[m.price], deep:m, closes:m.closes||[], finalSide:m.side, finalReason:'', moving_score:m.moving_score}})); for(let i=0;i<top3.length;i++){{ const m=top3[i]; document.getElementById('deepCoin'+i).innerText=m.symbol+' - '+m.side+' '+m.score_long+'v'+m.score_short+' move='+m.moving_score.toFixed(2)+' '+(m.strong?'✅ STRONG':'❌ WEAK'); document.getElementById('deepText'+i).innerText=m.symbol+' move='+m.moving_score.toFixed(2)+'\\n5m '+m.mom_5.toFixed(3)+'% 30m '+m.mom_30.toFixed(2)+'% vol '+m.volatility.toFixed(2)+'% RSI '+m.rsi.toFixed(0)+' '+m.side+' '+m.score_long+'v'+m.score_short+'\\n'+ (m.sma5>m.sma10 && m.sma10>m.sma20?'SMA5>10>20 uptrend strong': m.sma5<m.sma10 && m.sma10<m.sma20?'SMA5<10<20 downtrend strong': m.sma5>m.sma10?'SMA5>SMA10 up': 'SMA5<SMA10 down') +' | '+m.up_candles+'/10 candles'; drawDeepChart(i, m.closes||[], m); }} document.getElementById('analyzeStatus').innerText='✅ TOP 3 MOST MOVING FOUND: '+top3.map(m=>m.symbol+' '+m.side+' move='+m.moving_score.toFixed(2)).join(' | ')+' - Starting 1M live graph sense...'; startMovingLiveMonitor(); }}catch(e){{ logScan('startMovingScan err '+e); document.getElementById('analyzeStatus').innerText='ERR '+e; }} }}
    function drawDeepChart(idx, closes, deep){{const cv=document.getElementById('deepChart'+idx); if(!cv) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); if(!closes || closes.length<5){{ ctx.fillStyle='#666'; ctx.fillText('No data',10,h/2); return; }} const mn=Math.min(...closes)*0.999, mx=Math.max(...closes)*1.001; function yF(p){{return h*0.85-((p-mn)/(mx-mn||1))*h*0.7;}} ctx.strokeStyle='#1a1a1a'; for(let i=0;i<3;i++){{const y=h*0.1+i*h*0.8/2; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const sma5=deep.sma5||closes[closes.length-1]; const sma20=deep.sma20||closes[closes.length-1]; ctx.strokeStyle='#fc0'; ctx.setLineDash([3,3]); let y=yF(sma5); ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke(); ctx.strokeStyle='#666'; y=yF(sma20); ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke(); ctx.setLineDash([]); ctx.strokeStyle=deep.side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=1.5; ctx.beginPath(); closes.forEach((p,i)=>{{const x=i/(closes.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); }}
    function startMovingLiveMonitor(){{timeLeft=60; document.getElementById('monitorTimeLeft').innerText='60s'; document.getElementById('monitorProgress').innerText='0/60s'; for(let i=0;i<currentAnalysis.coins.length;i++){{ const c=currentAnalysis.coins[i]; document.getElementById('liveCoin'+i).innerText=c.symbol+' - '+c.finalSide+' (graph sense) - Monitoring...'; document.getElementById('liveStart'+i).innerText='$'+c.startPrice.toFixed(4); document.getElementById('livePrice'+i).innerText='$'+c.startPrice.toFixed(4); document.getElementById('liveChange'+i).innerText='+0.00%'; document.getElementById('liveDecision'+i).innerText='Graph sense: '+c.finalSide+'...'; c.livePrices=[c.startPrice]; drawLiveMonitorChart(i); }} const interval=setInterval(async()=>{{ timeLeft--; document.getElementById('monitorTimeLeft').innerText=timeLeft+'s'; document.getElementById('monitorProgress').innerText=(60-timeLeft)+'/60s'; let totalChange=0; for(let i=0;i<currentAnalysis.coins.length;i++){{ const c=currentAnalysis.coins[i]; try{{ const r=await fetch('/api/liveprice?symbol='+c.symbol+'&key='+ADMIN_KEY+'&t='+Date.now()); const txt=await r.text(); let j; try{{ j=JSON.parse(txt); }}catch(e){{ continue; }} if(j.price && j.price>0){{ c.livePrices.push(j.price); if(c.livePrices.length>60) c.livePrices.shift(); c.livePrice=j.price; const change=(j.price-c.startPrice)/c.startPrice*100; c.liveChange=change; totalChange+=change; document.getElementById('livePrice'+i).innerText='$'+j.price.toFixed(4); document.getElementById('liveChange'+i).innerText=(change>=0?'+':'')+change.toFixed(3)+'%'; document.getElementById('liveChange'+i).style.color=change>=0?'#0f8':'#f44'; drawLiveMonitorChart(i); const deep=c.deep||{{}}; let finalSide=deep.side||'LONG'; let graphSense=''; if(deep.sma5>deep.sma10 && deep.sma10>deep.sma20 && deep.mom_5>0 && change>=-0.1){{ finalSide='LONG'; graphSense='SMA5>10>20 uptrend + 5m '+deep.mom_5.toFixed(3)+'% up + live '+change.toFixed(3)+'% up -> LONG (graph up sense)'; }} else if(deep.sma5<deep.sma10 && deep.sma10<deep.sma20 && deep.mom_5<0 && change<=0.1){{ finalSide='SHORT'; graphSense='SMA5<10<20 downtrend + 5m '+deep.mom_5.toFixed(3)+'% down + live '+change.toFixed(3)+'% down -> SHORT (graph down sense)'; }} else if((deep.score_long||0) > (deep.score_short||0) && change>=-0.08){{ finalSide='LONG'; graphSense='Score '+deep.score_long+'v'+deep.score_short+' long + live '+change.toFixed(3)+'% -> LONG'; }} else{{ finalSide='SHORT'; graphSense='Score '+deep.score_long+'v'+deep.score_short+' short + live '+change.toFixed(3)+'% -> SHORT'; }} c.finalSide=finalSide; c.finalReason=graphSense+' | move='+deep.moving_score.toFixed(2)+' vol='+deep.volatility.toFixed(2)+'% RSI='+deep.rsi.toFixed(0)+' '+deep.up_candles+'/10 candles'; document.getElementById('liveDecision'+i).innerText=finalSide+' '+change.toFixed(3)+'% -> '+finalSide+' (graph sense)'; document.getElementById('liveDecision'+i).style.color=finalSide=='LONG'?'#0f8':'#f44'; document.getElementById('liveCoin'+i).innerText=c.symbol+' '+finalSide+' (graph sense)'; }} }}catch(e){{}} }} document.getElementById('monitorTotalMove').innerText=(totalChange/currentAnalysis.coins.length).toFixed(3)+'%'; let summary=currentAnalysis.coins.map(c=>c.symbol+': '+c.finalSide+' '+c.liveChange.toFixed(3)+'% move='+c.moving_score.toFixed(1)).join(' | '); document.getElementById('finalDecision').innerText='Live graph sense: '+summary+'\\nAUTO-OPEN in '+timeLeft+'s - Predicting from graph movement'; if(timeLeft<=0){{ clearInterval(interval); finishMovingLiveMonitor(); }} }},1000); }}
    function drawLiveMonitorChart(idx){{const c=currentAnalysis.coins[idx]; if(!c || c.livePrices.length<2) return; const cv=document.getElementById('liveMonitorChart'+idx); if(!cv) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...c.livePrices)*0.9995, mx=Math.max(...c.livePrices)*1.0005; const minRange=c.startPrice*0.002; let mn2=mn, mx2=mx; if((mx-mn)<minRange){{ const mid=(mn+mx)/2; mn2=mid-minRange/2; mx2=mid+minRange/2; }} function yF(p){{return h*0.85-((p-mn2)/(mx2-mn2||minRange))*h*0.7;}} ctx.strokeStyle='#1a1a1a'; for(let i=0;i<2;i++){{const y=h*0.1+i*h*0.8; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const startY=yF(c.startPrice); ctx.strokeStyle='#fc0'; ctx.setLineDash([3,3]); ctx.beginPath(); ctx.moveTo(0,startY); ctx.lineTo(w,startY); ctx.stroke(); ctx.setLineDash([]); ctx.strokeStyle=c.livePrices[c.livePrices.length-1]>=c.startPrice?'#0f8':'#f44'; ctx.lineWidth=1.5; ctx.beginPath(); c.livePrices.forEach((p,i)=>{{const x=i/(c.livePrices.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); }}
    function finishMovingLiveMonitor(){{let summary=currentAnalysis.coins.map(c=>{{ const deep=c.deep||{{}}; const change=c.liveChange||0; let finalSide=c.finalSide||deep.side||'LONG'; let reason=''; if(finalSide=='LONG'){{ reason='Graph up sense: SMA '+(deep.sma5>deep.sma10?'5>10 up':'5<10 down')+' + 5m '+deep.mom_5.toFixed(3)+'% + 30m '+deep.mom_30.toFixed(2)+'% + live '+change.toFixed(3)+'% up + RSI '+deep.rsi.toFixed(0)+' -> LONG'; }} else{{ reason='Graph down sense: SMA '+(deep.sma5<deep.sma10?'5<10 down':'5>10 up')+' + 5m '+deep.mom_5.toFixed(3)+'% + 30m '+deep.mom_30.toFixed(2)+'% + live '+change.toFixed(3)+'% down + RSI '+deep.rsi.toFixed(0)+' -> SHORT'; }} c.finalReason=reason+' | move='+deep.moving_score.toFixed(2)+' vol='+deep.volatility.toFixed(2)+'%'; return c.symbol+' '+finalSide+' '+change.toFixed(3)+'% move='+c.moving_score.toFixed(1); }}).join('\\n'); document.getElementById('finalDecision').innerText='✅ FINAL MOST MOVING GRAPH SENSE PREDICTION:\\n'+summary; document.getElementById('finalReason').innerText=currentAnalysis.coins.map(c=>c.symbol+': '+c.finalReason).join('\\n'); document.getElementById('liveMonitorText').innerText='✅ 3 MOST MOVING 1M LIVE DONE - Graph sense predicts LONG/SHORT from movement - Auto-opening...'; document.getElementById('autoStatus').innerText='🤖 AUTO-OPENING 3 MOST MOVING trades NOW - Graph sense LONG/SHORT...\\n'+summary+'\\nAttempt '+(retryCount+1)+'/3...'; document.getElementById('forceOpenBtn').style.display='block'; setTimeout(()=>{{ autoConfirm3Trades(); }},1000); }}
    async function autoConfirm3Trades(){{retryCount++; document.getElementById('autoStatus').innerText='🤖 Opening 3 most moving trades... Attempt '+retryCount+'/3\\n'+currentAnalysis.coins.map(c=>c.symbol+' '+c.finalSide+' $'+(c.livePrice||c.startPrice).toFixed(4)+' move='+c.moving_score.toFixed(1)).join(' | '); logError('Attempt '+retryCount+' most moving:'+currentAnalysis.coins.map(c=>c.symbol+' '+c.finalSide+' move='+c.moving_score.toFixed(1)).join(',')); let successCount=0; let errors=[]; for(let i=0;i<currentAnalysis.coins.length;i++){{ const c=currentAnalysis.coins[i]; try{{ const payload={{symbol:c.symbol, side:c.finalSide, reason:c.finalReason.substring(0,200), livePrice:c.livePrice||c.startPrice, moving_score:c.moving_score}}; logError('Opening '+c.symbol+' '+c.finalSide+' move='+c.moving_score.toFixed(1)+' price '+(c.livePrice||c.startPrice)); const r=await fetch('/api/open_analyzed?key='+ADMIN_KEY+'&t='+Date.now(), {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload)}}); const text=await r.text(); logError(c.symbol+' resp: '+text.substring(0,300)); let j; try{{ j=JSON.parse(text); }}catch(e){{ errors.push(c.symbol+' JSON fail:'+text.substring(0,100)); continue; }} if(j.ok){{ successCount++; logError(c.symbol+' SUCCESS $'+j.entry+' move='+c.moving_score.toFixed(1)); }} else{{ errors.push(c.symbol+' FAIL:'+(j.error||'unknown')); logError(c.symbol+' FAIL '+j.error); }} }}catch(e){{ errors.push(c.symbol+' EX:'+e); logError(c.symbol+' EX '+e); }} await new Promise(r=>setTimeout(r,700)); }} document.getElementById('autoStatus').innerText='✅ Opened '+successCount+'/'+currentAnalysis.coins.length+' most moving trades\\n'+currentAnalysis.coins.map(c=>c.symbol+' '+c.finalSide+' move='+c.moving_score.toFixed(1)).join(' | ')+'\\nErrors: '+errors.join('; ').substring(0,200)+'\\nReloading...'; if(successCount>0){{ setTimeout(()=>{{ closeOverlay(); location.reload(); }},2000); }} else{{ document.getElementById('autoStatus').innerText+='\\n❌ All failed: '+errors.join('; ')+'\\nWill keep FORCE button'; }} }}
    function closeOverlay(){{ document.getElementById('analyzeOverlay').classList.remove('show'); currentAnalysis=null; }}
    async function callReset(){{if(!confirm('RESET MOVING v13?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
    async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
    async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}
    function initChart(sym,entry,tp,sl,side,openTs,initialAge,cg_id){{const cv=document.getElementById('chart-'+sym); if(!cv) return; const ctx=cv.getContext('2d'); let prices = []; let liveHistory = []; let ageSec = initialAge; const ageEl=document.getElementById('live-age-'+sym); setInterval(()=>{{ ageSec += 1; const m=Math.floor(ageSec/60); const s=ageSec%60; if(ageEl) ageEl.innerText=m+'m '+s+'s'; }},1000); async function fetchPrice(){{let price=null; try{{ const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const txt=await r.text(); let j; try{{ j=JSON.parse(txt); }}catch(e){{ return; }} if(j.price && j.price>0) price=j.price; }}catch(e){{}} if(!price) return; const pct=side=='LONG'?(price-entry)/entry*100:(entry-price)/entry*100; if(Math.abs(pct)>30 && ageSec<300) return; const elP=document.getElementById('live-price-'+sym); const elC=document.getElementById('live-change-'+sym); const elPn=document.getElementById('live-pnl-'+sym); const dot=document.getElementById('live-dot-'+sym); if(elP){{elP.innerText='$'+price.toFixed(5); elP.style.color=pct>=0?'#0f8':'#f44';}} if(elC){{elC.innerText=pct.toFixed(3)+'%'; elC.style.color=pct>=0?'#0f8':'#f44';}} if(elPn){{ elPn.innerText=(pct>=0?'+':'')+'$'+(100*pct/100*0.3333).toFixed(2)+' / $1.00'; elPn.style.color=pct>=0?'#0f8':'#f44';}} if(dot) dot.innerText='● V859 MOVING '+new Date().toLocaleTimeString()+' '+pct.toFixed(3)+'% move'; liveHistory.push(price); if(liveHistory.length>60) liveHistory.shift(); prices = [...liveHistory]; draw(); if(pct >= TP_PCT){{ if(dot) dot.innerText='● TP HIT '+pct.toFixed(2)+'% - AUTO CLOSING'; setTimeout(async()=>{{ await fetch('/api/close?symbol='+sym+'&key='+ADMIN_KEY); location.reload(); }},1500); }} }} async function fetchKlines(){{try{{ const r=await fetch('/api/klines?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const txt=await r.text(); let j; try{{ j=JSON.parse(txt); }}catch(e){{ return; }} if(j.closes && j.closes.length>10){{ let kl = j.closes.filter(p=>p>0); if(liveHistory.length<5){{ prices = kl.slice(-30); liveHistory = [...kl.slice(-30)]; }} draw(); }} }}catch(e){{}}}} function draw(){{const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); if(prices.length<2){{ prices = Array(20).fill(entry).map((v,i)=> v + (Math.random()-0.5)*entry*0.0003); }} const usePrices = prices; let displayPrices = usePrices.map(p=>{{ let rawPct = (p-entry)/entry*100; let ampPct = rawPct; if(Math.abs(rawPct)<0.6) ampPct = rawPct*4; return entry * (1 + ampPct/100); }}); const allAmp = [...displayPrices, entry]; let mn=Math.min(...allAmp)*0.9995; let mx=Math.max(...allAmp)*1.0005; const minRange = entry*0.006; const mid = (mn+mx)/2; if((mx-mn) < minRange){{ mn=mid-minRange/2; mx=mid+minRange/2; }} const rg=mx-mn||entry*0.001; function yF(p){{return h*0.85-((p-mn)/rg)*h*0.7;}} ctx.strokeStyle='#1a1a1a'; ctx.lineWidth=1; for(let i=0;i<5;i++){{const y=h*0.1+i*h*0.8/4; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const entryY=yF(entry); ctx.strokeStyle='#fc0'; ctx.lineWidth=3; ctx.beginPath(); ctx.moveTo(0,entryY); ctx.lineTo(w,entryY); ctx.stroke(); ctx.fillStyle='#fc0'; ctx.font='bold 11px monospace'; ctx.fillText('ENTRY '+entry.toFixed(5),4,entryY-5); const tpDisplay = entry*(1+((tp-entry)/entry*100)*4/100); let tpY=yF(tpDisplay); if(tpY<0) tpY=5; if(tpY>h) tpY=h-5; ctx.strokeStyle='#0f8'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.fillStyle='#0f8'; ctx.font='9px monospace'; ctx.fillText('TP '+tp.toFixed(5)+' $1.00',4,tpY-3); ctx.setLineDash([]); const slDisplay = entry*(1+((sl-entry)/entry*100)*4/100); let slY=yF(slDisplay); if(slY<0) slY=5; if(slY>h) slY=h-5; ctx.strokeStyle='#f44'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,slY); ctx.lineTo(w,slY); ctx.stroke(); ctx.fillStyle='#f44'; ctx.fillText('SL '+sl.toFixed(5),4,slY+11); ctx.setLineDash([]); ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=3; ctx.beginPath(); displayPrices.forEach((p,i)=>{{const x=i/(displayPrices.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=displayPrices[displayPrices.length-1]; const ly=yF(last); ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(w-8,ly,5,0,Math.PI*2); ctx.fill(); ctx.fillStyle=last>=entry?'#0f8':'#f44'; ctx.beginPath(); ctx.arc(w-8,ly,3.5,0,Math.PI*2); ctx.fill();}} draw(); fetchKlines(); fetchPrice(); setInterval(fetchPrice, 3000); setInterval(fetchKlines, 20000);}}window.addEventListener('load',()=>{{drawEquity(); {chart_js_init}}});</script></body></html>"""
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
        closes, vols = fetch_klines(base, "1m", 30)
        if closes: return Response(json.dumps({"symbol":sym,"closes":closes}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
        from math import sin
        fake=[83670 + sin(i/5)*50 for i in range(30)]
        return Response(json.dumps({"symbol":sym,"closes":fake}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/scan_most_moving"):
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
                closes, vols = fetch_klines(base, "1m", 30)
                if not closes:
                    closes, vols = fetch_klines(base, "5m", 30)
                if not closes:
                    continue
                price, src = fetch_live_price_fast(base)
                if not price or price==0:
                    price=closes[-1] if closes else 100
                analysis=analyze_most_moving(closes, vols)
                analysis["symbol"]=base
                analysis["price"]=price
                analysis["src"]=src
                analysis["shark"]=shark
                analysis["closes"]=closes
                movers.append(analysis)
            # Sort by moving_score descending = most moving first
            movers_sorted=sorted(movers, key=lambda x: x["moving_score"], reverse=True)
            # Ensure distinct symbols (already distinct from batch) and pick top 3
            top3=movers_sorted[:3]
            # If less than 3, fill with fallback
            if len(top3)<slots_left:
                for base,shark in STATIC_TOP:
                    if len(top3)>=slots_left: break
                    if base in [m["symbol"] for m in top3] or base in open_syms: continue
                    price, src = fetch_live_price_fast(base)
                    if not price: price=100
                    closes, vols = fetch_klines(base, "1m", 30)
                    if not closes: closes=[price]*30
                    analysis=analyze_most_moving(closes, vols)
                    analysis["symbol"]=base
                    analysis["price"]=price
                    analysis["src"]=src
                    analysis["shark"]=shark
                    analysis["closes"]=closes
                    top3.append(analysis)
            # Update offset
            state["scan_offset"]=(offset+SCAN_BATCH)%TOP_N
            state["scan"]=state.get("scan",0)+1
            state["full_scans"]=state.get("scan",0)//(TOP_N//SCAN_BATCH)
            state["last_cron"]=f"v859 MOVING SCAN offset {offset}->{state['scan_offset']} movers {','.join([m['symbol']+':'+str(round(m['moving_score'],1)) for m in top3])} INV {current_inv:.0f}/{cap:.0f}"
            kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":True,"movers":movers_sorted,"top3":top3,"offset":offset,"scan":state["scan"],"full_scans":state["full_scans"],"inv":current_inv,"cap":cap}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
        except Exception as e:
            import traceback
            return Response(json.dumps({"ok":False,"error":str(e)[:200],"trace":traceback.format_exc()[:400]}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/deep30m"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper(); base=sym.replace("USDT","")
        closes, vols = fetch_klines(base, "1m", 30)
        if not closes:
            closes, vols = fetch_klines(base, "5m", 30)
        if not closes:
            from math import sin
            closes=[83670 + sin(i/4)*30 + i*2 for i in range(30)]
            vols=[1000]*30
        analysis=analyze_most_moving(closes, vols)
        return Response(json.dumps({"ok":True,"symbol":sym,"closes":closes,"vols":vols,"analysis":analysis}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/open_analyzed"):
        if key!=ADMIN_KEY: 
            return Response(json.dumps({"ok":False,"error":"Forbidden key"}), mimetype="application/json", status=403, headers={"Access-Control-Allow-Origin":"*"})
        try:
            data=None
            body_text=request.get_data(as_text=True) or ""
            if request.method=="POST":
                try:
                    data=request.get_json(force=True, silent=True)
                    if not data and body_text:
                        data=json.loads(body_text)
                except:
                    try:
                        data=json.loads(body_text) if body_text else {}
                    except:
                        data={}
                sym=(data.get("symbol","") if data else "").upper() or request.args.get("symbol","").upper()
                side=(data.get("side","") if data else "") or request.args.get("side","LONG")
                reason=(data.get("reason","") if data else "") or request.args.get("reason","v859 moving sense")
                live_price_fallback=data.get("livePrice") if data else None
                moving_score=data.get("moving_score",0) if data else 0
            else:
                sym=request.args.get("symbol","").upper()
                side=request.args.get("side","LONG")
                reason=request.args.get("reason","v859 moving sense")
                live_price_fallback=request.args.get("livePrice", type=float)
                moving_score=0
            if not sym:
                return Response(json.dumps({"ok":False,"error":"no symbol"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
            if side not in ["LONG","SHORT"]: side="LONG"
            state=load_state()
            current_inv=sum([t.get("pos",0) for t in state.get("open",[])])
            cap=state.get("cap",300.0)
            # Check duplicate - prevent same symbol 3 times
            open_syms=[t["symbol"] for t in state.get("open",[])]
            if sym in open_syms:
                return Response(json.dumps({"ok":False,"error":f"{sym} already open INV {current_inv:.0f}/{cap:.0f}","inv":current_inv,"cap":cap}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
            if len(state.get("open",[]))>=MAXP:
                return Response(json.dumps({"ok":False,"error":f"MAXP {MAXP} reached INV {current_inv:.0f}/{cap:.0f}","inv":current_inv,"cap":cap}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
            price, src = fetch_live_price_fast(sym)
            if (not price or price==0) and live_price_fallback and live_price_fallback>0:
                price=float(live_price_fallback)
                src="fallback livePrice v859"
            if not price or price==0:
                price=83670 if sym=="BTC" else 2500 if sym=="ETH" else 145
                src="ultimate fallback est v859"
            pos_size=cap*POS_PCT/100.0
            if current_inv+pos_size>cap: pos_size=(cap-current_inv)*0.95
            if pos_size<10: pos_size=10
            tr={"symbol":sym,"side":side,"entry":price,"price":price,"pos":pos_size,"ts":int(time.time()),"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":60,"tp":TP_PCT,"sl":SL_PCT,"reason":f"$1.00 MOVING v859 {side} ${price:.4f} {src} {reason[:80]} POS ${pos_size:.0f}/{cap:.0f} MOVE {moving_score:.1f}","rsi":50,"shark":60,"atr":1.0,"vol":50000000,"cg_id":SYM_TO_ID.get(sym,""),"analysis":reason[:200],"moving_score":moving_score}
            state["open"].append(tr)
            state["scan"]=state.get("scan",0)+1
            state["scan_offset"]=(state.get("scan_offset",0)+1)%TOP_N
            state["full_scans"]=state.get("scan",0)//(TOP_N//SCAN_BATCH)
            state["last_cron"]=f"v859 MOVING OPEN {sym} {side} ${price:.4f} MOVE {moving_score:.1f} {src} INV {current_inv+pos_size:.0f}/{cap:.0f} SCAN {state.get('scan',0)} POST_OK"
            eq=state.get("equity",[300]); eq.append(cap); state["equity"]=eq[-150:]
            ok=kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":True,"symbol":sym,"side":side,"entry":price,"pos":pos_size,"inv":current_inv+pos_size,"cap":cap,"reason":reason,"src":src,"moving_score":moving_score,"fix":"v859 MOVING SENSE"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
        except Exception as e:
            import traceback
            tb=traceback.format_exc()
            return Response(json.dumps({"ok":False,"error":str(e)[:200],"trace":tb[:400]}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); time.sleep(0.3)
        new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0],"last_cron":"reset v859 MOVING TRUE CLEAN"}
        ok=kv_set(STATE_KEY,new)
        return Response(json.dumps({"ok":ok,"cap":300,"cleared":True,"fix":"v859 MOVING"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]):
            lp,_=fetch_live_price_fast(tr["symbol"])
            if lp and lp>0:
                pct=(lp-tr["entry"])/tr["entry"]*100 if tr["side"]=="LONG" else (tr["entry"]-lp)/tr["entry"]*100
                pct_net=pct-TOTAL_FEE; net=tr["pos"]*pct_net/100
            else: net=tr.get("net",0)
            cap+=net; state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":net,"reason":f"CLOSE ALL LIVE ${lp if lp else 0:.5f} v859 MOVING","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"moving_score":tr.get("moving_score",0)})
        state["open"]=[]; state["cap"]=cap; state=recalc(state); state["peak"]=max(state.get("peak",cap),cap); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"cap":cap,"fix":"v859 MOVING"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
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
                cap+=net; state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":net,"reason":f"CLOSE {sym} LIVE ${lp if lp else 0:.5f} v859 MOVING","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0)})
            else: final.append(tr)
        state["open"]=final; state["cap"]=cap; state=recalc(state); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"closed":sym,"cap":cap,"fix":"v859 MOVING"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    if p.startswith("/api/debug") or p.startswith("/api/envcheck"):
        return Response(json.dumps({"kv_url":bool(KV_URL),"kv_token":bool(KV_TOKEN),"mem_open":len(MEM_STATE.get("open",[])),"fix":"v859 MOVING SENSE","state":load_state()}, indent=2), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    try:
        st=load_state(); return Response(render(st), mimetype="text/html", headers={"Access-Control-Allow-Origin":"*"})
    except Exception as e:
        import traceback
        return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:2000]}</pre> FIX v859 MOVING</body></html>", mimetype="text/html", status=200, headers={"Access-Control-Allow-Origin":"*"})
