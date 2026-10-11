from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse, hmac, hashlib, math

app = Flask(__name__)

def env(n):
    for k in n:
        v=os.environ.get(k)
        if v: return v.strip().strip('"').strip("'")
    return ""
KV_URL=env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"])
if not KV_URL:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "URL" in kk and "upstash" in vv.lower():
            KV_URL=vv.strip().strip('"').strip("'").rstrip("/")
            break
KV_URL=KV_URL.rstrip("/") if KV_URL else ""
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
if not KV_TOKEN:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "TOKEN" in kk and "upstash" in kk.lower():
            KV_TOKEN=vv.strip().strip('"').strip("'")
            break
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
BINANCE_BASE=env(["BINANCE_BASE"]) or "https://testnet.binance.vision"
BINANCE_KEY=env(["BINANCE_API_KEY"])
BINANCE_SECRET=env(["BINANCE_API_SECRET"])
REAL_TRADING=env(["BINANCE_REAL_TRADING"]) or "true"
POS_SIZE=env(["POS_SIZE"]) or "100"
STATE_KEY="VENUS_V755_MERGED_HISTORY_100_REAL"
OLD_KEYS=["VENUS_V752_RESTORED_SMART_100_REAL","VENUS_V750_LEARNING_AI_100_REAL","VENUS_V754_PROFITABLE_LEARNING_100_REAL","VENUS_V756_SMART_KEEP_TRACK_100_REAL"]

# ========== v771 FINAL PRO - FIXES SCAN #950 BLEED ==========
TP_BASE = 1.6
SL_BASE = 0.70
FEE_PCT = 0.20
MAX_POS = 2
DAILY_STOP = -10.0

# BAN from your screenshots: ZRO -2.92% slippage, RLC -0.64%, WLD, FET
HARD_BAD = set(["ZRO","APT","WLD","FET","RLC","S","MBL","STRK","TIA","MAGIC","VELDROME","VELODROME","NIGHT","SENT","CHIP","CFX","币安人生","PEOPLE","TRB","BLZ","ARKM","LUNA","LUNC"])

def kv_get(k):
    if not KV_URL or not KV_TOKEN: return None
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d=json.loads(r.read().decode())
            res=d[0].get("result") if isinstance(d,list) and d else None
            if not res: return None
            return json.loads(res) if res.startswith("{") or res.startswith("[") else res
    except: return None

def kv_set(k,obj):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["SET",k,json.dumps(obj)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return "OK" in r.read().decode()
    except: return False

def binance_sign(params, secret):
    q=urllib.parse.urlencode(params)
    sig=hmac.new(secret.encode(), q.encode(), hashlib.sha256).hexdigest()
    params['signature']=sig
    return params

def binance_req(endpoint, key, secret, base, params={}, method="GET"):
    if not key or not secret: return None, "NO KEYS"
    params['timestamp']=int(time.time()*1000)
    params['recvWindow']=5000
    signed=binance_sign(params, secret)
    url=f"{base}{endpoint}?{urllib.parse.urlencode(signed)}"
    try:
        req=urllib.request.Request(url, headers={"X-MBX-APIKEY":key,"User-Agent":"Mozilla/5.0"}, method=method)
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        try: return None, f"HTTP {e.code}: {e.read().decode()[:400]}"
        except: return None, f"HTTP {e.code}"
    except Exception as e: return None, str(e)[:400]

def get_tickers():
    base="https://data-api.binance.vision"
    try:
        req=urllib.request.Request(f"{base}/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data=json.loads(r.read().decode())
            return data, base
    except: return [], base

def get_lot_size(symbol):
    try:
        req=urllib.request.Request(f"https://data-api.binance.vision/api/v3/exchangeInfo?symbol={symbol}", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data=json.loads(r.read().decode())
            for s in data.get("symbols",[]):
                for f in s.get("filters",[]):
                    if f.get("filterType")=="LOT_SIZE":
                        return float(f.get("stepSize","1")), float(f.get("minQty","0"))
    except: pass
    return 1.0, 0.0

def round_qty(qty, step):
    if step==0 or step==1: return int(qty)
    prec = int(round(-math.log10(step),0)) if step<1 else 0
    floored = math.floor(qty/step)*step
    if prec>0: return round(floored, prec)
    return int(floored)

def load_state():
    s=kv_get(STATE_KEY)
    if not s or s.get("total",0) < 5:
        for ok in OLD_KEYS:
            os_state=kv_get(ok)
            if os_state and isinstance(os_state, dict) and os_state.get("total",0)>0:
                if not s or os_state.get("total",0) > s.get("total",0):
                    s=os_state
    if not s: s={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"buckets":{},"tp_sl":{},"pause_until":0,"consecutive_losses":0}}
    if "learn" not in s: s["learn"]={"coins":{},"blacklist":{},"buckets":{},"tp_sl":{},"pause_until":0,"consecutive_losses":0}
    L=s["learn"]
    L.setdefault("coins",{})
    L.setdefault("blacklist",{})
    L.setdefault("buckets",{})
    L.setdefault("tp_sl",{})
    L.setdefault("pause_until",0)
    L.setdefault("consecutive_losses",0)
    now=int(time.time())
    L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}
    return s

def update_learn(state, symbol, net, pct, features):
    L=state["learn"]
    coins=L["coins"]
    c=coins.setdefault(symbol, {"w":0,"l":0,"pnl":0.0,"avg_win":0.8,"avg_loss":0.6,"ev":0.0,"wr":0.0})
    if net>0:
        c["w"]+=1
        c["avg_win"]=c["avg_win"]*0.85 + pct*0.15 if c["w"]>1 else pct
        L["consecutive_losses"]=0
    else:
        c["l"]+=1
        c["avg_loss"]=c["avg_loss"]*0.85 + abs(pct)*0.15 if c["l"]>1 else abs(pct)
        L["consecutive_losses"]+=1
    c["pnl"]+=net
    total=c["w"]+c["l"]
    if total>=3:
        wr=c["w"]/total
        c["wr"]=wr
        ev_pct = (wr * c["avg_win"]) - ((1-wr) * c["avg_loss"]) - FEE_PCT
        c["ev"]=max(-2.0, min(2.0, ev_pct))
    
    # buckets
    for bf in features:
        b=L["buckets"].setdefault(bf, {"w":0,"l":0,"ev":0.0,"avg_win":0.6,"avg_loss":0.6})
        if net>0:
            b["w"]+=1
            b["avg_win"]=b["avg_win"]*0.9 + pct*0.1 if b["w"]>1 else pct
        else:
            b["l"]+=1
            b["avg_loss"]=b["avg_loss"]*0.9 + abs(pct)*0.1 if b["l"]>1 else abs(pct)
        tot=b["w"]+b["l"]
        if tot>=5:
            wr=b["w"]/tot
            ev= (wr*b["avg_win"]) - ((1-wr)*b["avg_loss"]) - FEE_PCT
            b["ev"]=max(-2.0, min(2.0, ev))

    # auto ban - from your ZRO -15
    if c["pnl"]<-8 or (total>=8 and c["ev"]<-0.2):
        L["blacklist"][symbol]=int(time.time())+86400*7
    if net<-2.0: # big slippage like ZRO -2.92
        L["blacklist"][symbol]=int(time.time())+86400*2

    if L["consecutive_losses"]>=4:
        L["pause_until"]=int(time.time())+10800
    if state.get("daily",0) <= DAILY_STOP:
        L["pause_until"]=int(time.time())+14400

def get_ev(state, symbol, bucket):
    coin=state["learn"]["coins"].get(symbol)
    buck=state["learn"]["buckets"].get(bucket)
    if coin and coin.get("w",0)+coin.get("l",0)>=5:
        return coin.get("ev",0.0)
    if buck and buck.get("w",0)+buck.get("l",0)>=5:
        return buck.get("ev",0.0)
    # defaults based on your GOOD/BAD
    if symbol=="LUMIA": return 0.65
    if symbol in ["MANTA","ARB","NIL","AERO","EIGEN"]: return 0.15
    return -0.1

def score_ticker(t, state, hour):
    try:
        sym=t.get("symbol","")
        if not sym.endswith("USDT"): return None
        base=sym.replace("USDT","")
        if base in HARD_BAD: return None
        if not base.isalnum(): return None
        if any(ord(c)>127 for c in base): return None
        if len(base)<2 or len(base)>8: return None
        if "UP" in sym or "DOWN" in sym or "BULL" in sym or "BEAR" in sym: return None
        price=float(t.get("lastPrice","0"))
        # v771 FIX 1: PRICE FILTER - no ZRO $2.08
        if price<0.005 or price>1.5: return None
        h1=float(t.get("priceChangePercent","0"))
        vol=float(t.get("quoteVolume","0"))
        # v771 FIX 2: TIGHT EARLY 3-8% ONLY, not 2-14%
        if h1<3.0 or h1>8.0: return None
        if vol<14_000_000: return None  # need liquidity
        high=float(t.get("highPrice","0"))
        low=float(t.get("lowPrice","0"))
        if high==0 or low==0: return None
        from_low=(price-low)/low*100 if low>0 else 0
        if from_low<3.0 or from_low>8.5: return None
        near_high=price/high*100
        if near_high<97.0: return None
        qty_est=100.0/price if price>0 else 0
        if qty_est<80: return None  # price too high
        
        bucket=f"H{int(h1)}_FL{int(from_low)}_V{int(vol/1e6)}M"
        ev=get_ev(state, base, bucket)
        # v771 FIX 3: EV FILTER >0.40% real, not fake +10%
        if base!="LUMIA" and ev<0.35:
            # allow only if very early 3-5%
            if not (h1<=5.5 and from_low<=5.5 and vol>=18_000_000):
                return None
        
        bonus=15.0 if base=="LUMIA" else (3.0 if base in ["MANTA","ARB","NIL"] else 1.0)
        score=ev*1000 + h1*(vol/1e6)*bonus
        tp_sl=state["learn"]["tp_sl"].get(base, {"tp":TP_BASE,"sl":SL_BASE})
        return {"symbol":base,"full":sym,"h1":h1,"price":price,"vol":int(vol),"score":score,"tier":"GOOD" if base=="LUMIA" else "PRO","from_low":from_low,"near_high":near_high,"bucket":bucket,"ev":ev,"tp":tp_sl.get("tp",TP_BASE),"sl":tp_sl.get("sl",SL_BASE)}
    except: return None

def do_cron():
    state=load_state()
    L=state["learn"]
    now_ts=int(time.time())
    hour=time.gmtime().tm_hour
    
    if L.get("pause_until",0) > now_ts:
        return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"scan":state.get("scan",0),"daily":state.get("daily",0),"v":"v771 PAUSED"}
    
    if state.get("daily",0) <= DAILY_STOP:
        L["pause_until"]=now_ts+14400
        kv_set(STATE_KEY, state)
        return {"ok":False,"paused":True,"reason":f"Daily stop {DAILY_STOP} hit","daily":state.get("daily",0)}

    tickers, base_url = get_tickers()
    pumps=[]
    for t in tickers:
        s=score_ticker(t, state, hour)
        if s: pumps.append(s)
    pumps=sorted(pumps, key=lambda x: (x["ev"], x["score"]), reverse=True)[:5]
    for i,p in enumerate(pumps): p["id"]=i+1

    open_tr=state.get("open",[])
    closed=state.get("closed",[])
    real_orders=state.get("real_orders",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    wins=state.get("wins",0)
    loss=state.get("loss",0)
    tot=state.get("total",0)
    scan=state.get("scan",0)+1

    # Close logic - FIXED TRAIL
    new_open=[]
    for tr in open_tr:
        try:
            sym_full=tr["symbol"]+"USDT"
            price_now=tr["price"]
            for tk in tickers:
                if tk.get("symbol")==sym_full:
                    price_now=float(tk.get("lastPrice",tr["price"]))
                    break
            entry=tr["entry"]
            pct=(price_now-entry)/entry*100 if entry else 0
            age=now_ts - tr.get("ts",now_ts)
            peak=max(tr.get("peak",0), pct)
            tr["price"]=price_now
            tr["pct"]=pct
            tr["peak"]=peak
            tr["age"]=age
            tr["net"]=float(POS_SIZE)*pct/100
            tp=tr.get("tp",TP_BASE)
            sl=tr.get("sl",SL_BASE)
            should=None
            if pct>=tp:
                should=f"TP {tp:.1f}% PRO +{pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f} EV{tr.get('ev',0):+.2f}"
            elif pct<=-sl:
                should=f"SL -{sl:.2f}% {pct:.1f}% ${float(POS_SIZE)*pct/100:+.2f}"
            elif peak>=0.9 and pct < peak-0.22:
                if pct>0.50:
                    should=f"TRAIL lock +{peak:.1f}% peak-0.22% {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            elif age>900 and pct>0.55:
                should=f"TIME WIN 900s {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            
            if should:
                net=float(POS_SIZE)*pct/100
                cap+=net
                daily+=net
                if net>0: wins+=1
                else: loss+=1
                tot+=1
                closed.insert(0, {"symbol":tr["symbol"],"net":net,"reason":should,"pct":pct,"pos":tr.get("pos"),"age":age,"bucket":tr.get("bucket",""),"ev":tr.get("ev",0)})
                update_learn(state, tr["symbol"], net, pct, [tr.get("bucket",""), f"COIN_{tr['symbol']}"])
                if REAL_TRADING=="true" and BINANCE_KEY and BINANCE_SECRET:
                    qty=tr.get("qty",0)
                    if qty>0:
                        data,err=binance_req("/api/v3/order", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, {"symbol":sym_full,"side":"SELL","type":"MARKET","quantity":qty}, method="POST")
                        real_orders.insert(0, {"side":"SELL","symbol":sym_full,"price":price_now,"pos":tr.get("pos"),"result":str(data)[:200] if data else err})
            else:
                new_open.append(tr)
        except:
            new_open.append(tr)

    # FIXED: check MAX before buy, not after
    open_symbols=[t["symbol"] for t in new_open]
    for fp in pumps:
        if len(new_open)>=MAX_POS: break
        sym=fp["symbol"]
        if sym in open_symbols: continue
        if sym in state["learn"]["blacklist"]: continue
        if fp["ev"]<0.30 and sym!="LUMIA": continue
        price=fp["price"]
        pos=float(POS_SIZE)
        qty=pos/price if price>0 else 0
        step,_=get_lot_size(sym+"USDT")
        qty=round_qty(qty, step)
        if qty<=0 or qty<80: continue
        tr={"symbol":sym,"entry":price,"price":price,"pos":pos,"qty":qty,"ts":now_ts,"peak":0,"pct":0,"net":0,"age":0,"h1":fp["h1"],"tier":fp["tier"],"bucket":fp["bucket"],"ev":fp["ev"],"tp":fp["tp"],"sl":fp["sl"]}
        new_open.append(tr)
        open_symbols.append(sym)
        if REAL_TRADING=="true" and BINANCE_KEY and BINANCE_SECRET:
            data,err=binance_req("/api/v3/order", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, {"symbol":sym+"USDT","side":"BUY","type":"MARKET","quantity":qty}, method="POST")
            real_orders.insert(0, {"side":"BUY","symbol":sym+"USDT","price":price,"pos":pos,"result":str(data)[:200] if data else err})

    state["open"]=new_open
    state["closed"]=closed[:200]
    state["real_orders"]=real_orders[:50]
    state["cap"]=cap
    state["daily"]=daily
    state["wins"]=wins
    state["loss"]=loss
    state["total"]=tot
    state["scan"]=scan
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan,"open":len(new_open),"pumps":pumps[:3],"cap":cap,"daily":daily,"total":tot,"v":"v771 FINAL PRO","ev":state["learn"]["coins"].get("LUMIA",{}).get("ev",0)}

def render(state):
    open_tr=state.get("open",[])
    closed=state.get("closed",[])
    real_orders=state.get("real_orders",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    wins=state.get("wins",0)
    loss=state.get("loss",0)
    tot=state.get("total",0)
    scan=state.get("scan",0)
    learn=state.get("learn",{})
    winrate=int(wins/(tot)*100) if tot>0 else 0
    unreal=sum([t.get("net",0) for t in open_tr])
    bl=learn.get("blacklist",{})
    coins=learn.get("coins",{})
    best=sorted([(k,v) for k,v in coins.items() if v.get("ev",0)>0.3], key=lambda x: x[1]["ev"], reverse=True)[:2]
    worst=sorted([(k,v) for k,v in coins.items() if v.get("ev",0)<-0.1], key=lambda x: x[1]["ev"])[:3]
    learn_txt=f"v771 FINAL PRO: TP {TP_BASE}% SL {SL_BASE}% MAX {MAX_POS} DAILY STOP {DAILY_STOP} BL:{len(bl)} "
    if best: learn_txt+=" | GOOD EV: " + ", ".join([f"{k} EV+{v['ev']*100:.1f}% {v['w']}W{v['l']}L +${v['pnl']:.1f}" for k,v in best])
    if worst: learn_txt+=" | BAD: " + ", ".join([f"{k} EV{v['ev']*100:.1f}% ${v['pnl']:.1f}" for k,v in worst])
    if learn.get("pause_until",0)>int(time.time()):
        learn_txt+=f" | PAUSED {int((learn['pause_until']-time.time())/60)}m"

    hour=time.gmtime().tm_hour
    tickers,_=get_tickers()
    pumps=[]
    for t in tickers:
        s=score_ticker(t, state, hour)
        if s: pumps.append(s)
    pumps=sorted(pumps, key=lambda x: x["ev"], reverse=True)[:5]
    for i,p in enumerate(pumps): p["id"]=i+1

    html=f"""<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{{background:#000;color:#0f8;font-family:monospace;font-size:11px;margin:0;padding:4px}} .foot{{border:1px solid #333;padding:6px;margin:4px 0;background:#0a0a0a}} .bigrow{{display:flex;gap:4px}} .bigbox{{flex:1;border:1px solid #333;padding:6px;text-align:center;background:#111}} .yellowbar{{background:#ffcc00;color:#000;padding:6px;font-weight:bold;margin:4px 0;font-size:10px}} .pro{{background:#001a33;border:1px solid #0ff;padding:6px;margin:4px}}</style></head><body>
<div style="text-align:center;padding:6px;font-size:14px;font-weight:bold;color:#ffcc00">VENUS v771 FINAL PRO LUMIA ONLY $300 REAL - SCAN #{scan} - {MAX_POS} MAX - POS ${POS_SIZE} - PRICE <1.5 ONLY</div>
<div class="bigrow"><div class="bigbox"><div style="font-size:10px;color:#aaa">CAP $300 REAL</div><div style="font-size:26px;font-weight:bold;color:#ffcc00">${cap:.2f}</div><div style="font-size:10px;color:#aaa">WITH OPEN {cap+unreal:.2f}</div></div><div class="bigbox"><div style="font-size:10px;color:#aaa">TODAY / $50</div><div style="font-size:26px;font-weight:bold;color:{'#0f8' if daily>=0 else '#f44'}">${daily:+.2f}</div><div style="font-size:10px;color:#aaa">STOP {DAILY_STOP} | CONSEC {learn.get('consecutive_losses',0)} | PAUSE {int((learn.get('pause_until',0)-time.time())/60) if learn.get('pause_until',0)>time.time() else 0}m</div></div><div class="bigbox"><div style="font-size:10px;color:#aaa">WIN {winrate}% EV</div><div style="font-size:18px;font-weight:bold;color:#0f8">W:{wins} L:{loss}<br>T:{tot}</div><div style="font-size:10px;color:#aaa">FINAL PRO - EV>0.40% - {MAX_POS} MAX</div></div></div>
<div class="pro"><div style="color:#0ff;font-size:10px">{learn_txt}</div></div>
<div class="yellowbar">PRO PUMP HUNTER {len(pumps)} - TOP {pumps[0]['symbol']+' +'+str(round(pumps[0]['h1'],1))+'% EV+'+str(round(pumps[0]['ev']*100,1))+'% '+pumps[0].get('bucket','') if pumps else 'NO +EV PUMPS - WAITING LUMIA 3-5%'} - EV >0.40% - PRICE<1.5 VOL>14M</div>"""
    for fp in pumps[:5]:
        col="#ffcc00" if fp['symbol']=="LUMIA" else ("#0ff" if fp['ev']>0.4 else "#888")
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:{col};font-weight:bold">{fp.get('tier','')} #{fp['id']} {fp['symbol']} H1 +{fp['h1']:.1f}% EV +{fp['ev']*100:.2f}% {fp.get('bucket','')}</span><br><span style="color:#0f8">VOL ${fp['vol']} PRICE ${fp['price']:.6f} SCORE {fp['score']:.1f} NEAR_HIGH {fp.get('near_high',0):.1f}% FROM_LOW {fp.get('from_low',0):.1f}%</span><br><span style="color:#ffcc00">POS ${POS_SIZE} TP {fp.get('tp',TP_BASE):.1f}% | SL {fp.get('sl',SL_BASE):.2f}% | EV +{fp['ev']*100:.2f}% QTY {int(100/fp['price']) if fp['price']>0 else 0}</span></div>"""
    html+=f"""<div class="yellowbar">OPEN {len(open_tr)}/{MAX_POS} MAX FINAL PRO - TP {TP_BASE}% | SL {SL_BASE}% | TRAIL 0.9%->0.22% lock +0.68% - DAILY STOP {DAILY_STOP}</div>"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:{'#ffcc00' if tr.get('tier')=='GOOD' else '#0ff'};font-weight:bold">FINAL {tr['symbol']} ${tr.get('pos')} EV +{tr.get('ev',0)*100:.2f}% AGE {tr.get('age',0)}s</span><br><span style="color:#0f8">ENTRY ${tr['entry']:.6f} -> NOW ${tr['price']:.6f} PEAK {tr.get('peak',0):.1f}% H1 {tr.get('h1',0):+.1f}% BUCKET {tr.get('bucket','')}</span><br><span style="color:{col};font-size:18px;font-weight:bold">{tr.get('pct',0):+.2f}% ${tr.get('net',0):+.2f} REAL</span><br><span style="font-size:9px;color:#aaa">TP {tr.get('tp',TP_BASE):.1f}% | SL {tr.get('sl',SL_BASE):.2f}% | TRAIL peak-0.22% | QTY {tr.get('qty',0)}</span></div>"""
    html+=f"""<div style="padding:6px"><div style="color:#ffcc00;font-weight:bold;font-size:12px">CLOSED {len(closed)} - W:{wins} L:{loss} T:{tot} CAP ${cap:.2f} DAILY ${daily:+.2f} / $50 - FINAL PRO</div>"""
    for cl in closed[:12]:
        ccol="#0f8" if cl["net"]>0 else "#f44"
        html+=f"""<div style="color:{ccol};padding:3px;border-bottom:1px solid #222;font-size:11px"><b>{cl['symbol']}</b> ${cl['net']:+.2f} {cl['reason']} {cl['pct']:+.1f}% EV {cl.get('ev',0)*100:+.1f}% AGE {cl['age']}s</div>"""
    html+=f"""</div><div style="text-align:center;padding:10px;color:#555;font-size:10px">v771 FINAL PRO - PRICE <1.5 VOL>14M 3-8% ONLY - TP {TP_BASE}% SL {SL_BASE}% - 2 MAX - DAILY STOP {DAILY_STOP} - <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON PRO</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#f44">RESET $300</a></div><div style="text-align:center;padding:12px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:12px 20px;text-decoration:none;font-weight:bold;font-size:12px">CRON v771 FINAL - CAP ${cap:.2f} DAILY ${daily:+.2f}/$50 - {len(pumps)} PUMPS</a></div></body></html>"""
    return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    key=request.args.get("key","")
    p="/"+path
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY and "cron" not in request.args: return Response("Forbidden", status=403)
        res=do_cron()
        return Response(json.dumps(res), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_set(STATE_KEY,{"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"buckets":{},"tp_sl":{},"pause_until":0,"consecutive_losses":0}})
        return Response(json.dumps({"ok":True,"cap":300}), mimetype="application/json")
    st=load_state()
    h=render(st)
    return Response(h, mimetype="text/html")
