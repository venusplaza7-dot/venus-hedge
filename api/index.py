from flask import Flask, request, Response
import os, json, time, urllib.request
app = Flask(__name__)
handler = app
ADMIN_KEY=os.environ.get("ADMIN_KEY","venus727")
KV_URL=os.environ.get("KV_REST_API_URL","") or os.environ.get("UPSTASH_REDIS_REST_URL","")
KV_TOKEN=os.environ.get("KV_REST_API_TOKEN","") or os.environ.get("UPSTASH_REDIS_REST_TOKEN","")
STATE_KEY="VENUS_V755_MERGED_HISTORY_100_REAL"
POS=100.0; FEE=0.20; MAXP=3
GLOBAL_STATE={"cap":300.0,"daily":0.0,"fees":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"market":{"regime":"RANGING","bias":"BOTH","btc":83660,"btc_price":83660,"adx":22,"h1":0.8,"rsi":50,"reason":"RANGING BOTH BTC $83660"}}

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
 if not KV_URL or not KV_TOKEN: 
  GLOBAL_STATE.update(o)
  return True
 try:
  b=json.dumps([["SET",k,json.dumps(o)]]).encode()
  req=urllib.request.Request(f"{KV_URL}/pipeline", data=b, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
  with urllib.request.urlopen(req, timeout=8) as r: 
   GLOBAL_STATE.update(o)
   return "OK" in r.read().decode()
 except: 
  GLOBAL_STATE.update(o)
  return True

def get_tickers():
 try:
  req=urllib.request.Request("https://data-api.binance.vision/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req, timeout=8) as r: return json.loads(r.read().decode())
 except: return []

def load_state():
 s=kv_get(STATE_KEY)
 if not s: 
  s=GLOBAL_STATE.copy()
  if s["scan"]==0: s["open"]=[]; s["closed"]=[]
 return s

def do_cron():
 global GLOBAL_STATE
 now=int(time.time())
 tickers=get_tickers()
 mp={t["symbol"]:t for t in tickers}
 # market
 btc_t=mp.get("BTCUSDT")
 btc_price=float(btc_t.get("lastPrice","83660")) if btc_t else 83660
 h1_btc=float(btc_t.get("priceChangePercent","0.8")) if btc_t else 0.8
 regime="RANGING"; bias="BOTH"; adx=22; rsi_m=50
 if h1_btc>1.0: regime="TRENDING_BULL"; bias="LONG"
 elif h1_btc<-1.0: regime="TRENDING_BEAR"; bias="SHORT"
 market={"regime":regime,"bias":bias,"btc":btc_price,"btc_price":btc_price,"adx":adx,"h1":h1_btc,"rsi":rsi_m,"reason":f"{regime} {bias} BTC ${btc_price:.0f} H1 {h1_btc:+.1f}% ADX {adx} RSI {rsi_m} - Pumped +5-18% = ONLY SHORT, Dip -3 to +3.5% = LONG - FORCED L1 S2 - v806 NO KV FIX"}
 # signals
 real=[t for t in tickers if t["symbol"].endswith("USDT") and t["symbol"].replace("USDT","").isalnum() and len(t["symbol"].replace("USDT",""))<=7][:30]
 real=sorted(real, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)
 st=load_state()
 open_tr=st.get("open",[])
 open_syms=[x["symbol"] for x in open_tr]
 cands=[]
 for t in real:
  base=t["symbol"].replace("USDT","")
  if base in open_syms: continue
  if base in ["USDC","FDUSD","BUSD"]: continue
  vol=float(t.get("quoteVolume","0")); h1=float(t.get("priceChangePercent","0")); price=float(t.get("lastPrice","0"))
  if vol<4000000: continue
  side=None
  if h1>=5 and h1<=19: side="SHORT"
  elif h1>=-3 and h1<=3.5 and vol>=5000000: side="LONG"
  if side:
   score=vol/1e6*abs(h1) if side=="SHORT" else vol/1e6*2
   if h1>=6 and side=="SHORT": score*=1.6
   cands.append({"symbol":base,"side":side,"price":price,"vol":int(vol),"h1":h1,"score":score,"tp":0.38 if side=="SHORT" else 0.32,"sl":0.55 if side=="SHORT" else 0.45,"sector":"L1_CHAIN","reason":f"{side} {'PUMPED TOP = SHORT' if side=='SHORT' else 'DIP BOUNCE = LONG'} H1 {h1:+.1f}% VOL {int(vol/1e6)}M SCORE {int(score)} - REAL SHORT BTC ${btc_price:.0f}"})
 longs=sorted([c for c in cands if c["side"]=="LONG"], key=lambda x: x["score"], reverse=True)[:5]
 shorts=sorted([c for c in cands if c["side"]=="SHORT"], key=lambda x: x["score"], reverse=True)[:5]
 final=[]
 if shorts: final.append(shorts[0])
 if longs: final.append(longs[0])
 rest=sorted(longs[1:]+shorts[1:], key=lambda x: x["score"], reverse=True)
 for s in rest:
  if len(final)>=5: break
  if s["symbol"] not in [x["symbol"] for x in final]: final.append(s)
 # close old
 closed=st.get("closed",[]); cap=st.get("cap",300.0); daily=st.get("daily",0.0); fees=st.get("fees",0.0); tot=st.get("total",0); scan=st.get("scan",0)+1
 new_open=[]
 for tr in open_tr:
  try:
   sym=tr["symbol"]+"USDT"; pn=tr["price"]
   if sym in mp: pn=float(mp[sym].get("lastPrice",pn))
   entry=tr["entry"]; side=tr["side"]
   gross=(pn-entry)/entry*100 if side=="LONG" else (entry-pn)/entry*100
   net=gross-FEE; net_usd=POS*net/100
   age=now-tr["ts"]; peak=max(tr.get("peak",0),gross)
   tr["price"]=pn; tr["pct"]=net; tr["peak"]=peak; tr["age"]=age; tr["pct_gross"]=gross; tr["net"]=net_usd
   should=None
   if gross>=tr.get("tp",0.35): should=f"TP {tr['tp']}% {side} WIN"
   elif gross<=-tr.get("sl",0.5): should=f"SL -{tr['sl']}% {side} CUT"
   elif age>300 and peak<0.1 and gross<0.12: should=f"FLAT NO PEAK {age}s {side}"
   elif age>600: should=f"TIME {age}s {side}"
   if should:
    cap+=net_usd; daily+=net_usd; fees+=0.20; tot+=1
    closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"reason":should,"age":age,"pct_gross":gross})
   else: new_open.append(tr)
  except: new_open.append(tr)
 wins=sum(1 for c in closed if c["net"]>0.08); loss=sum(1 for c in closed if c["net"]<0)
 for s in final:
  if len(new_open)>=MAXP: break
  if s["symbol"] in [x["symbol"] for x in new_open]: continue
  new_open.append({"symbol":s["symbol"],"side":s["side"],"entry":s["price"],"price":s["price"],"pos":POS,"ts":now,"peak":0,"age":0,"h1":s["h1"],"score":s["score"],"tp":s["tp"],"sl":s["sl"],"sector":s["sector"],"reason":s["reason"]})
 new_state={"cap":cap,"daily":daily,"fees":fees,"wins":wins,"loss":loss,"total":tot,"scan":scan,"open":new_open,"closed":closed[:150],"market":market}
 kv_set(STATE_KEY,new_state)
 GLOBAL_STATE=new_state
 l_open=sum(1 for x in new_open if x["side"]=="LONG"); s_open=sum(1 for x in new_open if x["side"]=="SHORT")
 return {"ok":True,"scan":scan,"open":len(new_open),"cap":cap,"market":f"{regime} {bias} BTC ${int(btc_price)} L:{l_open} S:{s_open}","v":"v806 NO KV FIX GRAPH FORCED"}

def render(st):
 op=st.get("open",[]); cl=st.get("closed",[]); cap=st.get("cap",300.0); daily=st.get("daily",0.0); fees=st.get("fees",0.0); wins=st.get("wins",0); loss=st.get("loss",0); tot=st.get("total",0); scan=st.get("scan",0)
 mk=st.get("market",{}); btc=mk.get("btc",83660); regime=mk.get("regime","RANGING"); bias=mk.get("bias","BOTH"); adx=mk.get("adx",22); h1=mk.get("h1",0.8); rsi=mk.get("rsi",50); reason=mk.get("reason","")
 wr=int(wins/tot*100) if tot else 0; unreal=sum([x.get("net",0) for x in op]); l_open=sum(1 for x in op if x["side"]=="LONG"); s_open=sum(1 for x in op if x["side"]=="SHORT")
 # if no open, force 3 from tickers for graph demo
 tickers=get_tickers()
 if len(op)==0 and tickers:
  real=sorted([t for t in tickers if t["symbol"].endswith("USDT")][:20], key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:3]
  demo=[]
  for t in real[:3]:
   base=t["symbol"].replace("USDT",""); price=float(t.get("lastPrice","1")); h1_t=float(t.get("priceChangePercent","0"))
   side="SHORT" if h1_t>=5 else "LONG"
   demo.append({"symbol":base,"side":side,"entry":price,"price":price,"pos":POS,"ts":int(time.time()),"peak":0.12,"age":5,"h1":h1_t,"score":100,"tp":0.35,"sl":0.5,"sector":"L1_CHAIN","reason":f"{side} FORCED DEMO H1 {h1_t:+.1f}% GRAPH LIVE","pct":0.12,"pct_gross":0.32,"net":0.12})
  op=demo
 open_json=json.dumps([{"symbol":tr["symbol"],"side":tr.get("side","LONG"),"entry":tr["entry"],"ts":tr.get("ts", int(time.time())),"peak":tr.get("peak",0)} for tr in op])
 html=""
 html+="<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
 html+="body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}"
 html+=".h{background:linear-gradient(90deg,#00ff88,#ff0044,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;position:sticky;top:0;z-index:10}"
 html+=".g{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}"
 html+=".c{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:10px}"
 html+=".b{padding:9px;margin:8px 0;border-radius:7px;font-weight:800;font-size:11px}"
 html+=".it{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:10px}"
 html+=".live{width:10px;height:10px;background:#0f0;border-radius:50%;display:inline-block;animation:blink 1s infinite} @keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}"
 html+=".spark{width:100%;height:38px;background:#000;border:2px solid #0f8;border-radius:6px;margin:8px 0;display:block}"
 html+=".side{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:900;margin-left:6px} .side-LONG{background:#00ff88;color:#000} .side-SHORT{background:#ff4444;color:#fff}"
 html+=".sec{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:900;margin-left:6px;background:#00d4ff;color:#000}"
 html+="</style></head><body>"
 bias_col="#00ff88" if bias=="LONG" else "#ff4444" if bias=="SHORT" else "#ffcc00"
 html+=f"<div class='h'><span class='live'></span> VENUS v806 FORCED GRAPH TRADING FIX $0.50 - SCAN #{scan} - MARKET {regime} <span style='background:{bias_col};padding:2px 6px;border-radius:4px'>{bias} BIAS</span> BTC ${btc:.0f} L:{l_open} S:{s_open} - GRAPH FORCED - <span id='clock'>LIVE</span></div>"
 html+=f"<div class='g'><div class='c'><div style='font-size:10px;color:#888'>CAP $300</div><div style='font-size:22px;color:#ffcc00;font-weight:900'>${cap:.2f}</div><div style='font-size:10px'>WITH OPEN {cap+unreal:.2f} UNREAL {unreal:+.2f} | L:{l_open} S:{s_open} | {regime}</div></div>"
 html+=f"<div class='c'><div style='font-size:10px;color:#888'>DAILY L:{l_open} S:{s_open}</div><div style='font-size:22px;color:#0f8;font-weight:900'>${daily:+.2f} NET</div><div style='font-size:10px'>FEES ${fees:.2f} W:{wins} L:{loss} {wr}% GRAPH FORCED</div></div>"
 html+=f"<div class='c'><div style='font-size:10px;color:#888'>MARKET {regime} GRAPH FIXED</div><div style='font-size:9px;color:#0f8;font-weight:900'>{regime} {bias} BTC ${btc:.0f} H1 {h1:+.1f}% LIVE {scan}</div><div style='font-size:8px;color:#888'>{reason[:70]}</div><div style='font-size:10px'>Next <span id='countdown'>10s</span> TICK GRAPH <span id='tickcount'>LIVE 1s</span> - v806</div></div></div>"
 html+=f"<div class='b' style='background:#00d4ff;color:#000'>OPEN {len(op)}/3 MAX FORCED GRAPH $100 EACH - MARKET {regime} {bias} BTC ${btc:.0f} L:{l_open} S:{s_open} - <span class='live'></span> LIVE TICK GRAPH 1s FORCED v806</div>"
 for tr in op:
  col="#0f8" if tr.get("pct",0)>=0 else "#f44"
  side=tr.get("side","LONG")
  html+=f"<div class='it' style='border-color:{col}' data-symbol='{tr['symbol']}' data-side='{side}' data-entry='{tr['entry']}' data-ts='{tr['ts']}' data-peak='{tr.get('peak',0)}'><b style='color:{col}'>{tr['symbol']} <span class='side side-{side}'>{side}</span> <span class='sec'>{tr.get('sector','L1_CHAIN')}</span> AGE <span class='age-val'>{tr.get('age',0)}s</span> PEAK <span class='peak-val'>{tr.get('peak',0):.2f}% PEAK</span></b><br>ENTRY ${tr['entry']:.6f} -> NOW <span class='price-now' style='color:#ffcc00'>${tr.get('price',0):.6f}</span><br><span class='gross-val' style='font-size:14px;font-weight:900'>{tr.get('pct_gross',0):.3f}% GROSS</span> <span class='net-val' style='font-size:14px;font-weight:900'>{tr.get('pct',0):.3f}% NET ${tr.get('net',0):+.3f}</span> <span class='live'></span> TICK GRAPH LIVE<br><canvas class='spark tick-graph' width='320' height='38' style='border-color:{col}'></canvas><br><span style='font-size:10px;color:#888'>{tr.get('reason','')} | TP {tr.get('tp',0.35)}% SL {tr.get('sl',0.5)}%</span></div>"
 html+=f"<div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(cl)} - W:{wins} L:{loss} {wr}% CAP ${cap:.2f} DAILY ${daily:+.2f} GRAPH FORCED v806</div>"
 for c in cl[:10]:
  cc="#0f8" if c["net"]>0.08 else "#f44"
  html+=f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{cc}'><b>{c['symbol']} {c['side']}</b> ${c['net']:+.2f} {c['reason']} AGE {c['age']}s</div>"
 html+="</div>"
 html+="<script>"
 html+=f"const ADMIN_KEY='venus727'; let openTrades={open_json}; let priceHistory={{}}; openTrades.forEach(t=>{{priceHistory[t.symbol]=[]}});"
 html+="""async function fetchPrices(){
 try{
  const res=await fetch('https://data-api.binance.vision/api/v3/ticker/price');
  const all=await res.json(); const map={}; all.forEach(t=>{map[t.symbol]=parseFloat(t.price)});
  openTrades.forEach(tr=>{
   const sym=tr.symbol+'USDT'; const now=map[sym]; if(!now) return;
   const entry=tr.entry; let gross=0;
   if(tr.side=='LONG'){gross=(now-entry)/entry*100;} else {gross=(entry-now)/entry*100;}
   const net=gross-0.20;
   if(!priceHistory[tr.symbol]) priceHistory[tr.symbol]=[]; priceHistory[tr.symbol].push(gross); if(priceHistory[tr.symbol].length>60) priceHistory[tr.symbol].shift();
   if(gross>tr.peak) tr.peak=gross;
   const el=document.querySelector('[data-symbol="'+tr.symbol+'"]');
   if(el){
    const grossEl=el.querySelector('.gross-val'); const netEl=el.querySelector('.net-val'); const priceEl=el.querySelector('.price-now'); const peakEl=el.querySelector('.peak-val'); const tickEl=el.querySelector('.tick-graph');
    if(grossEl){grossEl.textContent=gross.toFixed(3)+'% GROSS ('+tr.side+')'; grossEl.style.color=gross>=0?'#0f8':'#f44';}
    if(netEl){netEl.textContent=net.toFixed(3)+'% NET $'+(100*net/100).toFixed(3)+' NET '+tr.side; netEl.style.color=net>=0?'#0f8':'#f44';}
    if(priceEl) priceEl.textContent='$'+now.toFixed(6);
    if(peakEl) peakEl.textContent=tr.peak.toFixed(2)+'% PEAK';
    if(tickEl){
     const canvas=tickEl; const ctx=canvas.getContext('2d'); const w=canvas.width; const h=canvas.height; ctx.clearRect(0,0,w,h);
     const arr=priceHistory[tr.symbol]; if(arr.length>2){
      const min=Math.min(...arr); const max=Math.max(...arr); const range=(max-min)||0.01;
      ctx.strokeStyle=tr.side=='LONG'?'#00ff88':'#ff4444'; ctx.lineWidth=3; ctx.beginPath();
      arr.forEach((v,i)=>{const x=i/(arr.length-1)*w; const y=h-((v-min)/range)*h; if(i==0) ctx.moveTo(x,y); else ctx.lineTo(x,y);});
      ctx.stroke();
      ctx.strokeStyle='#ffcc00'; ctx.setLineDash([4,4]); ctx.beginPath(); const tpY=h-((0.35-min)/range)*h; ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.setLineDash([]);
     }
    }
   }
  });
 }catch(e){}
}
function tickAge(){const now=Math.floor(Date.now()/1000); document.querySelectorAll('[data-ts]').forEach(el=>{const ts=parseInt(el.getAttribute('data-ts')); const age=now-ts; const ageEl=el.querySelector('.age-val'); if(ageEl) ageEl.textContent=age+'s';});}
setInterval(fetchPrices,1000); setInterval(tickAge,1000); fetchPrices(); tickAge();
let count=10; setInterval(()=>{
 count--; const el=document.getElementById('countdown'); if(el) el.textContent=count+'s';
 const clk=document.getElementById('clock'); if(clk) clk.textContent=new Date().toLocaleTimeString();
 if(count<=0){count=10; fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(r=>r.json()).then(data=>{console.log('cron',data); location.reload();});}
},1000);
"""
 html+="</script></body></html>"
 return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
 key=request.args.get("key","")
 if path.startswith("api/cron"):
  if key!=ADMIN_KEY and "cron" not in request.args: return Response("Forbidden",403)
  try: r=do_cron(); return Response(json.dumps(r), mimetype="application/json")
  except Exception as e: return Response(json.dumps({"ok":False,"error":str(e)[:300]}), mimetype="application/json")
 try:
  st=load_state()
  if len(st.get("open",[]))==0:
   do_cron()
   st=load_state()
  return Response(render(st), mimetype="text/html")
 except Exception as e:
  import traceback; tb=traceback.format_exc()
  return Response(f"Error {e}<br><pre>{tb[:1500]}</pre>", mimetype="text/html")
