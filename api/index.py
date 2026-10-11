from flask import Flask, request, Response
import os, json, time, urllib.request
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
POS=100.0; FEE=0.20; MAXP=3
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
def get_klines(s, lim=40):
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
 btc=mp.get("BTCUSDT"); price=float(btc.get("lastPrice","83600")) if btc else 83600
 h1=float(btc.get("priceChangePercent","0")) if btc else 0
 kl=get_klines("BTCUSDT",70)
 if len(kl)<30:
  if h1>1: return {"regime":"TRENDING_BULL","bias":"LONG","btc":price,"adx":22,"h1":h1,"reason":f"BULL H1 +{h1:.1f}% BTC ${price:.0f} LONG boost allow SHORT"}
  if h1<-1: return {"regime":"TRENDING_BEAR","bias":"SHORT","btc":price,"adx":22,"h1":h1,"reason":f"BEAR H1 {h1:.1f}% BTC ${price:.0f} SHORT boost allow LONG"}
  return {"regime":"RANGING","bias":"BOTH","btc":price,"adx":16,"h1":h1,"reason":f"RANGING H1 {h1:+.1f}% BTC ${price:.0f} BOTH"}
 closes=[float(k[4]) for k in kl]; e50=ema(closes,50); e70=ema(closes,70)
 if e50 and e70 and closes[-1]>e50>e70 and h1>0.5: return {"regime":"TRENDING_BULL","bias":"LONG","btc":price,"adx":23,"h1":h1,"reason":f"BULL >{e50:.0f}>{e70:.0f} BTC ${price:.0f} H1 {h1:+.1f}% LONG boost allow SHORT"}
 if e50 and e70 and closes[-1]<e50<e70 and h1<-0.5: return {"regime":"TRENDING_BEAR","bias":"SHORT","btc":price,"adx":23,"h1":h1,"reason":f"BEAR <{e50:.0f}<{e70:.0f} BTC ${price:.0f} H1 {h1:+.1f}% SHORT boost allow LONG"}
 return {"regime":"RANGING","bias":"BOTH","btc":price,"adx":16,"h1":h1,"reason":f"RANGING BTC ${price:.0f} H1 {h1:+.1f}% BOTH LONG SHORT"}
def load_state():
 s=kv_get(STATE_KEY)
 if not s: s={"cap":300,"daily":0,"fees":0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"bl":{},"last":{}}}
 L=s.get("learn",{}); L.setdefault("bl",{}); L.setdefault("last",{})
 today=time.strftime("%Y-%m-%d")
 if L.get("date")!=today: s["daily"]=0; s["fees"]=0; L["date"]=today; L["last"]={}
 now=int(time.time()); L["bl"]={k:v for k,v in L["bl"].items() if v>now}; L["last"]={k:v for k,v in L["last"].items() if v>now}
 s["learn"]=L
 # FIX old market keys
 mk=s.get("market",{})
 if mk:
  # handle both btc and btc_price
  if "btc" not in mk:
   mk["btc"]=mk.get("btc_price",83600)
  if "reason" not in mk: mk["reason"]=mk.get("reason","")
  if "regime" not in mk: mk["regime"]=mk.get("regime","RANGING")
  if "bias" not in mk: mk["bias"]=mk.get("bias","BOTH")
  if "h1" not in mk: mk["h1"]=0
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
   sigs.append({"symbol":base,"side":"LONG","price":price,"vol":int(vol),"h1":h1,"rsi":r,"score":sc,"tp":0.35,"sl":0.45,"strat":"LONG_CONF","reason":f"LONG RSI {r:.0f} H1 {h1:+.1f}% {market.get('regime','')}"})
  if (h1>=4 and h1<=18) or (h1<=-1 and h1>=-8):
   ok=True
   if closes and len(closes)>=2:
    if h1>=4: ok = r>60 or closes[-1]<closes[-2]
   if ok and r>35:
    sc=vol/1e6*abs(h1)*0.8+(r-40)*0.1
    if base in ["BTC","ETH","ETC","SOL","AVAX","ARB","SUI","SEI","STRK","NEAR","ENA","FET","AERO","DOGE","OP","TIA","AVAX"]: sc*=1.5
    if h1>=5: sc*=1.4
    if market.get("bias")=="SHORT": sc*=1.25
    sigs.append({"symbol":base,"side":"SHORT","price":price,"vol":int(vol),"h1":h1,"rsi":r,"score":sc,"tp":0.38,"sl":0.50,"strat":"SHORT_CONF","reason":f"SHORT RSI {r:.0f} H1 {h1:+.1f}% PUMPED TOP {market.get('regime','')}"})
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
    closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"gross":gross_usd,"reason":should,"age":age,"pct_gross":gross,"strat":tr.get("strat","")})
    L["last"][tr["symbol"]]=now+400
    if net<-0.45: L["bl"][tr["symbol"]]=now+1800
   else: new_open.append(tr)
  except: new_open.append(tr)
 wins=sum(1 for c in closed if c["net"]>0.08); loss=sum(1 for c in closed if c["net"]<0)
 for s in final:
  if len(new_open)>=MAXP: break
  if s["symbol"] in [x["symbol"] for x in new_open]: continue
  new_open.append({"symbol":s["symbol"],"side":s["side"],"entry":s["price"],"price":s["price"],"pos":POS,"ts":now,"peak":0,"age":0,"h1":s["h1"],"rsi":s["rsi"],"score":s["score"],"strat":s["strat"],"tp":s["tp"],"sl":s["sl"],"reason":s["reason"]})
 st["open"]=new_open; st["closed"]=closed[:150]; st["cap"]=cap; st["daily"]=daily; st["fees"]=fees; st["wins"]=wins; st["loss"]=loss; st["total"]=tot; st["scan"]=scan; st["market"]=market
 kv_set(STATE_KEY,st)
 return {"ok":True,"scan":scan,"open":len(new_open),"cap":cap,"market":f"{market['regime']} {market['bias']} BTC ${int(market['btc'])} L:{sum(1 for x in new_open if x['side']=='LONG')} S:{sum(1 for x in new_open if x['side']=='SHORT')}","v":"v802 FIX btc error"}
def render(st):
 op=st.get("open",[]); cl=st.get("closed",[]); cap=st.get("cap",300); daily=st.get("daily",0); fees=st.get("fees",0); wins=st.get("wins",0); loss=st.get("loss",0); tot=st.get("total",0); scan=st.get("scan",0)
 mk=st.get("market",{})
 # FIX all possible keys
 btc=mk.get("btc", mk.get("btc_price",83600))
 regime=mk.get("regime","RANGING"); bias=mk.get("bias","BOTH"); h1=mk.get("h1",0); reason=mk.get("reason","")
 wr=int(wins/tot*100) if tot else 0; unreal=sum([x.get("net",0) for x in op]); l_open=sum(1 for x in op if x["side"]=="LONG"); s_open=sum(1 for x in op if x["side"]=="SHORT")
 html=f"<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{{background:#000;color:#eee;font-family:monospace;font-size:11px;padding:6px}} .h{{background:linear-gradient(90deg,#0f8,#0ff);color:#000;padding:10px;text-align:center;font-weight:900}} .c{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px}} .b{{background:#111;border:1px solid #333;padding:8px;border-radius:8px;text-align:center}} .it{{background:#111;border:1px solid #333;padding:8px;margin:6px 0;border-radius:8px}} .LONG{{color:#0f8}} .SHORT{{color:#f44}}</style></head><body>"
 html+=f"<div class='h'>VENUS v802 FIX btc ERROR SMART LONG SHORT $0.50 - SCAN #{scan} - {regime} {bias} BTC ${btc:.0f} L:{l_open} S:{s_open}</div>"
 html+=f"<div class='c'><div class='b'>CAP ${cap:.2f} WITH OPEN {cap+unreal:.2f} UNREAL {unreal:+.2f}</div><div class='b' style='color:{'#f44' if daily<0 else '#0f8'}'>DAILY ${daily:+.2f} NET FEES ${fees:.2f} W:{wins} L:{loss} {wr}%</div><div class='b'>{regime} {bias} BTC ${btc:.0f} H1 {h1:+.1f}%<br>{reason[:60]}</div></div>"
 html+=f"<div class='b'>OPEN {len(op)}/3 L:{l_open} S:{s_open} - {regime} {bias} - v802 FIX btc ERROR</div>"
 for tr in op:
  html+=f"<div class='it'><b class='{tr['side']}'>{tr['symbol']} {tr['side']} {tr.get('strat','')} AGE {tr.get('age',0)}s PEAK {tr.get('peak',0):.2f}%</b><br>ENTRY ${tr['entry']:.4f} -> NOW ${tr['price']:.4f} {tr.get('pct_gross',0):.3f}% GROSS {tr.get('pct',0):.3f}% NET ${tr.get('net',0):+.3f} H1 {tr.get('h1',0):+.1f}% RSI {tr.get('rsi',0):.0f}<br>{tr.get('reason','')}</div>"
 html+=f"<div class='b'>CLOSED {len(cl)} W:{wins} L:{loss} {wr}% CAP ${cap:.2f}</div>"
 for c in cl[:12]:
  col="#0f8" if c["net"]>0.08 else "#f44"
  html+=f"<div style='color:{col};border-bottom:1px solid #222;padding:3px'>{c['symbol']} {c['side']} ${c['net']:+.2f} {c['reason']} AGE {c['age']}s</div>"
 html+="</body></html>"
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
  return Response(f"Error {e}<br><pre>{tb[:1000]}</pre>", mimetype="text/html")
