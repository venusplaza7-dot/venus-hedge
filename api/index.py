from flask import Flask, request, Response
import os, json, time, urllib.request, math
app = Flask(__name__)
handler = app
def env(k):
 for kk in k:
  v=os.environ.get(kk)
  if v: return v.strip().strip('"').strip("'")
 return ""
KV_URL=(env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"]) or "").rstrip("/")
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V755_MERGED_HISTORY_100_REAL"
POS=100.0; FEE=0.20; FEE_USD=0.20; MAXP=3
SECTORS={"L1_CHAIN":["BTC","ETH","ETC","ARB","SUI","SEI","APT","TIA","ATOM","AVAX","SOL","NEAR","OP","STRK","SAGA","DOGE","CFX","ZEC"],"AI":["TAO","FET","ARKM","RNDR","GRT","LUMIA"],"DEFI":["ENA","PENDLE","AERO","LDO","UNI","AAVE","ETHFI","ONDO","NEAR"],"MEME":["PEPE","BONK","WIF","FLOKI","SHIB","BOME","POPCAT","DOGE","PUMP"],"RWA_GAMING":["IMX","RONIN","GALA","BEAM","PIXEL","SUI","ARB"],"DEPIN_WIFI":["FIL","RNDR","THETA","IOTX","AR","HNT","AKT","GRT","FET","AERO","JASMY"],"OTHER_BEST":[]}
COIN_SEC={}
for sec,coins in SECTORS.items():
 for c in coins:
  if c not in COIN_SEC: COIN_SEC[c]=sec
def get_sec(c): return COIN_SEC.get(c,"OTHER_BEST")
def kv_get(k):
 if not KV_URL or not KV_TOKEN: return None
 try:
  b=json.dumps([["GET",k]]).encode()
  req=urllib.request.Request(f"{KV_URL}/pipeline", data=b, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
  with urllib.request.urlopen(req, timeout=8) as r:
   d=json.loads(r.read().decode()); res=d[0].get("result") if isinstance(d,list) else None
   return json.loads(res) if res and (res.startswith("{") or res.startswith("[")) else None
 except: return None
def kv_set(k,o):
 if not KV_URL or not KV_TOKEN: return False
 try:
  b=json.dumps([["SET",k,json.dumps(o)]]).encode()
  req=urllib.request.Request(f"{KV_URL}/pipeline", data=b, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
  with urllib.request.urlopen(req, timeout=8) as r: return "OK" in r.read().decode()
 except: return False
def get_tickers():
 try:
  req=urllib.request.Request("https://data-api.binance.vision/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req, timeout=8) as r: return json.loads(r.read().decode())
 except: return []
def get_klines(s, lim=50):
 try:
  url=f"https://data-api.binance.vision/api/v3/klines?symbol={s}&interval=5m&limit={lim}"
  req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req, timeout=5) as r: return json.loads(r.read().decode())
 except: return []
def ema(vals,p):
 if len(vals)<p: return None
 k=2/(p+1); em=sum(vals[:p])/p
 for v in vals[p:]: em=v*k+em*(1-k)
 return em
def rsi_calc(closes):
 try:
  if len(closes)<15: return 50
  g=[]; l=[]
  for i in range(1,len(closes)):
   d=closes[i]-closes[i-1]; g.append(max(d,0)); l.append(max(-d,0))
  ag=sum(g[:14])/14; al=sum(l[:14])/14
  for i in range(14,len(g)): ag=(ag*13+g[i])/14; al=(al*13+l[i])/14
  if al==0: return 100
  return 100-100/(1+ag/al)
 except: return 50
def market_regime(mp):
 btc=mp.get("BTCUSDT"); price=float(btc.get("lastPrice","83660")) if btc else 83660
 h1=float(btc.get("priceChangePercent","0")) if btc else 0
 kl=get_klines("BTCUSDT",70)
 if len(kl)<30:
  if h1>1: return {"regime":"TRENDING_BULL","bias":"LONG","btc":price,"btc_price":price,"adx":22,"h1":h1,"reason":f"BULL H1 +{h1:.1f}% BTC ${price:.0f} LONG boost allow SHORT"}
  if h1<-1: return {"regime":"TRENDING_BEAR","bias":"SHORT","btc":price,"btc_price":price,"adx":22,"h1":h1,"reason":f"BEAR H1 {h1:.1f}% BTC ${price:.0f} SHORT boost allow LONG"}
  return {"regime":"RANGING","bias":"BOTH","btc":price,"btc_price":price,"adx":16,"h1":h1,"reason":f"RANGING H1 {h1:+.1f}% BTC ${price:.0f} BOTH"}
 closes=[float(k[4]) for k in kl]; e50=ema(closes,50); e70=ema(closes,70)
 if e50 and e70 and closes[-1]>e50>e70 and h1>0.5: return {"regime":"TRENDING_BULL","bias":"LONG","btc":price,"btc_price":price,"adx":23,"h1":h1,"reason":f"BULL >{e50:.0f}>{e70:.0f} BTC ${price:.0f} H1 {h1:+.1f}% LONG boost allow SHORT"}
 if e50 and e70 and closes[-1]<e50<e70 and h1<-0.5: return {"regime":"TRENDING_BEAR","bias":"SHORT","btc":price,"btc_price":price,"adx":23,"h1":h1,"reason":f"BEAR <{e50:.0f}<{e70:.0f} BTC ${price:.0f} H1 {h1:+.1f}% SHORT boost allow LONG"}
 return {"regime":"RANGING","bias":"BOTH","btc":price,"btc_price":price,"adx":16,"h1":h1,"reason":f"RANGING BTC ${price:.0f} H1 {h1:+.1f}% BOTH LONG SHORT"}
def load_state():
 s=kv_get(STATE_KEY)
 if not s: s={"cap":300,"daily":0,"fees":0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"bl":{},"last":{}}}
 L=s.get("learn",{}); L.setdefault("bl",{}); L.setdefault("last",{})
 today=time.strftime("%Y-%m-%d")
 if L.get("date")!=today: s["daily"]=0; s["fees"]=0; L["date"]=today; L["last"]={}
 now=int(time.time()); L["bl"]={k:v for k,v in L["bl"].items() if v>now}; L["last"]={k:v for k,v in L["last"].items() if v>now}
 s["learn"]=L
 mk=s.get("market",{})
 if mk:
  if "btc" not in mk: mk["btc"]=mk.get("btc_price",83600)
  if "btc_price" not in mk: mk["btc_price"]=mk.get("btc",83600)
  s["market"]=mk
 return s
def eval_sig(base,t,market):
 try:
  vol=float(t.get("quoteVolume","0")); h1=float(t.get("priceChangePercent","0")); price=float(t.get("lastPrice","0"))
  if vol<4000000 or price<0.000001: return []
  if len(base)>7 or not base.isalnum(): return []
  if base in ["USDC","FDUSD","TUSD","BUSD","DAI"]: return []
  kl=get_klines(base+"USDT",30); closes=[float(k[4]) for k in kl] if kl else []
  r=rsi_calc(closes) if closes else 50
  sigs=[]
  if h1>=-3.5 and h1<=4.5 and r<58 and vol>=5000000:
   sc=vol/1e6*(2 if h1>=0.3 else 1)+(60-r)*0.1
   if base in ["BTC","ETH","ETC","SOL","AVAX","ARB","SUI","SEI","STRK","NEAR","ENA","FET","AERO","DOGE","OP"]: sc*=1.4
   if market.get("bias")=="LONG": sc*=1.25
   sigs.append({"symbol":base,"side":"LONG","price":price,"vol":int(vol),"h1":h1,"rsi":r,"score":sc,"tp":0.35,"sl":0.48,"strat":"LONG_CONF","sector":get_sec(base),"reason":f"LONG RSI {r:.0f} H1 {h1:+.1f}% {market.get('regime','')} {market.get('bias','')}"})
  if (h1>=4 and h1<=18) or (h1<=-1 and h1>=-8):
   ok=True
   if closes and len(closes)>=2:
    if h1>=4: ok = r>60 or closes[-1]<closes[-2]
   if ok and r>35:
    sc=vol/1e6*abs(h1)*0.8+(r-40)*0.1
    if base in ["BTC","ETH","ETC","SOL","AVAX","ARB","SUI","SEI","STRK","NEAR","ENA","FET","AERO","DOGE","OP","TIA","AVAX","CFX","CHIP"]: sc*=1.5
    if h1>=5: sc*=1.6
    if market.get("bias")=="SHORT": sc*=1.25
    sigs.append({"symbol":base,"side":"SHORT","price":price,"vol":int(vol),"h1":h1,"rsi":r,"score":sc,"tp":0.38,"sl":0.55,"strat":"SHORT_CONF","sector":get_sec(base),"reason":f"SHORT RSI {r:.0f} H1 {h1:+.1f}% PUMPED TOP {market.get('regime','')} BTC ${market.get('btc',83660):.0f}"})
  return sigs
 except: return []
def do_cron():
 st=load_state(); L=st["learn"]; now=int(time.time())
 tickers=get_tickers(); mp={t["symbol"]:t for t in tickers}
 real=[t for t in tickers if t["symbol"].endswith("USDT") and t["symbol"].replace("USDT","").isalnum() and len(t["symbol"].replace("USDT",""))<=7 and t["symbol"].replace("USDT","") not in ["USDC","FDUSD","BUSD"]][:30]
 market=market_regime(mp)
 open_tr=st.get("open",[]); open_syms=[x["symbol"] for x in open_tr]
 all_sigs=[]
 for t in real:
  b=t["symbol"].replace("USDT","")
  if b in open_syms or b in L["bl"] or b in L["last"]: continue
  all_sigs.extend(eval_sig(b,t,market))
 longs=sorted([s for s in all_sigs if s["side"]=="LONG"], key=lambda x:x["score"], reverse=True)[:8]
 shorts=sorted([s for s in all_sigs if s["side"]=="SHORT"], key=lambda x:x["score"], reverse=True)[:8]
 final=[]
 if shorts: final.append(shorts[0])
 if longs: final.append(longs[0])
 rest=sorted(longs[1:]+shorts[1:], key=lambda x:x["score"], reverse=True)
 for s in rest:
  if len(final)>=5: break
  if s["symbol"] not in [x["symbol"] for x in final]: final.append(s)
 closed=st.get("closed",[]); cap=st.get("cap",300); daily=st.get("daily",0); fees=st.get("fees",0); tot=st.get("total",0); scan=st.get("scan",0)+1
 new_open=[]
 for tr in open_tr:
  try:
   sym=tr["symbol"]+"USDT"; pn=tr["price"]
   if sym in mp: pn=float(mp[sym].get("lastPrice",pn))
   entry=tr["entry"]; side=tr["side"]
   gross=(pn-entry)/entry*100 if side=="LONG" else (entry-pn)/entry*100
   net=gross-FEE; net_usd=POS*net/100; gross_usd=POS*gross/100
   age=now-tr["ts"]; peak=max(tr.get("peak",0),gross)
   tr["price"]=pn; tr["gross"]=gross_usd; tr["net"]=net_usd; tr["pct"]=net; tr["peak"]=peak; tr["age"]=age; tr["pct_gross"]=gross
   should=None
   if gross>=tr.get("tp",0.35): should=f"TP {tr['tp']}% {side} WIN +${net_usd:+.2f}"
   elif gross<=-tr.get("sl",0.5): should=f"SL -{tr['sl']}% {side} CUT"
   elif peak>=0.30 and gross<peak-0.13 and net>=0.05: should=f"TRAIL PEAK {peak:.2f}%->{gross:.2f}% {side}"
   elif age>320 and peak<0.12 and gross<0.14: should=f"FLAT NO PEAK 0.12% {age}s {side}"
   elif age>550 and gross<0.18: should=f"FLAT {gross:.2f}% {age}s {side}"
   elif age>900: should=f"TIME 900s {side}"
   if should:
    cap+=net_usd; daily+=net_usd; fees+=0.20; tot+=1
    closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"gross":gross_usd,"reason":should,"age":age,"pct_gross":gross,"strat":tr.get("strat",""),"sector":get_sec(tr["symbol"])})
    L["last"][tr["symbol"]]=now+400
    if net<-0.45: L["bl"][tr["symbol"]]=now+1800
   else: new_open.append(tr)
  except: new_open.append(tr)
 wins=sum(1 for c in closed if c["net"]>0.08); loss=sum(1 for c in closed if c["net"]<0)
 for s in final:
  if len(new_open)>=MAXP: break
  if s["symbol"] in [x["symbol"] for x in new_open]: continue
  new_open.append({"symbol":s["symbol"],"side":s["side"],"entry":s["price"],"price":s["price"],"pos":POS,"ts":now,"peak":0,"age":0,"h1":s["h1"],"rsi":s["rsi"],"score":s["score"],"strat":s["strat"],"tp":s["tp"],"sl":s["sl"],"sector":s["sector"],"reason":s["reason"]})
 st["open"]=new_open; st["closed"]=closed[:150]; st["cap"]=cap; st["daily"]=daily; st["fees"]=fees; st["wins"]=wins; st["loss"]=loss; st["total"]=tot; st["scan"]=scan; st["market"]=market
 kv_set(STATE_KEY,st)
 l_open=sum(1 for x in new_open if x["side"]=="LONG"); s_open=sum(1 for x in new_open if x["side"]=="SHORT")
 return {"ok":True,"scan":scan,"open":len(new_open),"cap":cap,"market":f"{market['regime']} {market['bias']} BTC ${int(market['btc'])} L:{l_open} S:{s_open}","v":"v803 FULL UI GRAPH RESTORED"}
def render(st):
 op=st.get("open",[]); cl=st.get("closed",[]); cap=st.get("cap",300); daily=st.get("daily",0); fees=st.get("fees",0); wins=st.get("wins",0); loss=st.get("loss",0); tot=st.get("total",0); scan=st.get("scan",0)
 mk=st.get("market",{}); btc=mk.get("btc", mk.get("btc_price",83660)); regime=mk.get("regime","RANGING"); bias=mk.get("bias","BOTH"); h1=mk.get("h1",0); reason=mk.get("reason",""); adx=mk.get("adx",16)
 wr=int(wins/tot*100) if tot else 0; unreal=sum([x.get("net",0) for x in op]); l_open=sum(1 for x in op if x["side"]=="LONG"); s_open=sum(1 for x in op if x["side"]=="SHORT")
 import json as jsjson
 open_json=jsjson.dumps([{"symbol":tr["symbol"],"side":tr.get("side","LONG"),"entry":tr["entry"],"ts":tr.get("ts", int(time.time())),"peak":tr.get("peak",0)} for tr in op])
 html="<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
 html+="body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}"
 html+=".h{background:linear-gradient(90deg,#00ff88,#ff0044,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;position:sticky;top:0;z-index:10}"
 html+=".g{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}"
 html+=".c{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:10px}"
 html+=".b{padding:9px;margin:8px 0;border-radius:7px;font-weight:800;font-size:11px}"
 html+=".by{background:#ffcc00;color:#000} .bb{background:#00d4ff;color:#000} .bd{background:#222;color:#888} .bg{background:#00ff88;color:#000} .bp{background:#ff00ff;color:#fff} .br{background:#ff4444;color:#fff}"
 html+=".it{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:10px;position:relative;overflow:hidden}"
 html+=".live{width:10px;height:10px;background:#0f0;border-radius:50%;display:inline-block;animation:blink 1s infinite} @keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}"
 html+=".spark{width:100%;height:32px;background:#0a0a0a;border:1px solid #222;border-radius:6px;margin:6px 0}"
 html+=".sec{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:900;margin-left:6px}"
 html+=".strat{padding:2px 6px;border-radius:4px;font-size:8px;font-weight:900;margin-left:4px}"
 html+=".side{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:900;margin-left:6px} .side-LONG{background:#00ff88;color:#000} .side-SHORT{background:#ff4444;color:#fff}"
 html+=".s-L1_CHAIN{background:#00d4ff;color:#000} .s-DEPIN_WIFI{background:#ffcc00;color:#000} .s-AI{background:#ff00ff;color:#fff} .s-DEFI{background:#00ff88;color:#000} .s-MEME{background:#ff8800;color:#000} .s-RWA_GAMING{background:#8800ff;color:#fff} .s-OTHER_BEST{background:#555;color:#fff}"
 html+="</style></head><body>"
 bias_col="#00ff88" if bias=="LONG" else "#ff4444" if bias=="SHORT" else "#ffcc00"
 html+=f"<div class='h'><span class='live'></span> VENUS v803 FULL UI GRAPH RESTORED $0.50 NET - SCAN #{scan} - 3 MAX $100 EACH - MARKET {regime} <span style='background:{bias_col};padding:2px 6px;border-radius:4px'>{bias} BIAS</span> BTC ${btc:.0f} ADX {adx:.0f} L:{l_open} S:{s_open} - <span id='clock'>LIVE</span></div>"
 html+=f"<div class='g'><div class='c'><div style='font-size:10px;color:#888'>CAP $300 REAL SHORT</div><div style='font-size:22px;color:#ffcc00;font-weight:900'>${cap:.2f}</div><div style='font-size:10px'>WITH OPEN {cap+unreal:.2f} UNREAL {unreal:+.2f} | L:{l_open} S:{s_open} | {regime}</div></div>"
 html+=f"<div class='c'><div style='font-size:10px;color:#888'>TODAY NET L:{l_open} S:{s_open} x $0.50</div><div style='font-size:22px;color:{'#f44' if daily<0 else '#0f8'};font-weight:900'>${daily:+.2f} NET</div><div style='font-size:10px'>GROSS ${daily:+.2f} - FEES ${fees:.2f} | W:{wins} L:{loss} {wr}% | FULL UI GRAPH</div></div>"
 html+=f"<div class='c'><div style='font-size:10px;color:#888'>MARKET REGIME FULL UI</div><div style='font-size:9px;color:#0f8;font-weight:900'>{regime} {bias} BTC ${btc:.0f} ADX {adx:.0f} H1 {h1:+.1f}% LIVE {scan}</div><div style='font-size:8px;color:#888'>{reason[:75]}</div><div style='font-size:10px'>Next <span id='countdown'>10s</span> TICK <span id='tickcount'>1s</span> - FULL UI</div></div></div>"
 html+="<div id='sharkbox'><div class='b bd'>Scanning FULL UI GRAPH...</div></div>"
 html+="<div id='openbox'></div><div id='closedbox'></div>"
 html+=f"""<script>
const ADMIN_KEY="venus727"; let openTrades={open_json}; let priceHistory={{}}; openTrades.forEach(t=>{{priceHistory[t.symbol]=[]}});
async function fetchPrices(){{try{{const res=await fetch('https://data-api.binance.vision/api/v3/ticker/price'); const all=await res.json(); const map={{}}; all.forEach(t=>{{map[t.symbol]=parseFloat(t.price)}}); let shouldCron=false; openTrades.forEach(tr=>{{const sym=tr.symbol+'USDT'; const now=map[sym]; if(!now) return; const entry=tr.entry; let pct_gross=0; if(tr.side=='LONG'){{pct_gross=(now-entry)/entry*100;}} else {{pct_gross=(entry-now)/entry*100;}} const pct_net=pct_gross-0.20; const net_usd=100*pct_net/100; if(!priceHistory[tr.symbol]) priceHistory[tr.symbol]=[]; priceHistory[tr.symbol].push(pct_gross); if(priceHistory[tr.symbol].length>60) priceHistory[tr.symbol].shift(); if(pct_gross>tr.peak) tr.peak=pct_gross; const el=document.querySelector(`[data-symbol="${{tr.symbol}}"]`); if(el){{const grossEl=el.querySelector('.gross-val'); const netEl=el.querySelector('.net-val'); const priceEl=el.querySelector('.price-now'); const peakEl=el.querySelector('.peak-val'); const tickEl=el.querySelector('.tick-graph'); if(grossEl){{grossEl.textContent=pct_gross.toFixed(3)+'% GROSS ('+tr.side+')'; grossEl.style.color=pct_gross>=0?'#0f8':'#f44';}} if(netEl){{netEl.textContent=pct_net.toFixed(3)+'% NET $'+net_usd.toFixed(3)+' NET '+tr.side; netEl.style.color=pct_net>=0?'#0f8':'#f44';}} if(priceEl) priceEl.textContent='$'+now.toFixed(6); if(peakEl) peakEl.textContent=tr.peak.toFixed(2)+'% PEAK'; if(tickEl && priceHistory[tr.symbol].length>2){{const canvas=tickEl; const ctx=canvas.getContext('2d'); const w=canvas.width; const h=canvas.height; ctx.clearRect(0,0,w,h); const arr=priceHistory[tr.symbol]; const min=Math.min(...arr); const max=Math.max(...arr); const range=(max-min)||0.01; ctx.strokeStyle=tr.side=='LONG'?'#0f8':'#ff4444'; ctx.lineWidth=2; ctx.beginPath(); arr.forEach((v,i)=>{{const x=i/(arr.length-1)*w; const y=h-((v-min)/range)*h; if(i==0) ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const tpY=h-((0.35-min)/range)*h; ctx.strokeStyle='#ffcc00'; ctx.setLineDash([3,3]); ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.setLineDash([]);}} if(pct_gross>=0.33 || pct_gross<=-0.48 || (tr.peak>=0.30 && pct_gross<tr.peak-0.13)){{shouldCron=true;}}}}}}); if(shouldCron){{fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(()=>{{fetch('/?key='+ADMIN_KEY).then(r=>r.text()).then(html=>{{const parser=new DOMParser(); const doc=parser.parseFromString(html,'text/html'); const openEl=doc.getElementById('openbox-inner'); const closedEl=doc.getElementById('closedbox-inner'); if(openEl) document.getElementById('openbox').innerHTML=openEl.innerHTML; if(closedEl) document.getElementById('closedbox').innerHTML=closedEl.innerHTML; const newOpen=[]; doc.querySelectorAll('[data-symbol]').forEach(div=>{{const sym=div.getAttribute('data-symbol'); const side=div.getAttribute('data-side')||'LONG'; const entry=parseFloat(div.getAttribute('data-entry')); const ts=parseInt(div.getAttribute('data-ts')); const peak=parseFloat(div.getAttribute('data-peak')||0); newOpen.push({{symbol:sym,side:side,entry:entry,ts:ts,peak:peak}});}}); openTrades=newOpen; Object.keys(priceHistory).forEach(k=>{{if(!newOpen.find(t=>t.symbol==k)) delete priceHistory[k];}}); newOpen.forEach(t=>{{if(!priceHistory[t.symbol]) priceHistory[t.symbol]=[];}});}});}});}}}}catch(e){{}}}} function tickAge(){{const now=Math.floor(Date.now()/1000); document.querySelectorAll('[data-ts]').forEach(el=>{{const ts=parseInt(el.getAttribute('data-ts')); const age=now-ts; const ageEl=el.querySelector('.age-val'); if(ageEl) ageEl.textContent=age+'s';}});}} setInterval(fetchPrices,1000); setInterval(tickAge,1000); fetchPrices(); tickAge(); let count=10; setInterval(()=>{{count--; const el=document.getElementById('countdown'); if(el) el.textContent=count+'s'; const clk=document.getElementById('clock'); if(clk) clk.textContent=new Date().toLocaleTimeString(); if(count<=0){{count=10; fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(r=>r.json()).then(data=>{{fetch('/?key='+ADMIN_KEY).then(r=>r.text()).then(html=>{{const parser=new DOMParser(); const doc=parser.parseFromString(html,'text/html'); const openEl=doc.getElementById('openbox-inner'); const closedEl=doc.getElementById('closedbox-inner'); const sharkEl=doc.getElementById('sharkbox-inner'); if(openEl) document.getElementById('openbox').innerHTML=openEl.innerHTML; if(closedEl) document.getElementById('closedbox').innerHTML=closedEl.innerHTML; if(sharkEl) document.getElementById('sharkbox').innerHTML=sharkEl.innerHTML; const newOpen=[]; doc.querySelectorAll('[data-symbol]').forEach(div=>{{const sym=div.getAttribute('data-symbol'); const side=div.getAttribute('data-side')||'LONG'; const entry=parseFloat(div.getAttribute('data-entry')); const ts=parseInt(div.getAttribute('data-ts')); const peak=parseFloat(div.getAttribute('data-peak')||0); newOpen.push({{symbol:sym,side:side,entry:entry,ts:ts,peak:peak}});}}); openTrades=newOpen; newOpen.forEach(t=>{{if(!priceHistory[t.symbol]) priceHistory[t.symbol]=[];}});}});}});}}}}},1000);
</script>"""
 html+="<div style='display:none'><div id='sharkbox-inner'>"
 html+=f"<div class='b bg'>FULL UI GRAPH RESTORED - MARKET {regime} BIAS {bias} - BTC ${btc:.0f} ADX {adx:.0f} H1 {h1:+.1f}% - Pumped H1 +4-18% = SHORT, Dip = LONG - {reason[:90]}</div>"
 html+="</div><div id='openbox-inner'>"
 html+=f"<div class='b bb'>OPEN {len(op)}/{MAXP} MAX FULL UI GRAPH $100 EACH - MARKET {regime} {bias} BTC ${btc:.0f} ADX {adx:.0f} L:{l_open} S:{s_open} - SECTORS - <span class='live'></span> LIVE TICK GRAPH 1s</div>"
 if len(op)==0:
  html+=f"<div class='it' style='text-align:center;color:#0f8;border-color:#0f8'>FULL UI GRAPH RESTORED - SCAN #{scan} - MARKET REGIME FULL UI:<br>{reason}<br>BIAS: {bias} - REGIME: {regime} - ADX {adx:.0f} BTC ${btc:.0f} H1 {h1:+.1f}% L:{l_open} S:{s_open}<br>3x$100 DIVERSIFIED FULL UI GRAPH - FORCED L:1 S:2 or L:2 S:1 ALWAYS<br>LONG_CONF: H1 -3.5% to +4.5% DIP BOUNCE<br>SHORT_CONF: H1 +4% to +18% PUMP TOP or -1% to -8% BREAKDOWN SHORT PUMP<br>GRAPH: Live sparkline 1s tick with TP yellow line - SEC TICK LIVE 1s - FULL UI</div>"
 for tr in op:
  col="#0f8" if tr.get("pct",0)>=0 else "#f44"; pct_gross=tr.get("pct_gross",0); pct_net=tr.get("pct",0); net_usd=tr.get("net",0); entry=tr.get("entry",0); ts=tr.get("ts", int(time.time())); peak=tr.get("peak",0); sector=tr.get("sector",get_sec(tr["symbol"])); strat=tr.get("strat",""); side=tr.get("side","LONG"); side_col="#0f8" if side=="LONG" else "#ff4444"
  html+=f"<div class='it' style='border-color:{col}' data-symbol='{tr['symbol']}' data-side='{side}' data-entry='{entry}' data-ts='{ts}' data-peak='{peak}'><b style='color:{col}'>{tr['symbol']} <span class='side side-{side}'>{side}</span> <span class='sec s-{sector}'>{sector}</span> <span class='strat' style='background:{side_col};color:{'#000' if side=='LONG' else '#fff'}'>{strat}</span> AGE <span class='age-val'>{tr.get('age',0)}s</span> PEAK <span class='peak-val'>{peak:.2f}% PEAK</span></b><br>ENTRY ${entry:.6f} ({side}) -> NOW <span class='price-now' style='color:#ffcc00'>${tr.get('price',0):.6f}</span> $100 POS RSI {tr.get('rsi',50):.0f}<br><span style='font-size:13px;font-weight:900' class='gross-val'>{pct_gross:.3f}% GROSS ({side})</span> <span style='font-size:13px;font-weight:900' class='net-val'>{pct_net:.3f}% NET ${net_usd:+.3f} NET {side}</span> <span class='live'></span> TICK GRAPH<br><canvas class='spark tick-graph' width='300' height='32' style='border-color:{side_col}'></canvas><br><span style='font-size:10px;color:#888'>{tr.get('reason','')} | {sector} | TP {tr.get('tp',0.35)}% SL {tr.get('sl',0.55)}% | $0.50 NET GOAL FULL UI GRAPH {regime} {bias} BTC ${btc:.0f}</span></div>"
 html+="</div><div id='closedbox-inner'>"
 html+=f"<div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(cl)} - W:{wins} L:{loss} T:{tot} {wr}% - CAP ${cap:.2f} DAILY NET ${daily:+.2f} (FEES ${fees:.2f}) - FULL UI GRAPH L:{l_open} S:{s_open} {regime} {bias} $0.50x3</div>"
 for cld in cl[:15]:
  net=cld.get("net",0); c="#0f8" if net>=0.08 else "#f44" if net<0 else "#ffcc00"; sec=cld.get("sector",get_sec(cld.get("symbol",""))); strat=cld.get("strat",""); side=cld.get("side","LONG")
  html+=f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{c}'><b>{cld.get('symbol','')} <span class='side side-{side}'>{side}</span> <span class='sec s-{sec}'>{sec}</span> <span class='strat'>{strat}</span></b> ${net:+.2f} NET {cld.get('reason','')} AGE {cld.get('age',0)}s</div>"
 html+="</div></div></div></body></html>"
 return html
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
 key=request.args.get("key","")
 if path.startswith("api/cron"):
  if key!="venus727" and "cron" not in request.args: return Response("Forbidden",403)
  try: r=do_cron(); return Response(json.dumps(r), mimetype="application/json")
  except Exception as e: return Response(json.dumps({"ok":False,"error":str(e)[:300]}), mimetype="application/json")
 try:
  st=load_state(); return Response(render(st), mimetype="text/html")
 except Exception as e:
  import traceback; tb=traceback.format_exc()
  return Response(f"Error {e}<br><pre>{tb[:1500]}</pre>", mimetype="text/html")
