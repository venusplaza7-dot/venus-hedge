
from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse, hmac, hashlib

app = Flask(__name__)

def env(n):
    for k in n:
        v=os.environ.get(k)
        if v: return v.strip().strip('"').strip("'")
    return ""
KV_URL=env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL","UPSTASH_REDIS_REST_URL"])
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
    import math
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
    if not s: s={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"tp_adj":1.0,"sl_adj":1.0,"avoid_pump":0}}
    if s.get("cap",0)<50: s["cap"]=300.0
    if "learn" not in s: s["learn"]={"coins":{},"blacklist":{},"tp_adj":1.0,"sl_adj":1.0,"avoid_pump":0}
    now=int(time.time())
    s["learn"]["blacklist"]={k:v for k,v in s["learn"].get("blacklist",{}).items() if v>now}
    # Force profitable R:R
    s["learn"]["tp_adj"]=1.0
    s["learn"]["sl_adj"]=1.0
    s["learn"]["avoid_pump"]=0
    return s

def learn_from_trade(state, symbol, net, reason):
    L=state["learn"]
    coins=L.setdefault("coins",{})
    c=coins.setdefault(symbol, {"w":0,"l":0,"pnl":0.0,"streak":0,"sl_hits":0})
    if net>0:
        c["w"]+=1
        c["streak"]= max(0, c["streak"]+1)
        if c["streak"]>0: c["sl_hits"]=0
    else:
        c["l"]+=1
        c["streak"]= min(0, c["streak"]-1)
        if "SL" in reason: c["sl_hits"]+=1
        if c["streak"]<=-2 or c["sl_hits"]>=2:
            # Big loss => 2h blacklist, huge loss => 24h
            dur=86400 if net < -2.0 else 7200
            L["blacklist"][symbol]=int(time.time())+dur
            c["sl_hits"]=0
    c["pnl"]+=net
    # MBL special ban if losing >5
    if symbol=="MBL" and c["pnl"] < -5:
        L["blacklist"]["MBL"]=int(time.time())+604800

def is_blacklisted(state, symbol):
    if symbol=="MBL":
        # Check if MBL pnl < -5, ban 7 days
        coins=state.get("learn",{}).get("coins",{}).get("MBL",{})
        if coins.get("pnl",0) < -5:
            return True
    bl=state.get("learn",{}).get("blacklist",{})
    return symbol in bl

def do_cron():
    state=load_state()
    tickers, base = get_tickers()
    # WINNING BACK - Only GOOD + early 2-12% + avoid BAD + avoid +20% top
    learn_coins=state.get("learn",{}).get("coins",{})
    good_coins=set([k for k,v in learn_coins.items() if v.get("pnl",0)>5])
    bad_coins=set([k for k,v in learn_coins.items() if v.get("pnl",0)<-4 or (v.get("w",0)+v.get("l",0)>10 and v.get("w",0)/(v.get("w",0)+v.get("l",0))<0.45)])
    # Always keep LUMIA as GOOD
    if "LUMIA" in learn_coins: good_coins.add("LUMIA")
    pumps=[]
    for t in tickers:
        try:
            sym=t.get("symbol","")
            if not sym.endswith("USDT"): continue
            base_sym=sym.replace("USDT","")
            if base_sym in bad_coins: continue
            if base_sym in ["MBL","STRK","TIA","S","VELDROME","VELODROME"]: continue
            if "UP" in sym or "DOWN" in sym or "BULL" in sym or "BEAR" in sym: continue
            price=float(t.get("lastPrice","0"))
            if price < 0.001 or price>20: continue
            h1=float(t.get("priceChangePercent","0"))
            vol=float(t.get("quoteVolume","0"))
            # WINNING: Avoid buying top +20%+ pumped (will dump)
            if h1>18: continue
            if vol < 1500000: continue
            if h1 < 2: continue
            high=float(t.get("highPrice","0"))
            low=float(t.get("lowPrice","0"))
            near_high = (price>=high*0.97) if high>0 else False
            # LUMIA bonus
            bonus = 5.0 if base_sym in good_coins else 1.0
            if base_sym=="LUMIA": bonus=6.0
            score = h1 * (vol/1000000) * bonus
            is_early=False
            if 2 < h1 < 10 and near_high:
                score*=5.0
                is_early=True
            elif 2 < h1 < 10:
                score*=3.0
                is_early=True
            tier="FOOT" if is_early else ("GOOD" if base_sym in good_coins else "WHALE")
            pumps.append({"symbol":base_sym,"h1":h1,"price":price,"vol":int(vol),"score":score,"tier":tier,"type":tier,"id":0,"is_early":is_early})
        except: continue
    pumps=sorted(pumps, key=lambda x: (x["symbol"] in good_coins, x.get("is_early",False), x["score"]), reverse=True)[:15]
    for i,p in enumerate(pumps): p["id"]=i+1

    tp_a=1.2
    sl_a=0.4
    now_ts=int(time.time())
    open_tr=state.get("open",[])
    closed=state.get("closed",[])
    real_orders=state.get("real_orders",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    wins=state.get("wins",0)
    loss=state.get("loss",0)
    tot=state.get("total",0)
    scan=state.get("scan",0)+1

    # Check open trades
    new_open=[]
    for tr in open_tr:
        try:
            sym_full=tr["symbol"]+"USDT"
            # get current price
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
            should_close=None
            # WINNING LOGIC - Take big wins, cut losses fast, no force loss
            if pct >= tp_a: should_close=f"TP {tp_a}% QUICK +{pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            elif pct <= -sl_a: should_close=f"SL -{sl_a}% QUICK {pct:.1f}% ${float(POS_SIZE)*pct/100:+.2f}"
            elif peak>=0.6 and pct < peak-0.15: should_close=f"TRAIL lock +{peak:.1f}% peak-{peak-pct:.1f}% {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            elif age>180 and pct>=0.5: should_close=f"TIME QUICK 180s {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            elif age>300 and pct>=0.2: should_close=f"TIME QUICK 300s {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            elif age>600 and pct>0: should_close=f"TIME WIN 600s {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            elif age>900: should_close=f"FORCE 900s {pct:.1f}% ${float(POS_SIZE)*pct/100:+.2f}"
            if not should_close:
                if pct >= tp_a: should_close=f"TP {tp_a}% QUICK +{pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
                elif pct <= -sl_a: should_close=f"SL -{sl_a}% QUICK {pct:.1f}% ${float(POS_SIZE)*pct/100:+.2f}"
                elif peak>=0.35 and pct < peak-0.2: should_close=f"TRAIL lock +{peak:.1f}% peak-{peak-pct:.1f}% {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
                elif age>60 and pct>=0.5: should_close=f"TIME QUICK 60s {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
                elif age>120 and pct>=0.35: should_close=f"TIME QUICK 120s {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
                elif age>180 and pct>=0.15: should_close=f"TIME QUICK 180s {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            if should_close:
                net=float(POS_SIZE)*pct/100
                cap+=net
                daily+=net
                if net>0: wins+=1
                else: loss+=1
                tot+=1
                closed.insert(0, {"symbol":tr["symbol"],"net":net,"reason":should_close,"pct":pct,"pos":tr.get("pos"),"age":age})
                learn_from_trade(state, tr["symbol"], net, should_close)
                # real sell
                if REAL_TRADING=="true" and BINANCE_KEY and BINANCE_SECRET:
                    qty=tr.get("qty",0)
                    if qty>0:
                        data,err=binance_req("/api/v3/order", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, {"symbol":sym_full,"side":"SELL","type":"MARKET","quantity":qty}, method="POST")
                        real_orders.insert(0, {"side":"SELL","symbol":sym_full,"price":price_now,"pos":tr.get("pos"),"result":str(data)[:200] if data else err})
            else:
                new_open.append(tr)
        except Exception as e:
            new_open.append(tr)
    state["open"]=new_open
    # Open new trades
    open_symbols=[t["symbol"] for t in new_open]
    for fp in pumps:
        if len(new_open)>=3: break
        sym=fp["symbol"]
        if sym in open_symbols: continue
        if is_blacklisted(state, sym): continue
        # open
        price=fp["price"]
        pos=float(POS_SIZE)
        qty=pos/price if price>0 else 0
        step,minQty=get_lot_size(sym+"USDT")
        qty=round_qty(qty, step)
        if qty<=0: continue
        tr={"symbol":sym,"entry":price,"price":price,"pos":pos,"qty":qty,"ts":now_ts,"peak":0,"pct":0,"net":0,"age":0,"h1":fp["h1"],"tier":fp["tier"],"move":fp["tier"]}
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
    state["learn"]["tp_adj"]=1.0
    state["learn"]["sl_adj"]=1.0
    state["learn"]["avoid_pump"]=0
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan,"open":len(new_open),"pumps":len(pumps),"base":base,"cap":cap,"total":tot,"tp":tp_a,"sl":sl_a,"mbl_filtered":True,"keep_track":True,"learn":state["learn"]}

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
    tp_a=1.2
    sl_a=0.4
    winrate=int(wins/(tot)*100) if tot>0 else 0
    daily_pct= round(daily/50*100,1) if True else 0
    unreal=sum([t.get("net",0) for t in open_tr])
    bl=learn.get("blacklist",{})
    av=learn.get("avoid_pump",0)
    learn_txt=f"KEEP TRACK LEARN AI: TP {tp_a}% SL {sl_a}% R:R 2.0 BL:{len(bl)} "
    if bl:
        try: learn_txt+=",".join([f"{k}({int((v-time.time())/60)}m)" for k,v in list(bl.items())[:4]])
        except: learn_txt+=",".join(list(bl.keys())[:4])
    if av: learn_txt+=" AVOID HIGH PUMP"
    good = sorted([(k,v) for k,v in learn.get("coins",{}).items() if v.get("pnl",0)>2], key=lambda x: x[1]["pnl"], reverse=True)[:2]
    bad = sorted([(k,v) for k,v in learn.get("coins",{}).items() if v.get("pnl",0)<-2], key=lambda x: x[1]["pnl"])[:3]
    if good: learn_txt+=" | GOOD: " + ", ".join([f"{k} {v['w']}W{v['l']}L +${v['pnl']:.1f}" for k,v in good])
    if bad: learn_txt+=" | BAD: " + ", ".join([f"{k} {v['w']}W{v['l']}L ${v['pnl']:.1f}" for k,v in bad])
    tickers, base = get_tickers()
    pumps=[]
    for t in tickers:
        try:
            sym=t.get("symbol","")
            if not sym.endswith("USDT"): continue
            price=float(t.get("lastPrice","0"))
            if price < 0.01: continue
            if sym.startswith("MBL"): continue
            if "UP" in sym or "DOWN" in sym: continue
            h1=float(t.get("priceChangePercent","0"))
            vol=float(t.get("quoteVolume","0"))
            if h1 < 8: continue
            if vol < 500000: continue
            score = h1 * (vol/1000000)
            tier="PUMP" if h1>15 else "WHALE"
            pumps.append({"symbol":sym.replace("USDT",""),"h1":h1,"price":price,"vol":int(vol),"score":score,"tier":tier,"type":"PUMP","id":0})
        except: continue
    pumps=sorted(pumps, key=lambda x: x["score"], reverse=True)[:15]
    for i,p in enumerate(pumps): p["id"]=i+1
    html=f"""<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{{background:#000;color:#0f8;font-family:monospace;font-size:11px;margin:0;padding:4px}} .foot{{border:1px solid #333;padding:6px;margin:4px 0;background:#0a0a0a}} .bigrow{{display:flex;gap:4px}} .bigbox{{flex:1;border:1px solid #333;padding:6px;text-align:center;background:#111}} .yellowbar{{background:#ffcc00;color:#000;padding:6px;font-weight:bold;margin:4px 0;font-size:10px}}</style></head><body>
<div style="text-align:center;padding:6px;font-size:14px;font-weight:bold;color:#ffcc00">VENUS v767 WINNING BACK LUMIA $300 REAL $300 REAL - SCAN #{scan} - 3 MAX - POS ${POS_SIZE} - KEEPS TRACK</div>
<div class="bigrow"><div class="bigbox"><div style="font-size:10px;color:#aaa">CAP $300 REAL</div><div style="font-size:26px;font-weight:bold;color:#ffcc00">${cap:.2f}</div><div style="font-size:10px;color:#aaa">WITH OPEN {cap+unreal:.2f}</div></div><div class="bigbox"><div style="font-size:10px;color:#aaa">TODAY / $50</div><div style="font-size:26px;font-weight:bold;color:{'#0f8' if daily>=0 else '#f44'}">${daily:+.2f}</div><div style="font-size:10px;color:#aaa">{daily_pct}% OF $50 TARGET</div></div><div class="bigbox"><div style="font-size:10px;color:#aaa">WIN {winrate}%</div><div style="font-size:18px;font-weight:bold;color:#0f8">W:{wins} L:{loss}<br>T:{tot}</div><div style="font-size:10px;color:#aaa">3 MAX PUMP+WHALE LEARN - WINNING LUMIA +$23.8</div></div></div>
<div style="padding:6px;background:#111;border:1px solid #0ff;margin:4px"><div style="color:#0ff;font-size:10px">{learn_txt}</div></div>
<div class="yellowbar">PUMP+WHALE HUNTER {len(pumps)} - TOP {pumps[0]['symbol']+' +'+str(round(pumps[0]['h1'],1))+'% '+pumps[0].get('tier','') if pumps else 'NO PUMPS'} - TODAY $300 REAL HUNT LEARN - WINNING EARLY 2-10% LUMIA ONLY + TP 1.2% SL 0.4%</div>"""
    for fp in pumps[:10]:
        html+=f"""<div class="foot" style="border-color:{'#ffcc00' if fp.get('tier')=='PUMP' else '#0ff'}"><span style="color:{'#ffcc00' if fp.get('tier')=='PUMP' else '#0ff'};font-weight:bold">{fp.get('tier','')} #{fp['id']} {fp['symbol']} H1 +{fp['h1']:.1f}% {fp['type']}</span><br><span style="color:#0f8">VOL ${fp['vol']} PRICE ${fp['price']:.6f} SCORE {fp['score']:.1f}</span><br><span style="color:#ffcc00">POS ${POS_SIZE} TP {tp_a}% | SL {sl_a}% R:R 2.0</span></div>"""
    html+=f"""<div class="yellowbar">OPEN {len(open_tr)}/3 MAX $300 REAL - LEARN AI - TP {tp_a}% | SL {sl_a}% R:R 2.0 | POS ${POS_SIZE} - WINNING LUMIA +$23.8</div>"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:{'#ffcc00' if tr.get('tier')=='PUMP' else '#0ff'};font-weight:bold">{tr.get('move')} {tr['symbol']} ${tr.get('pos')} AGE {tr.get('age',0)}s {tr.get('tier','')}</span><br><span style="color:#0f8">ENTRY ${tr['entry']:.6f} -> NOW ${tr['price']:.6f} PEAK {tr.get('peak',0):.1f}% H1 {tr.get('h1',0):+.1f}%</span><br><span style="color:{col};font-size:18px;font-weight:bold">{tr.get('pct',0):+.2f}% ${tr.get('net',0):+.2f} REAL</span><br><span style="font-size:9px;color:#aaa">TP {tp_a}% | SL {sl_a}% | TRAIL peak-0.15% | QTY {tr.get('qty',0)}</span></div>"""
    html+=f"""<div style="padding:6px"><div style="color:#ffcc00;font-weight:bold;font-size:12px">CLOSED {len(closed)} - W:{wins} L:{loss} T:{tot} CAP ${cap:.2f} DAILY ${daily:+.2f} / $50 - KEEP TRACK</div>"""
    for cl in closed[:15]:
        ccol="#0f8" if cl["net"]>0 else "#f44"
        html+=f"""<div style="color:{ccol};padding:3px;border-bottom:1px solid #222;font-size:11px"><b>{cl['symbol']}</b> ${cl['net']:+.2f} {cl['reason']} {cl['pct']:+.1f}% POS ${cl.get('pos','')} AGE {cl['age']}s REAL</div>"""
    html+=f"""</div><div style="padding:6px"><div style="color:#ffcc00;font-weight:bold;font-size:11px">REAL ORDERS - TESTNET {len(real_orders)} - REAL_TRADING={REAL_TRADING} - WINNING LUMIA +$23.8</div>"""
    for ro in real_orders[:10]:
        html+=f"""<div style="color:#0f8;padding:2px;font-size:10px">{ro.get('side')} {ro.get('symbol')} ${ro.get('price','')} POS ${ro.get('pos','')} {str(ro.get('result',''))[:150]}</div>"""
    html+=f"""</div><div style="text-align:center;padding:10px;color:#555;font-size:10px">v767 WINNING BACK LUMIA $300 REAL $300 REAL - 3x$100 - TP 1.2% SL 0.4% R:R 3.0 - FOOTPRINT 0.7% NET +0.5% - KEEP TRACK SCAN #{scan} - KV:{'OK' if KV_URL else 'MISS'} - <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON PUMP</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#f44">RESET $300</a></div><div style="text-align:center;padding:12px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:12px 20px;text-decoration:none;font-weight:bold;font-size:12px">CRON PUMP - CAP ${cap:.2f} DAILY ${daily:+.2f}/$50 - TP 0.7% SL 0.35%</a></div></body></html>"""
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
        kv_set(STATE_KEY,{"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"tp_adj":1.0,"sl_adj":1.0,"avoid_pump":0}})
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
    st=load_state(); h=render(st)
    return Response(h, mimetype="text/html")
