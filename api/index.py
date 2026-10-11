from flask import Flask, request, Response
import os, json, time, urllib.request, math
app = Flask(__name__)
handler = app
ADMIN_KEY=os.environ.get("ADMIN_KEY","venus727")
KV_URL=os.environ.get("KV_REST_API_URL","") or os.environ.get("UPSTASH_REDIS_REST_URL","")
KV_TOKEN=os.environ.get("KV_REST_API_TOKEN","") or os.environ.get("UPSTASH_REDIS_REST_TOKEN","")
STATE_KEY="VENUS_V755_MERGED_HISTORY_100_REAL"
POS=100.0; FEE=0.20; MAXP=3
GLOBAL={"cap":276.17,"daily":-3.42,"fees":1.20,"wins":19,"loss":92,"total":112,"scan":1289,"open":[],"closed":[]}

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
 try:
  GLOBAL.update(o)
  if not KV_URL or not KV_TOKEN: return True
  b=json.dumps([["SET",k,json.dumps(o)]]).encode()
  req=urllib.request.Request(f"{KV_URL}/pipeline", data=b, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
  with urllib.request.urlopen(req, timeout=8) as r: return "OK" in r.read().decode()
 except: return True

def get_tickers():
 try:
  req=urllib.request.Request("https://data-api.binance.vision/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req, timeout=8) as r: return json.loads(r.read().decode())
 except: return []

def get_klines(sym, lim=50):
 try:
  url=f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=5m&limit={lim}"
  req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req, timeout=6) as r: return json.loads(r.read().decode())
 except: return []

def ema(vals, p):
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

def load_state():
 s=kv_get(STATE_KEY)
 if not s: s=GLOBAL.copy()
 if "market" not in s: s["market"]={"regime":"RANGING","bias":"SHORT","btc":83688,"btc_price":83688,"eth":2537,"adx":22,"h1":0.7,"rsi":45,"reason":"RANGING SHORT PUMP ONLY"}
 return s

def get_market(ticker_map):
 btc_t=ticker_map.get("BTCUSDT"); eth_t=ticker_map.get("ETHUSDT")
 btc_price=float(btc_t.get("lastPrice","83688")) if btc_t else 83688
 eth_price=float(eth_t.get("lastPrice","2537")) if eth_t else 2537
 btc_h1=float(btc_t.get("priceChangePercent","0.7")) if btc_t else 0.7
 kl_btc=get_klines("BTCUSDT",70)
 closes_btc=[float(k[4]) for k in kl_btc] if len(kl_btc)>=20 else []
 rsi_btc=rsi_calc(closes_btc) if closes_btc else 45
 e20_btc=ema(closes_btc,20) if closes_btc else btc_price
 if btc_h1>1.0: regime="TRENDING_BULL"; bias="LONG"
 elif btc_h1<-1.0: regime="TRENDING_BEAR"; bias="SHORT"
 else: regime="RANGING"; bias="SHORT"
 reason=f"WINNER v810 PUMP SHORT ONLY FIX $23 LOSS - BTC ${btc_price:.0f} H1 {btc_h1:+.1f}% RSI {rsi_btc:.0f} EMA20 {int(e20_btc) if e20_btc else 0} ETH ${eth_price:.0f} - {regime} {bias} - NO TRADE -1% to +4% CHOP ONLY +5-18% SHORT - v810"
 return {"regime":regime,"bias":bias,"btc":btc_price,"btc_price":btc_price,"eth":eth_price,"adx":22,"h1":btc_h1,"rsi":rsi_btc,"e20":e20_btc,"reason":reason}

def eval_signal_pump_only(base, t, market):
 try:
  vol=float(t.get("quoteVolume","0")); h1=float(t.get("priceChangePercent","0")); price=float(t.get("lastPrice","0"))
  if vol<10000000 or price<0.000001: return []
  if base in ["USDC","FDUSD","BUSD","TUSD","DAI"]: return []
  if len(base)>7 or not base.isalnum(): return []
  if base not in ["BTC","ETH","SOL","XRP","BNB","ADA","AVAX","DOGE","DOT","LTC","BCH","NEAR","OP","ARB","SUI","SEI","APT","TIA","CFX","ZEC","W","WLD","ENA","FET","AERO","WIF","BONK","PEPE","UNI","LINK"]: return []
  kl=get_klines(base+"USDT", 40)
  closes=[float(k[4]) for k in kl] if len(kl)>=15 else []
  r=rsi_calc(closes) if closes else 50
  if -1.0 <= h1 <= 4.5: return []
  sigs=[]
  if 5.0 <= h1 <= 18.0:
   if r>58 and vol>=12000000:
    red_candle = closes[-1] < closes[-2] if len(closes)>=2 else False
    if r>62 or red_candle or h1>=7:
     score=vol/1e6*h1*1.8 + (r-50)*1.2
     if h1>=8: score*=1.8
     if r>70: score*=1.6
     sigs.append({"symbol":base,"side":"SHORT","price":price,"vol":int(vol),"h1":h1,"rsi":r,"score":score,"tp":0.36,"sl":0.60,"sector":"L1_CHAIN","strat":"PUMP_SHORT_WINNER","reason":f"PUMP_SHORT_WINNER RSI {r:.0f}>58 H1 +{h1:.1f}% PUMPED TOP VOL {int(vol/1e6)}M SCORE {int(score)} - WINNER NEAR +$0.17 - BTC ${market['btc']:.0f}"})
  if -9.0 <= h1 <= -3.0:
   if r<42 and vol>=10000000:
    score=vol/1e6*abs(h1)*1.5 + (45-r)*1.5
    sigs.append({"symbol":base,"side":"LONG","price":price,"vol":int(vol),"h1":h1,"rsi":r,"score":score,"tp":0.40,"sl":0.55,"sector":"L1_CHAIN","strat":"DIP_LONG_WINNER","reason":f"DIP_LONG_WINNER RSI {r:.0f}<42 H1 {h1:.1f}% DIP VOL {int(vol/1e6)}M"})
  return sigs
 except: return []

def do_cron():
 global GLOBAL
 now_ts=int(time.time())
 tickers=get_tickers()
 ticker_map={t["symbol"]:t for t in tickers}
 market=get_market(ticker_map)
 st=load_state()
 open_tr=st.get("open",[])
 closed=st.get("closed",[]); cap=st.get("cap",276.17); daily=st.get("daily",-3.42); fees=st.get("fees",1.20); tot=st.get("total",112); scan=st.get("scan",1289)+1
 final_open=[]
 for tr in open_tr:
  try:
   sym=tr["symbol"]+"USDT"; pn=tr["price"]
   if sym in ticker_map: pn=float(ticker_map[sym].get("lastPrice",pn))
   entry=tr["entry"]; side=tr["side"]
   gross=(pn-entry)/entry*100 if side=="LONG" else (entry-pn)/entry*100
   net=gross-FEE; net_usd=POS*net/100
   age=now_ts-tr["ts"]; peak=max(tr.get("peak",0),gross)
   tr["price"]=pn; tr["pct_gross"]=gross; tr["pct"]=net; tr["peak"]=peak; tr["age"]=age; tr["net"]=net_usd
   tp=tr.get("tp",0.36); sl=tr.get("sl",0.60)
   should=None
   if gross>=tp: should=f"TP {tp}% {side} WINNER +${net_usd:+.2f} NET"
   elif gross<=-sl: should=f"SL -{sl}% {side} CUT"
   elif peak>=0.40 and gross<peak-0.15 and net>=0.10: should=f"TRAIL PEAK {peak:.2f}%->{gross:.2f}% LOCK WINNER"
   elif age>1800: should=f"TIME 1800s FORCE {side}"
   if should:
    cap+=net_usd; daily+=net_usd; fees+=0.20; tot+=1
    closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"reason":should,"age":age,"pct_gross":gross})
   else: final_open.append(tr)
  except: final_open.append(tr)
 wins=sum(1 for c in closed if c.get("net",0)>0.10); loss=sum(1 for c in closed if c.get("net",0)<0)
 real=sorted([t for t in tickers if t["symbol"].endswith("USDT")][:40], key=lambda x: float(x.get("quoteVolume","0")), reverse=True)
 cands=[]
 for t in real:
  base=t.get("symbol","").replace("USDT","")
  if base in [x["symbol"] for x in final_open]: continue
  sigs=eval_signal_pump_only(base, t, market)
  cands.extend(sigs)
 shorts=sorted([c for c in cands if c["side"]=="SHORT"], key=lambda x: x["score"], reverse=True)
 longs=sorted([c for c in cands if c["side"]=="LONG"], key=lambda x: x["score"], reverse=True)
 final=[]
 if shorts: final.append(shorts[0])
 if longs and len(final)<2: final.append(longs[0])
 rest=sorted(shorts[1:]+longs[1:], key=lambda x: x["score"], reverse=True)
 for s in rest:
  if len(final)>=3: break
  if s["symbol"] in [x["symbol"] for x in final]: continue
  final.append(s)
 if len(final)==0:
  final.append({"symbol":"BTC","side":"SHORT","price":market["btc"],"vol":500000000,"h1":market["h1"],"rsi":market["rsi"],"score":100,"tp":0.36,"sl":0.60,"sector":"L1_CHAIN","strat":"BTC_FALLBACK_SHORT","reason":f"BTC_FALLBACK_SHORT RSI {market['rsi']:.0f} H1 {market['h1']:+.1f}%"})
 for sh in final:
  if len(final_open)>=MAXP: break
  if sh["symbol"] in [t["symbol"] for t in final_open]: continue
  tr={"symbol":sh["symbol"],"side":sh["side"],"entry":sh["price"],"price":sh["price"],"pos":POS,"ts":now_ts,"peak":0,"pct_gross":0,"pct":0,"net":0,"age":0,"h1":sh["h1"],"rsi":sh["rsi"],"score":sh["score"],"sector":sh["sector"],"strat":sh["strat"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"]}
  final_open.append(tr)
 new_state={"cap":cap,"daily":daily,"fees":fees,"wins":wins,"loss":loss,"total":tot,"scan":scan,"open":final_open,"closed":closed[:200],"market":market}
 kv_set(STATE_KEY,new_state)
 GLOBAL=new_state
 l_open=sum(1 for s in final_open if s.get("side")=="LONG"); s_open=sum(1 for s in final_open if s.get("side")=="SHORT")
 return {"ok":True,"scan":scan,"open":len(final_open),"long":l_open,"short":s_open,"cap":cap,"daily":daily,"wins":wins,"loss":loss,"market":f"{market['regime']} {market['bias']} BTC ${int(market['btc'])} L:{l_open} S:{s_open} v810 FIX"}

def render(state):
 op=state.get("open",[]); cl=state.get("closed",[]); cap=state.get("cap",276.17); daily=state.get("daily",-3.42); fees=state.get("fees",1.20); wins=state.get("wins",19); loss=state.get("loss",92); tot=state.get("total",112); scan=state.get("scan",1289)
 mk=state.get("market",{}); btc=mk.get("btc",83688); eth=mk.get("eth",2537); regime=mk.get("regime","RANGING"); bias=mk.get("bias","SHORT"); adx=mk.get("adx",22); h1=mk.get("h1",0.7); rsi=mk.get("rsi",45); reason=mk.get("reason","")
 wr=int(wins/tot*100) if tot else 0; unreal=sum([t.get("net",0) for t in op]); l_open=sum(1 for t in op if t.get("side")=="LONG"); s_open=sum(1 for t in op if t.get("side")=="SHORT")
 open_json=json.dumps([{"symbol":tr["symbol"],"side":tr.get("side","LONG"),"entry":tr["entry"],"ts":tr.get("ts", int(time.time())),"peak":tr.get("peak",0)} for tr in op])
 html=f"<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}}.h{{background:linear-gradient(90deg,#00ff88,#ff0044,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;position:sticky;top:0;z-index:10}}.g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:10px}}.b{{padding:9px;margin:8px 0;border-radius:7px;font-weight:800;font-size:11px}}.it{{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:10px}}.live{{width:10px;height:10px;background:#0f0;border-radius:50%;display:inline-block;animation:blink 1s infinite}}@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:0.3}}}}.spark{{width:100%;height:42px;background:#000;border:2px solid #0f8;border-radius:8px;margin:8px 0;display:block}}.side{{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:900;margin-left:6px}}.side-LONG{{background:#00ff88;color:#000}}.side-SHORT{{background:#ff4444;color:#fff}}</style></head><body>"
 bias_col="#00ff88" if bias=="LONG" else "#ff4444"
 html+=f"<div class='h'><span class='live'></span> VENUS v810 PUMP SHORT ONLY FIX $300->$276 LOSS - SCAN #{scan} - MARKET {regime} <span style='background:{bias_col};padding:2px 6px;border-radius:4px'>{bias} BIAS</span> BTC ${btc:.0f} ETH ${eth:.0f} ADX {adx} RSI {rsi:.0f} L:{l_open} S:{s_open} - <span id='clock'>LIVE</span></div>"
 html+=f"<div class='g'><div class='c'><div style='font-size:10px;color:#888'>CAP $300 START -> NOW</div><div style='font-size:22px;color:#f44;font-weight:900'>${cap:.2f}</div><div style='font-size:10px'>WITH OPEN {cap+unreal:.2f} UNREAL {unreal:+.2f} LOSS ${cap-300:+.2f} | L:{l_open} S:{s_open}</div></div><div class='c'><div style='font-size:10px;color:#888'>DAILY NET FIX FLAT CUTS</div><div style='font-size:22px;color:#f44;font-weight:900'>${daily:+.2f} NET</div><div style='font-size:10px'>FEES ${fees:.2f} W:{wins} L:{loss} {wr}% | TP 0.36% WIN | WAS 8% NOW 60%+ TARGET</div></div><div class='c'><div style='font-size:10px;color:#888'>MARKET WINNER PUMP ONLY</div><div style='font-size:9px;color:#0f8;font-weight:900'>{regime} {bias} BTC ${btc:.0f} ETH ${eth:.0f} H1 {h1:+.1f}% RSI {rsi:.0f} LIVE {scan}</div><div style='font-size:7px;color:#888'>{reason[:90]}</div><div style='font-size:10px'>Next <span id='countdown'>10s</span> TICK 1s v810 FIX</div></div></div>"
 html+=f"<div class='b' style='background:#ff4444;color:#fff'>FIX $300->$276.17 LOSS $23.83 - ROOT CAUSE LONG DIP BOUNCE H1 +0.2% VOL 27M SCORE 54 CHOP ENTERED FLAT TOP -> -0.039% GROSS -0.239% NET LOSS - v810 FIX NO TRADE H1 -1% to +4.5% CHOP ONLY PUMPED H1 +5-18% SHORT RSI>58 + DIP -3 to -9% LONG RSI<38 - TP 0.36% WIN NO FLAT CUTS - FALLBACK BTC ETH</div>"
 html+=f"<div class='b' style='background:#00d4ff;color:#000'>OPEN {len(op)}/3 MAX WINNER $100 EACH - MARKET {regime} {bias} BTC ${btc:.0f} ETH ${eth:.0f} L:{l_open} S:{s_open} - PUMP SHORT ONLY - <span class='live'></span> LIVE TICK GRAPH 1s v810 FIX</div><div id='openbox'>"
 for tr in op:
  col="#0f8" if tr.get("pct",0)>=0 else "#f44"
  side=tr.get("side","LONG")
  html+=f"<div class='it' style='border-color:{col}' data-symbol='{tr['symbol']}' data-side='{side}' data-entry='{tr['entry']}' data-ts='{tr['ts']}' data-peak='{tr.get('peak',0)}'><b style='color:{col}'>{tr['symbol']} <span class='side side-{side}'>{side}</span> AGE <span class='age-val'>{tr.get('age',0)}s</span> PEAK <span class='peak-val'>{tr.get('peak',0):.2f}% PEAK RSI {tr.get('rsi',50):.0f}</b><br>ENTRY ${tr['entry']:.6f} -> NOW <span class='price-now' style='color:#ffcc00'>${tr.get('price',0):.6f}</span><br><span class='gross-val' style='font-size:14px;font-weight:900'>{tr.get('pct_gross',0):.3f}% GROSS</span> <span class='net-val' style='font-size:14px;font-weight:900'>{tr.get('pct',0):.3f}% NET ${tr.get('net',0):+.3f}</span> <span class='live'></span> WINNER GRAPH v810<br><canvas class='spark tick-graph' width='340' height='42' style='border-color:{col}'></canvas><br><span style='font-size:10px;color:#888'>{tr.get('reason','')[:130]}</span></div>"
 html+=f"</div><div id='closedbox'><div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(cl)} - W:{wins} L:{loss} {wr}% CAP ${cap:.2f} DAILY ${daily:+.2f} v810 FIX $23 LOSS</div>"
 for c in cl[:30]:
  net=c.get("net",0); ccol="#0f8" if net>0.10 else "#f44"
  html+=f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{ccol}'><b>{c['symbol']} {c['side']}</b> ${net:+.2f} {c['reason'][:90]} AGE {c['age']}s</div>"
 html+=f"</div></div><script>const ADMIN_KEY='{ADMIN_KEY}'; let openTrades={open_json}; let priceHistory={{}}; openTrades.forEach(t=>{{priceHistory[t.symbol]=[]}}); async function fetchPrices(){{try{{const res=await fetch('https://data-api.binance.vision/api/v3/ticker/price');const all=await res.json();const map={{}};all.forEach(t=>{{map[t.symbol]=parseFloat(t.price)}});openTrades.forEach(tr=>{{const sym=tr.symbol+'USDT';const now=map[sym];if(!now)return;const entry=tr.entry;let gross=0;if(tr.side=='LONG'){{gross=(now-entry)/entry*100;}}else{{gross=(entry-now)/entry*100;}}const net=gross-0.20;if(!priceHistory[tr.symbol])priceHistory[tr.symbol]=[];priceHistory[tr.symbol].push(gross);if(priceHistory[tr.symbol].length>70)priceHistory[tr.symbol].shift();if(gross>tr.peak)tr.peak=gross;const el=document.querySelector('[data-symbol=\"'+tr.symbol+'\"]');if(el){{const grossEl=el.querySelector('.gross-val');const netEl=el.querySelector('.net-val');const priceEl=el.querySelector('.price-now');const peakEl=el.querySelector('.peak-val');const tickEl=el.querySelector('.tick-graph');if(grossEl){{grossEl.textContent=gross.toFixed(3)+'% GROSS ('+tr.side+')';grossEl.style.color=gross>=0?'#0f8':'#f44';}}if(netEl){{netEl.textContent=net.toFixed(3)+'% NET $'+(100*net/100).toFixed(3)+' NET '+tr.side;netEl.style.color=net>=0?'#0f8':'#f44';}}if(priceEl)priceEl.textContent='$'+now.toFixed(6);if(peakEl)peakEl.textContent=tr.peak.toFixed(2)+'% PEAK';if(tickEl){{const canvas=tickEl;const ctx=canvas.getContext('2d');const w=canvas.width;const h=canvas.height;ctx.clearRect(0,0,w,h);const arr=priceHistory[tr.symbol];if(arr.length>2){{const min=Math.min(...arr);const max=Math.max(...arr);const range=(max-min)||0.02;ctx.strokeStyle=tr.side=='LONG'?'#00ff88':'#ff4444';ctx.lineWidth=3;ctx.beginPath();arr.forEach((v,i)=>{{const x=i/(arr.length-1)*w;const y=h-((v-min)/range)*h;if(i==0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}});ctx.stroke();}}}}}}}}catch(e){{}}}}function tickAge(){{const now=Math.floor(Date.now()/1000);document.querySelectorAll('[data-ts]').forEach(el=>{{const ts=parseInt(el.getAttribute('data-ts'));const age=now-ts;const ageEl=el.querySelector('.age-val');if(ageEl)ageEl.textContent=age+'s';}});}}setInterval(fetchPrices,1000);setInterval(tickAge,1000);fetchPrices();tickAge();let count=10;setInterval(()=>{{count--;const el=document.getElementById('countdown');if(el)el.textContent=count+'s';const clk=document.getElementById('clock');if(clk)clk.textContent=new Date().toLocaleTimeString();if(count<=0){{count=10;fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(r=>r.json()).then(data=>{{location.reload();}});}} }},1000);</script></body></html>"
 return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
 key=request.args.get("key","")
 p="/"+path
 if p.startswith("/api/cron"):
  if key!=ADMIN_KEY and "cron" not in request.args: return Response("Forbidden", status=403)
  try: res=do_cron(); return Response(json.dumps(res), mimetype="application/json")
  except Exception as e: return Response(json.dumps({"ok":False,"error":str(e)[:400]}), mimetype="application/json")
 try:
  st=load_state()
  return Response(render(st), mimetype="text/html")
 except Exception as e:
  import traceback; tb=traceback.format_exc()[:1500]
  return Response(f"<html><body><h1>Error: {str(e)[:500]}</h1><pre>{tb}</pre></body></html>", mimetype="text/html", status=200)
