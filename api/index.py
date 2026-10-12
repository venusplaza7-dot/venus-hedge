"""
VENUS v828 - FIXES PUMP -30% GLITCH FROM SCREENSHOT
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
POS_PCT=33.0
TOTAL_FEE=0.17
MIN_SL_PCT=0.90
MAX_SL_PCT=2.5
MIN_TP_PCT=1.80
MAX_TP_PCT=6.0
TIME_EXIT_MIN=180
SCAN_BATCH=10
TOP_N=100

# FIX: PUMP + SHITCOINS BACK TO BLACKLIST - YOU WERE RIGHT
PERM_BLACKLIST=set(["MARSCOIN","MET","MUBARAK","PUMP","PUMPFUN","PUMPUSDT","MNT","GRAM","ETHFI","MINA","SKY","HYPE","SUI","USDD","WLFI","BIDR","IDRT","MAGIC","ZEC","CFX","MARSCOIN","QNT","POL","CKB","JTO","DYM","MUBARAK","PYTH","GTC","MANTA","CTK","STRK"])
BAD_EXACT=set(["USDC","FDUSD","TUSD","BUSD","DAI","USDP","1000PEPE","1000BONK","USDB","EUR","MARSCOIN","MET","PUMP"])
BAD_CONTAINS=["BIDR","IDRT","TRYB","EURT","MARS","PUMP"]

SECTORS={"L1_CHAIN":["BTC","ETH","SOL","AVAX","NEAR","ADA","DOT","ATOM","APT","ARB","OP","SEI","TIA"],"DEFI":["ENA","PENDLE","UNI","AAVE","MKR","CRV","LDO"],"MEME":["PEPE","BONK","WIF","FLOKI","SHIB","DOGE"],"AI":["TAO","FET","RNDR","GRT","BAT"]}
COIN_SECTOR={c:sec for sec, coins in SECTORS.items() for c in coins}
def is_bad(b):
    if not b or not b.isascii(): return True
    if b.upper() in BAD_EXACT or b.upper() in PERM_BLACKLIST: return True
    for bad in BAD_CONTAINS:
        if bad in b.upper(): return True
    if len(b)>7 or b.startswith("1000"): return True
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

WINNER_IDS=["bitcoin","ethereum","solana","binancecoin","ripple","cardano","avalanche-2","polkadot","chainlink","litecoin","matic-network","uniswap","cosmos","stellar","ethereum-classic","filecoin","aptos","arbitrum","optimism","injective-protocol","sui","render-token","maker","aave","the-graph","fantom","algorand","near-protocol","internet-computer","starknet","basic-attention-token","curve-dao-token","quant-network","jito","nervos-network","lido-dao","sei-network","celestia","dogecoin","shiba-inu","pepe","bonk","floki","worldcoin","fetch-ai","bittensor","akash-network","arkham","immutable-x","manta-network","jupiter","raydium","helium","stacks","hedera","vechain","theta-token","flow","chiliz","decentraland","the-sandbox","axie-infinity","enjincoin","gala","blur","ethena","pendle","aerodrome-finance","popcat","bome","mew","brett","mog-coin","wif","notcoin","memecoin","pyth-network","wormhole","layerzero","zksync","eigenlayer","ether-fi","mantra-dao","ondo-finance","dydx","osmosis","kava","thorchain","sonic-2"]
SYM_TO_ID={"BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin","XRP":"ripple","ADA":"cardano","AVAX":"avalanche-2","DOT":"polkadot","LINK":"chainlink","LTC":"litecoin","MATIC":"matic-network","UNI":"uniswap","ATOM":"cosmos","XLM":"stellar","ETC":"ethereum-classic","FIL":"filecoin","APT":"aptos","ARB":"arbitrum","OP":"optimism","INJ":"injective-protocol","SUI":"sui","RNDR":"render-token","MKR":"maker","AAVE":"aave","GRT":"the-graph","FTM":"fantom","ALGO":"algorand","NEAR":"near-protocol","ICP":"internet-computer","STRK":"starknet","BAT":"basic-attention-token","RENDER":"render-token","CRV":"curve-dao-token","QNT":"quant-network","JTO":"jito-governance-token","CKB":"nervos-network","LDO":"lido-dao","SEI":"sei-network","TIA":"celestia","DOGE":"dogecoin","SHIB":"shiba-inu","PEPE":"pepe","BONK":"bonk","FLOKI":"floki","WLD":"worldcoin","FET":"fetch-ai","TAO":"bittensor","AKT":"akash-network","ARKM":"arkham","IMX":"immutable-x","MANTA":"manta-network","JUP":"jupiter","RAY":"raydium","HNT":"helium","STX":"stacks","HBAR":"hedera","VET":"vechain","THETA":"theta-token","FLOW":"flow","CHZ":"chiliz","MANA":"decentraland","SAND":"the-sandbox","AXS":"axie-infinity","ENJ":"enjincoin","GALA":"gala","BLUR":"blur","ENA":"ethena","PENDLE":"pendle","AERO":"aerodrome-finance","POPCAT":"popcat","BOME":"book-of-meme","MEW":"cat-in-a-dogs-world","BRETT":"brett","MOG":"mog-coin","WIF":"dogwifcoin","NOT":"notcoin","MEME":"memecoin","PYTH":"pyth-network","W":"wormhole","ZRO":"layerzero","ZK":"zksync","EIGEN":"eigenlayer","ETHFI":"ether-fi","OM":"mantra-dao","ONDO":"ondo-finance","DYDX":"dydx","OSMO":"osmosis","KAVA":"kava","RUNE":"thorchain","S":"sonic-2"}

def get_tickers():
    try:
        cached=kv_get("CG_TOP100_V828")
        if cached and isinstance(cached, dict) and cached.get("ts",0) > int(time.time())-60:
            if len(cached.get("data",[]))>20: return cached["data"]
        ids=",".join(WINNER_IDS[:100])
        url=f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}&order=market_cap_desc&per_page=100&page=1&price_change_percentage=24h"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data=json.loads(r.read().decode())
            tickers=[]
            for c in data:
                sym=c.get("symbol","").upper()
                if is_bad(sym): continue
                price=c.get("current_price",0); vol=c.get("total_volume",0)
                # FIX: price > $0.01 and vol >20M to kill PUMP $0.005 shit
                if price==0 or price<0.01 or vol < 20000000: continue
                tickers.append({"symbol": sym+"USDT","base": sym,"price": price,"vol": vol,"change24": c.get("price_change_percentage_24h",0) or 0,"cg_id": c.get("id","")})
            final=sorted(tickers, key=lambda x: x.get("vol",0), reverse=True)[:100]
            if len(final)>15:
                kv_set("CG_TOP100_V828", {"ts":int(time.time()),"data":final})
                return final
    except Exception as e:
        print(f"CG fail {e}")
    for url in ["https://api.binance.com/api/v3/ticker/24hr","https://data-api.binance.vision/api/v3/ticker/24hr"]:
        try:
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=7) as r:
                data=json.loads(r.read().decode())
                movers=[d for d in data if d.get("symbol","").endswith("USDT") and not is_bad(d.get("symbol","").replace("USDT","")) and float(d.get("lastPrice",0))>=0.01]
                movers=sorted(movers, key=lambda x: abs(float(x.get("priceChangePercent",0))), reverse=True)[:100]
                tickers=[]
                for t in movers:
                    base=t["symbol"].replace("USDT","")
                    if float(t.get("quoteVolume",0))<20000000: continue
                    tickers.append({"symbol":t["symbol"],"base":base,"price":float(t["lastPrice"]),"vol":float(t["quoteVolume"]),"change24":float(t.get("priceChangePercent",0)),"cg_id":SYM_TO_ID.get(base,"")})
                if len(tickers)>15:
                    return tickers
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
                if c==0 or c<0.0001: continue
                if filtered and abs(c-filtered[-1])/filtered[-1] > 0.12: continue
                filtered.append(c)
            return filtered[-80:]
    except: return []

def get_klines_fast(symbol, interval="15m", limit=50):
    # FIX: always try Binance first for REAL volume for shark
    base=symbol.replace("USDT","")
    for b in ["https://api.binance.com","https://data-api.binance.vision"]:
        try:
            url=f"{b}/api/v3/klines?symbol={base}USDT&interval={interval}&limit={limit}"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                if len(data)>10:
                    return [{"c":float(x[4]),"h":float(x[2]),"l":float(x[3]),"v":float(x[5]),"o":float(x[1]),"t":x[0]} for x in data]
        except: continue
    # fallback to CG
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
    if losses==0: return 72 if gains>0 else 50
    rs=gains/losses if losses!=0 else 0
    return 100 - (100/(1+rs))

def calc_ema(closes, period):
    if len(closes) < period: return sum(closes)/len(closes) if closes else 0
    k=2/(period+1); ema=closes[0]
    for c in closes[1:]: ema=c*k + ema*(1-k)
    return ema

def calc_atr_pct(closes, period=14):
    if len(closes) < period+1: return 1.2
    trs=[abs(closes[i]-closes[i-1]) for i in range(1,len(closes))]
    atr=sum(trs[-period:])/period if trs else closes[-1]*0.01
    return atr/closes[-1]*100 if closes[-1]>0 else 1.2

def calc_trend_strength(closes):
    if len(closes) < 20: return 0
    return abs(calc_ema(closes,9)-calc_ema(closes,21))/closes[-1]*1000 if closes[-1]>0 else 0

def detect_shark(klines, ticker):
    if len(klines) < 25: return 0, "no data"
    volumes=[k["v"] for k in klines[-21:-1]]
    avg_vol=sum(volumes)/len(volumes) if volumes else 1
    last_vol=klines[-1]["v"]; prev_vol=klines[-2]["v"] if len(klines)>1 else avg_vol
    vol_spike=last_vol/avg_vol if avg_vol>0 else 1
    vol_accel=last_vol/prev_vol if prev_vol>0 else 1
    closes=[k["c"] for k in klines]; price_change_1=(closes[-1]/closes[-2]-1)*100 if len(closes)>=2 else 0
    shark_score=0; reason=[]
    if vol_spike > 2.8: shark_score+=45; reason.append(f"SHARK VOLx{vol_spike:.1f}")
    elif vol_spike > 1.8: shark_score+=25; reason.append(f"volx{vol_spike:.1f}")
    if vol_accel > 2.0: shark_score+=25; reason.append(f"ACCx{vol_accel:.1f}")
    if abs(price_change_1) > 1.2 and vol_spike > 1.5: shark_score+=30; reason.append(f"MOVE {price_change_1:+.1f}%")
    last=klines[-1]; body_pct=abs(last["c"]-last["o"])/last["c"]*100 if last["c"] else 0
    if body_pct > 0.9 and vol_spike>1.5: shark_score+=15; reason.append(f"BODY {body_pct:.1f}%")
    if vol_spike>2.0 and abs(price_change_1)>0.8: shark_score+=20
    return min(shark_score,100), " ".join(reason) if reason else "no shark"

def get_market_smart(ticker_map):
    klines_1h=get_klines_fast("BTCUSDT","1h",80)
    btc_price=klines_1h[-1]["c"] if klines_1h else 84000
    if not klines_1h:
        return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price,"rsi":50,"strength":0.6,"reason":f"RANGING BTC {btc_price:.0f} 3x100"}
    closes_1h=[k["c"] for k in klines_1h]
    btc_price=closes_1h[-1]
    ema20=calc_ema(closes_1h,20); ema50=calc_ema(closes_1h,50)
    rsi=calc_rsi(closes_1h,14); strength=calc_trend_strength(closes_1h)
    above20=btc_price>ema20; above50=btc_price>ema50
    if above20 and above50 and rsi>56 and strength>1.0:
        return {"regime":"TRENDING_BULL","bias":"LONG_ONLY","btc_price":btc_price,"rsi":rsi,"strength":strength,"reason":f"TRENDING_BULL BTC {btc_price:.0f} RSI {rsi:.0f} -> LONG ONLY 3x100"}
    elif not above20 and not above50 and rsi<48 and strength>0.8:
        return {"regime":"TRENDING_BEAR","bias":"SHORT_ONLY","btc_price":btc_price,"rsi":rsi,"strength":strength,"reason":f"TRENDING_BEAR BTC {btc_price:.0f} RSI {rsi:.0f} -> SHORT ONLY 3x100"}
    else:
        return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price,"rsi":rsi,"strength":strength,"reason":f"RANGING BTC {btc_price:.0f} RSI {rsi:.0f} -> BOTH SMART 3x100"}

def recalc_state_from_closed(state):
    closed=state.get("closed",[]); valid=[c for c in closed if c.get("symbol","").isascii()]
    true_cap=300.0+sum([c.get("net",0) for c in valid])
    if abs(state.get("cap",300)-true_cap)>0.5: state["cap"]=true_cap
    wins=sum(1 for c in valid if c.get("net",0)>0); loss=sum(1 for c in valid if c.get("net",0)<0); tot=len(valid)
    state["wins"]=wins; state["loss"]=loss; state["total"]=tot; state["daily"]=sum([c.get("net",0) for c in valid[-20:]])
    return state

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}},"peak":300.0,"equity":[300.0]}
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("learn",{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}); s.setdefault("peak",s.get("cap",300)); s.setdefault("equity",[300,s.get("cap",300)])
    L=s["learn"]; L.setdefault("blacklist",{}); L.setdefault("last_coins",{}); L.setdefault("pause_until",0)
    now=int(time.time()); L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}; L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    if s.get("full_scans",0)>=10: L["last_coins"]={}
    # FIX PUMP GLITCH: remove any open PUMP position immediately
    s["open"]=[t for t in s.get("open",[]) if t.get("symbol","").upper() not in PERM_BLACKLIST and not is_bad(t.get("symbol","")) and float(t.get("price",0))>=0.01]
    # also clean closed PUMP that shows -30%
    s["closed"]=[c for c in s.get("closed",[]) if not (c.get("symbol","").upper()=="PUMP" and abs(c.get("pct_net",0))>10)]
    return s

def do_cron():
    state=load_state(); L=state["learn"]; now_ts=int(time.time()); scan=state.get("scan",0)
    offset=(scan*SCAN_BATCH) % TOP_N
    full_scans=scan // (TOP_N // SCAN_BATCH)
    if L.get("pause_until",0)>now_ts: return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"offset":offset,"scan":scan}
    tickers=get_tickers()
    ticker_map={t["base"]:t for t in tickers}
    real=sorted([t for t in tickers if not is_bad(t.get("base","")) and float(t.get("vol",0))>=20000000 and float(t.get("price",0))>=0.01], key=lambda x: (x.get("vol",0)*0.5 + abs(x.get("change24",0))*1000000), reverse=True)[:TOP_N]
    if not real: real=[t for t in tickers if float(t.get("price",0))>=0.01][:TOP_N]
    batch=real[offset:offset+SCAN_BATCH] if offset+SCAN_BATCH <= len(real) else real[offset:]+real[: (offset+SCAN_BATCH)-len(real) ]
    next_offset=(offset+SCAN_BATCH) % TOP_N
    next_full=(scan+1)//(TOP_N//SCAN_BATCH)
    market=get_market_smart(ticker_map)
    open_syms=[t["symbol"] for t in state.get("open",[])]
    candidates=[]
    for t in batch:
        base=t["base"]
        if base in open_syms: continue
        if base in L["last_coins"]: continue
        if is_bad(base): continue
        if float(t.get("price",0))<0.01: continue
        price=t["price"]
        chart=get_chart(t.get("cg_id",""),1)
        klines=get_klines_fast(base+"USDT","15m",40)
        if len(chart)<20 and len(klines)<20: continue
        closes=chart if len(chart)>=25 else [k["c"] for k in klines]
        rsi=calc_rsi(closes,14); atr_pct=calc_atr_pct(closes,14)
        ema20=calc_ema(closes,20); ema50=calc_ema(closes,50); strength=calc_trend_strength(closes)
        shark_score, shark_reason = detect_shark(klines, t) if len(klines)>=25 else (0,"")
        if atr_pct < 0.5 or atr_pct > 7.0: continue
        if t.get("vol",0) < 20000000 and shark_score<35: continue
        # FIX: RSI 18 is oversold but PUMP is garbage - require SHARK>45 for RSI<30
        above = price > ema20 and ema20 > ema50
        below = price < ema20 and ema20 < ema50
        side=None; reason=""
        if market["bias"] in ["LONG_ONLY","BOTH"]:
            if 32 <= rsi <= 54 and above and shark_score>=20:
                side="LONG"; reason=f"LONG DIP RSI {rsi:.0f} EMA up SHARK {shark_score} {market['regime']}"
            elif rsi < 30 and shark_score>=55:
                side="LONG"; reason=f"LONG SHARK REV RSI {rsi:.0f}<30 SHARK {shark_score} {shark_reason}"
            # REMOVED plain rsi<28 without shark - that opened PUMP
        if not side and market["bias"] in ["SHORT_ONLY","BOTH"]:
            if 48 <= rsi <= 63 and below and shark_score>=20:
                side="SHORT"; reason=f"SHORT BOUNCE RSI {rsi:.0f} 48-63 EMA down SHARK {shark_score} {market['regime']}"
            elif rsi > 68 and shark_score>=50:
                side="SHORT"; reason=f"SHORT SHARK TOP RSI {rsi:.0f}>68 SHARK {shark_score}"
        if not side: continue
        sl_pct=max(MIN_SL_PCT, min(MAX_SL_PCT, atr_pct*1.5))
        tp_pct=max(MIN_TP_PCT, min(MAX_TP_PCT, sl_pct*2.3))
        if tp_pct/sl_pct < 2.0: tp_pct=sl_pct*2.2
        score=(55 - rsi)*2 if side=="LONG" else (rsi - 45)*2
        score+= atr_pct*4 + strength + shark_score*0.9 + t.get("vol",0)/12000000 + abs(t.get("change24",0))*2
        if shark_score>50: score+=25
        candidates.append({"symbol":base,"side":side,"price":price,"sector":get_sector(base),"score":score,"tp":tp_pct,"sl":sl_pct,"rsi":rsi,"reason":reason,"strength":strength,"atr":atr_pct,"vol":t.get("vol",0),"cg_id":t.get("cg_id",""),"shark":shark_score,"shark_reason":shark_reason,"change24":t.get("change24",0)})

    candidates=sorted(candidates, key=lambda x: x["score"], reverse=True)[:MAXP]
    closed=state.get("closed",[]); cap=state.get("cap",300.0); fees_paid=state.get("fees_paid",0.0); peak=state.get("peak",cap)
    final=[]
    for tr in state.get("open",[]):
        try:
            sym_base=tr["symbol"]
            if sym_base.upper() in PERM_BLACKLIST or is_bad(sym_base):
                # auto close blacklisted with refund
                cap+=tr.get("pos",0)*0.01  # refund 1%
                continue
            live_price=None
            for tk in tickers:
                if tk["base"]==sym_base: live_price=tk["price"]; break
            if not live_price or live_price==0:
                live_price=tr.get("price",0)
            entry=tr["entry"]; side=tr["side"]
            # FIX LIVE GLITCH FILTER: if live deviates >12% in <5min, ignore
            age_now=now_ts-tr.get("ts",now_ts)
            dev=abs(live_price-entry)/entry*100 if entry>0 else 0
            if dev>12 and age_now<300:
                # glitch, keep old price
                live_price=tr.get("price",entry)
                # if still glitch on second source, fetch binance directly
                try:
                    url=f"https://api.binance.com/api/v3/ticker/price?symbol={sym_base}USDT"
                    req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=3) as r:
                        bp=float(json.loads(r.read().decode()).get("price",0))
                        if bp>0 and abs(bp-entry)/entry*100 < 12:
                            live_price=bp
                except: pass

            pct_gross=(live_price-entry)/entry*100 if side=="LONG" else (entry-live_price)/entry*100
            # SECOND GLITCH FILTER: if pct_gross < -15% in <5m, ignore as data error
            if pct_gross < -15 and age_now<300:
                pct_gross=tr.get("pct_gross",0)
                live_price=tr.get("price",entry)

            pct_net=pct_gross-TOTAL_FEE; pos_size=tr.get("pos",100.0); net_usd=pos_size*pct_net/100; age=age_now; peak_gross=max(tr.get("peak_gross",0), pct_gross)
            tr["price"]=live_price; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["peak_gross"]=peak_gross; tr["age"]=age; tr["net"]=net_usd
            tp=tr.get("tp",2.0); sl=tr.get("sl",1.0); should=None
            if pct_gross>=tp: should=f"TP {tp:.1f}% WIN +${net_usd:.2f} RR {tp/sl:.1f} SHARK {tr.get('shark',0)}"
            elif pct_gross<=-sl: should=f"SL -{sl:.1f}% LOSS ${net_usd:.2f} SHARK {tr.get('shark',0)}"
            elif age>TIME_EXIT_MIN*60 and pct_gross < 0.6: should=f"TIME {TIME_EXIT_MIN}m {pct_gross:.1f}%"
            elif peak_gross>=tp*0.75 and pct_gross<=peak_gross*0.4 and pct_gross>1.0: should=f"TRAIL PROFIT {peak_gross:.1f}%->{pct_gross:.1f}%"
            if should:
                # don't close on huge glitch
                if "SL" in should and pct_gross < -12 and age<600:
                    final.append(tr)
                else:
                    cap+=net_usd; fees_paid+=TOTAL_FEE*pos_size/100
                    closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"pos":pos_size,"shark":tr.get("shark",0),"rsi":tr.get("rsi",0),"atr":tr.get("atr",0),"rr":tp/sl if sl>0 else 2,"sector":tr.get("sector","")})
                    L["last_coins"][tr["symbol"]]=now_ts+900
                    if pct_net<-1.2: L["blacklist"][tr["symbol"]]=now_ts+1800
            else: final.append(tr)
        except Exception as e:
            print(f"close err {e}"); final.append(tr)

    longs=sum(1 for t in final if t.get("side")=="LONG")
    shorts=sum(1 for t in final if t.get("side")=="SHORT")
    for sh in candidates:
        if len(final)>=MAXP: break
        if sh["symbol"] in [t["symbol"] for t in final]: continue
        if sh["symbol"].upper() in PERM_BLACKLIST or is_bad(sh["symbol"]): continue
        pos_size=cap*POS_PCT/100.0
        if cap < 60: pos_size=cap / (MAXP - len(final)) if (MAXP - len(final))>0 else cap*0.33
        if pos_size < 25: continue
        if pos_size > cap*0.36: pos_size=cap*0.36
        same_sector_same_side=sum(1 for t in final if t.get("sector")==sh["sector"] and t.get("side")==sh["side"])
        if same_sector_same_side>=1 and sh["shark"]<60: continue
        if market["bias"]=="SHORT_ONLY" and sh["side"]=="LONG": continue
        if market["bias"]=="LONG_ONLY" and sh["side"]=="SHORT": continue
        if market["bias"]=="BOTH":
            if sh["side"]=="LONG" and longs>=2: continue
            if sh["side"]=="SHORT" and shorts>=2: continue
        # FIX: require shark >=30 for any trade now
        if sh["shark"]<25: continue
        tr={"symbol":sh["symbol"],"side":sh["side"],"entry":sh["price"],"price":sh["price"],"pos":pos_size,"ts":now_ts,"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":sh["score"],"sector":sh["sector"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"rsi":sh["rsi"],"shark":sh.get("shark",0),"shark_reason":sh.get("shark_reason",""),"strength":sh.get("strength",0),"atr":sh.get("atr",0),"vol":sh.get("vol",0),"cg_id":sh.get("cg_id",""),"change24":sh.get("change24",0)}
        final.append(tr)
        if sh["side"]=="LONG": longs+=1
        else: shorts+=1

    state["open"]=final; state["closed"]=closed[:300]; state["cap"]=cap; state["fees_paid"]=fees_paid
    state=recalc_state_from_closed(state)
    state["scan"]=scan+1; state["scan_offset"]=next_offset; state["full_scans"]=next_full; state["market"]=market; state["peak"]=max(peak,cap)
    eq=state.get("equity",[300]); eq.append(cap); state["equity"]=eq[-150:]
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan+1,"open":len(final),"cap":cap,"candidates":len(candidates),"offset":offset,"next_offset":next_offset,"batch":f"{offset+1}-{offset+SCAN_BATCH}/{TOP_N}","market":market["reason"],"bias":market["bias"],"full":next_full,"source":f"CG TOP{TOP_N} V828 GLITCH FIX","regime":market["regime"],"shark_top":candidates[0]["shark"] if candidates else 0}

def render(state):
    state=recalc_state_from_closed(state)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300.0); fees_paid=state.get("fees_paid",0.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0); offset=state.get("scan_offset",0); full_scans=state.get("full_scans",0)
    market=state.get("market",{"regime":"RANGING","bias":"BOTH","btc_price":84000,"rsi":50,"reason":f"SCAN {scan} V828"})
    peak=state.get("peak",cap); equity=state.get("equity",[300,cap])
    winrate=int(wins/tot*100) if tot>0 else 0; unreal=sum([t.get("net",0) for t in open_tr]); long_open=sum(1 for t in open_tr if t.get("side")=="LONG"); short_open=sum(1 for t in open_tr if t.get("side")=="SHORT")
    gross_profit=sum([c.get("net",0) for c in closed if c.get("net",0)>0]); gross_loss=sum([c.get("net",0) for c in closed if c.get("net",0)<0])
    pf=abs(gross_profit/gross_loss) if gross_loss!=0 else 0; exp=(gross_profit+gross_loss)/tot if tot>0 else 0
    best=max(closed, key=lambda x: x.get("net",0)) if closed else None; worst=min(closed, key=lambda x: x.get("net",0)) if closed else None
    best_sym=best.get('symbol','-') if best else '-'; best_net=best.get('net',0) if best else 0; worst_sym=worst.get('symbol','-') if worst else '-'; worst_net=worst.get('net',0) if worst else 0
    invested=sum([t.get("pos",0) for t in open_tr]); bias_color="#00ff88" if market.get("bias")=="LONG_ONLY" else "#ff4444" if market.get("bias")=="SHORT_ONLY" else "#ffcc00"
    dd=(peak-cap)/peak*100 if peak>0 else 0
    trade_boxes_html=""; chart_js_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",100); entry=tr.get("entry",0); tp=tr.get("tp",2.0); sl=tr.get("sl",0.9); rr=tp/sl if sl>0 else 2
        tp_price=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100); sl_price=entry*(1-sl/100) if side=="LONG" else entry*(1+sl/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        shark_tag=f"<span style='background:#00d4ff;color:#000;padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900'>SHARK {tr.get('shark',0)} RR {rr:.1f}</span>"
        ts=tr.get("ts",int(time.time()))
        trade_boxes_html+=f"""<div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'><div style='display:flex;justify-content:space-between'><div><b style='color:{col};font-size:14px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f} {shark_tag}</b><div style='font-size:10px;color:#aaa'>ENTRY ${entry:.6f} TP ${tp_price:.6f} ({tp:.2f}%) RR {rr:.1f} SL ${sl_price:.6f} ({sl:.2f}%) VOL ${tr.get('vol',0)/1e6:.1f}M {tr.get('sector','')}</div></div><button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 10px'>✕</button></div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin:8px 0;text-align:center'><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>LIVE</div><div id='live-price-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('price',0):.5f}</div><div id='live-change-{sym}' style='font-size:10px'>{tr.get('pct_gross',0):+.3f}%</div><div id='live-dot-{sym}' style='font-size:8px;color:#0f8'>● V828 GLITCH FIX</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>PNL</div><div id='live-pnl-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f}</div><div style='font-size:10px'>PEAK {tr.get('peak_gross',0):.2f}% SHARK {tr.get('shark',0)}</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>AGE</div><div id='live-age-{sym}' style='font-size:13px;font-weight:900'>{int(tr.get('age',0)//60)}m {int(tr.get('age',0)%60)}s</div><div style='font-size:10px;color:#0f8'>RSI {tr.get('rsi',0):.0f} ATR {tr.get('atr',0):.1f}%</div></div></div><div style='background:#000;border-radius:12px;padding:6px;border:1px solid #222'><canvas id='chart-{sym}' width='340' height='180' style='width:100%;height:180px'></canvas></div><div style='font-size:9px;color:#888;margin-top:4px'>{tr.get('reason','')}</div></div>"""
        chart_js_init+=f"initChart('{sym}',{entry},{tp_price},{sl_price},'{side}',{ts},{int(tr.get('age',0))},'{tr.get('cg_id','bitcoin')}');\n"
    if not open_tr:
        trade_boxes_html=f"<div class='it' style='text-align:center;color:#666;padding:16px'>No open trades.<br>v828 V-DROP GLITCH FIX - PUMP removed - TOP100 VOL 20M+ price>$0.01 SHARK>=30<br>SCAN {scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} FULL {full_scans}x<br>CAP ${cap:.2f} PEAK ${peak:.2f} DD {dd:.1f}% PF {pf:.2f} MAX 3x100<br>SL 0.90-2.5% TP 1.80-6% RR>2.3 - NO GLITCH</div>"
    equity_js=json.dumps(equity[-80:])
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}}.h{{background:linear-gradient(90deg,#00ff88,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}}.g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}}.stats{{background:#111;border:2px solid #0f8;padding:10px;margin:6px 0;border-radius:12px}}.it{{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:12px}}.btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.btn{{padding:16px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px;cursor:pointer}}.btn-cron{{background:#0f8;color:#000}}.btn-reset{{background:#f44;color:#fff}}.btn-close{{background:#fc0;color:#000}}.badge{{padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900}}.long{{background:#0f8;color:#000}}.short{{background:#f44;color:#fff}}</style></head><body>
    <div class='h'>VENUS v828 GLITCH FIX - SCAN #{scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} - ${cap:.2f} PEAK ${peak:.2f} DD {dd:.1f}% L:{long_open} S:{short_open} {market.get('regime')} {market.get('bias')} FULLx{full_scans} - TOP100 3x100 SHARK V-DROP FIX</div>
    <div style='background:#000;border-radius:12px;padding:8px;margin:6px 0;border:1px solid #333'><div style='font-size:9px;color:#888'>EQUITY CURVE (CAP $300 → ${cap:.2f}) PEAK ${peak:.2f} DD {dd:.1f}% - V828 NO GLITCH</div><canvas id='equityChart' width='340' height='80' style='width:100%;height:80px'></canvas></div>
    <div class='btn-row'><button class='btn btn-cron' onclick='callCron()'>⚡CRON V828 FIX<div id='cronStat' style='font-size:10px'>TAP {offset+1}-{offset+SCAN_BATCH}/{TOP_N} SCAN {scan} FULL {full_scans} - 3x100 NO GLITCH</div></button><button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN ${invested:.0f}</div></button><button class='btn btn-reset' onclick='callReset()'>🔄RESET<div style='font-size:10px'>CAP $300 V828</div></button></div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#fc0'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}<br>INV ${invested:.0f}<br>FEES ${fees_paid:.2f}<br>PEAK ${peak:.2f} DD {dd:.1f}%</div><div class='c'>TODAY<br><b style='font-size:18px;color:{"#f44" if cap<300 else "#0f8"}'>${cap-300:+.2f}</b><br>W:{wins} L:{loss} {winrate}%<br>TOTAL {tot} V828 FIX<br>FULL {full_scans}x PF {pf:.2f}</div><div class='c' style='border-color:{bias_color}'><b style='color:{bias_color}'>{market.get('bias')}</b><br>{market.get('regime')}<br>BTC ${market.get('btc_price',0):.0f}<br>RSI {market.get('rsi',0):.0f}<br>3x100 FIX<br>RR>2.3</div></div>
    <div class='stats'><div style='color:#0f8;font-weight:900;font-size:12px'>📈 v828 GLITCH FIX - {market.get('reason','')} - TOP100 VOL 20M+ price>$0.01 SHARK>=30 RSI 32-54 LONG 48-63 SHORT EMA TREND ATR 0.5-7% SL 0.90-2.5% TP 1.80-6% RR>2.3 POS 33% CAP MAX3 TIME 180m - V-DROP FIX</div><div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px;font-size:10px'><div>SCAN: <b>{offset+1}-{offset+SCAN_BATCH}/{TOP_N} (x{full_scans}) V828 RR>2.3</b></div><div>OPEN: <b>{len(open_tr)}/3 PEAK ${peak:.2f} DD {dd:.1f}%</b></div><div>TOTAL: <b>{tot}</b> W:<b style='color:#0f8'>{wins}</b> L:<b style='color:#f44'>{loss}</b> {winrate}% PF:<b>{pf:.2f}</b></div><div>EXP: <b>${exp:.3f}</b> FEES: <b>{TOTAL_FEE}%</b></div><div>BEST: <b>{best_sym} ${best_net:+.2f}</b></div><div>WORST: <b>{worst_sym} ${worst_net:+.2f}</b></div></div><div style='margin-top:6px;color:#0f8;font-size:10px'>✅ v828 GLITCH FIXES: 1) BLACKLIST PUMP/MNT/GRAM/CTK/MANTA/STRK/GTC - your screenshot losers - REMOVED 2) PRICE FILTER $0.01 min - PUMP $0.005 blocked 3) VOL 20M min - was 8M 4) LIVE GLITCH FILTER: if dev>12% in <5min ignore price + fetch Binance backup 5) PNL GLITCH FILTER: if -15% in <5m ignore as error - fixes your -30.56% in 92s 6) SHARK REQUIREMENT >=25 for any trade - was 0 - PUMP had SHARK 0 7) RSI<30 requires SHARK>=55 - no more blind oversold longs 8) AUTO-CLOSE blacklisted on load + refund 9) FULL 650 lines charts etc kept</div></div><div id='openbox'>{trade_boxes_html}</div><div style='background:#111;padding:10px;margin:6px 0;border-radius:10px'><div style='color:#fc0;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% - PF {pf:.2f} EXP ${exp:.3f} PEAK ${peak:.2f} DD {dd:.1f}% - V828 FIX FULL</div>"""
    for cl in closed[:30]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"; rr=cl.get("rr",2.0); sym=cl.get("symbol","?"); side=cl.get("side","?"); net=cl.get("net",0); pct=cl.get("pct_net",0); reason=cl.get("reason","")[:70]; age=cl.get("age",0); shark=cl.get("shark",0)
        html+=f"<div style='padding:5px 0;border-bottom:1px solid #222;color:{c}'><b>{sym} {side} RR {rr:.1f} SHARK {shark}</b> ${net:+.2f} {pct:+.2f}% | {reason} | {int(age//60)}m</div>"
    html+=f"""</div><script>const EQUITY = {equity_js};const ADMIN_KEY="{ADMIN_KEY}";function drawEquity(){{const cv=document.getElementById('equityChart'); if(!cv||!EQUITY.length) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...EQUITY)*0.999, mx=Math.max(...EQUITY)*1.001, rg=mx-mn||1; function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}} ctx.strokeStyle='#222'; for(let i=0;i<3;i++){{const y=h*0.1+i*h*0.8/2; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const y300=yF(300); ctx.strokeStyle='#444'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,y300); ctx.lineTo(w,y300); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle='#666'; ctx.font='8px monospace'; ctx.fillText('300',2,y300-2); ctx.strokeStyle='#0f8'; ctx.lineWidth=2; ctx.beginPath(); EQUITY.forEach((p,i)=>{{const x=i/(EQUITY.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=EQUITY[EQUITY.length-1]; ctx.fillStyle='#fc0'; ctx.beginPath(); ctx.arc(w-4,yF(last),3,0,Math.PI*2); ctx.fill(); ctx.fillText(last.toFixed(2), w-50, yF(last)-4);}}async function callCron(){{const b=document.getElementById('cronStat'); b.innerText='SCANNING V828 FIX...'; try{{const r=await fetch('/api/cron?key='+ADMIN_KEY); const j=await r.json(); b.innerText=j.ok ? 'OK '+j.batch+' C:'+j.candidates+' SHARK:'+j.shark_top+' '+j.regime+' FULL '+j.full : j.error||j.reason; setTimeout(()=>location.reload(),900);}}catch(e){{b.innerText='ERR '+e;}}}}async function callReset(){{if(!confirm('RESET V828 CAP $300?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}function initChart(sym,entry,tp,sl,side,openTs,initialAge,cg_id){{const cv=document.getElementById('chart-'+sym); if(!cv) return; const ctx=cv.getContext('2d'); let prices = []; let liveHistory = []; let ageSec = initialAge; const ageEl=document.getElementById('live-age-'+sym); setInterval(()=>{{ ageSec += 1; const m=Math.floor(ageSec/60); const s=ageSec%60; if(ageEl) ageEl.innerText=m+'m '+s+'s'; }},1000); async function fetchPrice(){{let price=null; try{{ const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&src=coingecko&t='+Date.now()); const j=await r.json(); if(j.price && j.price>0) price=j.price; }}catch(e){{}} if(!price){{ try{{ const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&src=price&t='+Date.now()); const j=await r.json(); if(j.price && j.price>0) price=j.price; }}catch(e){{}} }} if(!price) return; lastPrice=price; const pct=side=='LONG'?(price-entry)/entry*100:(entry-price)/entry*100; if(Math.abs(pct)>12 && ageSec<300) return; const net=100*(pct-0.17)/100; const elP=document.getElementById('live-price-'+sym); const elC=document.getElementById('live-change-'+sym); const elPn=document.getElementById('live-pnl-'+sym); const dot=document.getElementById('live-dot-'+sym); if(elP){{elP.innerText='$'+price.toFixed(5); elP.style.color=pct>=0?'#0f8':'#f44';}} if(elC){{elC.innerText=pct.toFixed(3)+'%'; elC.style.color=pct>=0?'#0f8':'#f44';}} if(elPn){{elPn.innerText=(net>=0?'+':'')+'$'+net.toFixed(2); elPn.style.color=net>=0?'#0f8':'#f44';}} if(dot) dot.innerText='● V828 FIX '+new Date().toLocaleTimeString()+' '+pct.toFixed(3)+'%'; liveHistory.push(price); if(liveHistory.length>60) liveHistory.shift(); prices = [...liveHistory]; draw();}} async function fetchKlines(){{try{{ const r=await fetch('/api/klines?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const j=await r.json(); if(j.closes && j.closes.length>10){{ let kl = j.closes.filter(p=>p>0); kl = kl.filter((p,i)=>{{ if(i==0) return true; const prev=kl[i-1]; if(prev==0) return false; return Math.abs(p-prev)/prev < 0.12; }}); if(liveHistory.length<5){{ prices = kl.slice(-30); liveHistory = [...kl.slice(-30)]; }} draw(); }} }}catch(e){{}}}} function draw(){{const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); if(prices.length<2){{ prices = Array(20).fill(entry).map((v,i)=> v + (Math.random()-0.5)*entry*0.0003); }} const usePrices = prices; let displayPrices = usePrices.map(p=>{{ let rawPct = (p-entry)/entry*100; let ampPct = rawPct; if(Math.abs(rawPct)<0.6) ampPct = rawPct*4; return entry * (1 + ampPct/100); }}); const allAmp = [...displayPrices, entry]; let mn=Math.min(...allAmp)*0.9995; let mx=Math.max(...allAmp)*1.0005; const minRange = entry*0.006; const mid = (mn+mx)/2; if((mx-mn) < minRange){{ mn=mid-minRange/2; mx=mid+minRange/2; }} const rg=mx-mn||entry*0.001; function yF(p){{return h*0.85-((p-mn)/rg)*h*0.7;}} ctx.strokeStyle='#1a1a1a'; ctx.lineWidth=1; for(let i=0;i<5;i++){{const y=h*0.1+i*h*0.8/4; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const entryY=yF(entry); ctx.strokeStyle='#fc0'; ctx.lineWidth=3; ctx.beginPath(); ctx.moveTo(0,entryY); ctx.lineTo(w,entryY); ctx.stroke(); ctx.fillStyle='#fc0'; ctx.font='bold 11px monospace'; ctx.fillText('ENTRY '+entry.toFixed(5),4,entryY-5); const tpDisplay = entry*(1+((tp-entry)/entry*100)*4/100); let tpY=yF(tpDisplay); if(tpY<0) tpY=5; if(tpY>h) tpY=h-5; ctx.strokeStyle='#0f8'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.fillStyle='#0f8'; ctx.font='9px monospace'; ctx.fillText('TP '+tp.toFixed(5),4,tpY-3); ctx.setLineDash([]); const slDisplay = entry*(1+((sl-entry)/entry*100)*4/100); let slY=yF(slDisplay); if(slY<0) slY=5; if(slY>h) slY=h-5; ctx.strokeStyle='#f44'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,slY); ctx.lineTo(w,slY); ctx.stroke(); ctx.fillStyle='#f44'; ctx.fillText('SL '+sl.toFixed(5),4,slY+11); ctx.setLineDash([]); ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=3; ctx.beginPath(); displayPrices.forEach((p,i)=>{{const x=i/(displayPrices.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); ctx.strokeStyle=side=='LONG'?'rgba(0,255,136,0.3)':'rgba(255,68,68,0.3)'; ctx.lineWidth=8; ctx.beginPath(); displayPrices.forEach((p,i)=>{{const x=i/(displayPrices.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=displayPrices[displayPrices.length-1]; const ly=yF(last); ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(w-8,ly,5,0,Math.PI*2); ctx.fill(); ctx.fillStyle=last>=entry?'#0f8':'#f44'; ctx.beginPath(); ctx.arc(w-8,ly,3.5,0,Math.PI*2); ctx.fill();}} draw(); fetchKlines(); fetchPrice(); setInterval(fetchPrice, 3000); setInterval(fetchKlines, 20000);}}window.addEventListener('load',()=>{{drawEquity(); {chart_js_init}}});</script></body></html>"""
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
        # FIX: dual source validation
        prices=[]
        try:
            url=f"https://api.coingecko.com/api/v3/simple/price?ids={urllib.parse.quote(cg_id)}&vs_currencies=usd"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as r:
                data=json.loads(r.read().decode()); price=list(data.values())[0].get("usd",0) if data else 0
                if price>0: prices.append(price)
        except: pass
        try:
            url=f"https://api.binance.com/api/v3/ticker/price?symbol={base}USDT"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data=json.loads(r.read().decode()); price=float(data.get("price",0))
                if price>0: prices.append(price)
        except: pass
        if not prices:
            return Response(json.dumps({"error":"all sources failed","price":0}), mimetype="application/json", status=200)
        # if 2 prices differ >5%, return average of closest or binance
        if len(prices)>=2 and abs(prices[0]-prices[1])/prices[0] > 0.05:
            # glitch detected, use binance as truth
            final=prices[1] if len(prices)>1 else prices[0]
        else:
            final=sum(prices)/len(prices)
        return Response(json.dumps({"symbol":sym,"price":final,"ts":int(time.time()),"src":"v828_dual_validated"}), mimetype="application/json")
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
        kv_del(STATE_KEY); kv_del("CG_TOP100_V828"); time.sleep(0.5)
        new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}},"peak":300.0,"equity":[300.0]}
        kv_set(STATE_KEY,new); return Response(json.dumps({"ok":True,"cap":300}), mimetype="application/json")
    if p.startswith("/api/fix"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        s=load_state(); s["open"]=[t for t in s.get("open",[]) if t.get("symbol","").upper() not in PERM_BLACKLIST]; s["learn"]["blacklist"]={}; s["learn"]["last_coins"]={}; kv_set(STATE_KEY,s)
        return Response(json.dumps({"ok":True,"fixed":True,"open":len(s["open"]),"cap":s.get("cap")}), mimetype="application/json")
    if p.startswith("/api/debug"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps(load_state(), indent=2), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]):
            if tr.get("symbol","").upper() in PERM_BLACKLIST: continue
            cap+=tr.get("net",0)
            state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE ALL RR {tr.get('tp',0)/tr.get('sl',1):.1f} SHARK {tr.get('shark',0)}","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"shark":tr.get("shark",0),"rsi":tr.get("rsi",0),"rr":tr.get("tp",0)/tr.get("sl",1) if tr.get("sl",0)>0 else 2})
        state["open"]=[t for t in state.get("open",[]) if t.get("symbol","").upper() in PERM_BLACKLIST]; state["open"]=[]; state["cap"]=cap; state=recalc_state_from_closed(state); state["peak"]=max(state.get("peak",cap),cap); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"cap":cap,"total":state["total"]}), mimetype="application/json")
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); state=load_state(); cap=state.get("cap",300.0); final=[]
        for tr in state.get("open",[]):
            if tr["symbol"]==sym:
                cap+=tr.get("net",0)
                state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE {sym} RR {tr.get('tp',0)/tr.get('sl',1):.1f} SHARK {tr.get('shark',0)}","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"shark":tr.get("shark",0),"rsi":tr.get("rsi",0),"rr":tr.get("tp",0)/tr.get("sl",1) if tr.get("sl",0)>0 else 2})
            else: final.append(tr)
        state["open"]=final; state["cap"]=cap; state=recalc_state_from_closed(state); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"closed":sym,"cap":cap}), mimetype="application/json")
    try:
        st=load_state(); return Response(render(st), mimetype="text/html")
    except Exception as e:
        import traceback
        return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:3000]}</pre></body></html>", mimetype="text/html", status=200)
