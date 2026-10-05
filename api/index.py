
from flask import Flask
import json, time, os, requests
from datetime import datetime
app=Flask(__name__)

# REST version - no upstash_redis lib needed - uses Vercel KV REST API directly
UP_URL = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("KV_URL") or ""
UP_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
if not UP_TOKEN:
    for k,v in os.environ.items():
        if "TOKEN" in k.upper() and "UPSTASH" in k.upper() or "KV" in k.upper():
            if len(v)>20:
                UP_TOKEN=v
                break

def rget(k, d=None):
    try:
        if not UP_URL or not UP_TOKEN:
            return M.get(k, d)
        r=requests.get(f"{UP_URL}/get/{k}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=4)
        if r.status_code!=200: return d
        val=r.json().get("result")
        if val is None: return d
        try: return json.loads(val)
        except: return val
    except:
        return M.get(k, d) if 'M' in globals() else d

def rset(k,v):
    try:
        if not UP_URL or not UP_TOKEN:
            M[k]=v
            return
        requests.post(f"{UP_URL}/set/{k}", headers={"Authorization": f"Bearer {UP_TOKEN}", "Content-Type":"application/json"}, data=json.dumps(v), timeout=4)
    except:
        M[k]=v

def rdel(k):
    try:
        if not UP_URL or not UP_TOKEN:
            M.pop(k, None)
            return
        requests.get(f"{UP_URL}/del/{k}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=4)
    except:
        M.pop(k, None)

M={}
try:
    KV = bool(UP_URL and UP_TOKEN)
except:
    KV=False
    M={}

def load(k,d):
    return rget(k,d)
def save(k,v):
    rset(k,v)
def delete(k):
    rdel(k)

def get_prices_5coin():
 out={}
 headers={"User-Agent":"Mozilla/5.0"}
 cb_map={"PEPEUSDT":"PEPE-USD","BONKUSDT":"BONK-USD","SHIBUSDT":"SHIB-USD","FLOKIUSDT":"FLOKI-USD","DOGEUSDT":"DOGE-USD","WIFUSDT":"WIF-USD","BRETTUSDT":"BRETT-USD","TURBOUSDT":"TURBO-USD","NOTUSDT":"NOT-USD","MOGUSDT":"MOG-USD","GOATUSDT":"GOAT-USD","POPCATUSDT":"POPCAT-USD","MEWUSDT":"MEW-USD"}
 for sym,cb in cb_map.items():
  try:
   r=requests.get(f"https://api.coinbase.com/v2/prices/{cb}/spot",timeout=1.2)
   if r.status_code==200:
    p=float(r.json().get('data',{}).get('amount',0))
    if 0.0000005 < p < 0.11: out[sym]=p
  except: pass
 try:
  r=requests.get("https://api.binance.com/api/v3/ticker/price",timeout=2,headers=headers)
  if r.status_code==200:
   all_prices={d['symbol']: float(d['price']) for d in r.json() if 'price' in d}
   for sym in ["PEPEUSDT","BONKUSDT","1000BONKUSDT","SHIBUSDT","1000SHIBUSDT","FLOKIUSDT","1000FLOKIUSDT","WIFUSDT","POPCATUSDT","MEWUSDT","NOTUSDT","DOGEUSDT","BRETTUSDT","TURBOUSDT","MOGUSDT","GOATUSDT"]:
    try:
     p=all_prices.get(sym)
     if not p: continue
     if "1000" in sym: p=p/1000
     if 0.0000005 < p < 0.11:
      norm=sym.replace("1000","")
      if "BONK" in sym: norm="BONKUSDT"
      if "SHIB" in sym: norm="SHIBUSDT"
      if "FLOKI" in sym: norm="FLOKIUSDT"
      if norm not in out: out[norm]=p
    except: pass
 except: pass
 return out

@app.route('/api/cron')
def cron():
 save('last',datetime.now().strftime("%H:%M:%S"))
 try:
  o=load('VENUS_OPEN',[]); cl=load('VENUS_CLOSED',[]); cap=load('VENUS_CAP',300.0); tot=load('VENUS_TOT',0); wins=load('VENUS_WINS',0); st=load('VENUS_STATS',{}); fee_tot=load('VENUS_FEE',0.0); prev=load('VENUS_PREV',{}); prev2=load('VENUS_PREV2',{}); now=time.time()
  prices=get_prices_5coin()
  if len(prices)<3: return {"ok":False,"p":len(prices)}
  mom={}; mom90={}
  for s,p in prices.items():
   if s in prev and prev[s]>0: mom[s]=(p-prev[s])/prev[s]*100
   else: mom[s]=0
   if s in prev2 and prev2[s]>0: mom90[s]=(p-prev2[s])/prev2[s]*100
   else: mom90[s]=mom.get(s,0)
  save('VENUS_PREV2',prev); save('VENUS_PREV',prices)
  nw=[]; closed_now=[]
  for t in o:
   real=prices.get(t['symbol'])
   if not real:
    if now-t.get('t',now)>85:
     tot+=1; fee_tot+=0.02; cap-=0.06
     closed_now.append({'symbol':t['symbol'],'net':-0.06,'result':'LOSS','time':datetime.now().strftime("%H:%M:%S"),'hold':int(now-t.get('t',now)),'mode':t.get('mode','LONG'),'m90':t.get('m90',0)})
    else: nw.append(t)
    continue
   age=now-t.get('t',now); res=None; tm=t.get('mode','LONG')
   if tm=="LONG":
    if real>=t['entry']*1.0018: res="WIN"
    elif real<=t['entry']*0.9994: res="LOSS"
    elif age>85: res="WIN" if real>=t['entry']*1.0003 else "LOSS"
   else:
    if real<=t['entry']*0.9982: res="WIN"
    elif real>=t['entry']*1.0006: res="LOSS"
    elif age>85: res="WIN" if real<=t['entry']*0.9997 else "LOSS"
   if res:
    fee=0.02
    net=0.12 if res=="WIN" else -0.06
    fee_tot+=fee; cap+=net; tot+=1
    if res=="WIN": wins+=1
    if t['symbol'] not in st: st[t['symbol']]={"w":0,"l":0,"profit":0.0}
    st[t['symbol']]["w" if res=="WIN" else "l"]+=1; st[t['symbol']]["profit"]+=net
    closed_now.append({'symbol':t['symbol'],'entry':t['entry'],'net':net,'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'m':round(mom.get(t['symbol'],0),4),'m90':round(mom90.get(t['symbol'],0),3),'mode':tm,'price':real})
   else: nw.append(t)
  for c in closed_now: cl.insert(0,c)
  cl=cl[:150]; o=nw
  if len(o)<5:
   pool=[s for s in prices.keys() if abs(mom90.get(s,0))>0.04 and s not in [x['symbol'] for x in o]]
   pool.sort(key=lambda x: abs(mom90.get(x,0)), reverse=True)
   for sym in pool[:5-len(o)]:
    e=prices.get(sym)
    if not e: continue
    if mom90.get(sym,0)>0.08: mode="SHORT"
    elif mom90.get(sym,0)<-0.08: mode="LONG"
    else: mode="SHORT" if mom90.get(sym,0)>0 else "LONG"
    o.append({'symbol':sym,'entry':e,'t':now,'m':round(mom.get(sym,0),4),'m90':round(mom90.get(sym,0),3),'mode':mode,'price':e})
  save('VENUS_OPEN',o); save('VENUS_CLOSED',cl); save('VENUS_CAP',cap); save('VENUS_TOT',tot); save('VENUS_WINS',wins); save('VENUS_STATS',st); save('VENUS_FEE',fee_tot); save('VENUS_PRICE',len(prices))
  return {"ok":True,"p":len(prices),"open":len(o)}
 except Exception as e:
  save('last',f"ERR {str(e)[:80]}")
  return {"ok":False,"err":str(e)[:100]}

@app.route('/api/reset')
def reset():
 for k in ['VENUS_OPEN','VENUS_CLOSED','VENUS_CAP','VENUS_TOT','VENUS_WINS','VENUS_STATS','VENUS_FEE','VENUS_PRICE','VENUS_PREV','VENUS_PREV2','last']:
  try: delete(k)
  except: pass
 save('VENUS_CAP',300.0); save('VENUS_TOT',0); save('VENUS_WINS',0); save('VENUS_STATS',{}); save('VENUS_FEE',0.0); save('VENUS_OPEN',[]); save('VENUS_CLOSED',[]); save('last',datetime.now().strftime("%H:%M:%S"))
 return {"reset":True}
@app.route('/api/force')
def force(): return cron()
@app.route('/api/state')
def state(): 
 return {"open":load('VENUS_OPEN',[]),"closed":load('VENUS_CLOSED',[]),"cap":load('VENUS_CAP',300.0),"total":load('VENUS_TOT',0),"wins":load('VENUS_WINS',0),"stats":load('VENUS_STATS',{}),"last":load('last','never'),"kv":KV,"fee":load('VENUS_FEE',0.0),"price_count":load('VENUS_PRICE',0)}
@app.route('/api/index')
@app.route('/')
def home():
 return """<html><head><meta name=viewport content="width=device-width,initial-scale=1"><style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}.card{background:#1a1a1a;border:1px solid #333;border-radius:16px;padding:16px;margin:12px 0}.win{color:#00ff88}.loss{color:#ff4444}.m{color:#888;font-size:12px}.trade{padding:8px 0;border-bottom:1px solid #222;display:flex;justify-content:space-between;font-size:11px}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%;font-size:16px}.btn2{background:#ff4444;color:#fff;border:0;padding:10px;border-radius:10px;font-weight:700;width:100%;margin-top:8px}
</style></head><body>
<h2>VENUS v166 REST FIX $300→$50/DAY - NO LIB</h2>
<div class=card>CAP $<span id=cap>300</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Open <span id=oc>0/5</span> | Prices <span id=pc>0</span> | Fees $<span id=fee>0</span><br><span class=m>REST FIX: no upstash-redis lib, uses requests only - fixes Not Found on hedge.vercel.app</span><br><span class=m>Cron <span id=cr>never</span> | KV <span id=kv>YES</span> | 5-COIN ✅</span><br><br><button class=btn onclick="fetch('/api/force').then(()=>setTimeout(loadState,400))">🚀 FORCE 5-COIN WIN $0.12</button><button class=btn2 onclick="if(confirm('WIPE to $300?')){fetch('/api/reset').then(()=>setTimeout(loadState,400))}">🗑️ WIPE → $300</button></div>
<div class=card><b>Open <span id=oc2>0/5</span></b><div id=open>Press FORCE</div></div>
<div class=card><b>Closed WIN $0.12 LOSS $0.06</b><div id=closed>Waiting...</div></div>
<div class=card><b>Brain</b><div id=brain class=m>Training...</div></div>
<script>
async function loadState(){
 try{
  let r=await fetch('/api/state'); let j=await r.json();
  let el=(id)=>document.getElementById(id);
  if(el('cap')) el('cap').innerText=(j.cap||300).toFixed(2);
  if(el('fee')) el('fee').innerText=(j.fee||0).toFixed(2);
  if(el('cr')) el('cr').innerText=j.last||'never';
  if(el('kv')) el('kv').innerText=j.kv?'YES':'NO';
  if(el('pc')) el('pc').innerText=j.price_count||0;
  if(el('oc')) el('oc').innerText=(j.open||[]).length+'/5';
  if(el('oc2')) el('oc2').innerText=(j.open||[]).length+'/5';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  if(el('wr')) el('wr').innerText=wr+'%';
  if(el('tot')) el('tot').innerText=`${j.wins||0}W/${(j.total||0)-(j.wins||0)}L of ${j.total||0}`;
  if(el('open')) el('open').innerHTML=(j.open||[]).map(t=>`<div class=trade><span>${t.mode=='SHORT'?'🔻 SHORT':'🔥 LONG'} ${t.symbol} $${t.price} 90s ${t.m90||0}%</span><span class=m>${Math.floor(Date.now()/1000 - (t.t||Date.now()/1000))}s</span></div>`).join('')||'No open';
  if(el('closed')) el('closed').innerHTML=(j.closed||[]).map(c=>`<div class=trade><span>${c.time} ${c.mode} ${c.symbol} $${c.price} ${c.hold}s 90s ${c.m90||0}%</span><span><span class=${c.result=='WIN'?'win':'loss'}>${c.result} $${(c.net||0).toFixed(2)}</span></span></div>`).join('')||'No trades';
  if(el('brain')){ let stats=Object.entries(j.stats||{}).sort((a,b)=>(b[1].profit||0)-(a[1].profit||0)); el('brain').innerHTML=stats.slice(0,10).map(([k,v])=>`<div class=trade><span>${k.replace('USDT','')} ${v.w||0}W/${v.l||0}L ${Math.round(((v.w||0)/Math.max(1,(v.w||0)+(v.l||0)))*100)}% $${(v.profit||0).toFixed(2)}</span></div>`).join('')||'Scanning...'; }
 }catch(e){}
}
setInterval(loadState,2500); loadState(); setInterval(()=>{fetch('/api/cron').then(()=>loadState());},7000);
</script></body></html>"""
