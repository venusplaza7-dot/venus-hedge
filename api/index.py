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
FEE_PCT=0.20
FEE_USD=0.20
TP_GROSS=0.75
TP_NET=0.55
SL_GROSS=0.50
MAXP=2
BAD=set(["ZRO","WLD","FET","RLC","1000SATS","LUNA","LUNC","UP","DOWN","OP","ATOM"])

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
        s={"cap":300.0,"daily":0.0,"daily_gross":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":"","last_coins":{}}}
    if "learn" not in s: s["learn"]={"blacklist":{},"pause_until":0,"last_date":"","last_coins":{}}
    L=s["learn"]
    L.setdefault("blacklist",{})
    L.setdefault("pause_until",0)
    L.setdefault("last_date","")
    L.setdefault("last_coins",{})
    today=time.strftime("%Y-%m-%d")
    if L.get("last_date")!=today:
        s["daily"]=0.0
        s["daily_gross"]=0.0
        s["fees_paid"]=0.0
        L["last_date"]=today
        L["pause_until"]=0
        L["last_coins"]={}
    now=int(time.time())
    L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}
    L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    # MIGRATE old trades to have gross/fee fields to prevent 'gross' error
    for tr in s.get("open",[]):
        if "gross" not in tr:
            pct=tr.get("pct",0)
            # old pct was net, estimate gross = net + fee
            tr["gross"]=tr.get("pos",POS)*(pct+FEE_PCT)/100
            tr["pct_gross"]=pct+FEE_PCT
            tr["peak_gross"]=tr.get("peak",0)+FEE_PCT
            tr["room"]=0.8
    for cl in s.get("closed",[]):
        if "gross" not in cl:
            net=cl.get("net",0)
            cl["gross"]=net+FEE_USD if net>0 else net-FEE_USD
            cl["fee"]=FEE_USD
            cl["pct_gross"]=cl.get("pct",0)+FEE_PCT
            cl["pct_net"]=cl.get("pct",0)
    return s

def shark_fee_aware(t, last_coins):
    try:
        sym=t.get("symbol","")
        if not sym.endswith("USDT"): return None
        base=sym.replace("USDT","")
        if base in BAD: return None
        if base in last_coins: return None
        if not base.isalnum(): return None
        if len(base)<2 or len(base)>10: return None
        price=float(t.get("lastPrice","0"))
        if price<0.005 or price>1.5: return None
        h1=float(t.get("priceChangePercent","0"))
        vol=float(t.get("quoteVolume","0"))
        high=float(t.get("highPrice","0"))
        low=float(t.get("lowPrice","0"))
        if high==0 or low==0: return None
        if h1<2.8 or h1>6.0: return None
        if vol<13000000: return None
        from_low=(price-low)/low*100 if low>0 else 0
        if from_low<2.8 or from_low>6.0: return None
        near_high=price/high*100
        if near_high<97.0 or near_high>99.5: return None
        room_to_high=(high-price)/price*100
        if room_to_high<0.6: return None
        score=(vol/1000000)*h1/max(1,from_low)* (room_to_high)
        if base in ["LUMIA","MANTA","ARB","NIL","AERO","EIGEN"]: score*=2.2
        return {"symbol":base,"h1":h1,"price":price,"vol":int(vol),"from_low":from_low,"near_high":near_high,"room":room_to_high,"score":score}
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
        s=shark_fee_aware(t, L.get("last_coins",{}))
        if s and s["symbol"] not in L.get("blacklist",{}):
            sharks.append(s)
    sharks=sorted(sharks, key=lambda x: x["score"], reverse=True)[:10]

    open_tr=state.get("open",[])
    closed=state.get("closed",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    daily_gross=state.get("daily_gross",0.0)
    fees_paid=state.get("fees_paid",0.0)
    wins=state.get("wins",0)
    loss=state.get("loss",0)
    tot=state.get("total",0)
    scan=state.get("scan",0)+1

    final=[]
    for tr in open_tr:
        try:
            sym=tr["symbol"]+"USDT"
            price_now=tr.get("price", tr.get("entry",0))
            for tk in tickers:
                if tk.get("symbol")==sym:
                    price_now=float(tk.get("lastPrice",price_now))
                    break
            entry=tr.get("entry", price_now)
            pct_gross=(price_now-entry)/entry*100 if entry else 0
            pct_net=pct_gross - FEE_PCT
            net_usd=POS*pct_net/100
            gross_usd=POS*pct_gross/100
            age=now_ts-tr.get("ts",now_ts)
            peak_gross=max(tr.get("peak_gross",0), pct_gross)
            peak_net=peak_gross - FEE_PCT
            tr["price"]=price_now
            tr["pct_gross"]=pct_gross
            tr["pct"]=pct_net
            tr["peak_gross"]=peak_gross
            tr["peak"]=peak_net
            tr["age"]=age
            tr["net"]=net_usd
            tr["gross"]=gross_usd
            tr["room"]=tr.get("room",0.8)

            should=None
            if pct_gross>=TP_GROSS:
                should=f"TP {TP_GROSS}% GROSS {pct_gross:.2f}% NET +{pct_net:.2f}% +${net_usd:+.2f} NET JUMP"
            elif pct_gross<=-SL_GROSS:
                should=f"SL -{SL_GROSS}% GROSS {pct_gross:.1f}% NET {pct_net:.1f}% ${net_usd:+.2f} JUMP"
            elif peak_gross>=0.9 and pct_gross<peak_gross-0.18 and pct_net>0.35:
                should=f"TRAIL +{peak_gross:.1f}%->{pct_gross:.1f}% GROSS NET +{pct_net:.1f}% +${net_usd:+.2f} JUMP"
            elif age>300 and pct_net>=0.35:
                should=f"TIME 300s {pct_gross:.2f}% GROSS {pct_net:.2f}% NET +${net_usd:+.2f} JUMP"
            elif age>600 and pct_net>=0.15:
                should=f"TIME 600s {pct_gross:.2f}% GROSS {pct_net:.2f}% NET +${net_usd:+.2f} JUMP"
            elif age>900:
                should=f"TIME 900s FORCE {pct_gross:.2f}% GROSS {pct_net:.2f}% NET ${net_usd:+.2f} JUMP"
            elif age>200 and pct_gross<-0.30:
                should=f"FLAT CUT {pct_gross:.1f}% GROSS {pct_net:.1f}% NET {age}s"

            if should:
                cap+=net_usd
                daily+=net_usd
                daily_gross+=gross_usd
                fees_paid+=FEE_USD
                if net_usd>0: wins+=1
                else: loss+=1
                tot+=1
                closed.insert(0,{"symbol":tr["symbol"],"net":net_usd,"gross":gross_usd,"fee":FEE_USD,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age})
                L["last_coins"][tr["symbol"]]=now_ts+600
                if pct_net<-0.6:
                    L["blacklist"][tr["symbol"]]=now_ts+1800
            else:
                final.append(tr)
        except Exception as e:
            # keep trade on error to avoid losing it
            final.append(tr)

    open_syms=[t["symbol"] for t in final]
    for sh in sharks:
        if len(final)>=MAXP: break
        if sh["symbol"] in open_syms: continue
        if sh["symbol"] in L.get("blacklist",{}): continue
        if sh["symbol"] in L.get("last_coins",{}): continue
        price=sh["price"]
        qty=POS/price if price>0 else 0
        if qty<15: continue
        tr={"symbol":sh["symbol"],"entry":price,"price":price,"pos":POS,"qty":qty,"ts":now_ts,"peak_gross":0,"peak":0,"pct_gross":0,"pct":0,"net":0,"gross":0,"age":0,"h1":sh["h1"],"from_low":sh["from_low"],"score":sh["score"],"room":sh["room"]}
        final.append(tr)
        open_syms.append(sh["symbol"])

    state["open"]=final
    state["closed"]=closed[:200]
    state["cap"]=cap
    state["daily"]=daily
    state["daily_gross"]=daily_gross
    state["fees_paid"]=fees_paid
    state["wins"]=wins
    state["loss"]=loss
    state["total"]=tot
    state["scan"]=scan
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan,"open":len(final),"cap":cap,"daily":daily,"daily_gross":daily_gross,"fees":fees_paid,"sharks":len(sharks),"total":tot,"wins":wins,"loss":loss,"v":"v782 FIXED gross"}

def render(state):
    open_tr=state.get("open",[])
    closed=state.get("closed",[])
    cap=state.get("cap",300.0)
    daily=state.get("daily",0.0)
    daily_gross=state.get("daily_gross",0.0)
    fees_paid=state.get("fees_paid",0.0)
    wins=state.get("wins",0)
    loss=state.get("loss",0)
    tot=state.get("total",0)
    scan=state.get("scan",0)
    learn=state.get("learn",{})
    winrate=int(wins/tot*100) if tot>0 else 0
    unreal=sum([t.get("net",0) for t in open_tr])
    unreal_gross=sum([t.get("gross",0) for t in open_tr])

    try:
        tickers=get_tickers()
        sharks=[]
        for t in tickers:
            s=shark_fee_aware(t, learn.get("last_coins",{}))
            if s and s["symbol"] not in learn.get("blacklist",{}):
                sharks.append(s)
        sharks=sorted(sharks, key=lambda x: x["score"], reverse=True)[:5]
    except:
        sharks=[]

    html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
    html += "body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}"
    html += ".h{background:linear-gradient(90deg,#00ff88,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:14px;position:sticky;top:0;z-index:10}"
    html += ".g{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}"
    html += ".c{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:10px}"
    html += ".b{padding:9px;margin:8px 0;border-radius:7px;font-weight:800;font-size:11px}"
    html += ".by{background:#ffcc00;color:#000} .bb{background:#00d4ff;color:#000} .bd{background:#222;color:#888} .bg{background:#00ff88;color:#000}"
    html += ".it{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:10px}"
    html += ".live{width:10px;height:10px;background:#0f0;border-radius:50%;display:inline-block;animation:blink 1s infinite} @keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}"
    html += "</style></head><body>"
    html += f"<div class='h'><span class='live'></span> VENUS v782 FIXED $0.50 NET - SCAN #{scan} - {MAXP} MAX - TP {TP_GROSS}% GROSS = $0.50 NET AFTER FEE - <span id='clock'>LIVE</span></div>"
    html += "<div class='g'>"
    html += f"<div class='c'><div style='font-size:10px;color:#888'>CAP $300 REAL NET</div><div style='font-size:24px;color:#ffcc00;font-weight:900'>${cap:.2f}</div><div style='font-size:10px'>WITH OPEN {cap+unreal:.2f} GROSS {unreal_gross:+.2f} FEES</div></div>"
    html += f"<div class='c'><div style='font-size:10px;color:#888'>TODAY NET AFTER FEE</div><div style='font-size:24px;color:{'#f44' if daily<0 else '#0f8'};font-weight:900'>${daily:+.2f} NET</div><div style='font-size:10px'>GROSS ${daily_gross:+.2f} - FEES ${fees_paid:.2f} | W:{wins} L:{loss} {winrate}%</div></div>"
    html += f"<div class='c'><div style='font-size:10px;color:#888'>GOAL $0.50 NET/TRADE</div><div style='font-size:14px;color:#0f8;font-weight:900'>LIVE {scan} JUMP</div><div style='font-size:10px'>Next <span id='countdown'>10s</span> - TP {TP_GROSS}% = {TP_NET:.2f}% NET</div></div>"
    html += "</div>"

    html += "<div id='sharkbox'><div class='b bd'>Scanning...</div></div>"
    html += "<div id='openbox'></div>"
    html += "<div id='closedbox'></div>"
    html += f"<div style='text-align:center;padding:12px'><a href='/api/cron?key={ADMIN_KEY}&cron=1' style='background:#00ff88;color:#000;padding:12px 20px;text-decoration:none;font-weight:900;border-radius:8px'>CRON v782 FIXED $0.50 NET</a> "
    html += f"<a href='/api/reset?key={ADMIN_KEY}' style='background:#333;color:#888;padding:10px 14px;text-decoration:none;border-radius:8px;margin-left:6px'>RESET $300</a></div>"

    html += """
<script>
function fmt(n){return n.toFixed(2)}
async function loadLive(){
  try{
    const res = await fetch('/api/cron?key=""" + ADMIN_KEY + """&cron=1');
    await res.json();
    const pageRes = await fetch('/?key=""" + ADMIN_KEY + """');
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
let count=10;
setInterval(()=>{
  count--;
  const el=document.getElementById('countdown');
  if(el) el.textContent = count+'s';
  const clk=document.getElementById('clock');
  if(clk) clk.textContent = new Date().toLocaleTimeString();
  if(count<=0){ count=10; loadLive(); }
},1000);
setTimeout(()=>{ fetch(window.location.href).then(r=>r.text()).then(html=>{
  const parser=new DOMParser(); const doc=parser.parseFromString(html,'text/html');
  const sharkEl=doc.getElementById('sharkbox-inner'); const openEl=doc.getElementById('openbox-inner'); const closedEl=doc.getElementById('closedbox-inner');
  if(sharkEl) document.getElementById('sharkbox').innerHTML=sharkEl.innerHTML;
  if(openEl) document.getElementById('openbox').innerHTML=openEl.innerHTML;
  if(closedEl) document.getElementById('closedbox').innerHTML=closedEl.innerHTML;
});},1200);
</script>
<script>
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
        const pct_gross = (now-entry)/entry*100;
        const pct_net = pct_gross - """ + str(FEE_PCT) + """;
        const net_usd = 100*pct_net/100;
        el.textContent = pct_gross.toFixed(2)+'% GROSS '+pct_net.toFixed(2)+'% NET $'+net_usd.toFixed(2)+' NET REAL';
        el.style.color = pct_net>=0?'#0f8':'#f44';
      }
    });
  }catch(e){}
}
setInterval(updateLivePrices, 2000);
updateLivePrices();
</script>
"""

    html += "<div style='display:none'><div id='sharkbox-inner'>"
    if sharks:
        top=sharks[0]
        html += f"<div class='b bg'>FEE AWARE SHARK FOR $0.50 NET - TOP {top['symbol']} +{top['h1']:.1f}% SCORE {top['score']:.0f} VOL ${top['vol']} ROOM {top['room']:.1f}% - NEED {TP_GROSS}% GROSS = $0.50 NET - JUMP COIN</div>"
        for s in sharks[:4]:
            net_est=(TP_GROSS-FEE_PCT)*POS/100
            html += f"<div class='it' style='border-color:#00ff88'><b style='color:#00ff88'>#{sharks.index(s)+1} {s['symbol']} H1 +{s['h1']:.1f}% SCORE {s['score']:.0f} ROOM {s['room']:.1f}%</b><br><span style='color:#0f8'>VOL ${s['vol']} PRICE ${s['price']:.6f} FROM_LOW {s['from_low']:.1f}% - TP {TP_GROSS}% = ${net_est:.2f} NET AFTER ${FEE_USD:.2f} FEE</span></div>"
    else:
        html += "<div class='b bd'>SHARK EARLY 0 - NO 2.8-6% EARLY WITH ROOM FOR 0.75% GROSS - WAITING FOR $0.50 NET - JUMP COIN</div>"
    html += "</div>"

    html += "<div id='openbox-inner'>"
    html += f"<div class='b bb'>OPEN {len(open_tr)}/{MAXP} MAX FEE AWARE - NEED {TP_GROSS}% GROSS = {TP_NET:.2f}% NET $0.50 AFTER ${FEE_USD:.2f} FEE - JUMP - <span class='live'></span> LIVE</div>"
    if not open_tr:
        html += f"<div class='it' style='text-align:center;color:#666'>NO OPEN - WAITING EARLY SHARK FOR $0.50 NET AFTER FEE - JUMP DIFFERENT COIN - AUTO SCAN</div>"
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        pct_gross=tr.get("pct_gross", tr.get("pct",0)+FEE_PCT)
        pct_net=tr.get("pct",0)
        net_usd=tr.get("net",0)
        html += f"<div class='it' style='border-color:{col}'><b style='color:{col}'>{tr['symbol']} ${tr.get('pos')} AGE {tr.get('age',0)}s PEAK {tr.get('peak_gross',0):.1f}% GROSS SCORE {tr.get('score',0):.0f}</b><br>ENTRY ${tr.get('entry',0):.6f} -> NOW ${tr.get('price',0):.6f} H1 +{tr.get('h1',0):.1f}%<br><span style='color:{col};font-size:15px;font-weight:900' class='live-pct' data-entry='{tr.get('entry',0)}' data-symbol='{tr['symbol']}'>{pct_gross:.2f}% GROSS {pct_net:.2f}% NET ${net_usd:+.2f} NET REAL</span> <span class='live'></span> LIVE<br><span style='font-size:10px;color:#888'>NEED {TP_GROSS}% GROSS = {TP_NET:.2f}% NET $0.50 | SL {SL_GROSS}% | QTY {tr.get('qty',0):.1f}</span></div>"
    html += "</div>"

    html += "<div id='closedbox-inner'>"
    html += f"<div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} T:{tot} {winrate}% - CAP ${cap:.2f} DAILY NET ${daily:+.2f} (GROSS ${daily_gross:+.2f} - FEES ${fees_paid:.2f}) - GOAL $0.50 NET/TRADE</div>"
    for cl in closed[:15]:
        net=cl.get("net",0)
        gross=cl.get("gross", net+FEE_USD)
        fee=cl.get("fee", FEE_USD)
        pct_gross=cl.get("pct_gross", cl.get("pct",0)+FEE_PCT)
        pct_net=cl.get("pct_net", cl.get("pct",0))
        c="#0f8" if net>0 else "#f44"
        html += f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')}</b> ${net:+.2f} NET (${gross:+.2f} GROSS - ${fee:.2f} FEE) {cl.get('reason','')} {pct_gross:+.2f}% GROSS {pct_net:+.2f}% NET AGE {cl.get('age',0)}s</div>"
    html += "</div></div></div>"
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
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            kv_del(STATE_KEY)
            time.sleep(0.6)
            new={"cap":300.0,"daily":0.0,"daily_gross":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}}
            ok=kv_set(STATE_KEY, new)
            verify=kv_get(STATE_KEY)
            return Response(json.dumps({"ok":ok,"cap":300,"verify":verify.get("cap") if verify else None}), mimetype="application/json")
        except Exception as e:
            return Response(json.dumps({"ok":False,"error":str(e)[:300]}), mimetype="application/json")
    try:
        st=load_state()
        h=render(st)
        return Response(h, mimetype="text/html")
    except Exception as e:
        import traceback
        tb=traceback.format_exc()[:800]
        return Response(f"<html><body><h1>Error: {str(e)[:500]}</h1><pre>{tb}</pre><p><a href='/api/reset?key={ADMIN_KEY}'>RESET</a></p></body></html>", mimetype="text/html", status=200)
