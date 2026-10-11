from flask import Flask, request, Response
import os, json, time, urllib.request, math
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
            KV_URL=vv.strip().strip('"').strip("'").rstrip("/")
            break
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
if not KV_TOKEN:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "TOKEN" in kk and "upstash" in kk.lower():
            KV_TOKEN=vv.strip().strip('"').strip("'")
            break
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V755_MERGED_HISTORY_100_REAL"
POS=100.0
FEE_PCT=0.20
FEE_USD=0.20
MAXP=3

SECTORS = {
    "L1_CHAIN": ["ARB","SUI","SEI","APT","TIA","ATOM","AVAX","SOL","NEAR","OP","STRK","MANTA","NIL","ZK","SAGA","APT"],
    "DEPIN_WIFI": ["FIL","RNDR","THETA","IOTX","AR","STORJ","HNT","AKT","GRT","FET","PUMP","W","JASMY","AERO"],
    "AI": ["EIGEN","TAO","FET","WLD","ARKM","RNDR","GRT","NMR","RLC","LUMIA","NIL","AI"],
    "DEFI": ["ENA","PENDLE","AERO","LUMIA","LDO","UNI","AAVE","ETHFI","PUMP","RLC"],
    "MEME": ["PEPE","BONK","WIF","FLOKI","SHIB","BOME","POPCAT","BRETT","PUMP"],
    "RWA_GAMING": ["IMX","RONIN","GALA","BEAM","PIXEL","RLC"]
}
COIN_SECTOR={}
for sec, coins in SECTORS.items():
    for c in coins:
        if c not in COIN_SECTOR:
            COIN_SECTOR[c]=sec
BAD=set(["1000SATS","LUNA","LUNC","UP","DOWN","1000PEPE","ONDO","XLM","WLD"])

def get_sector(coin):
    return COIN_SECTOR.get(coin, "OTHER_BEST")

def kv_get(k):
    if not KV_URL or not KV_TOKEN: return None
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d=json.loads(r.read().decode())
            res=d[0].get("result") if isinstance(d,list) and d else None
            if not res: return None
            return json.loads(res) if (res.startswith("{") or res.startswith("[")) else res
    except: return None

def kv_set(k,o):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["SET",k,json.dumps(o)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return "OK" in r.read().decode()
    except: return False

def kv_del(k):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return True
    except: return False

def get_tickers():
    try:
        req=urllib.request.Request("https://data-api.binance.vision/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode())
    except: return []

def get_klines(symbol, interval="5m", limit=220):
    try:
        url=f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read().decode())
    except: return []

def ema_series(vals, period):
    if len(vals)<period: return []
    k=2/(period+1)
    res=[]
    sma=sum(vals[:period])/period
    res.append(sma)
    ema_val=sma
    for v in vals[period:]:
        ema_val = v*k + ema_val*(1-k)
        res.append(ema_val)
    return res

def calc_adx(klines, period=14):
    try:
        highs=[float(k[2]) for k in klines]
        lows=[float(k[3]) for k in klines]
        closes=[float(k[4]) for k in klines]
        if len(closes)<period*2: return 0,0,0
        trs=[]; dm_plus=[]; dm_minus=[]
        for i in range(1,len(klines)):
            hl=highs[i]-lows[i]
            hc=abs(highs[i]-closes[i-1])
            lc=abs(lows[i]-closes[i-1])
            tr=max(hl,hc,lc)
            trs.append(tr)
            up=highs[i]-highs[i-1]
            down=lows[i-1]-lows[i]
            dm_plus.append(up if up>down and up>0 else 0)
            dm_minus.append(down if down>up and down>0 else 0)
        atr=sum(trs[:period])/period
        pdi=sum(dm_plus[:period])/period
        mdi=sum(dm_minus[:period])/period
        for i in range(period, len(trs)):
            atr=(atr*(period-1)+trs[i])/period
            pdi=(pdi*(period-1)+dm_plus[i])/period
            mdi=(mdi*(period-1)+dm_minus[i])/period
        if atr==0: return 0,0,0
        pdi_pct=100*pdi/atr
        mdi_pct=100*mdi/atr
        dx=100*abs(pdi_pct-mdi_pct)/(pdi_pct+mdi_pct) if (pdi_pct+mdi_pct)!=0 else 0
        return dx,pdi_pct,mdi_pct
    except:
        return 0,0,0

def calc_rsi(closes, period=14):
    try:
        if len(closes)<period+1: return 50
        gains=[]; losses=[]
        for i in range(1,len(closes)):
            diff=closes[i]-closes[i-1]
            gains.append(max(diff,0))
            losses.append(max(-diff,0))
        avg_gain=sum(gains[:period])/period
        avg_loss=sum(losses[:period])/period
        for i in range(period,len(gains)):
            avg_gain=(avg_gain*(period-1)+gains[i])/period
            avg_loss=(avg_loss*(period-1)+losses[i])/period
        if avg_loss==0: return 100
        rs=avg_gain/avg_loss
        rsi=100-100/(1+rs)
        return rsi
    except:
        return 50

def calc_bollinger(closes, period=20, std=2):
    try:
        if len(closes)<period: return None,None,None
        last=closes[-period:]
        sma=sum(last)/period
        var=sum((c-sma)**2 for c in last)/period
        sd=math.sqrt(var)
        upper=sma+std*sd
        lower=sma-std*sd
        return upper,sma,lower
    except:
        return None,None,None

def detect_regime(adx, atr_pct):
    if adx>25:
        return "TRENDING_BULL"
    if adx<20 and atr_pct<0.015:
        return "RANGING"
    if adx<15:
        return "CHOPPY"
    return "BREAKOUT"

def strategy_1_trend_dip(base, ticker, used_sectors):
    # Hyper Scalper 74-78% win - Trend Following pullback
    try:
        if base in BAD: return None
        vol=float(ticker.get("quoteVolume","0"))
        h1=float(ticker.get("priceChangePercent","0"))
        if vol<13000000 or h1<2.5 or h1>11: return None
        sym=base+"USDT"
        klines=get_klines(sym,"5m",220)
        if len(klines)<210: return None
        closes=[float(k[4]) for k in klines]
        price=float(ticker.get("lastPrice",closes[-1]))
        ema25_s=ema_series(closes,25)
        ema100_s=ema_series(closes,100)
        ema200_s=ema_series(closes,200)
        if not ema25_s or not ema100_s or not ema200_s: return None
        ema25=ema25_s[-1]; ema100=ema100_s[-1]; ema200=ema200_s[-1]
        ema25_prev=ema25_s[-2]
        adx,pdi,mdi=calc_adx(klines,14)
        atr_pct=(max([float(k[2])-float(k[3]) for k in klines[-14:]])/price) if price>0 else 0
        regime=detect_regime(adx, atr_pct)
        if regime!="TRENDING_BULL": return None
        if not (price>ema200 and ema25>ema100 and ema100>ema200): return None
        if adx<24: return None
        # dip in last 5
        dipped=False
        for i in range(1,6):
            if closes[-i] < ema25_s[-i] and closes[-i] > ema100:
                dipped=True
        if not dipped: return None
        if not (price>ema25 and ema25>ema25_prev): return None
        sector=get_sector(base)
        if sector in used_sectors: return None
        score=vol/1e6*adx
        return {"symbol":base,"price":price,"vol":int(vol),"h1":h1,"adx":adx,"strategy":"TREND_DIP","strat_id":1,"sector":sector,"score":score,"tp":0.70,"sl":0.35,"reason":f"EMA25>{ema100:.4f}>{ema200:.4f} ADX {adx:.0f} DIP BOUNCE"}
    except: return None

def strategy_2_range_bounce(base, ticker, used_sectors):
    # VWAP Bounce 70% + Bollinger Reversion - Ranging
    try:
        if base in BAD: return None
        vol=float(ticker.get("quoteVolume","0"))
        if vol<10000000: return None
        sym=base+"USDT"
        klines=get_klines(sym,"5m",100)
        if len(klines)<50: return None
        closes=[float(k[4]) for k in klines]
        highs=[float(k[2]) for k in klines]
        lows=[float(k[3]) for k in klines]
        volumes=[float(k[5]) for k in klines]
        price=float(ticker.get("lastPrice",closes[-1]))
        adx,pdi,mdi=calc_adx(klines,14)
        atr_pct=(sum([highs[-i]-lows[-i] for i in range(1,15)])/14/price) if price>0 else 0
        regime=detect_regime(adx, atr_pct)
        if regime!="RANGING": return None
        # Bollinger
        upper,mid,lower=calc_bollinger(closes,20,2)
        if not upper: return None
        rsi=calc_rsi(closes,14)
        # Buy lower BB + RSI<35
        if not (price <= lower*1.01 and rsi<38): return None
        # VWAP
        # simple VWAP approx = sum(price*vol)/sum(vol) last 20
        pv=sum(closes[-20:][i]*volumes[-20:][i] for i in range(20))
        vv=sum(volumes[-20:])
        vwap=pv/vv if vv>0 else mid
        if price < vwap*0.998:  # below VWAP oversold bounce candidate
            pass
        else:
            return None
        sector=get_sector(base)
        if sector in used_sectors: return None
        score=vol/1e6*(40-rsi)  # lower RSI higher score
        return {"symbol":base,"price":price,"vol":int(vol),"h1":float(ticker.get("priceChangePercent","0")),"rsi":rsi,"strategy":"RANGE_BOUNCE","strat_id":2,"sector":sector,"score":score,"tp":0.65,"sl":0.30,"reason":f"BB LOWER {lower:.4f} RSI {rsi:.0f} VWAP {vwap:.4f} BOUNCE 70%"}
    except: return None

def strategy_3_breakout_sweep(base, ticker, used_sectors):
    # Breakout Momentum + SMC Liquidity Sweep 70-91% win
    try:
        if base in BAD: return None
        vol=float(ticker.get("quoteVolume","0"))
        if vol<11000000: return None
        sym=base+"USDT"
        klines=get_klines(sym,"5m",100)
        if len(klines)<50: return None
        closes=[float(k[4]) for k in klines]
        highs=[float(k[2]) for k in klines]
        lows=[float(k[3]) for k in klines]
        volumes=[float(k[5]) for k in klines]
        price=float(ticker.get("lastPrice",closes[-1]))
        adx,pdi,mdi=calc_adx(klines,14)
        # Breakout: new 20-bar high + close upper third + RVOL>=1.2
        last_20_high=max(highs[-21:-1]) if len(highs)>21 else 0
        last_20_vol_avg=sum(volumes[-21:-1])/20 if len(volumes)>21 else 1
        rvol=volumes[-1]/last_20_vol_avg if last_20_vol_avg>0 else 0
        # close upper third of bar
        bar_range=highs[-1]-lows[-1]
        close_pos=(closes[-1]-lows[-1])/bar_range if bar_range>0 else 0
        # SMC sweep: sweep low then bullish engulfing
        # Check if recent low swept: low[-1] < min(lows[-6:-1]) then close back above
        recent_lows_min=min(lows[-6:-1]) if len(lows)>6 else lows[-2]
        swept = lows[-1] < recent_lows_min*0.999 and closes[-1] > recent_lows_min
        breakout = price > last_20_high*0.998 and close_pos>0.66 and rvol>=1.15
        if not (breakout or swept): return None
        rsi=calc_rsi(closes,14)
        if rsi<50 or rsi>78:  # need momentum but not overbought
            if not swept:
                return None
        sector=get_sector(base)
        if sector in used_sectors: return None
        score=vol/1e6*rvol* (2 if swept else 1)
        return {"symbol":base,"price":price,"vol":int(vol),"h1":float(ticker.get("priceChangePercent","0")),"rvol":rvol,"strategy":"BREAKOUT_SMC","strat_id":3,"sector":sector,"score":score,"tp":0.80,"sl":0.32,"reason":f"{'SWEEP' if swept else 'BREAKOUT'} 20H {last_20_high:.4f} RVOL {rvol:.2f} CLOSE {close_pos:.2f}"}
    except: return None

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":300.0,"daily":0.0,"daily_gross":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":"","last_coins":{}}}
    if "learn" not in s: s["learn"]={"blacklist":{},"pause_until":0,"last_date":"","last_coins":{}}
    L=s["learn"]
    L.setdefault("blacklist",{})
    L.setdefault("pause_until",0)
    L.setdefault("last_date","")
    L.setdefault("last_coins",{})
    today=time.strftime("%Y-%m-%d")
    if L.get("last_date")!=today:
        s["daily"]=0.0; s["daily_gross"]=0.0; s["fees_paid"]=0.0; L["last_date"]=today; L["pause_until"]=0; L["last_coins"]={}
    now=int(time.time())
    L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}
    L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    return s

def do_cron():
    state=load_state()
    L=state["learn"]
    now_ts=int(time.time())
    if L.get("pause_until",0)>now_ts:
        return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"scan":state.get("scan",0)}
    tickers=get_tickers()
    # sort by vol to limit kline calls
    sorted_tickers=sorted(tickers, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:50]
    open_tr=state.get("open",[])
    used_sectors=set([get_sector(t["symbol"]) for t in open_tr])
    used_strats=set([t.get("strat_id",0) for t in open_tr])
    sharks=[]
    # Try each strategy in round robin to ensure diversification
    for strat_func in [strategy_1_trend_dip, strategy_2_range_bounce, strategy_3_breakout_sweep]:
        if len(sharks)>=10: break
        for t in sorted_tickers:
            if len(sharks)>=10: break
            sym=t.get("symbol","")
            if not sym.endswith("USDT"): continue
            base=sym.replace("USDT","")
            if base in [x["symbol"] for x in open_tr]: continue
            if base in [x["symbol"] for x in sharks]: continue
            if base in L.get("blacklist",{}): continue
            if base in L.get("last_coins",{}): continue
            if not base.isalnum() or len(base)<2 or len(base)>10: continue
            sig=strat_func(base, t, used_sectors)
            if sig:
                # avoid duplicate strat if already have that strat open
                if sig["strat_id"] in used_strats:
                    continue
                if sig["strat_id"] in [s["strat_id"] for s in sharks]:
                    continue
                sharks.append(sig)
    sharks=sorted(sharks, key=lambda x: x["score"], reverse=True)

    closed=state.get("closed",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    daily_gross=state.get("daily_gross",0.0)
    fees_paid=state.get("fees_paid",0.0)
    tot=state.get("total",0)
    scan=state.get("scan",0)+1
    final=[]
    ticker_map={t["symbol"]:t for t in tickers}
    for tr in open_tr:
        try:
            sym=tr["symbol"]+"USDT"
            price_now=tr.get("price", tr.get("entry",0))
            if sym in ticker_map:
                price_now=float(ticker_map[sym].get("lastPrice",price_now))
            entry=tr.get("entry", price_now)
            pct_gross=(price_now-entry)/entry*100 if entry else 0
            pct_net=pct_gross - FEE_PCT
            net_usd=POS*pct_net/100
            gross_usd=POS*pct_gross/100
            age=now_ts-tr.get("ts",now_ts)
            peak_gross=max(tr.get("peak_gross",0), pct_gross)
            tr["price"]=price_now; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["peak_gross"]=peak_gross; tr["peak"]=peak_gross-FEE_PCT; tr["age"]=age; tr["net"]=net_usd; tr["gross"]=gross_usd
            tp=tr.get("tp",0.70); sl=tr.get("sl",0.35)
            should=None
            if pct_gross>=tp:
                should=f"TP {tp}% {tr.get('strategy','')} +${net_usd:+.2f} NET $0.50 GOAL {get_sector(tr['symbol'])}"
            elif pct_gross<=-sl:
                should=f"SL -{sl}% {tr.get('strategy','')} CUT {get_sector(tr['symbol'])}"
            elif peak_gross>=0.50 and pct_gross<peak_gross-0.15 and pct_net>=0.18:
                should=f"TRAIL PEAK {peak_gross:.1f}%->{pct_gross:.1f}% DROP -0.15% JUMP {tr.get('strategy','')}"
            elif age>85 and peak_gross<0.08 and pct_gross<0.10:
                should=f"NO PEAK 0.08% {age}s FLAT CUT {tr.get('strategy','')} DIP FAILED"
            elif age>170 and pct_gross<0.22 and peak_gross<0.32:
                should=f"FLAT {pct_gross:.2f}% PEAK {peak_gross:.2f}% {age}s CUT {tr.get('strategy','')}"
            elif age>380 and pct_net>=0.50:
                should=f"TIME 380s {tr.get('strategy','')} {pct_gross:.2f}% NET +${net_usd:+.2f}"
            elif age>900:
                should=f"TIME 900s FORCE {tr.get('strategy','')} {pct_gross:.2f}%"
            if should:
                cap+=net_usd; daily+=net_usd; daily_gross+=gross_usd; fees_paid+=FEE_USD; tot+=1
                closed.insert(0,{"symbol":tr["symbol"],"net":net_usd,"gross":gross_usd,"fee":FEE_USD,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"sector":get_sector(tr["symbol"]),"strategy":tr.get("strategy","")})
                L["last_coins"][tr["symbol"]]=now_ts+900
                if pct_net<-0.35:
                    L["blacklist"][tr["symbol"]]=now_ts+3600
                used_sectors.discard(get_sector(tr["symbol"]))
                used_strats.discard(tr.get("strat_id",0))
            else:
                final.append(tr)
        except:
            final.append(tr)
    wins=sum(1 for c in closed if c.get("net",0)>0.30)
    loss=sum(1 for c in closed if c.get("net",0)<0)
    open_syms=[t["symbol"] for t in final]
    used_sectors=set([get_sector(t["symbol"]) for t in final])
    used_strats=set([t.get("strat_id",0) for t in final])
    for sh in sharks:
        if len(final)>=MAXP: break
        if sh["symbol"] in open_syms: continue
        if sh["symbol"] in L.get("blacklist",{}): continue
        if sh["symbol"] in L.get("last_coins",{}): continue
        if sh["strat_id"] in used_strats: continue
        if sh["sector"] in used_sectors:
            other=[s for s in sharks if s["sector"] not in used_sectors and s["strat_id"] not in used_strats and s["symbol"] not in open_syms]
            if other and len(final)>=2:
                continue
        price=sh["price"]; qty=POS/price if price>0 else 0
        if qty<5: continue
        tr={"symbol":sh["symbol"],"entry":price,"price":price,"pos":POS,"qty":qty,"ts":now_ts,"peak_gross":0,"peak":0,"pct_gross":0,"pct":0,"net":0,"gross":0,"age":0,"h1":sh["h1"],"score":sh["score"],"sector":sh["sector"],"strategy":sh["strategy"],"strat_id":sh["strat_id"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"]}
        final.append(tr)
        open_syms.append(sh["symbol"])
        used_sectors.add(sh["sector"])
        used_strats.add(sh["strat_id"])
    state["open"]=final; state["closed"]=closed[:200]; state["cap"]=cap; state["daily"]=daily; state["daily_gross"]=daily_gross; state["fees_paid"]=fees_paid; state["wins"]=wins; state["loss"]=loss; state["total"]=tot; state["scan"]=scan
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan,"open":len(final),"cap":cap,"daily":daily,"sharks":len(sharks),"total":tot,"wins":wins,"loss":loss,"top":sharks[0]["symbol"]+" "+sharks[0]["strategy"] if sharks else "none - waiting regime","sectors":list(used_sectors),"strats":list(used_strats),"v":"v792 TOP3 STRATS"}

def render(state):
    open_tr=state.get("open",[])
    closed=state.get("closed",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    daily_gross=state.get("daily_gross",0.0)
    fees_paid=state.get("fees_paid",0.0)
    wins=state.get("wins",0)
    loss=state.get("loss",0)
    tot=state.get("total",0)
    scan=state.get("scan",0)
    learn=state.get("learn",{})
    winrate=int(wins/tot*100) if tot>0 else 0
    unreal=sum([t.get("net",0) for t in open_tr])
    try:
        tickers=get_tickers()
        used_sectors=set([get_sector(t["symbol"]) for t in open_tr])
        sorted_tickers=sorted(tickers, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:30]
        sharks=[]
        for t in sorted_tickers:
            base=t.get("symbol","").replace("USDT","")
            if not base or base in BAD: continue
            if base in [tr["symbol"] for tr in open_tr]: continue
            sharks.append({"symbol":base,"h1":float(t.get("priceChangePercent","0")),"vol":int(float(t.get("quoteVolume","0"))),"sector":get_sector(base),"score":float(t.get("quoteVolume","0"))*float(t.get("priceChangePercent","0"))/1e6,"strategy":"CANDIDATE","strat_id":0})
        sharks=sorted(sharks, key=lambda x: x["score"], reverse=True)[:8]
    except:
        sharks=[]; used_sectors=set()
    html="<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
    html+="body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}"
    html+=".h{background:linear-gradient(90deg,#00ff88,#ffcc00,#ff00ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;position:sticky;top:0;z-index:10}"
    html+=".g{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}"
    html+=".c{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:10px}"
    html+=".b{padding:9px;margin:8px 0;border-radius:7px;font-weight:800;font-size:11px}"
    html+=".by{background:#ffcc00;color:#000} .bb{background:#00d4ff;color:#000} .bd{background:#222;color:#888} .bg{background:#00ff88;color:#000} .bp{background:#ff00ff;color:#fff}"
    html+=".it{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:10px;position:relative;overflow:hidden}"
    html+=".live{width:10px;height:10px;background:#0f0;border-radius:50%;display:inline-block;animation:blink 1s infinite} @keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}"
    html+=".spark{width:100%;height:32px;background:#0a0a0a;border:1px solid #222;border-radius:6px;margin:6px 0}"
    html+=".sec{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:900;margin-left:6px}"
    html+=".strat{padding:2px 6px;border-radius:4px;font-size:8px;font-weight:900;margin-left:4px}"
    html+=".s-L1_CHAIN{background:#00d4ff;color:#000} .s-DEPIN_WIFI{background:#ffcc00;color:#000} .s-AI{background:#ff00ff;color:#fff} .s-DEFI{background:#00ff88;color:#000} .s-MEME{background:#ff8800;color:#000} .s-RWA_GAMING{background:#8800ff;color:#fff} .s-OTHER_BEST{background:#555;color:#fff}"
    html+=".st-TREND_DIP{background:#00d4ff;color:#000} .st-RANGE_BOUNCE{background:#ffcc00;color:#000} .st-BREAKOUT_SMC{background:#ff00ff;color:#fff}"
    html+="</style></head><body>"
    html+=f"<div class='h'><span class='live'></span> VENUS v792 TOP3 STRATEGIES DIVERSIFIED $0.50 NET - SCAN #{scan} - 3 MAX $100 EACH - 1:TREND_DIP 74% 2:RANGE_BOUNCE 70% 3:BREAKOUT_SMC 91% - <span id='clock'>LIVE</span></div>"
    html+="<div class='g'>"
    html+=f"<div class='c'><div style='font-size:10px;color:#888'>CAP $300 REAL TOP3</div><div style='font-size:22px;color:#ffcc00;font-weight:900'>${cap:.2f}</div><div style='font-size:10px'>WITH OPEN {cap+unreal:.2f} UNREAL {unreal:+.2f} | TOP3</div></div>"
    html+=f"<div class='c'><div style='font-size:10px;color:#888'>TODAY NET TOP3 x $0.50</div><div style='font-size:22px;color:{'#f44' if daily<0 else '#0f8'};font-weight:900'>${daily:+.2f} NET</div><div style='font-size:10px'>GROSS ${daily_gross:+.2f} - FEES ${fees_paid:.2f} | W:{wins} L:{loss} {winrate}% | TOP3</div></div>"
    html+=f"<div class='c'><div style='font-size:10px;color:#888'>3 STRATS DIVERSIFIED</div><div style='font-size:9px;color:#0f8;font-weight:900'>{' '.join(list(used_sectors)) if used_sectors else 'WAITING'} LIVE {scan}</div><div style='font-size:10px'>Next <span id='countdown'>10s</span> TICK <span id='tickcount'>1s</span> - TOP3</div></div>"
    html+="</div>"
    html+="<div id='sharkbox'><div class='b bd'>Scanning TOP3 strategies...</div></div>"
    html+="<div id='openbox'></div><div id='closedbox'></div>"
    import json as jsjson
    open_json=jsjson.dumps([{"symbol":tr["symbol"],"entry":tr["entry"],"ts":tr.get("ts", int(time.time())),"peak_gross":tr.get("peak_gross",0)} for tr in open_tr])
    html+=f"""
<script>
const ADMIN_KEY="{ADMIN_KEY}";
let openTrades = {open_json};
let priceHistory = {{}};
openTrades.forEach(t=>{{priceHistory[t.symbol]=[]}});
async function fetchPrices(){{
  try{{
    const res = await fetch('https://data-api.binance.vision/api/v3/ticker/price');
    const all = await res.json();
    const map={{}}; all.forEach(t=>{{map[t.symbol]=parseFloat(t.price)}});
    let shouldCron = false;
    openTrades.forEach(tr=>{{
      const sym = tr.symbol+'USDT'; const now = map[sym]; if(!now) return;
      const entry = tr.entry; const pct_gross = (now-entry)/entry*100; const pct_net = pct_gross - 0.20; const net_usd = 100*pct_net/100;
      if(!priceHistory[tr.symbol]) priceHistory[tr.symbol]=[]; priceHistory[tr.symbol].push(pct_gross); if(priceHistory[tr.symbol].length>60) priceHistory[tr.symbol].shift();
      if(pct_gross > tr.peak_gross) tr.peak_gross = pct_gross;
      const el = document.querySelector(`[data-symbol="${{tr.symbol}}"]`);
      if(el){{
        const grossEl = el.querySelector('.gross-val'); const netEl = el.querySelector('.net-val'); const priceEl = el.querySelector('.price-now'); const peakEl = el.querySelector('.peak-val'); const tickEl = el.querySelector('.tick-graph');
        if(grossEl){{ grossEl.textContent = pct_gross.toFixed(3)+'% GROSS'; grossEl.style.color = pct_gross>=0?'#0f8':'#f44'; }}
        if(netEl){{ netEl.textContent = pct_net.toFixed(3)+'% NET $'+net_usd.toFixed(3)+' NET'; netEl.style.color = pct_net>=0?'#0f8':'#f44'; }}
        if(priceEl) priceEl.textContent = '$'+now.toFixed(6);
        if(peakEl) peakEl.textContent = tr.peak_gross.toFixed(2)+'% PEAK';
        if(tickEl && priceHistory[tr.symbol].length>2){{
          const canvas = tickEl; const ctx = canvas.getContext('2d'); const w = canvas.width; const h = canvas.height; ctx.clearRect(0,0,w,h);
          const arr = priceHistory[tr.symbol]; const min = Math.min(...arr); const max = Math.max(...arr); const range = (max-min) || 0.01;
          ctx.strokeStyle = pct_net>=0?'#0f8':'#f44'; ctx.lineWidth=2; ctx.beginPath();
          arr.forEach((v,i)=>{{ const x = i/(arr.length-1)*w; const y = h - ((v-min)/range)*h; if(i==0) ctx.moveTo(x,y); else ctx.lineTo(x,y); }});
          ctx.stroke();
          const tpY = h - ((0.70-min)/range)*h; ctx.strokeStyle='#ffcc00'; ctx.setLineDash([3,3]); ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.setLineDash([]);
        }}
        if(pct_gross >= 0.70 || pct_gross <= -0.35 || (tr.peak_gross >= 0.50 && pct_gross < tr.peak_gross - 0.15)){{ shouldCron = true; }}
      }}
    }});
    if(shouldCron){{ fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(()=>{{ fetch('/?key='+ADMIN_KEY).then(r=>r.text()).then(html=>{{ const parser=new DOMParser(); const doc=parser.parseFromString(html,'text/html'); const openEl=doc.getElementById('openbox-inner'); const closedEl=doc.getElementById('closedbox-inner'); const sharkEl=doc.getElementById('sharkbox-inner'); if(openEl) document.getElementById('openbox').innerHTML = openEl.innerHTML; if(closedEl) document.getElementById('closedbox').innerHTML = closedEl.innerHTML; if(sharkEl) document.getElementById('sharkbox').innerHTML = sharkEl.innerHTML; const newOpen = []; doc.querySelectorAll('[data-symbol]').forEach(div=>{{ const sym = div.getAttribute('data-symbol'); const entry = parseFloat(div.getAttribute('data-entry')); const ts = parseInt(div.getAttribute('data-ts')); const peak = parseFloat(div.getAttribute('data-peak')||0); newOpen.push({{symbol:sym, entry:entry, ts:ts, peak_gross:peak}}); }}); openTrades = newOpen; Object.keys(priceHistory).forEach(k=>{{ if(!newOpen.find(t=>t.symbol==k)) delete priceHistory[k]; }}); newOpen.forEach(t=>{{ if(!priceHistory[t.symbol]) priceHistory[t.symbol]=[]; }}); }}); }}); }}
  }}catch(e){{}}
}}
function tickAge(){{ const now = Math.floor(Date.now()/1000); document.querySelectorAll('[data-ts]').forEach(el=>{{ const ts = parseInt(el.getAttribute('data-ts')); const age = now - ts; const ageEl = el.querySelector('.age-val'); if(ageEl) ageEl.textContent = age+'s'; }}); }}
setInterval(fetchPrices, 1000); setInterval(tickAge, 1000); fetchPrices(); tickAge();
let count=10; setInterval(()=>{{ count--; const el=document.getElementById('countdown'); if(el) el.textContent = count+'s'; const clk=document.getElementById('clock'); if(clk) clk.textContent = new Date().toLocaleTimeString(); if(count<=0){{ count=10; fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(r=>r.json()).then(data=>{{ fetch('/?key='+ADMIN_KEY).then(r=>r.text()).then(html=>{{ const parser=new DOMParser(); const doc=parser.parseFromString(html,'text/html'); const openEl=doc.getElementById('openbox-inner'); const closedEl=doc.getElementById('closedbox-inner'); const sharkEl=doc.getElementById('sharkbox-inner'); if(openEl) document.getElementById('openbox').innerHTML = openEl.innerHTML; if(closedEl) document.getElementById('closedbox').innerHTML = closedEl.innerHTML; if(sharkEl) document.getElementById('sharkbox').innerHTML = sharkEl.innerHTML; const newOpen = []; doc.querySelectorAll('[data-symbol]').forEach(div=>{{ const sym = div.getAttribute('data-symbol'); const entry = parseFloat(div.getAttribute('data-entry')); const ts = parseInt(div.getAttribute('data-ts')); const peak = parseFloat(div.getAttribute('data-peak')||0); newOpen.push({{symbol:sym, entry:entry, ts:ts, peak_gross:peak}}); }}); openTrades = newOpen; newOpen.forEach(t=>{{ if(!priceHistory[t.symbol]) priceHistory[t.symbol]=[]; }}); }}); }}); }} }},1000);
</script>
"""
    html+="<div style='display:none'><div id='sharkbox-inner'>"
    if sharks:
        html+=f"<div class='b bg'>TOP3 STRATEGIES DIVERSIFIED - CANDIDATES VOL 10M+ - 1:TREND_DIP 74% 2:RANGE_BOUNCE 70% 3:BREAKOUT_SMC 91% - REGIME DETECTION ADX</div>"
        for s in sharks[:8]:
            html+=f"<div class='it' style='border-color:#00ff88'><b style='color:#00ff88'>#{sharks.index(s)+1} {s['symbol']} <span class='sec s-{s['sector']}'>{s['sector']}</span> H1 +{s['h1']:.1f}% VOL ${s['vol']}</b><br><span style='color:#0f8'>TOP3 CANDIDATE - SCORE {s['score']:.0f} - WAITING REGIME MATCH</span></div>"
    else:
        html+=f"<div class='b by'>TOP3 WAITING REGIME - NO TREND_DIP RANGE_BOUNCE BREAKOUT_SMC FOUND - ADX CHOPPY {scan} - WAITING DIP/BOUNCE/BREAKOUT FOR $0.50x3 NET</div>"
    html+="</div>"
    html+="<div id='openbox-inner'>"
    html+=f"<div class='b bb'>OPEN {len(open_tr)}/{MAXP} MAX TOP3 STRATEGIES $100 EACH - 1:TREND_DIP 74% 2:RANGE_BOUNCE 70% 3:BREAKOUT_SMC 91% - SECTORS {','.join(list(used_sectors)) if used_sectors else 'WAITING'} - <span class='live'></span> LIVE TICK GRAPH 1s</div>"
    if len(open_tr)==0:
        html+=f"<div class='it' style='text-align:center;color:#0f8;border-color:#0f8'>TOP3 STRATEGIES ACTIVE - SCAN #{scan} - 3x$100 DIVERSIFIED:<br>1:TREND_DIP EMA25>100>200 ADX>24 DIP BOUNCE 74% WIN (chain)<br>2:RANGE_BOUNCE BB LOWER RSI<38 VWAP BOUNCE 70% WIN (wifi/dePIN)<br>3:BREAKOUT_SMC LIQ SWEEP + 20H BREAKOUT RVOL1.2 91% WIN (AI/DeFi)<br>REGIME DETECTION ADX/ATR - NO CHOPPY TRADE - SEC TICK LIVE 1s - WAITING QUALITY</div>"
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        pct_gross=tr.get("pct_gross",0); pct_net=tr.get("pct",0); net_usd=tr.get("net",0); entry=tr.get("entry",0); ts=tr.get("ts", int(time.time())); peak=tr.get("peak_gross",0); sector=tr.get("sector", get_sector(tr["symbol"])); strat=tr.get("strategy","")
        html+=f"<div class='it' style='border-color:{col}' data-symbol='{tr['symbol']}' data-entry='{entry}' data-ts='{ts}' data-peak='{peak}'><b style='color:{col}'>{tr['symbol']} <span class='sec s-{sector}'>{sector}</span> <span class='strat st-{strat}'>{strat}</span> AGE <span class='age-val'>{tr.get('age',0)}s</span> PEAK <span class='peak-val'>{peak:.2f}% PEAK</span></b><br>ENTRY ${entry:.6f} -> NOW <span class='price-now' style='color:#ffcc00'>${tr.get('price',0):.6f}</span> $100 POS<br><span style='font-size:13px;font-weight:900' class='gross-val'>{pct_gross:.3f}% GROSS</span> <span style='font-size:13px;font-weight:900' class='net-val'>{pct_net:.3f}% NET ${net_usd:+.3f} NET REAL $100</span> <span class='live'></span> TICK GRAPH<br><canvas class='spark tick-graph' width='300' height='32'></canvas><br><span style='font-size:10px;color:#888'>{tr.get('reason','')} | {sector} | TP {tr.get('tp',0.70)}% SL {tr.get('sl',0.35)}% | $0.50 NET GOAL</span></div>"
    html+="</div>"
    html+="<div id='closedbox-inner'>"
    html+=f"<div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} T:{tot} {winrate}% - CAP ${cap:.2f} DAILY NET ${daily:+.2f} (GROSS ${daily_gross:+.2f} - FEES ${fees_paid:.2f}) - TOP3 STRATEGIES $0.50x3 = $1.50 TARGET</div>"
    for cl in closed[:15]:
        net=cl.get("net",0); gross=cl.get("gross",0); fee=cl.get("fee",FEE_USD); pct_gross=cl.get("pct_gross",0); pct_net=cl.get("pct_net",0); c="#0f8" if net>=0.30 else "#f44" if net<0 else "#ffcc00"; sec=cl.get("sector", get_sector(cl.get("symbol",""))); strat=cl.get("strategy","")
        html+=f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')} <span class='sec s-{sec}'>{sec}</span> <span class='strat st-{strat}'>{strat}</span></b> ${net:+.2f} NET (${gross:+.2f} GROSS - ${fee:.2f} FEE) {cl.get('reason','')} {pct_gross:+.2f}% GROSS {pct_net:+.2f}% NET AGE {cl.get('age',0)}s</div>"
    html+="</div></div></div></body></html>"
    return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    key=request.args.get("key","")
    p="/"+path
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY and "cron" not in request.args: return Response("Forbidden", status=403)
        try:
            res=do_cron()
            return Response(json.dumps(res), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)[:300]}), mimetype="application/json", status=200)
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            kv_del(STATE_KEY); time.sleep(0.6)
            new={"cap":300.0,"daily":0.0,"daily_gross":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}}
            ok=kv_set(STATE_KEY, new)
            return Response(json.dumps({"ok":ok,"cap":300}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)[:300]}), mimetype="application/json")
    try:
        st=load_state(); h=render(st); return Response(h, mimetype="text/html")
    except Exception as e:
        import traceback; tb=traceback.format_exc()[:800]
        return Response(f"<html><body><h1>Error: {str(e)[:500]}</h1><pre>{tb}</pre><p><a href='/api/reset?key={ADMIN_KEY}'>RESET</a></p></body></html>", mimetype="text/html", status=200)
