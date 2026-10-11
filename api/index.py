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
    "L1_CHAIN": ["BTC","ETH","ETC","ARB","SUI","SEI","APT","TIA","ATOM","AVAX","SOL","NEAR","OP","STRK","ZK","SAGA","DOGE"],
    "DEPIN_WIFI": ["FIL","RNDR","THETA","IOTX","AR","STORJ","HNT","AKT","GRT","FET","AERO","W","JASMY","BTC","ETH"],
    "AI": ["EIGEN","TAO","FET","ARKM","RNDR","GRT","RLC","LUMIA","AI"],
    "DEFI": ["ENA","PENDLE","AERO","LDO","UNI","AAVE","ETHFI","BTC","ETH","AVAX"],
    "MEME": ["PEPE","BONK","WIF","FLOKI","SHIB","BOME","POPCAT","BRETT","DOGE","PUMP"],
    "RWA_GAMING": ["IMX","RONIN","GALA","BEAM","PIXEL","ETC","BTC","SUI"]
}
COIN_SECTOR={}
for sec, coins in SECTORS.items():
    for c in coins:
        if c not in COIN_SECTOR:
            COIN_SECTOR[c]=sec

BAD_EXACT=set(["USDC","FDUSD","TUSD","BUSD","DAI","USDP","EUR","BIDR","IDRT","TRY","BRL","BRLT","BVND","VAI","USDB","USD1","BFUSD","TRYT","PLN","UAH","NGN","BKRW","ZAR","JPY","GBP","AUD","UAHT","MATICBIDR","SOLBIDR","XRPBIDR","BUSDBIDR","STRKTRY","IDRT","BUSDTRY","BTCBIDR"])
BAD_CONTAINS=["BIDR","IDRT","TRYB","EURT","EURS","BVND","BRLT"]

def is_bad_symbol(base):
    if base in BAD_EXACT: return True
    for bad in BAD_CONTAINS:
        if bad in base: return True
    if len(base)>8: return True
    if "BID" in base: return True
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

def get_klines_light(symbol, interval="5m", limit=50):
    try:
        url=f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
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

def get_market_regime(ticker_map):
    """Fixed: BTC price from ticker if klines fail, no more BTC $0"""
    try:
        btc_ticker=ticker_map.get("BTCUSDT")
        btc_price_ticker=float(btc_ticker.get("lastPrice","0")) if btc_ticker else 0
        klines=get_klines_light("BTCUSDT","5m",80)
        if len(klines)<40:
            # fallback to ticker + simple bias from H1
            h1=float(btc_ticker.get("priceChangePercent","0")) if btc_ticker else 0
            if h1>0.8:
                return {"regime":"TRENDING_BULL","bias":"LONG","btc_price":btc_price_ticker,"adx":20,"pdi":30,"mdi":18,"ema50":btc_price_ticker*0.999,"ema200":btc_price_ticker*0.995,"atr_pct":0.008,"reason":f"BULL fallback ticker H1 +{h1:.1f}% BTC ${btc_price_ticker:.0f}"}
            elif h1<-0.8:
                return {"regime":"TRENDING_BEAR","bias":"SHORT","btc_price":btc_price_ticker,"adx":20,"pdi":18,"mdi":30,"ema50":btc_price_ticker*1.001,"ema200":btc_price_ticker*1.005,"atr_pct":0.008,"reason":f"BEAR fallback ticker H1 {h1:.1f}% BTC ${btc_price_ticker:.0f}"}
            else:
                return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price_ticker,"adx":15,"pdi":25,"mdi":25,"ema50":btc_price_ticker,"ema200":btc_price_ticker,"atr_pct":0.006,"reason":f"RANGING fallback H1 {h1:+.1f}% BTC ${btc_price_ticker:.0f}"}
        closes=[float(k[4]) for k in klines]
        price=closes[-1]
        if btc_price_ticker>0:
            price=btc_price_ticker  # use real ticker price, not $0
        ema50=ema(closes,50)
        ema200=ema(closes,70) if len(closes)>=70 else ema(closes,50)
        adx,pdi,mdi=calc_adx(klines,14)
        highs=[float(k[2]) for k in klines[-14:]]
        lows=[float(k[3]) for k in klines[-14:]]
        atr=sum([highs[i]-lows[i] for i in range(len(highs))])/len(highs) if highs else 0
        atr_pct=atr/price if price>0 else 0
        if ema50 and ema200:
            if price>ema50>ema200 and pdi>mdi and adx>20:
                return {"regime":"TRENDING_BULL","bias":"LONG","btc_price":price,"adx":adx,"pdi":pdi,"mdi":mdi,"ema50":ema50,"ema200":ema200,"atr_pct":atr_pct,"reason":f"BULL Price>{ema50:.0f}>{ema200:.0f} ADX {adx:.0f} PDI {pdi:.0f}>MDI {mdi:.0f} BTC ${price:.0f}"}
            elif price<ema50<ema200 and mdi>pdi and adx>20:
                return {"regime":"TRENDING_BEAR","bias":"SHORT","btc_price":price,"adx":adx,"pdi":pdi,"mdi":mdi,"ema50":ema50,"ema200":ema200,"atr_pct":atr_pct,"reason":f"BEAR Price<{ema50:.0f}<{ema200:.0f} ADX {adx:.0f} MDI {mdi:.0f}>PDI {pdi:.0f} BTC ${price:.0f}"}
        if adx<17 and atr_pct<0.011:
            return {"regime":"RANGING","bias":"BOTH","btc_price":price,"adx":adx,"pdi":pdi,"mdi":mdi,"ema50":ema50,"ema200":ema200,"atr_pct":atr_pct,"reason":f"RANGING ADX {adx:.0f}<17 ATR% {atr_pct*100:.2f}% BTC ${price:.0f} BOTH"}
        if adx<13:
            return {"regime":"CHOPPY","bias":"BOTH","btc_price":price,"adx":adx,"pdi":pdi,"mdi":mdi,"ema50":ema50,"ema200":ema200,"atr_pct":atr_pct,"reason":f"CHOPPY ADX {adx:.0f}<13 BTC ${price:.0f} BOTH but small"}
        return {"regime":"BREAKOUT","bias":"BOTH","btc_price":price,"adx":adx,"pdi":pdi,"mdi":mdi,"ema50":ema50,"ema200":ema200,"atr_pct":atr_pct,"reason":f"BREAKOUT ADX {adx:.0f} BTC ${price:.0f} BOTH"}
    except Exception as e:
        btc_ticker=ticker_map.get("BTCUSDT")
        btc_price=float(btc_ticker.get("lastPrice","83886")) if btc_ticker else 83886
        return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price,"adx":18,"pdi":25,"mdi":25,"ema50":btc_price,"ema200":btc_price,"atr_pct":0.007,"reason":f"Error {str(e)[:40]} fallback BTC ${btc_price:.0f} RANGING BOTH"}

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

# FIXED STRATEGIES: lower TP, longer hold, allow SHORT
def strat_long_trend_dip(base, ticker, market):
    if market["bias"] not in ["LONG","BOTH"]: return None
    if is_bad_symbol(base): return None
    try:
        vol=float(ticker.get("quoteVolume","0"))
        h1=float(ticker.get("priceChangePercent","0"))
        if vol<8000000: return None
        if h1<1.2 or h1>10: return None
        price=float(ticker.get("lastPrice","0"))
        if price<0.0005 or price>200000: return None
        sym=base+"USDT"
        klines=get_klines_light(sym,"5m",40)
        if len(klines)<25: return None
        closes=[float(k[4]) for k in klines]
        ema20=ema(closes,20); ema50=ema(closes,50)
        if not ema20 or not ema50: return None
        if not (price>ema20*0.998 and ema20>ema50*0.999): return None
        # allow small dip
        sector=get_sector(base)
        score=vol/1e6*h1
        if base in ["BTC","ETH","ETC","SOL","AVAX","ARB","SUI","NEAR","STRK","FET","ENA","PENDLE","AERO","SUI","OP","DOGE"]: score*=1.6
        return {"symbol":base,"side":"LONG","price":price,"vol":int(vol),"h1":h1,"strategy":"LONG_TREND_DIP","strat_id":1,"sector":sector,"score":score,"tp":0.48,"sl":0.32,"reason":f"LONG DIP EMA20>{ema50:.2f} Market {market['regime']} BTC ${market['btc_price']:.0f}"}
    except: return None

def strat_short_trend_top(base, ticker, market):
    if market["bias"] not in ["SHORT","BOTH"]: return None
    if is_bad_symbol(base): return None
    try:
        vol=float(ticker.get("quoteVolume","0"))
        h1=float(ticker.get("priceChangePercent","0"))
        if vol<8000000: return None
        if h1>-1.2 and h1<10: 
            if h1>-0.8: return None
        if h1<-12: return None
        price=float(ticker.get("lastPrice","0"))
        if price<0.0005 or price>200000: return None
        sym=base+"USDT"
        klines=get_klines_light(sym,"5m",40)
        if len(klines)<25: return None
        closes=[float(k[4]) for k in klines]
        ema20=ema(closes,20); ema50=ema(closes,50)
        if not ema20 or not ema50: return None
        if not (price<ema20*1.002 and ema20<ema50*1.001): return None
        sector=get_sector(base)
        score=vol/1e6*abs(h1)
        return {"symbol":base,"side":"SHORT","price":price,"vol":int(vol),"h1":h1,"strategy":"SHORT_TREND_TOP","strat_id":1,"sector":sector,"score":score,"tp":0.48,"sl":0.32,"reason":f"SHORT TOP EMA20<{ema50:.2f} Market {market['regime']} BEAR BTC ${market['btc_price']:.0f}"}
    except: return None

def strat_long_bounce(base, ticker, market):
    if market["bias"]=="SHORT" and market["regime"]!="RANGING": return None
    if is_bad_symbol(base): return None
    try:
        vol=float(ticker.get("quoteVolume","0"))
        h1=float(ticker.get("priceChangePercent","0"))
        if vol<6000000: return None
        if abs(h1)>5: return None
        price=float(ticker.get("lastPrice","0"))
        if price<0.0005 or price>200000: return None
        sym=base+"USDT"
        klines=get_klines_light(sym,"5m",40)
        if len(klines)<30: return None
        closes=[float(k[4]) for k in klines]
        rsi=calc_rsi(closes,14)
        if rsi>42: return None
        last20=closes[-20:]
        sma=sum(last20)/20
        var=sum((c-sma)**2 for c in last20)/20
        sd=math.sqrt(var)
        lower=sma-2*sd
        if price>lower*1.025: return None
        sector=get_sector(base)
        score=vol/1e6*(45-rsi)
        return {"symbol":base,"side":"LONG","price":price,"vol":int(vol),"h1":h1,"rsi":rsi,"strategy":"LONG_BOUNCE","strat_id":2,"sector":sector,"score":score,"tp":0.45,"sl":0.30,"reason":f"LONG BOUNCE RSI {rsi:.0f} BB LOW Market {market['regime']}"}
    except: return None

def strat_short_bounce(base, ticker, market):
    if market["bias"]=="LONG" and market["regime"]!="RANGING": return None
    if is_bad_symbol(base): return None
    try:
        vol=float(ticker.get("quoteVolume","0"))
        h1=float(ticker.get("priceChangePercent","0"))
        if vol<6000000: return None
        if abs(h1)>5: return None
        price=float(ticker.get("lastPrice","0"))
        if price<0.0005 or price>200000: return None
        sym=base+"USDT"
        klines=get_klines_light(sym,"5m",40)
        if len(klines)<30: return None
        closes=[float(k[4]) for k in klines]
        rsi=calc_rsi(closes,14)
        if rsi<58: return None
        last20=closes[-20:]
        sma=sum(last20)/20
        var=sum((c-sma)**2 for c in last20)/20
        sd=math.sqrt(var)
        upper=sma+2*sd
        if price<upper*0.975: return None
        sector=get_sector(base)
        score=vol/1e6*(rsi-50)
        return {"symbol":base,"side":"SHORT","price":price,"vol":int(vol),"h1":h1,"rsi":rsi,"strategy":"SHORT_TOP","strat_id":2,"sector":sector,"score":score,"tp":0.45,"sl":0.30,"reason":f"SHORT TOP RSI {rsi:.0f} BB HIGH Market {market['regime']}"}
    except: return None

def strat_breakout_long(base, ticker, market):
    if market["bias"] not in ["LONG","BOTH"]: return None
    if is_bad_symbol(base): return None
    try:
        vol=float(ticker.get("quoteVolume","0"))
        h1=float(ticker.get("priceChangePercent","0"))
        if vol<10000000: return None
        if h1<2.0 or h1>13: return None
        price=float(ticker.get("lastPrice","0"))
        high=float(ticker.get("highPrice","0"))
        room=(high-price)/price*100 if price>0 else 0
        if room<0.25 or room>5: return None
        near_high=price/high*100
        if near_high<96: return None
        sym=base+"USDT"
        klines=get_klines_light(sym,"5m",30)
        if len(klines)>=20:
            highs=[float(k[2]) for k in klines]
            last20_high=max(highs[-21:-1]) if len(highs)>21 else 0
            if price < last20_high*0.995: return None
        sector=get_sector(base)
        score=vol/1e6*h1
        return {"symbol":base,"side":"LONG","price":price,"vol":int(vol),"h1":h1,"strategy":"LONG_BREAKOUT","strat_id":3,"sector":sector,"score":score,"tp":0.52,"sl":0.32,"reason":f"LONG BREAKOUT ROOM {room:.2f}% H1 {h1:.1f}% Market {market['regime']}"}
    except: return None

def strat_breakdown_short(base, ticker, market):
    if market["bias"] not in ["SHORT","BOTH"]: return None
    if is_bad_symbol(base): return None
    try:
        vol=float(ticker.get("quoteVolume","0"))
        h1=float(ticker.get("priceChangePercent","0"))
        if vol<10000000: return None
        if h1>-2.0 or h1<-13: return None
        price=float(ticker.get("lastPrice","0"))
        low=float(ticker.get("lowPrice","0"))
        room=(price-low)/price*100 if price>0 else 0
        if room<0.25 or room>5: return None
        near_low=price/low*100
        if near_low>104: return None
        sym=base+"USDT"
        klines=get_klines_light(sym,"5m",30)
        if len(klines)>=20:
            lows=[float(k[3]) for k in klines]
            last20_low=min(lows[-21:-1]) if len(lows)>21 else 999999
            if price > last20_low*1.005: return None
        sector=get_sector(base)
        score=vol/1e6*abs(h1)
        return {"symbol":base,"side":"SHORT","price":price,"vol":int(vol),"h1":h1,"strategy":"SHORT_BREAKDOWN","strat_id":3,"sector":sector,"score":score,"tp":0.52,"sl":0.32,"reason":f"SHORT BREAKDOWN ROOM {room:.2f}% H1 {h1:.1f}% BEAR Market {market['regime']}"}
    except: return None

def fallback_always(ticker_map, market, open_syms, blacklist, last_coins):
    fallbacks=["BTC","ETH","ETC","SOL","AVAX","ARB","SUI","SEI","FET","ENA","PENDLE","AERO","RNDR","PEPE","WIF","BONK","ZK","OP","DOGE","NEAR","STRK","TIA"]
    sharks=[]
    bias=market["bias"]
    for base in fallbacks:
        if len(sharks)>=3: break
        if base in open_syms: continue
        if base in blacklist: continue
        if base in last_coins: continue
        sym=base+"USDT"
        t=ticker_map.get(sym)
        if not t: continue
        vol=float(t.get("quoteVolume","0"))
        if vol<5000000: continue
        h1=float(t.get("priceChangePercent","0"))
        price=float(t.get("lastPrice","0"))
        if abs(h1)<0.15: continue
        if bias=="SHORT":
            side="SHORT" if h1<0 else "SHORT" if h1<1.5 else "LONG"
        elif bias=="LONG":
            side="LONG" if h1>0 else "LONG" if h1>-1.5 else "SHORT"
        else:
            side="LONG" if h1>0 else "SHORT"
        sector=get_sector(base)
        score=vol/1e6*abs(h1)+ (120 if base in ["BTC","ETH","ETC"] else 0)
        tp=0.48 if side=="LONG" else 0.48
        sharks.append({"symbol":base,"side":side,"price":price,"vol":int(vol),"h1":h1,"strategy":f"{side}_FALLBACK","strat_id":len(sharks)+1,"sector":sector,"score":score,"tp":tp,"sl":0.30,"reason":f"FALLBACK {base} {side} ALWAYS BTC ${market['btc_price']:.0f} {market['regime']} {market['bias']} H1 {h1:+.1f}%"})
    return sorted(sharks, key=lambda x: x["score"], reverse=True)

def do_cron():
    state=load_state()
    L=state["learn"]
    now_ts=int(time.time())
    if L.get("pause_until",0)>now_ts:
        return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"scan":state.get("scan",0)}
    tickers=get_tickers()
    ticker_map={}
    real_tickers=[]
    for t in tickers:
        sym=t.get("symbol","")
        ticker_map[sym]=t
        if not sym.endswith("USDT"): continue
        base=sym.replace("USDT","")
        if is_bad_symbol(base): continue
        if not base.isalnum(): continue
        if len(base)<2 or len(base)>8: continue
        real_tickers.append(t)
    real_tickers=sorted(real_tickers, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:20]
    market=get_market_regime(ticker_map)

    open_tr=state.get("open",[])
    used_sectors=set([get_sector(t["symbol"]) for t in open_tr])
    used_strats=set([t.get("strat_id",0) for t in open_tr])
    open_syms=[t["symbol"] for t in open_tr]

    sharks=[]
    # choose strats based on market bias
    if market["bias"]=="LONG":
        strat_list=[strat_long_trend_dip, strat_long_bounce, strat_breakout_long]
    elif market["bias"]=="SHORT":
        strat_list=[strat_short_trend_top, strat_short_bounce, strat_breakdown_short]
    else:
        strat_list=[strat_long_trend_dip, strat_short_trend_top, strat_long_bounce, strat_short_bounce, strat_breakout_long, strat_breakdown_short]

    for strat_func in strat_list:
        for t in real_tickers:
            if len(sharks)>=6: break
            base=t.get("symbol","").replace("USDT","")
            if base in open_syms: continue
            if base in [s["symbol"] for s in sharks]: continue
            if base in L.get("blacklist",{}): continue
            if base in L.get("last_coins",{}): continue
            sig=strat_func(base, t, market)
            if sig:
                if sig["strat_id"] in used_strats: continue
                if sig["strat_id"] in [s["strat_id"] for s in sharks]: continue
                sharks.append(sig)
                break

    if len(sharks)+len(open_tr) < 3:
        fb=fallback_always(ticker_map, market, open_syms+[s["symbol"] for s in sharks], L.get("blacklist",{}), L.get("last_coins",{}))
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
            side=tr.get("side","LONG")
            if side=="LONG":
                pct_gross=(price_now-entry)/entry*100 if entry else 0
            else:
                pct_gross=(entry-price_now)/entry*100 if entry else 0
            pct_net=pct_gross - FEE_PCT
            net_usd=POS*pct_net/100
            gross_usd=POS*pct_gross/100
            age=now_ts-tr.get("ts",now_ts)
            peak_gross=max(tr.get("peak_gross",0), pct_gross)
            tr["price"]=price_now; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["peak_gross"]=peak_gross; tr["peak"]=peak_gross-FEE_PCT; tr["age"]=age; tr["net"]=net_usd; tr["gross"]=gross_usd
            tp=tr.get("tp",0.48); sl=tr.get("sl",0.30)
            should=None
            # FIXED: longer hold, no more 77s flat cut 0.08%
            if pct_gross>=tp:
                should=f"TP {tp}% {side} {tr.get('strategy','')} +${net_usd:+.2f} NET $0.50 GOAL {market['regime']} {market['bias']}"
            elif pct_gross<=-sl:
                should=f"SL -{sl}% {side} {tr.get('strategy','')} CUT FAST {market['regime']}"
            elif peak_gross>=0.38 and pct_gross<peak_gross-0.12 and pct_net>=0.12:
                should=f"TRAIL PEAK {peak_gross:.2f}%->{pct_gross:.2f}% -0.12% JUMP {side}"
            elif age>180 and peak_gross<0.15 and pct_gross<0.18:
                should=f"NO PEAK 0.15% {age}s FLAT CUT {side} {tr.get('strategy','')} - was 77s now 180s"
            elif age>420 and pct_gross<0.20 and peak_gross<0.30:
                should=f"FLAT {pct_gross:.2f}% PEAK {peak_gross:.2f}% {age}s CUT {side}"
            elif age>900:
                should=f"TIME 900s FORCE {side} {tr.get('strategy','')} {pct_gross:.2f}%"
            if should:
                cap+=net_usd; daily+=net_usd; daily_gross+=gross_usd; fees_paid+=FEE_USD; tot+=1
                closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"gross":gross_usd,"fee":FEE_USD,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"sector":get_sector(tr["symbol"]),"strategy":tr.get("strategy","")})
                L["last_coins"][tr["symbol"]]=now_ts+500
                if pct_net<-0.40:
                    L["blacklist"][tr["symbol"]]=now_ts+1800
                used_sectors.discard(get_sector(tr["symbol"]))
                used_strats.discard(tr.get("strat_id",0))
            else:
                final.append(tr)
        except:
            final.append(tr)
    wins=sum(1 for c in closed if c.get("net",0)>0.20)
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
        if qty<0.00001: continue
        tr={"symbol":sh["symbol"],"side":sh["side"],"entry":price,"price":price,"pos":POS,"qty":qty,"ts":now_ts,"peak_gross":0,"peak":0,"pct_gross":0,"pct":0,"net":0,"gross":0,"age":0,"h1":sh["h1"],"score":sh["score"],"sector":sh["sector"],"strategy":sh["strategy"],"strat_id":sh["strat_id"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"]}
        final.append(tr)
        open_syms.append(sh["symbol"])
        used_sectors.add(sh["sector"])
        used_strats.add(sh["strat_id"])
    state["open"]=final; state["closed"]=closed[:200]; state["cap"]=cap; state["daily"]=daily; state["daily_gross"]=daily_gross; state["fees_paid"]=fees_paid; state["wins"]=wins; state["loss"]=loss; state["total"]=tot; state["scan"]=scan; state["market"]=market
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan,"open":len(final),"cap":cap,"daily":daily,"sharks":len(sharks),"total":tot,"wins":wins,"loss":loss,"market":market["regime"]+" "+market["bias"]+" BTC $"+str(int(market["btc_price"]))+" ADX "+str(int(market["adx"])),"top":sharks[0]["symbol"]+" "+sharks[0]["side"]+" "+sharks[0]["strategy"] if sharks else "none fallback","v":"v796 FIXED SMART"}

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
    market=state.get("market",{"regime":"RANGING","bias":"BOTH","btc_price":83886,"adx":23,"reason":"no market"})
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
    html+=".side{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:900;margin-left:6px} .side-LONG{background:#00ff88;color:#000} .side-SHORT{background:#ff4444;color:#fff}"
    html+=".s-L1_CHAIN{background:#00d4ff;color:#000} .s-DEPIN_WIFI{background:#ffcc00;color:#000} .s-AI{background:#ff00ff;color:#fff} .s-DEFI{background:#00ff88;color:#000} .s-MEME{background:#ff8800;color:#000} .s-RWA_GAMING{background:#8800ff;color:#fff} .s-OTHER_BEST{background:#555;color:#fff}"
    html+="</style></head><body>"
    bias_color="#00ff88" if market.get("bias")=="LONG" else "#ff4444" if market.get("bias")=="SHORT" else "#ffcc00"
    html+=f"<div class='h'><span class='live'></span> VENUS v796 FIXED SMART LONG SHORT $0.50 NET - SCAN #{scan} - 3 MAX $100 EACH - MARKET {market.get('regime','?')} <span style='background:{bias_color};padding:2px 6px;border-radius:4px'>{market.get('bias','?')} BIAS</span> BTC ${market.get('btc_price',0):.0f} ADX {market.get('adx',0):.0f} - <span id='clock'>LIVE</span></div>"
    html+="<div class='g'>"
    html+=f"<div class='c'><div style='font-size:10px;color:#888'>CAP $300 REAL FIXED SMART</div><div style='font-size:22px;color:#ffcc00;font-weight:900'>${cap:.2f}</div><div style='font-size:10px'>WITH OPEN {cap+unreal:.2f} UNREAL {unreal:+.2f} | {market.get('regime','?')}</div></div>"
    html+=f"<div class='c'><div style='font-size:10px;color:#888'>TODAY NET FIXED {market.get('bias','?')} x $0.50</div><div style='font-size:22px;color:{'#f44' if daily<0 else '#0f8'};font-weight:900'>${daily:+.2f} NET</div><div style='font-size:10px'>GROSS ${daily_gross:+.2f} - FEES ${fees_paid:.2f} | W:{wins} L:{loss} {winrate}% | FIXED</div></div>"
    html+=f"<div class='c'><div style='font-size:10px;color:#888'>MARKET REGIME FIXED</div><div style='font-size:9px;color:#0f8;font-weight:900'>{market.get('regime','?')} {market.get('bias','?')} BTC ${market.get('btc_price',0):.0f} ADX {market.get('adx',0):.0f} LIVE {scan}</div><div style='font-size:8px;color:#888'>{market.get('reason','')[:70]}</div><div style='font-size:10px'>Next <span id='countdown'>10s</span> TICK <span id='tickcount'>1s</span> - FIXED</div></div>"
    html+="</div>"
    html+="<div id='sharkbox'><div class='b bd'>Scanning FIXED SMART...</div></div>"
    html+="<div id='openbox'></div><div id='closedbox'></div>"
    import json as jsjson
    open_json=jsjson.dumps([{"symbol":tr["symbol"],"side":tr.get("side","LONG"),"entry":tr["entry"],"ts":tr.get("ts", int(time.time())),"peak_gross":tr.get("peak_gross",0)} for tr in open_tr])
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
      const entry = tr.entry; 
      let pct_gross = 0;
      if(tr.side=='LONG'){{ pct_gross = (now-entry)/entry*100; }} else {{ pct_gross = (entry-now)/entry*100; }}
      const pct_net = pct_gross - 0.20; const net_usd = 100*pct_net/100;
      if(!priceHistory[tr.symbol]) priceHistory[tr.symbol]=[]; priceHistory[tr.symbol].push(pct_gross); if(priceHistory[tr.symbol].length>60) priceHistory[tr.symbol].shift();
      if(pct_gross > tr.peak_gross) tr.peak_gross = pct_gross;
      const el = document.querySelector(`[data-symbol="${{tr.symbol}}"]`);
      if(el){{
        const grossEl = el.querySelector('.gross-val'); const netEl = el.querySelector('.net-val'); const priceEl = el.querySelector('.price-now'); const peakEl = el.querySelector('.peak-val'); const tickEl = el.querySelector('.tick-graph');
        if(grossEl){{ grossEl.textContent = pct_gross.toFixed(3)+'% GROSS ('+tr.side+')'; grossEl.style.color = pct_gross>=0?'#0f8':'#f44'; }}
        if(netEl){{ netEl.textContent = pct_net.toFixed(3)+'% NET $'+net_usd.toFixed(3)+' NET '+tr.side; netEl.style.color = pct_net>=0?'#0f8':'#f44'; }}
        if(priceEl) priceEl.textContent = '$'+now.toFixed(6);
        if(peakEl) peakEl.textContent = tr.peak_gross.toFixed(2)+'% PEAK';
        if(tickEl && priceHistory[tr.symbol].length>2){{
          const canvas = tickEl; const ctx = canvas.getContext('2d'); const w = canvas.width; const h = canvas.height; ctx.clearRect(0,0,w,h);
          const arr = priceHistory[tr.symbol]; const min = Math.min(...arr); const max = Math.max(...arr); const range = (max-min) || 0.01;
          ctx.strokeStyle = pct_net>=0?'#0f8':'#f44'; ctx.lineWidth=2; ctx.beginPath();
          arr.forEach((v,i)=>{{ const x = i/(arr.length-1)*w; const y = h - ((v-min)/range)*h; if(i==0) ctx.moveTo(x,y); else ctx.lineTo(x,y); }});
          ctx.stroke();
          const tpY = h - ((0.48-min)/range)*h; ctx.strokeStyle='#ffcc00'; ctx.setLineDash([3,3]); ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.setLineDash([]);
        }}
        if(pct_gross >= 0.45 || pct_gross <= -0.32 || (tr.peak_gross >= 0.35 && pct_gross < tr.peak_gross - 0.12)){{ shouldCron = true; }}
      }}
    }});
    if(shouldCron){{ fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(()=>{{ fetch('/?key='+ADMIN_KEY).then(r=>r.text()).then(html=>{{ const parser=new DOMParser(); const doc=parser.parseFromString(html,'text/html'); const openEl=doc.getElementById('openbox-inner'); const closedEl=doc.getElementById('closedbox-inner'); const sharkEl=doc.getElementById('sharkbox-inner'); if(openEl) document.getElementById('openbox').innerHTML = openEl.innerHTML; if(closedEl) document.getElementById('closedbox').innerHTML = closedEl.innerHTML; if(sharkEl) document.getElementById('sharkbox').innerHTML = sharkEl.innerHTML; const newOpen = []; doc.querySelectorAll('[data-symbol]').forEach(div=>{{ const sym = div.getAttribute('data-symbol'); const side = div.getAttribute('data-side')||'LONG'; const entry = parseFloat(div.getAttribute('data-entry')); const ts = parseInt(div.getAttribute('data-ts')); const peak = parseFloat(div.getAttribute('data-peak')||0); newOpen.push({{symbol:sym, side:side, entry:entry, ts:ts, peak_gross:peak}}); }}); openTrades = newOpen; Object.keys(priceHistory).forEach(k=>{{ if(!newOpen.find(t=>t.symbol==k)) delete priceHistory[k]; }}); newOpen.forEach(t=>{{ if(!priceHistory[t.symbol]) priceHistory[t.symbol]=[]; }}); }}); }}); }}
  }}catch(e){{}}
}}
function tickAge(){{ const now = Math.floor(Date.now()/1000); document.querySelectorAll('[data-ts]').forEach(el=>{{ const ts = parseInt(el.getAttribute('data-ts')); const age = now - ts; const ageEl = el.querySelector('.age-val'); if(ageEl) ageEl.textContent = age+'s'; }}); }}
setInterval(fetchPrices, 1000); setInterval(tickAge, 1000); fetchPrices(); tickAge();
let count=10; setInterval(()=>{{ count--; const el=document.getElementById('countdown'); if(el) el.textContent = count+'s'; const clk=document.getElementById('clock'); if(clk) clk.textContent = new Date().toLocaleTimeString(); if(count<=0){{ count=10; fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(r=>r.json()).then(data=>{{ fetch('/?key='+ADMIN_KEY).then(r=>r.text()).then(html=>{{ const parser=new DOMParser(); const doc=parser.parseFromString(html,'text/html'); const openEl=doc.getElementById('openbox-inner'); const closedEl=doc.getElementById('closedbox-inner'); const sharkEl=doc.getElementById('sharkbox-inner'); if(openEl) document.getElementById('openbox').innerHTML = openEl.innerHTML; if(closedEl) document.getElementById('closedbox').innerHTML = closedEl.innerHTML; if(sharkEl) document.getElementById('sharkbox').innerHTML = sharkEl.innerHTML; const newOpen = []; doc.querySelectorAll('[data-symbol]').forEach(div=>{{ const sym = div.getAttribute('data-symbol'); const side = div.getAttribute('data-side')||'LONG'; const entry = parseFloat(div.getAttribute('data-entry')); const ts = parseInt(div.getAttribute('data-ts')); const peak = parseFloat(div.getAttribute('data-peak')||0); newOpen.push({{symbol:sym, side:side, entry:entry, ts:ts, peak_gross:peak}}); }}); openTrades = newOpen; newOpen.forEach(t=>{{ if(!priceHistory[t.symbol]) priceHistory[t.symbol]=[]; }}); }}); }}); }} }},1000);
</script>
"""
    html+="<div style='display:none'><div id='sharkbox-inner'>"
    html+=f"<div class='b bg'>FIXED SMART REGIME - MARKET {market.get('regime','?')} BIAS {market.get('bias','?')} - BTC ${market.get('btc_price',0):.0f} ADX {market.get('adx',0):.0f} - {market.get('reason','')[:90]} - FIXED BTC $0 BUG</div>"
    if sharks:
        for s in sharks[:8]:
            html+=f"<div class='it' style='border-color:#00ff88'><b style='color:#00ff88'>#{sharks.index(s)+1} {s['symbol']} <span class='sec s-{s['sector']}'>{s['sector']}</span> H1 +{s['h1']:.1f}% VOL ${s['vol']}</b><br><span style='color:#0f8'>REAL USDT - SCORE {s['score']:.0f} - FIXED {market.get('regime','?')} {market.get('bias','?')} BTC ${market.get('btc_price',0):.0f}</span></div>"
    else:
        html+=f"<div class='b by'>FIXED SMART {market.get('regime','?')} {market.get('bias','?')} - BTC ${market.get('btc_price',0):.0f} ADX {market.get('adx',0):.0f} - {market.get('reason','')[:80]} - WILL FILL 3 WITH BTC ETH ETC LONG/SHORT - FIXED BTC $0 BUG - NO MORE 77s FLAT CUT</div>"
    html+="</div>"
    html+="<div id='openbox-inner'>"
    html+=f"<div class='b bb'>OPEN {len(open_tr)}/{MAXP} MAX FIXED SMART LONG SHORT $100 EACH - MARKET {market.get('regime','?')} {market.get('bias','?')} BTC ${market.get('btc_price',0):.0f} ADX {market.get('adx',0):.0f} - SECTORS {','.join(list(used_sectors)) if used_sectors else 'FIXED FALLBACK BTC ETH ETC'} - <span class='live'></span> LIVE TICK GRAPH 1s</div>"
    if len(open_tr)==0:
        html+=f"<div class='it' style='text-align:center;color:#0f8;border-color:#0f8'>FIXED SMART ACTIVE - SCAN #{scan} - MARKET REGIME THINKING FIXED:<br>{market.get('reason','')}<br>BIAS: {market.get('bias','?')} - REGIME: {market.get('regime','?')} - ADX {market.get('adx',0):.0f} BTC ${market.get('btc_price',0):.0f}<br>3x$100 DIVERSIFIED FIXED:<br>FIXED: BTC $0 BUG -> NOW BTC ${market.get('btc_price',0):.0f} FROM TICKER<br>FIXED: 77s FLAT CUT 0.08% -> NOW 180s FLAT CUT 0.15% LONGER HOLD<br>FIXED: TP 0.70% too high -> NOW TP 0.45-0.52% LOWER FOR 10%->60% WIN<br>LONG: TREND_DIP BOUNCE (BULL) / SHORT TOP REJECT (BEAR)<br>LONG: BOUNCE RSI<42 BB LOW / SHORT RSI>58 BB HIGH (RANGING BOTH)<br>LONG: BREAKOUT / SHORT BREAKDOWN ACCORDING TO MARKET<br>FALLBACK: BTC ETH ETC ALWAYS BOTH LONG/SHORT - BAN FIAT BIDR IDRT - SEC TICK LIVE 1s - FIXED</div>"
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        pct_gross=tr.get("pct_gross",0); pct_net=tr.get("pct",0); net_usd=tr.get("net",0); entry=tr.get("entry",0); ts=tr.get("ts", int(time.time())); peak=tr.get("peak_gross",0); sector=tr.get("sector", get_sector(tr["symbol"])); strat=tr.get("strategy",""); side=tr.get("side","LONG")
        html+=f"<div class='it' style='border-color:{col}' data-symbol='{tr['symbol']}' data-side='{side}' data-entry='{entry}' data-ts='{ts}' data-peak='{peak}'><b style='color:{col}'>{tr['symbol']} <span class='side side-{side}'>{side}</span> <span class='sec s-{sector}'>{sector}</span> <span class='strat st-{strat}'>{strat}</span> AGE <span class='age-val'>{tr.get('age',0)}s</span> PEAK <span class='peak-val'>{peak:.2f}% PEAK</span></b><br>ENTRY ${entry:.6f} ({side}) -> NOW <span class='price-now' style='color:#ffcc00'>${tr.get('price',0):.6f}</span> $100 POS<br><span style='font-size:13px;font-weight:900' class='gross-val'>{pct_gross:.3f}% GROSS ({side})</span> <span style='font-size:13px;font-weight:900' class='net-val'>{pct_net:.3f}% NET ${net_usd:+.3f} NET {side}</span> <span class='live'></span> TICK GRAPH<br><canvas class='spark tick-graph' width='300' height='32'></canvas><br><span style='font-size:10px;color:#888'>{tr.get('reason','')} | {sector} | TP {tr.get('tp',0.48)}% SL {tr.get('sl',0.30)}% | $0.50 NET GOAL FIXED {market.get('regime','?')} {market.get('bias','?')}</span></div>"
    html+="</div>"
    html+="<div id='closedbox-inner'>"
    html+=f"<div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} T:{tot} {winrate}% - CAP ${cap:.2f} DAILY NET ${daily:+.2f} (GROSS ${daily_gross:+.2f} - FEES ${fees_paid:.2f}) - FIXED SMART {market.get('regime','?')} {market.get('bias','?')} $0.50x3 = $1.50 TARGET - FIXED BTC $0 BUG</div>"
    for cl in closed[:15]:
        net=cl.get("net",0); gross=cl.get("gross",0); fee=cl.get("fee",FEE_USD); pct_gross=cl.get("pct_gross",0); pct_net=cl.get("pct_net",0); c="#0f8" if net>=0.20 else "#f44" if net<0 else "#ffcc00"; sec=cl.get("sector", get_sector(cl.get("symbol",""))); strat=cl.get("strategy",""); side=cl.get("side","LONG")
        html+=f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')} <span class='side side-{side}'>{side}</span> <span class='sec s-{sec}'>{sec}</span> <span class='strat st-{strat}'>{strat}</span></b> ${net:+.2f} NET (${gross:+.2f} GROSS - ${fee:.2f} FEE) {cl.get('reason','')} {pct_gross:+.2f}% GROSS {pct_net:+.2f}% NET AGE {cl.get('age',0)}s</div>"
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
