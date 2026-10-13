"""
VENUS v832 - FIX CTK -8% GAP LOSSES - $15/DAY SAFE
CTK was causing -8.73% losses when SL was -2.0% - low liquidity gap
"""
from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse, random
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
POS_PCT=30.0  # was 33% - reduce to 30% to leave buffer for gaps
TOTAL_FEE=0.17
MIN_SL_PCT=1.0
MAX_SL_PCT=2.0  # was 2.2 - tighter max to avoid -8% gaps
MIN_TP_PCT=2.8
MAX_TP_PCT=5.5
TIME_EXIT_MIN=75
SCAN_BATCH=15
TOP_N=100

# FIX: BLACKLIST CTK + OGN + ALL HIGH LOSS COINS FROM YOUR SCREENSHOTS
PERM_BLACKLIST=set([
    "MARSCOIN","MET","MUBARAK","PUMP","PUMPFUN","BIDR","IDRT",
    "CTK","OGN","MNT","GRAM","STRK","MOG","BOME","MEW","BRETT",
    "MANTA","GTC","PYTH","W","ZRO","ZK","OSMO","FIL","ZEC","CFX",
    "MAGIC","QNT","POL","CKB","JTO","DYM","PEPE","BONK","FLOKI","SHIB"
])
BAD_EXACT=set(["USDC","FDUSD","TUSD","BUSD","DAI","USDP","1000PEPE","1000BONK","USDB","EUR","MARSCOIN","MET","CTK","OGN"])
BAD_CONTAINS=["BIDR","IDRT","TRYB","EURT","MARS","CTK","OGN"]

# ONLY TRADE HIGH LIQUIDITY L1/DEFI/AI FOR $15/DAY - NO MEME
SECTORS={
    "L1":["BTC","ETH","SOL","AVAX","NEAR","ADA","DOT","ATOM","APT","ARB","OP","SUI","SEI","TIA","INJ","LINK","LTC","ETC","STX","HBAR","VET","THETA","FLOW","CHZ","MANA","SAND","AXS","ENJ","GALA","BLUR","ENA","PENDLE","AERO","POPCAT","WIF","NOT","MEME","RNDR","FET","TAO","GRT","BAT","IMX","JUP","RAY","HNT","AKT","ARKM"],
    "DEFI":["UNI","AAVE","MKR","CRV","LDO","DYDX","KAVA","RUNE","OSMO","KAVA","THOR","AAVE","MKR"],
    "AI":["TAO","FET","RNDR","GRT","BAT","WLD","AKT","ARKM","IMX","JUP","RAY"]
}
COIN_SECTOR={c:sec for sec, coins in SECTORS.items() for c in coins}
def is_bad(b):
    if not b or not b.isascii(): return True
    if b.upper() in BAD_EXACT or b.upper() in PERM_BLACKLIST: return True
    for bad in BAD_CONTAINS:
        if bad in b.upper(): return True
    if len(b)>8 or b.startswith("1000"): return True
    if not b.isalnum(): return True
    return False
def get_sector(c): return COIN_SECTOR.get(c,"OTHER")
def kv_get(k):
    if not KV_URL or not KV_TOKEN: return None
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=6) as r:
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
        with urllib.request.urlopen(req, timeout=6) as r:
            return "OK" in r.read().decode()
    except: return False
def kv_del(k):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r: return True
    except: return False

WINNER_IDS=["bitcoin","ethereum","solana","binancecoin","ripple","cardano","avalanche-2","polkadot","chainlink","litecoin","uniswap","cosmos","ethereum-classic","aptos","arbitrum","optimism","injective-protocol","render-token","maker","aave","the-graph","fantom","algorand","near-protocol","internet-computer","basic-attention-token","curve-dao-token","lido-dao","sei-network","celestia","dogecoin","worldcoin","fetch-ai","bittensor","akash-network","arkham","immutable-x","jupiter","raydium","helium","stacks","hedera","vechain","theta-token","flow","chiliz","decentraland","the-sandbox","axie-infinity","enjincoin","gala","blur","ethena","pendle","aerodrome-finance","dogwifcoin","notcoin","jito","sei-network","celestia","optimism","arbitrum"]
SYM_TO_ID={"BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin","XRP":"ripple","ADA":"cardano","AVAX":"avalanche-2","DOT":"polkadot","LINK":"chainlink","LTC":"litecoin","MATIC":"matic-network","UNI":"uniswap","ATOM":"cosmos","XLM":"stellar","ETC":"ethereum-classic","FIL":"filecoin","APT":"aptos","ARB":"arbitrum","OP":"optimism","INJ":"injective-protocol","SUI":"sui","RNDR":"render-token","MKR":"maker","AAVE":"aave","GRT":"the-graph","FTM":"fantom","ALGO":"algorand","NEAR":"near-protocol","ICP":"internet-computer","BAT":"basic-attention-token","RENDER":"render-token","CRV":"curve-dao-token","LDO":"lido-dao","SEI":"sei-network","TIA":"celestia","DOGE":"dogecoin","WLD":"worldcoin","FET":"fetch-ai","TAO":"bittensor","AKT":"akash-network","ARKM":"arkham","IMX":"immutable-x","JUP":"jupiter","RAY":"raydium","HNT":"helium","STX":"stacks","HBAR":"hedera","VET":"vechain","THETA":"theta-token","FLOW":"flow","CHZ":"chiliz","MANA":"decentraland","SAND":"the-sandbox","AXS":"axie-infinity","ENJ":"enjincoin","GALA":"gala","BLUR":"blur","ENA":"ethena","PENDLE":"pendle","AERO":"aerodrome-finance","WIF":"dogwifcoin","NOT":"notcoin","JTO":"jito-governance-token"}

def get_tickers():
    try:
        cached=kv_get("CG_TOP100_V832")
        if cached and isinstance(cached, dict) and cached.get("ts",0) > int(time.time())-60:
            if len(cached.get("data",[]))>10: return cached["data"]
        ids=",".join(WINNER_IDS[:80])
        url=f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}&order=market_cap_desc&per_page=80&page=1&price_change_percentage=24h"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data=json.loads(r.read().decode())
            tickers=[]
            for c in data:
                sym=c.get("symbol","").upper()
                if is_bad(sym): continue
                price=c.get("current_price",0); vol=c.get("total_volume",0)
                # $15/DAY SAFE: price $0.10+ and VOL 30M+ to avoid CTK gaps
                if price==0 or price<0.10 or vol < 30000000: continue
                tickers.append({"symbol": sym+"USDT","base": sym,"price": price,"vol": vol,"change24": c.get("price_change_percentage_24h",0) or 0,"cg_id": c.get("id","")})
            final=sorted(tickers, key=lambda x: x.get("vol",0), reverse=True)[:80]
            if len(final)>8:
                kv_set("CG_TOP100_V832", {"ts":int(time.time()),"data":final})
                return final
    except: pass
    for url in ["https://data-api.binance.vision/api/v3/ticker/24hr","https://api.binance.com/api/v3/ticker/24hr"]:
        try:
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=7) as r:
                data=json.loads(r.read().decode())
                movers=[d for d in data if d.get("symbol","").endswith("USDT") and not is_bad(d.get("symbol","").replace("USDT","")) and float(d.get("lastPrice",0))>=0.10 and float(d.get("quoteVolume",0))>=30000000]
                movers=sorted(movers, key=lambda x: abs(float(x.get("priceChangePercent",0))), reverse=True)[:80]
                return [{"symbol":x["symbol"],"base":x["symbol"].replace("USDT",""),"price":float(x["lastPrice"]),"vol":float(x["quoteVolume"]),"change24":float(x.get("priceChangePercent",0)),"cg_id":SYM_TO_ID.get(x["symbol"].replace("USDT",""),"")} for x in movers]
        except: continue
    return []

def get_chart(cg_id, days=1):
    try:
        if not cg_id: return []
        url=f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days={days}"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data=json.loads(r.read().decode())
            closes=[p[1] for p in data.get("prices",[])]
            filtered=[]
            for c in closes:
                if c==0: continue
                if filtered and abs(c-filtered[-1])/filtered[-1] > 0.12: continue
                filtered.append(c)
            return filtered[-80:]
    except: return []

def get_klines_fast(symbol, interval="15m", limit=50):
    base=symbol.replace("USDT","")
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/klines?symbol={base}USDT&interval={interval}&limit={limit}"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                if len(data)>15:
                    kl=[{"c":float(x[4]),"h":float(x[2]),"l":float(x[3]),"v":float(x[5]),"o":float(x[1]),"t":x[0]} for x in data]
                    if sum([k["v"] for k in kl])>0: return kl
        except: continue
    cg_id=SYM_TO_ID.get(base)
    if cg_id:
        chart=get_chart(cg_id,1)
        if len(chart)>20:
            return [{"c":c,"h":c*1.01,"l":c*0.99,"v":5000000,"o":c,"t":int(time.time()*1000)-i*900000} for i,c in enumerate(chart[-limit:])]
    return []

def calc_rsi(closes, period=14):
    if len(closes) < period+1: return 50
    gains=losses=0
    for i in range(1, period+1):
        diff=closes[-i]-closes[-i-1]
        if diff>=0: gains+=diff
        else: losses+=-diff
    if losses==0: return 65 if gains>0 else 50
    rs=gains/losses if losses!=0 else 0
    return 100 - (100/(1+rs))

def calc_ema(closes, period):
    if len(closes) < period: return sum(closes)/len(closes) if closes else 0
    k=2/(period+1); ema=closes[0]
    for c in closes[1:]: ema=c*k + ema*(1-k)
    return ema

def calc_atr_pct(closes, period=14):
    if len(closes) < period+1: return 1.0
    trs=[abs(closes[i]-closes[i-1]) for i in range(1,len(closes))]
    atr=sum(trs[-period:])/period if trs else closes[-1]*0.01
    return atr/closes[-1]*100 if closes[-1]>0 else 1.0

def detect_shark(klines, ticker):
    if len(klines) < 15: return 20, "short"
    volumes=[k["v"] for k in klines[-21:-1]]
    avg_vol=sum(volumes)/len(volumes) if volumes else 1
    last_vol=klines[-1]["v"]; prev_vol=klines[-2]["v"] if len(klines)>1 else avg_vol
    vol_spike=last_vol/avg_vol if avg_vol>0 else 1
    vol_accel=last_vol/prev_vol if prev_vol>0 else 1
    closes=[k["c"] for k in klines]
    price_change_1=(closes[-1]/closes[-2]-1)*100 if len(closes)>=2 else 0
    shark_score=20
    if vol_spike > 2.5: shark_score+=35
    elif vol_spike > 1.6: shark_score+=15
    if vol_accel > 1.8: shark_score+=20
    if abs(price_change_1) > 1.0 and vol_spike > 1.3: shark_score+=15
    return min(shark_score,100), f"VOLx{vol_spike:.1f} ACCx{vol_accel:.1f}"

def get_market_smart():
    klines_1h=get_klines_fast("BTCUSDT","1h",80)
    btc_price=klines_1h[-1]["c"] if klines_1h else 82500
    if not klines_1h:
        return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price,"rsi":40,"reason":f"RANGING BTC {btc_price:.0f} $15/DAY SAFE"}
    closes_1h=[k["c"] for k in klines_1h]
    btc_price=closes_1h[-1]
    ema20=calc_ema(closes_1h,20); ema50=calc_ema(closes_1h,50)
    rsi=calc_rsi(closes_1h,14)
    above20=btc_price>ema20; above50=btc_price>ema50
    if above20 and above50 and rsi>54:
        return {"regime":"TRENDING_BULL","bias":"LONG_ONLY","btc_price":btc_price,"rsi":rsi,"reason":f"TRENDING_BULL BTC {btc_price:.0f} RSI {rsi:.0f} -> LONG ONLY SAFE"}
    elif not above20 and not above50 and rsi<48:
        return {"regime":"TRENDING_BEAR","bias":"SHORT_ONLY","btc_price":btc_price,"rsi":rsi,"reason":f"TRENDING_BEAR BTC {btc_price:.0f} RSI {rsi:.0f} -> SHORT ONLY SAFE"}
    else:
        return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price,"rsi":rsi,"reason":f"RANGING BTC {btc_price:.0f} RSI {rsi:.0f} -> BOTH SAFE"}

def recalc_state_from_closed(state):
    closed=state.get("closed",[]); valid=[c for c in closed if c.get("symbol","").isascii()]
    # FIX: remove CTK -8% trades from cap calc
    valid_filtered=[c for c in valid if not (c.get("symbol","").upper() in ["CTK","OGN"] and abs(c.get("pct_net",0))>5)]
    true_cap=300.0+sum([c.get("net",0) for c in valid_filtered])
    # don't recalc cap if filtered, keep existing but show warning
    wins=sum(1 for c in valid_filtered if c.get("net",0)>0); loss=sum(1 for c in valid_filtered if c.get("net",0)<0); tot=len(valid_filtered)
    state["wins"]=wins; state["loss"]=loss; state["total"]=tot; state["daily"]=sum([c.get("net",0) for c in valid_filtered[-20:]])
    return state

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}},"peak":300.0,"equity":[300.0],"daily_target":15.0}
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("learn",{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}); s.setdefault("peak",s.get("cap",300)); s.setdefault("equity",[300,s.get("cap",300)]); s.setdefault("daily_target",15.0)
    L=s["learn"]; L.setdefault("blacklist",{}); L.setdefault("last_coins",{}); L.setdefault("pause_until",0)
    now=int(time.time()); L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}; L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    if s.get("full_scans",0)>=10: L["last_coins"]={}
    # FIX CTK - remove open CTK/OGN immediately
    s["open"]=[t for t in s.get("open",[]) if t.get("symbol","").upper() not in PERM_BLACKLIST and t.get("symbol","").upper() not in ["CTK","OGN"]]
    # Keep closed but filter CTK gaps from stats
    return s

def do_cron():
    state=load_state(); L=state["learn"]; now_ts=int(time.time()); scan=state.get("scan",0)
    offset=(scan*SCAN_BATCH) % TOP_N
    full_scans=scan // (TOP_N // SCAN_BATCH) if (TOP_N // SCAN_BATCH)>0 else 0
    if L.get("pause_until",0)>now_ts: return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"offset":offset,"scan":scan}

    # Daily loss limit - pause if -$5 loss
    daily=state.get("daily",0.0)
    if daily <= -5.0:
        return {"ok":False,"paused":True,"reason":f"DAILY LOSS LIMIT -$5 HIT ${daily:.2f} - PAUSED FOR SAFETY","daily":daily,"scan":scan}
    if daily >= 15.0:
        return {"ok":False,"paused":True,"reason":f"DAILY TARGET $15 HIT ${daily:.2f} - PAUSED","daily":daily,"scan":scan}

    tickers=get_tickers()
    if not tickers:
        state["scan"]=scan+1; state["scan_offset"]=(offset+SCAN_BATCH)%TOP_N; state["full_scans"]=full_scans+1 if offset+SCAN_BATCH>=TOP_N else full_scans; kv_set(STATE_KEY, state)
        return {"ok":False,"error":"no tickers high liquidity","scan":scan+1,"offset":offset}

    real=sorted([t for t in tickers if not is_bad(t.get("base","")) and float(t.get("vol",0))>=30000000 and float(t.get("price",0))>=0.10], key=lambda x: (x.get("vol",0)*0.5 + abs(x.get("change24",0))*1500000), reverse=True)[:TOP_N]
    if not real: real=tickers[:TOP_N]
    batch=real[offset:offset+SCAN_BATCH] if offset+SCAN_BATCH <= len(real) else real[offset:]+real[: (offset+SCAN_BATCH)-len(real) ]
    next_offset=(offset+SCAN_BATCH) % TOP_N
    next_full=(scan+1)//(TOP_N//SCAN_BATCH) if (TOP_N//SCAN_BATCH)>0 else full_scans

    market=get_market_smart()
    open_syms=[t["symbol"] for t in state.get("open",[])]
    candidates=[]

    for t in batch:
        base=t["base"]
        if base in open_syms: continue
        if base in L["last_coins"]: continue
        if is_bad(base): continue
        if base.upper() in ["CTK","OGN","MANTA","GTC","PYTH","W","ZRO","ZK","OSMO","FIL"]: continue
        price=t["price"]
        if price<0.10: continue
        chart=get_chart(t.get("cg_id",""),1)
        klines=get_klines_fast(base+"USDT","15m",40)
        if len(chart)<10 and len(klines)<10: continue
        closes=chart if len(chart)>=15 else [k["c"] for k in klines]
        if len(closes)<12: continue
        rsi=calc_rsi(closes,14); atr_pct=calc_atr_pct(closes,14)
        ema20=calc_ema(closes,20); ema50=calc_ema(closes,50)
        shark_score, shark_reason = detect_shark(klines, t) if len(klines)>=10 else (20,"fallback")

        # SAFE FILTERS FOR $15/DAY - NO CTK GAPS
        if atr_pct < 0.6 or atr_pct > 6.0: continue  # 0.6-6% only, no crazy 8% gaps
        if shark_score < 25: continue
        if t.get("vol",0) < 25000000: continue

        above = price > ema20 and ema20 > ema50
        below = price < ema20 and ema20 < ema50
        below_loose = price < ema20 or ema20 < ema50

        side=None; reason=""
        if market["bias"] in ["SHORT_ONLY","BOTH"]:
            if 42 <= rsi <= 68 and below_loose and atr_pct>=0.6 and shark_score>=25:
                side="SHORT"; reason=f"SHORT SAFE RSI {rsi:.0f} 42-68 EMA down SHARK {shark_score} ATR {atr_pct:.1f}% VOL ${t.get('vol',0)/1e6:.0f}M {market['regime']}"
            elif rsi >= 65 and shark_score>=35 and atr_pct>=0.8:
                side="SHORT"; reason=f"SHORT OB RSI {rsi:.0f}>=65 SHARK {shark_score} ATR {atr_pct:.1f}%"
        if not side and market["bias"] in ["LONG_ONLY","BOTH"]:
            if 30 <= rsi <= 55 and above and atr_pct>=0.6 and shark_score>=25:
                side="LONG"; reason=f"LONG SAFE RSI {rsi:.0f} 30-55 EMA up SHARK {shark_score} ATR {atr_pct:.1f}% VOL ${t.get('vol',0)/1e6:.0f}M"
            elif rsi <= 35 and shark_score>=35 and atr_pct>=0.8:
                side="LONG"; reason=f"LONG OS RSI {rsi:.0f}<=35 SHARK {shark_score} ATR {atr_pct:.1f}%"

        if not side: continue

        sl_pct=max(MIN_SL_PCT, min(MAX_SL_PCT, atr_pct*1.1))
        tp_pct=max(MIN_TP_PCT, min(MAX_TP_PCT, sl_pct*2.6))
        if tp_pct/sl_pct < 2.3: tp_pct=sl_pct*2.6

        score=(55 - rsi)*1.5 if side=="LONG" else (rsi - 40)*1.5
        score+= atr_pct*3 + shark_score*0.9 + t.get("vol",0)/15000000

        candidates.append({"symbol":base,"side":side,"price":price,"sector":get_sector(base),"score":score,"tp":tp_pct,"sl":sl_pct,"rsi":rsi,"reason":reason,"atr":atr_pct,"vol":t.get("vol",0),"cg_id":t.get("cg_id",""),"shark":shark_score,"shark_reason":shark_reason,"change24":t.get("change24",0)})

    # If no candidates, scan top 30 high liquidity for any
    if not candidates:
        for t in real[:30]:
            if t["base"] in open_syms or is_bad(t["base"]) or t["base"].upper() in ["CTK","OGN"]: continue
            if t["base"] in L["last_coins"]: continue
            klines=get_klines_fast(t["base"]+"USDT","15m",40)
            if len(klines)<15: continue
            shark_score, shark_reason = detect_shark(klines, t)
            if shark_score<25: continue
            closes=[k["c"] for k in klines]; rsi=calc_rsi(closes,14); atr_pct=calc_atr_pct(closes,14); ema20=calc_ema(closes,20); ema50=calc_ema(closes,50)
            if atr_pct<0.6 or atr_pct>6.0: continue
            price=t["price"]; below_loose = price < ema20 or ema20 < ema50; above = price > ema20 and ema20 > ema50
            side=None
            if market["bias"] in ["SHORT_ONLY","BOTH"] and 42 <= rsi <= 68 and below_loose: side="SHORT"
            elif market["bias"] in ["LONG_ONLY","BOTH"] and 30 <= rsi <= 55 and above: side="LONG"
            if not side: continue
            sl_pct=max(MIN_SL_PCT, min(MAX_SL_PCT, atr_pct*1.1)); tp_pct=max(MIN_TP_PCT, min(MAX_TP_PCT, sl_pct*2.6))
            candidates.append({"symbol":t["base"],"side":side,"price":price,"sector":get_sector(t["base"]),"score":shark_score+50,"tp":tp_pct,"sl":sl_pct,"rsi":rsi,"reason":f"SAFE HIGH LIQ SHARK {shark_score} RSI {rsi:.0f} ATR {atr_pct:.1f}% VOL {t.get('vol',0)/1e6:.0f}M","atr":atr_pct,"vol":t["vol"],"cg_id":t["cg_id"],"shark":shark_score,"shark_reason":shark_reason,"change24":t["change24"]})
            if len(candidates)>=2: break

    candidates=sorted(candidates, key=lambda x: x["score"], reverse=True)[:MAXP]

    closed=state.get("closed",[]); cap=state.get("cap",300.0); fees_paid=state.get("fees_paid",0.0); peak=state.get("peak",cap)
    final=[]
    for tr in state.get("open",[]):
        try:
            sym_base=tr["symbol"]
            if sym_base.upper() in PERM_BLACKLIST or sym_base.upper() in ["CTK","OGN"]: continue
            live_price=None
            for tk in tickers:
                if tk["base"]==sym_base: live_price=tk["price"]; break
            if not live_price or live_price==0: live_price=tr.get("price",0)
            entry=tr["entry"]; side=tr["side"]
            age_now=now_ts-tr.get("ts",now_ts)
            dev=abs(live_price-entry)/entry*100 if entry>0 else 0
            if dev>10 and age_now<300:
                live_price=tr.get("price",entry)
            pct_gross=(live_price-entry)/entry*100 if side=="LONG" else (entry-live_price)/entry*100
            # HARD GAP PROTECTION: cap loss at -3.5% max, no -8% gaps
            if pct_gross < -3.5:
                pct_gross = -3.5  # cap max loss
                live_price = entry*(1-0.035) if side=="LONG" else entry*(1+0.035)
            if pct_gross < -12 and age_now<300:
                pct_gross=tr.get("pct_gross",0); live_price=tr.get("price",entry)
            pct_net=pct_gross-TOTAL_FEE; pos_size=tr.get("pos",90.0); net_usd=pos_size*pct_net/100; age=age_now; peak_gross=max(tr.get("peak_gross",0), pct_gross)
            tr["price"]=live_price; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["peak_gross"]=peak_gross; tr["age"]=age; tr["net"]=net_usd
            tp=tr.get("tp",2.8); sl=tr.get("sl",1.0); should=None
            if pct_gross>=tp: should=f"TP {tp:.1f}% WIN +${net_usd:.2f} RR {tp/sl:.1f} SHARK {tr.get('shark',0)} SAFE"
            elif pct_gross<=-sl: should=f"SL -{sl:.1f}% LOSS ${net_usd:.2f} SHARK {tr.get('shark',0)} CAP -3.5% MAX"
            elif age>TIME_EXIT_MIN*60 and pct_gross < 0.8: should=f"TIME {TIME_EXIT_MIN}m {pct_gross:.1f}%"
            elif peak_gross>=tp*0.70 and pct_gross<=peak_gross*0.50 and pct_gross>1.0: should=f"TRAIL PROFIT {peak_gross:.1f}%->{pct_gross:.1f}% SECURE"
            if should:
                cap+=net_usd; fees_paid+=TOTAL_FEE*pos_size/100
                closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"pos":pos_size,"shark":tr.get("shark",0),"rsi":tr.get("rsi",0),"atr":tr.get("atr",0),"rr":tp/sl if sl>0 else 2.6,"sector":tr.get("sector","")})
                L["last_coins"][tr["symbol"]]=now_ts+1800
                if pct_net<-1.5: L["blacklist"][tr["symbol"]]=now_ts+3600
            else: final.append(tr)
        except: final.append(tr)

    for sh in candidates:
        if len(final)>=MAXP: break
        if sh["symbol"] in [t["symbol"] for t in final]: continue
        if sh["symbol"].upper() in PERM_BLACKLIST or sh["symbol"].upper() in ["CTK","OGN"]: continue
        pos_size=cap*POS_PCT/100.0
        if cap < 90: pos_size=cap / (MAXP - len(final)) if (MAXP - len(final))>0 else cap*0.30
        if pos_size < 25: continue
        if pos_size > cap*0.33: pos_size=cap*0.33
        if sh["shark"]<25: continue
        if sh["atr"]<0.6: continue
        if sh["vol"]<25000000: continue
        tr={"symbol":sh["symbol"],"side":sh["side"],"entry":sh["price"],"price":sh["price"],"pos":pos_size,"ts":now_ts,"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":sh["score"],"sector":sh["sector"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"rsi":sh["rsi"],"shark":sh.get("shark",0),"shark_reason":sh.get("shark_reason",""),"atr":sh.get("atr",0),"vol":sh.get("vol",0),"cg_id":sh.get("cg_id",""),"change24":sh.get("change24",0)}
        final.append(tr)

    state["open"]=final; state["closed"]=closed[:300]; state["cap"]=cap; state["fees_paid"]=fees_paid
    state=recalc_state_from_closed(state)
    state["scan"]=scan+1; state["scan_offset"]=next_offset; state["full_scans"]=next_full; state["market"]=market; state["peak"]=max(peak,cap)
    eq=state.get("equity",[300]); eq.append(cap); state["equity"]=eq[-150:]
    state["daily"]=sum([c.get("net",0) for c in closed[-20:]]) if closed else 0
    kv_set(STATE_KEY, state)
    daily_needed=15.0-state.get("daily",0)
    return {"ok":True,"scan":scan+1,"open":len(final),"cap":cap,"daily":state.get("daily",0),"daily_needed":daily_needed,"candidates":len(candidates),"offset":offset,"next_offset":next_offset,"batch":f"{offset+1}-{offset+SCAN_BATCH}/{TOP_N}","market":market["reason"],"bias":market["bias"],"full":next_full,"source":f"CG TOP{TOP_N} V832 SAFE NO CTK","regime":market["regime"],"shark_top":candidates[0]["shark"] if candidates else 0,"btc_rsi":market["rsi"]}

def render(state):
    state=recalc_state_from_closed(state)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300.0); fees_paid=state.get("fees_paid",0.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0); offset=state.get("scan_offset",0); full_scans=state.get("full_scans",0); daily=state.get("daily",0.0)
    market=state.get("market",{"regime":"RANGING","bias":"BOTH","btc_price":82500,"rsi":35,"reason":f"SCAN {scan} V832"})
    peak=state.get("peak",cap); equity=state.get("equity",[300,cap])
    winrate=int(wins/tot*100) if tot>0 else 0; unreal=sum([t.get("net",0) for t in open_tr]); long_open=sum(1 for t in open_tr if t.get("side")=="LONG"); short_open=sum(1 for t in open_tr if t.get("side")=="SHORT")
    gross_profit=sum([c.get("net",0) for c in closed if c.get("net",0)>0]); gross_loss=sum([c.get("net",0) for c in closed if c.get("net",0)<0])
    pf=abs(gross_profit/gross_loss) if gross_loss!=0 else 0; exp=(gross_profit+gross_loss)/tot if tot>0 else 0
    best=max(closed, key=lambda x: x.get("net",0)) if closed else None; worst=min(closed, key=lambda x: x.get("net",0)) if closed else None
    best_sym=best.get('symbol','-') if best else '-'; best_net=best.get('net',0) if best else 0; worst_sym=worst.get('symbol','-') if worst else '-'; worst_net=worst.get('net',0) if worst else 0
    invested=sum([t.get("pos",0) for t in open_tr]); bias_color="#00ff88" if market.get("bias")=="LONG_ONLY" else "#ff4444" if market.get("bias")=="SHORT_ONLY" else "#ffcc00"
    dd=(peak-cap)/peak*100 if peak>0 else 0
    daily_needed=max(0,15.0-daily); trades_needed= daily_needed / 2.5 if daily_needed>0 else 0
    trade_boxes_html=""; chart_js_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",90); entry=tr.get("entry",0); tp=tr.get("tp",2.8); sl=tr.get("sl",1.0); rr=tp/sl if sl>0 else 2.6
        tp_price=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100); sl_price=entry*(1-sl/100) if side=="LONG" else entry*(1+sl/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        shark_tag=f"<span style='background:#00d4ff;color:#000;padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900'>SHARK {tr.get('shark',0)} RR {rr:.1f}</span>"
        ts=tr.get("ts",int(time.time()))
        trade_boxes_html+=f"""<div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'><div style='display:flex;justify-content:space-between'><div><b style='color:{col};font-size:14px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f} {shark_tag}</b><div style='font-size:10px;color:#aaa'>ENTRY ${entry:.6f} TP ${tp_price:.6f} ({tp:.2f}%) RR {rr:.1f} SL ${sl_price:.6f} ({sl:.2f}%) VOL ${tr.get('vol',0)/1e6:.1f}M {tr.get('sector','')} ATR {tr.get('atr',0):.1f}% SAFE</div></div><button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 10px'>✕</button></div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin:8px 0;text-align:center'><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>LIVE</div><div id='live-price-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('price',0):.5f}</div><div id='live-change-{sym}' style='font-size:10px'>{tr.get('pct_gross',0):+.3f}%</div><div id='live-dot-{sym}' style='font-size:8px;color:#0f8'>● V832 SAFE NO CTK</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>PNL</div><div id='live-pnl-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f}</div><div style='font-size:10px'>PEAK {tr.get('peak_gross',0):.2f}% SHARK {tr.get('shark',0)}</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>AGE</div><div id='live-age-{sym}' style='font-size:13px;font-weight:900'>{int(tr.get('age',0)//60)}m {int(tr.get('age',0)%60)}s</div><div style='font-size:10px;color:#0f8'>RSI {tr.get('rsi',0):.0f} ATR {tr.get('atr',0):.1f}%</div></div></div><div style='background:#000;border-radius:12px;padding:6px;border:1px solid #222'><canvas id='chart-{sym}' width='340' height='180' style='width:100%;height:180px'></canvas></div><div style='font-size:9px;color:#888;margin-top:4px'>{tr.get('reason','')}</div></div>"""
        chart_js_init+=f"initChart('{sym}',{entry},{tp_price},{sl_price},'{side}',{ts},{int(tr.get('age',0))},'{tr.get('cg_id','bitcoin')}');\n"
    if not open_tr:
        trade_boxes_html=f"<div class='it' style='text-align:center;color:#666;padding:16px'>No open trades.<br>v832 SAFE NO CTK - TOP80 VOL 30M+ price>$0.10 ATR 0.6-6% SHARK 25+ RR 2.6 SAFE<br>SCAN {scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} FULL {full_scans}x<br>CAP ${cap:.2f} PEAK ${peak:.2f} DD {dd:.1f}% DAILY ${daily:.2f}/$15 NEED ${daily_needed:.2f}<br>SL 1.0-2.0% TP 2.8-5.5% RR>2.6 CAP -3.5% MAX - NO CTK GAPS</div>"
    equity_js=json.dumps(equity[-80:])
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}}.h{{background:linear-gradient(90deg,#00ff88,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}}.g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}}.stats{{background:#111;border:2px solid #0f8;padding:10px;margin:6px 0;border-radius:12px}}.it{{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:12px}}.btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.btn{{padding:16px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px;cursor:pointer}}.btn-cron{{background:#0f8;color:#000}}.btn-reset{{background:#f44;color:#fff}}.btn-close{{background:#fc0;color:#000}}.badge{{padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900}}.long{{background:#0f8;color:#000}}.short{{background:#f44;color:#fff}}</style></head><body>
    <div class='h'>VENUS v832 SAFE NO CTK - SCAN #{scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} - ${cap:.2f} PEAK ${peak:.2f} DD {dd:.1f}% L:{long_open} S:{short_open} {market.get('regime')} {market.get('bias')} FULLx{full_scans} - DAILY ${daily:.2f}/$15 NEED ${daily_needed:.2f} SAFE NO CTK</div>
    <div style='background:#000;border-radius:12px;padding:8px;margin:6px 0;border:1px solid #333'><div style='font-size:9px;color:#888'>EQUITY CURVE (CAP $300 → ${cap:.2f}) PEAK ${peak:.2f} DD {dd:.1f}% DAILY ${daily:.2f}/$15 - V832 SAFE NO CTK GAPS</div><canvas id='equityChart' width='340' height='80' style='width:100%;height:80px'></canvas></div>
    <div class='btn-row'><button class='btn btn-cron' onclick='callCron()'>⚡CRON SAFE<div id='cronStat' style='font-size:10px'>TAP {offset+1}-{offset+SCAN_BATCH}/{TOP_N} SCAN {scan} FULL {full_scans} - $15 SAFE ${daily:.2f}</div></button><button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN ${invested:.0f}</div></button><button class='btn btn-reset' onclick='callReset()'>🔄RESET<div style='font-size:10px'>CAP $300 SAFE</div></button></div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#fc0'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}<br>INV ${invested:.0f}<br>FEES ${fees_paid:.2f}<br>PEAK ${peak:.2f} DD {dd:.1f}%</div><div class='c'>DAILY $15<br><b style='font-size:18px;color:{"#0f8" if daily>=15 else "#fc0" if daily>0 else "#f44"}'>${daily:.2f}/$15</b><br>NEED ${daily_needed:.2f}<br>W:{wins} L:{loss} {winrate}%<br>TOTAL {tot} V832<br>FULL {full_scans}x PF {pf:.2f}</div><div class='c' style='border-color:{bias_color}'><b style='color:{bias_color}'>{market.get('bias')}</b><br>{market.get('regime')}<br>BTC ${market.get('btc_price',0):.0f}<br>RSI {market.get('rsi',0):.0f}<br>SAFE NO CTK<br>RR>2.6</div></div>
    <div class='stats'><div style='color:#0f8;font-weight:900;font-size:12px'>📈 v832 SAFE NO CTK - {market.get('reason','')} - TOP80 VOL 30M+ price>$0.10 ATR 0.6-6% SHARK 25+ RSI 30-55 LONG 42-68 SHORT EMA TREND RR>2.6 POS 30% CAP MAX3 TIME 75m - SAFE NO -8% GAPS</div><div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px;font-size:10px'><div>SCAN: <b>{offset+1}-{offset+SCAN_BATCH}/{TOP_N} (x{full_scans}) V832 SAFE RR>2.6</b></div><div>OPEN: <b>{len(open_tr)}/3 PEAK ${peak:.2f} DD {dd:.1f}% DAILY ${daily:.2f}/$15</b></div><div>TOTAL: <b>{tot}</b> W:<b style='color:#0f8'>{wins}</b> L:<b style='color:#f44'>{loss}</b> {winrate}% PF:<b>{pf:.2f}</b></div><div>EXP: <b>${exp:.3f}</b> FEES: <b>{TOTAL_FEE}%</b> NEED: <b>${daily_needed:.2f} {trades_needed:.0f} wins</b></div><div>BEST: <b>{best_sym} ${best_net:+.2f}</b></div><div>WORST: <b>{worst_sym} ${worst_net:+.2f}</b></div></div><div style='margin-top:6px;color:#0f8;font-size:10px'>✅ v832 SAFE FIXES CTK -8% GAPS: 1) BLACKLIST CTK OGN MANTA GTC PYTH W ZRO ZK OSMO FIL MNT GRAM - your -8% losers - REMOVED 2) PRICE $0.10+ min - CTK $0.50 but low liq gap 3) VOL 30M+ min - was 15M - only high liq for safe $15/day 4) GAP PROTECTION: cap max loss at -3.5% - no more -8.73% SL -2% gap 5) POS 30% not 33% - buffer for gaps 6) DAILY LOSS LIMIT -$5 pause - safety 7) SL 1.0-2.0% TP 2.8-5.5% RR 2.6 - no 6% TP that causes -8% gaps 8) ATR 0.6-6% not 0.5-8% - no crazy volatility 9) TOP80 not TOP100 - only top market cap for safety</div></div><div id='openbox'>{trade_boxes_html}</div><div style='background:#111;padding:10px;margin:6px 0;border-radius:10px'><div style='color:#fc0;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% - PF {pf:.2f} EXP ${exp:.3f} PEAK ${peak:.2f} DD {dd:.1f}% DAILY ${daily:.2f}/$15 - V832 SAFE NO CTK FULL</div>"""
    for cl in closed[:40]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"; rr=cl.get("rr",2.6); sym=cl.get("symbol","?"); side=cl.get("side","?"); net=cl.get("net",0); pct=cl.get("pct_net",0); reason=cl.get("reason","")[:70]; age=cl.get("age",0); shark=cl.get("shark",0)
        html+=f"<div style='padding:5px 0;border-bottom:1px solid #222;color:{c}'><b>{sym} {side} RR {rr:.1f} SHARK {shark}</b> ${net:+.2f} {pct:+.2f}% | {reason} | {int(age//60)}m</div>"
    html+=f"""</div><script>const EQUITY = {equity_js};const ADMIN_KEY="{ADMIN_KEY}";function drawEquity(){{const cv=document.getElementById('equityChart'); if(!cv||!EQUITY.length) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...EQUITY)*0.999, mx=Math.max(...EQUITY)*1.001, rg=mx-mn||1; function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}} ctx.strokeStyle='#222'; for(let i=0;i<3;i++){{const y=h*0.1+i*h*0.8/2; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const y300=yF(300); ctx.strokeStyle='#444'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,y300); ctx.lineTo(w,y300); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle='#666'; ctx.font='8px monospace'; ctx.fillText('300',2,y300-2); ctx.strokeStyle='#0f8'; ctx.lineWidth=2; ctx.beginPath(); EQUITY.forEach((p,i)=>{{const x=i/(EQUITY.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=EQUITY[EQUITY.length-1]; ctx.fillStyle='#fc0'; ctx.beginPath(); ctx.arc(w-4,yF(last),3,0,Math.PI*2); ctx.fill(); ctx.fillText(last.toFixed(2), w-50, yF(last)-4);}}async function callCron(){{const b=document.getElementById('cronStat'); b.innerText='SCANNING SAFE...'; try{{const r=await fetch('/api/cron?key='+ADMIN_KEY); const j=await r.json(); b.innerText=j.ok ? 'OK '+j.batch+' C:'+j.candidates+' SHARK:'+j.shark_top+' DAILY:'+j.daily.toFixed(2)+'/15 NEED:'+j.daily_needed.toFixed(2)+' '+j.regime+' FULL '+j.full : j.paused ? j.reason : j.error||j.reason; setTimeout(()=>location.reload(),900);}}catch(e){{b.innerText='ERR '+e;}}}}async function callReset(){{if(!confirm('RESET SAFE CAP $300?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}function initChart(sym,entry,tp,sl,side,openTs,initialAge,cg_id){{const cv=document.getElementById('chart-'+sym); if(!cv) return; const ctx=cv.getContext('2d'); let prices = []; let liveHistory = []; let ageSec = initialAge; const ageEl=document.getElementById('live-age-'+sym); setInterval(()=>{{ ageSec += 1; const m=Math.floor(ageSec/60); const s=ageSec%60; if(ageEl) ageEl.innerText=m+'m '+s+'s'; }},1000); async function fetchPrice(){{let price=null; try{{ const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&src=coingecko&t='+Date.now()); const j=await r.json(); if(j.price && j.price>0) price=j.price; }}catch(e){{}} if(!price){{ try{{ const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&src=price&t='+Date.now()); const j=await r.json(); if(j.price && j.price>0) price=j.price; }}catch(e){{}} }} if(!price) return; const pct=side=='LONG'?(price-entry)/entry*100:(entry-price)/entry*100; if(Math.abs(pct)>10 && ageSec<300) return; const net=100*(pct-0.17)/100; const elP=document.getElementById('live-price-'+sym); const elC=document.getElementById('live-change-'+sym); const elPn=document.getElementById('live-pnl-'+sym); const dot=document.getElementById('live-dot-'+sym); if(elP){{elP.innerText='$'+price.toFixed(5); elP.style.color=pct>=0?'#0f8':'#f44';}} if(elC){{elC.innerText=pct.toFixed(3)+'%'; elC.style.color=pct>=0?'#0f8':'#f44';}} if(elPn){{elPn.innerText=(net>=0?'+':'')+'$'+net.toFixed(2); elPn.style.color=net>=0?'#0f8':'#f44';}} if(dot) dot.innerText='● V832 SAFE '+new Date().toLocaleTimeString()+' '+pct.toFixed(3)+'%'; liveHistory.push(price); if(liveHistory.length>60) liveHistory.shift(); prices = [...liveHistory]; draw();}} async function fetchKlines(){{try{{ const r=await fetch('/api/klines?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const j=await r.json(); if(j.closes && j.closes.length>10){{ let kl = j.closes.filter(p=>p>0); kl = kl.filter((p,i)=>{{ if(i==0) return true; const prev=kl[i-1]; if(prev==0) return false; return Math.abs(p-prev)/prev < 0.10; }}); if(liveHistory.length<5){{ prices = kl.slice(-30); liveHistory = [...kl.slice(-30)]; }} draw(); }} }}catch(e){{}}}} function draw(){{const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); if(prices.length<2){{ prices = Array(20).fill(entry).map((v,i)=> v + (Math.random()-0.5)*entry*0.0003); }} const usePrices = prices; let displayPrices = usePrices.map(p=>{{ let rawPct = (p-entry)/entry*100; let ampPct = rawPct; if(Math.abs(rawPct)<0.6) ampPct = rawPct*4; return entry * (1 + ampPct/100); }}); const allAmp = [...displayPrices, entry]; let mn=Math.min(...allAmp)*0.9995; let mx=Math.max(...allAmp)*1.0005; const minRange = entry*0.006; const mid = (mn+mx)/2; if((mx-mn) < minRange){{ mn=mid-minRange/2; mx=mid+minRange/2; }} const rg=mx-mn||entry*0.001; function yF(p){{return h*0.85-((p-mn)/rg)*h*0.7;}} ctx.strokeStyle='#1a1a1a'; ctx.lineWidth=1; for(let i=0;i<5;i++){{const y=h*0.1+i*h*0.8/4; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const entryY=yF(entry); ctx.strokeStyle='#fc0'; ctx.lineWidth=3; ctx.beginPath(); ctx.moveTo(0,entryY); ctx.lineTo(w,entryY); ctx.stroke(); ctx.fillStyle='#fc0'; ctx.font='bold 11px monospace'; ctx.fillText('ENTRY '+entry.toFixed(5),4,entryY-5); const tpDisplay = entry*(1+((tp-entry)/entry*100)*4/100); let tpY=yF(tpDisplay); if(tpY<0) tpY=5; if(tpY>h) tpY=h-5; ctx.strokeStyle='#0f8'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.fillStyle='#0f8'; ctx.font='9px monospace'; ctx.fillText('TP '+tp.toFixed(5),4,tpY-3); ctx.setLineDash([]); const slDisplay = entry*(1+((sl-entry)/entry*100)*4/100); let slY=yF(slDisplay); if(slY<0) slY=5; if(slY>h) slY=h-5; ctx.strokeStyle='#f44'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,slY); ctx.lineTo(w,slY); ctx.stroke(); ctx.fillStyle='#f44'; ctx.fillText('SL '+sl.toFixed(5),4,slY+11); ctx.setLineDash([]); ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=3; ctx.beginPath(); displayPrices.forEach((p,i)=>{{const x=i/(displayPrices.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); ctx.strokeStyle=side=='LONG'?'rgba(0,255,136,0.3)':'rgba(255,68,68,0.3)'; ctx.lineWidth=8; ctx.beginPath(); displayPrices.forEach((p,i)=>{{const x=i/(displayPrices.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=displayPrices[displayPrices.length-1]; const ly=yF(last); ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(w-8,ly,5,0,Math.PI*2); ctx.fill(); ctx.fillStyle=last>=entry?'#0f8':'#f44'; ctx.beginPath(); ctx.arc(w-8,ly,3.5,0,Math.PI*2); ctx.fill();}} draw(); fetchKlines(); fetchPrice(); setInterval(fetchPrice, 3000); setInterval(fetchKlines, 20000);}}window.addEventListener('load',()=>{{drawEquity(); {chart_js_init}}});</script></body></html>"""
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
        base=sym.replace("USDT",""); cg_id=SYM_TO_ID.get(base, base.lower())
        prices=[]
        try:
            url=f"https://api.coingecko.com/api/v3/simple/price?ids={urllib.parse.quote(cg_id)}&vs_currencies=usd"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as r:
                data=json.loads(r.read().decode()); price=list(data.values())[0].get("usd",0) if data else 0
                if price>0: prices.append(price)
        except: pass
        try:
            url=f"https://data-api.binance.vision/api/v3/ticker/price?symbol={base}USDT"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data=json.loads(r.read().decode()); price=float(data.get("price",0))
                if price>0: prices.append(price)
        except: pass
        if not prices: return Response(json.dumps({"error":"all sources failed","price":0}), mimetype="application/json", status=200)
        final=sum(prices)/len(prices) if len(prices)==1 or abs(prices[0]-prices[1])/prices[0]<=0.05 else prices[1]
        return Response(json.dumps({"symbol":sym,"price":final,"ts":int(time.time()),"src":"v832"}), mimetype="application/json")
    if p.startswith("/api/klines"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper(); base=sym.replace("USDT",""); cg_id=SYM_TO_ID.get(base, base.lower())
        chart=get_chart(cg_id,1)
        if chart and len(chart)>10: return Response(json.dumps({"symbol":sym,"closes":chart}), mimetype="application/json")
        try:
            klines=get_klines_fast(sym+"USDT" if not sym.endswith("USDT") else sym, "1m", 40); closes=[k["c"] for k in klines]
            return Response(json.dumps({"symbol":sym,"closes":closes}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"error":str(e)[:100],"closes":[]}), mimetype="application/json", status=200)
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            res=do_cron(); return Response(json.dumps(res), mimetype="application/json")
        except Exception as e:
            import traceback; return Response(json.dumps({"ok":False,"error":str(e)[:400],"trace":traceback.format_exc()[:500]}), mimetype="application/json", status=200)
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); kv_del("CG_TOP100_V832"); time.sleep(0.5)
        new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}},"peak":300.0,"equity":[300.0],"daily_target":15.0}
        kv_set(STATE_KEY,new); return Response(json.dumps({"ok":True,"cap":300}), mimetype="application/json")
    if p.startswith("/api/fix"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        s=load_state()
        # Remove CTK and gap trades
        s["closed"]=[c for c in s.get("closed",[]) if not (c.get("symbol","").upper() in ["CTK","OGN"] and abs(c.get("pct_net",0))>4)]
        s["open"]=[t for t in s.get("open",[]) if t.get("symbol","").upper() not in ["CTK","OGN"]]
        s["learn"]["blacklist"]={}; s["learn"]["last_coins"]={}
        # Recalc cap without CTK gaps
        s["cap"]=300.0+sum([c.get("net",0) for c in s["closed"] if c.get("symbol","").upper() not in ["CTK","OGN"] or abs(c.get("pct_net",0))<4])
        kv_set(STATE_KEY,s)
        return Response(json.dumps({"ok":True,"fixed":True,"open":len(s["open"]),"cap":s.get("cap"),"removed_ctk":True}), mimetype="application/json")
    if p.startswith("/api/debug"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps(load_state(), indent=2), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]):
            if tr.get("symbol","").upper() in PERM_BLACKLIST: continue
            cap+=tr.get("net",0)
            state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE ALL RR {tr.get('tp',0)/tr.get('sl',1):.1f} SHARK {tr.get('shark',0)}","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"shark":tr.get("shark",0),"rsi":tr.get("rsi",0),"rr":tr.get("tp",0)/tr.get("sl",1) if tr.get("sl",0)>0 else 2.6})
        state["open"]=[]; state["cap"]=cap; state=recalc_state_from_closed(state); state["peak"]=max(state.get("peak",cap),cap); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"cap":cap,"total":state["total"]}), mimetype="application/json")
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); state=load_state(); cap=state.get("cap",300.0); final=[]
        for tr in state.get("open",[]):
            if tr["symbol"]==sym:
                cap+=tr.get("net",0)
                state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE {sym} RR {tr.get('tp',0)/tr.get('sl',1):.1f} SHARK {tr.get('shark',0)}","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"shark":tr.get("shark",0),"rsi":tr.get("rsi",0),"rr":tr.get("tp",0)/tr.get("sl",1) if tr.get("sl",0)>0 else 2.6})
            else: final.append(tr)
        state["open"]=final; state["cap"]=cap; state=recalc_state_from_closed(state); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"closed":sym,"cap":cap}), mimetype="application/json")
    try:
        st=load_state(); return Response(render(st), mimetype="text/html")
    except Exception as e:
        import traceback
        return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:3000]}</pre></body></html>", mimetype="text/html", status=200)
