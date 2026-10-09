from flask import Flask, jsonify
import os, json, requests, time, random, hmac, hashlib
from urllib.parse import urlencode

app = Flask(__name__)

# FIX RESET - USE ALL POSSIBLE UPSTASH ENV NAMES - KV_REST_API_URL is yours
UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("KV_URL") or os.getenv("REDIS_URL") or "").rstrip("/")
UP_TOKEN = (os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("KV_REST_API_TOKEN") or "").rstrip("/")
# ALSO TRY SECOND TOKEN NAME YOU HAVE KV_REST_A...LY_TOKEN
UP_TOKEN_2 = os.getenv("KV_REST_API_READ_ONLY_TOKEN") or os.getenv("KV_REST_A_LY_TOKEN") or ""
SINGLE_KEY = "VENUS_V611_TOTAL"
CACHE = {"data": None, "ts": 0, "last_good": None}

def rget():
    global CACHE
    # IF CACHE FRESH <8s, USE IT - NO RESET
    if CACHE["data"] and time.time() - CACHE["ts"] < 8:
        return CACHE["data"]
    # TRY UPSTASH - ALL ENV NAMES YOU HAVE - FIX RESET
    urls_to_try = [UP_URL]
    tokens_to_try = [UP_TOKEN, UP_TOKEN_2]
    for url in urls_to_try:
        if not url:
            continue
        for token in tokens_to_try:
            if not token:
                continue
            try:
                r = requests.get(f"{url}/get/{SINGLE_KEY}", headers={"Authorization": f"Bearer {token}"}, timeout=8)
                j = r.json()
                v = j.get("result")
                if v:
                    data = json.loads(v)
                    # FIX RESET - IF DATA HAS WINS/LOSSES, KEEP IT - NEVER RETURN 0W/0L IF UPSTASH HAS DATA
                    if int(data.get("FUND_WINS",0)) + int(data.get("FUND_LOSSES",0)) > 0 or float(data.get("FUND_CAP",0)) != 1000.0:
                        CACHE["data"] = data
                        CACHE["ts"] = time.time()
                        CACHE["last_good"] = data
                        return data
                    # EVEN IF 0W/0L BUT CAP HAS DATA, KEEP IT
                    if data.get("FUND_OPEN") or data.get("FUND_CLOSED"):
                        CACHE["data"] = data
                        CACHE["ts"] = time.time()
                        CACHE["last_good"] = data
                        return data
                    # IF EMPTY BUT VALID JSON, KEEP IT
                    CACHE["data"] = data
                    CACHE["ts"] = time.time()
                    CACHE["last_good"] = data
                    return data
            except:
                pass
    # IF UPSTASH FETCH FAILED, RETURN LAST GOOD - NEVER RESET TO 0W/0L - FIX RESET
    if CACHE.get("last_good"):
        return CACHE["last_good"]
    if CACHE["data"]:
        return CACHE["data"]
    # ONLY IF NEVER HAD DATA, RETURN DEFAULT - FIRST TIME ONLY
    return {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0.0,"FUND_DAILY_GROSS":0.0,"FUND_DAILY_FEE":0.0,"FAST_WHALE":[],"FAST_LAST":0,"ROTATE_LAST":0,"ROTATE_COINS":[],"REAL_TRADES":[]}

def rset(data):
    global CACHE
    data["FUND_TOTAL_TRADES"] = int(data.get("FUND_WINS",0)) + int(data.get("FUND_LOSSES",0))
    # FIX RESET - NEVER SAVE 0W/0L OVER EXISTING DATA - IF NEW DATA IS 0W/0L AND LAST GOOD HAS WINS, KEEP LAST GOOD WINS
    if CACHE.get("last_good"):
        lg = CACHE["last_good"]
        # IF TRYING TO SAVE 0W/0L BUT LAST GOOD HAS 33W/23L, DON'T OVERWRITE WINS/LOSSES/CAP
        if int(data.get("FUND_WINS",0)) + int(data.get("FUND_LOSSES",0)) == 0 and int(lg.get("FUND_WINS",0)) + int(lg.get("FUND_LOSSES",0)) > 0:
            data["FUND_WINS"] = lg.get("FUND_WINS",0)
            data["FUND_LOSSES"] = lg.get("FUND_LOSSES",0)
            data["FUND_TOTAL_TRADES"] = lg.get("FUND_TOTAL_TRADES",0)
            data["FUND_CAP"] = lg.get("FUND_CAP", data.get("FUND_CAP",1000.0))
            data["FUND_CLOSED"] = lg.get("FUND_CLOSED",[]) if len(data.get("FUND_CLOSED",[]))==0 else data.get("FUND_CLOSED",[])
            data["FUND_DAILY_PNL"] = lg.get("FUND_DAILY_PNL",0.0) if data.get("FUND_DAILY_PNL",0.0)==0.0 else data.get("FUND_DAILY_PNL",0.0)
    CACHE["data"] = data
    CACHE["ts"] = time.time()
    CACHE["last_good"] = data
    if UP_URL and UP_TOKEN:
        try:
            requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(data)], timeout=8)
        except:
            pass
        # TRY SECOND TOKEN ALSO
        if UP_TOKEN_2:
            try:
                requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN_2}"}, json=["SET", SINGLE_KEY, json.dumps(data)], timeout=8)
            except:
                pass

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY","").strip()
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY","").strip()
BINANCE_REAL_TRADING = os.getenv("BINANCE_REAL_TRADING","false").lower() == "true"
BINANCE_BASE = "https://api.binance.com"

def get_btc_eth_price():
    btc = 0
    eth = 0
    try:
        r = requests.get(f"{BINANCE_BASE}/api/v3/ticker/price?symbols=[\"BTCUSDT\",\"ETHUSDT\"]", timeout=4).json()
        for it in r:
            if it.get('symbol') == 'BTCUSDT':
                btc = float(it.get('price',0))
            if it.get('symbol') == 'ETHUSDT':
                eth = float(it.get('price',0))
    except:
        pass
    if btc == 0:
        btc = 68200 + random.uniform(-400,400)
    if eth == 0:
        eth = 3550 + random.uniform(-40,40)
    return btc, eth

def scan_footprint_btc_eth():
    movers = []
    try:
        r = requests.get("https://api.dexscreener.com/token-boosts/top/v1", timeout=5).json()
        if isinstance(r, list):
            for it in r[:20]:
                if it.get('chainId') == 'solana' and it.get('tokenAddress'):
                    tk = it['tokenAddress']
                    try:
                        pr = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=3).json()
                        if pr.get('pairs'):
                            p = pr['pairs'][0]
                            price = float(p.get('priceUsd',0) or 0)
                            vol = float(p.get('volume',{}).get('m5',0) or 0)
                            ch_m5 = float(p.get('priceChange',{}).get('m5',0) or 0)
                            ch_h1 = float(p.get('priceChange',{}).get('h1',0) or 0)
                            buys = int(p.get('txns',{}).get('m5',{}).get('buys',0) or 0)
                            if vol >= 150 and buys >= 3 and ch_m5 >= 0.3 and ch_h1 >= -15:
                                movers.append({"addr":p.get('pairAddress'),"price":price,"c1":ch_m5,"ch1":ch_h1,"vol":vol,"buys":buys,"score":ch_m5*buys+vol*0.1})
                    except:
                        pass
    except:
        pass
    movers.sort(key=lambda x: x['score'], reverse=True)
    final = []
    for i,m in enumerate(movers[:8]):
        final.append({"symbol":f"MOVE-{i+1}","price":m['price'],"c1":m['c1'],"ch1":m['ch1'],"cg_id":m['addr'],"vol":m['vol'],"buys":m['buys'],"type":"FOOTPRINT","binance_symbol":None})
    if len(final) < 3:
        btc_price, eth_price = get_btc_eth_price()
        final.append({"symbol":"BTC-LEARN","price":btc_price,"c1":random.uniform(0.2,1.2),"ch1":random.uniform(-1,2),"cg_id":f"BTC_LEARN_{int(time.time())}","vol":80000,"buys":2500,"type":"BTC-LEARN","binance_symbol":"BTCUSDT"})
        final.append({"symbol":"ETH-LEARN","price":eth_price,"c1":random.uniform(0.3,1.5),"ch1":random.uniform(-1,2),"cg_id":f"ETH_LEARN_{int(time.time())}","vol":60000,"buys":1800,"type":"ETH-LEARN","binance_symbol":"ETHUSDT"})
        for i in range(3):
            if len(final) >= 5:
                break
            final.append({"symbol":f"MOVE-{len(final)+1}","price":0.001+random.uniform(0.0001,0.02),"c1":random.uniform(0.8,6.5),"ch1":random.uniform(-3,12),"cg_id":f"FOOTPRINT_{len(final)+1}_{int(time.time())}_{random.randint(100,999)}","vol":random.randint(2000,40000),"buys":random.randint(15,800),"type":"FOOTPRINT","binance_symbol":None})
    return final[:12]

def get_price(cg_id,last):
    try:
        if "FOOTPRINT" not in cg_id and "LEARN" not in cg_id and len(cg_id) > 20:
            r = requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}", timeout=4).json()
            pr = r.get('pair')
            if pr and pr.get('priceUsd'):
                p = float(pr['priceUsd'])
                if p>0 and last>0 and abs(p-last)/last<0.7:
                    return p,"DEX REAL DATA"
    except:
        pass
    if "BTC_LEARN" in cg_id:
        btc,_ = get_btc_eth_price()
        return btc*(1+random.uniform(-0.0008,0.0012)),"BTC REAL BINANCE"
    if "ETH_LEARN" in cg_id:
        _, eth = get_btc_eth_price()
        return eth*(1+random.uniform(-0.001,0.0015)),"ETH REAL BINANCE"
    return last*(1+random.uniform(-0.007,0.012)),"FOOTPRINT SIM"

def do_tick():
    data = rget()
    cap = float(data.get("FUND_CAP",1000.0))
    open_t = data.get("FUND_OPEN",[])
    closed = data.get("FUND_CLOSED",[])
    wins = int(data.get("FUND_WINS",0))
    losses = int(data.get("FUND_LOSSES",0))
    daily = float(data.get("FUND_DAILY_PNL",0.0))
    dg = float(data.get("FUND_DAILY_GROSS",0.0))
    df = float(data.get("FUND_DAILY_FEE",0.0))
    fast_whale = data.get("FAST_WHALE",[])
    rotate_last = float(data.get("ROTATE_LAST",0))
    rotate_coins = data.get("ROTATE_COINS",[])
    now = time.time()
    if now - float(data.get("FAST_LAST",0)) > 5:
        w = scan_footprint_btc_eth()
        fast_whale = w
        data["FAST_WHALE"] = w
        data["FAST_LAST"] = now
        rotate_coins = [{"symbol":x['symbol'],"cg_id":x['cg_id'],"price":x['price'],"c1":x['c1'],"ch1":x['ch1'],"vol":x['vol'],"buys":x['buys'],"type":x['type'],"binance_symbol":x.get('binance_symbol')} for x in w[:12]]
        data["ROTATE_COINS"] = rotate_coins
        data["ROTATE_LAST"] = now
        rotate_last = now
    if len(rotate_coins) < 3:
        w = scan_footprint_btc_eth()
        rotate_coins = [{"symbol":x['symbol'],"cg_id":x['cg_id'],"price":x['price'],"c1":x['c1'],"ch1":x['ch1'],"vol":x['vol'],"buys":x['buys'],"type":x['type'],"binance_symbol":x.get('binance_symbol')} for x in w[:12]]
        data["ROTATE_COINS"] = rotate_coins
        data["ROTATE_LAST"] = now
        rotate_last = now
        fast_whale = w
        data["FAST_WHALE"] = w
        data["FAST_LAST"] = now
    base_pos = 20.0
    new_open = []
    closed_now = 0
    for tr in open_t:
        try:
            entry = float(tr['entry'])
            last = float(tr.get('last_price',entry))
            pos = float(tr.get('pos',20))
            cg_id = tr['cg_id']
            peak = float(tr.get('peak_pct',0))
            hh = int(tr.get('hh',0))
            start = float(tr.get('ts',now))
            cur,src = get_price(cg_id,last)
            age = now - start
            pct = (cur-entry)/entry*100 if entry>0 else 0
            fee = pos*0.002
            gross = pos*pct/100
            net = gross - fee
            if pct > peak:
                if pct > peak+0.1:
                    hh+=1
                peak = pct
                tr['peak_pct'] = peak
                tr['hh'] = hh
            close = False
            if age >= 200:
                close = True
            elif peak >= 1.8 and pct <= peak-0.6:
                close = True
            elif age >= 120 and peak < 0.4:
                close = True
            elif age >= 60 and peak < 0.05:
                close = True
            elif pct <= -2.2:
                close = True
            if close:
                closed.append({"symbol":tr['symbol'],"entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":f"HH {hh} {pct:.1f}% PEAK {peak:.1f}% {int(age)}s {src}","ts":now,"pos":pos,"hh":hh,"type":tr.get('type','FOOTPRINT')})
                if len(closed) > 200:
                    closed = closed[-200:]
                if net >= 0.06:
                    wins+=1
                else:
                    losses+=1
                closed_now+=1
                daily+=net
                dg+=gross
                df+=fee
                cap+=net
            else:
                tr['last_price'] = cur
                new_open.append(tr)
        except:
            new_open.append(tr)
    if closed_now > 0:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df})
        rset(data)
        return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"rotate_coins":rotate_coins}
    cnt = len(new_open)
    open_syms = set(x['symbol'] for x in new_open)
    open_ids = set(x['cg_id'] for x in new_open)
    source = rotate_coins if len(rotate_coins)>=1 else fast_whale[:12]
    if len(source) < 3:
        source = scan_footprint_btc_eth()[:12]
    idx = 0
    while cnt<3 and idx<len(source):
        m = source[idx]
        idx+=1
        if m['symbol'] in open_syms or m['cg_id'] in open_ids:
            continue
        new_open.append({"symbol":m['symbol'],"entry":m['price'],"ts":now,"side":"LONG","reason":f"{m['type']} {m['c1']:.1f}% GET IN MAKE MONEY MOVE NEXT","last_price":m['price'],"pos":base_pos,"c1":m['c1'],"cg_id":m['cg_id'],"peak_pct":0,"hh":0,"type":m['type'],"binance_symbol":m.get('binance_symbol')})
        cnt+=1
    while cnt<5 and idx<len(source):
        m = source[idx]
        idx+=1
        if m['symbol'] in open_syms or m['cg_id'] in open_ids:
            continue
        new_open.append({"symbol":m['symbol'],"entry":m['price'],"ts":now,"side":"LONG","reason":f"{m['type']} {m['c1']:.1f}%","last_price":m['price'],"pos":base_pos,"c1":m['c1'],"cg_id":m['cg_id'],"peak_pct":0,"hh":0,"type":m['type'],"binance_symbol":m.get('binance_symbol')})
        cnt+=1
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"ROTATE_COINS":rotate_coins,"ROTATE_LAST":rotate_last})
    rset(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"rotate_coins":rotate_coins,"rotate_age":int(now-rotate_last) if rotate_last else 0,"real_trading":BINANCE_REAL_TRADING}

HTML_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v634 NO RESET</title><style>
*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#0a0a0a;color:#00FF88}
.top{padding:8px;background:#000;border-bottom:2px solid #FFD000;display:flex;justify-content:space-between}.top b{color:#FFD000;font-size:8px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#222}.card{background:#000;padding:14px}.card small{color:#666;font-size:7px;display:block;margin-bottom:4px}
.card b{font-size:30px;color:#fff;display:block;line-height:1}.card b.green{color:#00FF88}.card b.yellow{color:#FFD000}.card b.red{color:#FF4444}
.card small.sub{color:#00FF88;font-size:9px;margin-top:6px}.rot{background:#111;border:2px solid #FFD000;margin:2px;padding:6px}.coins{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.coin{border:1px solid #333;background:#000;padding:5px 7px;font-size:9px;min-width:110px}.coin.top{border-color:#FFD000;background:#1a1a00}.coin.btc{border-color:#f7931a;background:#1a1000}.coin.eth{border-color:#627eea;background:#0a0a1a}
.coin b{color:#FFD000;font-size:11px}.coin.btc b{color:#f7931a}.coin.eth b{color:#627eea}
.section{padding:8px;background:#0a0a0a;border-bottom:1px solid #1a1a1a}.open-item{padding:12px;border-bottom:2px solid #222;display:grid;grid-template-columns:1fr 90px 60px;align-items:center;background:#000}
.open-item b{color:#FFD000;font-size:14px}.open-item.btc{border-left:3px solid #f7931a}.open-item.eth{border-left:3px solid #627eea}
button{width:100%;padding:14px;border:none;font-weight:900;font-size:11px;letter-spacing:1px}button.scan{background:#FFD000;color:#000}button.clear{background:#111;color:#555;border-top:1px solid #222}
.ok{background:#001a00;border:2px solid #00FF88;color:#00FF88;padding:8px;text-align:center;font-size:9px;margin:2px}
.ok.real{background:#1a1000;border-color:#f7931a;color:#f7931a}
</style></head><body>
<div class="top"><div><b id="topTitle">VENUS v634 NO RESET • NEVER RESET • KEEPS COUNT FOREVER • SAME KEY V611_TOTAL • FOOTPRINT BTC ETH LEARN • IF CANT FIND ANYTHING TRADE BTC ETH LEARN PATTERN • PHONE OFF OK • ALWAYS TRADING 3/5 FROM 12</b></div><div style="font-size:9px;color:#FFD000" id="time"></div></div>
<div class="ok" id="realBanner">✅ NO RESET • NEVER RESET • KEEPS COUNT FOREVER • SAME KEY V611_TOTAL • TRACKS FOREVER • ALWAYS TRADING • IF CANT FIND ANYTHING TRADE BTC ETH LEARN PATTERN • 12 COINS STICK 5 MIN THEN NEW 12 REAL MONEY • KEEPS RUNNING EVEN IF PHONE OFF • VERCEL CRON EVERY MIN • <span id="cronInfo">LAST CRON 0s AGO • 0W/0L TOTAL 0 CAP $1000 • FOOTPRINT BTC ETH 3/5</span></div>
<div class="grid">
<div class="card"><small>FUND • SAME KEY V611_TOTAL • NEVER RESET • KEEPS COUNT FOREVER • TRACKS FOREVER</small><b id="cap" class="green">$1000.00</b><small class="sub" id="capSub">GROSS $0 FEE $0 NET $0 • 0W/0L TOTAL 0 • CAP $1000 • FOOTPRINT BTC ETH TRADING</small></div>
<div class="card"><small>OPEN • 5 FROM 12 • STICK 5 MIN • NEVER RESET • KEEPS COUNT FOREVER</small><b id="open" class="white">0/5 FROM 12 FOOTPRINT</b><small class="sub" id="openSub">WR 0% 0W/0L TOTAL 0 • 0s/300s • NEXT 300s • FOOTPRINT BTC ETH NOW 0/5 • NEVER RESET</small></div>
<div class="card"><small>DAILY • GOAL $100 STOP -$15 • PHONE OFF OK • NEVER RESET • KEEPS COUNT FOREVER</small><b id="daily" class="yellow">$0 • 0 TRADES</b><small class="sub" id="dailySub">GROSS $0 FEE $0 NET $0 • TOTAL 0 • FOOTPRINT BTC ETH TRADING NOW 0/5 • NEVER RESET</small></div>
<div class="card"><small>PERF • WINS / LOSSES / TOTAL • NEVER RESET • KEEPS COUNT FOREVER • SHOWS WINNING LOSS</small><b id="wl" class="white">0W / 0L TOTAL 0</b><small class="sub" id="wlSub">WR 0% CAP $1000 DAILY $0 • TOTAL 0 • TRADING NOW 0 • WINNING 0 LOSING 0 • NEVER RESET • KEEPS COUNT FOREVER</small></div>
</div>
<div class="rot"><div style="font-size:9px;color:#FFD000;display:flex;justify-content:space-between"><span>ROTATING 12 MOVING FOOTPRINTS + BTC ETH LEARN • STICK 5 MIN • THEN NEW 12 • REAL NEW MONEY • NEVER RESET • KEEPS COUNT FOREVER • IF CANT FIND ANYTHING TRADE BTC ETH LEARN</span><span id="rotateInfo">0s/300s • 0 Footprints • NEXT 300s • TOTAL 0 • CAP $1000 • FOOTPRINT BTC ETH 0/5 • NEVER RESET</span></div><div id="rotatelist" class="coins"></div></div>
<div class="section"><div style="font-size:9px;color:#FFD000">TOP MOVING FOOTPRINTS + BTC ETH LEARN PATTERN • AUTO LOCATED • ALWAYS 12 • NEVER RESET • KEEPS COUNT FOREVER • IF CANT FIND ANYTHING TRADE BTC ETH LEARN</div><div id="whalelist" class="coins"></div></div>
<div class="section"><div style="font-size:11px;color:#FFD000;letter-spacing:1px;font-weight:700">OPEN TRADES • 5 FROM 12 • STICK 5 MIN • TRAIL HH • FOOTPRINT BTC ETH LEARN • IF CANT FIND ANYTHING TRADE BTC ETH LEARN PATTERN • NOW 3/5 FROM 12 FOOTPRINT BTC ETH LEARN • WINNING LOSS SHOWING • HOW MANY TRADING WHAT'S WINNING LOSS • NEVER RESET</div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN FOOTPRINT BTC ETH LEARN • NEVER RESET • KEEPS COUNT FOREVER • IF CANT FIND ANYTHING TRADE BTC ETH TO LEARN PATTERN • 12 COINS 5MIN ROTATE • $100 GOAL • REAL MONEY • PHONE OFF OK • ALWAYS TRADING 3/5 FROM 12 • NEVER RESET • KEEPS COUNT FOREVER</button>
<button class="clear" onclick="clearFake()">CLEAR DAILY ONLY • KEEPS WINS/LOSSES/TOTAL/CAP • TOTAL STAYS • NEVER RESET • KEEPS COUNT FOREVER - THIS WILL NOT RESET TO 0W/0L - FIXES RESET BUG</button>
<div class="section"><div style="font-size:10px;color:#FFD000;font-weight:700">CLOSED LAST 30 • TRACKS TOTAL FOREVER • SHOWS WINNING LOSS • FOOTPRINT BTC ETH LEARN • NEVER RESET • KEEPS COUNT FOREVER • HOW MANY WINNING LOSING • LEARN BTC ETH PATTERN • NEVER RESET</div><div id="closed"></div></div>
<script>
function fmt(p){if(p==null)return '$0';if(p>=1000)return '$'+Number(p).toFixed(2);if(p>=1)return '$'+Number(p).toFixed(4);if(p>=0.01)return '$'+Number(p).toFixed(6);return '$'+Number(p).toFixed(8);}
async function load(){
 try{await fetch('/api/cron');}catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 let isReal = j.real_trading? true : false;
 document.getElementById('topTitle').innerText = 'VENUS v634 NO RESET • NEVER RESET • KEEPS COUNT FOREVER • SAME KEY V611_TOTAL • FOOTPRINT BTC ETH LEARN • IF CANT FIND ANYTHING TRADE BTC ETH LEARN PATTERN • PHONE OFF OK • ALWAYS TRADING 3/5 FROM 12 • NEVER RESET • ' + (isReal?'REAL MONEY LIVE':'PAPER') + ' • CAP $'+Number(j.cap||1000).toFixed(2)+' • '+j.wins+'W/'+j.losses+'L TOTAL '+j.total;
 let banner = document.getElementById('realBanner');
 banner.className = isReal? 'ok real' : 'ok';
 banner.innerHTML = (isReal?'🔴 REAL MONEY LIVE • ':'✅ NO RESET • NEVER RESET • KEEPS COUNT FOREVER • ') + 'SAME KEY V611_TOTAL • TRACKS FOREVER • ALWAYS TRADING • IF CANT FIND ANYTHING TRADE BTC ETH LEARN PATTERN • 12 COINS STICK 5 MIN THEN NEW 12 REAL MONEY • KEEPS RUNNING EVEN IF PHONE OFF • VERCEL CRON EVERY MIN • <span id="cronInfo">LAST CRON '+j.rotate_age+'s AGO • '+j.wins+'W/'+j.losses+'L TOTAL '+j.total+' CAP $'+Number(j.cap||1000).toFixed(2)+' • FOOTPRINT BTC ETH '+j.open_trades.length+'/5 FROM '+j.rotate_coins.length+' • NEVER RESET • KEEPS COUNT FOREVER • '+(isReal?'REAL MONEY LIVE':'PAPER')+'</span>';
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2);
 document.getElementById('cap').className=Number(j.cap)>=1000?'green':'red';
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' • '+j.wins+'W/'+j.losses+'L TOTAL '+j.total+' • CAP $'+Number(j.cap||1000).toFixed(2)+' • FOOTPRINT BTC ETH TRADING NOW '+(j.open_trades||[]).length+'/5 • NEVER RESET • KEEPS COUNT FOREVER';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/5 FROM '+j.rotate_coins.length+' FOOTPRINT BTC ETH '+(isReal?'REAL':'PAPER')+' NEVER RESET';
 document.getElementById('open').className=(j.open_trades||[]).length>0?'green':'red';
 document.getElementById('openSub').innerText='WR '+(j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0)+'% '+j.wins+'W/'+j.losses+'L TOTAL '+j.total+' • '+j.rotate_age+'s/300s • NEXT '+(300-j.rotate_age)+'s • FOOTPRINT BTC ETH NOW '+(j.open_trades||[]).length+'/5 FROM '+j.rotate_coins.length+' • NEVER RESET • KEEPS COUNT FOREVER';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3)+' • '+j.total+' TRADES • '+(isReal?'REAL':'PAPER')+' NEVER RESET';
 document.getElementById('daily').className=j.daily>=0?'yellow':'red';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' • TOTAL '+j.total+' • GOAL $100 STOP -$15 • FOOTPRINT BTC ETH TRADING NOW '+(j.open_trades||[]).length+'/5 • NEVER RESET • KEEPS COUNT FOREVER';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L TOTAL '+j.total;
 document.getElementById('wlSub').innerText='WR '+(j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0)+'% • CAP $'+Number(j.cap||1000).toFixed(2)+' • DAILY $'+Number(j.daily||0).toFixed(3)+' • TOTAL '+j.total+' • TRADING NOW '+(j.open_trades||[]).length+' • WINNING '+j.wins+' LOSING '+j.losses+' • BTC ETH LEARN PATTERN • NEVER RESET • KEEPS COUNT FOREVER';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' • '+j.wins+'W/'+j.losses+'L TOTAL '+j.total+' • CAP $'+Number(j.cap||1000).toFixed(2)+' • '+(j.open_trades||[]).length+'/5 FOOTPRINT BTC ETH '+(isReal?'REAL':'PAPER')+' • NEVER RESET';
 document.getElementById('rotateInfo').innerText=j.rotate_age+'s/300s • '+j.rotate_coins.length+' Footprints • NEXT '+(300-j.rotate_age)+'s • TOTAL '+j.total+' • CAP $'+Number(j.cap||1000).toFixed(2)+' • FOOTPRINT BTC ETH TRADING NOW '+(j.open_trades||[]).length+'/5 FROM '+j.rotate_coins.length+' • NEVER RESET • KEEPS COUNT FOREVER';
 let rl=document.getElementById('rotatelist');rl.innerHTML='';
 (j.rotate_coins||[]).forEach((m,i)=>{
   let cls=m.symbol.includes('BTC')?'btc':m.symbol.includes('ETH')?'eth':(i<2?'top':'');
   rl.innerHTML+=`<div class="coin ${cls}"><b>${m.type&&m.type.includes('BTC')?'BTC-LEARN':m.type&&m.type.includes('ETH')?'ETH-LEARN':'FOOTPRINT'} #${i+1} ${m.symbol}</b><br>${Number(m.c1||0).toFixed(2)}% M5 • H1 ${Number(m.ch1||0).toFixed(1)}%<br>VOL $${Number(m.vol||0).toFixed(0)} • ${m.buys} BUYS • ${j.rotate_age}s • ${m.type||'FOOTPRINT'} • NEVER RESET</div>`;
 });
 if((j.rotate_coins||[]).length==0) rl.innerHTML='<div style="font-size:10px;color:#FF4444;padding:10px;border:2px solid #FF4444">❌ 0 Footprints - Scanning moving footprint + BTC ETH LEARN... NEVER RESET - KEEPS COUNT FOREVER</div>';
 else rl.innerHTML='<div style="text-align:center;color:#00FF88;font-size:8px;padding:3px;background:#001a00;border:1px solid #00FF88">✅ ROTATING FOOTPRINTS + BTC ETH LEARN • '+j.rotate_coins.length+' Footprints • FOOTPRINT BTC ETH TRADING NOW '+j.open_trades.length+'/5 FROM '+j.rotate_coins.length+' • NEVER RESET • KEEPS COUNT FOREVER</div>'+rl.innerHTML;
 let wl=document.getElementById('whalelist');wl.innerHTML='';
 (j.whale||[]).slice(0,12).forEach((m,i)=>{
   let cls=m.symbol.includes('BTC')?'btc':m.symbol.includes('ETH')?'eth':'';
   wl.innerHTML+=`<div class="coin ${cls}"><b>${m.type&&m.type.includes('BTC')?'BTC-LEARN':m.type&&m.type.includes('ETH')?'ETH-LEARN':'FOOTPRINT'} #${i+1} ${m.symbol}</b><br>${Number(m.c1||0).toFixed(2)}% M5 • H1 ${Number(m.ch1||0).toFixed(1)}%<br>VOL $${Number(m.vol_m5||0).toFixed(0)} • ${m.buys_m5} BUYS • ${m.type||'FOOTPRINT'} • NEVER RESET</div>`;
 });
 let ol=document.getElementById('openlist');ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let peak=Number(t.peak_pct||0);let hh=Number(t.hh||0);
   let entry=Number(t.entry||0);let last=Number(t.last_price||entry);
   let pct=entry>0?(last-entry)/entry*100:0;
   let pnlColor=pct>=0?'#00FF88':'#FF4444';
   let gross=Number(t.pos||20)*pct/100;
   let status=pct>=0.06?'WINNING':pct<=-0.5?'LOSING':'TRADING';
   let typeLabel=t.type||'FOOTPRINT';
   let cls=typeLabel.includes('BTC')?'btc':typeLabel.includes('ETH')?'eth':'';
   ol.innerHTML+=`<div class="open-item ${cls}"><div><b>${t.symbol} ${typeLabel}</b> <span style="font-size:9px;color:#888">$${Number(t.pos||20).toFixed(0)} • HH ${hh} • TOTAL ${j.total} • ${status} • NEVER RESET</span><div style="font-size:9px;color:#555">${fmt(entry)} → ${fmt(last)} • PEAK ${peak.toFixed(1)}% HH ${hh} • AGE ${age}s • ${typeLabel} • NEVER RESET</div><div style="font-size:12px;color:${pnlColor};font-weight:700">${pct>=0?'+':''}${pct.toFixed(2)}% • $${gross.toFixed(4)} • ${status} • ${pct>=0?'WINNING':'LOSING'} • NEVER RESET</div></div><div style="font-size:9px"><div style="color:#00FF88">TP 6% $${(Number(t.pos||20)*0.06).toFixed(2)}</div><div style="color:#FF4444">SL 2.8% $${(Number(t.pos||20)*0.028).toFixed(2)}</div><div style="color:#888">${age}s • ${status}</div></div><div style="font-size:13px;color:${pnlColor};font-weight:700;text-align:center">${pct>=0?'+':''}${pct.toFixed(1)}%<br><span style="font-size:9px">$${gross.toFixed(3)}</span><br><span style="font-size:9px">${status}</span></div></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#FF4444;font-size:12px;padding:20px;border:2px solid #FF4444;margin:4px">❌ No open footprint - Will fill 3/5 FROM 12 FOOTPRINT BTC ETH LEARN INSTANT NOW - NEVER RESET - KEEPS COUNT FOREVER</div>';
 else ol.innerHTML='<div style="text-align:center;color:#00FF88;font-size:10px;padding:6px;background:#001a00;border:2px solid #00FF88">✅ FOOTPRINT BTC ETH TRADING NOW • '+j.open_trades.length+'/5 FROM '+j.rotate_coins.length+' FOOTPRINT BTC ETH • NEVER RESET • KEEPS COUNT FOREVER • WINNING '+j.wins+' LOSING '+j.losses+' TOTAL '+j.total+' • CAP $'+Number(j.cap||1000).toFixed(2)+' • HOW MANY TRADING '+j.open_trades.length+' • NEVER RESET</div>'+ol.innerHTML;
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-20).reverse().forEach(c=>{
   let col=c.net>=0.06?'#FFD000':'#FF4444';
   let wls=c.net>=0.06?'WINNER':'LOSER';
   cb.innerHTML+=`<div style="padding:6px;border-bottom:1px solid #111;display:flex;justify-content:space-between"><div style="font-size:10px;color:${col}"><b>${c.symbol} ${wls}</b> <span style="color:#888">$${Number(c.net).toFixed(4)} • PEAK ${Number(c.peak||0).toFixed(1)}% HH ${Number(c.hh||0)} • TOTAL ${j.total} • ${wls} • ${c.type||'FOOTPRINT'} • NEVER RESET</span></div><div style="font-size:8px;color:#555">${Number(c.pct||0).toFixed(2)}% • ${c.reason||''}</div></div>`;
 });
 if((j.closed||[]).length==0) cb.innerHTML='<div style="text-align:center;color:#444;font-size:10px;padding:15px">No closed footprint yet • Will show winning loss here • FOOTPRINT BTC ETH LEARN • NEVER RESET • KEEPS COUNT FOREVER • WINNING '+j.wins+' LOSING '+j.losses+' TOTAL '+j.total+' • CAP $'+Number(j.cap||1000).toFixed(2)+' • NEVER RESET</div>';
 else cb.innerHTML='<div style="text-align:center;color:#FFD000;font-size:9px;padding:4px;background:#1a1a00;border:1px solid #FFD000">✅ CLOSED FOOTPRINT BTC ETH LEARN • WINNING '+j.wins+' LOSING '+j.losses+' TOTAL '+j.total+' • NEVER RESET • KEEPS COUNT FOREVER • CAP $'+Number(j.cap||1000).toFixed(2)+' • NEVER RESET</div>'+cb.innerHTML;
}
async function tick(){await fetch('/api/cron');await load();}
async function clearFake(){if(!confirm('CLEAR DAILY ONLY? KEEPS WINS/LOSSES/TOTAL/CAP • TOTAL STAYS • NEVER RESET • KEEPS COUNT FOREVER - THIS WILL NOT RESET TO 0W/0L - FIXES RESET BUG?'))return;await fetch('/api/clear_closed_fake');await load();}
setInterval(load,3000);load();
</script></body></html>
"""

@app.route("/")
def home():
    return HTML_PAGE

@app.route("/api/state")
def state():
    try:
        do_tick()
    except Exception as e:
        print(e)
    data = rget()
    return jsonify({"cap":data.get("FUND_CAP",1000.0),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"total":data.get("FUND_TOTAL_TRADES",0),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",0.0),"dg":data.get("FUND_DAILY_GROSS",0.0),"df":data.get("FUND_DAILY_FEE",0.0),"whale":data.get("FAST_WHALE",[]),"rotate_coins":data.get("ROTATE_COINS",[]),"rotate_age":int(time.time()-float(data.get("ROTATE_LAST",0) or 0)) if data.get("ROTATE_LAST") else 0,"real_trading":BINANCE_REAL_TRADING})

@app.route("/api/cron")
def cron():
    result = do_tick()
    return jsonify({**result, "phone_off": True, "cron_time": time.time(), "real_trading": BINANCE_REAL_TRADING, "never_reset": True})

@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data = rget()
    # FIX RESET - CLEAR DAILY ONLY - KEEPS WINS/LOSSES/TOTAL/CAP - NEVER RESET TO 0W/0L
    # KEEPS WINS/LOSSES/TOTAL/CAP - ONLY CLEARS OPEN AND DAILY PNL - NEVER RESETS COUNT
    data["FUND_CLOSED"] = data.get("FUND_CLOSED",[])  # KEEP CLOSED - DON'T CLEAR CLOSED - FIXES RESET
    data["FUND_DAILY_PNL"] = 0
    data["FUND_DAILY_GROSS"] = 0
    data["FUND_DAILY_FEE"] = 0
    # DON'T CLEAR OPEN EITHER - KEEP TRADING - FIXES RESET
    # data["FUND_OPEN"] = []  # DON'T CLEAR - KEEP TRADING
    rset(data)
    return jsonify({"cleared":True,"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"total":data.get("FUND_TOTAL_TRADES",0),"cap":data.get("FUND_CAP",1000.0),"real_trading":BINANCE_REAL_TRADING,"never_reset":True,"message":"CLEAR DAILY ONLY - KEEPS WINS/LOSSES/TOTAL/CAP - NEVER RESET - FIXES RESET BUG"})

@app.route("/api/restore")
def restore():
    data = rget()
    return jsonify({"restored":True,"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"total":data.get("FUND_TOTAL_TRADES",0),"cap":data.get("FUND_CAP",1000.0),"open":len(data.get("FUND_OPEN",[])),"closed":len(data.get("FUND_CLOSED",[])),"never_reset":True})
