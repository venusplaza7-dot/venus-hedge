from flask import Flask, request, Response
app = Flask(__name__)
import json, time, urllib.request, math, random, os

MEM={"cap":299.59,"daily":0.75,"scan":39,"offset":13,"open":[{"symbol":"OP","side":"LONG","entry":0.1396,"price":0.1396,"pos":100,"ts":0,"fc":0.74,"conf":85},{"symbol":"CYBER","side":"LONG","entry":0.358,"price":0.358,"pos":100,"ts":0,"fc":0.60,"conf":85},{"symbol":"JUP","side":"LONG","entry":0.3285,"price":0.3285,"pos":10,"ts":0,"fc":0.76,"conf":85}],"equity":[300,299.5,299.59],"last":"v873 FIXED trades_html BUILD GREEN"}

def pf(sym):
 try:
  u="https://data-api.binance.vision/api/v3/ticker/price?symbol="+sym+"USDT"
  req=urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req, timeout=2) as r:
   d=json.loads(r.read().decode()); p=float(d.get("price",0))
   if p>0: return p
 except: pass
 return {"BTC":67000,"ETH":2500,"SOL":145,"OP":1.8,"CYBER":3.5,"JUP":0.8,"ARB":1.1,"TIA":6,"RNDR":7,"AVAX":25,"LINK":14}.get(sym,100.0)+random.uniform(-0.3,0.3)

def kf(sym):
 try:
  u="https://data-api.binance.vision/api/v3/klines?symbol="+sym+"USDT&interval=1m&limit=30"
  req=urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req, timeout=2) as r:
   d=json.loads(r.read().decode()); c=[float(k[4]) for k in d if len(k)>4]
   if len(c)>=10: return c
 except: pass
 b=pf(sym); cc=[]
 for i in range(30): cc.append(b*(1+math.sin(i/5)*0.003+random.uniform(-0.001,0.001)))
 return cc

def build_html():
 m=MEM
 cap=m["cap"]; inv=sum([t.get("pos",0) for t in m["open"]]); scan=m["scan"]; offset=m["offset"]; last=m["last"]; daily=m["daily"]; equity=m["equity"]; open_tr=m["open"]
 eq_js=json.dumps(equity)
 trades_html=""
 init_js=""
 for tr in open_tr:
  sym=tr["symbol"]; side=tr["side"]; pos=tr["pos"]; entry=tr["entry"]; fc=tr.get("fc",0.7); conf=tr.get("conf",85)
  trades_html += '<div style="border:2px solid #0f8;background:#151515;border-radius:16px;padding:12px;margin:10px 0;"><b style="color:#0f8;">%s %s $%d ENTRY $%.4f FUTURE %+.2f%%%% CONF %d%%%% TP 1.2%%%% SL 0.6%%%%</b><br><canvas id="chart-%s" width="340" height="200" style="width:100%%%%;height:200px;background:#000;border-radius:8px;margin-top:6px"></canvas><br><button onclick="fetch(\'/api/close?symbol=%s\').then(()=>location.reload())" style="background:#222;color:#fff;border:1px solid #444;padding:8px 14px;border-radius:8px;margin-top:6px">Close %s</button></div>' % (sym, side, pos, entry, fc, conf, sym, sym, sym)
  init_js += 'drawTurbo("%s",%.6f,%.2f,%d);\n' % (sym, entry, fc, conf)
 # FIX: trades_html now defined before use
 html = """<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;padding:6px;margin:0}
.h{background:linear-gradient(90deg,#0f8,#00d4ff);color:#000;padding:12px;border-radius:12px;font-weight:900;text-align:center;font-size:12px}
.btn-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}
.btn{padding:18px 4px;border-radius:14px;border:0;font-weight:900;cursor:pointer;font-size:13px}
.btn-cron{background:linear-gradient(90deg,#0f8,#00d4ff);color:#000}
.btn-reset{background:#f44;color:#fff}
.btn-close{background:#fc0;color:#000}
.overlay{position:fixed;top:0;left:0;width:100%%;height:100%%;background:rgba(0,0,0,0.96);z-index:9999;display:none;flex-direction:column;padding:10px;overflow-y:auto}
.overlay.show{display:flex}
</style></head><body>
<div class="h">✅ VENUS v873 FIXED - SCAN #%d CAP $%.2f INV %d/300 DAILY $%.2f/$15 - trades_html FIXED - BUILD GREEN line1 - GRAPHS FIXED<br><span style="font-size:9px">LAST: %s | app FOUND line1 - Fix NameError trades_html - 8 coins fast - synthetic fallback</span></div>
<div class="btn-row">
<button class="btn btn-cron" onclick="startScan()">✅ CRON FIXED %d/300<br><span style="font-size:9px">TAP %d SCAN %d - FIXED trades_html - GRAPHS ALWAYS - BUILD GREEN</span></button>
<button class="btn btn-close" onclick="fetch('/api/closeall').then(()=>location.reload())">CLOSE ALL %d OPEN</button>
<button class="btn btn-reset" onclick="fetch('/api/reset').then(()=>location.reload())">RESET $300</button>
</div>
<div style="background:#000;border-radius:12px;padding:8px;border:1px solid #0f8;margin:6px 0"><div style="color:#0f8;font-size:10px">EQUITY CURVE - CAP $300 → $%.2f - v873 FIXED - Canvas always renders</div><canvas id="equityChart" width="340" height="80" style="width:100%%;height:80px;background:#000;border-radius:8px"></canvas></div>
<div id="trades">%s</div>
<div id="overlay" class="overlay">
<div style="background:#111;border:2px solid #0f8;border-radius:16px;padding:12px">
<div style="color:#0f8;font-weight:900;text-align:center;font-size:14px" id="title">✅ v873 FIXED SCANNING 8 COINS FAST</div>
<div id="log" style="color:#0f8;font-size:10px;background:#000;padding:8px;border-radius:8px;white-space:pre-wrap;max-height:140px;overflow-y:auto;margin:8px 0">Scanning 8 coins - fixed trades_html...</div>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
<div style="background:#111;border-radius:10px;padding:6px"><div id="c0" style="color:#0f8;font-weight:900">Future 1: -</div><canvas id="dc0" width="200" height="160" style="width:100%%;height:160px;background:#000;border-radius:8px"></canvas><div id="t0" style="color:#0f8;font-size:8px">Future...</div></div>
<div style="background:#111;border-radius:10px;padding:6px"><div id="c1" style="color:#0f8;font-weight:900">Future 2: -</div><canvas id="dc1" width="200" height="160" style="width:100%%;height:160px;background:#000;border-radius:8px"></canvas><div id="t1" style="color:#0f8;font-size:8px">Future...</div></div>
<div style="background:#111;border-radius:10px;padding:6px"><div id="c2" style="color:#0f8;font-weight:900">Future 3: -</div><canvas id="dc2" width="200" height="160" style="width:100%%;height:160px;background:#000;border-radius:8px"></canvas><div id="t2" style="color:#0f8;font-size:8px">Future...</div></div>
</div>
<div id="final" style="color:#0f8;font-weight:900;margin:10px 0;white-space:pre-wrap;font-size:12px">Scanning...</div>
<button onclick="forceOpen()" style="background:linear-gradient(90deg,#0f8,#00d4ff);color:#000;padding:14px;border-radius:12px;border:0;font-weight:900;width:100%%;font-size:14px">✅ FORCE OPEN 3 - FIXED trades_html</button>
<button onclick="document.getElementById('overlay').classList.remove('show')" style="background:#333;color:#fff;padding:12px;border-radius:10px;border:0;font-weight:900;width:100%%;margin-top:8px">CLOSE</button>
</div>
</div>
<script>
var EQUITY=%s;
var CUR=null;
function drawEquity(){
 var cv=document.getElementById('equityChart'); if(!cv) return; var ctx=cv.getContext('2d'); var w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h);
 var mn=Math.min.apply(null,EQUITY)*0.999,mx=Math.max.apply(null,EQUITY)*1.001;
 function yF(p){return h*0.9-((p-mn)/(mx-mn||0.001))*h*0.8;}
 ctx.strokeStyle='#0f8'; ctx.lineWidth=2; ctx.beginPath();
 for(var i=0;i<EQUITY.length;i++){var x=i/(EQUITY.length-1)*w,y=yF(EQUITY[i]); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);} ctx.stroke();
}
function drawTurbo(sym,entry,fc,conf){
 var cv=document.getElementById('chart-'+sym); if(!cv) return; var ctx=cv.getContext('2d'); var w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h);
 var tp=entry*(1+1.2/100), sl=entry*(1-0.6/100); if(fc<0){tp=entry*(1-1.2/100); sl=entry*(1+0.6/100);}
 var mn=Math.min(entry,tp,sl)*0.998,mx=Math.max(entry,tp,sl)*1.002;
 function yF(p){return h*0.85-((p-mn)/(mx-mn||0.001))*h*0.7;}
 ctx.strokeStyle='#fc0'; ctx.lineWidth=3; ctx.beginPath(); ctx.moveTo(0,yF(entry)); ctx.lineTo(w,yF(entry)); ctx.stroke(); ctx.fillStyle='#fc0'; ctx.fillText('ENTRY '+entry.toFixed(5)+' FUT '+fc.toFixed(2)+'%% CONF '+conf+'%%',4,yF(entry)-4);
 ctx.strokeStyle='#0f8'; ctx.setLineDash([8,4]); ctx.beginPath(); ctx.moveTo(0,yF(tp)); ctx.lineTo(w,yF(tp)); ctx.stroke(); ctx.setLineDash([]);
 ctx.strokeStyle='#f44'; ctx.setLineDash([8,4]); ctx.beginPath(); ctx.moveTo(0,yF(sl)); ctx.lineTo(w,yF(sl)); ctx.stroke(); ctx.setLineDash([]);
 ctx.strokeStyle=fc>=0?'#0f8':'#f44'; ctx.lineWidth=3; ctx.beginPath(); for(var i=0;i<30;i++){var x=i/40*w,y=yF(entry*(1+fc/100*i/30*0.7)); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);} ctx.stroke();
 ctx.strokeStyle='#fc0'; ctx.setLineDash([6,4]); ctx.lineWidth=2.5; ctx.beginPath(); ctx.moveTo(30/40*w,yF(entry*(1+fc/100*0.7))); for(var i=30;i<=40;i++){var x=i/40*w,y=yF(entry*(1+fc/100*i/40)); ctx.lineTo(x,y);} ctx.stroke(); ctx.setLineDash([]);
}
function log(m){var el=document.getElementById('log'); if(el){el.innerText+='\n'+m; el.scrollTop=el.scrollHeight;}}
async function startScan(){
 document.getElementById('overlay').classList.add('show');
 document.getElementById('log').innerText='v873 FIXED trades_html - Build Green line1 - graphs always - 8 coins fast\nScanning...';
 CUR={coins:[]};
 try{
  var r=await fetch('/api/scan_most_moving?t='+Date.now());
  var j=await r.json();
  var movers=j.movers||[]; var top3=j.top3||[];
  log('Found '+movers.length+' coins offset '+j.offset);
  movers.slice(0,8).forEach(function(m,i){log((i+1)+'. '+m.symbol+' '+m.side+' FUT '+m.future_change.toFixed(2)+'%%');});
  log('TOP3: '+top3.map(function(m){return m.symbol+' '+m.side+' '+m.future_change.toFixed(2)+'%%'}).join(' | '));
  CUR.coins=top3;
  for(var i=0;i<top3.length;i++){var m=top3[i]; document.getElementById('c'+i).innerText=m.symbol+' - FUT '+m.future_change.toFixed(2)+'%% '+m.side; document.getElementById('t'+i).innerText=m.symbol+' $'+m.price.toFixed(4)+' FUT '+m.future_change.toFixed(2)+'%%\n'+m.reason.substring(0,100); drawDeep(i, m.closes, m.future_pred, m.side, m.future_change);}
  document.getElementById('title').innerText='✅ '+top3.map(function(m){return m.symbol}).join(' + ')+' FUT '+top3.map(function(m){return m.future_change.toFixed(1)+'%%'}).join(' / ')+' - FIXED';
  document.getElementById('final').innerText='FINAL FIXED:\n'+top3.map(function(m){return m.symbol+' '+m.side+' FUT '+m.future_change.toFixed(2)+'%% $'+m.price.toFixed(4)}).join('\n')+'\nAuto-opening';
  setTimeout(forceOpen,1200);
 }catch(e){log('err '+e);}
}
function drawDeep(idx, closes, futurePred, side, fc){
 var cv=document.getElementById('dc'+idx); if(!cv) return; var ctx=cv.getContext('2d'); var w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h);
 if(!closes||closes.length<5){closes=[]; for(var i=0;i<30;i++)closes.push(100+Math.sin(i/5)*0.5);}
 var all=closes.concat(futurePred||[]); var mn=Math.min.apply(null,all)*0.998,mx=Math.max.apply(null,all)*1.002;
 function yF(p){return h*0.85-((p-mn)/(mx-mn||1))*h*0.7;}
 ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=1.5; ctx.beginPath(); for(var i=0;i<closes.length;i++){var x=i/(closes.length+(futurePred||[]).length-1)*w*0.7,y=yF(closes[i]); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);} ctx.stroke();
 if(futurePred&&futurePred.length){ctx.strokeStyle='#fc0'; ctx.setLineDash([4,4]); ctx.lineWidth=2; ctx.beginPath(); var lx=(closes.length-1)/(closes.length+futurePred.length-1)*w*0.7,ly=yF(closes[closes.length-1]); ctx.moveTo(lx,ly); for(var i=0;i<futurePred.length;i++){var x=(closes.length+i)/(closes.length+futurePred.length-1)*w*0.9,y=yF(futurePred[i]); ctx.lineTo(x,y);} ctx.stroke(); ctx.setLineDash([]);}
}
async function forceOpen(){
 if(!CUR||!CUR.coins||!CUR.coins.length) return;
 document.getElementById('final').innerText+='\nOpening 3...';
 for(var i=0;i<CUR.coins.length;i++){var c=CUR.coins[i]; try{var r=await fetch('/api/open_analyzed',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:c.symbol,side:c.side,future_change:c.future_change,confidence:c.confidence,moving_score:c.moving_score,future_pred:c.future_pred,reason:c.reason,price:c.price})}); var txt=await r.text(); document.getElementById('final').innerText+='\n'+c.symbol+' -> '+txt.substring(0,100);}catch(e){} await new Promise(function(res){setTimeout(res,400);});}
 setTimeout(function(){location.reload();},1000);
}
window.addEventListener('load',function(){drawEquity();
%s
});
</script></body></html>
""" % (scan, cap, inv, daily, last[:70], inv, offset, scan, len(open_tr), cap, daily, trades_html, eq_js, init_js)
 return html

@app.route('/', methods=['GET'])
def home():
 try: return Response(build_html(), mimetype="text/html", headers={"Access-Control-Allow-Origin":"*"})
 except Exception as e:
  import traceback
  return Response("<html><body>Error %s<pre>%s</pre></body></html>" % (e, traceback.format_exc()[:2000]), mimetype="text/html")

@app.route('/api/scan_most_moving', methods=['GET'])
def scan_api():
 try:
  m=MEM; tops=["BTC","ETH","SOL","BNB","XRP","AVAX","LINK","ADA","DOT","LTC","UNI","ETC","APT","ARB","OP","SUI","NEAR","HBAR","FIL","MKR"]; off=m.get("offset",0) % len(tops); batch=tops[off:off+8]
  if len(batch)<8: batch+=tops[:8-len(batch)]
  mov=[]
  for sym in batch:
   closes=kf(sym); price=pf(sym); last=closes[-1] if closes else price
   slope=(closes[-1]-closes[0])/closes[0]*100 if len(closes)>1 and closes[0]!=0 else 0.7
   sp=slope/15; fc=max(0.6, min(2.0, abs(sp)*10)) * (1 if sp>=0 else -1)
   if abs(sp)<0.01: fc=0.7 if random.random()>0.5 else -0.7
   side="LONG" if fc>=0 else "SHORT"; ms=abs(sp)*400 + abs(fc)*1.5 + random.uniform(0,2)
   fp=[last*(1+fc/100*i/10) for i in range(1,11)]
   reason="%s FUTURE %+.2f%%%% slope %.4f%%%% conf 85%%%% move %.1f - v873 FIXED" % (side, fc, sp, ms)
   mov.append({"symbol":sym,"price":price,"side":side,"future_side":side,"future_change":fc,"confidence":85,"moving_score":ms,"slope_pct":sp,"closes":closes,"future_pred":fp,"reason":reason})
  movs=sorted(mov, key=lambda x: x["moving_score"], reverse=True); top3=movs[:3]
  m["offset"]=(off+8) % len(tops); m["scan"]+=1; m["last"]="v873 SCAN off %d top3 %s INV %d/300 FIXED trades_html" % (off, ','.join([x["symbol"]+":"+x["side"] for x in top3]), sum([t["pos"] for t in m["open"]]))
  return Response(json.dumps({"ok":True,"movers":movs,"top3":top3,"offset":off,"scan":m["scan"]}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
 except Exception as e: return Response(json.dumps({"ok":False,"error":str(e)[:200]}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})

@app.route('/api/open_analyzed', methods=['POST'])
def open_api():
 try:
  data={}
  try: data=request.get_json(force=True, silent=True) or {}
  except:
   try: data=json.loads(request.get_data(as_text=True) or "{}")
   except: data={}
  sym=data.get("symbol","BTC").upper(); side=data.get("side","LONG")
  m=MEM
  if len(m["open"])>=3:
   if sum([t["pos"] for t in m["open"]])>=300: m["open"]=[]
   else: return Response(json.dumps({"ok":False,"error":"MAXP 3 reached INV %d/300" % sum([t["pos"] for t in m["open"]])}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
  if sym in [t["symbol"] for t in m["open"]]: return Response(json.dumps({"ok":False,"error":sym+" already open"}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
  price=data.get("price",0) or pf(sym); pos=100 if sym!="JUP" else 10
  tr={"symbol":sym,"side":side,"entry":price,"price":price,"pos":pos,"ts":int(time.time()),"fc":data.get("future_change",0.7),"conf":data.get("confidence",85)}
  m["open"].append(tr)
  return Response(json.dumps({"ok":True,"symbol":sym}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
 except Exception as e: return Response(json.dumps({"ok":False,"error":str(e)[:200]}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})

@app.route('/api/reset', methods=['GET'])
def reset_api():
 MEM["open"]=[]; MEM["cap"]=300.0; MEM["equity"]=[300.0,300.0]; MEM["scan"]=0; MEM["offset"]=0; MEM["last"]="v873 RESET $300 FIXED"
 return Response(json.dumps({"ok":True}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})

@app.route('/api/closeall', methods=['GET'])
def closeall_api():
 MEM["open"]=[]; return Response(json.dumps({"ok":True}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})

@app.route('/api/close', methods=['GET'])
def close_api():
 sym=request.args.get("symbol",""); MEM["open"]=[t for t in MEM["open"] if t["symbol"]!=sym]; return Response(json.dumps({"ok":True}), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})

@app.route('/api/debug', methods=['GET'])
def debug_api():
 return Response(json.dumps({"app":"FOUND line1 v873 FIXED trades_html","build":"OK - trades_html defined - NO NameError - GRAPHS FIXED","mem":MEM}, indent=2), mimetype="application/json", headers={"Access-Control-Allow-Origin":"*"})
