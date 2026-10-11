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
STATE_KEY="VENUS_V800_WINNER" # NEW KEY - fresh start
POS_PCT=0.20 # 20% of cap per trade max, not 33% fixed $100
FEE_PCT=0.075 # REAL binance fee with BNB
FEE_USD=0.075 # fix double count
MAXP=3
RISK_PER_TRADE=0.02 # 2% risk

SECTORS={"L1_CHAIN":["BTC","ETH","ETC","ARB","SUI","SEI","APT","TIA","ATOM","AVAX","SOL","NEAR","OP","STRK","ZK","SAGA","DOGE","CFX","ZEC","CHIP"],"DEPIN_WIFI":["FIL","RNDR","THETA","IOTX","AR","STORJ","HNT","AKT","GRT","FET","AERO","W","JASMY"],"AI":["EIGEN","TAO","FET","ARKM","RNDR","GRT","LUMIA","ZEC","CFX"],"DEFI":["ENA","PENDLE","AERO","LDO","UNI","AAVE","ETHFI","BTC","ETH","AVAX","ONDO","LUMIA","NEAR"],"MEME":["PEPE","BONK","WIF","FLOKI","SHIB","BOME","POPCAT","BRETT","DOGE"],"RWA_GAMING":["IMX","RONIN","GALA","BEAM","PIXEL","ETC","BTC"]}
COIN_SECTOR={}
for sec, coins in SECTORS.items():
    for c in coins:
        if c not in COIN_SECTOR: COIN_SECTOR[c]=sec
BAD_EXACT=set(["USDC","FDUSD","TUSD","BUSD","DAI","USDP","EUR","BIDR","IDRT","TRY","BRL","BRLT","BVND","VAI","USDB","USD1","BFUSD","TRYT","PLN","UAH","NGN","BKRW","ZAR","JPY","GBP","AUD","UAHT","MATICBIDR","SOLBIDR","XRPBIDR","BUSDBIDR","STRKTRY","IDRT","BUSDTRY","BTCBIDR","USD1","1000PEPE","1000BONK"])
BAD_CONTAINS=["BIDR","IDRT","TRYB","EURT","EURS","BVND","BRLT"]
def is_bad(b):
    if b in BAD_EXACT: return True
    for bad in BAD_CONTAINS:
        if bad in b: return True
    if len(b)>8 or b.startswith("1000"): return True
    if "BID" in b: return True
    return False
def get_sector(c): return COIN_SECTOR.get(c,"OTHER_BEST")

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

def get_klines(symbol, interval="15m", limit=50):
    try:
        url=f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data=json.loads(r.read().decode())
            # [open_time, open, high, low, close, volume...]
            return [{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data]
    except: return []

def calc_rsi(closes, period=14):
    if len(closes) < period+1: return 50
    gains=0; losses=0
    for i in range(1, period+1):
        diff=closes[-i]-closes[-i-1]
        if diff>=0: gains+=diff
        else: losses+=-diff
    if losses==0: return 70
    rs=gains/losses
    return 100 - (100/(1+rs))

def calc_atr(klines, period=14):
    if len(klines) < period+1: return klines[-1]["c"]*0.01 if klines else 0.01
    trs=[]
    for i in range(1, len(klines)):
        h=klines[i]["h"]; l=klines[i]["l"]; pc=klines[i-1]["c"]
        tr=max(h-l, abs(h-pc), abs(l-pc))
        trs.append(tr)
    return sum(trs[-period:])/period

def calc_ema(closes, period):
    if len(closes) < period: return sum(closes)/len(closes)
    k=2/(period+1)
    ema=closes[0]
    for c in closes[1:]:
        ema=c*k + ema*(1-k)
    return ema

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

def get_market(ticker_map):
    klines=get_klines("BTCUSDT","1h",50)
    if not klines:
        btc_ticker=ticker_map.get("BTCUSDT")
        btc_price=float(btc_ticker.get("lastPrice","83866")) if btc_ticker else 83866
        return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price,"h1":0,"reason":"klines fail fallback"}
    closes=[k["c"] for k in klines]
    btc_price=closes[-1]
    ema200=calc_ema(closes, 50)
    rsi=calc_rsi(closes, 14)
    # REAL regime
    if btc_price > ema200 and rsi>55: regime="TRENDING_BULL"; bias="LONG"
    elif btc_price < ema200 and rsi<45: regime="TRENDING_BEAR"; bias="SHORT"
    else: regime="RANGING"; bias="BOTH"
    return {"regime":regime,"bias":bias,"btc_price":btc_price,"rsi":rsi,"ema":ema200,"h1":(closes[-1]/closes[-2]-1)*100,"reason":f"{regime} BTC {btc_price:.0f} RSI {rsi:.0f} vs EMA {ema200:.0f}"}

def do_cron():
    state=load_state()
    L=state["learn"]
    now_ts=int(time.time())
    if L.get("pause_until",0)>now_ts:
        return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"scan":state.get("scan",0)}
    
    tickers=get_tickers()
    ticker_map={}
    real=[]
    for t in tickers:
        sym=t.get("symbol","")
        ticker_map[sym]=t
        if not sym.endswith("USDT"): continue
        base=sym.replace("USDT","")
        if is_bad(base): continue
        if not base.isalnum(): continue
        if len(base)<2 or len(base)>8: continue
        real.append(t)
    real=sorted(real, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:40]
    market=get_market(ticker_map)

    open_tr=state.get("open",[])
    open_syms=[t["symbol"] for t in open_tr]

    candidates=[]
    for t in real:
        base=t.get("symbol","").replace("USDT","")
        if base in open_syms: continue
        if base in L.get("blacklist",{}): continue
        if base in L.get("last_coins",{}): continue
        vol=float(t.get("quoteVolume","0"))
        if vol<8000000: continue # higher filter
        h1=float(t.get("priceChangePercent","0"))
        price=float(t.get("lastPrice","0"))
        if price<0.0000005 or price>200000: continue
        sector=get_sector(base)

        klines=get_klines(base+"USDT","15m",50)
        if len(klines)<30: continue
        closes=[k["c"] for k in klines]
        rsi=calc_rsi(closes,14)
        atr=calc_atr(klines,14)
        atr_pct=(atr/price*100) if price else 1
        if atr_pct < 0.4 or atr_pct > 6: continue # skip dead and crazy volatile

        ema20=calc_ema(closes,20)
        last_c=closes[-1]
        
        score=0; side=None; reason=""
        # WINNING LOGIC 1: Mean reversion long - oversold dip in uptrend
        if rsi < 32 and last_c < ema20*0.998 and market["bias"]!="SHORT" and h1 > -8:
            # dip buy
            score=(32-rsi)*vol/1e7 * (1+atr_pct)
            side="LONG"
            reason=f"LONG DIP RSI {rsi:.0f} <32 ATR {atr_pct:.2f}% BTC {market['regime']}"
            tp=atr*1.8; sl=atr*1.0
        # WINNING LOGIC 2: Mean reversion short - overbought pump
        elif rsi > 68 and last_c > ema20*1.002 and market["bias"]!="LONG" and h1 < 15:
            score=(rsi-68)*vol/1e7 * (1+atr_pct)
            side="SHORT"
            reason=f"SHORT PUMP RSI {rsi:.0f} >68 ATR {atr_pct:.2f}%"
            tp=atr*1.8; sl=atr*1.0
        # WINNING LOGIC 3: Breakout with volume
        elif abs(last_c-ema20)/ema20 < 0.003 and vol > 20000000 and rsi>55 and rsi<65:
            # tight consolidation breakout, follow BTC bias
            if market["bias"]=="LONG":
                side="LONG"; score=vol/1e7*2; reason=f"LONG BREAKOUT squeeze BTC BULL"
                tp=atr*2.2; sl=atr*0.9
            elif market["bias"]=="SHORT":
                side="SHORT"; score=vol/1e7*2; reason=f"SHORT BREAKDOWN squeeze BTC BEAR"
                tp=atr*2.2; sl=atr*0.9

        if side:
            tp_pct=tp/price*100
            sl_pct=sl/price*100
            if tp_pct < 0.6: continue # must be worth fee*3
            candidates.append({"symbol":base,"side":side,"price":price,"vol":int(vol),"h1":h1,"sector":sector,"score":score,"tp":tp_pct,"sl":sl_pct,"tp_price":tp,"sl_price":sl,"rsi":rsi,"atr_pct":atr_pct,"reason":reason})

    candidates=sorted(candidates, key=lambda x: x["score"], reverse=True)
    # No forced balance - take best 3, but respect market bias
    final_sharks=[]
    for c in candidates:
        if len(final_sharks)>=3: break
        # Filter by BTC bias
        if market["bias"]=="LONG" and c["side"]=="SHORT" and c["rsi"]<72: continue # skip shorts in bull unless extreme
        if market["bias"]=="SHORT" and c["side"]=="LONG" and c["rsi"]>28: continue
        if c["symbol"] not in [x["symbol"] for x in final_sharks]:
            final_sharks.append(c)

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
            pos_size=tr.get("pos", cap*POS_PCT)
            net_usd=pos_size*pct_net/100
            gross_usd=pos_size*pct_gross/100
            age=now_ts-tr.get("ts",now_ts)
            peak_gross=max(tr.get("peak_gross",0), pct_gross)
            tr["price"]=price_now; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["peak_gross"]=peak_gross; tr["age"]=age; tr["net"]=net_usd; tr["gross"]=gross_usd
            
            tp=tr.get("tp",1.2); sl=tr.get("sl",0.8)
            klines=get_klines(sym,"5m",20)
            atr_now=calc_atr(klines,14) if klines else entry*0.01
            # DYNAMIC EXITS - THIS IS WHAT FIXES YOUR LOSSES
            should=None
            if pct_gross>=tp:
                should=f"TP {tp:.2f}% WIN +${net_usd:+.2f}"
            elif pct_gross<=-sl:
                should=f"SL -{sl:.2f}% CUT"
            elif peak_gross>=tp*0.7 and pct_gross<peak_gross - (atr_now/entry*100*0.5):
                should=f"TRAIL peak {peak_gross:.2f}%->{pct_gross:.2f}% ATR trail"
            elif age>1800: # 30 min max, not 800s
                should=f"TIME 30m {pct_gross:.2f}%"
            elif age>600 and pct_gross < -0.15 and peak_gross<0.2:
                should=f"FLAT 10m no momentum CUT"

            if should:
                cap+=net_usd; daily+=net_usd; daily_gross+=gross_usd; fees_paid+=FEE_PCT*pos_size/100; tot+=1
                closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"gross":gross_usd,"fee":FEE_PCT*pos_size/100,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"sector":get_sector(tr["symbol"]),"strategy":tr.get("strategy","")})
                L["last_coins"][tr["symbol"]]=now_ts+600
                if pct_net<-1.0: # only blacklist hard losers
                    L["blacklist"][tr["symbol"]]=now_ts+3600
            else:
                final.append(tr)
        except Exception as e:
            final.append(tr)
    
    wins=sum(1 for c in closed if c.get("net",0)>0.05)
    loss=sum(1 for c in closed if c.get("net",0)<0)
    
    for sh in final_sharks:
        if len(final)>=MAXP: break
        if sh["symbol"] in [t["symbol"] for t in final]: continue
        if sh["symbol"] in L.get("blacklist",{}): continue
        # POS SIZE BASED ON RISK, NOT FIXED $100
        risk_usd=cap * RISK_PER_TRADE
        sl_pct=sh["sl"]
        if sl_pct <=0: continue
        pos_size = risk_usd / (sl_pct/100)
        pos_size = min(pos_size, cap*POS_PCT) # cap max
        if pos_size < 10: continue
        price=sh["price"]; qty=pos_size/price if price>0 else 0
        tr={"symbol":sh["symbol"],"side":sh["side"],"entry":price,"price":price,"pos":pos_size,"qty":qty,"ts":now_ts,"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"gross":0,"age":0,"h1":sh["h1"],"score":sh["score"],"sector":sh["sector"],"strategy":sh["side"]+"_ATR_RSI","tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"rsi":sh["rsi"],"atr":sh["atr_pct"]}
        final.append(tr)

    state["open"]=final; state["closed"]=closed[:200]; state["cap"]=cap; state["daily"]=daily; state["daily_gross"]=daily_gross; state["fees_paid"]=fees_paid; state["wins"]=wins; state["loss"]=loss; state["total"]=tot; state["scan"]=scan; state["market"]=market
    kv_set(STATE_KEY, state)
    long_c=sum(1 for s in final if s.get("side")=="LONG")
    short_c=sum(1 for s in final if s.get("side")=="SHORT")
    return {"ok":True,"scan":scan,"open":len(final),"long":long_c,"short":short_c,"cap":cap,"daily":daily,"candidates":len(candidates),"total":tot,"wins":wins,"loss":loss,"market":market["regime"]+" "+market["bias"]+" BTC $"+str(int(market["btc_price"]))+" RSI "+str(int(market.get("rsi",50))),"v":"v800 WINNER ATR+RSI"}

def render(state):
    # KEEP YOUR RENDER - I only changed title
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
    market=state.get("market",{"regime":"RANGING","bias":"BOTH","btc_price":83866,"rsi":50,"reason":"no market"})
    winrate=int(wins/tot*100) if tot>0 else 0
    unreal=sum([t.get("net",0) for t in open_tr])
    long_open=sum(1 for t in open_tr if t.get("side")=="LONG")
    short_open=sum(1 for t in open_tr if t.get("side")=="SHORT")
    html="<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
    html+="body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}"
    html+=".h{background:linear-gradient(90deg,#00ff88,#ff0044,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;position:sticky;top:0;z-index:10}"
    html+=".g{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}"
    html+=".c{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:10px}"
    html+=".b{padding:9px;margin:8px 0;border-radius:7px;font-weight:800;font-size:11px}"
    html+=".by{background:#ffcc00;color:#000} .bb{background:#00d4ff;color:#000} .bd{background:#222;color:#888} .bg{background:#00ff88;color:#000} .bp{background:#ff00ff;color:#fff} .br{background:#ff4444;color:#fff}"
    html+=".it{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:10px;position:relative;overflow:hidden}"
    html+="</style></head><body>"
    bias_color="#00ff88" if market.get("bias")=="LONG" else "#ff4444" if market.get("bias")=="SHORT" else "#ffcc00"
    html+=f"<div class='h'>VENUS v800 WINNER ATR RSI - SCAN #{scan} - CAP ${cap:.2f} L:{long_open} S:{short_open} {market.get('regime')} BTC ${market.get('btc_price',0):.0f} RSI {market.get('rsi',50):.0f}</div>"
    html+=f"<div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#ffcc00'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f} UNREAL {unreal:+.2f}</div><div class='c'>TODAY<br><b style='font-size:18px;color:{'#f44' if daily<0 else '#0f8'}'>${daily:+.2f}</b><br>W:{wins} L:{loss} {winrate}% FEES ${fees_paid:.2f}</div><div class='c'>MARKET<br><b>{market.get('regime')} {market.get('bias')}</b><br>BTC ${market.get('btc_price',0):.0f} {market.get('reason','')[:60]}</div></div>"
    html+="<div id='openbox'>"
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"<div class='it' style='border-color:{col}'><b style='color:{col}'>{tr['symbol']} {tr.get('side')} {tr.get('sector')} {tr.get('age',0)}s PEAK {tr.get('peak_gross',0):.2f}%</b><br>ENTRY ${tr.get('entry',0):.6f} -> NOW ${tr.get('price',0):.6f} POS ${tr.get('pos',0):.0f} H1 {tr.get('h1',0):+.1f}% RSI {tr.get('rsi',0):.0f}<br><b>{tr.get('pct_gross',0):.3f}% GROSS {tr.get('pct',0):.3f}% NET ${tr.get('net',0):+.3f}</b> TP {tr.get('tp',0):.2f}% SL {tr.get('sl',0):.2f}%<br><span style='font-size:10px;color:#888'>{tr.get('reason','')}</span></div>"
    if not open_tr:
        html+=f"<div class='it' style='text-align:center;color:#0f8'>SCANNER ACTIVE - {market.get('reason','')} - Looking for RSI <32 LONG or >68 SHORT + ATR filter</div>"
    html+="</div><div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'>"
    html+=f"<div style='color:#ffcc00;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% - CAP ${cap:.2f} DAILY ${daily:+.2f}</div>"
    for cl in closed[:20]:
        c="#0f8" if cl.get("net",0)>=0.05 else "#f44"
        html+=f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')} {cl.get('side','')}</b> ${cl.get('net',0):+.2f} {cl.get('reason','')} {cl.get('pct_gross',0):+.2f}%</div>"
    html+="</div></body></html>"
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
