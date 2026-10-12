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
        if "REDIS" in kk and "URL" in kk and "upstash" in vv.lower():
            KV_URL=vv.strip().strip('"').strip("'").rstrip("/"); break
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
if not KV_TOKEN:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "TOKEN" in kk and "upstash" in kk.lower():
            KV_TOKEN=vv.strip().strip('"').strip("'"); break
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V808_SHARK100"
POS_FIXED=100.0; MAXP=3; FEE_PCT=0.15; MAX_DAILY_LOSS_PCT=4.5; MIN_TP_PCT=0.70; MAX_TP_PCT=2.4; MAX_SL_PCT=0.85; TIME_EXIT_MIN=45; SCAN_BATCH=10; TOP_N=100
PERM_BLACKLIST=set(["MAGIC","ZEC","CFX","UNI","NEAR","TIA","ENA","LUMIA","STRK","DOGE"])
SECTORS={"L1_CHAIN":["BTC","ETH","ARB","SUI","SEI","APT","TIA","AVAX","SOL","NEAR","OP","STRK","DOGE","CFX","ZEC"],"DEFI":["ENA","PENDLE","AERO","LDO","UNI","AAVE","BTC","ETH"],"MEME":["PEPE","BONK","WIF","FLOKI","SHIB","POPCAT","BRETT","DOGE"],"AI":["TAO","FET","RNDR","GRT"]}
COIN_SECTOR={c:sec for sec, coins in SECTORS.items() for c in coins}
BAD_EXACT=set(["USDC","FDUSD","TUSD","BUSD","DAI","USDP","1000PEPE","1000BONK","USDB","EUR","BIDR","IDRT","币安人生"])
BAD_CONTAINS=["BIDR","IDRT","TRYB","EURT"]
def is_bad(b):
    if not b.isascii(): return True
    if b in BAD_EXACT or b in PERM_BLACKLIST: return True
    for bad in BAD_CONTAINS:
        if bad in b: return True
    if len(b)>8 or b.startswith("1000") or not b.isalnum(): return True
    return False
def get_sector(c): return COIN_SECTOR.get(c,"OTHER")

def kv_get(k):
    if not KV_URL or not KV_TOKEN: return None
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=6) as r:
            d=json.loads(r.read().decode()); res=d[0].get("result") if isinstance(d,list) and d else None
            if not res: return None
            return json.loads(res) if (res.startswith("{") or res.startswith("[")) else res
    except: return None
def kv_set(k,o):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["SET",k,json.dumps(o)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=6) as r: return "OK" in r.read().decode()
    except: return False
def kv_del(k):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r: return True
    except: return False

def get_tickers():
    for url in ["https://api.binance.com/api/v3/ticker/24hr","https://data-api.binance.vision/api/v3/ticker/24hr"]:
        try:
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=7) as r:
                data=json.loads(r.read().decode())
                if len(data)>50: return data
        except: continue
    return []
def get_klines_fast(symbol, interval="15m", limit=50):
    for base in ["https://api.binance.com","https://data-api.binance.vision"]:
        try:
            url=f"{base}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                if len(data)>10:
                    return [{"c":float(x[4]),"h":float(x[2]),"l":float(x[3]),"v":float(x[5]),"o":float(x[1]),"t":x[0]} for x in data]
        except: continue
    return []

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
def detect_shark(klines, ticker):
    if len(klines) < 25: return 0, "no data"
    volumes = [k["v"] for k in klines[-21:-1]]; avg_vol = sum(volumes)/len(volumes) if volumes else 1
    last_vol = klines[-1]["v"]; prev_vol = klines[-2]["v"] if len(klines)>1 else avg_vol
    vol_spike = last_vol / avg_vol if avg_vol>0 else 1; vol_accel = last_vol / prev_vol if prev_vol>0 else 1
    closes = [k["c"] for k in klines]; price_change_1 = (closes[-1]/closes[-2]-1)*100 if len(closes)>=2 else 0
    shark_score = 0; reason=[]
    if vol_spike > 2.5: shark_score+=40; reason.append(f"VOLx{vol_spike:.1f}")
    elif vol_spike > 1.6: shark_score+=20; reason.append(f"volx{vol_spike:.1f}")
    if vol_accel > 1.8: shark_score+=20; reason.append(f"ACCx{vol_accel:.1f}")
    if abs(price_change_1) > 1.0 and vol_spike > 1.4: shark_score+=25; reason.append(f"MOVE {price_change_1:+.1f}%")
    last = klines[-1]; body_pct = abs(last["c"]-last["o"])/last["c"]*100 if last["c"] else 0
    if body_pct > 0.8 and vol_spike>1.4: shark_score+=10; reason.append(f"BODY {body_pct:.1f}%")
    return min(shark_score,100), " ".join(reason) if reason else "no shark"

def get_market_smart(ticker_map):
    klines_1h=get_klines_fast("BTCUSDT","1h",60); klines_15m=get_klines_fast("BTCUSDT","15m",60)
    btc_ticker=ticker_map.get("BTCUSDT"); btc_price=float(btc_ticker.get("lastPrice","84000")) if btc_ticker else 84000
    if not klines_1h: return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price,"rsi":50,"rsi_15":50,"strength":0,"reason":f"RANGING BTC {btc_price:.0f} NO KLINES - TICKER ONLY"}
    closes_1h=[k["c"] for k in klines_1h]; closes_15m=[k["c"] for k in klines_15m] if klines_15m else closes_1h
    btc_price=closes_1h[-1]; ema20_1h=calc_ema(closes_1h, 20); ema50_1h=calc_ema(closes_1h, 50)
    rsi_1h=calc_rsi(closes_1h, 14); rsi_15m=calc_rsi(closes_15m, 14); strength=calc_trend_strength(closes_1h)
    above_ema20 = btc_price > ema20_1h; above_ema50 = btc_price > ema50_1h; ema20_above_50 = ema20_1h > ema50_1h
    if above_ema20 and above_ema50 and ema20_above_50 and rsi_1h>56 and strength>1.0: regime="TRENDING_BULL"; bias="LONG_ONLY"; reason=f"TRENDING_BULL BTC {btc_price:.0f} RSI {rsi_1h:.0f} STR {strength:.1f} -> LONG ONLY"
    elif not above_ema20 and not above_ema50 and not ema20_above_50 and rsi_1h<44 and strength>1.0: regime="TRENDING_BEAR"; bias="SHORT_ONLY"; reason=f"TRENDING_BEAR BTC {btc_price:.0f} RSI {rsi_1h:.0f} STR {strength:.1f} -> SHORT ONLY"
    else: regime="RANGING"; bias="BOTH"; reason=f"RANGING BTC {btc_price:.0f} RSI {rsi_1h:.0f} STR {strength:.1f} -> BOTH LOOSE"
    return {"regime":regime,"bias":bias,"btc_price":btc_price,"rsi":rsi_1h,"rsi_15":rsi_15m,"strength":strength,"reason":reason}

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":301.90,"daily":1.90,"fees_paid":0.30,"wins":2,"loss":1,"total":3,"scan":213,"scan_offset":30,"full_scans":21,"open":[],"closed":[{"symbol":"币安人生","side":"LONG","net":-0.85,"reason":"SL -0.7% CUT $-0.85 | 8m","pct_gross":-0.85,"pct_net":-0.85,"age":480,"pos":100,"shark":0},{"symbol":"INJ","side":"SHORT","net":0.86,"reason":"TP 1.0% WIN +$0.86 | 24m","pct_gross":0.86,"pct_net":0.86,"age":1440,"pos":100,"shark":0},{"symbol":"INJ","side":"LONG","net":1.89,"reason":"TP 1.9% WIN +$1.89 | 24m","pct_gross":1.89,"pct_net":1.89,"age":1440,"pos":100,"shark":65}],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}}
        kv_set(STATE_KEY, s)
    s.setdefault("cap",301.90); s.setdefault("daily",1.90); s.setdefault("fees_paid",0.30); s.setdefault("wins",2); s.setdefault("loss",1); s.setdefault("total",3); s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("learn",{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}})
    L=s["learn"]; L.setdefault("blacklist",{}); L.setdefault("last_coins",{}); L.setdefault("pause_until",0); L.setdefault("last_date",time.strftime("%Y-%m-%d"))
    now=int(time.time()); L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}; L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    if s.get("full_scans",0) >= 10: L["last_coins"]={}
    # filter bad open (chinese)
    s["open"]=[t for t in s.get("open",[]) if t.get("symbol","").isascii()]
    return s

def do_cron():
    state=load_state(); L=state["learn"]; now_ts=int(time.time()); scan=state.get("scan",0); offset = (scan * SCAN_BATCH) % TOP_N; full_scans = scan // 10
    if L.get("pause_until",0)>now_ts: return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"reason":"PAUSED","offset":offset,"scan":scan}
    if state.get("daily",0) < -state.get("cap",300)*MAX_DAILY_LOSS_PCT/100: L["pause_until"]=now_ts+3600*2; kv_set(STATE_KEY, state); return {"ok":False,"paused":True,"reason":"DAILY STOP","offset":offset}
    tickers=get_tickers()
    if not tickers:
        state["scan"]=scan+1; state["scan_offset"]=(offset+SCAN_BATCH)%TOP_N; state["full_scans"]=full_scans; kv_set(STATE_KEY, state)
        return {"ok":False,"error":"Binance ticker empty - advanced scan","offset":offset,"scan":scan+1,"next_offset":(offset+SCAN_BATCH)%TOP_N}
    ticker_map={t.get("symbol",""):t for t in tickers}; real=[]
    for t in tickers:
        sym=t.get("symbol",""); 
        if not sym.endswith("USDT"): continue
        base=sym.replace("USDT","")
        if is_bad(base): continue
        try:
            qv=float(t.get("quoteVolume","0"))
            if qv < 2500000: continue
        except: continue
        real.append(t)
    real_sorted=sorted(real, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:TOP_N]
    if not real_sorted:
        state["scan"]=scan+1; state["scan_offset"]=(offset+SCAN_BATCH)%TOP_N; kv_set(STATE_KEY, state)
        return {"ok":False,"error":"No real coins filtered","offset":offset,"scan":scan+1}
    batch=real_sorted[offset:offset+SCAN_BATCH]; next_offset = (offset + SCAN_BATCH) % TOP_N; next_full = (scan+1)//10
    market=get_market_smart(ticker_map); open_tr=state.get("open",[]); open_syms=[t["symbol"] for t in open_tr]; candidates=[]; shark_found=[]; debug=[]
    if full_scans>=8: L["last_coins"]={}
    for t in batch:
        base=t.get("symbol","").replace("USDT","")
        if base in open_syms: debug.append(f"{base} OPEN"); continue
        if base in L.get("blacklist",{}): debug.append(f"{base} BL"); continue
        if base in L.get("last_coins",{}): debug.append(f"{base} COOLDOWN"); continue
        price=float(t.get("lastPrice","0"))
        klines=get_klines_fast(base+"USDT","15m",40)
        if len(klines)<25:
            try:
                change=float(t.get("priceChangePercent","0"))
                if abs(change)>0.7:
                    side="LONG" if change<-0.7 else "SHORT" if change>1.0 else "LONG"
                    candidates.append({"symbol":base,"side":side,"price":price,"sector":get_sector(base),"score":abs(change)*5+10,"tp":1.0,"sl":0.65,"rsi":40 if side=="LONG" else 60,"reason":f"TICKER {change:+.1f}%","strength":0.5,"shark":0,"shark_reason":"TICKER"})
            except: pass
            continue
        closes=[k["c"] for k in klines]; rsi=calc_rsi(closes,14); atr=calc_atr(klines,14); atr_pct=(atr/price*100) if price else 1
        if atr_pct < 0.20 or atr_pct > 5.5: debug.append(f"{base} ATR {atr_pct:.2f}%"); continue
        strength=calc_trend_strength(closes)
        if strength < 0.18: debug.append(f"{base} STR {strength:.2f} low"); continue
        shark_score, shark_reason = detect_shark(klines, t); ema20=calc_ema(closes,20); last_c=closes[-1]; coin_bull = last_c > ema20; coin_bear = last_c < ema20
        if market["regime"]=="RANGING": rsi_long=46; rsi_short=54
        elif market["bias"]=="LONG_ONLY": rsi_long=42; rsi_short=999
        elif market["bias"]=="SHORT_ONLY": rsi_long=-1; rsi_short=58
        else: rsi_long=44; rsi_short=56
        side=None; reason=""
        if rsi < rsi_long and coin_bull: side="LONG"; reason=f"LONG RSI {rsi:.0f} STR {strength:.1f} {shark_reason}"
        elif rsi > rsi_short and coin_bear: side="SHORT"; reason=f"SHORT RSI {rsi:.0f} STR {strength:.1f} {shark_reason}"
        elif rsi < 37: side="LONG"; reason=f"LONG EXT RSI {rsi:.0f} SHARK {shark_score}"
        elif rsi > 63: side="SHORT"; reason=f"SHORT EXT RSI {rsi:.0f} SHARK {shark_score}"
        if side:
            tp_pct=min(atr*1.8/price*100, MAX_TP_PCT); tp_pct=max(tp_pct, MIN_TP_PCT); sl_pct=min(atr*0.65/price*100, MAX_SL_PCT)
            base_score = (abs(rsi-50)+strength*8)*float(t.get("quoteVolume","0"))/1e7; score = base_score + shark_score*1.2
            if score < 5 and shark_score<20: debug.append(f"{base} SCORE {score:.1f} low"); continue
            candidates.append({"symbol":base,"side":side,"price":price,"sector":get_sector(base),"score":score,"tp":tp_pct,"sl":sl_pct,"rsi":rsi,"reason":reason,"strength":strength,"shark":shark_score,"shark_reason":shark_reason})
            if shark_score>=30: shark_found.append(base)
        else: debug.append(f"{base} RSI {rsi:.0f} no side")
    fallback=False
    if not candidates:
        if full_scans>=2 or scan>=5:
            L["blacklist"]={}; L["last_coins"]={}
            for fb in real_sorted[offset:offset+SCAN_BATCH]:
                fb_base=fb.get("symbol","").replace("USDT","")
                if not fb_base.isascii(): continue
                if fb_base in open_syms: continue
                price=float(fb.get("lastPrice","0"))
                if price==0: continue
                side="LONG" if len(candidates)%2==0 else "SHORT"
                if market["bias"]=="LONG_ONLY": side="LONG"
                if market["bias"]=="SHORT_ONLY": side="SHORT"
                candidates.append({"symbol":fb_base,"side":side,"price":price,"sector":get_sector(fb_base),"score":100,"tp":1.0,"sl":0.65,"rsi":45,"reason":f"ULTRA FORCE FILL {offset}-{offset+SCAN_BATCH} SCAN {scan} FULL {full_scans}x","strength":0.6,"shark":0,"shark_reason":"FORCE"})
                fallback=True
                if len(candidates)>=3: break
    candidates=sorted(candidates, key=lambda x: x["score"], reverse=True)[:3]
    closed=state.get("closed",[]); cap=state.get("cap",300.0); daily=state.get("daily",0.0); fees_paid=state.get("fees_paid",0.0); tot=state.get("total",0)
    final=[]
    for tr in open_tr:
        try:
            sym=tr["symbol"]+"USDT"; price_now=float(ticker_map[sym].get("lastPrice",tr.get("price",tr.get("entry",0)))) if sym in ticker_map else tr.get("price",0)
            entry=tr.get("entry",price_now); side=tr.get("side","LONG")
            pct_gross=(price_now-entry)/entry*100 if side=="LONG" and entry else (entry-price_now)/entry*100 if entry else 0
            pct_net=pct_gross - FEE_PCT; pos_size=tr.get("pos",POS_FIXED); net_usd=pos_size*pct_net/100; age=now_ts-tr.get("ts",now_ts); peak_gross=max(tr.get("peak_gross",0), pct_gross)
            tr["price"]=price_now; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["peak_gross"]=peak_gross; tr["age"]=age; tr["net"]=net_usd
            tp=tr.get("tp",1.0); sl=tr.get("sl",0.65); should=None
            if pct_gross>=tp: should=f"TP {tp:.1f}% WIN +${net_usd:.2f}"
            elif pct_gross<=-sl: should=f"SL -{sl:.1f}% CUT ${net_usd:.2f}"
            elif peak_gross>=0.6 and pct_gross<=0.10: should=f"BE_PROTECT {peak_gross:.1f}%->0.1%"
            elif peak_gross>=tp*0.5 and pct_gross<peak_gross-0.45: should=f"TRAIL {peak_gross:.1f}%->{pct_gross:.1f}%"
            elif age>TIME_EXIT_MIN*60 and pct_gross < 0.20: should=f"TIME {TIME_EXIT_MIN}m"
            if pct_net < -0.9: should=f"MAXLOSS -0.9% ${net_usd:.2f}"
            if should:
                cap+=net_usd; daily+=net_usd; fees_paid+=FEE_PCT*pos_size/100; tot+=1
                closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"pos":pos_size,"shark":tr.get("shark",0)})
                L["last_coins"][tr["symbol"]]=now_ts+300
                if pct_net<-0.7: L["blacklist"][tr["symbol"]]=now_ts+1800
            else: final.append(tr)
        except: final.append(tr)
    wins=sum(1 for c in closed if c.get("net",0)>0); loss=sum(1 for c in closed if c.get("net",0)<0)
    for sh in candidates:
        if len(final)>=MAXP: break
        if sh["symbol"] in [t["symbol"] for t in final]: continue
        pos_size=POS_FIXED
        if cap < 20: break
        if pos_size > cap: pos_size=cap*0.9
        if pos_size < 15: continue
        tr={"symbol":sh["symbol"],"side":sh["side"],"entry":sh["price"],"price":sh["price"],"pos":pos_size,"ts":now_ts,"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":sh["score"],"sector":sh["sector"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"rsi":sh["rsi"],"shark":sh.get("shark",0),"strength":sh.get("strength",0)}
        final.append(tr)
    state["open"]=final; state["closed"]=closed[:400]; state["cap"]=cap; state["daily"]=daily; state["fees_paid"]=fees_paid; state["wins"]=wins; state["loss"]=loss; state["total"]=tot; state["scan"]=scan+1; state["scan_offset"]=next_offset; state["full_scans"]=next_full; state["market"]=market; kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan+1,"open":len(final),"cap":cap,"daily":daily,"candidates":len(candidates),"offset":offset,"next_offset":next_offset,"batch":f"{offset+1}-{offset+SCAN_BATCH}","sharks":shark_found,"fallback":fallback,"market":market["reason"],"bias":market["bias"],"debug":debug[:6],"full":next_full}

def render(state):
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",301.90); daily=state.get("daily",0.0); fees_paid=state.get("fees_paid",0.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0); offset=state.get("scan_offset",0); full_scans=state.get("full_scans",0)
    market=state.get("market",{"regime":"RANGING","bias":"BOTH","btc_price":84000,"rsi":50,"reason":f"SCAN {scan} OFFSET {offset} v814 LIVE","strength":0})
    winrate=int(wins/tot*100) if tot>0 else 0; unreal=sum([t.get("net",0) for t in open_tr]); long_open=sum(1 for t in open_tr if t.get("side")=="LONG"); short_open=sum(1 for t in open_tr if t.get("side")=="SHORT")
    gross_profit=sum([c.get("net",0) for c in closed if c.get("net",0)>0]); gross_loss=sum([c.get("net",0) for c in closed if c.get("net",0)<0])
    pf=abs(gross_profit/gross_loss) if gross_loss!=0 else (gross_profit if gross_profit>0 else 0); exp=(gross_profit+gross_loss)/tot if tot>0 else 0
    best = max(closed, key=lambda x: x.get("net",0)) if closed else None; worst = min(closed, key=lambda x: x.get("net",0)) if closed else None
    best_sym=best.get('symbol','-') if best else '-'; best_net=best.get('net',0) if best else 0; worst_sym=worst.get('symbol','-') if worst else '-'; worst_net=worst.get('net',0) if worst else 0
    invested=sum([t.get("pos",0) for t in open_tr]); bias_color="#00ff88" if market.get("bias")=="LONG_ONLY" else "#ff4444" if market.get("bias")=="SHORT_ONLY" else "#ffcc00"
    trade_boxes_html=""; chart_js_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",100); entry=tr.get("entry",0)
        tp_price = entry * (1 + tr.get("tp",1)/100) if side=="LONG" else entry * (1 - tr.get("tp",1)/100)
        sl_price = entry * (1 - tr.get("sl",0.65)/100) if side=="LONG" else entry * (1 + tr.get("sl",0.65)/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        shark_tag = f"<span style='background:#00d4ff;color:#000;padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900'>🦈 {tr.get('shark',0)}</span>" if tr.get('shark',0)>=20 else ""
        # Pass ts for live age
        ts = tr.get("ts", int(time.time()))
        trade_boxes_html+=f"""
        <div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'>
          <div style='display:flex;justify-content:space-between;align-items:center'>
            <div><b style='color:{col};font-size:14px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f} {shark_tag}</b>
            <div style='font-size:10px;color:#aaa'>ENTRY ${entry:.6f} | TP ${tp_price:.6f} ({tr.get('tp',0):.2f}%) | SL ${sl_price:.6f} ({tr.get('sl',0):.2f}%) | {tr.get('sector','')}</div></div>
            <button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 10px;font-weight:900'>✕</button>
          </div>
          <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin:8px 0;text-align:center'>
            <div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>LIVE PRICE</div><div id='live-price-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('price',0):.4f}</div><div id='live-change-{sym}' style='font-size:10px'>{tr.get('pct_gross',0):+.3f}%</div><div id='live-dot-{sym}' style='font-size:8px;color:#0f8'>● LIVE 3s</div></div>
            <div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>UNREAL PNL</div><div id='live-pnl-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f}</div><div style='font-size:10px'>PEAK {tr.get('peak_gross',0):.2f}%</div></div>
            <div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>AGE / TP</div><div id='live-age-{sym}' style='font-size:13px;font-weight:900' data-ts='{ts}'>{int(tr.get('age',0)//60)}m {int(tr.get('age',0)%60)}s</div><div style='font-size:10px;color:#0f8'>to go {(tr.get('tp',0)-tr.get('pct_gross',0)):.2f}%</div></div>
          </div>
          <div style='position:relative;background:#000;border-radius:12px;padding:6px;border:1px solid #222'>
            <canvas id='chart-{sym}' width='340' height='140' style='width:100%;height:140px'></canvas>
            <div style='display:flex;justify-content:space-between;font-size:8px;color:#666;margin-top:3px'><span>15m - ENTRY yellow TP green SL red - Vercel proxy live 3s</span><span id='chart-status-{sym}' style='color:#00d4ff'>LIVE 3s</span></div>
          </div>
          <div style='font-size:9px;color:#888;margin-top:4px'>{tr.get('reason','')} | RSI {tr.get('rsi',0):.0f} STR {tr.get('strength',0):.1f} SECTOR {tr.get('sector','')}</div>
        </div>"""
        chart_js_init+=f"initChart('{sym}',{entry},{tp_price},{sl_price},'{side}',{ts});\n"
    if not open_tr:
        trade_boxes_html=f"<div class='it' style='text-align:center;color:#666;padding:16px'>No open trades.<br>v814 TRULY LIVE - age + price + graph all live 3s via Vercel proxy<br>SCAN {scan} OFFSET {offset}-{offset+SCAN_BATCH} FULL {full_scans}x<br>Tap CRON - guarantees 3x$100<br>CAP ${cap:.2f}</div>"
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>
    body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}}
    .h{{background:linear-gradient(90deg,#0f8,#fc0,#0df);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}}
    .g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}}
    .stats{{background:#111;border:2px solid {bias_color};padding:10px;margin:6px 0;border-radius:12px}}
    .it{{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:12px}}
    .trade-box{{background:#151515;border:1px solid #333;padding:10px;margin:8px 0;border-radius:14px}}
    .btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.btn{{padding:16px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px;cursor:pointer}}.btn-cron{{background:#0f8;color:#000}}.btn-reset{{background:#f44;color:#fff}}.btn-close{{background:#fc0;color:#000}}.badge{{padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900}}.long{{background:#0f8;color:#000}}.short{{background:#f44;color:#fff}}
    </style></head><body>
    <div class='h'>VENUS v814 TRULY LIVE 3s - SCAN #{scan} OFFSET {offset}-{offset+SCAN_BATCH} - ${cap:.2f} L:{long_open} S:{short_open} {market.get('regime')} BIAS {market.get('bias')} FULLx{full_scans} - LIVE GRAPH FIX</div>
    <div class='btn-row'>
      <button class='btn btn-cron' onclick='callCron()'>⚡CRON 10 COINS<div id='cronStat' style='font-size:10px'>TAP {offset+1}-{offset+SCAN_BATCH}/100 SCAN {scan}</div></button>
      <button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN ${invested:.0f}</div></button>
      <button class='btn btn-reset' onclick='callReset()'>🔄RESET<div style='font-size:10px'>CAP $300</div></button>
    </div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#fc0'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}<br>INV ${invested:.0f}<br>FEES ${fees_paid:.2f}</div>
    <div class='c'>TODAY<br><b style='font-size:18px;color:{"#f44" if daily<0 else "#0f8"}'>${daily:+.2f}</b><br>W:{wins} L:{loss} {winrate}%<br>FEES ${fees_paid:.2f}<br>SCAN {offset}-{offset+SCAN_BATCH}<br>TOTAL {tot}</div>
    <div class='c' style='border-color:{bias_color}'>SHARK + GRAPH<br><b style='color:{bias_color}'>{market.get('bias')}</b><br>{market.get('regime')}<br>BTC ${market.get('btc_price',0):.0f}<br>RSI {market.get('rsi',0):.0f}<br>FULL {full_scans}x<br>LIVE 3s</div></div>
    <div class='stats'>
      <div style='color:{bias_color};font-weight:900;font-size:12px'>📈 v814 TRULY LIVE 3s - BIAS: {market.get('bias')} - {market.get('regime')} LOOSE RSI 46/54 STR 0.18 SHARK + ATR + EMA + GRAPH - LIVE FIX</div>
      <div style='margin-top:4px;font-size:10px;color:#eee'>{market.get('reason','')}</div>
      <div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px;font-size:10px'>
        <div>SCAN: <b>{offset+1}-{offset+SCAN_BATCH}/100 (x{full_scans}) NEVER STUCK - Vercel proxy live</b></div><div>OPEN: <b>{len(open_tr)}/3</b></div>
        <div>TOTAL: <b>{tot}</b> WIN: <b style='color:#0f8'>{wins}</b> LOSS: <b style='color:#f44'>{loss}</b> {winrate}%</div><div>PF: <b>{pf:.2f}</b> EXP: <b>${exp:.3f}</b></div>
        <div>BEST: <b>{best_sym} ${best_net:+.2f}</b></div><div>WORST: <b>{worst_sym} ${worst_net:+.2f}</b></div>
      </div>
      <div style='margin-top:6px;color:#0f8;font-size:10px'>✅ v814 FIX: Graph + price + AGE timer now LIVE 3s via /api/liveprice proxy - no CORS - filters Chinese symbols - never stuck</div>
    </div>
    <div id='openbox'>{trade_boxes_html}</div>
    <div style='background:#111;padding:10px;margin:6px 0;border-radius:10px'><div style='color:#fc0;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% - PF {pf:.2f} EXP ${exp:.3f}</div>
    """
    for cl in closed[:20]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"; sh=f"🦈{cl.get('shark',0)}" if cl.get('shark',0)>=20 else ""
        html+=f"<div style='padding:5px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')} {cl.get('side','')} ${cl.get('pos',100):.0f} {sh}</b> ${cl.get('net',0):+.2f} {cl.get('pct_net',0):+.2f}% | {cl.get('reason','')} | {int(cl.get('age',0)//60)}m</div>"
    html+=f"""</div>
<script>
const ADMIN_KEY="{ADMIN_KEY}";
async function callCron(){{const b=document.getElementById('cronStat'); b.innerText='SCANNING...'; try{{const r=await fetch('/api/cron?key='+ADMIN_KEY); const j=await r.json(); b.innerText=j.ok ? 'OK '+j.batch+' C:'+j.candidates+(j.fallback?' FORCE':'')+' FULL '+j.full : j.error||j.reason; setTimeout(()=>location.reload(),800);}}catch(e){{b.innerText='ERR '+e;}}}}
async function callReset(){{if(!confirm('RESET CAP $300?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}

function initChart(sym,entry,tp,sl,side,openTs){{
  const cv=document.getElementById('chart-'+sym); if(!cv) return; const ctx=cv.getContext('2d'); let prices=[]; let lastFetch=0;
  // LIVE AGE TIMER - updates every 1s without CRON
  const ageEl=document.getElementById('live-age-'+sym);
  setInterval(()=>{{
    if(!ageEl) return;
    const ts=parseInt(ageEl.dataset.ts||openTs); const now=Math.floor(Date.now()/1000); const age=now-ts;
    const m=Math.floor(age/60); const s=age%60; ageEl.innerText=m+'m '+s+'s';
  }},1000);

  async function fetchPrice(){{
    try{{
      const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY);
      const j=await r.json();
      if(j.price){{
        const price=j.price;
        const pct=side=='LONG'?(price-entry)/entry*100:(entry-price)/entry*100;
        const net=100*(pct-0.15)/100;
        const elP=document.getElementById('live-price-'+sym);
        const elC=document.getElementById('live-change-'+sym);
        const elPn=document.getElementById('live-pnl-'+sym);
        const dot=document.getElementById('live-dot-'+sym);
        const status=document.getElementById('chart-status-'+sym);
        if(elP){{elP.innerText='$'+price.toFixed(4); elP.style.color=pct>=0?'#0f8':'#f44';}}
        if(elC){{elC.innerText=pct.toFixed(3)+'%'; elC.style.color=pct>=0?'#0f8':'#f44';}}
        if(elPn){{elPn.innerText=(net>=0?'+':'')+'$'+net.toFixed(2); elPn.style.color=net>=0?'#0f8':'#f44';}}
        if(dot) dot.innerText='● LIVE '+new Date().toLocaleTimeString();
        if(status) status.innerText='LIVE '+new Date().toLocaleTimeString();
        // append to prices for chart trail
        prices.push(price);
        if(prices.length>40) prices.shift();
        draw();
      }}
    }}catch(e){{}}
  }}

  async function fetchKlines(){{
    try{{
      const r=await fetch('/api/klines?symbol='+sym+'&key='+ADMIN_KEY);
      const j=await r.json();
      if(j.closes && j.closes.length>5){{prices=j.closes; draw();}}
    }}catch(e){{}}
  }}

  function draw(){{
    if(!prices.length) return; const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h);
    const allP=[...prices,entry,tp,sl]; const mn=Math.min(...allP)*0.999, mx=Math.max(...allP)*1.001, rg=mx-mn||1;
    function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}}
    ctx.strokeStyle='#222'; for(let i=0;i<4;i++){{const y=h*0.1+i*h*0.8/3; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}}
    ctx.strokeStyle='#0f8'; ctx.setLineDash([6,4]); ctx.lineWidth=1.2; ctx.beginPath(); ctx.moveTo(0,yF(tp)); ctx.lineTo(w,yF(tp)); ctx.stroke(); ctx.fillStyle='#0f8'; ctx.font='9px monospace'; ctx.fillText('TP '+tp.toFixed(4),3,yF(tp)-3); ctx.setLineDash([]);
    ctx.strokeStyle='#fc0'; ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,yF(entry)); ctx.lineTo(w,yF(entry)); ctx.stroke(); ctx.fillStyle='#fc0'; ctx.fillText('ENTRY '+entry.toFixed(4),3,yF(entry)-3);
    ctx.strokeStyle='#f44'; ctx.setLineDash([6,4]); ctx.lineWidth=1.2; ctx.beginPath(); ctx.moveTo(0,yF(sl)); ctx.lineTo(w,yF(sl)); ctx.stroke(); ctx.fillStyle='#f44'; ctx.fillText('SL '+sl.toFixed(4),3,yF(sl)+10); ctx.setLineDash([]);
    ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=2; ctx.beginPath(); prices.forEach((p,i)=>{{const x=i/(prices.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();
    const last=prices[prices.length-1]; const ly=yF(last); ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(w-6,ly,3.5,0,Math.PI*2); ctx.fill(); ctx.fillStyle=last>=entry?'#0f8':'#f44'; ctx.beginPath(); ctx.arc(w-6,ly,2,0,Math.PI*2); ctx.fill();
  }}

  fetchKlines(); fetchPrice();
  setInterval(fetchPrice, 3000);
  setInterval(fetchKlines, 15000);
}}
window.addEventListener('load',()=>{{{chart_js_init}}});
</script></body></html>"""
    return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    key=request.args.get("key","")
    p="/"+path
    if p.startswith("/api/liveprice"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper()
        if not sym: return Response(json.dumps({"error":"no symbol"}), mimetype="application/json")
        full_sym=sym+"USDT" if not sym.endswith("USDT") else sym
        try:
            # proxy via Vercel backend to avoid CORS
            url=f"https://api.binance.com/api/v3/ticker/price?symbol={full_sym}"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as r:
                data=json.loads(r.read().decode())
                price=float(data.get("price",0))
                return Response(json.dumps({"symbol":sym,"price":price,"ts":int(time.time())}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"error":str(e)[:100]}), mimetype="application/json", status=200)
    if p.startswith("/api/klines"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper()
        full_sym=sym+"USDT" if not sym.endswith("USDT") else sym
        try:
            url=f"https://api.binance.com/api/v3/klines?symbol={full_sym}&interval=1m&limit=40"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as r:
                data=json.loads(r.read().decode())
                closes=[float(x[4]) for x in data]
                return Response(json.dumps({"symbol":sym,"closes":closes}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"error":str(e)[:100],"closes":[]}), mimetype="application/json", status=200)
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try: res=do_cron(); return Response(json.dumps(res), mimetype="application/json")
        except Exception as e: import traceback; return Response(json.dumps({"ok":False,"error":str(e)[:400],"trace":traceback.format_exc()[:500]}), mimetype="application/json", status=200)
    if p.startswith("/api/fix"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        s=load_state(); s["scan_offset"]=0; s["learn"]["blacklist"]={}; s["learn"]["last_coins"]={}; kv_set(STATE_KEY,s); return Response(json.dumps({"ok":True,"fixed":True,"scan":s.get("scan",0)}), mimetype="application/json")
    if p.startswith("/api/debug"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps(load_state(), indent=2), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); time.sleep(0.5); new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}}; kv_set(STATE_KEY,new); return Response(json.dumps({"ok":True,"cap":300}), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]): cap+=tr.get("net",0); state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":"MANUAL CLOSE ALL","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"shark":tr.get("shark",0)})
        state["open"]=[]; state["cap"]=cap; kv_set(STATE_KEY,state); return Response(json.dumps({"ok":True}), mimetype="application/json")
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); state=load_state(); cap=state.get("cap",300.0); final=[]
        for tr in state.get("open",[]):
            if tr["symbol"]==sym: cap+=tr.get("net",0); state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE {sym}","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"shark":tr.get("shark",0)})
            else: final.append(tr)
        state["open"]=final; state["cap"]=cap; kv_set(STATE_KEY,state); return Response(json.dumps({"ok":True,"closed":sym}), mimetype="application/json")
    try: st=load_state(); return Response(render(st), mimetype="text/html")
    except Exception as e: import traceback; return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:2000]}</pre></body></html>", mimetype="text/html", status=200)
