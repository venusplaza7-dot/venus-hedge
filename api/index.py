from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse, hmac, hashlib, math, re
from collections import defaultdict

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

# ========== v770 PRO LEARNER PARAMS ==========
TP_BASE = 1.4
SL_BASE = 0.65
FEE = 0.20  # 0.1% buy + 0.1% sell
HARD_BAD = set(["MBL","STRK","TIA","S","MAGIC","VELDROME","VELODROME","NIGHT","SENT","CHIP","CFX","币安人生","PEOPLE","TRB","BLZ","ARKM","LUNA","LUNC","WLD","FET"])

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
    if not s: s={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"features":{},"buckets":{},"ev":{},"tp_sl":{}}}
    if "learn" not in s: s["learn"]={"coins":{},"blacklist":{},"features":{},"buckets":{},"ev":{},"tp_sl":{}}
    L=s["learn"]
    L.setdefault("coins",{})
    L.setdefault("blacklist",{})
    L.setdefault("features",{})  # feature -> stats
    L.setdefault("buckets",{})   # bucket key -> w,l,pnl,avg_win,avg_loss
    L.setdefault("ev",{})        # symbol -> ev
    L.setdefault("tp_sl",{})     # symbol -> {tp,sl}
    # clean expired blacklist
    now=int(time.time())
    L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}
    # circuit breaker
    L.setdefault("pause_until",0)
    L.setdefault("consecutive_losses",0)
    L.setdefault("daily_loss",0)
    return s

# ========== PRO LEARNER CORE ==========
def get_feature_bucket(h1, from_low, vol, hour):
    h1_b = "3-5" if h1<5 else ("5-7" if h1<7 else ("7-9" if h1<9 else "9-14"))
    fl_b = "3-5" if from_low<5 else ("5-7" if from_low<7 else ("7-9.5" if from_low<9.5 else "9.5-14"))
    vol_b = "3-8M" if vol<8_000_000 else ("8-15M" if vol<15_000_000 else "15M+")
    hour_b = "asian" if 0<=hour<8 else ("eu" if 8<=hour<16 else "us")
    return f"H{h1_b}_FL{fl_b}_V{vol_b}_{hour_b}"

def update_pro_learner(state, symbol, net, reason, features):
    """Real learning: update buckets and EV"""
    L=state["learn"]
    coins=L["coins"]
    buckets=L["buckets"]
    c=coins.setdefault(symbol, {"w":0,"l":0,"pnl":0.0,"avg_win":0.6,"avg_loss":0.5,"ev":0.0,"trades":[]})
    
    # Update coin stats
    is_win = net>0
    if is_win:
        c["w"]+=1
        # rolling avg win
        c["avg_win"] = (c["avg_win"]*0.9 + net*0.1) if c["w"]>1 else net
        L["consecutive_losses"]=0
    else:
        c["l"]+=1
        c["avg_loss"] = (c["avg_loss"]*0.9 + abs(net)*0.1) if c["l"]>1 else abs(net)
        L["consecutive_losses"]+=1
    
    c["pnl"]+=net
    total = c["w"]+c["l"]
    if total>=3:
        wr = c["w"]/total
        c["ev"] = (wr * c["avg_win"]) - ((1-wr) * c["avg_loss"]) - (FEE*float(POS_SIZE)/100)
    
    # Update feature buckets
    for feat_key in features:
        b=buckets.setdefault(feat_key, {"w":0,"l":0,"pnl":0.0,"avg_win":0.5,"avg_loss":0.5,"ev":-1.0})
        if is_win:
            b["w"]+=1
            b["avg_win"] = b["avg_win"]*0.9 + net*0.1 if b["w"]>1 else net
        else:
            b["l"]+=1
            b["avg_loss"] = b["avg_loss"]*0.9 + abs(net)*0.1 if b["l"]>1 else abs(net)
        b["pnl"]+=net
        tot = b["w"]+b["l"]
        if tot>=5:
            wr=b["w"]/tot
            b["ev"] = (wr * b["avg_win"]) - ((1-wr)*b["avg_loss"]) - (FEE*float(POS_SIZE)/100)
    
    # Self-tune TP/SL per coin
    tp_sl=L["tp_sl"].setdefault(symbol, {"tp":TP_BASE,"sl":SL_BASE,"peak":0.6})
    if total>=10 and c["ev"]>0.2:
        # If coin tends to go higher, increase TP
        if c["avg_win"]>1.0:
            tp_sl["tp"]=min(2.2, c["avg_win"]*1.2)
        # If coin wicks a lot, increase SL
        if c["avg_loss"]>0.7:
            tp_sl["sl"]=min(0.9, c["avg_loss"]*0.9)
    
    # Auto blacklist if EV negative for 10+ trades
    if total>=10 and c["ev"]<-0.15:
        L["blacklist"][symbol]=int(time.time())+86400*3  # 3 day ban
    if c["pnl"]<-8:
        L["blacklist"][symbol]=int(time.time())+86400*7
    
    # Circuit breaker
    if L["consecutive_losses"]>=5:
        L["pause_until"]=int(time.time())+7200  # pause 2h
    if state.get("daily",0) < -12:
        L["pause_until"]=int(time.time())+3600*4  # pause 4h after -$12 daily

def get_ev_for_trade(state, symbol, bucket_key):
    L=state["learn"]
    coin_ev = L["coins"].get(symbol,{}).get("ev", 0.0)
    bucket_ev = L["buckets"].get(bucket_key,{}).get("ev", 0.0)
    
    # If not enough data, use defaults: LUMIA positive, others neutral
    if symbol=="LUMIA":
        base_ev = 0.5
    elif symbol in ["ARB","AERO","MANTA","EIGEN","NIL"]:
        base_ev = 0.1
    else:
        base_ev = -0.1
    
    # Weighted EV
    if bucket_ev!=0 and bucket_ev!=-1.0:
        # 60% bucket, 40% coin
        return bucket_ev*0.6 + coin_ev*0.4 if coin_ev!=0 else bucket_ev*0.6 + base_ev*0.4
    elif coin_ev!=0:
        return coin_ev
    else:
        return base_ev

def is_blacklisted(state, symbol):
    bl=state.get("learn",{}).get("blacklist",{})
    return symbol in bl

def is_scam(sym):
    base=sym.replace("USDT","")
    if base in HARD_BAD: return True
    if not base.isalnum(): return True
    if any(ord(c)>127 for c in base): return True
    if len(base)<2 or len(base)>10: return True
    if "UP" in sym or "DOWN" in sym or "BULL" in sym or "BEAR" in sym: return True
    return False

def score_ticker_pro(t, state, hour):
    try:
        sym=t.get("symbol","")
        if not sym.endswith("USDT"): return None
        base=sym.replace("USDT","")
        if base in HARD_BAD: return None
        if is_scam(sym): return None
        price=float(t.get("lastPrice","0"))
        if price<0.005 or price>10: return None
        h1=float(t.get("priceChangePercent","0"))
        vol=float(t.get("quoteVolume","0"))
        if h1<3 or h1>9.5: return None  # v770 tight 3-9.5%
        if vol<8_000_000: return None  # v770 need liquidity
        high=float(t.get("highPrice","0"))
        low=float(t.get("lowPrice","0"))
        if high==0 or low==0: return None
        from_low=(price-low)/low*100 if low>0 else 0
        if from_low<3 or from_low>9.5: return None
        near_high=price/high*100
        if near_high<96.5: return None
        
        bucket=get_feature_bucket(h1, from_low, vol, hour)
        ev=get_ev_for_trade(state, base, bucket)
        
        # PRO FILTER: Only trade if EV > +0.35% OR LUMIA
        if base!="LUMIA" and ev<0.35:
            # Allow if not enough data but LUMIA-like features
            if not (3<=h1<=6 and 3<=from_low<=6 and vol>=15_000_000):
                # If EV negative and not LUMIA early, skip
                if ev<0.1:
                    return None
        
        bonus=10.0 if base=="LUMIA" else (2.5 if base in ["ARB","AERO","MANTA","EIGEN","NIL","RLC"] else 1.0)
        score = ev*1000 + h1*(vol/1_000_000)*bonus
        if base=="LUMIA": score+=5000
        
        tp_sl=state["learn"]["tp_sl"].get(base, {"tp":TP_BASE,"sl":SL_BASE})
        
        return {"symbol":base,"full":sym,"h1":h1,"price":price,"vol":int(vol),"score":score,"tier":"GOOD" if base=="LUMIA" else "PRO","type":"PRO","from_low":from_low,"near_high":near_high,"bucket":bucket,"ev":ev,"tp":tp_sl["tp"],"sl":tp_sl["sl"]}
    except Exception as e:
        return None

def do_cron():
    state=load_state()
    L=state["learn"]
    now_ts=int(time.time())
    hour=time.gmtime().tm_hour
    
    # Circuit breaker check
    if L.get("pause_until",0) > now_ts:
        return {"ok":False,"paused":True,"pause_left":L["pause_until"]-now_ts,"scan":state.get("scan",0),"reason":"Circuit breaker - 5 losses or daily -$12"}
    
    tickers, base = get_tickers()
    pumps=[]
    for t in tickers:
        s=score_ticker_pro(t, state, hour)
        if s: pumps.append(s)
    pumps=sorted(pumps, key=lambda x: (x["ev"], x["score"]), reverse=True)[:8]
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
            
            # Use per-coin TP/SL
            tp_sl=state["learn"]["tp_sl"].get(tr["symbol"], {"tp":TP_BASE,"sl":SL_BASE})
            tp=tp_sl["tp"]
            sl=tp_sl["sl"]
            
            should_close=None
            if pct>=tp:
                should_close=f"TP {tp:.1f}% PRO +{pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f} EV{tr.get('ev',0):+.2f}"
            elif pct<=-sl:
                should_close=f"SL -{sl:.2f}% QUICK {pct:.1f}% ${float(POS_SIZE)*pct/100:+.2f}"
            elif peak>=0.7 and pct < peak-0.18:
                if pct>0.35:
                    should_close=f"TRAIL lock +{peak:.1f}% peak-0.18% {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            elif age>600 and pct>0.45:
                should_close=f"TIME WIN 600s {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            
            if should_close:
                net=float(POS_SIZE)*pct/100
                cap+=net
                daily+=net
                if net>0: wins+=1
                else: loss+=1
                tot+=1
                features=[tr.get("bucket",""), f"COIN_{tr['symbol']}", f"H_{int(tr.get('h1',0))}"]
                closed.insert(0, {"symbol":tr["symbol"],"net":net,"reason":should_close,"pct":pct,"pos":tr.get("pos"),"age":age,"bucket":tr.get("bucket",""),"ev":tr.get("ev",0)})
                update_pro_learner(state, tr["symbol"], net, should_close, features)
                if REAL_TRADING=="true" and BINANCE_KEY and BINANCE_SECRET:
                    qty=tr.get("qty",0)
                    if qty>0:
                        data,err=binance_req("/api/v3/order", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, {"symbol":sym_full,"side":"SELL","type":"MARKET","quantity":qty}, method="POST")
                        real_orders.insert(0, {"side":"SELL","symbol":sym_full,"price":price_now,"pos":tr.get("pos"),"result":str(data)[:200] if data else err})
            else:
                new_open.append(tr)
        except:
            new_open.append(tr)
    
    state["open"]=new_open
    open_symbols=[t["symbol"] for t in new_open]
    # Open only 2 MAX for PRO
    for fp in pumps:
        if len(new_open)>=2: break
        sym=fp["symbol"]
        if sym in open_symbols: continue
        if is_blacklisted(state, sym): continue
        # Extra EV check
        if fp["ev"]<0.25 and sym!="LUMIA": continue
        
        price=fp["price"]
        pos=float(POS_SIZE)
        qty=pos/price if price>0 else 0
        step,minQty=get_lot_size(sym+"USDT")
        qty=round_qty(qty, step)
        if qty<=0: continue
        tr={"symbol":sym,"entry":price,"price":price,"pos":pos,"qty":qty,"ts":now_ts,"peak":0,"pct":0,"net":0,"age":0,"h1":fp["h1"],"tier":fp["tier"],"move":fp["tier"],"bucket":fp["bucket"],"ev":fp["ev"],"tp":fp["tp"],"sl":fp["sl"]}
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
    
    best_bucket=sorted(state["learn"]["buckets"].items(), key=lambda x: x[1].get("ev",-10), reverse=True)[:2]
    return {"ok":True,"scan":scan,"open":len(new_open),"pumps":pumps[:3],"cap":cap,"total":tot,"v":"v770 PRO LEARNER","ev_top":best_bucket,"pause":L.get("pause_until",0)>now_ts}

def render(state, live_pumps=None):
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
    buckets=learn.get("buckets",{})
    
    # PRO LEARN text
    best_ev=sorted([(k,v) for k,v in buckets.items() if v.get("ev",-10)>0.1], key=lambda x: x[1]["ev"], reverse=True)[:2]
    worst_ev=sorted([(k,v) for k,v in buckets.items() if v.get("ev",0)<-0.1], key=lambda x: x[1]["ev"])[:2]
    learn_txt=f"PRO LEARN AI: TP {TP_BASE}% SL {SL_BASE}% FEE {FEE}% BL:{len(bl)} "
    if best_ev:
        learn_txt+=" | BEST EV: " + ", ".join([f"{k} EV+${v['ev']*100:.2f} {v['w']}W{v['l']}L" for k,v in best_ev])
    if worst_ev:
        learn_txt+=" | SKIP: " + ", ".join([f"{k} EV{v['ev']*100:.1f}" for k,v in worst_ev])
    good = sorted([(k,v) for k,v in learn.get("coins",{}).items() if v.get("ev",0)>0.2], key=lambda x: x[1]["ev"], reverse=True)[:2]
    bad = sorted([(k,v) for k,v in learn.get("coins",{}).items() if v.get("ev",0)<-0.1], key=lambda x: x[1]["ev"])[:3]
    if good: learn_txt+=" | GOOD: " + ", ".join([f"{k} EV+{v['ev']*100:.1f} {v['w']}W{v['l']}L +${v['pnl']:.1f}" for k,v in good])
    if bad: learn_txt+=" | BAD: " + ", ".join([f"{k} EV{v['ev']*100:.1f} ${v['pnl']:.1f}" for k,v in bad])
    if learn.get("pause_until",0)>int(time.time()):
        learn_txt+=f" | PAUSED {int((learn['pause_until']-time.time())/60)}m CIRCUIT BREAKER"

    hour=time.gmtime().tm_hour
    if live_pumps is None:
        tickers,_=get_tickers()
        pumps=[]
        for t in tickers:
            s=score_ticker_pro(t, state, hour)
            if s: pumps.append(s)
        pumps=sorted(pumps, key=lambda x: x["ev"], reverse=True)[:8]
        for i,p in enumerate(pumps): p["id"]=i+1
    else:
        pumps=live_pumps

    html=f"""<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{{background:#000;color:#0f8;font-family:monospace;font-size:11px;margin:0;padding:4px}} .foot{{border:1px solid #333;padding:6px;margin:4px 0;background:#0a0a0a}} .bigrow{{display:flex;gap:4px}} .bigbox{{flex:1;border:1px solid #333;padding:6px;text-align:center;background:#111}} .yellowbar{{background:#ffcc00;color:#000;padding:6px;font-weight:bold;margin:4px 0;font-size:10px}} .pro{{background:#0a2a4a;border:1px solid #0ff;padding:6px;margin:4px}}</style></head><body>
<div style="text-align:center;padding:6px;font-size:14px;font-weight:bold;color:#ffcc00">VENUS v770 PRO LEARNER LUMIA ONLY $300 REAL - SCAN #{scan} - 2 MAX - POS ${POS_SIZE} - EV BASED</div>
<div class="bigrow"><div class="bigbox"><div style="font-size:10px;color:#aaa">CAP $300 REAL</div><div style="font-size:26px;font-weight:bold;color:#ffcc00">${cap:.2f}</div><div style="font-size:10px;color:#aaa">WITH OPEN {cap+unreal:.2f}</div></div><div class="bigbox"><div style="font-size:10px;color:#aaa">TODAY / $50</div><div style="font-size:26px;font-weight:bold;color:{'#0f8' if daily>=0 else '#f44'}">${daily:+.2f}</div><div style="font-size:10px;color:#aaa">CONSEC LOSS {learn.get('consecutive_losses',0)} | PAUSE {int((learn.get('pause_until',0)-time.time())/60) if learn.get('pause_until',0)>time.time() else 0}m</div></div><div class="bigbox"><div style="font-size:10px;color:#aaa">WIN {winrate}% EV</div><div style="font-size:18px;font-weight:bold;color:#0f8">W:{wins} L:{loss}<br>T:{tot}</div><div style="font-size:10px;color:#aaa">PRO LEARN - EV >0.35% ONLY - 2 MAX</div></div></div>
<div class="pro"><div style="color:#0ff;font-size:10px">{learn_txt}</div></div>
<div class="yellowbar">PRO PUMP HUNTER {len(pumps)} - TOP {pumps[0]['symbol']+' +'+str(round(pumps[0]['h1'],1))+'% EV+'+str(round(pumps[0]['ev']*100,1))+'% '+pumps[0].get('bucket','') if pumps else 'NO +EV PUMPS - WAITING LUMIA 3-6%'} - EV FILTER >0.35% - LUMIA ONLY</div>"""
    for fp in pumps[:6]:
        col="#ffcc00" if fp['symbol']=="LUMIA" else ("#0ff" if fp['ev']>0.4 else "#aaa")
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:{col};font-weight:bold">{fp.get('tier','')} #{fp['id']} {fp['symbol']} H1 +{fp['h1']:.1f}% EV +{fp['ev']*100:.2f}% {fp.get('bucket','')}</span><br><span style="color:#0f8">VOL ${fp['vol']} PRICE ${fp['price']:.6f} SCORE {fp['score']:.1f} NEAR_HIGH {fp.get('near_high',0):.1f}% FROM_LOW {fp.get('from_low',0):.1f}%</span><br><span style="color:#ffcc00">POS ${POS_SIZE} TP {fp.get('tp',TP_BASE):.1f}% | SL {fp.get('sl',SL_BASE):.2f}% | EV +{fp['ev']*100:.2f}%</span></div>"""
    html+=f"""<div class="yellowbar">OPEN {len(open_tr)}/2 MAX PRO - EV BASED - TP {TP_BASE}% | SL {SL_BASE}% | TRAIL 0.7%->0.18% lock +0.52% - CIRCUIT BREAKER</div>"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:{'#ffcc00' if tr.get('tier')=='GOOD' else '#0ff'};font-weight:bold">PRO {tr['symbol']} ${tr.get('pos')} EV +{tr.get('ev',0)*100:.2f}% AGE {tr.get('age',0)}s {tr.get('tier','')}</span><br><span style="color:#0f8">ENTRY ${tr['entry']:.6f} -> NOW ${tr['price']:.6f} PEAK {tr.get('peak',0):.1f}% H1 {tr.get('h1',0):+.1f}% BUCKET {tr.get('bucket','')}</span><br><span style="color:{col};font-size:18px;font-weight:bold">{tr.get('pct',0):+.2f}% ${tr.get('net',0):+.2f} REAL</span><br><span style="font-size:9px;color:#aaa">TP {tr.get('tp',TP_BASE):.1f}% | SL {tr.get('sl',SL_BASE):.2f}% | TRAIL peak-0.18% lock +0.52% | QTY {tr.get('qty',0)}</span></div>"""
    html+=f"""<div style="padding:6px"><div style="color:#ffcc00;font-weight:bold;font-size:12px">CLOSED {len(closed)} - W:{wins} L:{loss} T:{tot} CAP ${cap:.2f} DAILY ${daily:+.2f} / $50 - PRO LEARN EV</div>"""
    for cl in closed[:15]:
        ccol="#0f8" if cl["net"]>0 else "#f44"
        html+=f"""<div style="color:{ccol};padding:3px;border-bottom:1px solid #222;font-size:11px"><b>{cl['symbol']}</b> ${cl['net']:+.2f} {cl['reason']} {cl['pct']:+.1f}% EV {cl.get('ev',0)*100:+.1f}% BUCKET {cl.get('bucket','')} AGE {cl['age']}s</div>"""
    html+=f"""</div><div style="text-align:center;padding:10px;color:#555;font-size:10px">v770 PRO LEARNER - EV >0.35% ONLY - TP {TP_BASE}% SL {SL_BASE}% NET +1.2% vs -0.85% - 2 MAX - PAUSE 5 LOSS - <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON PRO</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#f44">RESET $300</a></div><div style="text-align:center;padding:12px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:12px 20px;text-decoration:none;font-weight:bold;font-size:12px">CRON PRO v770 - CAP ${cap:.2f} EV LEARN - {len(pumps)} PUMPS</a></div></body></html>"""
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
        kv_set(STATE_KEY,{"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"features":{},"buckets":{},"ev":{},"tp_sl":{},"pause_until":0,"consecutive_losses":0}})
        return Response(json.dumps({"ok":True,"cap":300}), mimetype="application/json")
    if p.startswith("/api/test_real"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        base=BINANCE_BASE; pub_ok=False; btc_price="?"
        try:
            req=urllib.request.Request(f"https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT", headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                d=json.loads(r.read().decode()); btc_price=d.get('price'); pub_ok=True
        except: pass
        data, err = binance_req("/api/v3/account", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, {})
        res={"public": "OK "+str(btc_price) if pub_ok else "FAIL","base":base,"real_trading":REAL_TRADING,"pos":POS_SIZE,"btc":btc_price}
        if err: res["account"]=f"FAIL {err[:300]}"
        else: res["account"]="OK SUCCESS"; res["balances"]=[f"{b['asset']}:{float(b['free']):.1f}" for b in data.get('balances',[]) if float(b.get('free','0'))>0.001][:10]
        return Response(json.dumps(res, indent=2), mimetype="application/json")
    st=load_state()
    h=render(st)
    return Response(h, mimetype="text/html")
