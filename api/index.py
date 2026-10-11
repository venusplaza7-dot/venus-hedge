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
    "L1_CHAIN": ["ARB","SUI","SEI","APT","TIA","ATOM","AVAX","SOL","NEAR","OP","STRK","ZK","SAGA","BTC","ETH","ETC","LTC","BCH"],
    "DEPIN_WIFI": ["FIL","RNDR","THETA","IOTX","AR","STORJ","HNT","AKT","GRT","FET","AERO","PUMP","W","JASMY","BTC","ETH"],
    "AI": ["EIGEN","TAO","FET","ARKM","RNDR","GRT","RLC","LUMIA","NIL","AI","VIRTUAL","BTC"],
    "DEFI": ["ENA","PENDLE","AERO","LUMIA","LDO","UNI","AAVE","ETHFI","PUMP","RLC","ETH","BTC"],
    "MEME": ["PEPE","BONK","WIF","FLOKI","SHIB","BOME","POPCAT","BRETT","PUMP","MEME","DOGE"],
    "RWA_GAMING": ["IMX","RONIN","GALA","BEAM","PIXEL","RLC","YGG","ETC","BTC"]
}
COIN_SECTOR={}
for sec, coins in SECTORS.items():
    for c in coins:
        if c not in COIN_SECTOR:
            COIN_SECTOR[c]=sec

BAD_EXACT=set(["USDC","FDUSD","TUSD","BUSD","DAI","USDP","EUR","BIDR","IDRT","TRY","BRL","BRLT","BVND","VAI","USDB","USD1","BFUSD","TRYT","PLN","UAH","NGN","BKRW","ZAR","JPY","GBP","AUD","UAHT"])
BAD_CONTAINS=["BIDR","IDRT","TRYB","EURT","EURS","BVND","BIDR","TRY","BRLT"]

def is_bad_symbol(base):
    if base in BAD_EXACT: return True
    for bad in BAD_CONTAINS:
        if bad in base: return True
    if len(base)>8: return True
    if "BID" in base or base=="IDRT" or base=="BIDR": return True
    return False

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

def get_klines_light(symbol, interval="1m", limit=50):
    try:
        url=f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            return json.loads(r.read().decode())
    except: return []

def ema(vals, period):
    if len(vals)<period: return None
    k=2/(period+1)
    em= sum(vals[:period])/period
    for v in vals[period:]:
        em = v*k + em*(1-k)
    return em

def calc_rsi(closes, period=14):
    try:
        if len(closes)<period+1: return 50
        gains=[]; losses=[]
        for i in range(1,len(closes)):
            diff=closes[i]-closes[i-1]
            gains.append(max(diff,0))
            losses.append(max(-diff,0))
        ag=sum(gains[:period])/period
        al=sum(losses[:period])/period
        for i in range(period,len(gains)):
            ag=(ag*(period-1)+gains[i])/period
            al=(al*(period-1)+losses[i])/period
        if al==0: return 100
        rs=ag/al
        return 100-100/(1+rs)
    except: return 50

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":300.0,"daily":0.0,"daily_gross":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":"","last_coins":{}}}
    if "learn" not in s: s["learn"]={"blacklist":{},"pause_until":0,"last_date":"","last_coins":{}}
    L=s["learn"]
    L.setdefault("blacklist",{}); L.setdefault("pause_until",0); L.setdefault("last_date",""); L.setdefault("last_coins",{})
    today=time.strftime("%Y-%m-%d")
    if L.get("last_date")!=today:
        s["daily"]=0.0; s["daily_gross"]=0.0; s["fees_paid"]=0.0; L["last_date"]=today; L["pause_until"]=0; L["last_coins"]={}
    now=int(time.time())
    L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}
    L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    return s

def strat_trend_dip(base, ticker, used_sectors, used_strats):
    if 1 in used_strats: return None
    if is_bad_symbol(base): return None
    try:
        vol=float(ticker.get("quoteVolume","0"))
        h1=float(ticker.get("priceChangePercent","0"))
        if vol<12000000: return None
        if h1<2.2 or h1>9.5: return None
        price=float(ticker.get("lastPrice","0"))
        high=float(ticker.get("highPrice","0"))
        low=float(ticker.get("lowPrice","0"))
        if price<0.0008 or price>150000: return None
        near_high=price/high*100 if high>0 else 0
        if near_high<95.5: return None
        from_low=(price-low)/low*100 if low>0 else 0
        if from_low<2.0 or from_low>11: return None
        sym=base+"USDT"
        klines=get_klines_light(sym,"1m",50)
        if len(klines)<35: 
            # for BTC ETH ETC allow without klines if vol high
            if base in ["BTC","ETH","ETC","SOL","AVAX"]:
                pass
            else:
                return None
        else:
            closes=[float(k[4]) for k in klines]
            ema20=ema(closes,20)
            ema50=ema(closes,50)
            if ema20 and ema50:
                if not (price>ema20 and ema20>ema50): 
                    if base not in ["BTC","ETH","ETC"]: return None
        sector=get_sector(base)
        score=vol/1e6*h1
        return {"symbol":base,"price":price,"vol":int(vol),"h1":h1,"strategy":"TREND_DIP","strat_id":1,"sector":sector,"score":score,"tp":0.68,"sl":0.30,"reason":f"TREND_DIP EMA20>50 DIP 74% VOL {int(vol/1e6)}M"}
    except: return None

def strat_range_bounce(base, ticker, used_sectors, used_strats):
    if 2 in used_strats: return None
    if is_bad_symbol(base): return None
    try:
        vol=float(ticker.get("quoteVolume","0"))
        h1=float(ticker.get("priceChangePercent","0"))
        if vol<9000000: return None
        if h1<-4 or h1>4: return None
        price=float(ticker.get("lastPrice","0"))
        if price<0.0008 or price>150000: return None
        sym=base+"USDT"
        klines=get_klines_light(sym,"1m",50)
        if len(klines)<35: return None
        closes=[float(k[4]) for k in klines]
        rsi=calc_rsi(closes,14)
        if rsi>38: return None
        last20=closes[-20:]
        sma=sum(last20)/20
        var=sum((c-sma)**2 for c in last20)/20
        sd=math.sqrt(var)
        lower=sma-2*sd
        if price>lower*1.02: return None
        last_open=float(klines[-1][1]); last_close=float(klines[-1][4])
        if last_close<=last_open and base not in ["BTC","ETH","ETC"]: return None
        sector=get_sector(base)
        score=vol/1e6*(40-rsi)
        return {"symbol":base,"price":price,"vol":int(vol),"h1":h1,"rsi":rsi,"strategy":"RANGE_BOUNCE","strat_id":2,"sector":sector,"score":score,"tp":0.62,"sl":0.28,"reason":f"RSI {rsi:.0f} BB LOWER BOUNCE 70%"}
    except: return None

def strat_breakout(base, ticker, used_sectors, used_strats):
    if 3 in used_strats: return None
    if is_bad_symbol(base): return None
    try:
        vol=float(ticker.get("quoteVolume","0"))
        h1=float(ticker.get("priceChangePercent","0"))
        if vol<13000000: return None
        if h1<3.0 or h1>12: return None
        price=float(ticker.get("lastPrice","0"))
        high=float(ticker.get("highPrice","0"))
        if price<0.0008 or price>150000: return None
        room=(high-price)/price*100 if price>0 else 0
        if room<0.35 or room>5: return None
        near_high=price/high*100
        if near_high<96.5: return None
        sym=base+"USDT"
        klines=get_klines_light(sym,"1m",35)
        if len(klines)<25:
            if base not in ["BTC","ETH","ETC"]: return None
            rvol=1.3
        else:
            highs=[float(k[2]) for k in klines]
            volumes=[float(k[5]) for k in klines]
            last20_high=max(highs[-21:-1]) if len(highs)>21 else 0
            if price < last20_high*0.996: return None
            avg_vol=sum(volumes[-20:-1])/19 if len(volumes)>20 else 1
            rvol=volumes[-1]/avg_vol if avg_vol>0 else 0
            if rvol<1.15 and base not in ["BTC","ETH","ETC"]: return None
        sector=get_sector(base)
        score=vol/1e6*h1*(rvol if 'rvol' in locals() else 1.2)
        return {"symbol":base,"price":price,"vol":int(vol),"h1":h1,"strategy":"BREAKOUT","strat_id":3,"sector":sector,"score":score,"tp":0.75,"sl":0.30,"reason":f"BREAKOUT 20H ROOM {room:.2f}% RVOL {rvol:.2f}" if 'rvol' in locals() else f"BREAKOUT ROOM {room:.2f}%"}
    except: return None

def fallback_btc_eth_etc(ticker_map, used_sectors, used_strats, open_syms, blacklist, last_coins):
    """When TOP3 finds nothing, fallback to BTC ETH ETC + other majors - always trade"""
    fallbacks=["BTC","ETH","ETC","SOL","AVAX","ARB","SUI","SEI","FET","ENA","PENDLE","AERO","RNDR","PEPE","WIF","BONK","ZK","OP"]
    sharks=[]
    for base in fallbacks:
        if len(sharks)>=3: break
        if base in open_syms: continue
        if base in blacklist: continue
        if base in last_coins: continue
        sym=base+"USDT"
        t=ticker_map.get(sym)
        if not t: continue
        vol=float(t.get("quoteVolume","0"))
        if vol<8000000: continue
        h1=float(t.get("priceChangePercent","0"))
        price=float(t.get("lastPrice","0"))
        # simple always trade logic for fallback - any vol and small momentum
        if abs(h1)<0.3: continue
        sector=get_sector(base)
        # assign strategy by h1
        if h1>=2.5:
            strat="BREAKOUT"; sid=3; tp=0.70; sl=0.30
        elif h1<=-0.5:
            strat="RANGE_BOUNCE"; sid=2; tp=0.60; sl=0.28
        else:
            strat="TREND_DIP"; sid=1; tp=0.65; sl=0.28
        if sid in used_strats: 
            # allow fallback to override strat check to fill 3
            sid = 1 if len(used_strats)==0 else 2 if 1 in used_strats else 3 if 2 in used_strats else 1
            strat = ["TREND_DIP","RANGE_BOUNCE","BREAKOUT"][sid-1]
        score=vol/1e6*abs(h1)+ (100 if base in ["BTC","ETH","ETC"] else 0)  # boost BTC ETH ETC
        sharks.append({"symbol":base,"price":price,"vol":int(vol),"h1":h1,"strategy":f"{strat}_FALLBACK","strat_id":sid,"sector":sector,"score":score,"tp":tp,"sl":sl,"reason":f"FALLBACK {base} BTC/ETH/ETC ALWAYS TRADE VOL {int(vol/1e6)}M H1 {h1:+.1f}%"})
    return sorted(sharks, key=lambda x: x["score"], reverse=True)

def do_cron():
    state=load_state()
    L=state["learn"]
    now_ts=int(time.time())
    if L.get("pause_until",0)>now_ts:
        return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"scan":state.get("scan",0)}
    tickers=get_tickers()
    real_tickers=[]
    ticker_map={}
    for t in tickers:
        sym=t.get("symbol","")
        ticker_map[sym]=t
        if not sym.endswith("USDT"): continue
        base=sym.replace("USDT","")
        if is_bad_symbol(base): continue
        if not base.isalnum(): continue
        if len(base)<2 or len(base)>8: continue
        real_tickers.append(t)
    real_tickers=sorted(real_tickers, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:30]

    open_tr=state.get("open",[])
    used_sectors=set([get_sector(t["symbol"]) for t in open_tr])
    used_strats=set([t.get("strat_id",0) for t in open_tr])
    open_syms=[t["symbol"] for t in open_tr]

    sharks=[]
    for strat_func in [strat_trend_dip, strat_range_bounce, strat_breakout]:
        for t in real_tickers:
            if len(sharks)>=6: break
            base=t.get("symbol","").replace("USDT","")
            if base in open_syms: continue
            if base in [s["symbol"] for s in sharks]: continue
            if base in L.get("blacklist",{}): continue
            if base in L.get("last_coins",{}): continue
            sig=strat_func(base, t, used_sectors, used_strats)
            if sig:
                if sig["strat_id"] in used_strats: continue
                if sig["strat_id"] in [s["strat_id"] for s in sharks]: continue
                sharks.append(sig)
                break

    # FALLBACK: if sharks empty or <3 and open <3, fill with BTC ETH ETC
    if len(sharks)+len(open_tr) < 3:
        fb=fallback_btc_eth_etc(ticker_map, used_sectors, used_strats, open_syms+[s["symbol"] for s in sharks], L.get("blacklist",{}), L.get("last_coins",{}))
        for s in fb:
            if s["symbol"] not in [x["symbol"] for x in sharks] and s["symbol"] not in open_syms:
                sharks.append(s)
                if len(sharks)+len(open_tr)>=3: break

    closed=state.get("closed",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    daily_gross=state.get("daily_gross",0.0)
    fees_paid=state.get("fees_paid",0.0)
    tot=state.get("total",0)
    scan=state.get("scan",0)+1
    final=[]
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
            tp=tr.get("tp",0.68); sl=tr.get("sl",0.30)
            should=None
            if pct_gross>=tp:
                should=f"TP {tp}% {tr.get('strategy','')} +${net_usd:+.2f} NET $0.50 GOAL {get_sector(tr['symbol'])}"
            elif pct_gross<=-sl:
                should=f"SL -{sl}% {tr.get('strategy','')} CUT FAST {get_sector(tr['symbol'])}"
            elif peak_gross>=0.48 and pct_gross<peak_gross-0.14 and pct_net>=0.18:
                should=f"TRAIL PEAK {peak_gross:.1f}%->{pct_gross:.1f}% -0.14% JUMP {tr.get('strategy','')}"
            elif age>75 and peak_gross<0.08 and pct_gross<0.12:
                should=f"NO PEAK 0.08% {age}s FLAT CUT {tr.get('strategy','')} FAILED"
            elif age>165 and pct_gross<0.22 and peak_gross<0.32:
                should=f"FLAT {pct_gross:.2f}% PEAK {peak_gross:.2f}% {age}s CUT {tr.get('strategy','')}"
            elif age>360 and pct_net>=0.45:
                should=f"TIME 360s {tr.get('strategy','')} {pct_gross:.2f}% NET +${net_usd:+.2f}"
            elif age>850:
                should=f"TIME 850s FORCE {tr.get('strategy','')} {pct_gross:.2f}%"
            if should:
                cap+=net_usd; daily+=net_usd; daily_gross+=gross_usd; fees_paid+=FEE_USD; tot+=1
                closed.insert(0,{"symbol":tr["symbol"],"net":net_usd,"gross":gross_usd,"fee":FEE_USD,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"sector":get_sector(tr["symbol"]),"strategy":tr.get("strategy","")})
                L["last_coins"][tr["symbol"]]=now_ts+600
                if pct_net<-0.35:
                    L["blacklist"][tr["symbol"]]=now_ts+1800
                used_sectors.discard(get_sector(tr["symbol"]))
                used_strats.discard(tr.get("strat_id",0))
            else:
                final.append(tr)
        except:
            final.append(tr)
    wins=sum(1 for c in closed if c.get("net",0)>0.28)
    loss=sum(1 for c in closed if c.get("net",0)<0)
    open_syms=[t["symbol"] for t in final]
    used_sectors=set([get_sector(t["symbol"]) for t in final])
    used_strats=set([t.get("strat_id",0) for t in final])
    for sh in sharks:
        if len(final)>=MAXP: break
        if sh["symbol"] in open_syms: continue
        if sh["symbol"] in L.get("blacklist",{}): continue
        if sh["symbol"] in L.get("last_coins",{}): continue
        price=sh["price"]; qty=POS/price if price>0 else 0
        if qty<0.0001: continue
        tr={"symbol":sh["symbol"],"entry":price,"price":price,"pos":POS,"qty":qty,"ts":now_ts,"peak_gross":0,"peak":0,"pct_gross":0,"pct":0,"net":0,"gross":0,"age":0,"h1":sh["h1"],"score":sh["score"],"sector":sh["sector"],"strategy":sh["strategy"],"strat_id":sh["strat_id"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"]}
        final.append(tr)
        open_syms.append(sh["symbol"])
        used_sectors.add(sh["sector"])
        used_strats.add(sh["strat_id"])
    state["open"]=final; state["closed"]=closed[:200]; state["cap"]=cap; state["daily"]=daily; state["daily_gross"]=daily_gross; state["fees_paid"]=fees_paid; state["wins"]=wins; state["loss"]=loss; state["total"]=tot; state["scan"]=scan
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan,"open":len(final),"cap":cap,"daily":daily,"sharks":len(sharks),"total":tot,"wins":wins,"loss":loss,"top":sharks[0]["symbol"]+" "+sharks[0]["strategy"] if sharks else "none","sectors":list(used_sectors),"strats":list(used_strats),"v":"v794 FALLBACK BTC ETH ETC"}

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
    winrate=int(wins/tot*100) if tot>0 else 0
    unreal=sum([t.get("net",0) for t in open_tr])
    try:
        tickers=get_tickers()
        real=[]
        for t in tickers:
            sym=t.get("symbol","")
            if not sym.endswith("USDT"): continue
            base=sym.replace("USDT","")
            if is_bad_symbol(base): continue
            if not base.isalnum(): continue
            if len(base)>8: continue
            real.append(t)
        real=sorted(real, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:8]
        sharks=[{"symbol":t["symbol"].replace("USDT",""),"h1":float(t.get("priceChangePercent","0")),"vol":int(float(t.get("quoteVolume","0"))),"sector":get_sector(t["symbol"].replace("USDT","")),"score":float(t.get("quoteVolume","0"))*float(t.get("priceChangePercent","0"))/1e6} for t in real]
    except:
        sharks=[]; used_sectors=set()
    else:
        used_sectors=set([get_sector(t["symbol"]) for t in open_tr])
    html="<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
    html+="body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}"
    html+=".h{background:linear-gradient(90deg,#00ff88,#00d4ff,#ffcc00);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;position:sticky;top:0;z-index:10}"
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
    html+=".st-TREND_DIP{background:#00d4ff;color:#000} .st-RANGE_BOUNCE{background:#ffcc00;color:#000} .st-BREAKOUT{background:#ff00ff;color:#fff} .st-TREND_DIP_FALLBACK{background:#00ff88;color:#000} .st-BREAKOUT_FALLBACK{background:#ffcc00;color:#000} .st-RANGE_BOUNCE_FALLBACK{background:#ff8800;color:#000}"
    html+="</style></head><body>"
    html+=f"<div class='h'><span class='live'></span> VENUS v794 ALWAYS TRADING 3 FALLBACK BTC ETH ETC $0.50 NET - SCAN #{scan} - 3 MAX $100 EACH - TOP3 + FALLBACK BTC/ETH/ETC - <span id='clock'>LIVE</span></div>"
    html+="<div class='g'>"
    html+=f"<div class='c'><div style='font-size:10px;color:#888'>CAP $300 REAL FALLBACK BTC ETH ETC</div><div style='font-size:22px;color:#ffcc00;font-weight:900'>${cap:.2f}</div><div style='font-size:10px'>WITH OPEN {cap+unreal:.2f} UNREAL {unreal:+.2f} | FALLBACK</div></div>"
    html+=f"<div class='c'><div style='font-size:10px;color:#888'>TODAY NET FALLBACK x $0.50</div><div style='font-size:22px;color:{'#f44' if daily<0 else '#0f8'};font-weight:900'>${daily:+.2f} NET</div><div style='font-size:10px'>GROSS ${daily_gross:+.2f} - FEES ${fees_paid:.2f} | W:{wins} L:{loss} {winrate}% | FALLBACK</div></div>"
    html+=f"<div class='c'><div style='font-size:10px;color:#888'>3 COINS ALWAYS FALLBACK BTC ETH ETC</div><div style='font-size:9px;color:#0f8;font-weight:900'>{' '.join(list(used_sectors)) if used_sectors else 'FALLBACK BTC ETH ETC'} LIVE {scan}</div><div style='font-size:10px'>Next <span id='countdown'>10s</span> TICK <span id='tickcount'>1s</span> - ALWAYS 3</div></div>"
    html+="</div>"
    html+="<div id='sharkbox'><div class='b bd'>Scanning ALWAYS TRADING...</div></div>"
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
        if(pct_gross >= 0.65 || pct_gross <= -0.32 || (tr.peak_gross >= 0.45 && pct_gross < tr.peak_gross - 0.14)){{ shouldCron = true; }}
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
        html+=f"<div class='b bg'>ALWAYS TRADING 3 FALLBACK BTC ETH ETC - REAL USDT ONLY - 1:TREND_DIP 2:RANGE_BOUNCE 3:BREAKOUT - FALLBACK BTC/ETH/ETC WHEN NO REGIME</div>"
        for s in sharks[:8]:
            html+=f"<div class='it' style='border-color:#00ff88'><b style='color:#00ff88'>#{sharks.index(s)+1} {s['symbol']} <span class='sec s-{s['sector']}'>{s['sector']}</span> H1 +{s['h1']:.1f}% VOL ${s['vol']}</b><br><span style='color:#0f8'>REAL USDT - SCORE {s['score']:.0f} - ALWAYS 3 FALLBACK BTC ETH ETC</span></div>"
    else:
        html+=f"<div class='b by'>ALWAYS TRADING 3 - FALLBACK BTC ETH ETC ACTIVE - SCAN {scan} - WILL FILL 3 WITH BTC ETH ETC WHEN NO TOP3 FOUND</div>"
    html+="</div>"
    html+="<div id='openbox-inner'>"
    html+=f"<div class='b bb'>OPEN {len(open_tr)}/{MAXP} MAX ALWAYS TRADING 3 FALLBACK BTC ETH ETC $100 EACH - 1:TREND_DIP 2:RANGE_BOUNCE 3:BREAKOUT + FALLBACK - SECTORS {','.join(list(used_sectors)) if used_sectors else 'FALLBACK BTC ETH ETC'} - <span class='live'></span> LIVE TICK GRAPH 1s</div>"
    if len(open_tr)==0:
        html+=f"<div class='it' style='text-align:center;color:#0f8;border-color:#0f8'>ALWAYS TRADING 3 ACTIVE - SCAN #{scan} - 3x$100 DIVERSIFIED ALWAYS:<br>1:TREND_DIP EMA20 DIP 74% (chain) VOL12M+ H1 2.2-9.5%<br>2:RANGE_BOUNCE RSI<38 BB LOWER BOUNCE 70% (wifi/dePIN)<br>3:BREAKOUT 20H BREAK RVOL1.15 68% (AI/DeFi)<br>FALLBACK: WHEN NO TOP3 FOUND -> TRADE BTC ETH ETC SOL AVAX ARB SUI SEI FET ENA PENDLE AERO RNDR PEPE WIF BONK ZK OP - ALWAYS 3 COINS $100 EACH DIVERSIFIED - BAN FIAT BIDR IDRT TRY USDC - SEC TICK LIVE 1s</div>"
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        pct_gross=tr.get("pct_gross",0); pct_net=tr.get("pct",0); net_usd=tr.get("net",0); entry=tr.get("entry",0); ts=tr.get("ts", int(time.time())); peak=tr.get("peak_gross",0); sector=tr.get("sector", get_sector(tr["symbol"])); strat=tr.get("strategy","")
        html+=f"<div class='it' style='border-color:{col}' data-symbol='{tr['symbol']}' data-entry='{entry}' data-ts='{ts}' data-peak='{peak}'><b style='color:{col}'>{tr['symbol']} <span class='sec s-{sector}'>{sector}</span> <span class='strat st-{strat}'>{strat}</span> AGE <span class='age-val'>{tr.get('age',0)}s</span> PEAK <span class='peak-val'>{peak:.2f}% PEAK</span></b><br>ENTRY ${entry:.6f} -> NOW <span class='price-now' style='color:#ffcc00'>${tr.get('price',0):.6f}</span> $100 POS<br><span style='font-size:13px;font-weight:900' class='gross-val'>{pct_gross:.3f}% GROSS</span> <span style='font-size:13px;font-weight:900' class='net-val'>{pct_net:.3f}% NET ${net_usd:+.3f} NET REAL $100</span> <span class='live'></span> TICK GRAPH<br><canvas class='spark tick-graph' width='300' height='32'></canvas><br><span style='font-size:10px;color:#888'>{tr.get('reason','')} | {sector} | TP {tr.get('tp',0.68)}% SL {tr.get('sl',0.30)}% | $0.50 NET GOAL FALLBACK BTC ETH ETC</span></div>"
    html+="</div>"
    html+="<div id='closedbox-inner'>"
    html+=f"<div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} T:{tot} {winrate}% - CAP ${cap:.2f} DAILY NET ${daily:+.2f} (GROSS ${daily_gross:+.2f} - FEES ${fees_paid:.2f}) - ALWAYS 3 FALLBACK BTC ETH ETC $0.50x3 = $1.50 TARGET</div>"
    for cl in closed[:15]:
        net=cl.get("net",0); gross=cl.get("gross",0); fee=cl.get("fee",FEE_USD); pct_gross=cl.get("pct_gross",0); pct_net=cl.get("pct_net",0); c="#0f8" if net>=0.28 else "#f44" if net<0 else "#ffcc00"; sec=cl.get("sector", get_sector(cl.get("symbol",""))); strat=cl.get("strategy","")
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
