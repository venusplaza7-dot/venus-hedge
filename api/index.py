from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse, random, math
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

# === V825 WINNER FIXES ===
POS_PCT=20.0
MAXP=2
TOTAL_FEE=0.17
MIN_SL_PCT=0.80
MAX_SL_PCT=2.00  # widened from 1.80
MIN_TP_PCT=1.80  # must be > SL*2
MAX_TP_PCT=5.0
TIME_EXIT_MIN=240  # was 90m -> too short for 2R
TOP_N=30

# FIX 1: YOUR BLACKLIST WAS KILLING TOP30 SCAN
# You blacklisted SOL, SUI, HYPE, PUMP, SKY etc which ARE in your TOP30 list
# So scan 10 coins -> 4-5 removed -> 0 candidates
PERM_BLACKLIST=set(["MARSCOIN","MET","PUMP","MUBARAK","PYTH","1000PEPE","1000BONK","BIDR","IDRT"]) 
BAD_EXACT=set(["USDC","FDUSD","TUSD","BUSD","DAI","USDP","USDB","EUR","MARSCOIN","MET"])
BAD_CONTAINS=["BIDR","IDRT","TRYB","EURT"]

SECTORS={
    "L1":["BTC","ETH","SOL","AVAX","NEAR","ADA","DOT","ATOM","APT","ARB","OP","SUI","SEI","TIA"],
    "DEFI":["ENA","PENDLE","UNI","AAVE","MKR","LDO","CRV"],
    "MEME":["PEPE","BONK","WIF","FLOKI","SHIB","DOGE"],
    "AI":["TAO","FET","RNDR","GRT","BAT"]
}
COIN_SECTOR={c:sec for sec, coins in SECTORS.items() for c in coins}
def is_bad(b):
    if not b or not b.isascii(): return True
    if b in BAD_EXACT or b in PERM_BLACKLIST: return True
    for bad in BAD_CONTAINS:
        if bad in b: return True
    if len(b)>8 or b.startswith("1000"): return True
    if not b.isalnum(): return True
    return False
def get_sector(c): return COIN_SECTOR.get(c,"OTHER")

# === KV ===
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

WINNER_IDS=["bitcoin","ethereum","solana","binancecoin","ripple","cardano","avalanche-2","polkadot","chainlink","litecoin","matic-network","uniswap","cosmos","stellar","ethereum-classic","filecoin","aptos","arbitrum","optimism","injective-protocol","sui","render-token","maker","aave","the-graph","fantom","algorand","near-protocol","internet-computer","starknet","basic-attention-token","curve-dao-token"]
SYM_TO_ID={"BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin","XRP":"ripple","ADA":"cardano","AVAX":"avalanche-2","DOT":"polkadot","LINK":"chainlink","LTC":"litecoin","MATIC":"matic-network","UNI":"uniswap","ATOM":"cosmos","XLM":"stellar","ETC":"ethereum-classic","FIL":"filecoin","APT":"aptos","ARB":"arbitrum","OP":"optimism","INJ":"injective-protocol","SUI":"sui","RNDR":"render-token","MKR":"maker","AAVE":"aave","GRT":"the-graph","FTM":"fantom","ALGO":"algorand","NEAR":"near-protocol","ICP":"internet-computer","STRK":"starknet","BAT":"basic-attention-token","RENDER":"render-token","CRV":"curve-dao-token","QNT":"quant-network","JTO":"jito","CKB":"nervos-network"}

def get_tickers():
    try:
        cached=kv_get("CG_TOP30_V825")
        if cached and isinstance(cached, dict) and cached.get("ts",0) > int(time.time())-45:
            if len(cached.get("data",[]))>10:
                return cached["data"]
        ids=",".join(WINNER_IDS[:30])
        url=f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}&order=market_cap_desc&per_page=30&page=1&price_change_percentage=24h,7d"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data=json.loads(r.read().decode())
            tickers=[]
            for c in data:
                sym=c.get("symbol","").upper()
                if is_bad(sym): continue
                price=c.get("current_price",0); vol=c.get("total_volume",0)
                if price==0 or vol < 15000000: continue
                tickers.append({"symbol": sym+"USDT","base": sym,"price": price,"lastPrice": str(price),"vol": vol,"quoteVolume": str(vol),"change24": c.get("price_change_percentage_24h",0) or 0,"cg_id": c.get("id","")})
            if len(tickers)>8:
                kv_set("CG_TOP30_V825", {"ts":int(time.time()),"data":tickers})
                return tickers
    except Exception as e:
        print(f"CG fail {e}")
    # fallback binance
    for url in ["https://api.binance.com/api/v3/ticker/24hr","https://data-api.binance.vision/api/v3/ticker/24hr"]:
        try:
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=7) as r:
                data=json.loads(r.read().decode())
                filtered=[t for t in data if t.get("symbol","").replace("USDT","") in SYM_TO_ID and not is_bad(t.get("symbol","").replace("USDT",""))]
                if len(filtered)>8: return [{"symbol":x["symbol"],"base":x["symbol"].replace("USDT",""),"price":float(x["lastPrice"]),"lastPrice":x["lastPrice"],"vol":float(x["quoteVolume"]),"quoteVolume":x["quoteVolume"],"change24":float(x.get("priceChangePercent",0)),"cg_id":SYM_TO_ID.get(x["symbol"].replace("USDT",""))} for x in filtered[:30]]
        except: continue
    return []

def get_chart(cg_id, days=1):
    try:
        url=f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days={days}"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data=json.loads(r.read().decode())
            prices=data.get("prices",[])
            closes=[p[1] for p in prices]
            filtered=[]
            for c in closes:
                if c==0 or c is None: continue
                if filtered and filtered[-1]>0 and abs(c-filtered[-1])/filtered[-1] > 0.15: continue
                filtered.append(c)
            return filtered[-80:]
    except: return []

# === INDICATORS ===
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
    return abs(calc_ema(closes,9)-calc_ema(closes,21))/closes[-1]*1000

def get_market_smart(ticker_map):
    # get BTC closes
    btc_cg = get_chart("bitcoin",2)
    if len(btc_cg)<30:
        return {"regime":"RANGING","bias":"BOTH","btc_price":84000,"rsi":50,"strength":0.5,"reason":"RANGING BTC CG fallback - BOTH"}
    btc_price=btc_cg[-1]
    ema20=calc_ema(btc_cg,20); ema50=calc_ema(btc_cg,50); ema200=calc_ema(btc_cg,200) if len(btc_cg)>=200 else ema50
    rsi=calc_rsi(btc_cg,14); strength=calc_trend_strength(btc_cg)
    above20=btc_price>ema20; above50=btc_price>ema50
    if above20 and above50 and btc_price>ema200 and rsi>54 and strength>0.8:
        return {"regime":"TRENDING_BULL","bias":"LONG_ONLY","btc_price":btc_price,"rsi":rsi,"strength":strength,"reason":f"TRENDING_BULL BTC {btc_price:.0f} RSI {rsi:.0f} STR {strength:.1f} -> LONG ONLY TOP30"}
    elif not above20 and not above50 and rsi<48 and strength>0.8:
        return {"regime":"TRENDING_BEAR","bias":"SHORT_ONLY","btc_price":btc_price,"rsi":rsi,"strength":strength,"reason":f"TRENDING_BEAR BTC {btc_price:.0f} RSI {rsi:.0f} STR {strength:.1f} -> SHORT ONLY TOP30"}
    else:
        return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price,"rsi":rsi,"strength":strength,"reason":f"RANGING BTC {btc_price:.0f} RSI {rsi:.0f} STR {strength:.1f} -> BOTH FILTERED"}

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0]}
    s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("learn",{"blacklist":{},"last_coins":{}}); s.setdefault("peak",s.get("cap",300)); s.setdefault("equity",[300,s.get("cap",300)]); s.setdefault("scan",0)
    return s

def recalc_state_from_closed(state):
    closed=state.get("closed",[])
    true_cap=300.0+sum([c.get("net",0) for c in closed if isinstance(c,dict)])
    if abs(state.get("cap",300)-true_cap)>0.6: state["cap"]=true_cap
    wins=sum(1 for c in closed if c.get("net",0)>0); loss=sum(1 for c in closed if c.get("net",0)<0); tot=len(closed)
    state["wins"]=wins; state["loss"]=loss; state["total"]=tot; state["daily"]=sum([c.get("net",0) for c in closed[-20:]])
    return state

# === V825 CORE FIX ===
def do_cron():
    state=load_state()
    tickers=get_tickers()
    if not tickers:
        return {"ok":False,"error":"no tickers","scan":state.get("scan",0)}
    ticker_map={t["base"]:t for t in tickers}
    real_sorted=sorted(tickers, key=lambda x: x.get("vol",0), reverse=True)[:TOP_N]
    
    # FIX: SCAN ALL 30, NOT 1-10 OFFSET
    batch=real_sorted  # full top30
    
    market=get_market_smart(ticker_map)
    open_syms=[t["symbol"] for t in state.get("open",[])]
    
    candidates=[]
    for t in batch:
        base=t["base"]
        if base in open_syms: continue
        if is_bad(base): continue
        price=t["price"]
        chart=get_chart(t.get("cg_id",""),2)
        if len(chart)<25: continue
        
        rsi=calc_rsi(chart,14)
        atr_pct=calc_atr_pct(chart,14)
        ema20=calc_ema(chart,20)
        ema50=calc_ema(chart,50)
        strength=calc_trend_strength(chart)
        
        # V825 FILTER - widened
        if atr_pct < 0.55 or atr_pct > 6.0: continue
        if t["vol"] < 18000000: continue
        
        above = price > ema20 and ema20 > ema50
        below = price < ema20 and ema20 < ema50
        
        side=None; reason=""
        # === FIXED LOGIC FOR BEAR ===
        if market["bias"]=="SHORT_ONLY":
            # Bear shorts: bounce to EMA, RSI 48-62, not >65
            if 48 <= rsi <= 62 and below:
                side="SHORT"; reason=f"SHORT BEAR BOUNCE RSI {rsi:.0f} 48-62 EMA down ATR {atr_pct:.1f}% {market['regime']}"
            elif rsi >= 68 and atr_pct>0.8:  # overbought reversal only
                side="SHORT"; reason=f"SHORT OB RSI {rsi:.0f}>68 ATR {atr_pct:.1f}% REV"
        elif market["bias"]=="LONG_ONLY":
            if 38 <= rsi <= 55 and above:
                side="LONG"; reason=f"LONG BULL DIP RSI {rsi:.0f} 38-55 EMA up ATR {atr_pct:.1f}% {market['regime']}"
            elif rsi <= 32:
                side="LONG"; reason=f"LONG OS RSI {rsi:.0f}<32 ATR {atr_pct:.1f}% REV"
        else: # RANGING - both but stricter
            if rsi < 33 and above and strength>0.6:
                side="LONG"; reason=f"LONG RANGE OVERSOLD RSI {rsi:.0f}<33"
            elif rsi > 67 and below and strength>0.6:
                side="SHORT"; reason=f"SHORT RANGE OVERBOUGHT RSI {rsi:.0f}>67"
        
        if not side: continue
        
        sl_pct=max(MIN_SL_PCT, min(MAX_SL_PCT, atr_pct*1.4))
        tp_pct=max(MIN_TP_PCT, min(MAX_TP_PCT, sl_pct*2.2))
        if tp_pct/sl_pct < 2.0: tp_pct=sl_pct*2.2
        
        score = (rsi-50) if side=="SHORT" else (50-rsi)
        score = abs(score)*2 + atr_pct*3 + strength + t["vol"]/15000000
        
        candidates.append({"symbol":base,"side":side,"price":price,"sector":get_sector(base),"score":score,"tp":tp_pct,"sl":sl_pct,"rsi":rsi,"reason":reason,"strength":strength,"atr":atr_pct,"vol":t["vol"],"cg_id":t.get("cg_id","")})
    
    candidates=sorted(candidates, key=lambda x: x["score"], reverse=True)[:MAXP]
    
    # === CLOSE LOGIC - FIX EARLY CUT BUG ===
    closed=state.get("closed",[]); cap=state.get("cap",300.0); fees=state.get("fees_paid",0.0)
    final=[]
    for tr in state.get("open",[]):
        base=tr["symbol"]
        live=None
        for tk in tickers:
            if tk["base"]==base: live=tk["price"]; break
        if not live or live==0: live=tr.get("price",0)
        entry=tr["entry"]; side=tr["side"]
        pct_gross=(live-entry)/entry*100 if side=="LONG" else (entry-live)/entry*100
        pct_net=pct_gross-TOTAL_FEE
        pos=tr.get("pos",60); net_usd=pos*pct_net/100; age=int(time.time())-tr.get("ts",int(time.time()))
        tr["price"]=live; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["net"]=net_usd; tr["age"]=age
        tr["peak_gross"]=max(tr.get("peak_gross",0), pct_gross)
        
        tp=tr.get("tp",2.0); sl=tr.get("sl",0.9); should=None
        # FIX: only real SL/TP, no fake CUT before SL
        if pct_gross >= tp: should=f"TP {tp:.2f}% WIN +${net_usd:.2f} RR {tp/sl:.1f}"
        elif pct_gross <= -sl: should=f"SL -{sl:.2f}% LOSS ${net_usd:.2f}"
        elif age > TIME_EXIT_MIN*60:
            # time exit only if not in profit >0.5%
            if pct_gross < 0.5: should=f"TIME {TIME_EXIT_MIN}m {pct_gross:.2f}%"
        # REMOVED: trail logic that was cutting winners early
        # REMOVED: MAXLOSS -1.5% that closed before SL
        
        if should:
            cap+=net_usd; fees+=TOTAL_FEE*pos/100
            closed.insert(0,{"symbol":base,"side":side,"net":net_usd,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"pos":pos,"rsi":tr.get("rsi",0),"rr":tp/sl if sl>0 else 2})
        else:
            final.append(tr)
    
    # open new
    for c in candidates:
        if len(final)>=MAXP: break
        if c["symbol"] in [t["symbol"] for t in final]: continue
        pos=cap*POS_PCT/100
        if pos<15 or cap<20: continue
        final.append({"symbol":c["symbol"],"side":c["side"],"entry":c["price"],"price":c["price"],"pos":pos,"ts":int(time.time()),"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":c["score"],"sector":c["sector"],"tp":c["tp"],"sl":c["sl"],"reason":c["reason"],"rsi":c["rsi"],"strength":c["strength"],"atr":c["atr"],"vol":c["vol"],"cg_id":c["cg_id"]})
    
    state["open"]=final; state["closed"]=closed[:200]; state["cap"]=cap; state["fees_paid"]=fees
    state=recalc_state_from_closed(state); state["scan"]=state.get("scan",0)+1; state["market"]=market; state["peak"]=max(state.get("peak",cap),cap)
    eq=state.get("equity",[300]); eq.append(cap); state["equity"]=eq[-100:]
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":state["scan"],"open":len(final),"cap":cap,"candidates":len(candidates),"bias":market["bias"],"market":market["reason"],"regime":market["regime"],"batch":f"1-{TOP_N} FULL","source":"CG TOP30 V825 FIXED"}

def render(state):
    # simplified render reusing v824 but with v825 tag
    state=recalc_state_from_closed(state)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300); peak=state.get("peak",cap); scan=state.get("scan",0)
    market=state.get("market",{"regime":"RANGING","bias":"BOTH","btc_price":0,"rsi":0,"reason":"v825"})
    wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); fees=state.get("fees_paid",0)
    gross_profit=sum([c.get("net",0) for c in closed if c.get("net",0)>0]); gross_loss=sum([c.get("net",0) for c in closed if c.get("net",0)<0])
    pf=abs(gross_profit/gross_loss) if gross_loss!=0 else 0; exp=(gross_profit+gross_loss)/tot if tot>0 else 0; winrate=int(wins/tot*100) if tot>0 else 0; unreal=sum([t.get("net",0) for t in open_tr]); dd=(peak-cap)/peak*100 if peak>0 else 0
    long_o=sum(1 for t in open_tr if t["side"]=="LONG"); short_o=sum(1 for t in open_tr if t["side"]=="SHORT")
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}}.h{{background:linear-gradient(90deg,#00ff88,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;border-radius:12px}}.c{{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}}.g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}}.it{{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:12px}}.btn{{padding:14px;border-radius:12px;border:0;font-weight:900}}</style></head><body>
    <div class='h'>VENUS v825 FIXED - SCAN #{scan} - ${cap:.2f} PEAK ${peak:.2f} DD {dd:.1f}% L:{long_o} S:{short_o} {market.get('regime')} {market.get('bias')} - TOP30 FULL SCAN RR>2.0</div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#fc0'>${cap:.2f}</b><br>UNREAL {unreal:+.2f}<br>FEES ${fees:.2f}<br>DD {dd:.1f}%</div>
    <div class='c'>TODAY<br><b style='font-size:18px;color:{"#f44" if cap<300 else "#0f8"}'>${cap-300:+.2f}</b><br>W:{wins} L:{loss} {winrate}%<br>PF {pf:.2f} EXP ${exp:.3f}</div>
    <div class='c'>{market.get('bias')}<br>{market.get('regime')}<br>BTC ${market.get('btc_price',0):.0f}<br>RSI {market.get('rsi',0):.0f}<br>RR>2.0</div></div>
    <div class='it' style='border-color:#0f8'>📈 v825 FIXES: 1) SCAN FULL 30 NOT 1-10 offset - fixes nothing found 2) BLACKLIST cleaned SOL/SUI not blocked 3) BEAR SHORT RSI 48-62 not >65 - finds signals 4) REMOVED early CUT bug SL -0.7% - now only real SL 0.80-2.0% 5) REMOVED trail 35% cut that killed winners 6) TIME 240m not 90m 7) BIAS LOCK - SHORT_ONLY blocks LONGS 8) ATR 0.55-6% VOL 18M min<br>{market.get('reason')}</div>
    """
    for tr in open_tr:
        html+=f"<div class='it' style='border-color:{'#0f8' if tr['pct']>=0 else '#f44'}'><b>{tr['symbol']} {tr['side']} RR {tr['tp']/tr['sl']:.1f}</b> ${tr['net']:+.2f} {tr['pct']:+.2f}% ENTRY {tr['entry']:.4f} LIVE {tr['price']:.4f} SL {tr['sl']:.2f}% TP {tr['tp']:.2f}%<br>{tr['reason']}</div>"
    html+=f"<div class='it'><b>CLOSED {len(closed)} W:{wins} L:{loss} {winrate}% PF {pf:.2f}</b><br>"
    for cl in closed[:20]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"
        html+=f"<div style='color:{c}'>{cl.get('symbol')} {cl.get('side')} ${cl.get('net',0):+.2f} {cl.get('pct_net',0):+.2f}% | {cl.get('reason','')}</div>"
    html+="""</div><script>async function callCron(){fetch('/api/cron?key=venus727').then(r=>r.json()).then(j=>{document.body.innerHTML+='<pre>'+JSON.stringify(j)+'</pre>'; setTimeout(()=>location.reload(),1000)})}</script>
    <button class='btn' style='background:#0f8;width:100%;margin:6px 0' onclick='callCron()'>⚡ CRON V825 FULL SCAN 1-30</button>
    </body></html>"""
    return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    key=request.args.get("key","")
    p="/"+path
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps(do_cron()), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); kv_del("CG_TOP30_V825"); kv_set(STATE_KEY, {"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0]})
        return Response(json.dumps({"ok":True}), mimetype="application/json")
    if p.startswith("/api/debug"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps(load_state(), indent=2), mimetype="application/json")
    st=load_state(); return Response(render(st), mimetype="text/html")
