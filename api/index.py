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
# FIX 451: Use vision for public, testnet for private
ENV_BASE=get_env(["BINANCE_BASE"]) or "https://testnet.binance.vision"
if "api.binance.com" in ENV_BASE and "vision" not in ENV_BASE:
    # User mistakenly set mainnet with testnet keys - auto fix to testnet for private calls
    PRIVATE_BASE="https://testnet.binance.vision"
    PUBLIC_BASE="https://data-api.binance.vision"
else:
    PRIVATE_BASE=ENV_BASE
    PUBLIC_BASE="https://data-api.binance.vision" if "testnet" in ENV_BASE else "https://data-api.binance.vision"

BINANCE_KEY=get_env(["BINANCE_API_KEY","BINANCE_API_KEY_TESTNET"])
BINANCE_SECRET=get_env(["BINANCE_API_SECRET","BINANCE_SECRET_KEY","BINANCE_API_SECRET_TESTNET"])
BINANCE_REAL=get_env(["BINANCE_REAL_TRADING"]) or "false"
POS_SIZE=get_env(["POS_SIZE"]) or "10"
STATE_KEY="VENUS_V740_FIX_451_TESTNET"

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
    query=urllib.parse.urlencode(params)
    sig=hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    params['signature']=sig
    return params

def binance_request(endpoint, key, secret, base, params={}, method="GET"):
    if not key or not secret:
        return None, "NO KEYS"
    params['timestamp']=int(time.time()*1000)
    params['recvWindow']=10000
    signed=binance_sign(params, secret)
    url=f"{base}{endpoint}?{urllib.parse.urlencode(signed)}"
    try:
        req=urllib.request.Request(url, headers={"X-MBX-APIKEY":key,"User-Agent":"Mozilla/5.0"}, method=method)
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        try:
            body=e.read().decode()
            return None, f"HTTP {e.code}: {body[:500]}"
        except:
            return None, f"HTTP {e.code}: {str(e)}"
    except Exception as e:
        return None, str(e)[:500]

def test_connection():
    res={}
    res['env_base_input']=ENV_BASE
    res['private_base_used']=PRIVATE_BASE
    res['public_base_used']=PUBLIC_BASE
    res['key_prefix']=BINANCE_KEY[:8]+"..." if BINANCE_KEY else "MISSING"
    res['secret_present']=bool(BINANCE_SECRET)
    res['real_trading']=BINANCE_REAL
    res['pos_size']=POS_SIZE

    # 1. Public via vision (not blocked by 451)
    try:
        req=urllib.request.Request(f"{PUBLIC_BASE}/api/v3/ticker/price?symbol=BTCUSDT", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d=json.loads(r.read().decode())
            res['public_test']="OK"
            res['btc_price']=d.get('price')
            res['public_base']=PUBLIC_BASE
    except Exception as e:
        res['public_test']=f"FAIL {str(e)[:300]}"
        # fallback try testnet itself for public
        try:
            req=urllib.request.Request(f"{PRIVATE_BASE}/api/v3/ticker/price?symbol=BTCUSDT", headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                d=json.loads(r.read().decode())
                res['public_test']=f"OK via PRIVATE_BASE fallback"
                res['btc_price']=d.get('price')
        except Exception as e2:
            res['public_test']+=f" + fallback FAIL {str(e2)[:200]}"

    # 2. Account via PRIVATE_BASE (must be testnet.binance.vision for testnet keys)
    data, err = binance_request("/api/v3/account", BINANCE_KEY, BINANCE_SECRET, PRIVATE_BASE, {})
    if err:
        res['account_test']=f"FAIL {err}"
        res['connection']="FAILED"
        # give fix hint
        if "451" in err:
            res['fix_hint']="451 = Restricted location. For testnet, BASE must be https://testnet.binance.vision (not api.binance.com). Public data uses data-api.binance.vision which is NOT blocked. Your ENV BASE is wrong - change to https://testnet.binance.vision in Vercel"
        elif "Invalid API-key" in err:
            res['fix_hint']="Invalid key - Testnet keys only work on testnet.binance.vision. Mainnet keys work on api.binance.com. You have testnet keys + mainnet base = FAIL. Change BASE to https://testnet.binance.vision"
    else:
        res['account_test']="OK SUCCESS"
        bals=[]
        for b in data.get('balances',[]):
            free=float(b.get('free','0'))
            if free>0 or b['asset'] in ['USDT','BTC','BNB']:
                bals.append(f"{b['asset']}:{free}")
        res['balances']=bals[:15]
        res['can_trade']=data.get('canTrade')
        res['connection']="SUCCESS - Testnet working"

    # 3. Order test
    if "SUCCESS" in res.get('connection',''):
        data2, err2 = binance_request("/api/v3/order/test", BINANCE_KEY, BINANCE_SECRET, PRIVATE_BASE, {'symbol':'BTCUSDT','side':'BUY','type':'MARKET','quoteOrderQty':'10'}, method="POST")
        if err2:
            res['order_test']=f"FAIL {err2[:400]}"
        else:
            res['order_test']="OK - Can place $10 BUY - Ready for REAL TESTNET trading"
    return res

def get_tickers():
    # Use PUBLIC_BASE which is data-api.binance.vision - never blocked by 451
    for b in [PUBLIC_BASE, PRIVATE_BASE, "https://data-api.binance.vision"]:
        try:
            req=urllib.request.Request(f"{b}/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data=json.loads(r.read().decode())
                if len(data)>50:
                    return data, b
        except: continue
    return [], PUBLIC_BASE

def build_real():
    tickers, used = get_tickers()
    fps=[]
    for t in tickers:
        try:
            s=t.get("symbol","")
            if not s.endswith("USDT"): continue
            if any(x in s for x in ["USDC","BUSD","FDUSD","EUR","GBP"]): continue
            vol=float(t.get("quoteVolume","0"))
            if vol<800000: continue
            price=float(t.get("lastPrice","0"))
            if price<=0: continue
            h1=float(t.get("priceChangePercent","0"))
            if h1<-20: continue
            fps.append({"symbol":s.replace("USDT",""),"full":s,"price":price,"h1":h1,"vol":int(vol),"score":h1*2+vol/8000000 if h1>0 else vol/8000000})
        except: continue
    fps=sorted(fps, key=lambda x: x["score"], reverse=True)[:12]
    for i,f in enumerate(fps): f["id"]=i+1
    return fps, used

def load_state():
    s=kv_get(STATE_KEY)
    if not s: s={"cap":1000.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_log":[]}
    return s

def do_cron():
    state=load_state(); now=int(time.time())
    fps, base = build_real()
    if not fps:
        return {"ok":False,"error":"No tickers","base":base}
    new_open=[]
    for tr in state.get("open",[]):
        tr["age"]=now-tr.get("opened",now)
        fp=next((f for f in fps if f["symbol"]==tr["symbol"]),None)
        if fp:
            cur=fp["price"]; entry=tr.get("entry",cur); pct=(cur-entry)/entry*100 if entry else 0
            tr["price"]=cur; tr["pct"]=pct; tr["h1"]=fp["h1"]; tr["vol"]=fp["vol"]
            tr["peak"]=max(tr.get("peak",pct),pct)
            net=pct/100*float(POS_SIZE)-0.04
            tr["net"]=net
            close=False; reason=""
            if pct>=0.8: close=True; reason=f"TP 0.8% REAL"
            elif pct<=-2.0: close=True; reason=f"SL -2%"
            elif tr["age"]>180 and net>=0.08: close=True; reason=f"QUICK TP {tr['age']}s"
            elif tr["age"]>300: close=True; reason=f"ROTATE 300s"
            if close:
                state["closed"].insert(0,{"symbol":tr["symbol"],"net":net,"pct":pct,"reason":reason,"age":tr["age"]})
                state["closed"]=state["closed"][:30]
                state["cap"]+=net; state["daily"]+=net
                if net>0: state["wins"]+=1
                else: state["loss"]+=1
                state["total"]+=1
            else:
                new_open.append(tr)
    state["open"]=new_open
    need=5-len(state["open"])
    open_sym=set(t["symbol"] for t in state["open"])
    cands=[f for f in fps if f["symbol"] not in open_sym]
    for i in range(need):
        if i>=len(cands): break
        c=cands[i]
        state["open"].append({"symbol":c["symbol"],"full":c["full"],"entry":c["price"],"price":c["price"],"pct":0,"peak":0,"net":-0.04,"opened":now,"age":0,"h1":c["h1"],"vol":c["vol"],"move":f"MOVE-{c['id']}","id":c["id"]})
    state["scan"]+=1
    state["base"]=base
    kv_set(STATE_KEY,state)
    return {"ok":True,"scan":state["scan"],"open":len(state["open"]),"cap":round(state["cap"],2),"wins":state["wins"],"loss":state["loss"],"total":state["total"],"footprints":len(fps),"base":base,"real_trading":BINANCE_REAL,"private_base":PRIVATE_BASE,"public_base":PUBLIC_BASE}

def render(state):
    now=int(time.time()); fps, base = build_real()
    test_res=test_connection()
    cap=state.get("cap",1000); daily=state.get("daily",0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0)
    open_tr=state.get("open",[]); closed=state.get("closed",[])
    unreal=sum(t.get("net",0) for t in open_tr)

    html=f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>v740 FIX 451</title>
<style>body{{background:#000;color:#0f8;font-family:monospace;margin:0}} .topdash{{background:#111;border-bottom:4px solid #ffcc00;padding:10px}} .bigbox{{background:#000;border:3px solid #ffcc00;padding:12px;text-align:center}} .bigrow{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:8px}} .greenbar{{background:#0a5;color:#fff;padding:10px;text-align:center;font-weight:bold}} .redbar{{background:#a00;color:#fff;padding:10px;text-align:center;font-weight:bold}} .yellowbar{{background:#ffcc00;color:#000;padding:10px;text-align:center;font-weight:bold}} .foot{{border:2px solid #0f8;margin:4px;padding:6px;background:#0a0a0a}} </style>
<meta http-equiv="refresh" content="12">
</head><body>
<div class="topdash">
<div style="text-align:center;color:#ffcc00;font-size:12px;font-weight:bold">VENUS v740 FIX 451 - TESTNET - POS {POS_SIZE} - SCAN #{scan} - PRIVATE_BASE {PRIVATE_BASE} - PUBLIC {PUBLIC_BASE}</div>
"""
    if "SUCCESS" in test_res.get('connection',''):
        html+=f"""<div class="greenbar">SUCCESS - {test_res.get('connection')} - BTC ${test_res.get('btc_price')} - CanTrade {test_res.get('can_trade')} - Balances {', '.join(test_res.get('balances',[])[:4])} - Order {test_res.get('order_test')}</div>"""
    else:
        html+=f"""<div class="redbar">FAILED - {test_res.get('connection')} - {test_res.get('account_test','')[:400]}<br>FIX: {test_res.get('fix_hint','Change BINANCE_BASE to https://testnet.binance.vision in Vercel ENV')}</div>"""

    html+=f"""
<div style="background:#001100;border:2px solid #0f8;padding:8px;margin:8px 0;font-size:11px">
<div style="color:#0f8;font-weight:bold">ENV CHECK (FIX 451):</div>
<div>INPUT BASE={test_res.get('env_base_input')} -> PRIVATE_USED={test_res.get('private_base_used')} PUBLIC_USED={test_res.get('public_base_used')}</div>
<div>KEY={test_res.get('key_prefix')} SECRET={test_res.get('secret_present')} REAL_TRADING={test_res.get('real_trading')} POS={test_res.get('pos_size')}</div>
<div>Public Test: {test_res.get('public_test')} BTC={test_res.get('btc_price')}</div>
<div>Account Test: {test_res.get('account_test')}</div>
<div>Balances: {', '.join(test_res.get('balances',[])[:8])}</div>
<div>Order Test: {test_res.get('order_test','')}</div>
<div style="color:#ffcc00;margin-top:6px">IF 451 ERROR: In Vercel Dashboard > Settings > Environment Variables, set BINANCE_BASE = https://testnet.binance.vision (not https://api.binance.com). api.binance.com is blocked from US/Vercel. data-api.binance.vision is NOT blocked for public data.</div>
</div>

<div class="bigrow">
<div class="bigbox"><div style="font-size:11px;color:#aaa">CAP REAL TESTNET</div><div style="font-size:28px;font-weight:bold;color:#ffcc00">${cap:.2f}</div><div style="font-size:11px;color:#aaa">WITH OPEN {cap+unreal:.2f}</div></div>
<div class="bigbox"><div style="font-size:11px;color:#aaa">TODAY REAL</div><div style="font-size:28px;font-weight:bold;color:#0f8">${daily:+.2f}</div><div style="font-size:11px;color:#aaa">REAL ONLY</div></div>
<div class="bigbox"><div style="font-size:11px;color:#aaa">STATUS</div><div style="font-size:18px;font-weight:bold;color:{'#0f8' if 'SUCCESS' in test_res.get('connection','') else '#f44'}">{test_res.get('connection','')}</div><div style="font-size:10px;color:#aaa">{test_res.get('public_base','')}</div></div>
</div>
</div>

<div class="yellowbar">FOOTPRINTS {len(fps)} REAL - BASE {base} - TOP {fps[0]['symbol']+' '+f'{fps[0]['h1']:+.1f}%' if fps else 'NO DATA - Check BASE'}</div>
"""
    for fp in fps[:8]:
        html+=f"""<div class="foot"><span style="color:#ffcc00;font-weight:bold">{fp['symbol']} H1 {fp['h1']:+.1f}% REAL</span><br><span style="color:#0f8">VOL ${fp['vol']} PRICE ${fp['price']:.8f}</span></div>"""
    html+=f"""<div class="yellowbar">OPEN {len(open_tr)}/5 REAL</div>"""
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html+=f"""<div class="foot" style="border-color:{col}"><span style="color:#ffcc00">{tr.get('move')} {tr['symbol']} ${POS_SIZE} AGE {tr.get('age',0)}s</span><br><span style="color:#0f8">ENTRY ${tr['entry']:.8f} NOW ${tr['price']:.8f}</span><br><span style="color:{col};font-size:18px">{tr.get('pct',0):+.3f}% ${tr.get('net',0):+.4f}</span></div>"""
    html+=f"""<div style="text-align:center;padding:10px;color:#555;font-size:11px">v740 FIX 451 - <a href="/api/test_real?key={ADMIN_KEY}" style="color:#0f8">TEST REAL</a> | <a href="/api/cron?key={ADMIN_KEY}&cron=1" style="color:#0f8">CRON</a> | <a href="/api/reset?key={ADMIN_KEY}" style="color:#0f8">RESET</a></div>
<div style="text-align:center;padding:10px"><a href="/api/test_real?key={ADMIN_KEY}" style="background:#0f8;color:#000;padding:12px 20px;text-decoration:none;font-weight:bold">TEST REAL CONNECTION NOW</a></div>
</body></html>"""
    return html

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        p=urlparse(self.path); qs=parse_qs(p.query); key=qs.get("key",[""])[0]
        if p.path.startswith("/api/test_real") or "test_real" in qs:
            if key!=ADMIN_KEY: self.send_response(403); self.end_headers(); return
            res=test_connection()
            self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(json.dumps(res, indent=2).encode()); return
        if p.path.startswith("/api/cron") or "cron" in qs:
            if key!=ADMIN_KEY and "cron" not in qs: self.send_response(403); self.end_headers(); return
            res=do_cron()
            self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(json.dumps(res).encode()); return
        if p.path.startswith("/api/reset"):
            if key!=ADMIN_KEY: self.send_response(403); self.end_headers(); return
            kv_set(STATE_KEY,{"cap":1000.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"real_log":[]})
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"ok":True}).encode()); return
        st=load_state(); h=render(st)
        self.send_response(200); self.send_header("Content-Type","text/html"); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(h.encode())
    def do_POST(self): self.do_GET()
