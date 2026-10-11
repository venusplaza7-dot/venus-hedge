from flask import Flask, request, Response
import os, json, time, urllib.request
app = Flask(__name__)

def env(k):
    for kk in k:
        v=os.environ.get(kk)
        if v: return v.strip().strip('"').strip("'")
    return ""
KV_URL=(env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"]) or "").rstrip("/")
if not KV_URL:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "URL" in kk and "upstash" in vv.lower():
            KV_URL=vv.strip().strip('"').strip("'").rstrip("/")
            break
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
if not KV_TOKEN:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "TOKEN" in kk and "upstash" in kk.lower():
            KV_TOKEN=vv.strip().strip('"').strip("'")
            break
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V755_MERGED_HISTORY_100_REAL"
POS=100.0
TP=0.9
SL=0.55
MAXP=3
BAD=set(["ZRO","WLD","FET","RLC","1000SATS","LUNA","LUNC","UP","DOWN"])

def kv_get(k):
    if not KV_URL or not KV_TOKEN: return None
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d=json.loads(r.read().decode())
            res=d[0].get("result") if isinstance(d,list) and d else None
            if not res: return None
            return json.loads(res) if (res.startswith("{") or res.startswith("[")) else res
    except: return None

def kv_set(k,o):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["SET",k,json.dumps(o)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return "OK" in r.read().decode()
    except: return False

def kv_del(k):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return True
    except: return False

def get_tickers():
    try:
        req=urllib.request.Request("https://data-api.binance.vision/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode())
    except: return []

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":""}}
    if "learn" not in s: s["learn"]={"blacklist":{},"pause_until":0,"last_date":""}
    L=s["learn"]
    L.setdefault("blacklist",{})
    L.setdefault("pause_until",0)
    L.setdefault("last_date","")
    today=time.strftime("%Y-%m-%d")
    if L.get("last_date")!=today:
        s["daily"]=0.0
        L["last_date"]=today
        L["pause_until"]=0
    now=int(time.time())
    L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}
    return s

def shark(t):
    try:
        sym=t.get("symbol","")
        if not sym.endswith("USDT"): return None
        base=sym.replace("USDT","")
        if base in BAD: return None
        if not base.isalnum(): return None
        if len(base)<2 or len(base)>10: return None
        price=float(t.get("lastPrice","0"))
        if price<0.0005 or price>5: return None
        h1=float(t.get("priceChangePercent","0"))
        vol=float(t.get("quoteVolume","0"))
        high=float(t.get("highPrice","0"))
        low=float(t.get("lowPrice","0"))
        if high==0 or low==0: return None
        if h1<2.8 or h1>12: return None
        if vol<8000000: return None
        from_low=(price-low)/low*100 if low>0 else 0
        if from_low<2.5 or from_low>11: return None
        if price/high*100<95.5: return None
        score=(vol/1000000)*h1/max(1,from_low)
        if base in ["LUMIA","MANTA","ARB","NIL","AERO","APT","PEPE","WIF","BONK"]: score*=1.5
        return {"symbol":base,"h1":h1,"price":price,"vol":int(vol),"from_low":from_low,"near_high":price/high*100,"score":score}
    except: return None

def do_cron():
    state=load_state()
    L=state["learn"]
    now_ts=int(time.time())
    if L.get("pause_until",0)>now_ts:
        return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"scan":state.get("scan",0)}

    tickers=get_tickers()
    sharks=[]
    for t in tickers:
        s=shark(t)
        if s and s["symbol"] not in L.get("blacklist",{}):
            sharks.append(s)
    sharks=sorted(sharks, key=lambda x: x["score"], reverse=True)[:10]

    open_tr=state.get("open",[])
    closed=state.get("closed",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    wins=state.get("wins",0)
    loss=state.get("loss",0)
    tot=state.get("total",0)
    scan=state.get("scan",0)+1

    final=[]
    for tr in open_tr:
        try:
            sym=tr["symbol"]+"USDT"
            price_now=tr["price"]
            for tk in tickers:
                if tk.get("symbol")==sym:
                    price_now=float(tk.get("lastPrice",price_now))
                    break
            pct=(price_now-tr["entry"])/tr["entry"]*100 if tr["entry"] else 0
            age=now_ts-tr.get("ts",now_ts)
            peak=max(tr.get("peak",0),pct)
            tr["price"]=price_now
            tr["pct"]=pct
            tr["peak"]=peak
            tr["age"]=age
            tr["net"]=POS*pct/100

            should=None
            if pct>=TP: should=f"SHARK TP {TP}% +{pct:.2f}% JUMP"
            elif pct<=-SL: should=f"SHARK SL -{SL}% {pct:.1f}% JUMP"
            elif peak>=0.7 and pct<peak-0.18 and pct>0.35: should=f"TRAIL +{peak:.1f}->{pct:.1f}%"
            elif age>400 and pct>0.35: should=f"TIME 400s {pct:.1f}% NEXT"
            elif age>1200: should=f"TIME 1200s FORCE {pct:.1f}% NEXT"

            if should:
                net=POS*pct/100
                cap+=net
                daily+=net
                if net>0: wins+=1
                else: loss+=1
                tot+=1
                closed.insert(0,{"symbol":tr["symbol"],"net":net,"reason":should,"pct":pct,"age":age})
            else:
                final.append(tr)
        except:
            final.append(tr)

    open_syms=[t["symbol"] for t in final]
    for sh in sharks:
        if len(final)>=MAXP: break
        if sh["symbol"] in open_syms: continue
        if sh["symbol"] in L.get("blacklist",{}): continue
        price=sh["price"]
        qty=POS/price if price>0 else 0
        if qty<5: continue
        tr={"symbol":sh["symbol"],"entry":price,"price":price,"pos":POS,"qty":qty,"ts":now_ts,"peak":0,"pct":0,"net":0,"age":0,"h1":sh["h1"],"from_low":sh["from_low"],"score":sh["score"]}
        final.append(tr)
        open_syms.append(sh["symbol"])

    state["open"]=final
    state["closed"]=closed[:200]
    state["cap"]=cap
    state["daily"]=daily
    state["wins"]=wins
    state["loss"]=loss
    state["total"]=tot
    state["scan"]=scan
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan,"open":len(final),"cap":cap,"daily":daily,"sharks":len(sharks),"total":tot,"wins":wins,"loss":loss}

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
    winrate=int(wins/tot*100) if tot>0 else 0
    unreal=sum([t.get("net",0) for t in open_tr])

    html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
    html += "body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}"
    html += ".h{background:#ffcc00;color:#000;padding:12px;text-align:center;font-weight:900;font-size:14px;position:sticky;top:0;z-index:10}"
    html += ".g{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}"
    html += ".c{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:8px}"
    html += ".b{padding:8px;margin:8px 0;border-radius:6px;font-weight:700;font-size:11px}"
    html += ".by{background:#ffcc00;color:#000} .bb{background:#00d4ff;color:#000} .bd{background:#222;color:#888}"
    html += ".it{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:8px}"
    html += ".live{width:10px;height:10px;background:#0f0;border-radius:50%;display:inline-block;animation:blink 1s infinite} @keyframes blink{0%,100%{opacity:1}50%{opacity:0.2}}"
    html += "</style></head><body>"
    html += f"<div class='h'><span class='live'></span> VENUS v779 LIVE AUTO SHARK - SCAN #{scan} - {MAXP} MAX - TP {TP}% - <span id='clock'>LIVE</span></div>"
    html += "<div class='g'>"
    html += f"<div class='c'><div style='font-size:10px;color:#888'>CAP $300 REAL</div><div style='font-size:24px;color:#ffcc00;font-weight:900' id='cap'>${cap:.2f}</div><div style='font-size:10px'>WITH OPEN <span id='withopen'>{cap+unreal:.2f}</span> <span style='color:#0f0' id='unreal'>{unreal:+.2f}</span></div></div>"
    html += f"<div class='c'><div style='font-size:10px;color:#888'>TODAY LIVE</div><div style='font-size:24px;color:{'#f44' if daily<0 else '#0f8'};font-weight:900' id='daily'>${daily:+.2f}</div><div style='font-size:10px'>W:<span id='wins'>{wins}</span> L:<span id='loss'>{loss}</span> T:<span id='total'>{tot}</span> <span id='winrate'>{winrate}%</span></div></div>"
    html += f"<div class='c'><div style='font-size:10px;color:#888'>AUTO SCAN</div><div style='font-size:14px;color:#0f8;font-weight:900'>LIVE <span id='scan'>{scan}</span></div><div style='font-size:10px'>Next scan <span id='countdown'>10s</span> - Auto TP {TP}%</div></div>"
    html += "</div>"
    html += "<div id='sharkbox'><div class='b bd'>Loading sharks...</div></div>"
    html += "<div id='openbox'></div>"
    html += "<div id='closedbox'></div>"
    html += f"<div style='text-align:center;padding:12px'><a href='/api/cron?key={ADMIN_KEY}&cron=1' style='background:#ffcc00;color:#000;padding:12px 20px;text-decoration:none;font-weight:900;border-radius:8px'>MANUAL CRON</a> "
    html += f"<a href='/api/unpause?key={ADMIN_KEY}' style='background:#222;color:#aaa;padding:10px 14px;text-decoration:none;border-radius:8px;margin-left:6px'>UNPAUSE</a> "
    html += f"<a href='/api/reset?key={ADMIN_KEY}' style='background:#333;color:#888;padding:10px 14px;text-decoration:none;border-radius:8px;margin-left:6px'>RESET $300</a></div>"

    # LIVE JS - auto refreshes data without page reload
    html += """
<script>
let scanNum = """ + str(scan) + """;
function fmt(n){return n.toFixed(2)}

async function loadLive(){
  try{
    // Fetch fresh state via cron endpoint (does scan + returns data)
    const res = await fetch('/api/cron?key=""" + ADMIN_KEY + """&cron=1');
    const data = await res.json();
    if(data.cap!==undefined){
      document.getElementById('cap').textContent = '$'+fmt(data.cap);
      document.getElementById('daily').textContent = (data.daily>=0?'+':'')+'$'+fmt(data.daily);
      document.getElementById('scan').textContent = data.scan;
      scanNum = data.scan;
    }
    // Fetch page HTML for open/closed rendering without full reload
    const pageRes = await fetch('/?key=""" + ADMIN_KEY + """&partial=1');
    const html = await pageRes.text();
    // Parse sharks and open from HTML
    const parser = new DOMParser();
    const doc = parser.parseFromString(html,'text/html');
    const sharkEl = doc.getElementById('sharkbox-inner');
    const openEl = doc.getElementById('openbox-inner');
    const closedEl = doc.getElementById('closedbox-inner');
    if(sharkEl) document.getElementById('sharkbox').innerHTML = sharkEl.innerHTML;
    if(openEl) document.getElementById('openbox').innerHTML = openEl.innerHTML;
    if(closedEl) document.getElementById('closedbox').innerHTML = closedEl.innerHTML;
    
    // Update live counters
    if(data.wins!==undefined){
      document.getElementById('wins').textContent = data.wins||0;
      document.getElementById('loss').textContent = data.loss||0;
      document.getElementById('total').textContent = data.total||0;
    }
  }catch(e){console.log('live err',e)}
}

async function loadPartial(){
  try{
    const pageRes = await fetch(window.location.href);
    const html = await pageRes.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(html,'text/html');
    const sharkEl = doc.getElementById('sharkbox-inner');
    const openEl = doc.getElementById('openbox-inner');
    const closedEl = doc.getElementById('closedbox-inner');
    if(sharkEl) document.getElementById('sharkbox').innerHTML = sharkEl.innerHTML;
    if(openEl) document.getElementById('openbox').innerHTML = openEl.innerHTML;
    if(closedEl) document.getElementById('closedbox').innerHTML = closedEl.innerHTML;
  }catch(e){}
}

// Auto countdown and refresh every 10s
let count=10;
setInterval(()=>{
  count--;
  document.getElementById('countdown').textContent = count+'s';
  document.getElementById('clock').textContent = new Date().toLocaleTimeString();
  if(count<=0){
    count=10;
    loadLive();
  }
},1000);

// Initial load after 2s
setTimeout(loadPartial, 1000);
</script>
"""

    # Hidden partials for JS to parse
    # Sharks
    try:
        tickers=get_tickers()
        sharks=[]
        for t in tickers:
            s=shark(t)
            if s and s["symbol"] not in learn.get("blacklist",{}):
                sharks.append(s)
        sharks=sorted(sharks, key=lambda x: x["score"], reverse=True)[:5]
    except:
        sharks=[]

    html += "<div style='display:none'><div id='sharkbox-inner'>"
    if sharks:
        top=sharks[0]
        html += f"<div class='b by'>SHARK HUNTER {len(sharks)} - TOP {top['symbol']} +{top['h1']:.1f}% SCORE {top['score']:.0f} VOL ${top['vol']} - AUTO SCAN EVERY 10s</div>"
        for s in sharks[:4]:
            html += f"<div class='it' style='border-color:#ffcc00'><b style='color:#ffcc00'>#{sharks.index(s)+1} {s['symbol']} H1 +{s['h1']:.1f}% SCORE {s['score']:.0f}</b><br><span style='color:#0f8'>VOL ${s['vol']} PRICE ${s['price']:.6f} FROM_LOW {s['from_low']:.1f}%</span><br>POS $100 TP {TP}% SL {SL}%</div>"
    else:
        html += "<div class='b bd'>SHARK HUNTER 0 - NO MOVING COINS 2.8-12% - WAITING NEXT WAVE - AUTO SCANNING</div>"
    html += "</div>"

    html += "<div id='openbox-inner'>"
    html += f"<div class='b bb'>OPEN {len(open_tr)}/{MAXP} MAX - LIVE SEC MOVING - TP {TP}% AUTO JUMP - <span class='live'></span> LIVE</div>"
    if not open_tr:
        html += "<div class='it' style='text-align:center;color:#666'>NO OPEN - WAITING SHARK 2.8-12% - AUTO SCAN EVERY 10s</div>"
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        html += f"<div class='it' style='border-color:{col}'><b style='color:{col}'>{tr['symbol']} ${tr.get('pos')} AGE {tr.get('age',0)}s PEAK {tr.get('peak',0):.1f}% SCORE {tr.get('score',0):.0f}</b><br>ENTRY ${tr['entry']:.6f} -> NOW <span style='color:#ffcc00'>${tr['price']:.6f}</span> H1 +{tr.get('h1',0):.1f}%<br><span style='color:{col};font-size:18px;font-weight:900' class='live-pct' data-entry='{tr['entry']}' data-symbol='{tr['symbol']}'>{tr.get('pct',0):+.2f}% ${tr.get('net',0):+.2f} REAL</span> <span class='live'></span> LIVE<br><span style='font-size:10px;color:#888'>TP {TP}% SL {SL}% QTY {tr.get('qty',0):.1f}</span></div>"
    html += "</div>"

    html += "<div id='closedbox-inner'>"
    html += f"<div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(closed)} - W:<span id='cwins'>{wins}</span> L:<span id='closs'>{loss}</span> T:<span id='ctotal'>{tot}</span> CAP ${cap:.2f} DAILY ${daily:+.2f} - AUTO UPDATES</div>"
    for cl in closed[:15]:
        c="#0f8" if cl["net"]>0 else "#f44"
        html += f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{c}'><b>{cl['symbol']}</b> ${cl['net']:+.2f} {cl['reason']} {cl['pct']:+.1f}% AGE {cl['age']}s</div>"
    html += "</div></div>"
    html += "</div>"

    # Live price ticker via Binance WS simulation with polling
    html += """
<script>
// Live price moving every second - fetch Binance ticker for open symbols
async function updateLivePrices(){
  try{
    const res = await fetch('https://data-api.binance.vision/api/v3/ticker/price');
    const all = await res.json();
    const map={};
    all.forEach(t=>{map[t.symbol]=parseFloat(t.price)});
    document.querySelectorAll('.live-pct').forEach(el=>{
      const sym = el.dataset.symbol+'USDT';
      const entry = parseFloat(el.dataset.entry);
      const now = map[sym];
      if(now && entry){
        const pct = (now-entry)/entry*100;
        const net = 100*pct/100;
        el.textContent = (pct>=0?'+':'')+pct.toFixed(2)+'% $'+(net>=0?'+':'')+net.toFixed(2)+' REAL';
        el.style.color = pct>=0?'#0f8':'#f44';
        // update price display
        const priceSpan = el.parentElement.querySelector('span[style*=\"#ffcc00\"]');
        if(priceSpan) priceSpan.textContent = '$'+now.toFixed(6);
      }
    });
  }catch(e){}
}
setInterval(updateLivePrices, 2000);
updateLivePrices();
</script>
"""
    html += "</body></html>"
    return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    key=request.args.get("key","")
    p="/"+path
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY and "cron" not in request.args: return Response("Forbidden", status=403)
        try:
            res=do_cron()
            return Response(json.dumps(res), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)[:300]}), mimetype="application/json", status=200)
    if p.startswith("/api/nuke"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            state=load_state()
            now_ts=int(time.time())
            open_tr=state.get("open",[])
            closed=state.get("closed",[])
            cap=state.get("cap",300.0)
            daily=state.get("daily",0.0)
            wins=state.get("wins",0)
            loss=state.get("loss",0)
            tot=state.get("total",0)
            tickers=get_tickers()
            for tr in open_tr:
                try:
                    price_now=tr["price"]
                    for tk in tickers:
                        if tk.get("symbol")==tr["symbol"]+"USDT":
                            price_now=float(tk.get("lastPrice",price_now))
                            break
                    pct=(price_now-tr["entry"])/tr["entry"]*100 if tr["entry"] else 0
                    net=POS*pct/100
                    cap+=net
                    daily+=net
                    if net>0: wins+=1
                    else: loss+=1
                    tot+=1
                    closed.insert(0,{"symbol":tr["symbol"],"net":net,"reason":f"NUKE {pct:+.2f}%","pct":pct,"age":now_ts-tr.get("ts",now_ts)})
                except: pass
            state["open"]=[]
            state["closed"]=closed[:200]
            state["cap"]=cap
            state["daily"]=daily
            state["wins"]=wins
            state["loss"]=loss
            state["total"]=tot
            kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":True,"nuked":len(open_tr),"cap":cap}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)[:200]}), mimetype="application/json")
    if p.startswith("/api/unpause"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            state=load_state()
            state["learn"]["pause_until"]=0
            state["learn"]["consecutive_losses"]=0
            if state.get("daily",0)<-20:
                state["daily"]=0.0
            kv_set(STATE_KEY, state)
            return Response(json.dumps({"ok":True,"unpaused":True,"daily":state.get("daily",0)}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)[:200]}), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            kv_del(STATE_KEY)
            time.sleep(0.6)
            new={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d")}}
            ok=kv_set(STATE_KEY, new)
            verify=kv_get(STATE_KEY)
            return Response(json.dumps({"ok":ok,"cap":300,"verify":verify.get("cap") if verify else None,"deleted":True}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)[:300]}), mimetype="application/json")
    if p.startswith("/api/force_reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            for kk in [STATE_KEY,"VENUS_V752_RESTORED_SMART_100_REAL","VENUS_V750_LEARNING_AI_100_REAL"]:
                kv_del(kk)
            time.sleep(0.6)
            new={"cap":300.0,"daily":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d")}}
            kv_set(STATE_KEY, new)
            return Response(json.dumps({"ok":True,"cap":300,"force":True}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)[:300]}), mimetype="application/json")
    try:
        st=load_state()
        h=render(st)
        return Response(h, mimetype="text/html")
    except Exception as e:
        return Response(f"<html><body><h1>Error: {str(e)[:500]}</h1><p><a href='/api/reset?key={ADMIN_KEY}'>RESET</a></p></body></html>", mimetype="text/html", status=200)
