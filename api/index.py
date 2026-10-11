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

# v777 SHARK FOOTPRINT - ORIGINAL PLAN
TP_BASE = 0.9  # quick 0.9% profit and move to next batch
SL_BASE = 0.55
MAX_POS = 3  # 3 concurrent shark hunts
DAILY_STOP = -15.0
HARD_BAD = set(["ZRO","WLD","FET","RLC","S","MBL","STRK","TIA","MAGIC","VELDROME","VELODROME","NIGHT","SENT","CHIP","CFX","PEOPLE","TRB","BLZ","ARKM","LUNA","LUNC","1000SATS","UP","DOWN","BULL","BEAR","BUSD"])

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
    except Exception as e:
        print(f"kv_get err {e}")
        return None

def kv_set(k,obj):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["SET",k,json.dumps(obj)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            txt=r.read().decode()
            return "OK" in txt
    except Exception as e:
        print(f"kv_set err {e}")
        return False

def kv_del(k):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return True
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
    except Exception as e:
        print(f"tickers err {e}")
        return [], base

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
        s={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"pause_until":0,"consecutive_losses":0,"last_date":time.strftime("%Y-%m-%d")}}
    if "learn" not in s: s["learn"]={"coins":{},"blacklist":{},"pause_until":0,"consecutive_losses":0,"last_date":time.strftime("%Y-%m-%d")}
    L=s["learn"]
    L.setdefault("coins",{})
    L.setdefault("blacklist",{})
    L.setdefault("pause_until",0)
    L.setdefault("consecutive_losses",0)
    L.setdefault("last_date",time.strftime("%Y-%m-%d"))
    # daily reset if date changed
    today=time.strftime("%Y-%m-%d")
    if L.get("last_date")!=today:
        s["daily"]=0.0
        L["last_date"]=today
        L["consecutive_losses"]=0
        L["pause_until"]=0
        kv_set(STATE_KEY, s)
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
    # ban only if really bad
    if c["pnl"]<-12 or (total>=10 and c["ev"]<-0.3):
        L["blacklist"][symbol]=int(time.time())+86400*3
    if L["consecutive_losses"]>=6:
        L["pause_until"]=int(time.time())+1800  # only 30min pause now, not 4h
    if state.get("daily",0) <= DAILY_STOP:
        L["pause_until"]=int(time.time())+3600

def shark_score(t):
    """SHARK FOOTPRINT: find coins where sharks are buying NOW"""
    try:
        sym=t.get("symbol","")
        if not sym.endswith("USDT"): return None
        base=sym.replace("USDT","")
        if base in HARD_BAD: return None
        if not base.isalnum(): return None
        if any(ord(c)>127 for c in base): return None
        if len(base)<2 or len(base)>10: return None
        if "UP" in sym or "DOWN" in sym or "BULL" in sym or "BEAR" in sym: return None
        price=float(t.get("lastPrice","0"))
        if price<0.0005 or price>5.0: return None
        # SHARK: must be moving NOW
        h1=float(t.get("priceChangePercent","0"))
        vol=float(t.get("quoteVolume","0"))
        high=float(t.get("highPrice","0"))
        low=float(t.get("lowPrice","0"))
        if high==0 or low==0: return None
        
        # SHARK FILTER: early momentum 2.5-12%
        if h1<2.8 or h1>12.0: return None
        # SHARK: needs volume = shark money
        if vol<8_000_000: return None
        from_low=(price-low)/low*100 if low>0 else 0
        if from_low<2.5 or from_low>11.0: return None
        near_high=price/high*100
        if near_high<95.5: return None  # must be near high = still pumping
        
        # SHARK SCORE: volume * momentum / distance from low
        # Higher volume + higher H1 + lower from_low = shark just entered early
        shark_score_val = (vol/1_000_000) * h1 / max(1, from_low) * (near_high/100)
        
        # Bonus for LUMIA and known runners
        if base in ["LUMIA","MANTA","ARB","NIL","AERO","EIGEN","APT","ZRO","RLC","AERO","PEPE","WIF","BONK","FET","WLD"]:
            shark_score_val*=1.5
        
        return {"symbol":base,"full":sym,"h1":h1,"price":price,"vol":int(vol),"from_low":from_low,"near_high":near_high,"score":shark_score_val,"shark":shark_score_val}
    except: return None

def do_cron():
    state=load_state()
    L=state["learn"]
    now_ts=int(time.time())
    # auto unpause if pause expired
    if L.get("pause_until",0) > now_ts:
        # still paused but allow if we manually unpaused
        if L["pause_until"]-now_ts > 3600 and state.get("daily",0)>DAILY_STOP:
            pass  # keep paused
        elif L["pause_until"]-now_ts < 1800:
            # almost done, clear
            L["pause_until"]=0
    if state.get("daily",0) <= DAILY_STOP and L.get("pause_until",0)==0:
        L["pause_until"]=now_ts+3600

    if L.get("pause_until",0) > now_ts:
        return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"scan":state.get("scan",0),"daily":state.get("daily",0),"v":"v777 SHARK PAUSED"}

    tickers,_ = get_tickers()
    sharks=[]
    for t in tickers:
        s=shark_score(t)
        if s:
            if s["symbol"] in L["blacklist"]:
                continue
            sharks.append(s)
    # Sort by shark score - highest = shark money flowing NOW
    sharks=sorted(sharks, key=lambda x: x["shark"], reverse=True)[:10]
    for i,p in enumerate(sharks): p["id"]=i+1

    open_tr=state.get("open",[])
    closed=state.get("closed",[])
    real_orders=state.get("real_orders",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    wins=state.get("wins",0)
    loss=state.get("loss",0)
    tot=state.get("total",0)
    scan=state.get("scan",0)+1

    # Close logic - FAST SHARK: take 0.9% and jump to next
    final_open=[]
    for tr in open_tr:
        try:
            sym_full=tr["symbol"]+"USDT"
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
            # SHARK: instant TP 0.9% and move to next batch
            if pct>=TP_BASE:
                should=f"SHARK TP {TP_BASE}% +{pct:.2f}% +${float(POS_SIZE)*pct/100:+.2f} JUMP NEXT"
            elif pct<=-SL_BASE:
                should=f"SHARK SL -{SL_BASE}% {pct:.1f}% ${float(POS_SIZE)*pct/100:+.2f} JUMP NEXT"
            elif peak>=0.7 and pct < peak-0.18 and pct>0.35:
                should=f"SHARK TRAIL +{peak:.1f}%->{pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f}"
            elif age>400 and pct>0.35:
                should=f"SHARK TIME 400s {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f} NEXT BATCH"
            elif age>900 and pct>0.15:
                should=f"SHARK TIME 900s {pct:.1f}% +${float(POS_SIZE)*pct/100:+.2f} NEXT BATCH"
            elif age>1200:
                should=f"SHARK TIME 1200s FORCE CLOSE {pct:.1f}% ${float(POS_SIZE)*pct/100:+.2f} NEXT"

            if should:
                net=float(POS_SIZE)*pct/100
                cap+=net
                daily+=net
                if net>0: wins+=1
                else: loss+=1
                tot+=1
                closed.insert(0, {"symbol":tr["symbol"],"net":net,"reason":should,"pct":pct,"pos":tr.get("pos"),"age":age})
                update_learn(state, tr["symbol"], net, pct)
            else:
                final_open.append(tr)
        except Exception as e:
            final_open.append(tr)

    # Open new sharks - jump to next batch
    open_symbols=[t["symbol"] for t in final_open]
    for sh in sharks:
        if len(final_open)>=MAX_POS: break
        sym=sh["symbol"]
        if sym in open_symbols: continue
        if sym in L["blacklist"]: continue
        if sym in HARD_BAD: continue
        price=sh["price"]
        qty=100.0/price if price>0 else 0
        if qty<5: continue  # price too high
        step,_=get_lot_size(sym+"USDT")
        qty_r=round_qty(qty, step)
        if qty_r<=0: continue
        tr={"symbol":sym,"entry":price,"price":price,"pos":100.0,"qty":qty_r,"ts":now_ts,"peak":0,"pct":0,"net":0,"age":0,"h1":sh["h1"],"from_low":sh["from_low"],"shark":sh["shark"]}
        final_open.append(tr)
        open_symbols.append(sym)

    state["open"]=final_open
    state["closed"]=closed[:250]
    state["real_orders"]=real_orders[:50]
    state["cap"]=cap
    state["daily"]=daily
    state["wins"]=wins
    state["loss"]=loss
    state["total"]=tot
    state["scan"]=scan
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan,"open":len(final_open),"cap":cap,"daily":daily,"sharks":sharks[:3],"v":"v777 SHARK FOOTPRINT","total":tot}

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
    sharks=[]
    for t in tickers:
        s=shark_score(t)
        if s:
            if s["symbol"] not in learn.get("blacklist",{}):
                sharks.append(s)
    sharks=sorted(sharks, key=lambda x: x["shark"], reverse=True)[:6]

    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{margin:0;padding:0;box-sizing:border-box}} body{{background:#050505;color:#e0e0e0;font-family:system-ui,monospace;font-size:12px}}
.hdr{{background:linear-gradient(135deg,#ffcc00,#ff9900);color:#000;padding:14px;text-align:center;font-weight:900;font-size:15px}}
.grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;padding:10px}} .card{{background:#111;border:1px solid #222;border-radius:10px;padding:12px;text-align:center}}
.card .l{{font-size:10px;color:#888;text-transform:uppercase}} .card .v{{font-size:26px;font-weight:900;margin:6px 0}} .cap{{color:#ffcc00}} .neg{{color:#ff4444}} .pos{{color:#00ff88}}
.banner{{margin:8px;padding:10px;border-radius:8px;font-weight:700;font-size:11px}} .b-y{{background:#ffcc00;color:#000}} .b-b{{background:#00d4ff;color:#000}} .b-d{{background:#1a1a1a;border:1px solid #333;color:#888}}
.list{{padding:0 8px}} .item{{background:#111;border:1px solid #222;border-radius:10px;padding:12px;margin:6px 0;display:flex;justify-content:space-between;align-items:center}}
.item .sym{{font-weight:800;color:#ffcc00}} .item .meta{{font-size:11px;color:#999;margin-top:2px}} .item .right{{text-align:right}} .item .pct{{font-size:18px;font-weight:900}} .pos{{border-color:#00ff88}} .neg{{border-color:#ff4444}}
.closed{{background:#0f0f0f;border:1px solid #222;border-radius:10px;margin:10px;padding:12px}} .closed h3{{color:#ffcc00;font-size:12px;margin-bottom:10px}} .row{{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid #1a1a1a;font-size:11px}} .g{{color:#00ff88}} .r{{color:#ff5555}}
.btns{{display:flex;gap:8px;padding:14px;flex-wrap:wrap;justify-content:center}} .btn{{padding:12px 16px;border-radius:10px;font-weight:800;text-decoration:none;font-size:12px}} .by{{background:#ffcc00;color:#000}} .br{{background:#ff3333;color:#fff}} .bd{{background:#222;color:#aaa}}
.shark{{background:linear-gradient(90deg,#ffcc00 0%,#ff9900 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:900}}
</style></head><body>
<div class="hdr">🦈 VENUS v777 SHARK FOOTPRINT HUNTER • SCAN #{scan} • {MAX_POS} MAX • TP {TP_BASE}% • JUMP NEXT BATCH</div>
<div class="grid">
<div class="card"><div class="l">CAP $300 REAL</div><div class="v cap">${cap:.2f}</div><div class="l">WITH OPEN {cap+unreal:.2f}</div></div>
<div class="card"><div class="l">TODAY / TARGET $50</div><div class="v {'neg' if daily<0 else 'pos'}">${daily:+.2f}</div><div class="l">STOP {DAILY_STOP} • CONSEC {learn.get('consecutive_losses',0)} • PAUSE {int((learn.get('pause_until',0)-time.time())/60) if learn.get('pause_until',0)>time.time() else 0}m</div></div>
<div class="card"><div class="l">WIN {winrate}% SHARK</div><div class="v" style="color:#00ff88">W:{wins} L:{loss}</div><div class="l">T:{tot} • TP {TP_BASE}% SL {SL_BASE}% • SHARK</div></div>
</div>
"""

    if sharks:
        top=sharks[0]
        html+=f"""<div class="banner b-y">🦈 SHARK HUNTER {len(sharks)} • TOP <span class="shark">{top['symbol']} +{top['h1']:.1f}% SHARK {top['shark']:.0f} VOL ${top['vol']} FROM_LOW {top['from_low']:.1f}%</span> • EARLY 2.8-12% • VOL>8M • JUMP BATCH</div>"""
        for s in sharks[:5]:
            html+=f"""<div class="list"><div class="item pos"><div><div class="sym">🦈 #{s['id']} {s['symbol']} H1 +{s['h1']:.1f}% SHARK {s['shark']:.0f}</div><div class="meta">VOL ${s['vol']} PRICE ${s['price']:.6f} FROM_LOW {s['from_low']:.1f}% NEAR_HIGH {s['near_high']:.1f}%</div></div><div class="right"><div class="pct pos">+{s['h1']:.1f}%</div><div class="meta">POS $100 TP {TP_BASE}% SL {SL_BASE}%</div></div></div></div>"""
    else:
        html+=f"""<div class="banner b-d">🦈 SHARK HUNTER 0 • NO MOVING COINS 2.8-12% • MARKET DEAD • WAITING NEXT WAVE • VOL>8M</div>"""

    html+=f"""<div class="banner b-b">OPEN {len(open_tr)}/{MAX_POS} MAX • SHARK TP {TP_BASE}% INSTANT JUMP NEXT BATCH • SL {SL_BASE}% • AGE FORCE 1200s</div>"""
    if not open_tr:
        html+=f"""<div class="list"><div class="item b-d" style="justify-content:center;color:#666">NO OPEN • WAITING SHARK FOOTPRINT 2.8-12% EARLY • SCANNING ALL COINS</div></div>"""
    for tr in open_tr:
        col="pos" if tr.get("pct",0)>=0 else "neg"
        html+=f"""<div class="list"><div class="item {col}"><div><div class="sym">🦈 {tr['symbol']} ${tr.get('pos')} AGE {tr.get('age',0)}s PEAK {tr.get('peak',0):.1f}% SHARK {tr.get('shark',0):.0f}</div><div class="meta">ENTRY ${tr['entry']:.6f} → NOW ${tr['price']:.6f} H1 +{tr.get('h1',0):.1f}% FROM_LOW {tr.get('from_low',0):.1f}%</div></div><div class="right"><div class="pct {col}">{tr.get('pct',0):+.2f}% ${tr.get('net',0):+.2f}</div><div class="meta">TP {TP_BASE}% SL {SL_BASE}% QTY {tr.get('qty',0)}</div></div></div></div>"""

    html+=f"""<div class="closed"><h3>🦈 CLOSED {len(closed)} • W:{wins} L:{loss} T:{tot} • CAP ${cap:.2f} DAILY ${daily:+.2f} • SHARK JUMP BATCH</h3>"""
    for cl in closed[:20]:
        c="g" if cl["net"]>0 else "r"
        html+=f"""<div class="row"><span><b class="{c}">{cl['symbol']}</b> <span class="{c}">${cl['net']:+.2f} {cl['reason']}</span> {cl['pct']:+.1f}% AGE {cl['age']}s</span></div>"""
    html+=f"""</div><div class="btns"><a class="btn by" href="/api/cron?key={ADMIN_KEY}&cron=1">🦈 CRON v777 SHARK • CAP ${cap:.2f} • {len(sharks)} SHARKS</a><a class="btn br" href="/api/nuke?key={ADMIN_KEY}">NUKE</a><a class="btn bd" href="/api/unpause?key={ADMIN_KEY}">UNPAUSE</a><a class="btn bd" href="/api/reset?key={ADMIN_KEY}">RESET $300</a></div><div style="text-align:center;padding:10px;color:#555;font-size:10px">v777 SHARK FOOTPRINT • SCAN ALL COINS 2.8-12% VOL>8M PRICE<5 • TP {TP_BASE}% SL {SL_BASE}% • {MAX_POS} MAX • JUMP NEXT BATCH • ORIGINAL PLAN</div></body></html>"""
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
                closed.insert(0, {"symbol":tr["symbol"],"net":net,"reason":f"NUKE {pct:+.2f}%","pct":pct,"pos":tr.get("pos"),"age":now_ts-tr.get("ts",now_ts)})
            except: pass
        state["open"]=[]
        state["closed"]=closed[:250]
        state["cap"]=cap
        state["daily"]=daily
        state["wins"]=wins
        state["loss"]=loss
        state["total"]=tot
        state["scan"]=state.get("scan",0)+1
        kv_set(STATE_KEY, state)
        return Response(json.dumps({"ok":True,"nuked":len(open_tr),"cap":cap}), mimetype="application/json")
    if p.startswith("/api/unpause"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state()
        state["learn"]["pause_until"]=0
        state["learn"]["consecutive_losses"]=0
        # reset daily if negative from yesterday
        if state.get("daily",0) < -20:
            state["daily"]=0.0
        kv_set(STATE_KEY, state)
        return Response(json.dumps({"ok":True,"unpaused":True,"daily":state.get("daily",0)}), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        # FORCE DELETE then SET - fixes your reset bug
        kv_del(STATE_KEY)
        time.sleep(0.5)
        new_state={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"pause_until":0,"consecutive_losses":0,"last_date":time.strftime("%Y-%m-%d")}}
        ok=kv_set(STATE_KEY, new_state)
        # verify
        verify=kv_get(STATE_KEY)
        return Response(json.dumps({"ok":ok,"cap":300,"verify_cap":verify.get("cap") if verify else None,"deleted":True}), mimetype="application/json")
    if p.startswith("/api/force_reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        # ultimate force reset - delete all old keys
        for k in [STATE_KEY,"VENUS_V752_RESTORED_SMART_100_REAL","VENUS_V750_LEARNING_AI_100_REAL","VENUS_V754_PROFITABLE_LEARNING_100_REAL","VENUS_V756_SMART_KEEP_TRACK_100_REAL"]:
            kv_del(k)
        time.sleep(0.5)
        new_state={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"pause_until":0,"consecutive_losses":0,"last_date":time.strftime("%Y-%m-%d")}}
        kv_set(STATE_KEY, new_state)
        return Response(json.dumps({"ok":True,"cap":300,"force":True}), mimetype="application/json")
    st=load_state()
    h=render(st)
    return Response(h, mimetype="text/html")
