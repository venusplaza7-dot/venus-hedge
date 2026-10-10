
from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse, hmac, hashlib

app = Flask(__name__)

def env(n):
    for k in n:
        v=os.environ.get(k)
        if v: return v.strip().strip('"').strip("'")
    return ""
KV_URL=env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"]).rstrip("/")
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"]) or env(["KV_REST_API_READ_ONLY_TOKEN"])
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
BINANCE_BASE=env(["BINANCE_BASE"]) or "https://testnet.binance.vision"
BINANCE_KEY=env(["BINANCE_API_KEY","BINANCE_API_KEY_TESTNET"])
BINANCE_SECRET=env(["BINANCE_API_SECRET","BINANCE_SECRET_KEY","BINANCE_API_SECRET_TESTNET"])
REAL_TRADING=env(["BINANCE_REAL_TRADING"]) or "true"
POS_SIZE=env(["POS_SIZE"]) or "100"
STATE_KEY="VENUS_V750_LEARN_100_REAL"

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
    if not s: s={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"tp_adj":1.0,"sl_adj":1.0,"avoid_pump":0}}
    if s.get("cap",0)<100: s["cap"]=300.0
    if "learn" not in s: s["learn"]={"coins":{},"blacklist":{},"tp_adj":1.0,"sl_adj":1.0,"avoid_pump":0}
    now=int(time.time())
    s["learn"]["blacklist"]={k:v for k,v in s["learn"].get("blacklist",{}).items() if v>now}
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
            L["blacklist"][symbol]=int(time.time())+2700
            c["sl_hits"]=0
    c["pnl"]+=net
    closed=state.get("closed",[])[:6]
    if len(closed)>=5:
        recent_w = sum(1 for x in closed[:5] if x["net"]>0)
        if recent_w<=1:
            L["avoid_pump"]=1
            L["sl_adj"]=0.7
            L["tp_adj"]=0.8
        elif recent_w>=4:
            L["avoid_pump"]=0
            L["sl_adj"]=1.0
            L["tp_adj"]=1.3
        else:
            L["sl_adj"]=1.0
            L["tp_adj"]=1.0
            L["avoid_pump"]=0

def is_blacklisted(state, symbol):
    return symbol in state["learn"].get("blacklist",{}) and state["learn"]["blacklist"][symbol]>int(time.time())

def get_adaptive(state):
    L=state["learn"]
    return L.get("tp_adj",1.0), L.get("sl_adj",1.0), L.get("avoid_pump",0)

def build_pump_hunter():
    tickers, used_base = get_tickers()
    pumps=[]; whales=[]
    for t in tickers:
        try:
            s=t.get("symbol","")
            if not s.endswith("USDT"): continue
            if any(x in s for x in ["USDC","BUSD","FDUSD","TUSD","USDP"]): continue
            vol=float(t.get("quoteVolume","0"))
            if vol<2000000: continue
            price=float(t.get("lastPrice","0"))
            if price<0.0001: continue
            h1=float(t.get("priceChangePercent","0"))
            if h1>=3.0:
                if s in ["BTCUSDT","ETHUSDT"] and h1<5.0: continue
                pumps.append({"symbol":s.replace("USDT",""),"full":s,"price":price,"h1":h1,"vol":int(vol),"score":h1*15 + vol/800000,"tier":"PUMP","type":"PUMP"})
            elif h1>=0.5 and vol>=5000000:
                score = (vol/1000000)*2 + abs(h1)*3
                whales.append({"symbol":s.replace("USDT",""),"full":s,"price":price,"h1":h1,"vol":int(vol),"score":score,"tier":"WHALE","type":"WHALE FOOTPRINT"})
        except: continue
    pumps=sorted(pumps, key=lambda x: x["score"], reverse=True)
    whales=sorted(whales, key=lambda x: x["score"], reverse=True)[:8]
    all_display = sorted(pumps+whales, key=lambda x: x["score"], reverse=True)[:10]
    for i,f in enumerate(all_display): f["id"]=i+1
    build_pump_hunter.last_all = all_display
    build_pump_hunter.last_combined = (pumps+whales)[:10]
    return all_display, used_base

def do_cron():
    state=load_state()
    now=int(time.time())
    pumps, base = build_pump_hunter()
    combined = getattr(build_pump_hunter, "last_combined", pumps)
    if not combined:
        state["scan"]+=1
        kv_set(STATE_KEY, state)
        return {"ok":True,"scan":state["scan"],"msg":"NO PUMPS - PROTECT","cap":state["cap"],"pumps":0,"base":base}
    new_open=[]
    for tr in state.get("open",[]):
        try:
            sym_full=tr.get("full","")
            if not sym_full: continue
            req=urllib.request.Request(f"https://data-api.binance.vision/api/v3/ticker/price?symbol={sym_full}", headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as r:
                cur=float(json.loads(r.read().decode()).get("price","0"))
            entry=tr["entry"]; pct=(cur-entry)/entry*100 if entry else 0
            tr["price"]=cur; tr["pct"]=pct; tr["age"]=now-tr.get("ts",now)
            tr["peak"]=max(tr.get("peak",0), pct)
            # adaptive TP/SL
            tp_a, sl_a, _ = get_adaptive(state)
            tp_target = 1.0*tp_a
            sl_target = -1.0*sl_a
            should_close=False; reason=""
            if pct>=tp_target: should_close=True; reason=f"TP {tp_target:.1f}% QUICK +{pct:.1f}%"
            elif pct<=sl_target: should_close=True; reason=f"SL {sl_target:.1f}% QUICK {pct:.1f}%"
            elif tr["age"]>=180 and pct>=0.3: should_close=True; reason=f"TIME QUICK 180s {pct:.1f}%"
            elif tr["age"]>=600: should_close=True; reason=f"ROTATE 600s {pct:.1f}% QUICK"
            elif tr.get("peak",0)>=0.6 and pct<=tr.get("peak",0)-0.5: should_close=True; reason=f"TRAIL peak-0.5% {pct:.1f}%"
            if should_close:
                pos=float(tr.get("pos",100))
                net=pos*pct/100 - pos*0.002
                state["cap"]+=net; state["daily"]+=net
                if net>0: state["wins"]+=1
                else: state["loss"]+=1
                state["total"]+=1
                try: learn_from_trade(state, tr["symbol"], net, reason)
                except: pass
                state["closed"].insert(0, {"symbol":tr["symbol"],"net":round(net,2),"reason":reason,"pct":round(pct,2),"pos":tr.get("pos"),"age":tr["age"]})
                # sell real
                try:
                    qty=tr.get("qty",0)
                    if qty and BINANCE_KEY:
                        step,minQty=get_lot_size(sym_full)
                        q=round_qty(qty, step)
                        if q>=minQty:
                            data,err=binance_req("/api/v3/order", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, {"symbol":sym_full,"side":"SELL","type":"MARKET","quantity":str(q)}, "POST")
                            state["real_orders"].insert(0, {"side":"SELL","symbol":sym_full,"price":cur,"pos":tr.get("pos"),"result":str(data)[:200] if data else err[:200]})
                except: pass
            else:
                new_open.append(tr)
        except: new_open.append(tr)
    # LEARNING FILTER
    tp_adapt, sl_adapt, avoid_pump = get_adaptive(state)
    filtered=[]
    for cand in combined:
        if is_blacklisted(state, cand["symbol"]): continue
        if avoid_pump and cand.get("h1",0)>40 and cand.get("tier")=="PUMP": continue
        cs = state["learn"].get("coins",{}).get(cand["symbol"],{})
        if cs.get("pnl",0) < -3.0: continue
        filtered.append(cand)
    if filtered: combined=filtered
    need = 3 - len(new_open)
    if need>0:
        for cand in combined:
            if need<=0: break
            if any(x["symbol"]==cand["symbol"] for x in new_open): continue
            price=cand["price"]; pos=float(POS_SIZE)
            qty=pos/price
            tr={"symbol":cand["symbol"],"full":cand["full"],"entry":price,"price":price,"pos":pos,"qty":qty,"ts":now,"age":0,"pct":0,"peak":0,"h1":cand["h1"],"tier":cand["tier"],"move":cand["type"],"net":0}
            new_open.append(tr)
            need-=1
            try:
                if BINANCE_KEY:
                    step,minQty=get_lot_size(cand["full"])
                    q=round_qty(qty, step)
                    if q>=minQty:
                        data,err=binance_req("/api/v3/order", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, {"symbol":cand["full"],"side":"BUY","type":"MARKET","quoteOrderQty":str(pos)}, "POST")
                        state["real_orders"].insert(0, {"side":"BUY","symbol":cand["full"],"price":price,"pos":pos,"result":str(data)[:200] if data else err[:200]})
            except: pass
    state["open"]=new_open
    state["scan"]+=1
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":state["scan"],"open":len(new_open),"pumps":len(pumps),"base":base,"cap":state["cap"],"learn":state["learn"]}

def render(state):
    cap=state.get("cap",300); daily=state.get("daily",0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0)
    scan=state.get("scan",0); open_tr=state.get("open",[]); closed=state.get("closed",[]); real_orders=state.get("real_orders",[])
    unreal=sum([t.get("pct",0)/100*float(t.get("pos",100)) for t in open_tr])
    winrate=int(wins/tot*100) if tot else 0; daily_pct=round(daily/50*100,1) if daily else 0
    pumps=getattr(build_pump_hunter, "last_all", [])
    learn=state.get("learn",{}); bl=learn.get("blacklist",{})
    tp_a, sl_a, av = get_adaptive(state)
    learn_txt = f"LEARN AI: TP {tp_a:.1f}% SL {sl_a:.1f}% BL:{len(bl)} "
    if bl:
        try: learn_txt+= ",".join([f"{k}({int((v-time.time())/60)}m)" for k,v in list(bl.items())[:3]])
        except: learn_txt+= ",".join(list(bl.keys())[:3])
    if av: learn_txt+=" AVOID HIGH PUMP"
    bad = sorted([(k,v) for k,v in learn.get("coins",{}).items() if v.get("pnl",0)<0], key=lambda x: x[1]["pnl"])[:2]
    if bad: learn_txt+= " | BAD: " + ", ".join([f"{k} {v['w']}W{v['l']}L ${v['pnl']:+.1f}" for k,v in bad])
    html=f"""<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{{background:#000;color:#0f8;font-family:monospace;font-size:11px;margin:0;padding:4px}} .foot{{border:1px solid #333;padding:6px;margin:4px 0;background:#0a0a0a}} .bigrow{{display:flex;gap:4px}} .bigbox{{flex:1;border:1px solid #333;padding:6px;text-align:center;background:#111}} .yellowbar{{background:#ffcc00;color:#000;padding:6px;font-weight:bold;margin:4px 0;font-size:10px}}</style></head><body>
<div style="text-align:center;padding:6px;font-size:14px;font-weight:bold;color:#ffcc00">VENUS v752 RESTORED SMART LEARNING $300 REAL - SCAN #{scan} - 3 MAX - POS ${POS_SIZE} - {"LEARNING" if learn else ""}</div>
<div class="bigrow"><div class="bigbox"><div style="font-size:10px;color:#aaa">CAP $300 REAL</div><div style="font-size:26px;font-weight:bold;color:#ffcc00">${cap:.2f}</div><div style="font-size:10px;color:#aaa">WITH OPEN {cap+unreal:.2f}</div></div><div class="bigbox"><div style="font-size:10px;color:#aaa">TODAY / $50</div><div style="font-size:26px;font-weight:bold;color:{'#0f8' if daily>=0 else '#f44'}">${daily:+.2f}</div><div style="font-size:10px;color:#aaa">{daily_pct}% OF $50 TARGET</div></div><div class="bigbox"><div style="font-size:10px;color:#aaa">WIN {winrate}%</div><div style="font-size:18px;font-weight:bold;color:#0f8">W:{wins} L:{loss}<br>T:{tot}</div><div style="font-size:10px;color:#aaa">3 MAX PUMP+WHALE LEARN</div></div></div>
<div style="padding:6px;background:#111;border:1px solid #0ff;margin:4px"><div style="color:#0ff;font-size:10px">{learn_txt}</div></div>
<div class="yellowbar">PUMP+WHALE HUNTER {len(pumps)} - TOP {pumps[0]['symbol']+' +'+str(round(pumps[0]['h1'],1))+'% '+pumps[0].get('tier','') if pumps else 'NO PUMPS'} - TODAY $300 REAL HUNT LEARN</div>"""
    for fp in pumps[:10]:
        html+=f"""<div class="foot" style="border-color:{'#ffcc00' if fp.get('tier')=='PUMP' else '#0ff'}"><span style="color:{'#ffcc00' if fp.get('tier')=='PUMP' else '#0ff'};font-weight:bold">{fp.get('tier','PUMP')} #{fp['id']} {fp['symbol']} H1 +{fp['h1']:.1f}% {fp['type']}</span><br><span style="color:#0f8">VOL ${fp['vol']} PRICE ${fp['price']:.6f} SCORE {fp['score']:.1f}</span><br><span style="color:#ffcc00">POS ${POS_SIZE} TP {tp_a:.1f}% | SL {sl_a:.1f}%</span></div>"""
    html+=f"""<div class="yellowbar">OPEN {len(open_tr)}/3 MAX $300 REAL - LEARN AI - TP {tp_a:.1f}% | SL {sl_a:.1f}% | POS ${POS_SIZE}</div>"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:{'#ffcc00' if tr.get('tier')=='PUMP' else '#0ff'};font-weight:bold">{tr.get('move')} {tr['symbol']} ${tr.get('pos')} AGE {tr.get('age',0)}s {tr.get('tier','')}</span><br><span style="color:#0f8">ENTRY ${tr['entry']:.6f} -> NOW ${tr['price']:.6f} PEAK {tr.get('peak',0):.1f}% H1 {tr.get('h1',0):+.1f}%</span><br><span style="color:{col};font-size:18px;font-weight:bold">{tr.get('pct',0):+.2f}% ${tr.get('net',0):+.2f} REAL</span><br><span style="font-size:9px;color:#aaa">TP {tp_a:.1f}% | SL {sl_a:.1f}% | TRAIL peak-0.5% | QTY {tr.get('qty',0)}</span></div>"""
    html+=f"""<div style="padding:6px"><div style="color:#ffcc00;font-weight:bold;font-size:12px">CLOSED {len(closed)} - W:{wins} L:{loss} T:{tot} CAP ${cap:.2f} DAILY ${daily:+.2f} / $50</div>"""
    for cl in closed[:12]:
        ccol="#0f8" if cl["net"]>0 else "#f44"
        html+=f"""<div style="color:{ccol};padding:3px;border-bottom:1px solid #222;font-size:11px"><b>{cl['symbol']}</b> ${cl['net']:+.2f} {cl['reason']} {cl['pct']:+.1f}% POS ${cl.get('pos','')} AGE {cl['age']}s REAL</div>"""
    html+=f"""</div><div style="padding:6px"><div style="color:#ffcc00;font-weight:bold;font-size:11px">REAL ORDERS - TESTNET {len(real_orders)} - REAL_TRADING={REAL_TRADING}</div>"""
    for ro in real_orders[:10]:
        html+=f"""<div style="color:#0f8;padding:2px;font-size:10px">{ro.get('side')} {ro.get('symbol')} ${ro.get('price','')} POS ${ro.get('pos','')} {str(ro.get('result',''))[:150]}</div>"""
    html+=f"""</div><div style="text-align:center;padding:10px;color:#555;font-size:10px">v752 RESTORED SMART LEARNING $300 REAL - 3x$100 - LEARN FROM MISTAKES - KV:{'OK' if KV_URL else 'MISS'} SCAN #{scan} - <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON PUMP</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#0f8">RESET $300</a></div><div style="text-align:center;padding:12px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:12px 20px;text-decoration:none;font-weight:bold;font-size:12px">CRON PUMP - CAP ${cap:.2f} DAILY ${daily:+.2f}/$50</a></div></body></html>"""
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
