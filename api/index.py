from flask import Flask, request, Response
import os, json, time, urllib.request
app = Flask(__name__)

# ============ ENV / KV ============
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
STATE_KEY="VENUS_V800_WINNER_FINAL"
POS_PCT=0.20
FEE_PCT=0.075
MAXP=3
RISK_PER_TRADE=0.02

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
    for base_url in ["https://data-api.binance.vision", "https://api.binance.com"]:
        try:
            url=f"{base_url}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as r:
                data=json.loads(r.read().decode())
                return [{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in data]
        except: continue
    return []

def calc_rsi(closes, period=14):
    if len(closes) < period+1: return 50
    gains=0; losses=0
    for i in range(1, period+1):
        diff=closes[-i]-closes[-i-1]
        if diff>=0: gains+=diff
        else: losses+=-diff
    if losses==0: return 70 if gains>0 else 50
    rs=gains/losses if losses!=0 else 0
    return 100 - (100/(1+rs))

def calc_atr(klines, period=14):
    if len(klines) < period+1: return klines[-1]["c"]*0.01 if klines else 0.01
    trs=[]
    for i in range(1, len(klines)):
        h=klines[i]["h"]; l=klines[i]["l"]; pc=klines[i-1]["c"]
        tr=max(h-l, abs(h-pc), abs(l-pc))
        trs.append(tr)
    return sum(trs[-period:])/period if trs else klines[-1]["c"]*0.01

def calc_ema(closes, period):
    if len(closes) < period: return sum(closes)/len(closes) if closes else 0
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
        return {"regime":"RANGING","bias":"BOTH","btc_price":btc_price,"rsi":50,"ema":btc_price,"h1":0,"reason":"klines fail - tap CRON again"}
    closes=[k["c"] for k in klines]
    btc_price=closes[-1]
    ema200=calc_ema(closes, 50)
    rsi=calc_rsi(closes, 14)
    if btc_price > ema200 and rsi>55: regime="TRENDING_BULL"; bias="LONG"
    elif btc_price < ema200 and rsi<45: regime="TRENDING_BEAR"; bias="SHORT"
    else: regime="RANGING"; bias="BOTH"
    return {"regime":regime,"bias":bias,"btc_price":btc_price,"rsi":rsi,"ema":ema200,"h1":(closes[-1]/closes[-2]-1)*100 if len(closes)>1 else 0,"reason":f"{regime} BTC {btc_price:.0f} RSI {rsi:.0f} vs EMA {ema200:.0f}"}

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
        if vol<8000000: continue
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
        if atr_pct < 0.4 or atr_pct > 6: continue
        ema20=calc_ema(closes,20)
        last_c=closes[-1]
        score=0; side=None; reason=""; tp=0; sl=0
        if rsi < 32 and last_c < ema20*0.998 and market["bias"]!="SHORT" and h1 > -8:
            score=(32-rsi)*vol/1e7 * (1+atr_pct)
            side="LONG"; reason=f"LONG DIP RSI {rsi:.0f} <32 ATR {atr_pct:.2f}% BTC {market['regime']}"
            tp=atr*1.8; sl=atr*1.0
        elif rsi > 68 and last_c > ema20*1.002 and market["bias"]!="LONG" and h1 < 15:
            score=(rsi-68)*vol/1e7 * (1+atr_pct)
            side="SHORT"; reason=f"SHORT PUMP RSI {rsi:.0f} >68 ATR {atr_pct:.2f}%"
            tp=atr*1.8; sl=atr*1.0
        elif abs(last_c-ema20)/ema20 < 0.003 and vol > 20000000 and rsi>55 and rsi<65:
            if market["bias"]=="LONG":
                side="LONG"; score=vol/1e7*2; reason=f"LONG BREAKOUT squeeze BTC BULL"; tp=atr*2.2; sl=atr*0.9
            elif market["bias"]=="SHORT":
                side="SHORT"; score=vol/1e7*2; reason=f"SHORT BREAKDOWN squeeze BTC BEAR"; tp=atr*2.2; sl=atr*0.9
        if side:
            tp_pct=tp/price*100; sl_pct=sl/price*100
            if tp_pct < 0.6: continue
            candidates.append({"symbol":base,"side":side,"price":price,"vol":int(vol),"h1":h1,"sector":sector,"score":score,"tp":tp_pct,"sl":sl_pct,"rsi":rsi,"atr_pct":atr_pct,"reason":reason})
    candidates=sorted(candidates, key=lambda x: x["score"], reverse=True)
    final_sharks=[]
    for c in candidates:
        if len(final_sharks)>=3: break
        if market["bias"]=="LONG" and c["side"]=="SHORT" and c["rsi"]<72: continue
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
            if side=="LONG": pct_gross=(price_now-entry)/entry*100 if entry else 0
            else: pct_gross=(entry-price_now)/entry*100 if entry else 0
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
            should=None
            if pct_gross>=tp: should=f"TP {tp:.2f}% WIN +${net_usd:+.2f}"
            elif pct_gross<=-sl: should=f"SL -{sl:.2f}% CUT"
            elif peak_gross>=tp*0.7 and pct_gross<peak_gross - (atr_now/entry*100*0.5): should=f"TRAIL peak {peak_gross:.2f}%->{pct_gross:.2f}%"
            elif age>1800: should=f"TIME 30m {pct_gross:.2f}%"
            elif age>600 and pct_gross < -0.15 and peak_gross<0.2: should=f"FLAT 10m CUT"
            if should:
                cap+=net_usd; daily+=net_usd; daily_gross+=gross_usd; fees_paid+=FEE_PCT*pos_size/100; tot+=1
                closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"gross":gross_usd,"fee":FEE_PCT*pos_size/100,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"sector":get_sector(tr["symbol"])})
                L["last_coins"][tr["symbol"]]=now_ts+600
                if pct_net<-1.0: L["blacklist"][tr["symbol"]]=now_ts+3600
            else:
                final.append(tr)
        except:
            final.append(tr)
    wins=sum(1 for c in closed if c.get("net",0)>0.05)
    loss=sum(1 for c in closed if c.get("net",0)<0)
    for sh in final_sharks:
        if len(final)>=MAXP: break
        if sh["symbol"] in [t["symbol"] for t in final]: continue
        if sh["symbol"] in L.get("blacklist",{}): continue
        risk_usd=cap * RISK_PER_TRADE
        sl_pct=sh["sl"]
        if sl_pct <=0: continue
        pos_size = risk_usd / (sl_pct/100)
        pos_size = min(pos_size, cap*POS_PCT)
        if pos_size < 10: continue
        price=sh["price"]; qty=pos_size/price if price>0 else 0
        tr={"symbol":sh["symbol"],"side":sh["side"],"entry":price,"price":price,"pos":pos_size,"qty":qty,"ts":now_ts,"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"gross":0,"age":0,"h1":sh["h1"],"score":sh["score"],"sector":sh["sector"],"strategy":sh["side"]+"_ATR_RSI","tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"rsi":sh["rsi"],"atr":sh["atr_pct"]}
        final.append(tr)
    state["open"]=final; state["closed"]=closed[:200]; state["cap"]=cap; state["daily"]=daily; state["daily_gross"]=daily_gross; state["fees_paid"]=fees_paid; state["wins"]=wins; state["loss"]=loss; state["total"]=tot; state["scan"]=scan; state["market"]=market
    kv_set(STATE_KEY, state)
    long_c=sum(1 for s in final if s.get("side")=="LONG")
    short_c=sum(1 for s in final if s.get("side")=="SHORT")
    return {"ok":True,"scan":scan,"open":len(final),"long":long_c,"short":short_c,"cap":cap,"daily":daily,"candidates":len(candidates),"total":tot,"wins":wins,"loss":loss,"market":market["regime"]+" "+market["bias"]+" BTC $"+str(int(market["btc_price"]))+" RSI "+str(int(market.get("rsi",50))),"v":"v800 WINNER FINAL"}

def render(state):
    open_tr=state.get("open",[])
    closed=state.get("closed",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    fees_paid=state.get("fees_paid",0.0)
    wins=state.get("wins",0)
    loss=state.get("loss",0)
    tot=state.get("total",0)
    scan=state.get("scan",0)
    market=state.get("market",{"regime":"RANGING","bias":"BOTH","btc_price":83866,"rsi":50,"reason":"no market - tap CRON"})
    winrate=int(wins/tot*100) if tot>0 else 0
    unreal=sum([t.get("net",0) for t in open_tr])
    long_open=sum(1 for t in open_tr if t.get("side")=="LONG")
    short_open=sum(1 for t in open_tr if t.get("side")=="SHORT")
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'>
    <style>
    body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}}
   .h{{background:linear-gradient(90deg,#00ff88,#ff0044,#00d4ff);color:#000;padding:14px;text-align:center;font-weight:900;font-size:13px;position:sticky;top:0;z-index:10;border-radius:12px}}
   .g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}
   .c{{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:10px}}
   .it{{background:#111;border:1px solid #333;padding:12px;margin:8px 0;border-radius:12px}}
   .btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:12px 0;position:sticky;top:60px;z-index:9}}
   .btn{{padding:16px 6px;border-radius:14px;border:0;font-weight:900;font-size:13px;text-align:center;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,0.4)}}
   .btn-cron{{background:#00ff88;color:#000}}.btn-reset{{background:#ff4444;color:#fff}}.btn-close{{background:#ffcc00;color:#000}}
   .btn:active{{transform:scale(0.93)}}
   .icon{{font-size:22px;display:block;margin-bottom:2px}}
   .badge{{padding:3px 8px;border-radius:20px;font-size:10px;font-weight:900}}
   .long{{background:#00ff88;color:#000}}.short{{background:#ff4444;color:#fff}}
    </style></head><body>
    <div class='h'>VENUS v800 FINAL - SCAN #{scan} - ${cap:.2f} L:{long_open} S:{short_open} {market.get('regime')} BTC ${market.get('btc_price',0):.0f}</div>
    <div class='btn-row'>
      <button class='btn btn-cron' onclick='callCron()'><span class='icon'>⚡</span>CRON<div id='cronStat' style='font-size:11px;margin-top:4px'>TAP TO SCAN</div></button>
      <button class='btn btn-close' onclick='closeAll()'><span class='icon'>💰</span>CLOSE ALL<div style='font-size:11px;margin-top:4px'>{len(open_tr)} OPEN</div></button>
      <button class='btn btn-reset' onclick='callReset()'><span class='icon'>🔄</span>RESET<div style='font-size:11px;margin-top:4px'>CAP $300</div></button>
    </div>
    <div class='g'>
      <div class='c'>CAP<br><b style='font-size:20px;color:#ffcc00'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}</div>
      <div class='c'>TODAY<br><b style='font-size:20px;color:{"#f44" if daily<0 else "#0f8"}'>${daily:+.2f}</b><br>W:{wins} L:{loss} {winrate}%<br>FEES ${fees_paid:.2f}</div>
      <div class='c'>MARKET<br><b>{market.get('regime')} {market.get('bias')}</b><br>BTC ${market.get('btc_price',0):.0f} RSI {market.get('rsi',50):.0f}<br><small>{market.get('reason','')[:52]}</small></div>
    </div>
    <div class='it' style='border-color:#00ff88;color:#00ff88;text-align:center;font-weight:900'>
      {market.get('reason','no market - tap CRON')} - Looking for RSI &lt;32 LONG / &gt;68 SHORT
      <br><small>Last scan: #{scan} | L:{long_open} S:{short_open}</small>
    </div>
    <div id='openbox'>"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class='it' style='border-color:{col}'>
          <div style='display:flex;justify-content:space-between;align-items:center'><b style='color:{col}'>{tr['symbol']} <span class='badge {tr.get('side','').lower()}'>{tr.get('side')}</span> {tr.get('sector')}</b>
          <button onclick='closeOne("{tr['symbol']}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 12px;font-weight:900'>✕</button></div>
          ENTRY ${tr.get('entry',0):.6f} -> NOW ${tr.get('price',0):.6f} POS ${tr.get('pos',0):.0f}<br>
          H1 {tr.get('h1',0):+.1f}% RSI {tr.get('rsi',0):.0f} AGE {tr.get('age',0)}s PEAK {tr.get('peak_gross',0):.2f}%<br>
          <b style='font-size:14px'>{tr.get('pct_gross',0):.3f}% GROSS {tr.get('pct',0):.3f}% NET ${tr.get('net',0):+.3f}</b> TP {tr.get('tp',0):.2f}% SL {tr.get('sl',0):.2f}%<br>
          <small style='color:#888'>{tr.get('reason','')}</small>
        </div>"""
    if not open_tr:
        html+=f"<div class='it' style='text-align:center;color:#666'>No open trades. Tap ⚡ CRON to find setups.</div>"
    html+=f"""</div>
    <div style='background:#111;padding:12px;margin:8px 0;border-radius:12px'>
      <div style='color:#ffcc00;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% - CAP ${cap:.2f} DAILY ${daily:+.2f}</div>"""
    for cl in closed[:20]:
        c="#0f8" if cl.get("net",0)>=0.05 else "#f44"
        html+=f"<div style='padding:6px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')} {cl.get('side','')}</b> ${cl.get('net',0):+.2f} {cl.get('reason','')} {cl.get('pct_gross',0):+.2f}%</div>"
    html+=f"""</div>
    <script>
    const ADMIN_KEY="{ADMIN_KEY}";
    async function callCron(){{
      const btn=document.getElementById('cronStat');
      btn.innerText='SCANNING...';
      try{{
        const r=await fetch('/api/cron?key='+ADMIN_KEY);
        const j=await r.json();
        if(j.ok){{ btn.innerText='OK SCAN #'+j.scan; setTimeout(()=>location.reload(), 1000); }}
        else{{ btn.innerText='PAUSED '+j.left+'s'; }}
      }}catch(e){{ btn.innerText='FAILED'; alert('Cron failed: '+e); }}
    }}
    async function callReset(){{
      if(!confirm('RESET? This wipes all trades and sets CAP to $300')) return;
      try{{
        const r=await fetch('/api/reset?key='+ADMIN_KEY);
        const j=await r.json();
        location.reload();
      }}catch(e){{ alert('Reset failed'); }}
    }}
    async function closeAll(){{
      if({len(open_tr)}==0){{ alert('No trades'); return; }}
      if(!confirm('Close all {len(open_tr)} trades?')) return;
      try{{ await fetch('/api/closeall?key='+ADMIN_KEY); location.reload(); }}catch(e){{ alert('Failed'); }}
    }}
    async function closeOne(sym){{
      if(!confirm('Close '+sym+'?')) return;
      try{{ await fetch('/api/close?symbol='+sym+'&key='+ADMIN_KEY); location.reload(); }}catch(e){{ alert('Close failed'); }}
    }}
    let autoCount=30;
    setInterval(()=>{{
      autoCount--;
      const el=document.getElementById('cronStat');
      if(el && el.innerText.includes('s auto') || el.innerText.includes('TAP') || el.innerText.includes('OK')){{
        el.innerText=autoCount+'s auto';
      }}
      if(autoCount<=0){{ autoCount=30; callCron(); }}
    }},1000);
    </script></body></html>"""
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
            return Response(json.dumps({"ok":False,"error":str(e)[:400]}), mimetype="application/json", status=200)
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            kv_del(STATE_KEY); time.sleep(0.6)
            new={"cap":300.0,"daily":0.0,"daily_gross":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}}
            ok=kv_set(STATE_KEY, new)
            return Response(json.dumps({"ok":ok,"cap":300}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)[:300]}), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            state=load_state(); cap=state.get("cap",300.0)
            for tr in state.get("open",[]):
                cap+=tr.get("net",0)
                state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"gross":tr.get("gross",0),"reason":"MANUAL CLOSE ALL","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0)})
            state["open"]=[]; state["cap"]=cap
            kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":True,"closed":"ALL","cap":cap}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)[:400]}), mimetype="application/json")
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            sym=request.args.get("symbol","")
            state=load_state(); cap=state.get("cap",300.0)
            final=[]
            for tr in state.get("open",[]):
                if tr["symbol"]==sym or sym=="":
                    if sym=="": continue
                    if tr["symbol"]==sym:
                        cap+=tr.get("net",0)
                        state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"gross":tr.get("gross",0),"reason":f"MANUAL CLOSE {sym}","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0)})
                        continue
                final.append(tr)
            if sym!="": state["open"]=final
            else: state["open"]=[] # closeall via same endpoint
            state["cap"]=cap
            kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":True,"closed":sym or "ALL","cap":cap}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)[:400]}), mimetype="application/json")
    try:
        st=load_state(); h=render(st); return Response(h, mimetype="text/html")
    except Exception as e:
        import traceback; tb=traceback.format_exc()[:800]
        return Response(f"<html><body><h1>Error: {str(e)[:500]}</h1><pre>{tb}</pre><p><a href='/api/reset?key={ADMIN_KEY}'>RESET</a></p></body></html>", mimetype="text/html", status=200)
