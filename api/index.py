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
STATE_KEY="VENUS_V808_SHARK100"  # keep same as v808 so you don't lose INJ trade

POS_FIXED=100.0; MAXP=3; FEE_PCT=0.15; MAX_DAILY_LOSS_PCT=4.5
MIN_TP_PCT=0.90; MAX_TP_PCT=2.4; MAX_SL_PCT=0.85; TIME_EXIT_MIN=65
SCAN_BATCH=10; TOP_N=100
PERM_BLACKLIST=set(["MAGIC","ZEC","CFX","UNI","NEAR","TIA","ENA","LUMIA","STRK","DOGE"])
COIN_SECTOR={"L1_CHAIN":["BTC","ETH","ARB","SUI","SEI","APT","TIA","AVAX","SOL","NEAR","OP","STRK","DOGE","CFX","ZEC"],"DEFI":["ENA","PENDLE","AERO","LDO","UNI","AAVE","BTC","ETH"],"MEME":["PEPE","BONK","WIF","FLOKI","SHIB","POPCAT","BRETT","DOGE"],"AI":["TAO","FET","RNDR","GRT"]}
COIN_SECTOR={c:sec for sec, coins in SECTORS.items() for c in coins} if (SECTORS:= {"L1_CHAIN":["BTC","ETH","ARB","SUI","SEI","APT","TIA","AVAX","SOL","NEAR","OP","STRK","DOGE","CFX","ZEC"],"DEFI":["ENA","PENDLE","AERO","LDO","UNI","AAVE","BTC","ETH"],"MEME":["PEPE","BONK","WIF","FLOKI","SHIB","POPCAT","BRETT","DOGE"],"AI":["TAO","FET","RNDR","GRT"]}) else {}
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
        with urllib.request.urlopen(req, timeout=6) as r: return json.loads(r.read().decode())
    except:
        try:
            req=urllib.request.Request("https://data-api.binance.vision/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as r: return json.loads(r.read().decode())
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
def detect_shark(klines, ticker):
    if len(klines) < 25: return 0, "no data"
    volumes = [k["v"] for k in klines[-21:-1]]
    avg_vol = sum(volumes)/len(volumes) if volumes else 1
    last_vol = klines[-1]["v"]
    prev_vol = klines[-2]["v"] if len(klines)>1 else avg_vol
    vol_spike = last_vol / avg_vol if avg_vol>0 else 1
    vol_accel = last_vol / prev_vol if prev_vol>0 else 1
    closes = [k["c"] for k in klines]
    price_change_1 = (closes[-1]/closes[-2]-1)*100 if len(closes)>=2 else 0
    shark_score = 0; reason=[]
    if vol_spike > 2.5: shark_score+=40; reason.append(f"VOLx{vol_spike:.1f}")
    elif vol_spike > 1.8: shark_score+=20; reason.append(f"volx{vol_spike:.1f}")
    if vol_accel > 1.8: shark_score+=20; reason.append(f"ACCx{vol_accel:.1f}")
    if abs(price_change_1) > 1.2 and vol_spike > 1.5: shark_score+=25; reason.append(f"MOVE {price_change_1:+.1f}%")
    last = klines[-1]; body_pct = abs(last["c"]-last["o"])/last["c"]*100 if last["c"] else 0
    if body_pct > 1.0 and vol_spike>1.5: shark_score+=10; reason.append(f"BODY {body_pct:.1f}%")
    return min(shark_score,100), " ".join(reason) if reason else "no shark"
def get_market_smart(ticker_map):
    klines_1h=get_klines_fast("BTCUSDT","1h",60)
    klines_15m=get_klines_fast("BTCUSDT","15m",60)
    if not klines_1h:
        btc_ticker=ticker_map.get("BTCUSDT"); btc_price=float(btc_ticker.get("lastPrice","70000")) if btc_ticker else 70000
        return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price,"rsi":50,"rsi_15":50,"strength":0,"reason":f"RANGING BTC {btc_price:.0f} NO DATA"}
    closes_1h=[k["c"] for k in klines_1h]; closes_15m=[k["c"] for k in klines_15m] if klines_15m else closes_1h
    btc_price=closes_1h[-1]; ema20_1h=calc_ema(closes_1h, 20); ema50_1h=calc_ema(closes_1h, 50)
    rsi_1h=calc_rsi(closes_1h, 14); rsi_15m=calc_rsi(closes_15m, 14); strength=calc_trend_strength(closes_1h)
    above_ema20 = btc_price > ema20_1h; above_ema50 = btc_price > ema50_1h; ema20_above_50 = ema20_1h > ema50_1h
    if above_ema20 and above_ema50 and ema20_above_50 and rsi_1h>56 and strength>1.0:
        regime="TRENDING_BULL"; bias="LONG_ONLY"; reason=f"TRENDING_BULL BTC {btc_price:.0f} RSI {rsi_1h:.0f} STR {strength:.1f} -> LONG ONLY"
    elif not above_ema20 and not above_ema50 and not ema20_above_50 and rsi_1h<44 and strength>1.0:
        regime="TRENDING_BEAR"; bias="SHORT_ONLY"; reason=f"TRENDING_BEAR BTC {btc_price:.0f} RSI {rsi_1h:.0f} STR {strength:.1f} -> SHORT ONLY"
    elif strength < 0.5:
        regime="RANGING"; bias="BOTH_WEAK"; reason=f"RANGING BTC {btc_price:.0f} RSI {rsi_1h:.0f} STR {strength:.1f} -> shark hunt"
    else:
        regime="WEAK_TREND"; bias="BOTH"; reason=f"WEAK_TREND BTC {btc_price:.0f} RSI {rsi_1h:.0f} STR {strength:.1f} -> BOTH"
    return {"regime":regime,"bias":bias,"btc_price":btc_price,"rsi":rsi_1h,"rsi_15":rsi_15m,"strength":strength,"reason":reason}
def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}}
    if "learn" not in s: s["learn"]={"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}
    L=s["learn"]; L.setdefault("blacklist",{}); L.setdefault("pause_until",0); L.setdefault("last_date",""); L.setdefault("last_coins",{})
    s.setdefault("scan_offset",0); s.setdefault("full_scans",0)
    today=time.strftime("%Y-%m-%d")
    if L.get("last_date")!=today:
        s["daily"]=0.0; s["fees_paid"]=0.0; L["last_date"]=today; L["pause_until"]=0; L["last_coins"]={}
    now=int(time.time()); L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}; L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    return s
def do_cron():
    state=load_state(); L=state["learn"]; now_ts=int(time.time())
    if L.get("pause_until",0)>now_ts: return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"reason":"PAUSED"}
    if state.get("daily",0) < -state.get("cap",300)*MAX_DAILY_LOSS_PCT/100:
        L["pause_until"]=now_ts+3600*4; kv_set(STATE_KEY, state); return {"ok":False,"paused":True,"left":3600*4,"reason":f"DAILY -{MAX_DAILY_LOSS_PCT}% STOP"}
    tickers=get_tickers(); ticker_map={}; real=[]
    for t in tickers:
        sym=t.get("symbol",""); ticker_map[sym]=t
        if not sym.endswith("USDT"): continue
        base=sym.replace("USDT","")
        if is_bad(base): continue
        if not base.isalnum() or len(base)<2 or len(base)>7: continue
        try:
            qv=float(t.get("quoteVolume","0"))
            if qv < 5000000: continue
        except: continue
        real.append(t)
    real_sorted=sorted(real, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:TOP_N]
    market=get_market_smart(ticker_map)
    offset=state.get("scan_offset",0)
    batch=real_sorted[offset:offset+SCAN_BATCH]
    if not batch:
        offset=0
        batch=real_sorted[offset:offset+SCAN_BATCH]
        state["full_scans"]=state.get("full_scans",0)+1
    next_offset = offset + SCAN_BATCH
    if next_offset >= TOP_N:
        next_offset = 0
        state["full_scans"]=state.get("full_scans",0)+1
    open_tr=state.get("open",[]); open_syms=[t["symbol"] for t in open_tr]; candidates=[]; shark_found=[]
    for t in batch:
        base=t.get("symbol","").replace("USDT","")
        if base in open_syms: continue
        if base in L.get("blacklist",{}): continue
        if base in L.get("last_coins",{}): continue
        price=float(t.get("lastPrice","0")); klines=get_klines_fast(base+"USDT","15m",40)
        if len(klines)<25: continue
        closes=[k["c"] for k in klines]; rsi=calc_rsi(closes,14); atr=calc_atr(klines,14); atr_pct=(atr/price*100) if price else 1
        if atr_pct < 0.35 or atr_pct > 4.5: continue
        strength=calc_trend_strength(closes)
        if strength < 0.4: continue
        shark_score, shark_reason = detect_shark(klines, t)
        ema20=calc_ema(closes,20); ema50=calc_ema(closes,50); last_c=closes[-1]
        coin_bull = last_c > ema20 and ema20 > ema50; coin_bear = last_c < ema20 and ema20 < ema50
        if shark_score >= 60:
            rsi_long = 38; rsi_short = 62
        elif market["bias"]=="LONG_ONLY":
            rsi_long = 36; rsi_short = 999
        elif market["bias"]=="SHORT_ONLY":
            rsi_long = -1; rsi_short = 64
        elif market["bias"]=="BOTH_WEAK":
            rsi_long = 30; rsi_short = 70
        else:
            rsi_long = 33; rsi_short = 67
        side=None; reason=""
        if rsi < rsi_long and coin_bull:
            side="LONG"; reason=f"LONG RSI {rsi:.0f} {'SHARK '+shark_reason if shark_score>=40 else f'STR {strength:.1f}'}"
        elif rsi > rsi_short and coin_bear:
            side="SHORT"; reason=f"SHORT RSI {rsi:.0f} {'SHARK '+shark_reason if shark_score>=40 else f'STR {strength:.1f}'}"
        if side:
            tp_pct=min(atr*2.0/price*100, MAX_TP_PCT); sl_pct=min(atr*0.65/price*100, MAX_SL_PCT)
            if tp_pct < MIN_TP_PCT: continue
            base_score = (abs(rsi-50)+strength*10)*float(t.get("quoteVolume","0"))/1e7
            score = base_score + shark_score*2
            if shark_score>=60: score+=50; shark_found.append(base)
            if score < 15 and shark_score < 50: continue
            candidates.append({"symbol":base,"side":side,"price":price,"sector":get_sector(base),"score":score,"tp":tp_pct,"sl":sl_pct,"rsi":rsi,"reason":reason,"strength":strength,"shark":shark_score,"shark_reason":shark_reason})
    fallback_used=False
    if not candidates and len(open_tr) < MAXP:
        if state.get("scan_offset",0) > 80 or state.get("full_scans",0)>=1:
            for fb in ["BTCUSDT","ETHUSDT"]:
                fb_base=fb.replace("USDT","")
                if fb_base in open_syms: continue
                if fb_base in L.get("blacklist",{}): continue
                klines=get_klines_fast(fb,"15m",40)
                if len(klines)<20: continue
                closes=[k["c"] for k in klines]; rsi=calc_rsi(closes,14); atr=calc_atr(klines,40)
                price=closes[-1]; ema20=calc_ema(closes,20); last_c=closes[-1]
                side=None
                if market["bias"] in ["LONG_ONLY","BOTH","BOTH_WEAK"] and rsi<38 and last_c < ema20:
                    side="LONG"; reason=f"FALLBACK {fb_base} LONG RSI {rsi:.0f}"
                elif market["bias"] in ["SHORT_ONLY","BOTH","BOTH_WEAK"] and rsi>62 and last_c > ema20:
                    side="SHORT"; reason=f"FALLBACK {fb_base} SHORT RSI {rsi:.0f}"
                if side:
                    tp_pct=min(atr*1.8/price*100, 1.8); sl_pct=0.7
                    candidates.append({"symbol":fb_base,"side":side,"price":price,"sector":get_sector(fb_base),"score":100,"tp":tp_pct,"sl":sl_pct,"rsi":rsi,"reason":reason,"strength":1.5,"shark":0,"shark_reason":"FALLBACK"})
                    fallback_used=True
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
            elif peak_gross>=0.7 and pct_gross<=0.12: should=f"BE_PROTECT {peak_gross:.1f}%->0.1%"
            elif peak_gross>=tp*0.5 and pct_gross<peak_gross-0.5: should=f"TRAIL {peak_gross:.1f}%->{pct_gross:.1f}%"
            elif age>TIME_EXIT_MIN*60 and pct_gross < 0.25: should=f"TIME {TIME_EXIT_MIN}m"
            if pct_net < -0.9: should=f"MAXLOSS -0.9% ${net_usd:.2f}"
            if should:
                cap+=net_usd; daily+=net_usd; fees_paid+=FEE_PCT*pos_size/100; tot+=1
                closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"pos":pos_size,"shark":tr.get("shark",0)})
                L["last_coins"][tr["symbol"]]=now_ts+900
                if pct_net<-0.7: L["blacklist"][tr["symbol"]]=now_ts+7200
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
        tr={"symbol":sh["symbol"],"side":sh["side"],"entry":sh["price"],"price":sh["price"],"pos":pos_size,"ts":now_ts,"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":sh["score"],"sector":sh["sector"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"rsi":sh["rsi"],"shark":sh.get("shark",0)}
        final.append(tr)
    state["open"]=final; state["closed"]=closed[:400]; state["cap"]=cap; state["daily"]=daily; state["fees_paid"]=fees_paid; state["wins"]=wins; state["loss"]=loss; state["total"]=tot; state["scan"]=scan; state["market"]=market; state["scan_offset"]=next_offset
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan,"open":len(final),"cap":cap,"daily":daily,"candidates":len(candidates),"offset":offset,"next_offset":next_offset,"batch":f"{offset+1}-{offset+len(batch)}","sharks":shark_found,"fallback":fallback_used,"market":market["reason"],"bias":market["bias"]}

def render(state):
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300.0); daily=state.get("daily",0.0); fees_paid=state.get("fees_paid",0.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0)
    offset=state.get("scan_offset",0); full_scans=state.get("full_scans",0)
    market=state.get("market",{"regime":"RANGING","bias":"BOTH","btc_price":70000,"rsi":50,"rsi_15":50,"reason":"Tap CRON","strength":0})
    winrate=int(wins/tot*100) if tot>0 else 0; unreal=sum([t.get("net",0) for t in open_tr]); long_open=sum(1 for t in open_tr if t.get("side")=="LONG"); short_open=sum(1 for t in open_tr if t.get("side")=="SHORT")
    gross_profit=sum([c.get("net",0) for c in closed if c.get("net",0)>0]); gross_loss=sum([c.get("net",0) for c in closed if c.get("net",0)<0])
    avg_win=gross_profit / wins if wins>0 else 0; avg_loss=gross_loss / loss if loss>0 else 0
    profit_factor=abs(gross_profit / gross_loss) if gross_loss!=0 else (gross_profit if gross_profit>0 else 0); expectancy=(gross_profit + gross_loss) / tot if tot>0 else 0
    best = max(closed, key=lambda x: x.get("net",0)) if closed else None; worst = min(closed, key=lambda x: x.get("net",0)) if closed else None
    best_sym = best.get('symbol','-') if best else '-'; best_net = best.get('net',0) if best else 0
    worst_sym = worst.get('symbol','-') if worst else '-'; worst_net = worst.get('net',0) if worst else 0
    invested=sum([t.get("pos",0) for t in open_tr]); bias_color="#00ff88" if market.get("bias")=="LONG_ONLY" else "#ff4444" if market.get("bias")=="SHORT_ONLY" else "#ffcc00"

    # Build trade boxes with live graph canvas
    trade_boxes_html=""
    chart_js_init=""
    for idx,tr in enumerate(open_tr):
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",100); entry=tr.get("entry",0)
        tp_price = entry * (1 + tr.get("tp",1.8)/100) if side=="LONG" else entry * (1 - tr.get("tp",1.8)/100)
        sl_price = entry * (1 - tr.get("sl",0.7)/100) if side=="LONG" else entry * (1 + tr.get("sl",0.7)/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        shark_tag = f"<span style='background:#00d4ff;color:#000;padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900'>🦈 {tr.get('shark',0)}</span>" if tr.get('shark',0)>=50 else ""
        trade_boxes_html+=f"""
        <div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'>
          <div style='display:flex;justify-content:space-between;align-items:center'>
            <div><b style='color:{col};font-size:15px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f} {shark_tag}</b>
            <div style='font-size:11px;color:#aaa;margin-top:2px'>ENTRY ${entry:.6f} | TP ${tp_price:.6f} ({tr.get('tp',0):.2f}%) | SL ${sl_price:.6f} ({tr.get('sl',0):.2f}%)</div></div>
            <button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:8px 14px;font-weight:900'>✕</button>
          </div>
          
          <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:10px 0;text-align:center'>
            <div style='background:#0a0a0a;padding:8px;border-radius:10px'><div style='font-size:10px;color:#888'>LIVE PRICE</div><div id='live-price-{sym}' style='font-size:16px;font-weight:900;color:{col}'>${tr.get('price',0):.4f}</div><div id='live-change-{sym}' style='font-size:11px'>{tr.get('pct_gross',0):+.3f}%</div></div>
            <div style='background:#0a0a0a;padding:8px;border-radius:10px'><div style='font-size:10px;color:#888'>UNREAL PNL</div><div id='live-pnl-{sym}' style='font-size:16px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f}</div><div style='font-size:11px'>PEAK {tr.get('peak_gross',0):.2f}%</div></div>
            <div style='background:#0a0a0a;padding:8px;border-radius:10px'><div style='font-size:10px;color:#888'>AGE / TP</div><div style='font-size:13px;font-weight:900'>{int(tr.get('age',0)//60)}m {int(tr.get('age',0)%60)}s</div><div style='font-size:11px;color:#0f8'>TP {tr.get('tp',0):.1f}% to go {(tr.get('tp',0)-tr.get('pct_gross',0)):.2f}%</div></div>
          </div>

          <div style='position:relative;background:#000;border-radius:12px;padding:8px;border:1px solid #222'>
            <canvas id='chart-{sym}' width='340' height='140' style='width:100%;height:140px'></canvas>
            <div style='display:flex;justify-content:space-between;font-size:9px;color:#666;margin-top:4px'>
              <span>15m chart - Entry yellow, TP green, SL red - live from Binance</span><span id='chart-status-{sym}' style='color:#00d4ff'>LIVE</span>
            </div>
          </div>
          <div style='font-size:10px;color:#888;margin-top:6px'>{tr.get('reason','')} | RSI {tr.get('rsi',0):.0f} STR {tr.get('strength',0):.1f}</div>
        </div>
        """
        chart_js_init+=f"initChart('{sym}', {entry}, {tp_price}, {sl_price}, '{side}');\n"

    if not open_tr:
        trade_boxes_html="<div class='it' style='text-align:center;color:#666;padding:20px'>No open trades.<br>Graph will appear here when trade opens.<br>Tap CRON to scan next 10/100.</div>"

    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'>
    <style>
    body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}}
   .h{{background:linear-gradient(90deg,#00ff88,#ffcc00,#00d4ff);color:#000;padding:14px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}}
   .g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:10px}}
   .stats{{background:#111;border:2px solid {bias_color};padding:12px;margin:8px 0;border-radius:12px}}
   .it{{background:#111;border:1px solid #333;padding:12px;margin:8px 0;border-radius:12px}}
   .trade-box{{background:#151515;border:1px solid #333;padding:12px;margin:10px 0;border-radius:16px}}
   .btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:12px 0}}
   .btn{{padding:18px 6px;border-radius:16px;border:0;font-weight:900;font-size:14px;cursor:pointer}}
   .btn-cron{{background:#00ff88;color:#000}}.btn-reset{{background:#ff4444;color:#fff}}.btn-close{{background:#ffcc00;color:#000}}
   .badge{{padding:3px 8px;border-radius:20px;font-size:10px;font-weight:900}}.long{{background:#00ff88;color:#000}}.short{{background:#ff4444;color:#fff}}
    </style></head><body>
    <div class='h'>VENUS v809 LIVE GRAPH - SCAN #{scan} OFFSET {offset}-{offset+SCAN_BATCH} - ${cap:.2f} L:{long_open} S:{short_open} {market.get('regime')} BIAS {market.get('bias')} FULLx{full_scans}</div>
    <div class='btn-row'>
      <button class='btn btn-cron' onclick='callCron()'><span>⚡</span>CRON 10 COINS<div id='cronStat' style='font-size:10px'>TAP {offset+1}-{offset+SCAN_BATCH}/100</div></button>
      <button class='btn btn-close' onclick='closeAll()'><span>💰</span>CLOSE ALL<div style='font-size:11px'>{len(open_tr)} OPEN ${invested:.0f}</div></button>
      <button class='btn btn-reset' onclick='callReset()'><span>🔄</span>RESET<div style='font-size:11px'>CAP $300</div></button>
    </div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:20px;color:#ffcc00'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}<br>INV ${invested:.0f}</div>
    <div class='c'>TODAY<br><b style='font-size:20px;color:{"#f44" if daily<0 else "#0f8"}'>${daily:+.2f}</b><br>W:{wins} L:{loss} {winrate}%<br>FEES ${fees_paid:.2f}<br>SCAN {offset}-{offset+SCAN_BATCH}</div>
    <div class='c' style='border-color:{bias_color}'>SHARK + GRAPH<br><b style='color:{bias_color}'>{market.get('bias')}</b><br>{market.get('regime')}<br>BTC ${market.get('btc_price',0):.0f}<br>FULL {full_scans}x</div></div>

    <div class='stats'>
      <div style='color:{bias_color};font-weight:900;font-size:13px'>📈 LIVE GRAPH v809 - 3x$100 - BIAS: {market.get('bias')}</div>
      <div style='margin-top:6px;font-size:11px;color:#eee'>{market.get('reason','')}</div>
      <div style='display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px'>
        <div>SCAN: <b>{offset+1}-{offset+SCAN_BATCH}/100</b> (x{full_scans})</div><div>OPEN: <b>{len(open_tr)}/3</b></div>
        <div>TOTAL: <b>{tot}</b></div><div>WIN: <b style='color:#0f8'>{wins}</b> | LOSS: <b style='color:#f44'>{loss}</b> | <b>{winrate}%</b></div>
        <div>PF: <b>{profit_factor:.2f}</b></div><div>EXP: <b>${expectancy:.3f}</b></div>
        <div>BEST: <b>{best_sym} ${best_net:+.2f}</b></div><div>WORST: <b>{worst_sym} ${worst_net:+.2f}</b></div>
      </div>
      <div style='margin-top:8px;color:#00d4ff;font-size:11px'>📊 NEW: Live moving graph in each trade box - entry/TP/SL lines + price ticks from Binance every 5s</div>
    </div>

    <div id='openbox'>{trade_boxes_html}</div>

    <div style='background:#111;padding:12px;margin:8px 0;border-radius:12px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% - PF {profit_factor:.2f}</div>
    """

    for cl in closed[:20]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"; sh = f"🦈{cl.get('shark',0)}" if cl.get('shark',0)>=40 else ""
        html+=f"<div style='padding:6px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')} {cl.get('side','')} ${cl.get('pos',POS_FIXED):.0f} {sh}</b> ${cl.get('net',0):+.2f} {cl.get('pct_net',0):+.2f}% | {cl.get('reason','')}</div>"
    html+=f"""</div>
<script>
const ADMIN_KEY="{ADMIN_KEY}";
async function callCron(){{const b=document.getElementById('cronStat'); b.innerText='SCANNING 10...'; try{{const r=await fetch('/api/cron?key='+ADMIN_KEY); const j=await r.json(); b.innerText=j.ok ? 'OK '+j.batch : j.reason; if(j.ok) setTimeout(()=>location.reload(),1500); else b.innerText=j.reason;}}catch(e){{b.innerText='ERR '+e;}} }}
async function callReset(){{if(!confirm('RESET v809?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}

// LIVE GRAPH SYSTEM
function initChart(symbol, entry, tp, sl, side) {{
  const canvas = document.getElementById('chart-'+symbol);
  if(!canvas) return;
  const ctx = canvas.getContext('2d');
  let prices = [];
  let labels = [];

  async function fetchKlines() {{
    try {{
      const res = await fetch('https://api.binance.com/api/v3/klines?symbol='+symbol+'USDT&interval=1m&limit=40');
      const data = await res.json();
      prices = data.map(k=>parseFloat(k[4]));
      draw();
      updateLiveNumbers();
    }} catch(e) {{
      document.getElementById('chart-status-'+symbol).innerText='OFFLINE';
    }}
  }}

  function draw() {{
    if(prices.length==0) return;
    const w=canvas.width, h=canvas.height;
    ctx.clearRect(0,0,w,h);
    const min = Math.min(...prices, entry, tp, sl) * 0.999;
    const max = Math.max(...prices, entry, tp, sl) * 1.001;
    const range = max-min || 1;

    // grid
    ctx.strokeStyle='#222'; ctx.lineWidth=0.5;
    for(let i=0;i<4;i++){{ const y=h*0.1 + i*h*0.8/3; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke(); }}

    function yFor(price){{ return h*0.9 - ((price-min)/range)*h*0.8; }}

    // TP line green
    ctx.strokeStyle='#00ff88'; ctx.setLineDash([6,4]); ctx.lineWidth=1.5;
    ctx.beginPath(); ctx.moveTo(0,yFor(tp)); ctx.lineTo(w,yFor(tp)); ctx.stroke();
    ctx.fillStyle='#00ff88'; ctx.font='10px monospace'; ctx.fillText('TP '+tp.toFixed(4), 4, yFor(tp)-4);

    // Entry yellow
    ctx.strokeStyle='#ffcc00'; ctx.setLineDash([]); ctx.lineWidth=1.5;
    ctx.beginPath(); ctx.moveTo(0,yFor(entry)); ctx.lineTo(w,yFor(entry)); ctx.stroke();
    ctx.fillStyle='#ffcc00'; ctx.fillText('ENTRY '+entry.toFixed(4), 4, yFor(entry)-4);

    // SL red
    ctx.strokeStyle='#ff4444'; ctx.setLineDash([6,4]); ctx.lineWidth=1.2;
    ctx.beginPath(); ctx.moveTo(0,yFor(sl)); ctx.lineTo(w,yFor(sl)); ctx.stroke();
    ctx.fillStyle='#ff4444'; ctx.fillText('SL '+sl.toFixed(4), 4, yFor(sl)+12);

    // price line
    ctx.setLineDash([]); ctx.strokeStyle= side=='LONG' ? '#00ff88' : '#ff4444'; ctx.lineWidth=2;
    ctx.beginPath();
    prices.forEach((p,i)=>{{
      const x = (i/(prices.length-1))*w;
      const y = yFor(p);
      if(i==0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
    }});
    ctx.stroke();

    // last price dot pulsing
    const last = prices[prices.length-1];
    const lastY = yFor(last); const lastX = w;
    ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(lastX-6,lastY,4,0,Math.PI*2); ctx.fill();
    ctx.fillStyle= last>=entry ? '#00ff88' : '#ff4444';
    ctx.beginPath(); ctx.arc(lastX-6,lastY,2.5,0,Math.PI*2); ctx.fill();
  }}

  function updateLiveNumbers() {{
    if(prices.length==0) return;
    const last = prices[prices.length-1];
    const pct = side=='LONG' ? (last-entry)/entry*100 : (entry-last)/entry*100;
    const net = 100 * (pct - 0.15) / 100; // $100 pos
    const priceEl = document.getElementById('live-price-'+symbol);
    const changeEl = document.getElementById('live-change-'+symbol);
    const pnlEl = document.getElementById('live-pnl-'+symbol);
    if(priceEl) priceEl.innerText='$'+last.toFixed(4);
    if(changeEl) {{ changeEl.innerText=pct.toFixed(3)+'%'; changeEl.style.color = pct>=0 ? '#00ff88' : '#ff4444'; }}
    if(pnlEl) {{ pnlEl.innerText=(net>=0?'+':'')+'$'+net.toFixed(2); pnlEl.style.color = net>=0 ? '#00ff88' : '#ff4444'; if(priceEl) priceEl.style.color = net>=0 ? '#00ff88' : '#ff4444'; }}
  }}

  fetchKlines();
  setInterval(fetchKlines, 5000); // live every 5s from Binance
}}

window.addEventListener('load', function() {{
  {chart_js_init}
}});
</script>
</body></html>"""
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
        kv_del(STATE_KEY); time.sleep(0.6)
        new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}}
        ok=kv_set(STATE_KEY, new); return Response(json.dumps({"ok":ok,"cap":300}), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]): cap+=tr.get("net",0); state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":"MANUAL CLOSE ALL","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"shark":tr.get("shark",0)})
        state["open"]=[]; state["cap"]=cap; kv_set(STATE_KEY, state); return Response(json.dumps({"ok":True}), mimetype="application/json")
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); state=load_state(); cap=state.get("cap",300.0); final=[]
        for tr in state.get("open",[]):
            if tr["symbol"]==sym: cap+=tr.get("net",0); state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE {sym}","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"shark":tr.get("shark",0)})
            else: final.append(tr)
        state["open"]=final; state["cap"]=cap; kv_set(STATE_KEY, state); return Response(json.dumps({"ok":True,"closed":sym}), mimetype="application/json")
    try: st=load_state(); return Response(render(st), mimetype="text/html")
    except Exception as e:
        import traceback; return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:2000]}</pre></body></html>", mimetype="text/html", status=200)
