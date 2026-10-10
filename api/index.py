
import os, json, time, urllib.request, urllib.parse, hmac, hashlib
from flask import Flask, request, Response

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
REAL_TRADING=env(["BINANCE_REAL_TRADING"]) or "false"
POS_SIZE=env(["POS_SIZE"]) or "150"
STATE_KEY="VENUS_V748_LEARNING_AI_100_REAL"

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
    if not key or not secret:
        return None, "NO KEYS"
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
    except:
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
    if step==0 or step==1:
        return int(qty)
    # floor to step
    import math
    prec = int(round(-math.log10(step),0)) if step<1 else 0
    # round down
    floored = math.floor(qty/step)*step
    if prec>0:
        return round(floored, prec)
    return int(floored)


def build_pump_hunter():
    tickers, used_base = get_tickers()
    pumps=[]
    whales=[]
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
            elif h1<=-0.5 and vol>=8000000:
                score = (vol/1000000)*2 + abs(h1)*2
                whales.append({"symbol":s.replace("USDT",""),"full":s,"price":price,"h1":h1,"vol":int(vol),"score":score,"tier":"WHALE_DUMP","type":"WHALE DUMP REVERSAL"})
        except: continue
    pumps=sorted(pumps, key=lambda x: x["score"], reverse=True)
    whales=sorted(whales, key=lambda x: x["score"], reverse=True)[:8]
    all_display = sorted(pumps+whales, key=lambda x: x["score"], reverse=True)[:10]
    for i,f in enumerate(all_display): f["id"]=i+1
    build_pump_hunter.last_all = all_display
    build_pump_hunter.last_combined = (pumps+whales)[:10]
    return all_display, used_base

def load_state():
    s=kv_get(STATE_KEY)
    if not s: s={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[],"learn":{"coins":{},"blacklist":{},"tp_adj":1.0,"sl_adj":1.0,"avoid_pump":0}}
    if s.get("cap",0)<100: s["cap"]=300.0
    if "learn" not in s: s["learn"]={"coins":{},"blacklist":{},"tp_adj":1.0,"sl_adj":1.0,"avoid_pump":0}
    # cleanup expired blacklist
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
        if "SL" in reason:
            c["sl_hits"]+=1
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


def do_cron():
    state=load_state()
    now=int(time.time())
    pumps, base = build_pump_hunter()
    combined = getattr(build_pump_hunter, "last_combined", pumps)
    if not combined:
        state["scan"]+=1
        kv_set(STATE_KEY, state)
        return {"ok":True,"scan":state["scan"],"msg":"NO PUMPS OR WHALES - PROTECT $300 - NO TRADE","cap":state["cap"],"pumps":0,"base":base}
    new_open=[]
    for tr in state.get("open",[]):
        tr["age"]=now-tr.get("opened",now)
        fp=next((f for f in pumps if f["symbol"]==tr["symbol"]), None)
        if not fp:
            all_tickers,_=get_tickers()
            at=next((x for x in all_tickers if x.get("symbol")==tr.get("full")), None)
            if at:
                cur=float(at.get("lastPrice","0"))
                h1=float(at.get("priceChangePercent","0"))
            else:
                cur=tr.get("price",0)
                h1=tr.get("h1",0)
        else:
            cur=fp["price"]
            h1=fp["h1"]
        entry=tr.get("entry",cur)
        pct=(cur-entry)/entry*100 if entry else 0
        tr["price"]=cur; tr["pct"]=pct; tr["h1"]=h1
        tr["peak"]=max(tr.get("peak",pct),pct)
        pos=float(tr.get("pos",POS_SIZE))
        fee=pos*0.001
        net=pct/100*pos - fee
        tr["net"]=net
        close=False; reason=""
        if pct>=1.0: close=True; reason=f"TP 1.0% QUICK +${net:.2f} {tr.get('tier','')}"
        elif pct<=-1.0: close=True; reason=f"SL -1.0% QUICK {net:.2f}"
        elif tr["peak"]>=1.2 and pct<=tr["peak"]-0.5: close=True; reason=f"TRAIL QUICK peak {tr['peak']:.1f}%->{pct:.1f}% +${net:.2f}"
        elif tr["age"]>180 and pct>=0.3: close=True; reason=f"TIME QUICK 180s {pct:.1f}% +${net:.2f}"
        elif tr["age"]>600: close=True; reason=f"ROTATE 600s {pct:.1f}% QUICK"
        if close:
            state["closed"].insert(0,{"symbol":tr["symbol"],"net":net,"pct":pct,"reason":reason,"age":tr["age"],"pos":pos})
            state["closed"]=state["closed"][:30]
            state["cap"]+=net; state["daily"]+=net
            if net>0: state["wins"]+=1
            else: state["loss"]+=1
            state["total"]+=1
            try:
                learn_from_trade(state, tr["symbol"], net, reason)
            except: pass
            if REAL_TRADING.lower()=="true" and BINANCE_KEY and "testnet" in BINANCE_BASE:
                qty=tr.get("qty",0)
                step=tr.get("step",1)
                qty=round_qty(qty, step)
                if qty>0:
                    params={"symbol":tr["full"],"side":"SELL","type":"MARKET","quantity":qty}
                    data, err = binance_req("/api/v3/order", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, params, "POST")
                    state.setdefault("real_orders",[]).insert(0,{"side":"SELL","symbol":tr["symbol"],"result":str(data)[:200] if data else err,"time":now,"pct":pct})
        else:
            new_open.append(tr)
    state["open"]=new_open
    need=3-len(state["open"])
    open_sym=set(t["symbol"] for t in state["open"])
    cands=[f for f in combined if f["symbol"] not in open_sym]
    for i in range(need):
        if i>=len(cands): break
        c=cands[i]
        pos=float(POS_SIZE)
        step,minQty=get_lot_size(c["full"])
        raw_qty=pos / c["price"] if c["price"]>0 else 0
        qty=round_qty(raw_qty, step)
        if qty<minQty: qty=minQty
        state["open"].append({"symbol":c["symbol"],"full":c["full"],"entry":c["price"],"price":c["price"],"pct":0,"peak":0,"net":-pos*0.001,"opened":now,"age":0,"h1":c["h1"],"vol":c["vol"],"move":f"{c.get('tier','PUMP')}-{c['id']}","id":c["id"],"pos":pos,"qty":qty,"step":step,"tier":c.get("tier","PUMP")})
        if REAL_TRADING.lower()=="true" and BINANCE_KEY and "testnet" in BINANCE_BASE:
            params={"symbol":c["full"],"side":"BUY","type":"MARKET","quoteOrderQty":str(int(pos))}
            data, err = binance_req("/api/v3/order", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, params, "POST")
            state.setdefault("real_orders",[]).insert(0,{"side":"BUY","symbol":c["symbol"],"price":c["price"],"pos":pos,"result":str(data)[:200] if data else err,"time":now})
    state["scan"]+=1
    state["base"]=base
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":state["scan"],"open":len(state["open"]),"cap":round(state["cap"],2),"daily":round(state["daily"],2),"wins":state["wins"],"loss":state["loss"],"total":state["total"],"pumps":len(pumps),"top":pumps[0]["symbol"]+" +"+str(round(pumps[0]["h1"],1))+"%" if pumps else "NONE","base":base,"real_trading":REAL_TRADING,"pos":POS_SIZE}

def render(state):
    now=int(time.time())
    pumps, base = build_pump_hunter()
    cap=state.get("cap",300); daily=state.get("daily",0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); real_orders=state.get("real_orders",[])
    winrate=round(wins/tot*100,1) if tot>0 else 0
    unreal=sum(t.get("net",0) for t in open_tr)
    daily_target=50.0
    daily_pct=round(daily/daily_target*100,1) if daily_target else 0
    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v746 FLASK $300 REAL WHALE+PUMP</title>
<style>body{{background:#000;color:#0f8;font-family:monospace;margin:0}} .topdash{{background:#111;border-bottom:4px solid #ffcc00;padding:12px}} .bigbox{{background:#000;border:3px solid #ffcc00;padding:10px;text-align:center}} .bigrow{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:8px}} .yellowbar{{background:#ffcc00;color:#000;padding:8px;text-align:center;font-weight:bold;font-size:12px}} .foot{{border:2px solid #0f8;margin:4px;padding:6px;background:#0a0a0a;font-size:12px}}</style>
<meta http-equiv="refresh" content="15">
</head><body>
<div class="topdash">
<div style="text-align:center;color:#ffcc00;font-size:12px;font-weight:bold">VENUS v748 FLASK $300 REAL LEARNING AI 3x$100 - SCAN #{scan} - 3 MAX - POS ${POS_SIZE} - REAL_TRADING={REAL_TRADING}</div>
<div style="text-align:center;color:{'#0f8' if daily>=0 else '#f44'};font-size:11px">DAILY {daily:+.2f} / $50 TARGET {daily_pct}% - CAP ${cap:.2f} + UNREAL ${unreal:+.2f} = ${cap+unreal:.2f} REAL</div>
</div>
<div class="bigrow">
<div class="bigbox"><div style="font-size:10px;color:#aaa">CAP $300 REAL</div><div style="font-size:26px;font-weight:bold;color:#ffcc00">${cap:.2f}</div><div style="font-size:10px;color:#aaa">WITH OPEN {cap+unreal:.2f}</div></div>
<div class="bigbox"><div style="font-size:10px;color:#aaa">TODAY / $50</div><div style="font-size:26px;font-weight:bold;color:{'#0f8' if daily>=0 else '#f44'}">${daily:+.2f}</div><div style="font-size:10px;color:#aaa">{daily_pct}% OF $50 TARGET</div></div>
<div class="bigbox"><div style="font-size:10px;color:#aaa">WIN {winrate}%</div><div style="font-size:18px;font-weight:bold;color:#0f8">W:{wins} L:{loss}<br>T:{tot}</div><div style="font-size:10px;color:#aaa">3 MAX PUMP+WHALE</div></div>
</div>
<div class="yellowbar">PUMP+WHALE HUNTER {len(pumps)} - BASE {base} - TOP {pumps[0]['symbol']+' +'+str(round(pumps[0]['h1'],1))+'% '+pumps[0].get('tier','') if pumps else 'NO PUMPS - WHALE HUNT'} - TODAY $300 REAL HUNT</div>
"""
    for fp in pumps[:10]:
        html+=f"""<div class="foot" style="border-color:{'#ffcc00' if fp.get('tier')=='PUMP' else '#0ff'}"><span style="color:{'#ffcc00' if fp.get('tier')=='PUMP' else '#0ff'};font-weight:bold">{fp.get('tier','PUMP')} #{fp['id']} {fp['symbol']} H1 +{fp['h1']:.1f}% {fp['type']}</span><br><span style="color:#0f8">VOL ${fp['vol']} PRICE ${fp['price']:.6f} SCORE {fp['score']:.1f}</span><br><span style="color:#ffcc00">POS ${POS_SIZE} TP 1% +$1.20 net | SL -1% -$1.65</span></div>"""
    if not pumps:
        html+=f"""<div class="foot" style="border-color:#f44"><span style="color:#f44">NO PUMPS OR WHALES - PROTECTING $300 - NO TRADE</span></div>"""
    html+=f"""<div class="yellowbar">OPEN {len(open_tr)}/3 MAX $300 REAL - PUMP+WHALE ONLY - TP 1% +$1.20 | SL -1% | TRAIL 0.5% | POS ${POS_SIZE}</div>"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:{'#ffcc00' if tr.get('tier')=='PUMP' else '#0ff'};font-weight:bold">{tr.get('move')} {tr['symbol']} ${tr.get('pos')} AGE {tr.get('age',0)}s {tr.get('tier','')}</span><br><span style="color:#0f8">ENTRY ${tr['entry']:.6f} -> NOW ${tr['price']:.6f} PEAK {tr.get('peak',0):.1f}% H1 {tr.get('h1',0):+.1f}%</span><br><span style="color:{col};font-size:18px;font-weight:bold">{tr.get('pct',0):+.2f}% ${tr.get('net',0):+.2f} REAL</span><br><span style="font-size:9px;color:#aaa">TP 1% +$1.20 | SL -1% -$1.65 | TRAIL peak-0.5% | QTY {tr.get('qty',0)}</span></div>"""
    html+=f"""    learn=state.get("learn",{})
    bl = learn.get("blacklist",{})
    tp_a, sl_a, av = get_adaptive(state)
    learn_txt = f"LEARN AI: TP {tp_a:.1f}% SL {sl_a:.1f}% BL:{len(bl)} "
    if bl:
        learn_txt+= ",".join([f"{k}({int((v-time.time())/60)}m)" for k,v in list(bl.items())[:3]])
    if av:
        learn_txt+=" AVOID HIGH PUMP"
    bad = sorted([(k,v) for k,v in learn.get("coins",{}).items() if v.get("pnl",0)<0], key=lambda x: x[1]["pnl"])[:2]
    if bad:
        learn_txt+= " | BAD: " + ", ".join([f"{k} {v['w']}W{v['l']}L ${v['pnl']:+.1f}" for k,v in bad])
    html+=f"""<div style="padding:6px;background:#111;border:1px solid #0ff;margin:4px"><div style="color:#0ff;font-size:10px">{learn_txt}</div></div>"""
    html+=f"""<div style="padding:6px"><div style="color:#ffcc00;font-weight:bold;font-size:12px">CLOSED {len(closed)} - W:{wins} L:{loss} T:{tot} CAP ${cap:.2f} DAILY ${daily:+.2f} / $50</div>"""
    for cl in closed[:12]:
        ccol="#0f8" if cl["net"]>0 else "#f44"
        html+=f"""<div style="color:{ccol};padding:3px;border-bottom:1px solid #222;font-size:11px"><b>{cl['symbol']}</b> ${cl['net']:+.2f} {cl['reason']} {cl['pct']:+.1f}% POS ${cl.get('pos','')} AGE {cl['age']}s REAL</div>"""
    html+=f"""</div><div style="padding:6px"><div style="color:#ffcc00;font-weight:bold;font-size:11px">REAL ORDERS - TESTNET {len(real_orders)} - REAL_TRADING={REAL_TRADING}</div>"""
    for ro in real_orders[:10]:
        html+=f"""<div style="color:#0f8;padding:2px;font-size:10px">{ro.get('side')} {ro.get('symbol')} ${ro.get('price','')} POS ${ro.get('pos','')} {str(ro.get('result',''))[:150]}</div>"""
    html+=f"""</div><div style="text-align:center;padding:10px;color:#555;font-size:10px">v748 FLASK $300 REAL LEARNING AI - 3x$100 - TP1% SL1% QUICK - KV:{'OK' if KV_URL else 'MISS'} SCAN #{scan} - <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON PUMP</a> | <a href="/api/test_real?key={ADMIN_KEY}" style="color:#0f8">TEST REAL</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#0f8">RESET $300</a></div>
<div style="text-align:center;padding:12px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:12px 20px;text-decoration:none;font-weight:bold;font-size:12px">CRON PUMP - CAP ${cap:.2f} DAILY ${daily:+.2f}/$50</a> <a href="/api/test_real?key={ADMIN_KEY}" style="background:#0f8;color:#000;padding:12px 20px;text-decoration:none;font-weight:bold;margin-left:8px;font-size:12px">TEST REAL $300</a></div>
</body></html>"""
    return html

app = Flask(__name__)

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    from urllib.parse import urlparse, parse_qs
    key=request.args.get("key","")
    p="/"+path
    if p.startswith("/api/test_real"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        base=BINANCE_BASE
        pub_ok=False; btc_price="?"
        try:
            req=urllib.request.Request(f"https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT", headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                d=json.loads(r.read().decode()); btc_price=d.get('price'); pub_ok=True
        except: pass
        data, err = binance_req("/api/v3/account", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, {})
        res={"public": "OK "+str(btc_price) if pub_ok else "FAIL","base":base,"key_prefix":BINANCE_KEY[:8]+"..." if BINANCE_KEY else "MISSING","real_trading":REAL_TRADING,"pos":POS_SIZE,"btc":btc_price}
        if err: res["account"]=f"FAIL {err[:300]}"; res["connection"]="FAILED"
        else:
            bals=[f"{b['asset']}:{float(b['free']):.1f}" for b in data.get('balances',[]) if float(b.get('free','0'))>0.001 or b['asset']=='USDT'][:10]
            res["account"]="OK SUCCESS"; res["balances"]=bals; res["connection"]="SUCCESS $300 READY"; res["canTrade"]=data.get('canTrade')
            tp={"symbol":"BTCUSDT","side":"BUY","type":"MARKET","quoteOrderQty":"10"}
            d2,e2=binance_req("/api/v3/order/test", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, tp, "POST")
            res["order_test"]= "OK $10 BUY READY" if not e2 else f"FAIL {e2[:200]}"
        return Response(json.dumps(res, indent=2), mimetype="application/json")
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY and "cron" not in request.args: return Response("Forbidden", status=403)
        res=do_cron()
        return Response(json.dumps(res), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_set(STATE_KEY,{"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[]})
        return Response(json.dumps({"ok":True,"cap":300}), mimetype="application/json")
    st=load_state(); h=render(st)
    return Response(h, mimetype="text/html")

# For Vercel serverless - required top-level app
# This is the Flask instance Vercel looks for
handler = app

# Vercel requires top-level app variable
# app is already defined above as Flask instance
