from flask import Flask, request, Response
import os, json, time, urllib.request
app = Flask(__name__)
def env(k):
    for kk in k:
        v=os.environ.get(kk)
        if v: return v.strip().strip('"').strip("'")
    return ""
KV_URL=(env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"]) or "").rstrip("/")
if not KV_URL:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "URL" in kk and "upstash" in vv.lower(): KV_URL=vv.strip().strip('"').strip("'").rstrip("/"); break
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
if not KV_TOKEN:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "TOKEN" in kk and "upstash" in kk.lower(): KV_TOKEN=vv.strip().strip('"').strip("'"); break
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V806_SMART"

POS_FIXED=100.0; MAXP=3; FEE_PCT=0.15; MAX_DAILY_LOSS_PCT=4.0
MIN_TP_PCT=1.0; MAX_TP_PCT=2.2; MAX_SL_PCT=0.85
TIME_EXIT_MIN=70

PERM_BLACKLIST=set(["MAGIC","ZEC","CFX","UNI","NEAR","TIA","ENA","LUMIA"])

SECTORS={"L1_CHAIN":["BTC","ETH","ARB","SUI","SEI","APT","TIA","AVAX","SOL","NEAR","OP","STRK","DOGE","CFX","ZEC"],"DEFI":["ENA","PENDLE","AERO","LDO","UNI","AAVE","BTC","ETH"],"MEME":["PEPE","BONK","WIF","FLOKI","SHIB","POPCAT","BRETT","DOGE"],"AI":["TAO","FET","RNDR","GRT"]}
COIN_SECTOR={c:sec for sec, coins in SECTORS.items() for c in coins}
BAD_EXACT=set(["USDC","FDUSD","TUSD","BUSD","DAI","USDP","1000PEPE","1000BONK","USDB"])
BAD_CONTAINS=["BIDR","IDRT","TRYB","EURT"]
def is_bad(b):
    if b in BAD_EXACT or b in PERM_BLACKLIST: return True
    for bad in BAD_CONTAINS:
        if bad in b: return True
    if len(b)>8 or b.startswith("1000"): return True
    return False
def get_sector(c): return COIN_SECTOR.get(c,"OTHER")

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
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r: return True
    except: return False

def get_tickers():
    try:
        req=urllib.request.Request("https://api.binance.com/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r: return json.loads(r.read().decode())
    except:
        try:
            req=urllib.request.Request("https://data-api.binance.vision/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r: return json.loads(r.read().decode())
        except: return []
def get_klines_fast(symbol, interval="15m", limit=50):
    try:
        url=f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data=json.loads(r.read().decode())
            return [{"c":float(x[4]),"h":float(x[2]),"l":float(x[3]),"v":float(x[5]),"o":float(x[1])} for x in data]
    except: return []
def calc_rsi(closes, period=14):
    if len(closes) < period+1: return 50
    gains=losses=0
    for i in range(1, period+1):
        diff=closes[-i]-closes[-i-1]
        if diff>=0: gains+=diff
        else: losses+=-diff
    if losses==0: return 70 if gains>0 else 50
    rs=gains/losses if losses!=0 else 0
    return 100 - (100/(1+rs))
def calc_atr(klines, period=14):
    if len(klines) < period+1: return klines[-1]["c"]*0.012 if klines else 0.01
    trs=[]
    for i in range(1, len(klines)):
        h=klines[i]["h"]; l=klines[i]["l"]; pc=klines[i-1]["c"]
        tr=max(h-l, abs(h-pc), abs(l-pc)); trs.append(tr)
    return sum(trs[-period:])/period if trs else klines[-1]["c"]*0.012
def calc_ema(closes, period):
    if len(closes) < period: return sum(closes)/len(closes) if closes else 0
    k=2/(period+1); ema=closes[0]
    for c in closes[1:]: ema=c*k + ema*(1-k)
    return ema

def calc_trend_strength(closes):
    if len(closes) < 20: return 0
    ema9 = calc_ema(closes, 9); ema21 = calc_ema(closes, 21)
    return abs(ema9 - ema21) / closes[-1] * 100 * 10

# === SMART BRAIN: Multi-timeframe BTC trend ===
def get_market_smart(ticker_map):
    klines_1h=get_klines_fast("BTCUSDT","1h",60)
    klines_15m=get_klines_fast("BTCUSDT","15m",60)
    if not klines_1h:
        btc_ticker=ticker_map.get("BTCUSDT"); btc_price=float(btc_ticker.get("lastPrice","70000")) if btc_ticker else 70000
        return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price,"rsi":50,"strength":0,"rsi_15":50,"ema20":btc_price,"ema50":btc_price,"reason":f"RANGING BTC {btc_price:.0f} NO DATA"}
    closes_1h=[k["c"] for k in klines_1h]
    closes_15m=[k["c"] for k in klines_15m] if klines_15m else closes_1h
    btc_price=closes_1h[-1]
    ema20_1h=calc_ema(closes_1h, 20); ema50_1h=calc_ema(closes_1h, 50)
    rsi_1h=calc_rsi(closes_1h, 14); rsi_15m=calc_rsi(closes_15m, 14)
    strength=calc_trend_strength(closes_1h)
    # trend score
    above_ema20 = btc_price > ema20_1h
    above_ema50 = btc_price > ema50_1h
    ema20_above_50 = ema20_1h > ema50_1h

    # SMART BIAS LOGIC
    if above_ema20 and above_ema50 and ema20_above_50 and rsi_1h>58 and rsi_15m>55 and strength>1.2:
        regime="TRENDING_BULL"; bias="LONG_ONLY"  # SMART: Block all shorts in strong bull
        reason=f"TRENDING_BULL BTC {btc_price:.0f} RSI {rsi_1h:.0f}/{rsi_15m:.0f} STR {strength:.1f} -> LONG ONLY"
    elif not above_ema20 and not above_ema50 and not ema20_above_50 and rsi_1h<42 and rsi_15m<45 and strength>1.2:
        regime="TRENDING_BEAR"; bias="SHORT_ONLY"
        reason=f"TRENDING_BEAR BTC {btc_price:.0f} RSI {rsi_1h:.0f}/{rsi_15m:.0f} STR {strength:.1f} -> SHORT ONLY"
    elif strength < 0.7:
        regime="RANGING"; bias="NONE"
        reason=f"RANGING BTC {btc_price:.0f} RSI {rsi_1h:.0f} STR {strength:.1f} -> NO TRADE"
    else:
        regime="WEAK_TREND"; bias="BOTH"
        reason=f"WEAK_TREND BTC {btc_price:.0f} RSI {rsi_1h:.0f} STR {strength:.1f} -> BOTH but strict"

    return {"regime":regime,"bias":bias,"btc_price":btc_price,"rsi":rsi_1h,"rsi_15":rsi_15m,"strength":strength,"ema20":ema20_1h,"ema50":ema50_1h,"reason":reason}

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        old=kv_get("VENUS_V805_REALTP") or kv_get("VENUS_V804_3X100") or kv_get("VENUS_V803_SUPER")
        if old: s=old; s["learn"]["pause_until"]=0
        else: s={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":"","last_coins":{}}}
    if "learn" not in s: s["learn"]={"blacklist":{},"pause_until":0,"last_date":"","last_coins":{}}
    L=s["learn"]; L.setdefault("blacklist",{}); L.setdefault("pause_until",0); L.setdefault("last_date",""); L.setdefault("last_coins",{})
    today=time.strftime("%Y-%m-%d")
    if L.get("last_date")!=today:
        s["daily"]=0.0; s["fees_paid"]=0.0; L["last_date"]=today; L["pause_until"]=0; L["last_coins"]={}
    now=int(time.time()); L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}; L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    return s

def do_cron():
    state=load_state(); L=state["learn"]; now_ts=int(time.time())
    if L.get("pause_until",0)>now_ts: return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"reason":"PAUSED"}
    if state.get("daily",0) < -state.get("cap",300)*MAX_DAILY_LOSS_PCT/100:
        L["pause_until"]=now_ts+3600*6; kv_set(STATE_KEY, state); return {"ok":False,"paused":True,"left":3600*6,"reason":f"DAILY -{MAX_DAILY_LOSS_PCT}% STOP"}
    tickers=get_tickers(); ticker_map={}; real=[]
    for t in tickers:
        sym=t.get("symbol",""); ticker_map[sym]=t
        if not sym.endswith("USDT"): continue
        base=sym.replace("USDT","")
        if is_bad(base): continue
        if not base.isalnum() or len(base)<2 or len(base)>7: continue
        real.append(t)
    real=sorted(real, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:15]
    market=get_market_smart(ticker_map)

    # SMART: Don't trade in RANGING/NONE
    if market["bias"]=="NONE":
        return {"ok":False,"paused":False,"scan":state.get("scan",0),"reason":f"SMART SKIP {market['regime']} - Waiting for trend","market":market["reason"]}

    open_tr=state.get("open",[]); open_syms=[t["symbol"] for t in open_tr]; candidates=[]

    for t in real:
        base=t.get("symbol","").replace("USDT","")
        if base in open_syms: continue
        if base in L.get("blacklist",{}): continue
        if base in L.get("last_coins",{}): continue
        vol=float(t.get("quoteVolume","0"))
        if vol<12000000: continue
        price=float(t.get("lastPrice","0")); klines=get_klines_fast(base+"USDT","15m",40)
        if len(klines)<30: continue
        closes=[k["c"] for k in klines]; rsi=calc_rsi(closes,14); atr=calc_atr(klines,14); atr_pct=(atr/price*100) if price else 1
        if atr_pct < 0.45 or atr_pct > 3.0: continue
        strength=calc_trend_strength(closes)
        if strength < 0.6 or strength > 7.0: continue
        if rsi < 22 or rsi > 78: continue
        ema20=calc_ema(closes,20); ema50=calc_ema(closes,50); last_c=closes[-1]
        
        # SMART COIN TREND
        coin_bull = last_c > ema20 and ema20 > ema50
        coin_bear = last_c < ema20 and ema20 < ema50

        side=None; reason=""
        # === SMART LONG/SHORT BRAIN ===
        if market["bias"]=="LONG_ONLY":
            # In bull market, ONLY long dips, never short
            if rsi < 34 and last_c < ema20*0.997 and coin_bull and strength>0.8:
                side="LONG"; reason=f"SMART LONG BULL DIP RSI {rsi:.0f} COIN BULL STR {strength:.1f}"
        elif market["bias"]=="SHORT_ONLY":
            if rsi > 66 and last_c > ema20*1.003 and coin_bear and strength>0.8:
                side="SHORT"; reason=f"SMART SHORT BEAR PUMP RSI {rsi:.0f} COIN BEAR STR {strength:.1f}"
        else: # BOTH weak trend - strict both
            if rsi < 28 and last_c < ema20*0.996 and coin_bull:
                side="LONG"; reason=f"SMART LONG WEAK RSI {rsi:.0f} STR {strength:.1f}"
            elif rsi > 72 and last_c > ema20*1.004 and coin_bear:
                side="SHORT"; reason=f"SMART SHORT WEAK RSI {rsi:.0f} STR {strength:.1f}"

        if side:
            tp_pct=min(atr*2.0/price*100, MAX_TP_PCT); sl_pct=min(atr*0.6/price*100, MAX_SL_PCT)
            if tp_pct < MIN_TP_PCT: continue
            if tp_pct/sl_pct < 2.0: continue
            score=(abs(rsi-50)+strength*12)*vol/1e7
            if score < 20: continue
            candidates.append({"symbol":base,"side":side,"price":price,"vol":int(vol),"sector":get_sector(base),"score":score,"tp":tp_pct,"sl":sl_pct,"rsi":rsi,"reason":reason,"strength":strength})

    candidates=sorted(candidates, key=lambda x: x["score"], reverse=True)[:3]

    closed=state.get("closed",[]); cap=state.get("cap",300.0); daily=state.get("daily",0.0); fees_paid=state.get("fees_paid",0.0); tot=state.get("total",0); scan=state.get("scan",0)+1
    final=[]
    for tr in open_tr:
        try:
            sym=tr["symbol"]+"USDT"
            price_now=float(ticker_map[sym].get("lastPrice",tr.get("price",tr.get("entry",0)))) if sym in ticker_map else tr.get("price",0)
            entry=tr.get("entry", price_now); side=tr.get("side","LONG")
            pct_gross=(price_now-entry)/entry*100 if side=="LONG" and entry else (entry-price_now)/entry*100 if entry else 0
            pct_net=pct_gross - FEE_PCT; pos_size=tr.get("pos",POS_FIXED); net_usd=pos_size*pct_net/100; age=now_ts-tr.get("ts",now_ts)
            peak_gross=max(tr.get("peak_gross",0), pct_gross)
            tr["price"]=price_now; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["peak_gross"]=peak_gross; tr["age"]=age; tr["net"]=net_usd
            tp=tr.get("tp",1.8); sl=tr.get("sl",0.75); should=None
            if pct_gross>=tp: should=f"TP {tp:.1f}% WIN +${net_usd:.2f}"
            elif pct_gross<=-sl: should=f"SL -{sl:.1f}% CUT ${net_usd:.2f}"
            elif peak_gross>=0.6 and pct_gross<=0.10: should=f"BE_PROTECT {peak_gross:.1f}%->+0.1% LOCK"
            elif peak_gross>=tp*0.5 and pct_gross<peak_gross-0.5: should=f"TRAIL {peak_gross:.1f}%->{pct_gross:.1f}%"
            elif age>TIME_EXIT_MIN*60 and pct_gross < 0.20: should=f"TIME {TIME_EXIT_MIN}m"
            if pct_net < -0.85: should=f"MAXLOSS -0.85% ${net_usd:.2f}"
            if should:
                cap+=net_usd; daily+=net_usd; fees_paid+=FEE_PCT*pos_size/100; tot+=1
                closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"pos":pos_size})
                L["last_coins"][tr["symbol"]]=now_ts+1200
                if pct_net<-0.65: L["blacklist"][tr["symbol"]]=now_ts+10800
            else: final.append(tr)
        except: final.append(tr)
    wins=sum(1 for c in closed if c.get("net",0)>0); loss=sum(1 for c in closed if c.get("net",0)<0)
    for sh in candidates:
        if len(final)>=MAXP: break
        if sh["symbol"] in [t["symbol"] for t in final]: continue
        pos_size=POS_FIXED
        if cap < 20: break
        if pos_size > cap: pos_size=cap*0.9
        if pos_size < 20: continue
        tr={"symbol":sh["symbol"],"side":sh["side"],"entry":sh["price"],"price":sh["price"],"pos":pos_size,"ts":now_ts,"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":sh["score"],"sector":sh["sector"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"rsi":sh["rsi"]}
        final.append(tr)
    state["open"]=final; state["closed"]=closed[:300]; state["cap"]=cap; state["daily"]=daily; state["fees_paid"]=fees_paid; state["wins"]=wins; state["loss"]=loss; state["total"]=tot; state["scan"]=scan; state["market"]=market
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan,"open":len(final),"cap":cap,"daily":daily,"candidates":len(candidates),"market":market["reason"],"bias":market["bias"]}

def render(state):
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300.0); daily=state.get("daily",0.0); fees_paid=state.get("fees_paid",0.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0)
    market=state.get("market",{"regime":"RANGING","bias":"BOTH","btc_price":70000,"rsi":50,"rsi_15":50,"reason":"Tap CRON","strength":0})
    winrate=int(wins/tot*100) if tot>0 else 0; unreal=sum([t.get("net",0) for t in open_tr]); long_open=sum(1 for t in open_tr if t.get("side")=="LONG"); short_open=sum(1 for t in open_tr if t.get("side")=="SHORT")
    gross_profit=sum([c.get("net",0) for c in closed if c.get("net",0)>0]); gross_loss=sum([c.get("net",0) for c in closed if c.get("net",0)<0])
    avg_win=gross_profit / wins if wins>0 else 0; avg_loss=gross_loss / loss if loss>0 else 0
    profit_factor=abs(gross_profit / gross_loss) if gross_loss!=0 else (gross_profit if gross_profit>0 else 0); expectancy=(gross_profit + gross_loss) / tot if tot>0 else 0
    best=max(closed, key=lambda x: x.get("net",0)) if closed else None; worst=min(closed, key=lambda x: x.get("net",0)) if closed else None
    invested=sum([t.get("pos",0) for t in open_tr]); bias_color="#00ff88" if market.get("bias")=="LONG_ONLY" else "#ff4444" if market.get("bias")=="SHORT_ONLY" else "#ffcc00"
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>
    body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}}
   .h{{background:linear-gradient(90deg,#00ff88,#ffcc00,#00d4ff);color:#000;padding:14px;text-align:center;font-weight:900;font-size:12px;border-radius:12px}}
   .g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:10px}}
   .stats{{background:#111;border:2px solid {bias_color};padding:12px;margin:8px 0;border-radius:12px}}
   .it{{background:#111;border:1px solid #333;padding:12px;margin:8px 0;border-radius:12px}}
   .btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:12px 0}}
   .btn{{padding:18px 6px;border-radius:16px;border:0;font-weight:900;font-size:14px;cursor:pointer}}
   .btn-cron{{background:#00ff88;color:#000}}.btn-reset{{background:#ff4444;color:#fff}}.btn-close{{background:#ffcc00;color:#000}}
   .badge{{padding:3px 8px;border-radius:20px;font-size:10px;font-weight:900}}.long{{background:#00ff88;color:#000}}.short{{background:#ff4444;color:#fff}}
    </style></head><body>
    <div class='h'>VENUS v806 SMART BRAIN - SCAN #{scan} - ${cap:.2f} L:{long_open} S:{short_open} {market.get('regime')} BIAS {market.get('bias')} BTC ${market.get('btc_price',0):.0f}</div>
    <div class='btn-row'>
      <button class='btn btn-cron' onclick='callCron()'><span>⚡</span>CRON<div id='cronStat' style='font-size:11px'>TAP</div></button>
      <button class='btn btn-close' onclick='closeAll()'><span>💰</span>CLOSE ALL<div style='font-size:11px'>{len(open_tr)} OPEN ${invested:.0f}</div></button>
      <button class='btn btn-reset' onclick='callReset()'><span>🔄</span>RESET<div style='font-size:11px'>CAP $300</div></button>
    </div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:20px;color:#ffcc00'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}<br>INV ${invested:.0f}</div>
    <div class='c'>TODAY<br><b style='font-size:20px;color:{"#f44" if daily<0 else "#0f8"}'>${daily:+.2f}</b><br>W:{wins} L:{loss} {winrate}%<br>FEES ${fees_paid:.2f}<br>3x${POS_FIXED:.0f}</div>
    <div class='c' style='border-color:{bias_color}'>SMART BRAIN<br><b style='color:{bias_color}'>{market.get('bias')}</b><br>{market.get('regime')}<br>BTC ${market.get('btc_price',0):.0f} RSI {market.get('rsi',50):.0f}/{market.get('rsi_15',50):.0f}<br>STR {market.get('strength',0):.2f}</div></div>
    <div class='stats'>
      <div style='color:{bias_color};font-weight:900;font-size:13px'>🧠 SMART LONG/SHORT BRAIN - BIAS: {market.get('bias')}</div>
      <div style='margin-top:6px;font-size:11px;color:#eee'>{market.get('reason','')}</div>
      <div style='display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px'>
        <div>TOTAL: <b>{tot}</b></div><div>WIN: <b style='color:#0f8'>{wins}</b> | LOSS: <b style='color:#f44'>{loss}</b> | <b>{winrate}%</b></div>
        <div>AVG WIN: <b style='color:#0f8'>${avg_win:.2f}</b></div><div>AVG LOSS: <b style='color:#f44'>${avg_loss:.2f}</b> {'✅' if abs(avg_win) > abs(avg_loss) else '❌ FIX NEEDED'}</div>
        <div>PF: <b style='color:{"#0f8" if profit_factor>1.5 else "#ffcc00"}'>{profit_factor:.2f}</b></div><div>EXP: <b>${expectancy:.3f}</b></div>
        <div>BEST: <b>{best.get('symbol','-') if best else '-'} ${best.get('net',0):+.2f}</b></div><div>WORST: <b>{worst.get('symbol','-') if worst else '-'} ${worst.get('net',0):+.2f}</b></div>
      </div>
      <div style='margin-top:8px;color:#00ff88;font-size:11px'>✅ SMART: Bull= LONG ONLY blocks shorts | Bear= SHORT ONLY blocks longs | Ranging= NO TRADE | Coin must match BTC trend</div>
      <div style='color:#888;font-size:10px'>TP max {MAX_TP_PCT}% SL max {MAX_SL_PCT}% RR 3:1 | LUMIA/MAGIC blacklisted | RSI 22-78 filter</div>
    </div>
    <div class='it' style='border-color:{bias_color};color:{bias_color};text-align:center;font-weight:900'>{market.get('reason','Tap CRON')}<br><small>Scan #{scan} v806 SMART {market.get('bias')}</small></div>
    <div id='openbox'>"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class='it' style='border-color:{col}'><b style='color:{col}'>{tr['symbol']} <span class='badge {tr.get('side','').lower()}'>{tr.get('side')}</span> ${tr.get('pos',0):.0f}</b>
        <button onclick='closeOne("{tr['symbol']}")' style='float:right;background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 12px'>✕</button><br>
        PEAK {tr.get('peak_gross',0):.2f}% <b>{tr.get('pct_gross',0):.3f}% NET ${tr.get('net',0):+.2f}</b> TP {tr.get('tp',0):.2f}% SL {tr.get('sl',0):.2f}%<br>
        <small>{tr.get('reason','')}</small></div>"""
    if not open_tr: html+=f"<div class='it' style='text-align:center;color:#666'>No open. Smart brain waiting for correct BIAS {market.get('bias')}. Tap CRON.</div>"
    html+=f"""</div><div style='background:#111;padding:12px;margin:8px 0;border-radius:12px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% - PF {profit_factor:.2f} - BIAS {market.get('bias')}</div>"""
    for cl in closed[:25]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"
        html+=f"<div style='padding:6px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')} {cl.get('side','')} ${cl.get('pos',POS_FIXED):.0f}</b> ${cl.get('net',0):+.2f} {cl.get('pct_net',0):+.2f}% | {cl.get('reason','')}</div>"
    html+=f"""</div><script>const ADMIN_KEY="{ADMIN_KEY}";
    async function callCron(){{const b=document.getElementById('cronStat'); b.innerText='...'; try{{const r=await fetch('/api/cron?key='+ADMIN_KEY); const j=await r.json(); b.innerText=j.ok ? 'OK '+j.bias : j.reason; if(j.ok) setTimeout(()=>location.reload(),1000);}}catch(e){{b.innerText='ERR';}} }}
    async function callReset(){{if(!confirm('RESET v806?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
    async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
    async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}
    </script></body></html>"""
    return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    key=request.args.get("key",""); p="/"+path
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try: res=do_cron(); return Response(json.dumps(res), mimetype="application/json")
        except Exception as e: return Response(json.dumps({"ok":False,"error":str(e)[:500]}), mimetype="application/json", status=200)
    if p.startswith("/api/debug"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps({"KV_URL":bool(KV_URL),"KV_TOKEN":bool(KV_TOKEN),"STATE_KEY":STATE_KEY,"state":load_state()}), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); time.sleep(0.4)
        new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}}
        ok=kv_set(STATE_KEY, new); return Response(json.dumps({"ok":ok,"cap":300}), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]): cap+=tr.get("net",0); state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":"MANUAL CLOSE ALL","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0)})
        state["open"]=[]; state["cap"]=cap; kv_set(STATE_KEY, state); return Response(json.dumps({"ok":True}), mimetype="application/json")
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); state=load_state(); cap=state.get("cap",300.0); final=[]
        for tr in state.get("open",[]):
            if tr["symbol"]==sym: cap+=tr.get("net",0); state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE {sym}","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0)})
            else: final.append(tr)
        state["open"]=final; state["cap"]=cap; kv_set(STATE_KEY, state); return Response(json.dumps({"ok":True,"closed":sym}), mimetype="application/json")
    try: st=load_state(); return Response(render(st), mimetype="text/html")
    except Exception as e:
        import traceback; return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:800]}</pre></body></html>", mimetype="text/html", status=200)
