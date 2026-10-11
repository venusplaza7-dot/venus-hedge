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

# v775 CLEAN UI - LUMIA ONLY - TP 1.0% INSTANT
TP_BASE = 1.0
SL_BASE = 0.55
MAX_POS = 2
DAILY_STOP = -10.0
HARD_BAD = set(["ZRO","WLD","FET","RLC","S","MBL","STRK","TIA","MAGIC","VELDROME","VELODROME","NIGHT","SENT","CHIP","CFX","PEOPLE","TRB","BLZ","ARKM","LUNA","LUNC","APT","TRB","1000SATS"])

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

def update_learn(state, symbol, net, pct):
    L=state["learn"]
    c=L["coins"].setdefault(symbol, {"w":0,"l":0,"pnl":0.0,"avg_win":0.7,"avg_loss":0.6,"ev":0.0})
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
        ev=(wr*c["avg_win"]) - ((1-wr)*c["avg_loss"]) - 0.20
        c["ev"]=max(-2.0, min(2.0, ev))
    if c["pnl"]<-8 or net<-2.0 or total>=8 and c["ev"]<-0.2:
        L["blacklist"][symbol]=int(time.time())+86400*7
    if L["consecutive_losses"]>=4:
        L["pause_until"]=int(time.time())+10800
    if state.get("daily",0) <= -10:
        L["pause_until"]=int(time.time())+14400

def score_ticker(t):
    try:
        sym=t.get("symbol","")
        if not sym.endswith("USDT"): return None
        base=sym.replace("USDT","")
        if base in HARD_BAD: return None
        if not base.isalnum(): return None
        if any(ord(c)>127 for c in base): return None
        if len(base)<2 or len(base)>8: return None
        if "UP" in sym or "DOWN" in sym: return None
        price=float(t.get("lastPrice","0"))
        if price<0.005 or price>1.0: return None
        h1=float(t.get("priceChangePercent","0"))
        vol=float(t.get("quoteVolume","0"))
        # LUMIA ONLY: 3-6% early
        if h1<3.0 or h1>6.0: return None
        if vol<16_000_000: return None
        high=float(t.get("highPrice","0"))
        low=float(t.get("lowPrice","0"))
        if high==0 or low==0: return None
        from_low=(price-low)/low*100 if low>0 else 0
        if from_low<3.0 or from_low>6.0: return None
        if price/high*100<97.2: return None
        if 100.0/price < 90: return None
        # LUMIA ONLY + MANTA + NIL
        if base not in ["LUMIA","MANTA","NIL","AERO","EIGEN"]:
            return None
        score=h1*(vol/1e6)*(20.0 if base=="LUMIA" else 2.5)
        return {"symbol":base,"full":sym,"h1":h1,"price":price,"vol":int(vol),"score":score,"from_low":from_low,"near_high":price/high*100}
    except: return None

def do_cron():
    state=load_state()
    L=state["learn"]
    now_ts=int(time.time())
    if L.get("pause_until",0) > now_ts:
        return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"scan":state.get("scan",0)}
    if state.get("daily",0) <= -10:
        L["pause_until"]=now_ts+14400
        kv_set(STATE_KEY, state)
        return {"ok":False,"paused":True,"reason":"Daily stop","daily":state.get("daily",0)}

    tickers,_ = get_tickers()
    pumps=[]
    for t in tickers:
        s=score_ticker(t)
        if s: pumps.append(s)
    pumps=sorted(pumps, key=lambda x: x["score"], reverse=True)[:5]

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
    for tr in open_tr:
        # Force close banned or excess
        sym=tr["symbol"]
        if sym in HARD_BAD or float(tr.get("entry",0))>1.5 or len(final_open)>=MAX_POS:
            net=float(POS_SIZE)*tr.get("pct",0)/100
            # if pct not set, calc
            try:
                price_now=tr["price"]
                for tk in tickers:
                    if tk.get("symbol")==sym+"USDT":
                        price_now=float(tk.get("lastPrice",price_now))
                        break
                pct=(price_now-tr["entry"])/tr["entry"]*100 if tr["entry"] else tr.get("pct",0)
                net=float(POS_SIZE)*pct/100
                tr["pct"]=pct
                tr["net"]=net
            except: pass
            cap+=net
            daily+=net
            if net>0: wins+=1
            else: loss+=1
            tot+=1
            reason=f"FORCE BAN {sym} CLEAN" if sym in HARD_BAD else f"FORCE EXCESS {len(open_tr)}/{MAX_POS}"
            closed.insert(0, {"symbol":sym,"net":net,"reason":reason,"pct":tr.get("pct",0),"pos":tr.get("pos"),"age":now_ts-tr.get("ts",now_ts)})
            update_learn(state, sym, net, tr.get("pct",0))
            continue
        
        try:
            sym_full=sym+"USDT"
            price_now=tr["price"]
            for tk in tickers:
                if tk.get("symbol")==sym_full:
                    price_now=float(tk.get("lastPrice",price_now))
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

            should=None
            if pct>=TP_BASE:
                should=f"TP {TP_BASE}% INSTANT +{pct:.2f}% +${float(POS_SIZE)*pct/100:+.2f}"
            elif pct<=-SL_BASE:
                should=f"SL -{SL_BASE}% {pct:.1f}% ${float(POS_SIZE)*pct/100:+.2f}"
            elif peak>=0.8 and pct < peak-0.20 and pct>0.35:
                should=f"TRAIL +{peak:.1f}%->{pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            elif age>600 and pct>0.45:
                should=f"TIME WIN 600s {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            elif age>1800 and pct>0.25:
                should=f"TIME WIN 1800s {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"

            if should:
                net=float(POS_SIZE)*pct/100
                cap+=net
                daily+=net
                if net>0: wins+=1
                else: loss+=1
                tot+=1
                closed.insert(0, {"symbol":sym,"net":net,"reason":should,"pct":pct,"pos":tr.get("pos"),"age":age})
                update_learn(state, sym, net, pct)
            else:
                final_open.append(tr)
        except:
            final_open.append(tr)

    open_symbols=[t["symbol"] for t in final_open]
    for fp in pumps:
        if len(final_open)>=MAX_POS: break
        sym=fp["symbol"]
        if sym in open_symbols: continue
        if sym in state["learn"]["blacklist"]: continue
        if sym in HARD_BAD: continue
        price=fp["price"]
        qty=100.0/price
        if qty<90: continue
        step,_=get_lot_size(sym+"USDT")
        qty_r=round_qty(qty, step)
        if qty_r<=0: continue
        tr={"symbol":sym,"entry":price,"price":price,"pos":100.0,"qty":qty_r,"ts":now_ts,"peak":0,"pct":0,"net":0,"age":0,"h1":fp["h1"],"from_low":fp["from_low"]}
        final_open.append(tr)
        open_symbols.append(sym)

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
    return {"ok":True,"scan":scan,"open":len(final_open),"cap":cap,"daily":daily,"v":"v775 CLEAN UI","pumps":pumps[:2]}

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
        s=score_ticker(t)
        if s: pumps.append(s)
    pumps=sorted(pumps, key=lambda x: x["score"], reverse=True)[:5]

    # CLEAN UI CSS - no overlap
    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0a0a;color:#e0e0e0;font-family:system-ui,-apple-system,monospace;font-size:12px;line-height:1.4}}
.header{{background:#111;padding:12px;text-align:center;border-bottom:2px solid #ffcc00}}
.header h1{{color:#ffcc00;font-size:16px;font-weight:800;letter-spacing:0.5px}}
.grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;padding:8px}}
.card{{background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:12px;text-align:center}}
.card .label{{font-size:10px;color:#888;text-transform:uppercase;letter-spacing:1px}}
.card .value{{font-size:24px;font-weight:800;margin:4px 0}}
.card .sub{{font-size:10px;color:#666}}
.cap{{color:#ffcc00}} .neg{{color:#ff4444}} .pos{{color:#00ff88}} .win{{color:#00ff88}}
.banner{{background:#ffcc00;color:#000;padding:8px 12px;font-weight:700;font-size:11px;margin:8px;border-radius:6px}}
.banner2{{background:#00d4ff;color:#000;padding:8px 12px;font-weight:700;font-size:11px;margin:8px;border-radius:6px}}
.list{{padding:0 8px}}
.item{{background:#151515;border:1px solid #222;border-radius:8px;padding:10px;margin:6px 0;display:flex;justify-content:space-between;align-items:center}}
.item .left{{flex:1}}
.item .sym{{font-weight:800;color:#ffcc00;font-size:13px}}
.item .meta{{font-size:11px;color:#aaa;margin-top:2px}}
.item .right{{text-align:right}}
.item .pct{{font-size:18px;font-weight:800}}
.item.pos{{border-color:#00ff88}} .item.neg{{border-color:#ff4444}}
.closed{{background:#111;border-radius:8px;margin:8px;padding:10px}}
.closed h3{{color:#ffcc00;font-size:12px;margin-bottom:8px}}
.row{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #222;font-size:11px}}
.row .g{{color:#00ff88}} .row .r{{color:#ff4444}}
.btns{{display:flex;gap:8px;padding:12px;justify-content:center}}
.btn{{padding:12px 18px;border-radius:8px;font-weight:800;text-decoration:none;font-size:12px;text-align:center}}
.btn-y{{background:#ffcc00;color:#000}} .btn-r{{background:#ff3333;color:#fff}}
</style></head><body>
<div class="header"><h1>VENUS v775 CLEAN UI LUMIA ONLY • SCAN #{scan} • 2 MAX • TP {TP_BASE}% • PRICE &lt;1.0</h1></div>
<div class="grid">
<div class="card"><div class="label">CAP $300 REAL</div><div class="value cap">${cap:.2f}</div><div class="sub">WITH OPEN {cap+unreal:.2f}</div></div>
<div class="card"><div class="label">TODAY / $50 TARGET</div><div class="value {'neg' if daily<0 else 'pos'}">${daily:+.2f}</div><div class="sub">STOP {DAILY_STOP} • CONSEC {learn.get('consecutive_losses',0)} • PAUSE {int((learn.get('pause_until',0)-time.time())/60) if learn.get('pause_until',0)>time.time() else 0}m</div></div>
<div class="card"><div class="label">WIN {winrate}%</div><div class="value win">W:{wins} L:{loss}</div><div class="sub">T:{tot} • INSTANT TP {TP_BASE}% • SL {SL_BASE}%</div></div>
</div>
"""

    if pumps:
        html+=f"""<div class="banner">PUMP HUNTER {len(pumps)} • TOP {pumps[0]['symbol']} +{pumps[0]['h1']:.1f}% FROM_LOW {pumps[0]['from_low']:.1f}% • LUMIA ONLY 3-6% EARLY • PRICE&lt;1.0 VOL&gt;16M</div>"""
        for p in pumps[:3]:
            html+=f"""<div class="list"><div class="item pos"><div class="left"><div class="sym">{p['symbol']} H1 +{p['h1']:.1f}% FROM_LOW {p['from_low']:.1f}%</div><div class="meta">VOL ${p['vol']} PRICE ${p['price']:.6f} SCORE {p['score']:.1f} NEAR_HIGH {p['near_high']:.1f}%</div></div><div class="right"><div class="pct pos">+{p['h1']:.1f}%</div><div class="meta">POS $100 TP {TP_BASE}% SL {SL_BASE}%</div></div></div></div>"""
    else:
        html+=f"""<div class="banner">PUMP HUNTER 0 • NO +EV LUMIA 3-6% EARLY • WAITING • PRICE&lt;1.0 VOL&gt;16M</div>"""

    html+=f"""<div class="banner2">OPEN {len(open_tr)}/{MAX_POS} MAX • TP {TP_BASE}% INSTANT • SL {SL_BASE}% • BAN ZRO/APT/WLD/FET/RLC • LUMIA ONLY</div>"""
    if not open_tr:
        html+=f"""<div class="list"><div class="item" style="justify-content:center;color:#666">NO OPEN POSITIONS • WAITING LUMIA 3-6% EARLY</div></div>"""
    for tr in open_tr:
        col="pos" if tr.get("pct",0)>=0 else "neg"
        html+=f"""<div class="list"><div class="item {col}"><div class="left"><div class="sym">{tr['symbol']} ${tr.get('pos')} AGE {tr.get('age',0)}s PEAK {tr.get('peak',0):.1f}%</div><div class="meta">ENTRY ${tr['entry']:.6f} → NOW ${tr['price']:.6f} H1 +{tr.get('h1',0):.1f}% FROM_LOW {tr.get('from_low',0):.1f}%</div></div><div class="right"><div class="pct {col}">{tr.get('pct',0):+.2f}% ${tr.get('net',0):+.2f}</div><div class="meta">TP {TP_BASE}% SL {SL_BASE}% QTY {tr.get('qty',0)}</div></div></div></div>"""

    html+=f"""<div class="closed"><h3>CLOSED {len(closed)} • W:{wins} L:{loss} T:{tot} • CAP ${cap:.2f} DAILY ${daily:+.2f}</h3>"""
    for cl in closed[:20]:
        c="g" if cl["net"]>0 else "r"
        html+=f"""<div class="row"><span><b class="{c}">{cl['symbol']}</b> <span class="{c}">${cl['net']:+.2f} {cl['reason']}</span> {cl['pct']:+.1f}% AGE {cl['age']}s</span></div>"""
    html+=f"""</div><div class="btns"><a class="btn btn-y" href="/api/cron?key={ADMIN_KEY}&cron=1">CRON v775 • CAP ${cap:.2f} • {len(pumps)} PUMPS</a><a class="btn btn-r" href="/api/nuke?key={ADMIN_KEY}">NUKE STUCK</a><a class="btn btn-y" href="/api/reset?key={ADMIN_KEY}" style="background:#333;color:#aaa">RESET $300</a></div></body></html>"""
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
        state=load_state()
        now_ts=int(time.time())
        open_tr=state.get("open",[])
        closed=state.get("closed",[])
        cap=state.get("cap",300.0)
        daily=state.get("daily",0.0)
        wins=state.get("wins",0)
        loss=state.get("loss",0)
        tot=state.get("total",0)
        tickers,_=get_tickers()
        for tr in open_tr:
            try:
                price_now=tr["price"]
                for tk in tickers:
                    if tk.get("symbol")==tr["symbol"]+"USDT":
                        price_now=float(tk.get("lastPrice",price_now))
                        break
                entry=tr["entry"]
                pct=(price_now-entry)/entry*100 if entry else tr.get("pct",0)
                net=float(POS_SIZE)*pct/100
                cap+=net
                daily+=net
                if net>0: wins+=1
                else: loss+=1
                tot+=1
                closed.insert(0, {"symbol":tr["symbol"],"net":net,"reason":f"NUKE FORCE CLOSE {pct:+.2f}% AGE {now_ts-tr.get('ts',now_ts)}s","pct":pct,"pos":tr.get("pos"),"age":now_ts-tr.get("ts",now_ts)})
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
        return Response(json.dumps({"ok":True,"nuked":len(open_tr),"cap":cap,"daily":daily}), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_set(STATE_KEY,{"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{"ZRO":int(time.time())+86400*7,"APT":int(time.time())+86400*7,"WLD":int(time.time())+86400*7,"FET":int(time.time())+86400*7,"RLC":int(time.time())+86400*7},"pause_until":0,"consecutive_losses":0}})
        return Response(json.dumps({"ok":True,"cap":300}), mimetype="application/json")
    st=load_state()
    h=render(st)
    return Response(h, mimetype="text/html")
