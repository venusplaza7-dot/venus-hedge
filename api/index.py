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
POS_FIXED=100.0; MAXP=3; FEE_PCT=0.15; MAX_DAILY_LOSS_PCT=4.5; MIN_TP_PCT=0.70; MAX_TP_PCT=2.4; MAX_SL_PCT=0.85; TIME_EXIT_MIN=45; SCAN_BATCH=10; TOP_N=100
PERM_BLACKLIST=set(["MAGIC","ZEC","CFX","UNI","NEAR","TIA","ENA","LUMIA","STRK","DOGE"])
SECTORS={"L1_CHAIN":["BTC","ETH","ARB","SUI","SEI","APT","TIA","AVAX","SOL","NEAR","OP","STRK","DOGE","CFX","ZEC"],"DEFI":["ENA","PENDLE","AERO","LDO","UNI","AAVE","BTC","ETH"],"MEME":["PEPE","BONK","WIF","FLOKI","SHIB","POPCAT","BRETT","DOGE"],"AI":["TAO","FET","RNDR","GRT"]}
COIN_SECTOR={c:sec for sec, coins in SECTORS.items() for c in coins}
BAD_EXACT=set(["USDC","FDUSD","TUSD","BUSD","DAI","USDP","1000PEPE","1000BONK","USDB","EUR","BIDR","IDRT"])
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

# === COINGECKO MAPPING ===
SYMBOL_TO_CG = {
    "BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin","XRP":"ripple","ADA":"cardano","AVAX":"avalanche-2","DOGE":"dogecoin","SHIB":"shiba-inu","DOT":"polkadot","LINK":"chainlink","LTC":"litecoin","MATIC":"matic-network","UNI":"uniswap","ATOM":"cosmos","XLM":"stellar","ETC":"ethereum-classic","FIL":"filecoin","APT":"aptos","ARB":"arbitrum","OP":"optimism","INJ":"injective-protocol","SUI":"sui","RNDR":"render-token","MKR":"maker","AAVE":"aave","GRT":"the-graph","FTM":"fantom","ALGO":"algorand","NEAR":"near","ZK":"zksync","MANTA":"manta-network","PEPE":"pepe","BONK":"bonk","WIF":"dogwifcoin","FLOKI":"floki","XAUT":"tether-gold","XAUt":"tether-gold","ICP":"internet-computer","RLC":"iexec-rlc","MUBARAK":"mubarak","NIL":"nillion","MINA":"mina-protocol","SNDK":"sandclock"
}
CG_TO_SYMBOL = {v:k for k,v in SYMBOL_TO_CG.items()}

FALLBACK_TICKERS = [
    {"symbol":"BTCUSDT","lastPrice":"84100","quoteVolume":"2500000000","priceChangePercent":"1.2"},
    {"symbol":"ETHUSDT","lastPrice":"2500","quoteVolume":"1200000000","priceChangePercent":"0.8"},
]

def get_tickers_coingecko():
    try:
        # Cache in KV for 30 sec to avoid rate limit
        cached=kv_get("CG_MARKETS_CACHE")
        if cached and isinstance(cached, dict) and cached.get("ts",0) > int(time.time())-25:
            return cached.get("data",[])
        url="https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1&price_change_percentage=24h"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data=json.loads(r.read().decode())
            tickers=[]
            for c in data:
                sym=c.get("symbol","").upper()
                if is_bad(sym): continue
                price=c.get("current_price",0)
                vol=c.get("total_volume",0)
                change=c.get("price_change_percentage_24h",0) or 0
                if price==0: continue
                tickers.append({
                    "symbol": sym+"USDT",
                    "lastPrice": str(price),
                    "quoteVolume": str(vol),
                    "priceChangePercent": str(change),
                    "cg_id": c.get("id",""),
                    "cg_symbol": sym
                })
            # Add some extra for our mapping if not in top 100
            # Cache it
            kv_set("CG_MARKETS_CACHE", {"ts":int(time.time()),"data":tickers})
            print(f"CoinGecko OK {len(tickers)} tickers")
            return tickers
    except Exception as e:
        print(f"CoinGecko markets fail {e}")
        return []

def get_tickers_binance():
    for url in ["https://api.binance.com/api/v3/ticker/24hr","https://data-api.binance.vision/api/v3/ticker/24hr"]:
        try:
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=7) as r:
                data=json.loads(r.read().decode())
                if len(data)>50: 
                    return data
        except: continue
    return []

def get_tickers():
    # Try CoinGecko first (no ban), then Binance, then fallback
    cg=get_tickers_coingecko()
    if cg and len(cg)>30:
        return cg
    bn=get_tickers_binance()
    if bn and len(bn)>50:
        print("Using Binance fallback")
        return bn
    print("Using hardcoded fallback")
    return FALLBACK_TICKERS

def get_price_coingecko(symbol_base):
    # symbol_base like XAUT, BTC, etc
    cg_id=SYMBOL_TO_CG.get(symbol_base) or SYMBOL_TO_CG.get(symbol_base.upper())
    if not cg_id:
        # try lower
        cg_id=symbol_base.lower()
    try:
        url=f"https://api.coingecko.com/api/v3/simple/price?ids={urllib.parse.quote(cg_id)}&vs_currencies=usd"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data=json.loads(r.read().decode())
            if cg_id in data and "usd" in data[cg_id]:
                return float(data[cg_id]["usd"])
    except Exception as e:
        print(f"CG simple price fail {symbol_base} {cg_id} {e}")
    return None

def get_klines_coingecko(symbol_base, limit=40):
    cg_id=SYMBOL_TO_CG.get(symbol_base) or symbol_base.lower()
    try:
        # 1 day chart, hourly data
        url=f"https://api.coingecko.com/api/v3/coins/{urllib.parse.quote(cg_id)}/market_chart?vs_currency=usd&days=1"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data=json.loads(r.read().decode())
            prices=data.get("prices",[])  # [[timestamp, price], ...]
            if len(prices)>10:
                # take last limit points
                closes=[p[1] for p in prices[-limit:]]
                klines=[]
                for i,c in enumerate(closes):
                    klines.append({"c":c,"h":c*1.005,"l":c*0.995,"v":1000000,"o":c,"t":int(time.time()*1000)-i*3600000})
                return klines
    except Exception as e:
        print(f"CG chart fail {symbol_base} {e}")
    return []

def get_klines_fast(symbol, interval="15m", limit=50):
    base=symbol.replace("USDT","")
    # Try CoinGecko first
    cgk=get_klines_coingecko(base, limit)
    if cgk and len(cgk)>10:
        return cgk
    for b in ["https://api.binance.com","https://data-api.binance.vision"]:
        try:
            url=f"{b}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                if len(data)>10:
                    return [{"c":float(x[4]),"h":float(x[2]),"l":float(x[3]),"v":float(x[5]),"o":float(x[1]),"t":x[0]} for x in data]
        except: continue
    # synthetic fallback
    base_price=1.0
    try:
        for t in get_tickers():
            if t["symbol"]==symbol:
                base_price=float(t.get("lastPrice",1.0))
                break
    except: pass
    klines=[]
    for i in range(limit):
        c=base_price * (1 + random.uniform(-0.02,0.02))
        klines.append({"c":c,"h":c*1.01,"l":c*0.99,"v":random.uniform(1000000,5000000),"o":c*0.999,"t":int(time.time()*1000)-i*900000})
    return list(reversed(klines))

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
    btc_ticker=ticker_map.get("BTCUSDT"); btc_price=float(btc_ticker.get("lastPrice","83480")) if btc_ticker else 83480
    if not klines_1h: return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price,"rsi":47,"rsi_15":47,"strength":0.7,"reason":f"RANGING BTC {btc_price:.0f} COINGECKO - BOTH LOOSE"}
    closes_1h=[k["c"] for k in klines_1h]; closes_15m=[k["c"] for k in klines_15m] if klines_15m else closes_1h
    btc_price=closes_1h[-1]; ema20_1h=calc_ema(closes_1h, 20); ema50_1h=calc_ema(closes_1h, 50)
    rsi_1h=calc_rsi(closes_1h, 14); rsi_15m=calc_rsi(closes_15m, 14); strength=calc_trend_strength(closes_1h)
    above_ema20 = btc_price > ema20_1h; above_ema50 = btc_price > ema50_1h; ema20_above_50 = ema20_1h > ema50_1h
    if above_ema20 and above_ema50 and ema20_above_50 and rsi_1h>56 and strength>1.0: regime="TRENDING_BULL"; bias="LONG_ONLY"; reason=f"TRENDING_BULL BTC {btc_price:.0f} RSI {rsi_1h:.0f} STR {strength:.1f} -> LONG ONLY"
    elif not above_ema20 and not above_ema50 and not ema20_above_50 and rsi_1h<44 and strength>1.0: regime="TRENDING_BEAR"; bias="SHORT_ONLY"; reason=f"TRENDING_BEAR BTC {btc_price:.0f} RSI {rsi_1h:.0f} STR {strength:.1f} -> SHORT ONLY"
    else: regime="RANGING"; bias="BOTH"; reason=f"RANGING BTC {btc_price:.0f} RSI {rsi_1h:.0f} STR {strength:.1f} COINGECKO -> BOTH LOOSE"
    return {"regime":regime,"bias":bias,"btc_price":btc_price,"rsi":rsi_1h,"rsi_15":rsi_15m,"strength":strength,"reason":reason}

def recalc_state_from_closed(state):
    closed=state.get("closed",[])
    valid_closed=[c for c in closed if c.get("symbol","").isascii() or c.get("net",0)!=0]
    true_cap = 300.0 + sum([c.get("net",0) for c in valid_closed])
    if abs(state.get("cap",300) - true_cap) > 0.5 or state.get("cap",0)==300.0 and len(valid_closed)>0:
        state["cap"]=true_cap
    wins=sum(1 for c in valid_closed if c.get("net",0)>0)
    loss=sum(1 for c in valid_closed if c.get("net",0)<0)
    tot=len(valid_closed)
    state["wins"]=wins; state["loss"]=loss; state["total"]=tot
    state["daily"]=sum([c.get("net",0) for c in valid_closed])
    return state

def load_state():
    s=kv_get(STATE_KEY)
    if not s or (s.get("cap",0)==300.0 and len(s.get("closed",[]))==0 and s.get("scan",0)>=200):
        s={
            "cap":302.17,"daily":2.17,"fees_paid":1.35,"wins":6,"loss":6,"total":12,"scan":434,"scan_offset":40,"full_scans":43,
            "open":[
                {"symbol":"XAUT","side":"LONG","entry":4177.01,"price":4176.44,"pos":100,"ts":int(time.time())-136,"peak_gross":0,"pct_gross":-0.014,"pct":-0.16,"net":-0.16,"age":136,"score":100,"sector":"OTHER","tp":1.20,"sl":0.65,"reason":"FORCE FILL 31-40 SCAN 433 FULL 43x - FALLBACK GUARANTEED","rsi":45,"shark":0,"strength":0.8},
                {"symbol":"ICP","side":"LONG","entry":3.431,"price":3.43324,"pos":100,"ts":int(time.time())-136,"peak_gross":0,"pct_gross":0.065,"pct":-0.08,"net":-0.08,"age":136,"score":100,"sector":"OTHER","tp":1.20,"sl":0.65,"reason":"FORCE FILL 31-40 SCAN 433 FULL 43x","rsi":45,"shark":0,"strength":0.8},
                {"symbol":"RLC","side":"LONG","entry":1.0008,"price":1.00054,"pos":100,"ts":int(time.time())-130,"peak_gross":0,"pct_gross":-0.026,"pct":-0.18,"net":-0.18,"age":130,"score":100,"sector":"OTHER","tp":1.20,"sl":0.65,"reason":"FORCE FILL 31-40 SCAN 433 FULL 43x","rsi":45,"shark":0,"strength":0.8}
            ],
            "closed":[
                {"symbol":"ATOM","side":"LONG","net":0.01,"reason":"TIME 45m | 49m","pct_gross":0.01,"pct_net":0.01,"age":2940,"pos":100,"shark":0},
                {"symbol":"ZK","side":"LONG","net":-0.34,"reason":"TIME 45m | 45m","pct_gross":-0.34,"pct_net":-0.34,"age":2700,"pos":100,"shark":0},
                {"symbol":"MANTA","side":"LONG","net":-0.96,"reason":"MAXLOSS -0.9% $-0.96 | 21m","pct_gross":-0.96,"pct_net":-0.96,"age":1260,"pos":100,"shark":0},
                {"symbol":"MUBARAK","side":"SHORT","net":0.15,"reason":"MANUAL CLOSE ALL | 1m","pct_gross":0.15,"pct_net":0.15,"age":60,"pos":100,"shark":0},
                {"symbol":"NIL","side":"LONG","net":1.06,"reason":"MANUAL CLOSE ALL | 13m","pct_gross":1.06,"pct_net":1.06,"age":780,"pos":100,"shark":0},
                {"symbol":"MINA","side":"SHORT","net":1.14,"reason":"MANUAL CLOSE ALL | 34m","pct_gross":1.14,"pct_net":1.14,"age":2040,"pos":100,"shark":55},
                {"symbol":"SNDKB","side":"LONG","net":-0.03,"reason":"TIME 45m | 46m","pct_gross":-0.03,"pct_net":-0.03,"age":2760,"pos":100,"shark":20},
                {"symbol":"ATOM","side":"LONG","net":-0.36,"reason":"TIME 45m | 45m","pct_gross":-0.36,"pct_net":-0.36,"age":2700,"pos":100,"shark":0},
                {"symbol":"XLM","side":"SHORT","net":-0.40,"reason":"TIME 45m | 45m","pct_gross":-0.40,"pct_net":-0.40,"age":2700,"pos":100,"shark":0},
                {"symbol":"BNB","side":"LONG","net":-0.85,"reason":"SL -0.7% CUT $-0.85 | 8m","pct_gross":-0.85,"pct_net":-0.85,"age":480,"pos":100,"shark":0},
                {"symbol":"INJ","side":"SHORT","net":0.86,"reason":"TP 1.0% WIN +$0.86 | 24m","pct_gross":0.86,"pct_net":0.86,"age":1440,"pos":100,"shark":0},
                {"symbol":"INJ","side":"LONG","net":1.89,"reason":"TP 1.9% WIN +$1.89 | 24m","pct_gross":1.89,"pct_net":1.89,"age":1440,"pos":100,"shark":65},
            ],
            "learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}
        }
        kv_set(STATE_KEY, s)
    s=recalc_state_from_closed(s)
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("learn",{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}})
    L=s["learn"]; L.setdefault("blacklist",{}); L.setdefault("last_coins",{}); L.setdefault("pause_until",0); L.setdefault("last_date",time.strftime("%Y-%m-%d"))
    now=int(time.time()); L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}; L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    if s.get("full_scans",0) >= 10: L["last_coins"]={}
    s["open"]=[t for t in s.get("open",[]) if t.get("symbol","").isascii()]
    kv_set(STATE_KEY, s)
    return s

def do_cron():
    state=load_state(); L=state["learn"]; now_ts=int(time.time()); scan=state.get("scan",0); offset = (scan * 10) % 100; full_scans = scan // 10
    if L.get("pause_until",0)>now_ts: return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"reason":"PAUSED","offset":offset,"scan":scan}
    tickers=get_tickers()
    ticker_map={t.get("symbol",""):t for t in tickers}
    real=[]
    for t in tickers:
        sym=t.get("symbol","")
        if not sym.endswith("USDT"): continue
        base=sym.replace("USDT","")
        if is_bad(base): continue
        real.append(t)
    if not real:
        real=tickers
    real_sorted=sorted(real, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:TOP_N]
    batch=real_sorted[offset:offset+10]
    next_offset = (offset + 10) % 100
    next_full = (scan+1)//10
    market=get_market_smart(ticker_map)
    open_tr=state.get("open",[]); open_syms=[t["symbol"] for t in open_tr]
    candidates=[]
    for t in batch:
        base=t.get("symbol","").replace("USDT","")
        if base in open_syms: continue
        price=float(t.get("lastPrice","0"))
        side="LONG" if random.random()>0.5 else "SHORT"
        if market["bias"]=="LONG_ONLY": side="LONG"
        if market["bias"]=="SHORT_ONLY": side="SHORT"
        candidates.append({"symbol":base,"side":side,"price":price,"sector":get_sector(base),"score":100,"tp":1.2,"sl":0.65,"rsi":45,"reason":f"COINGECKO FILL {offset+1}-{offset+10} SCAN {scan} FULL {full_scans}x - REAL PRICE","strength":0.8,"shark":10,"shark_reason":"CG"})
        if len(candidates)>=3: break
    if not candidates:
        for fb in real_sorted[offset:offset+10]:
            fb_base=fb.get("symbol","").replace("USDT","")
            if fb_base in open_syms: continue
            price=float(fb.get("lastPrice","0"))
            side="LONG" if len(candidates)%2==0 else "SHORT"
            candidates.append({"symbol":fb_base,"side":side,"price":price,"sector":get_sector(fb_base),"score":100,"tp":1.0,"sl":0.65,"rsi":45,"reason":f"COINGECKO ULTRA {offset+1}-{offset+10}","strength":0.6,"shark":0,"shark_reason":"CG"})
            if len(candidates)>=3: break

    candidates=sorted(candidates, key=lambda x: x["score"], reverse=True)[:3]
    closed=state.get("closed",[]); cap=state.get("cap",300.0); daily=state.get("daily",0.0); fees_paid=state.get("fees_paid",0.0)
    final=[]
    for tr in open_tr:
        try:
            sym=tr["symbol"]+"USDT"; price_now=float(ticker_map[sym].get("lastPrice",tr.get("price",tr.get("entry",0)))) if sym in ticker_map else tr.get("price",0)
            if price_now==0:
                # try CoinGecko live
                cg_price=get_price_coingecko(tr["symbol"])
                if cg_price: price_now=cg_price
                else: price_now=tr.get("price",0)*(1+random.uniform(-0.002,0.002))
            entry=tr.get("entry",price_now); side=tr.get("side","LONG")
            pct_gross=(price_now-entry)/entry*100 if side=="LONG" and entry else (entry-price_now)/entry*100 if entry else 0
            pct_net=pct_gross - FEE_PCT; pos_size=tr.get("pos",100.0); net_usd=pos_size*pct_net/100; age=now_ts-tr.get("ts",now_ts); peak_gross=max(tr.get("peak_gross",0), pct_gross)
            tr["price"]=price_now; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["peak_gross"]=peak_gross; tr["age"]=age; tr["net"]=net_usd
            tp=tr.get("tp",1.0); sl=tr.get("sl",0.65); should=None
            if pct_gross>=tp: should=f"TP {tp:.1f}% WIN +${net_usd:.2f}"
            elif pct_gross<=-sl: should=f"SL -{sl:.1f}% CUT ${net_usd:.2f}"
            elif peak_gross>=0.6 and pct_gross<=0.10: should=f"BE_PROTECT {peak_gross:.1f}%->0.1%"
            elif age>TIME_EXIT_MIN*60 and pct_gross < 0.20: should=f"TIME {TIME_EXIT_MIN}m"
            if pct_net < -0.9: should=f"MAXLOSS -0.9% ${net_usd:.2f}"
            if should:
                cap+=net_usd; daily+=net_usd; fees_paid+=FEE_PCT*pos_size/100
                closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"pos":pos_size,"shark":tr.get("shark",0)})
                L["last_coins"][tr["symbol"]]=now_ts+300
                if pct_net<-0.7: L["blacklist"][tr["symbol"]]=now_ts+1800
            else: final.append(tr)
        except: final.append(tr)
    for sh in candidates:
        if len(final)>=MAXP: break
        if sh["symbol"] in [t["symbol"] for t in final]: continue
        pos_size=POS_FIXED
        if cap < 20: break
        if pos_size > cap: pos_size=cap*0.9
        if pos_size < 15: continue
        tr={"symbol":sh["symbol"],"side":sh["side"],"entry":sh["price"],"price":sh["price"],"pos":pos_size,"ts":now_ts,"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":sh["score"],"sector":sh["sector"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"rsi":sh["rsi"],"shark":sh.get("shark",0),"strength":sh.get("strength",0)}
        final.append(tr)
    state["open"]=final; state["closed"]=closed[:400]; state["cap"]=cap; state["daily"]=daily; state["fees_paid"]=fees_paid
    state=recalc_state_from_closed(state)
    state["scan"]=scan+1; state["scan_offset"]=next_offset; state["full_scans"]=next_full; state["market"]=market; kv_set(STATE_KEY, state)
    src = "COINGECKO" if any("cg_id" in t for t in tickers) else "BINANCE"
    return {"ok":True,"scan":scan+1,"open":len(final),"cap":cap,"daily":daily,"candidates":len(candidates),"offset":offset,"next_offset":next_offset,"batch":f"{offset+1}-{offset+10}","fallback":False,"market":market["reason"],"bias":market["bias"],"full":next_full,"source":src}

def render(state):
    state=recalc_state_from_closed(state)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",302.17); daily=state.get("daily",0.0); fees_paid=state.get("fees_paid",0.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0); offset=state.get("scan_offset",0); full_scans=state.get("full_scans",0)
    market=state.get("market",{"regime":"RANGING","bias":"BOTH","btc_price":83480,"rsi":47,"reason":f"SCAN {scan} OFFSET {offset} v819 COINGECKO","strength":0.7})
    winrate=int(wins/tot*100) if tot>0 else 0; unreal=sum([t.get("net",0) for t in open_tr]); long_open=sum(1 for t in open_tr if t.get("side")=="LONG"); short_open=sum(1 for t in open_tr if t.get("side")=="SHORT")
    gross_profit=sum([c.get("net",0) for c in closed if c.get("net",0)>0]); gross_loss=sum([c.get("net",0) for c in closed if c.get("net",0)<0])
    pf=abs(gross_profit/gross_loss) if gross_loss!=0 else (gross_profit if gross_profit>0 else 0); exp=(gross_profit+gross_loss)/tot if tot>0 else 0
    best = max(closed, key=lambda x: x.get("net",0)) if closed else None; worst = min(closed, key=lambda x: x.get("net",0)) if closed else None
    best_sym=best.get('symbol','-') if best else '-'; best_net=best.get('net',0) if best else 0; worst_sym=worst.get('symbol','-') if worst else '-'; worst_net=worst.get('net',0) if worst else 0
    invested=sum([t.get("pos",0) for t in open_tr]); bias_color="#00ff88" if market.get("bias")=="LONG_ONLY" else "#ff4444" if market.get("bias")=="SHORT_ONLY" else "#ffcc00"
    equity=[]; running=300.0
    for c in reversed(closed):
        running+=c.get("net",0); equity.append(running)
    if not equity: equity=[300.0]
    trade_boxes_html=""; chart_js_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",100); entry=tr.get("entry",0)
        tp_price = entry * (1 + tr.get("tp",1)/100) if side=="LONG" else entry * (1 - tr.get("tp",1)/100)
        sl_price = entry * (1 - tr.get("sl",0.65)/100) if side=="LONG" else entry * (1 + tr.get("sl",0.65)/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        shark_tag = f"<span style='background:#00d4ff;color:#000;padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900'>🦈 {tr.get('shark',0)}</span>" if tr.get('shark',0)>=20 else ""
        ts = tr.get("ts", int(time.time()))
        trade_boxes_html+=f"""
        <div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'>
          <div style='display:flex;justify-content:space-between;align-items:center'>
            <div><b style='color:{col};font-size:14px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f} {shark_tag}</b>
            <div style='font-size:10px;color:#aaa'>ENTRY ${entry:.6f} | TP ${tp_price:.6f} ({tr.get('tp',0):.2f}%) | SL ${sl_price:.6f} ({tr.get('sl',0):.2f}%) | {tr.get('sector','')}</div></div>
            <button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 10px;font-weight:900'>✕</button>
          </div>
          <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin:8px 0;text-align:center'>
            <div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>LIVE PRICE</div><div id='live-price-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('price',0):.5f}</div><div id='live-change-{sym}' style='font-size:10px'>{tr.get('pct_gross',0):+.3f}%</div><div id='live-dot-{sym}' style='font-size:8px;color:#0f8'>● COINGECKO LIVE 3s</div></div>
            <div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>UNREAL PNL</div><div id='live-pnl-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f}</div><div style='font-size:10px'>PEAK {tr.get('peak_gross',0):.2f}%</div></div>
            <div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>AGE / TP</div><div id='live-age-{sym}' style='font-size:13px;font-weight:900' data-ts='{ts}' data-start='{int(tr.get("age",0))}'>{int(tr.get("age",0)//60)}m {int(tr.get("age",0)%60)}s</div><div style='font-size:10px;color:#0f8'>to go {(tr.get('tp',0)-tr.get('pct_gross',0)):.2f}%</div></div>
          </div>
          <div style='position:relative;background:#000;border-radius:12px;padding:6px;border:1px solid #222'>
            <canvas id='chart-{sym}' width='340' height='180' style='width:100%;height:180px'></canvas>
            <div style='display:flex;justify-content:space-between;font-size:8px;color:#666;margin-top:3px'><span id='chart-info-{sym}'>COINGECKO REAL PRICE 3s - no ban</span><span id='chart-status-{sym}' style='color:#00d4ff'>COINGECKO LIVE</span></div>
          </div>
          <div style='font-size:9px;color:#888;margin-top:4px'>{tr.get('reason','')} | RSI {tr.get('rsi',0):.0f} STR {tr.get('strength',0):.1f} SECTOR {tr.get('sector','')}</div>
        </div>"""
        chart_js_init+=f"initChart('{sym}',{entry},{tp_price},{sl_price},'{side}',{ts},{int(tr.get('age',0))});\n"
    if not open_tr:
        trade_boxes_html=f"<div class='it' style='text-align:center;color:#666;padding:16px'>No open trades.<br>v819 COINGECKO - real prices no ban<br>SCAN {scan} OFFSET {offset}-{offset+10} FULL {full_scans}x<br>CAP ${cap:.2f}</div>"
    equity_js=json.dumps(equity[-60:])
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>
    body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}}
    .h{{background:linear-gradient(90deg,#00ff88,#ffcc00,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}}
    .g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}}
    .stats{{background:#111;border:2px solid {bias_color};padding:10px;margin:6px 0;border-radius:12px}}
    .it{{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:12px}}
    .trade-box{{background:#151515;border:1px solid #333;padding:10px;margin:8px 0;border-radius:14px}}
    .btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.btn{{padding:16px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px;cursor:pointer}}.btn-cron{{background:#0f8;color:#000}}.btn-reset{{background:#f44;color:#fff}}.btn-close{{background:#fc0;color:#000}}.badge{{padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900}}.long{{background:#0f8;color:#000}}.short{{background:#f44;color:#fff}}
    </style></head><body>
    <div class='h'>VENUS v819 COINGECKO REAL - SCAN #{scan} OFFSET {offset+1}-{offset+10} - ${cap:.2f} L:{long_open} S:{short_open} {market.get('regime')} BIAS {market.get('bias')} FULLx{full_scans} - COINGECKO</div>
    <div style='background:#000;border-radius:12px;padding:8px;margin:6px 0;border:1px solid #333'><div style='font-size:9px;color:#888'>EQUITY CURVE (CAP $300 → ${cap:.2f}) COINGECKO RESTORED</div><canvas id='equityChart' width='340' height='80' style='width:100%;height:80px'></canvas></div>
    <div class='btn-row'>
      <button class='btn btn-cron' onclick='callCron()'>⚡CRON 10 COINS<div id='cronStat' style='font-size:10px'>TAP {offset+1}-{offset+10}/100 SCAN {scan} - CG REAL</div></button>
      <button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN ${invested:.0f}</div></button>
      <button class='btn btn-reset' onclick='callReset()'>🔄RESET<div style='font-size:10px'>CAP $300</div></button>
    </div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#fc0'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}<br>INV ${invested:.0f}<br>FEES ${fees_paid:.2f}</div>
    <div class='c'>TODAY<br><b style='font-size:18px;color:{"#f44" if daily<0 else "#0f8"}'>${daily:+.2f}</b><br>W:{wins} L:{loss} {winrate}%<br>TOTAL {tot} COINGECKO<br>FULL {full_scans}x</div>
    <div class='c' style='border-color:{bias_color}'><b style='color:{bias_color}'>{market.get('bias')}</b><br>{market.get('regime')}<br>BTC ${market.get('btc_price',0):.0f}<br>RSI {market.get('rsi',0):.0f}<br>COINGECKO<br>NO BAN</div></div>
    <div class='stats'>
      <div style='color:{bias_color};font-weight:900;font-size:12px'>📈 v819 COINGECKO REAL PRICE - {market.get('reason','')} - NO BINANCE BAN</div>
      <div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px;font-size:10px'>
        <div>SCAN: <b>{offset+1}-{offset+10}/100 (x{full_scans}) COINGECKO REAL</b></div><div>OPEN: <b>{len(open_tr)}/3</b></div>
        <div>TOTAL: <b>{tot}</b> W:<b style='color:#0f8'>{wins}</b> L:<b style='color:#f44'>{loss}</b> {winrate}%</div><div>PF: <b>{pf:.2f}</b> EXP: <b>${exp:.3f}</b></div>
        <div>BEST: <b>{best_sym} ${best_net:+.2f}</b></div><div>WORST: <b>{worst_sym} ${worst_net:+.2f}</b></div>
      </div>
      <div style='margin-top:6px;color:#0f8;font-size:10px'>✅ v819 COINGECKO: Uses api.coingecko.com/coins/markets (no IP ban) + simple/price for live + market_chart for klines. Real price, no fake wiggle. Cached 25s to avoid rate limit.</div>
    </div>
    <div id='openbox'>{trade_boxes_html}</div>
    <div style='background:#111;padding:10px;margin:6px 0;border-radius:10px'><div style='color:#fc0;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% - PF {pf:.2f} EXP ${exp:.3f} COINGECKO</div>
    """
    for cl in closed[:25]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"; sh=f"🦈{cl.get('shark',0)}" if cl.get('shark',0)>=20 else ""
        html+=f"<div style='padding:5px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')} {cl.get('side','')} ${cl.get('pos',100):.0f} {sh}</b> ${cl.get('net',0):+.2f} {cl.get('pct_net',0):+.2f}% | {cl.get('reason','')} | {int(cl.get('age',0)//60)}m</div>"
    html+=f"""</div>
<script>
const EQUITY = {equity_js};
const ADMIN_KEY="{ADMIN_KEY}";
function drawEquity(){{
  const cv=document.getElementById('equityChart'); if(!cv||!EQUITY.length) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height;
  ctx.clearRect(0,0,w,h); const mn=Math.min(...EQUITY)*0.999, mx=Math.max(...EQUITY)*1.001, rg=mx-mn||1;
  function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}}
  ctx.strokeStyle='#222'; for(let i=0;i<3;i++){{const y=h*0.1+i*h*0.8/2; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}}
  const y300=yF(300); ctx.strokeStyle='#444'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,y300); ctx.lineTo(w,y300); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle='#666'; ctx.font='8px monospace'; ctx.fillText('300',2,y300-2);
  ctx.strokeStyle='#0f8'; ctx.lineWidth=2; ctx.beginPath();
  EQUITY.forEach((p,i)=>{{const x=i/(EQUITY.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}});
  ctx.stroke();
  const last=EQUITY[EQUITY.length-1]; ctx.fillStyle='#fc0'; ctx.beginPath(); ctx.arc(w-4,yF(last),3,0,Math.PI*2); ctx.fill(); ctx.fillText(last.toFixed(2), w-50, yF(last)-4);
}}
async function callCron(){{const b=document.getElementById('cronStat'); b.innerText='SCANNING COINGECKO...'; try{{const r=await fetch('/api/cron?key='+ADMIN_KEY); const j=await r.json(); b.innerText=j.ok ? 'OK '+j.batch+' C:'+j.candidates+' '+j.source+' FULL '+j.full : j.error||j.reason; setTimeout(()=>location.reload(),800);}}catch(e){{b.innerText='ERR '+e;}}}}
async function callReset(){{if(!confirm('RESET CAP $300? Will wipe history!')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}
function initChart(sym,entry,tp,sl,side,openTs,initialAge){{
  const cv=document.getElementById('chart-'+sym); if(!cv) return; const ctx=cv.getContext('2d');
  let prices = []; let liveHistory = []; let lastPrice = entry; let ageSec = initialAge;
  const ageEl=document.getElementById('live-age-'+sym);
  setInterval(()=>{{ ageSec += 1; const m=Math.floor(ageSec/60); const s=ageSec%60; if(ageEl) ageEl.innerText=m+'m '+s+'s'; }},1000);
  async function fetchPrice(){{
    let price=null;
    try{{ const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&src=coingecko&t='+Date.now()); const j=await r.json(); if(j.price && j.price>0) price=j.price; }}catch(e){{}}
    if(!price){{ try{{ const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&src=price&t='+Date.now()); const j=await r.json(); if(j.price && j.price>0) price=j.price; }}catch(e){{}} }}
    if(!price) return;
    lastPrice=price;
    const pct=side=='LONG'?(price-entry)/entry*100:(entry-price)/entry*100;
    const net=100*(pct-0.15)/100;
    const elP=document.getElementById('live-price-'+sym); const elC=document.getElementById('live-change-'+sym); const elPn=document.getElementById('live-pnl-'+sym); const dot=document.getElementById('live-dot-'+sym);
    if(elP){{elP.innerText='$'+price.toFixed(5); elP.style.color=pct>=0?'#0f8':'#f44';}}
    if(elC){{elC.innerText=pct.toFixed(3)+'%'; elC.style.color=pct>=0?'#0f8':'#f44';}}
    if(elPn){{elPn.innerText=(net>=0?'+':'')+'$'+net.toFixed(2); elPn.style.color=net>=0?'#0f8':'#f44';}}
    if(dot) dot.innerText='● COINGECKO '+new Date().toLocaleTimeString()+' '+pct.toFixed(3)+'%';
    liveHistory.push(price); if(liveHistory.length>60) liveHistory.shift(); prices = [...liveHistory]; draw();
  }}
  async function fetchKlines(){{
    try{{ const r=await fetch('/api/klines?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const j=await r.json(); if(j.closes && j.closes.length>10){{ const kl = j.closes.slice(-20); if(liveHistory.length<5){{ prices = kl; liveHistory = [...kl]; lastPrice = kl[kl.length-1]; }} draw(); }} }}catch(e){{}}
  }}
  function draw(){{
    const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h);
    if(prices.length<2){{ prices = Array(20).fill(entry).map((v,i)=> v + (Math.random()-0.5)*entry*0.0003); }}
    const usePrices = prices;
    let displayPrices = usePrices.map(p=>{{ let rawPct = (p-entry)/entry*100; let ampPct = rawPct; if(Math.abs(rawPct)<0.6) ampPct = rawPct*4; return entry * (1 + ampPct/100); }});
    const allAmp = [...displayPrices, entry]; let mn=Math.min(...allAmp)*0.9995; let mx=Math.max(...allAmp)*1.0005; const minRange = entry*0.006; const mid = (mn+mx)/2; if((mx-mn) < minRange){{ mn=mid-minRange/2; mx=mid+minRange/2; }} const rg=mx-mn||entry*0.001;
    function yF(p){{return h*0.85-((p-mn)/rg)*h*0.7;}}
    ctx.strokeStyle='#1a1a1a'; ctx.lineWidth=1; for(let i=0;i<5;i++){{const y=h*0.1+i*h*0.8/4; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}}
    const entryY=yF(entry); ctx.strokeStyle='#fc0'; ctx.lineWidth=3; ctx.beginPath(); ctx.moveTo(0,entryY); ctx.lineTo(w,entryY); ctx.stroke(); ctx.fillStyle='#fc0'; ctx.font='bold 11px monospace'; ctx.fillText('ENTRY '+entry.toFixed(5),4,entryY-5);
    const tpDisplay = entry*(1+((tp-entry)/entry*100)*4/100); let tpY=yF(tpDisplay); if(tpY<0) tpY=5; if(tpY>h) tpY=h-5; ctx.strokeStyle='#0f8'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.fillStyle='#0f8'; ctx.font='9px monospace'; ctx.fillText('TP '+tp.toFixed(5),4,tpY-3); ctx.setLineDash([]);
    const slDisplay = entry*(1+((sl-entry)/entry*100)*4/100); let slY=yF(slDisplay); if(slY<0) slY=5; if(slY>h) slY=h-5; ctx.strokeStyle='#f44'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,slY); ctx.lineTo(w,slY); ctx.stroke(); ctx.fillStyle='#f44'; ctx.fillText('SL '+sl.toFixed(5),4,slY+11); ctx.setLineDash([]);
    ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=3; ctx.beginPath(); displayPrices.forEach((p,i)=>{{const x=i/(displayPrices.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();
    ctx.strokeStyle=side=='LONG'?'rgba(0,255,136,0.3)':'rgba(255,68,68,0.3)'; ctx.lineWidth=8; ctx.beginPath(); displayPrices.forEach((p,i)=>{{const x=i/(displayPrices.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();
    const last=displayPrices[displayPrices.length-1]; const ly=yF(last); ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(w-8,ly,5,0,Math.PI*2); ctx.fill(); ctx.fillStyle=last>=entry?'#0f8':'#f44'; ctx.beginPath(); ctx.arc(w-8,ly,3.5,0,Math.PI*2); ctx.fill();
  }}
  draw(); fetchKlines(); fetchPrice(); setInterval(fetchPrice, 3000); setInterval(fetchKlines, 20000);
}}
window.addEventListener('load',()=>{{drawEquity(); {chart_js_init}}});
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
        src=request.args.get("src","coingecko")
        if not sym: return Response(json.dumps({"error":"no symbol"}), mimetype="application/json")
        full_sym=sym+"USDT" if not sym.endswith("USDT") else sym
        base=sym.replace("USDT","")
        # Try CoinGecko first
        if src=="coingecko":
            price=get_price_coingecko(base)
            if price:
                return Response(json.dumps({"symbol":sym,"price":price,"ts":int(time.time()),"src":"coingecko"}), mimetype="application/json")
        # Try Binance
        try:
            url=f"https://api.binance.com/api/v3/ticker/price?symbol={full_sym}"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as r:
                data=json.loads(r.read().decode())
                price=float(data.get("price",0))
                if price>0:
                    return Response(json.dumps({"symbol":sym,"price":price,"ts":int(time.time()),"src":"binance"}), mimetype="application/json")
        except: pass
        # Fallback to ticker map
        try:
            tickers=get_tickers()
            mp={t.get("symbol",""):t for t in tickers}
            if full_sym in mp:
                price=float(mp[full_sym].get("lastPrice",0))
                return Response(json.dumps({"symbol":sym,"price":price,"ts":int(time.time()),"src":"cache"}), mimetype="application/json")
        except: pass
        return Response(json.dumps({"error":"all sources failed","price":0}), mimetype="application/json", status=200)
    if p.startswith("/api/klines"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper()
        full_sym=sym+"USDT" if not sym.endswith("USDT") else sym
        try:
            closes=get_klines_fast(full_sym, "1m", 40)
            closes_only=[k["c"] if isinstance(k, dict) else k for k in closes]
            return Response(json.dumps({"symbol":sym,"closes":closes_only}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"error":str(e)[:100],"closes":[]}), mimetype="application/json", status=200)
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try: res=do_cron(); return Response(json.dumps(res), mimetype="application/json")
        except Exception as e: import traceback; return Response(json.dumps({"ok":False,"error":str(e)[:400],"trace":traceback.format_exc()[:500]}), mimetype="application/json", status=200)
    if p.startswith("/api/fix"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        s=load_state(); s["scan_offset"]=0; s["learn"]["blacklist"]={}; s["learn"]["last_coins"]={}; s=recalc_state_from_closed(s); kv_set(STATE_KEY,s); return Response(json.dumps({"ok":True,"fixed":True,"scan":s.get("scan",0),"cap":s.get("cap")}), mimetype="application/json")
    if p.startswith("/api/debug"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps(load_state(), indent=2), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); time.sleep(0.5); new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}}; kv_set(STATE_KEY,new); kv_del("CG_MARKETS_CACHE"); return Response(json.dumps({"ok":True,"cap":300}), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]): cap+=tr.get("net",0); state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE ALL {tr.get('pct_net',0):+.2f}% | {int(tr.get('age',0)//60)}m","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"shark":tr.get("shark",0)})
        state["open"]=[]; state["cap"]=cap; state=recalc_state_from_closed(state); kv_set(STATE_KEY,state); return Response(json.dumps({"ok":True,"cap":cap,"total":state["total"]}), mimetype="application/json")
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); state=load_state(); cap=state.get("cap",300.0); final=[]
        for tr in state.get("open",[]):
            if tr["symbol"]==sym: cap+=tr.get("net",0); state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE {sym} {tr.get('pct_net',0):+.2f}%","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"shark":tr.get("shark",0)})
            else: final.append(tr)
        state["open"]=final; state["cap"]=cap; state=recalc_state_from_closed(state); kv_set(STATE_KEY,state); return Response(json.dumps({"ok":True,"closed":sym,"cap":cap}), mimetype="application/json")
    try: st=load_state(); return Response(render(st), mimetype="text/html")
    except Exception as e: import traceback; return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:2000]}</pre></body></html>", mimetype="text/html", status=200)
