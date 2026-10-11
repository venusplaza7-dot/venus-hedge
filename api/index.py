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
TP_GROSS=0.78  # need 0.78% gross to get 0.58% net - higher quality
TP_NET=0.58
SL_GROSS=0.32
MAXP=3

SECTORS = {
    "L1_CHAIN": ["ARB","SUI","SEI","APT","TIA","ATOM","AVAX","SOL","NEAR","OP","STRK","MANTA","NIL","ZK","ZRO","SAGA","APT"],
    "DEPIN_WIFI": ["FIL","RNDR","THETA","IOTX","AR","STORJ","HNT","AKT","GRT","FET","PUMP","W","JASMY","FET","AERO"],
    "AI": ["EIGEN","TAO","FET","WLD","ARKM","AGIX","RNDR","GRT","NMR","OCEAN","AI","VIRTUAL","LUMIA","NIL","RLC"],
    "DEFI": ["ENA","PENDLE","AERO","LUMIA","LDO","UNI","AAVE","CRV","MKR","1INCH","PUMP","ETHFI","ENA","AERO"],
    "MEME": ["PEPE","BONK","WIF","FLOKI","SHIB","DOGE","MEME","BOME","MEW","PUMP","BRETT","POPCAT","PUMP"],
    "RWA_GAMING": ["IMX","RONIN","GALA","AXS","FLOW","CHZ","ENJ","MANA","SAND","BEAM","PIXEL","YGG","RLC"]
}
COIN_SECTOR={}
for sec, coins in SECTORS.items():
    for c in coins:
        if c not in COIN_SECTOR:
            COIN_SECTOR[c]=sec

BAD=set(["1000SATS","LUNA","LUNC","UP","DOWN","1000PEPE","ONDO","XLM","WLD"])  # BAN ONDO XLM WLD repeated losers from your SCAN 312

def get_sector(coin):
    return COIN_SECTOR.get(coin, "OTHER_BEST")

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
    return s

def shark_quality(t, last_coins, used_sectors):
    try:
        sym=t.get("symbol","")
        if not sym.endswith("USDT"): return None
        base=sym.replace("USDT","")
        if base in BAD: return None
        if base in last_coins: return None
        if not base.isalnum(): return None
        if len(base)<2 or len(base)>10: return None
        price=float(t.get("lastPrice","0"))
        if price<0.001 or price>5.0: return None
        h1=float(t.get("priceChangePercent","0"))
        vol=float(t.get("quoteVolume","0"))
        high=float(t.get("highPrice","0"))
        low=float(t.get("lowPrice","0"))
        if high==0 or low==0: return None
        # QUALITY: stronger to avoid flat losers like APT 110s 0.129%
        if h1<4.0 or h1>11.0: return None  # 4.0% min not 1.8%
        if vol<14000000: return None  # 14M min not 5.5M - avoid FET $9M flat
        from_low=(price-low)/low*100 if low>0 else 0
        if from_low<3.5 or from_low>12.0: return None
        near_high=price/high*100
        if near_high<97.0: return None  # must be 97% near high with momentum
        room=(high-price)/price*100
        if room<0.60: return None  # 0.60% room for 0.78% TP
        sector=get_sector(base)
        penalty = 0.35 if sector in used_sectors else 1.0
        score=(vol/1000000)*h1*(1+room)*penalty
        # Boost proven winners from your logs
        if base in ["RLC","ZK","PUMP","ENA","APT","AERO","ARB","FET","SEI","SUI","TIA","RNDR","PENDLE"]: score*=2.8
        if base in ["ONDO","OP","XLM","WLD","PUMP","ENA","FET","ARB","APT"] and vol<20000000:
            # these were flat losers in SCAN 312 unless high vol
            score*=0.4
        return {"symbol":base,"h1":h1,"price":price,"vol":int(vol),"from_low":from_low,"near_high":near_high,"room":room,"score":score,"sector":sector}
    except: return None

def do_cron():
    state=load_state()
    L=state["learn"]
    now_ts=int(time.time())
    if L.get("pause_until",0)>now_ts:
        return {"ok":False,"paused":True,"left":L["pause_until"]-now_ts,"scan":state.get("scan",0)}
    tickers=get_tickers()
    open_tr=state.get("open",[])
    used_sectors=set([get_sector(t["symbol"]) for t in open_tr])
    sharks=[]
    for t in tickers:
        s=shark_quality(t, L.get("last_coins",{}), used_sectors)
        if s and s["symbol"] not in L.get("blacklist",{}):
            sharks.append(s)
    sharks=sorted(sharks, key=lambda x: x["score"], reverse=True)[:15]

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
            tr["price"]=price_now
            tr["pct_gross"]=pct_gross
            tr["pct"]=pct_net
            tr["peak_gross"]=peak_gross
            tr["peak"]=peak_gross - FEE_PCT
            tr["age"]=age
            tr["net"]=net_usd
            tr["gross"]=gross_usd
            should=None
            if pct_gross>=TP_GROSS:
                should=f"TP {TP_GROSS}% GRAPH HIT +${net_usd:+.2f} NET $0.58 GOAL JUMP {get_sector(tr['symbol'])} QUALITY"
            elif pct_gross<=-SL_GROSS:
                should=f"SL -{SL_GROSS}% GRAPH DROP CUT FAST {get_sector(tr['symbol'])}"
            elif peak_gross>=0.55 and pct_gross<peak_gross-0.14 and pct_net>=0.22:
                should=f"GRAPH TRAIL PEAK {peak_gross:.1f}%->{pct_gross:.1f}% DROP -0.14% JUMP"
            elif age>70 and peak_gross<0.08 and pct_gross<0.10:
                should=f"GRAPH NO PEAK 0.08% {age}s FLAT CUT ULTRA FAST - AVOID FEE - QUALITY"
            elif age>120 and pct_gross<0.20 and peak_gross<0.30:
                should=f"GRAPH FLAT {pct_gross:.2f}% PEAK {peak_gross:.2f}% {age}s CUT FAST - QUALITY 14M VOL"
            elif age>300 and pct_net>=0.50:
                should=f"TIME 300s GRAPH {pct_gross:.2f}% NET +${net_usd:+.2f} $0.58 GOAL"
            elif age>600 and pct_net>=0.10:
                should=f"TIME 600s GRAPH {pct_gross:.2f}% NET ${net_usd:+.2f} JUMP"
            elif age>800:
                should=f"TIME 800s FORCE GRAPH {pct_gross:.2f}% NET ${net_usd:+.2f}"
            if should:
                cap+=net_usd
                daily+=net_usd
                daily_gross+=gross_usd
                fees_paid+=FEE_USD
                tot+=1
                closed.insert(0,{"symbol":tr["symbol"],"net":net_usd,"gross":gross_usd,"fee":FEE_USD,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"sector":get_sector(tr["symbol"])})
                L["last_coins"][tr["symbol"]]=now_ts+600
                if pct_net<-0.35:
                    L["blacklist"][tr["symbol"]]=now_ts+2400
                used_sectors.discard(get_sector(tr["symbol"]))
            else:
                final.append(tr)
        except:
            final.append(tr)
    wins = sum(1 for c in closed if c.get("net",0) > 0.30)
    loss = sum(1 for c in closed if c.get("net",0) < 0)
    open_syms=[t["symbol"] for t in final]
    used_sectors=set([get_sector(t["symbol"]) for t in final])
    for sh in sharks:
        if len(final)>=MAXP: break
        if sh["symbol"] in open_syms: continue
        if sh["symbol"] in L.get("blacklist",{}): continue
        if sh["symbol"] in L.get("last_coins",{}): continue
        if sh["sector"] in used_sectors:
            other_options = [s for s in sharks if s["sector"] not in used_sectors and s["symbol"] not in open_syms and s["symbol"] not in L.get("last_coins",{}) and s["symbol"] not in L.get("blacklist",{})]
            if len(other_options)>0:
                continue
        price=sh["price"]
        qty=POS/price if price>0 else 0
        if qty<5: continue
        tr={"symbol":sh["symbol"],"entry":price,"price":price,"pos":POS,"qty":qty,"ts":now_ts,"peak_gross":0,"peak":0,"pct_gross":0,"pct":0,"net":0,"gross":0,"age":0,"h1":sh["h1"],"from_low":sh["from_low"],"score":sh["score"],"room":sh["room"],"sector":sh["sector"]}
        final.append(tr)
        open_syms.append(sh["symbol"])
        used_sectors.add(sh["sector"])
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
    return {"ok":True,"scan":scan,"open":len(final),"cap":cap,"daily":daily,"sharks":len(sharks),"total":tot,"wins":wins,"loss":loss,"top":sharks[0]["symbol"]+" "+sharks[0]["sector"] if sharks else "none","sectors":list(used_sectors),"v":"v790 QUALITY 3COIN"}

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
    try:
        tickers=get_tickers()
        used_sectors=set([get_sector(t["symbol"]) for t in open_tr])
        sharks=[]
        for t in tickers:
            s=shark_quality(t, learn.get("last_coins",{}), used_sectors)
            if s and s["symbol"] not in learn.get("blacklist",{}):
                sharks.append(s)
        sharks=sorted(sharks, key=lambda x: x["score"], reverse=True)[:8]
    except:
        sharks=[]
        used_sectors=set()
    html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
    html += "body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}"
    html += ".h{background:linear-gradient(90deg,#00ff88,#ffcc00,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;position:sticky;top:0;z-index:10}"
    html += ".g{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}"
    html += ".c{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:10px}"
    html += ".b{padding:9px;margin:8px 0;border-radius:7px;font-weight:800;font-size:11px}"
    html += ".by{background:#ffcc00;color:#000} .bb{background:#00d4ff;color:#000} .bd{background:#222;color:#888} .bg{background:#00ff88;color:#000}"
    html += ".it{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:10px;position:relative;overflow:hidden}"
    html += ".live{width:10px;height:10px;background:#0f0;border-radius:50%;display:inline-block;animation:blink 1s infinite} @keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}"
    html += ".spark{width:100%;height:32px;background:#0a0a0a;border:1px solid #222;border-radius:6px;margin:6px 0}"
    html += ".sec{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:900;margin-left:6px}"
    html += ".s-L1_CHAIN{background:#00d4ff;color:#000} .s-DEPIN_WIFI{background:#ffcc00;color:#000} .s-AI{background:#ff00ff;color:#fff} .s-DEFI{background:#00ff88;color:#000} .s-MEME{background:#ff8800;color:#000} .s-RWA_GAMING{background:#8800ff;color:#fff} .s-OTHER_BEST{background:#555;color:#fff}"
    html += "</style></head><body>"
    html += f"<div class='h'><span class='live'></span> VENUS v790 QUALITY 3-COIN $0.58 NET - SCAN #{scan} - 3 MAX $100 EACH QUALITY 14M VOL - BAN ONDO XLM WLD - TP {TP_GROSS}%=${TP_NET:.2f} NET LIVE TICK GRAPH - <span id='clock'>LIVE</span></div>"
    html += "<div class='g'>"
    html += f"<div class='c'><div style='font-size:10px;color:#888'>CAP $300 REAL 3x$100 QUALITY</div><div style='font-size:22px;color:#ffcc00;font-weight:900'>${cap:.2f}</div><div style='font-size:10px'>WITH OPEN {cap+unreal:.2f} UNREAL {unreal:+.2f} | QUALITY</div></div>"
    html += f"<div class='c'><div style='font-size:10px;color:#888'>TODAY NET $0.58x3 QUALITY</div><div style='font-size:22px;color:{'#f44' if daily<0 else '#0f8'};font-weight:900'>${daily:+.2f} NET</div><div style='font-size:10px'>GROSS ${daily_gross:+.2f} - FEES ${fees_paid:.2f} | W:{wins} L:{loss} {winrate}% | BAN FLAT</div></div>"
    html += f"<div class='c'><div style='font-size:10px;color:#888'>3 SECTORS QUALITY 14M</div><div style='font-size:11px;color:#0f8;font-weight:900'>{' '.join(list(used_sectors)) if used_sectors else 'NONE'} LIVE {scan}</div><div style='font-size:10px'>Next <span id='countdown'>10s</span> TICK <span id='tickcount'>1s</span> - QUALITY</div></div>"
    html += "</div>"
    html += "<div id='sharkbox'><div class='b bd'>Scanning quality 3 sectors 14M vol...</div></div>"
    html += "<div id='openbox'></div>"
    html += "<div id='closedbox'></div>"
    import json as jsjson
    open_json = jsjson.dumps([{"symbol":tr["symbol"],"entry":tr["entry"],"ts":tr.get("ts", int(time.time())),"peak_gross":tr.get("peak_gross",0)} for tr in open_tr])
    html += f"""
<script>
const ADMIN_KEY="{ADMIN_KEY}";
const TP_GROSS={TP_GROSS};
const SL_GROSS={SL_GROSS};
const FEE_PCT={FEE_PCT};
let openTrades = {open_json};
let priceHistory = {{}};
openTrades.forEach(t=>{{priceHistory[t.symbol]=[]}});
async function fetchPrices(){{
  try{{
    const res = await fetch('https://data-api.binance.vision/api/v3/ticker/price');
    const all = await res.json();
    const map={{}};
    all.forEach(t=>{{map[t.symbol]=parseFloat(t.price)}});
    let shouldCron = false;
    openTrades.forEach(tr=>{{
      const sym = tr.symbol+'USDT';
      const now = map[sym];
      if(!now) return;
      const entry = tr.entry;
      const pct_gross = (now-entry)/entry*100;
      const pct_net = pct_gross - FEE_PCT;
      const net_usd = 100*pct_net/100;
      if(!priceHistory[tr.symbol]) priceHistory[tr.symbol]=[];
      priceHistory[tr.symbol].push(pct_gross);
      if(priceHistory[tr.symbol].length>60) priceHistory[tr.symbol].shift();
      if(pct_gross > tr.peak_gross) tr.peak_gross = pct_gross;
      const el = document.querySelector(`[data-symbol="${{tr.symbol}}"]`);
      if(el){{
        const grossEl = el.querySelector('.gross-val');
        const netEl = el.querySelector('.net-val');
        const priceEl = el.querySelector('.price-now');
        const peakEl = el.querySelector('.peak-val');
        const tickEl = el.querySelector('.tick-graph');
        if(grossEl){{ grossEl.textContent = pct_gross.toFixed(3)+'% GROSS'; grossEl.style.color = pct_gross>=0?'#0f8':'#f44'; }}
        if(netEl){{ netEl.textContent = pct_net.toFixed(3)+'% NET $'+net_usd.toFixed(3)+' NET'; netEl.style.color = pct_net>=0?'#0f8':'#f44'; }}
        if(priceEl) priceEl.textContent = '$'+now.toFixed(6);
        if(peakEl) peakEl.textContent = tr.peak_gross.toFixed(2)+'% PEAK';
        if(tickEl && priceHistory[tr.symbol].length>2){{
          const canvas = tickEl;
          const ctx = canvas.getContext('2d');
          const w = canvas.width; const h = canvas.height;
          ctx.clearRect(0,0,w,h);
          const arr = priceHistory[tr.symbol];
          const min = Math.min(...arr); const max = Math.max(...arr);
          const range = (max-min) || 0.01;
          ctx.strokeStyle = pct_net>=0?'#0f8':'#f44';
          ctx.lineWidth=2;
          ctx.beginPath();
          arr.forEach((v,i)=>{{
            const x = i/(arr.length-1)*w;
            const y = h - ((v-min)/range)*h;
            if(i==0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
          }});
          ctx.stroke();
          const tpY = h - ((TP_GROSS-min)/range)*h;
          ctx.strokeStyle='#ffcc00'; ctx.setLineDash([3,3]); ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.setLineDash([]);
        }}
        if(pct_gross >= TP_GROSS || pct_gross <= -SL_GROSS || (tr.peak_gross >= 0.55 && pct_gross < tr.peak_gross - 0.14)){{
          shouldCron = true;
        }}
      }}
    }});
    if(shouldCron){{
      fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(()=>{{
        fetch('/?key='+ADMIN_KEY).then(r=>r.text()).then(html=>{{
          const parser=new DOMParser(); const doc=parser.parseFromString(html,'text/html');
          const openEl=doc.getElementById('openbox-inner'); const closedEl=doc.getElementById('closedbox-inner'); const sharkEl=doc.getElementById('sharkbox-inner');
          if(openEl) document.getElementById('openbox').innerHTML = openEl.innerHTML;
          if(closedEl) document.getElementById('closedbox').innerHTML = closedEl.innerHTML;
          if(sharkEl) document.getElementById('sharkbox').innerHTML = sharkEl.innerHTML;
          const newOpen = [];
          doc.querySelectorAll('[data-symbol]').forEach(div=>{{
            const sym = div.getAttribute('data-symbol');
            const entry = parseFloat(div.getAttribute('data-entry'));
            const ts = parseInt(div.getAttribute('data-ts'));
            const peak = parseFloat(div.getAttribute('data-peak')||0);
            newOpen.push({{symbol:sym, entry:entry, ts:ts, peak_gross:peak}});
          }});
          openTrades = newOpen;
          Object.keys(priceHistory).forEach(k=>{{ if(!newOpen.find(t=>t.symbol==k)) delete priceHistory[k]; }});
          newOpen.forEach(t=>{{ if(!priceHistory[t.symbol]) priceHistory[t.symbol]=[]; }});
        }});
      }});
    }}
  }}catch(e){{}}
}}
function tickAge(){{
  const now = Math.floor(Date.now()/1000);
  document.querySelectorAll('[data-ts]').forEach(el=>{{
    const ts = parseInt(el.getAttribute('data-ts'));
    const age = now - ts;
    const ageEl = el.querySelector('.age-val');
    if(ageEl) ageEl.textContent = age+'s';
  }});
}}
setInterval(fetchPrices, 1000);
setInterval(tickAge, 1000);
fetchPrices();
tickAge();
let count=10;
setInterval(()=>{{
  count--;
  const el=document.getElementById('countdown');
  if(el) el.textContent = count+'s';
  const clk=document.getElementById('clock');
  if(clk) clk.textContent = new Date().toLocaleTimeString();
  if(count<=0){{ 
    count=10; 
    fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(r=>r.json()).then(data=>{{
      fetch('/?key='+ADMIN_KEY).then(r=>r.text()).then(html=>{{
        const parser=new DOMParser(); const doc=parser.parseFromString(html,'text/html');
        const openEl=doc.getElementById('openbox-inner'); const closedEl=doc.getElementById('closedbox-inner'); const sharkEl=doc.getElementById('sharkbox-inner');
        if(openEl) document.getElementById('openbox').innerHTML = openEl.innerHTML;
        if(closedEl) document.getElementById('closedbox').innerHTML = closedEl.innerHTML;
        if(sharkEl) document.getElementById('sharkbox').innerHTML = sharkEl.innerHTML;
        const newOpen = [];
        doc.querySelectorAll('[data-symbol]').forEach(div=>{{
          const sym = div.getAttribute('data-symbol');
          const entry = parseFloat(div.getAttribute('data-entry'));
          const ts = parseInt(div.getAttribute('data-ts'));
          const peak = parseFloat(div.getAttribute('data-peak')||0);
          newOpen.push({{symbol:sym, entry:entry, ts:ts, peak_gross:peak}});
        }});
        openTrades = newOpen;
        newOpen.forEach(t=>{{ if(!priceHistory[t.symbol]) priceHistory[t.symbol]=[]; }});
      }});
    }});
  }}
}},1000);
</script>
"""
    html += "<div style='display:none'><div id='sharkbox-inner'>"
    if sharks:
        top=sharks[0]
        html += f"<div class='b bg'>QUALITY 3-COIN 14M VOL - TOP {top['symbol']} {top['sector']} +{top['h1']:.1f}% SCORE {top['score']:.0f} VOL ${top['vol']} ROOM {top['room']:.1f}% - QUALITY FILTER NO FLAT - BAN ONDO XLM WLD</div>"
        for s in sharks[:8]:
            html += f"<div class='it' style='border-color:#00ff88'><b style='color:#00ff88'>#{sharks.index(s)+1} {s['symbol']} <span class='sec s-{s['sector']}'>{s['sector']}</span> H1 +{s['h1']:.1f}% ROOM {s['room']:.1f}% SCORE {s['score']:.0f}</b><br><span style='color:#0f8'>VOL ${s['vol']} PRICE ${s['price']:.6f} - TP {TP_GROSS}% = ${TP_NET:.2f} NET - QUALITY 14M - NO FLAT</span></div>"
    else:
        html += f"<div class='b by'>QUALITY SHARK 0 - NO 4.0%+ WITH 14M VOL 97% HIGH - USED {','.join(list(used_sectors))} - WAITING QUALITY FOR $0.58 NET - BAN FLAT ONDO XLM - LIVE TICK</div>"
    html += "</div>"
    html += "<div id='openbox-inner'>"
    html += f"<div class='b bb'>OPEN {len(open_tr)}/{MAXP} MAX QUALITY 3-COIN $100 EACH - NEED {TP_GROSS}% GROSS = {TP_NET:.2f}% NET $0.58x3 = $1.74 NET - SECTORS {','.join(list(used_sectors)) if used_sectors else 'NONE'} - QUALITY 14M - <span class='live'></span> LIVE TICK GRAPH 1s</div>"
    if len(open_tr)==0:
        html += f"<div class='it' style='text-align:center;color:#0f8;border-color:#0f8'>QUALITY WAITING 3 COINS $100 EACH - 14M VOL MIN - 97% NEAR HIGH - 0.60% ROOM - BAN ONDO XLM WLD FLAT LOSERS - SEC TICK LIVE 1s - WILL FILL ONLY QUALITY FOR $0.58 NET</div>"
    for tr in open_tr:
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        pct_gross=tr.get("pct_gross",0)
        pct_net=tr.get("pct",0)
        net_usd=tr.get("net",0)
        entry=tr.get("entry",0)
        ts=tr.get("ts", int(time.time()))
        peak=tr.get("peak_gross",0)
        sector=tr.get("sector", get_sector(tr["symbol"]))
        html += f"<div class='it' style='border-color:{col}' data-symbol='{tr['symbol']}' data-entry='{entry}' data-ts='{ts}' data-peak='{peak}'><b style='color:{col}'>{tr['symbol']} <span class='sec s-{sector}'>{sector}</span> AGE <span class='age-val'>{tr.get('age',0)}s</span> PEAK <span class='peak-val'>{peak:.2f}% PEAK</span> ROOM {tr.get('room',0):.1f}%</b><br>ENTRY ${entry:.6f} -> NOW <span class='price-now' style='color:#ffcc00'>${tr.get('price',0):.6f}</span> $100 POS<br><span style='font-size:13px;font-weight:900' class='gross-val'>{pct_gross:.3f}% GROSS</span> <span style='font-size:13px;font-weight:900' class='net-val'>{pct_net:.3f}% NET ${net_usd:+.3f} NET REAL $100</span> <span class='live'></span> TICK GRAPH<br><canvas class='spark tick-graph' width='300' height='32'></canvas><br><span style='font-size:10px;color:#888'>SECTOR {sector} | QUALITY 14M VOL | BAN ONDO XLM WLD | TP {TP_GROSS}% | TRAIL -0.14% | SL {SL_GROSS}% | AGE 1s | PRICE 1s | $0.58 NET GOAL</span></div>"
    html += "</div>"
    html += "<div id='closedbox-inner'>"
    html += f"<div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} T:{tot} {winrate}% - CAP ${cap:.2f} DAILY NET ${daily:+.2f} (GROSS ${daily_gross:+.2f} - FEES ${fees_paid:.2f}) - QUALITY 14M VOL BAN FLAT $0.58x3 = $1.74 TARGET</div>"
    for cl in closed[:15]:
        net=cl.get("net",0)
        gross=cl.get("gross",0)
        fee=cl.get("fee",FEE_USD)
        pct_gross=cl.get("pct_gross",0)
        pct_net=cl.get("pct_net",0)
        c="#0f8" if net>=0.40 else "#f44" if net<0 else "#ffcc00"
        sec=cl.get("sector", get_sector(cl.get("symbol","")))
        html += f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')} <span class='sec s-{sec}'>{sec}</span></b> ${net:+.2f} NET (${gross:+.2f} GROSS - ${fee:.2f} FEE) {cl.get('reason','')} {pct_gross:+.2f}% GROSS {pct_net:+.2f}% NET AGE {cl.get('age',0)}s</div>"
    html += "</div></div></div></body></html>"
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
            return Response(json.dumps({"ok":ok,"cap":300}), mimetype="application/json")
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
