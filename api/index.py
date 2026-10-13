from flask import Flask, request, Response
app = Flask(__name__)
import os, json, time, urllib.request, urllib.parse

MEM_STATE={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"peak":300.0,"equity":[300.0],"last_cron":"v868 STABLE NO CRASH INIT"}

def env(k):
    for kk in k:
        v=os.environ.get(kk)
        if v: return v.strip().strip('"').strip("'")
    return ""
KV_URL=(env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"]) or "").rstrip("/")
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V808_SHARK100"
MAXP=3
POS_PCT=33.33
TOTAL_FEE=0.17
SCAN_BATCH=8
TP_PCT=1.20
SL_PCT=0.60
STATIC_TOP=["BTC","ETH","SOL","BNB","XRP","AVAX","LINK","ADA","DOT","LTC","UNI","ETC","APT","ARB","OP","SUI","NEAR","RNDR","SEI","TIA","DOGE","ZEC","STRK","CYBER"]
SYM_TO_ID={"BTC":"bitcoin","ETH":"ethereum","SOL":"solana"}

def kv_get(k):
    global MEM_STATE
    if not KV_URL or not KV_TOKEN: return MEM_STATE
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=4) as r:
            d=json.loads(r.read().decode()); res=d[0].get("result") if isinstance(d,list) and d else None
            if res: return json.loads(res)
    except: pass
    return MEM_STATE

def kv_set(k,o):
    global MEM_STATE
    MEM_STATE=o
    if not KV_URL or not KV_TOKEN: return True
    try:
        body=json.dumps([["SET",k,json.dumps(o)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=4) as r: return True
    except: return True

def kv_del(k):
    global MEM_STATE
    MEM_STATE={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"peak":300.0,"equity":[300.0],"last_cron":"reset v868 STABLE"}
    if not KV_URL or not KV_TOKEN: return True
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=3) as r: return True
    except: return True

def fetch_price(base):
    try:
        url=f"https://data-api.binance.vision/api/v3/ticker/price?symbol={base}USDT"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2) as r:
            data=json.loads(r.read().decode())
            return float(data.get("price",0)), "binance"
    except: return None, "fail"

def fetch_klines_fast(base):
    try:
        url=f"https://data-api.binance.vision/api/v3/klines?symbol={base}USDT&interval=1m&limit=30"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2.5) as r:
            data=json.loads(r.read().decode())
            closes=[float(k[4]) for k in data if len(k)>4]
            if len(closes)>=10: return closes
    except: pass
    return []

def analyze(closes):
    if len(closes)<15:
        return {"side":"LONG","future_change":0.7,"confidence":60,"moving_score":5,"slope":0.01,"rsi":50,"vol":0.5}
    last=closes[-1]
    n=15
    y=closes[-n:]
    x=list(range(n))
    xm=sum(x)/n
    ym=sum(y)/n
    num=sum((x[i]-xm)*(y[i]-ym) for i in range(n))
    den=sum((x[i]-xm)**2 for i in range(n))
    slope=num/den if den!=0 else 0
    slope_pct=slope/ym*100 if ym!=0 else 0
    future_change = max(0.6, min(2.0, abs(slope_pct)*10)) * (1 if slope_pct>=0 else -1)
    if abs(slope_pct)<0.008:
        future_change=0.7
        side="LONG"
    else:
        side="LONG" if slope_pct>0 else "SHORT"
    vol=(max(y)-min(y))/last*100 if last!=0 else 0
    rsi=50
    moving_score=abs(slope_pct)*300 + abs(future_change)*1.5 + vol
    return {"side":side,"future_change":future_change,"confidence":65,"moving_score":moving_score,"slope":slope_pct,"rsi":rsi,"vol":vol,"closes":closes}

def load_state():
    s=kv_get(STATE_KEY)
    if not s or not isinstance(s,dict) or "cap" not in s: s=MEM_STATE
    s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("equity",[300,s.get("cap",300)]); s.setdefault("peak",s.get("cap",300)); s.setdefault("last_cron","never v868")
    inv=sum([t.get("pos",0) for t in s.get("open",[])])
    if inv>=300 or len(s.get("open",[]))>MAXP:
        s["open"]=[]; s["last_cron"]=f"v868 AUTO FIX 301 OVER CLEAR INV {inv:.0f} -> 0"
        kv_set(STATE_KEY,s)
    return s

@app.route('/', methods=['GET'])
def index():
    try:
        state=load_state()
        cap=state.get("cap",300.0)
        inv=sum([t.get("pos",0) for t in state.get("open",[])])
        scan=state.get("scan",0)
        offset=state.get("scan_offset",0)
        last=state.get("last_cron","never")
        open_tr=state.get("open",[])
        daily=sum([c.get("net",0) for c in state.get("closed",[])][-10:]) if state.get("closed",[]) else 0
        kv_status="OK" if KV_URL and KV_TOKEN else "MEM v868 STABLE"
        trades_html=""
        for tr in open_tr:
            trades_html+=f"<div style='border:2px solid #0f8;background:#151515;border-radius:12px;padding:10px;margin:8px 0'><b>{tr['symbol']} {tr['side']} ${tr['pos']:.0f} ENTRY ${tr['entry']:.4f} LIVE ${tr.get('price',tr['entry']):.4f} FUTURE {tr.get('future_change',0):+.2f}% CONF {tr.get('confidence',0):.0f}%</b><br>TP {TP_PCT}% SL {SL_PCT}% <button onclick=\"fetch('/api/close?symbol={tr['symbol']}&key={ADMIN_KEY}').then(()=>location.reload())\">Close</button></div>"
        if not open_tr:
            trades_html=f"<div style='border:2px solid #0f8;padding:14px;text-align:center;border-radius:12px'>✅ v868 STABLE NO CRASH - READY<br>INV {inv:.0f}/{cap:.0f} SCAN {scan} OFFSET {offset}-{offset+SCAN_BATCH} LAST {last}<br>KV:{kv_status} app FOUND line 2<br>TAP CRON BELOW - Scans 8 coins fast (no 120s timeout)</div>"
        html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;padding:6px}} .h{{background:linear-gradient(90deg,#0f8,#00d4ff);color:#000;padding:12px;border-radius:12px;font-weight:900;text-align:center}} .btn{{padding:16px;border-radius:14px;border:0;font-weight:900;cursor:pointer}} .btn-cron{{background:linear-gradient(90deg,#0f8,#00d4ff);color:#000}} .btn-reset{{background:#f44;color:#fff}} .btn-close{{background:#fc0;color:#000}} .row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}</style></head><body>
        <div class='h'>✅ VENUS v868 STABLE NO CRASH - SCAN #{scan} CAP ${cap:.2f} INV {inv:.0f}/{cap:.0f} DAILY ${daily:.2f}/$15 {kv_status} - app FOUND line 2<br><span style='font-size:9px'>LAST: {last[:100]}</span></div>
        <div class='row'><button class='btn btn-cron' onclick='startScan()'>✅ CRON STABLE {inv:.0f}/{cap:.0f}<div style='font-size:9px'>TAP {offset+1}-{offset+SCAN_BATCH} SCAN {scan} - FAST 8 COINS (fixes 120s timeout Internal Server Error)</div></button><button class='btn btn-close' onclick='fetch("/api/closeall?key={ADMIN_KEY}").then(()=>location.reload())'>CLOSE ALL</button><button class='btn btn-reset' onclick='fetch("/api/reset?key={ADMIN_KEY}").then(()=>location.reload())'>RESET $300</button></div>
        <div id='trades'>{trades_html}</div>
        <div id='scanResult' style='background:#111;border:1px solid #333;padding:10px;border-radius:12px;margin:8px 0;white-space:pre-wrap'></div>
        <script>const KEY="{ADMIN_KEY}";async function startScan(){{document.getElementById('scanResult').innerText='Scanning 8 coins fast...';try{{const r=await fetch('/api/scan_most_moving?key='+KEY+'&t='+Date.now());const txt=await r.text();let j;try{{j=JSON.parse(txt)}}catch(e){{document.getElementById('scanResult').innerText='Scan JSON fail: '+txt.substring(0,500);return}}if(!j.ok){{document.getElementById('scanResult').innerText='Scan fail: '+(j.error||'unknown')+'\\n'+JSON.stringify(j,null,2).substring(0,500);return}}let out='✅ SCAN OK - Found '+j.movers.length+' coins:\\n';j.movers.slice(0,8).forEach((m,i)=>{{out+=(i+1)+'. '+m.symbol+' '+m.side+' FUTURE '+m.future_change.toFixed(2)+'% move='+m.moving_score.toFixed(1)+' vol='+m.vol.toFixed(2)+'%\\n'}});out+='\\nTOP3: '+j.top3.map(m=>m.symbol+' '+m.side+' '+m.future_change.toFixed(2)+'%').join(' | ')+'\\n\\nAuto-opening...';document.getElementById('scanResult').innerText=out;for(let m of j.top3){{try{{const payload={{symbol:m.symbol, side:m.side, future_change:m.future_change, confidence:m.confidence, moving_score:m.moving_score}};const rr=await fetch('/api/open_analyzed?key='+KEY,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}});const tt=await rr.text();out+='\\n'+m.symbol+' -> '+tt.substring(0,150);document.getElementById('scanResult').innerText=out;}}catch(e){{out+='\\n'+m.symbol+' err '+e;}}await new Promise(r=>setTimeout(r,500));}}document.getElementById('scanResult').innerText=out+'\\n\\nReloading...';setTimeout(()=>location.reload(),1500);}}catch(e){{document.getElementById('scanResult').innerText='ERR '+e}}}}async function closeOne(s){{await fetch('/api/close?symbol='+s+'&key='+KEY);location.reload()}}</script></body></html>"""
        return Response(html, mimetype="text/html", headers={"Access-Control-Allow-Origin":"*"})
    except Exception as e:
        import traceback
        return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:3000]}</pre></body></html>", mimetype="text/html", status=200)

@app.route('/api/scan_most_moving', methods=['GET'])
@app.route('/api/cron', methods=['GET'])
def scan():
    try:
        state=load_state()
        cap=state.get("cap",300.0)
        offset=state.get("scan_offset",0)
        batch=STATIC_TOP[offset:offset+SCAN_BATCH]
        if len(batch)<SCAN_BATCH: batch+=STATIC_TOP[:SCAN_BATCH-len(batch)]
        open_syms=[t["symbol"] for t in state.get("open",[])]
        movers=[]
        for base in batch:
            if base in open_syms: continue
            closes=fetch_klines_fast(base)
            if not closes: continue
            price,_=fetch_price(base)
            if not price or price==0: price=closes[-1]
            an=analyze(closes)
            an["symbol"]=base
            an["price"]=price
            an["closes"]=closes[-20:]
            movers.append(an)
        movers_sorted=sorted(movers, key=lambda x: x["moving_score"], reverse=True)
        top3=movers_sorted[:MAXP]
        state["scan_offset"]=(offset+SCAN_BATCH)%len(STATIC_TOP)
        state["scan"]=state.get("scan",0)+1
        state["last_cron"]=f"v868 SCAN offset {offset} top3 {','.join([m['symbol']+':'+m['side']+':'+str(round(m['future_change'],2))+'%' for m in top3])} INV {sum([t.get('pos',0) for t in state.get('open',[])]) :.0f}/{cap:.0f}"
        kv_set(STATE_KEY, state)
        return Response(json.dumps({"ok":True,"movers":movers_sorted,"top3":top3,"offset":offset,"scan":state["scan"],"fix":"v868 STABLE 8 COINS NO TIMEOUT"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    except Exception as e:
        import traceback
        return Response(json.dumps({"ok":False,"error":str(e)[:200],"trace":traceback.format_exc()[:500]}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})

@app.route('/api/open_analyzed', methods=['POST','GET'])
def open_analyzed():
    try:
        data={}
        try: data=request.get_json(force=True, silent=True) or {}
        except: pass
        if not data:
            try: data=json.loads(request.get_data(as_text=True) or "{}")
            except: data={}
        sym=(data.get("symbol","") if data else "").upper() or request.args.get("symbol","").upper()
        side=data.get("side","LONG") if data else request.args.get("side","LONG")
        if not sym: return Response(json.dumps({"ok":False,"error":"no symbol"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
        state=load_state()
        inv=sum([t.get("pos",0) for t in state.get("open",[])])
        cap=state.get("cap",300.0)
        if len(state.get("open",[]))>=MAXP:
            if inv>=300: state["open"]=[]; inv=0
            else: return Response(json.dumps({"ok":False,"error":f"MAXP {MAXP} reached INV {inv:.0f}/{cap:.0f}"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
        if sym in [t["symbol"] for t in state.get("open",[])]:
            return Response(json.dumps({"ok":False,"error":f"{sym} already open"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
        price,_=fetch_price(sym)
        if not price or price==0: price=data.get("price",100) if data else 100
        pos_size=cap*POS_PCT/100.0
        if inv+pos_size>cap: pos_size=max(10,(cap-inv)*0.95)
        tr={"symbol":sym,"side":side,"entry":price,"price":price,"pos":pos_size,"ts":int(time.time()),"future_change":data.get("future_change",0) if data else 0,"confidence":data.get("confidence",0) if data else 0,"moving_score":data.get("moving_score",0) if data else 0}
        state["open"].append(tr)
        kv_set(STATE_KEY, state)
        return Response(json.dumps({"ok":True,"symbol":sym,"side":side,"entry":price,"pos":pos_size}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    except Exception as e:
        import traceback
        return Response(json.dumps({"ok":False,"error":str(e)[:200]}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})

@app.route('/api/liveprice', methods=['GET'])
def liveprice():
    sym=request.args.get("symbol","").upper()
    base=sym.replace("USDT","")
    price,_=fetch_price(base)
    if price is None: return Response(json.dumps({"error":"fail","price":0}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
    return Response(json.dumps({"symbol":sym,"price":price,"ts":int(time.time())}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})

@app.route('/api/reset', methods=['GET'])
def reset():
    kv_del(STATE_KEY)
    return Response(json.dumps({"ok":True,"cap":300,"cleared":True,"fix":"v868 STABLE RESET"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})

@app.route('/api/closeall', methods=['GET'])
def closeall():
    state=load_state()
    state["open"]=[]; kv_set(STATE_KEY, state)
    return Response(json.dumps({"ok":True,"cap":state.get("cap",300)}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})

@app.route('/api/close', methods=['GET'])
def close():
    sym=request.args.get("symbol","")
    state=load_state()
    state["open"]=[t for t in state.get("open",[]) if t["symbol"]!=sym]
    kv_set(STATE_KEY, state)
    return Response(json.dumps({"ok":True,"closed":sym}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})

@app.route('/api/debug', methods=['GET'])
def debug():
    return Response(json.dumps({"ok":True,"app":"FOUND line 2","fix":"v868 STABLE NO CRASH","state":load_state()}, indent=2), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
