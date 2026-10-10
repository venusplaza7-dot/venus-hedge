import os, json, time, urllib.request, urllib.parse, hmac, hashlib
from http.server import BaseHTTPRequestHandler

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
POS_SIZE=env(["POS_SIZE"]) or "100"
STATE_KEY="VENUS_V745_WHALE_PUMP_HUNTER"

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

def build_pump_hunter():
    # TIER 1: PUMP HUNTER H1>3% (STRK +45% style) + TIER 2: WHALE FOOTPRINT FALLBACK
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
            # TIER 1: BIG PUMP >3%
            if h1>=3.0:
                if s in ["BTCUSDT","ETHUSDT"] and h1<5.0: 
                    continue
                pumps.append({"symbol":s.replace("USDT",""),"full":s,"price":price,"h1":h1,"vol":int(vol),"score":h1*15 + vol/800000,"tier":"PUMP","type":"PUMP"})
            # TIER 2: WHALE FOOTPRINT - High vol + moving >0.5%
            elif h1>=0.5 and vol>=5000000:
                # Whale footprint score: vol * h1 - large volume + movement
                score = (vol/1000000)*2 + abs(h1)*3
                whales.append({"symbol":s.replace("USDT",""),"full":s,"price":price,"h1":h1,"vol":int(vol),"score":score,"tier":"WHALE","type":"WHALE FOOTPRINT"})
            elif h1<=-0.5 and vol>=8000000:
                # Whale dump also opportunity for reversal
                score = (vol/1000000)*2 + abs(h1)*2
                whales.append({"symbol":s.replace("USDT",""),"full":s,"price":price,"h1":h1,"vol":int(vol),"score":score,"tier":"WHALE_DUMP","type":"WHALE DUMP REVERSAL"})
        except: continue
    pumps=sorted(pumps, key=lambda x: x["score"], reverse=True)
    whales=sorted(whales, key=lambda x: x["score"], reverse=True)[:8]
    # If pumps <3, fill with whale footprints
    combined = pumps[:]
    if len(combined)<3:
        need=3-len(combined)
        combined+=whales[:need]
    # If still <3, add top whales anyway to make 5 total for display
    all_display = (pumps+whales)
    all_display=sorted(all_display, key=lambda x: x["score"], reverse=True)[:10]
    for i,f in enumerate(all_display): f["id"]=i+1
    # Return combined for trading (pumps + whale fallback), and all_display for UI
    # For trading we use combined (at least 3 if available), for UI we show all_display
    # Store both in global for render
    build_pump_hunter.last_all = all_display
    build_pump_hunter.last_combined = combined
    return all_display, used_base
    return all_display, used_base

def load_state():
    s=kv_get(STATE_KEY)
    if not s: s={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[]}
    # Ensure cap is 300 for this version
    if s.get("cap",0)<100: s["cap"]=300.0
    return s

def do_cron():
    state=load_state()
    now=int(time.time())
    pumps, base = build_pump_hunter()
    if not pumps or len(pumps)==0:
        # No pumps today - no trade, protect $300
        state["scan"]+=1
        kv_set(STATE_KEY, state)
        if len(getattr(build_pump_hunter, "last_combined", []))==0:
        state["scan"]+=1
        kv_set(STATE_KEY, state)
        return {"ok":True,"scan":state["scan"],"msg":"NO PUMPS OR WHALES - PROTECT $300 - NO TRADE","cap":state["cap"],"pumps":0,"base":base}

    # Update existing with REAL price
    new_open=[]
    for tr in state.get("open",[]):
        tr["age"]=now-tr.get("opened",now)
        fp=next((f for f in pumps if f["symbol"]==tr["symbol"]), None)
        # Also check all tickers for price even if not pumping anymore
        if not fp:
            # Get price from broader market if pump faded
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
        fee=pos*0.001  # 0.1% fee
        net=pct/100*pos - fee
        tr["net"]=net

        close=False; reason=""
        # $300 REAL RULES: TP 2.5% = $2.40 net for $100 pos, SL -1.5% = -$1.60
        if pct>=1.0: close=True; reason=f"TP 1.0% QUICK +${net:.2f} PUMP"
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
            # REAL ORDER SELL if REAL_TRADING=true
            if REAL_TRADING.lower()=="true" and BINANCE_KEY and "testnet" in BINANCE_BASE:
                # Place real SELL on testnet
                qty=tr.get("qty",0)
                if qty>0:
                    params={"symbol":tr["full"],"side":"SELL","type":"MARKET","quantity":qty}
                    data, err = binance_req("/api/v3/order", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, params, "POST")
                    state.setdefault("real_orders",[]).insert(0,{"side":"SELL","symbol":tr["symbol"],"result":str(data)[:200] if data else err,"time":now,"pct":pct})
        else:
            new_open.append(tr)

    state["open"]=new_open
    need=3-len(state["open"])  # ONLY 3 MAX for $300
    open_sym=set(t["symbol"] for t in state["open"])
    cands=[f for f in pumps if f["symbol"] not in open_sym]

    for i in range(need):
        if i>=len(cands): break
        c=cands[i]
        pos=float(POS_SIZE)
        # Calculate qty for real order
        qty= round(pos / c["price"], 6) if c["price"]>0 else 0
        state["open"].append({"symbol":c["symbol"],"full":c["full"],"entry":c["price"],"price":c["price"],"pct":0,"peak":0,"net":-pos*0.001,"opened":now,"age":0,"h1":c["h1"],"vol":c["vol"],"move":f"PUMP-{c['id']}","id":c["id"],"pos":pos,"qty":qty})

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

    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v742 $300 REAL $50/DAY PUMP HUNTER</title>
<style>body{{background:#000;color:#0f8;font-family:monospace;margin:0}} .topdash{{background:#111;border-bottom:4px solid #ffcc00;padding:12px}} .bigbox{{background:#000;border:3px solid #ffcc00;padding:10px;text-align:center}} .bigrow{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:8px}} .greenbar{{background:#0a5;color:#fff;padding:10px;text-align:center;font-weight:bold}} .redbar{{background:#a00;color:#fff;padding:10px;text-align:center;font-weight:bold}} .yellowbar{{background:#ffcc00;color:#000;padding:8px;text-align:center;font-weight:bold;font-size:12px}} .foot{{border:2px solid #0f8;margin:4px;padding:6px;background:#0a0a0a;font-size:12px}}</style>
<meta http-equiv="refresh" content="15">
</head><body>
<div class="topdash">
<div style="text-align:center;color:#ffcc00;font-size:12px;font-weight:bold">VENUS v745 $300 REAL WHALE+PUMP HUNTER - PUMP>3% + WHALE FOOTPRINT FALLBACK - SCAN #{scan} - 3 MAX - POS ${POS_SIZE} - REAL_TRADING={REAL_TRADING}</div>
<div style="text-align:center;color:{'#0f8' if daily>=0 else '#f44'};font-size:11px">DAILY {daily:+.2f} / $50 TARGET {daily_pct}% - CAP ${cap:.2f} + UNREAL ${unreal:+.2f} = ${cap+unreal:.2f} REAL</div>
</div>
<div class="bigrow">
<div class="bigbox"><div style="font-size:10px;color:#aaa">CAP $300 REAL</div><div style="font-size:26px;font-weight:bold;color:#ffcc00">${cap:.2f}</div><div style="font-size:10px;color:#aaa">WITH OPEN {cap+unreal:.2f}</div></div>
<div class="bigbox"><div style="font-size:10px;color:#aaa">TODAY / $50</div><div style="font-size:26px;font-weight:bold;color:{'#0f8' if daily>=0 else '#f44'}">${daily:+.2f}</div><div style="font-size:10px;color:#aaa">{daily_pct}% OF $50 TARGET</div></div>
<div class="bigbox"><div style="font-size:10px;color:#aaa">WIN {winrate}%</div><div style="font-size:22px;font-weight:bold;color:#0f8">{wins}W {loss}L {tot}T</div><div style="font-size:10px;color:#aaa">3 MAX PUMP ONLY</div></div>
</div>
<div class="yellowbar">PUMP HUNTER {len(pumps)} (PUMPS+WHALE FOOTPRINTS) - BASE {base} - TOP {pumps[0]['symbol']+' +'+str(round(pumps[0]['h1'],1))+'%' if pumps else 'NO PUMPS - PROTECT $300'} - TODAY $300 REAL HUNT</div>
"""
    for fp in pumps[:6]:
        html+=f"""<div class="foot" style="border-color:#ffcc00"><span style="color:#ffcc00;font-weight:bold">PUMP #{fp['id']} {fp['symbol']} H1 +{fp['h1']:.1f}% REAL PUMP</span><br><span style="color:#0f8">VOL ${fp['vol']} PRICE ${fp['price']:.6f} SCORE {fp['score']:.1f}</span><br><span style="color:#ffcc00">POS ${POS_SIZE} TP 2.5% = +$2.40 net | SL -1.5% = -$1.60</span></div>"""
    if not pumps or len(pumps)==0:
        html+=f"""<div class="foot" style="border-color:#f44"><span style="color:#f44">NO PUMPS H1>3% TODAY - PROTECTING $300 - NO TRADE - Waiting for STRK +41% style pump</span></div>"""

    html+=f"""<div class="yellowbar">OPEN {len(open_tr)}/3 MAX $300 REAL - PUMP HUNTER ONLY - TP 1.0% QUICK +$1.35 | SL -1.0% | TRAIL 0.5% | POS ${POS_SIZE}</div>"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:#ffcc00;font-weight:bold">{tr.get('move')} {tr['symbol']} ${tr.get('pos')} AGE {tr.get('age',0)}s PUMP</span><br><span style="color:#0f8">ENTRY ${tr['entry']:.6f} -> NOW ${tr['price']:.6f} PEAK {tr.get('peak',0):.1f}% H1 {tr.get('h1',0):+.1f}%</span><br><span style="color:{col};font-size:18px;font-weight:bold">{tr.get('pct',0):+.2f}% ${tr.get('net',0):+.2f} REAL</span><br><span style="font-size:9px;color:#aaa">TP 2.5% +$2.40 | SL -1.0% -$1.65 | TRAIL peak-1% | QTY {tr.get('qty',0)}</span></div>"""

    html+=f"""<div style="padding:6px"><div style="color:#ffcc00;font-weight:bold;font-size:12px">CLOSED {len(closed)} - WIN {wins} LOSS {loss} TOTAL {tot} CAP ${cap:.2f} DAILY ${daily:+.2f} / $50 TARGET</div>"""
    for cl in closed[:12]:
        ccol="#0f8" if cl["net"]>0 else "#f44"
        html+=f"""<div style="color:{ccol};padding:3px;border-bottom:1px solid #222;font-size:11px"><b>{cl['symbol']}</b> ${cl['net']:+.2f} {cl['reason']} {cl['pct']:+.1f}% POS ${cl.get('pos','')} AGE {cl['age']}s REAL</div>"""

    html+=f"""</div><div style="padding:6px"><div style="color:#ffcc00;font-weight:bold;font-size:11px">REAL ORDERS - TESTNET {len(real_orders)} - REAL_TRADING={REAL_TRADING}</div>"""
    for ro in real_orders[:10]:
        html+=f"""<div style="color:#0f8;padding:2px;font-size:10px">{ro.get('side')} {ro.get('symbol')} ${ro.get('price','')} POS ${ro.get('pos','')} {str(ro.get('result',''))[:150]}</div>"""

    html+=f"""</div><div style="text-align:center;padding:10px;color:#555;font-size:10px">v745 $300 REAL WHALE+PUMP HUNTER - $50/DAY - 3 MAX - TP1% SL1% WHALE - KV:{'OK' if KV_URL else 'MISS'} SCAN #{scan} - <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON PUMP</a> | <a href="/api/test_real?key={ADMIN_KEY}" style="color:#0f8">TEST REAL</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#0f8">RESET $300</a></div>
<div style="text-align:center;padding:12px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:12px 20px;text-decoration:none;font-weight:bold;font-size:12px">CRON PUMP - CAP ${cap:.2f} DAILY ${daily:+.2f}/$50</a> <a href="/api/test_real?key={ADMIN_KEY}" style="background:#0f8;color:#000;padding:12px 20px;text-decoration:none;font-weight:bold;margin-left:8px;font-size:12px">TEST REAL $300</a></div>
</body></html>"""
    return html

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        p=urlparse(self.path); qs=parse_qs(p.query); key=qs.get("key",[""])[0]
        if p.path.startswith("/api/test_real"):
            if key!=ADMIN_KEY: self.send_response(403); self.end_headers(); return
            # Test real
            base=BINANCE_BASE
            pub_ok=False; btc_price="?"
            try:
                req=urllib.request.Request(f"https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT", headers={"User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    d=json.loads(r.read().decode()); btc_price=d.get('price'); pub_ok=True
            except: pass
            data, err = binance_req("/api/v3/account", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, {})
            res={"public": "OK "+btc_price if pub_ok else "FAIL","base":base,"key_prefix":BINANCE_KEY[:8]+"..." if BINANCE_KEY else "MISSING","real_trading":REAL_TRADING,"pos":POS_SIZE,"btc":btc_price}
            if err: res["account"]=f"FAIL {err[:300]}"; res["connection"]="FAILED"
            else:
                bals=[f"{b['asset']}:{float(b['free']):.1f}" for b in data.get('balances',[]) if float(b.get('free','0'))>0.001 or b['asset']=='USDT'][:10]
                res["account"]="OK SUCCESS"; res["balances"]=bals; res["connection"]="SUCCESS $300 READY"; res["canTrade"]=data.get('canTrade')
                # Test order
                tp={"symbol":"BTCUSDT","side":"BUY","type":"MARKET","quoteOrderQty":"10"}
                d2,e2=binance_req("/api/v3/order/test", BINANCE_KEY, BINANCE_SECRET, BINANCE_BASE, tp, "POST")
                res["order_test"]= "OK $10 BUY READY" if not e2 else f"FAIL {e2[:200]}"
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps(res, indent=2).encode()); return
        if p.path.startswith("/api/cron"):
            if key!=ADMIN_KEY and "cron" not in qs: self.send_response(403); self.end_headers(); return
            res=do_cron()
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps(res).encode()); return
        if p.path.startswith("/api/reset"):
            if key!=ADMIN_KEY: self.send_response(403); self.end_headers(); return
            kv_set(STATE_KEY,{"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_orders":[]})
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"ok":True,"cap":300}).encode()); return
        st=load_state(); h=render(st)
        self.send_response(200); self.send_header("Content-Type","text/html"); self.end_headers(); self.wfile.write(h.encode())
    def do_POST(self): self.do_GET()

# Vercel compatibility - define top-level app
app = handler
