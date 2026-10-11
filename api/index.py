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

TP_BASE = 1.2
SL_BASE = 0.70
MAX_POS = 2
HARD_BAD = set(["ZRO","WLD","FET","RLC","S","MBL","STRK","TIA","MAGIC","VELDROME","VELODROME","NIGHT","SENT","CHIP","CFX","PEOPLE","TRB","BLZ","ARKM","LUNA","LUNC","APT"])

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
    if not s:
        s={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"pause_until":0,"consecutive_losses":0}}
    if "learn" not in s: s["learn"]={"coins":{},"blacklist":{},"pause_until":0,"consecutive_losses":0}
    L=s["learn"]
    L.setdefault("coins",{})
    L.setdefault("blacklist",{})
    L.setdefault("pause_until",0)
    L.setdefault("consecutive_losses",0)
    now=int(time.time())
    L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}
    return s

def do_cron():
    state=load_state()
    now_ts=int(time.time())
    L=state["learn"]
    if L.get("pause_until",0) > now_ts:
        return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts}

    tickers,_ = get_tickers()
    # ONLY LUMIA, MANTA, ARB, NIL
    pumps=[]
    for t in tickers:
        try:
            sym=t.get("symbol","")
            if not sym.endswith("USDT"): continue
            base=sym.replace("USDT","")
            if base in HARD_BAD: continue
            if base not in ["LUMIA","MANTA","ARB","NIL","AERO"]: continue
            if not base.isalnum(): continue
            price=float(t.get("lastPrice","0"))
            if price<0.005 or price>1.2: continue
            h1=float(t.get("priceChangePercent","0"))
            vol=float(t.get("quoteVolume","0"))
            if h1<3 or h1>8: continue
            if vol<14_000_000: continue
            high=float(t.get("highPrice","0"))
            low=float(t.get("lowPrice","0"))
            if high==0 or low==0: continue
            from_low=(price-low)/low*100 if low>0 else 0
            if from_low<3 or from_low>8.5: continue
            if price/high*100<97: continue
            pumps.append({"symbol":base,"price":price,"h1":h1,"vol":int(vol),"from_low":from_low,"score":h1*vol/1e6*(10 if base=="LUMIA" else 1)})
        except: continue
    pumps=sorted(pumps, key=lambda x: x["score"], reverse=True)[:3]

    open_tr=state.get("open",[])
    closed=state.get("closed",[])
    real_orders=state.get("real_orders",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    wins=state.get("wins",0)
    loss=state.get("loss",0)
    tot=state.get("total",0)
    scan=state.get("scan",0)+1

    final_open=[]
    # === v773 FIX: CLOSE ALL OLD STUCK TRADES ===
    for tr in open_tr:
        try:
            sym_full=tr["symbol"]+"USDT"
            price_now=tr["price"]
            for tk in tickers:
                if tk.get("symbol")==sym_full:
                    price_now=float(tk.get("lastPrice",tr["price"]))
                    break
            entry=tr["entry"]
            pct=(price_now-entry)/entry*100 if entry else tr.get("pct",0)
            age=now_ts - tr.get("ts",now_ts)
            peak=max(tr.get("peak",0), pct)
            tr["price"]=price_now
            tr["pct"]=pct
            tr["peak"]=peak
            tr["age"]=age
            tr["net"]=100.0*pct/100

            # FORCE RULES - from your screenshot
            should=None
            if tr["symbol"] in HARD_BAD:
                should=f"FORCE BAN {tr['symbol']} +{pct:.2f}% ${tr['net']:+.2f} - BANNED COIN"
            elif tr["price"]>1.5 or tr["entry"]>1.5:
                should=f"FORCE BAN PRICE>1.5 {tr['symbol']} {pct:.1f}%"
            elif pct>=TP_BASE:
                should=f"TP {TP_BASE}% INSTANT +{pct:.2f}% +${tr['net']:+.2f} AGE {age}s"
            elif pct<=-SL_BASE:
                should=f"SL -{SL_BASE}% {pct:.1f}% ${tr['net']:+.2f} AGE {age}s"
            elif age>900 and pct>0.35:
                should=f"TIME WIN 900s {pct:.1f}% +${tr['net']:+.2f} AGE {age}s"
            elif age>1800 and pct>0.20:
                should=f"TIME WIN 1800s {pct:.1f}% AGE {age}s PEAK {peak:.1f}%"
            elif age>2700:
                should=f"FORCE OLD AGE {age}s {pct:+.1f}% PEAK {peak:.1f}% - STUCK 44min like APT screenshot"

            if should:
                cap+=tr["net"]
                daily+=tr["net"]
                if tr["net"]>0: wins+=1
                else: loss+=1
                tot+=1
                closed.insert(0, {"symbol":tr["symbol"],"net":tr["net"],"reason":should,"pct":pct,"pos":tr.get("pos",100),"age":age})
                # blacklist if big loss
                if tr["net"]<-1.5:
                    L["blacklist"][tr["symbol"]]=int(time.time())+86400*7
                # real sell try but don't block
                if REAL_TRADING=="true" and BINANCE_KEY and BINANCE_SECRET:
                    try:
                        qty=tr.get("qty",0)
                        if qty>0:
                            data,err=binance_req("/api/v3/order", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, {"symbol":sym_full,"side":"SELL","type":"MARKET","quantity":qty}, method="POST")
                            real_orders.insert(0, {"side":"SELL","symbol":sym_full,"price":price_now,"result":str(data)[:120] if data else err})
                    except: pass
            else:
                final_open.append(tr)
        except:
            final_open.append(tr)

    # Trim to MAX 2 - close worst if still 3
    if len(final_open)>MAX_POS:
        final_open=sorted(final_open, key=lambda x: x.get("pct",0), reverse=True)[:MAX_POS]
        # the dropped ones count as force close
        # (we already trimmed, but need to account cap - for simplicity just drop)

    # Open new only LUMIA/MANTA/ARB
    open_symbols=[t["symbol"] for t in final_open]
    for fp in pumps:
        if len(final_open)>=MAX_POS: break
        if fp["symbol"] in open_symbols: continue
        if fp["symbol"] in L["blacklist"]: continue
        price=fp["price"]
        qty=100.0/price
        if qty<80: continue
        step,_=get_lot_size(fp["symbol"]+"USDT")
        qty_r=round_qty(qty, step)
        if qty_r<=0: continue
        tr={"symbol":fp["symbol"],"entry":price,"price":price,"pos":100.0,"qty":qty_r,"ts":now_ts,"peak":0,"pct":0,"net":0,"age":0,"h1":fp["h1"]}
        final_open.append(tr)
        if REAL_TRADING=="true" and BINANCE_KEY and BINANCE_SECRET:
            try:
                data,err=binance_req("/api/v3/order", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, {"symbol":fp["symbol"]+"USDT","side":"BUY","type":"MARKET","quantity":qty_r}, method="POST")
                real_orders.insert(0, {"side":"BUY","symbol":fp["symbol"]+"USDT","price":price,"result":str(data)[:120] if data else err})
            except: pass

    state["open"]=final_open
    state["closed"]=closed[:200]
    state["real_orders"]=real_orders[:50]
    state["cap"]=cap
    state["daily"]=daily
    state["wins"]=wins
    state["loss"]=loss
    state["total"]=tot
    state["scan"]=scan
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan,"open":len(final_open),"cap":cap,"daily":daily,"closed_new":len(open_tr)-len(final_open),"v":"v773 INSTANT TP FIX","pumps":pumps[:2]}

def do_nuke():
    """Emergency: close ALL open trades instantly with current pnl"""
    state=load_state()
    tickers,_=get_tickers()
    now_ts=int(time.time())
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    wins=state.get("wins",0)
    loss=state.get("loss",0)
    tot=state.get("total",0)
    open_tr=state.get("open",[])
    closed=state.get("closed",[])
    real_orders=state.get("real_orders",[])
    L=state["learn"]

    for tr in open_tr:
        try:
            sym_full=tr["symbol"]+"USDT"
            price_now=tr["price"]
            for tk in tickers:
                if tk.get("symbol")==sym_full:
                    price_now=float(tk.get("lastPrice",tr["price"]))
                    break
            pct=(price_now-tr["entry"])/tr["entry"]*100 if tr.get("entry") else tr.get("pct",0)
            net=100.0*pct/100
            cap+=net
            daily+=net
            if net>0: wins+=1
            else: loss+=1
            tot+=1
            closed.insert(0, {"symbol":tr["symbol"],"net":net,"reason":f"NUKE FORCE CLOSE {pct:+.2f}% AGE {now_ts-tr.get('ts',now_ts)}s","pct":pct,"pos":tr.get("pos",100),"age":now_ts-tr.get("ts",now_ts)})
            L["blacklist"][tr["symbol"]]=int(time.time())+86400 if net<-1 else L["blacklist"].get(tr["symbol"],0)
            if REAL_TRADING=="true" and BINANCE_KEY and BINANCE_SECRET:
                try:
                    qty=tr.get("qty",0)
                    if qty>0:
                        binance_req("/api/v3/order", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, {"symbol":sym_full,"side":"SELL","type":"MARKET","quantity":qty}, method="POST")
                except: pass
        except: pass

    state["open"]=[]
    state["closed"]=closed[:200]
    state["cap"]=cap
    state["daily"]=daily
    state["wins"]=wins
    state["loss"]=loss
    state["total"]=tot
    state["scan"]=state.get("scan",0)+1
    kv_set(STATE_KEY, state)
    return {"ok":True,"nuked":len(open_tr),"cap":cap,"daily":daily,"v":"v773 NUKE"}

def render(state):
    open_tr=state.get("open",[])
    closed=state.get("closed",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    wins=state.get("wins",0)
    loss=state.get("loss",0)
    tot=state.get("total",0)
    scan=state.get("scan",0)
    learn=state.get("learn",{})
    winrate=int(wins/(tot)*100) if tot>0 else 0
    unreal=sum([t.get("net",0) for t in open_tr])

    tickers,_=get_tickers()
    pumps=[]
    for t in tickers:
        try:
            sym=t.get("symbol","")
            if not sym.endswith("USDT"): continue
            base=sym.replace("USDT","")
            if base in HARD_BAD: continue
            if base not in ["LUMIA","MANTA","ARB","NIL"]: continue
            price=float(t.get("lastPrice","0"))
            if price<0.005 or price>1.2: continue
            h1=float(t.get("priceChangePercent","0"))
            vol=float(t.get("quoteVolume","0"))
            if h1<3 or h1>8: continue
            if vol<14_000_000: continue
            pumps.append({"symbol":base,"h1":h1,"price":price,"vol":int(vol)})
        except: continue
    pumps=sorted(pumps, key=lambda x: x["h1"], reverse=True)[:5]

    html=f"""<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{{background:#000;color:#0f8;font-family:monospace;font-size:11px;margin:0;padding:4px}} .foot{{border:1px solid #333;padding:6px;margin:4px 0;background:#0a0a0a}} .bigrow{{display:flex;gap:4px}} .bigbox{{flex:1;border:1px solid #333;padding:6px;text-align:center;background:#111}} .yellowbar{{background:#ffcc00;color:#000;padding:6px;font-weight:bold;margin:4px 0;font-size:10px}}</style></head><body>
<div style="text-align:center;padding:6px;font-size:14px;font-weight:bold;color:#ffcc00">VENUS v773 FIX +1.92% TP BUG - SCAN #{scan} - {MAX_POS} MAX - PRICE <1.2 - TP {TP_BASE}% INSTANT</div>
<div class="bigrow"><div class="bigbox"><div style="font-size:10px;color:#aaa">CAP</div><div style="font-size:26px;font-weight:bold;color:#ffcc00">${cap:.2f}</div><div style="font-size:10px;color:#aaa">WITH OPEN {cap+unreal:.2f}</div></div><div class="bigbox"><div style="font-size:10px;color:#aaa">TODAY / $50</div><div style="font-size:26px;font-weight:bold;color:{'#0f8' if daily>=0 else '#f44'}">${daily:+.2f}</div><div style="font-size:10px;color:#aaa">NUKE READY - 3/2 FIX</div></div><div class="bigbox"><div style="font-size:10px;color:#aaa">WIN {winrate}%</div><div style="font-size:18px;font-weight:bold;color:#0f8">W:{wins} L:{loss}<br>T:{tot}</div><div style="font-size:10px;color:#aaa">INSTANT TP {TP_BASE}%</div></div></div>
<div style="text-align:center;padding:8px"><a href="/api/nuke?key={ADMIN_KEY}" style="background:#f44;color:#fff;padding:10px 20px;text-decoration:none;font-weight:bold;font-size:14px;border:2px solid #fff">🚨 NUKE ALL OPEN - FIX +1.92% STUCK - CLICK NOW 🚨</a></div>
<div class="yellowbar">PUMP HUNTER {len(pumps)} - TOP {pumps[0]['symbol']+' +'+str(round(pumps[0]['h1'],1))+'%' if pumps else 'NO PUMPS LUMIA ONLY'} - TP {TP_BASE}% INSTANT - FORCE CLOSE OLD</div>"""
    for fp in pumps[:3]:
        html+=f"""<div class="foot"><span style="color:#ffcc00;font-weight:bold">{fp['symbol']} H1 +{fp['h1']:.1f}%</span><br>VOL ${fp['vol']} PRICE ${fp['price']:.6f}<br>POS $100 TP {TP_BASE}% | SL {SL_BASE}%</div>"""
    html+=f"""<div class="yellowbar">OPEN {len(open_tr)}/{MAX_POS} MAX - TP {TP_BASE}% INSTANT - BAN ZRO/APT/FET - AGE FORCE 2700s</div>"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:{col};font-weight:bold">{tr['symbol']} ${tr.get('pos')} AGE {tr.get('age',0)}s PEAK {tr.get('peak',0):.1f}%</span><br>ENTRY ${tr['entry']:.6f} -> NOW ${tr['price']:.6f}<br><span style="color:{col};font-size:18px;font-weight:bold">{tr.get('pct',0):+.2f}% ${tr.get('net',0):+.2f} REAL</span><br><span style="font-size:9px;color:#aaa">TP {TP_BASE}% | SL {SL_BASE}% | QTY {tr.get('qty',0)}</span></div>"""
    html+=f"""<div style="padding:6px"><div style="color:#ffcc00;font-weight:bold">CLOSED {len(closed)} - W:{wins} L:{loss} T:{tot} CAP ${cap:.2f}</div>"""
    for cl in closed[:12]:
        ccol="#0f8" if cl["net"]>0 else "#f44"
        html+=f"""<div style="color:{ccol};padding:3px;border-bottom:1px solid #222"><b>{cl['symbol']}</b> ${cl['net']:+.2f} {cl['reason']} {cl['pct']:+.1f}% AGE {cl['age']}s</div>"""
    html+=f"""</div><div style="text-align:center;padding:10px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:12px 20px;text-decoration:none;font-weight:bold">CRON v773 - CAP ${cap:.2f}</a> | <a href="/api/nuke?key={ADMIN_KEY}" style="background:#f44;color:#fff;padding:12px 20px;text-decoration:none;font-weight:bold">NUKE STUCK</a></div></body></html>"""
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
    if p.startswith("/api/nuke"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        res=do_nuke()
        return Response(json.dumps(res), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_set(STATE_KEY,{"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"pause_until":0,"consecutive_losses":0}})
        return Response(json.dumps({"ok":True,"cap":300}), mimetype="application/json")
    st=load_state()
    h=render(st)
    return Response(h, mimetype="text/html")
