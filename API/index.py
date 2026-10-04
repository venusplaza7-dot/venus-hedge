from flask import Flask
import json, time, os, requests
from datetime import datetime
app = Flask(__name__)
try:
    from upstash_redis import Redis
    url = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or ""
    token = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
    if not token:
        for k,v in os.environ.items():
            if "TOKEN" in k.upper():
                token=v; break
    db = Redis(url=url, token=token) if url and token else Redis.from_env()
    def load(k,d):
        try:
            v=db.get(k)
            return json.loads(v) if v else d
        except:
            return d
    def save(k,v):
        try:
            db.set(k, json.dumps(v))
        except:
            pass
    KV=True
except:
    M={}
    def load(k,d):
        return M.get(k,d)
    def save(k,v):
        M[k]=v
    KV=False
def get_prices():
    out={}
    coins=["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT","LINKUSDT","AVAXUSDT","ADAUSDT","XRPUSDT"]
    try:
        r=requests.get("https://api.binance.com/api/v3/ticker/price",timeout=3)
        if r.status_code==200:
            for d in r.json():
                if d['symbol'] in coins:
                    out[d['symbol']]=float(d['price'])
    except:
        pass
    return out
@app.route('/api/cron')
def cron():
    try:
        o=load('OPEN',[]); cl=load('CLOSED',[]); cap=load('CAP',1000.0); tot=load('TOT',0); wins=load('WINS',0); ticks=load('TICKS',{}); now=time.time()
        prices=get_prices()
        if len(prices)<2:
            return {"ok":False}
        for s,p in prices.items():
            if s not in ticks:
                ticks[s]=[]
            ticks[s].append(p)
            ticks[s]=ticks[s][-60:]
        save('TICKS',ticks)
        nw=[]; cn=[]; fee=load('FEE',0.0)
        for t in o:
            sym=t['symbol']; entry=t['entry']; tm=t['mode']; entry_t=t['t']; pos=t.get('pos',200.0)
            real=prices.get(sym)
            if not real:
                nw.append(t); continue
            age=now-entry_t
            pct=((real-entry)/entry*100) if tm=="LONG" else ((entry-real)/entry*100)
            gross=pos*pct/100; fee_fut=pos*0.0004; net_fut=gross-fee_fut
            tk=ticks.get(sym,[])
            tr=[abs(tk[i]-tk[i-1])/tk[i-1]*100 for i in range(1,len(tk))] if len(tk)>1 else [0.02]
            atr=sum(tr[-6:])/6 if len(tr)>=6 else 0.02
            target=0.20 if atr>0.025 else 0.12
            cut=max(0.10, atr*1.5)
            should=False; reason=""; peak=t.get('peak',pct)
            if pct>peak:
                t['peak']=pct
            if pct>=target:
                should=True; reason=f"WIN 30SEC $1 {pct:.3f}% target {target:.3f}% net ${net_fut:.2f}"
            elif peak>=target and pct<peak*0.40:
                should=True; reason=f"TRAIL {peak:.2f}%->{pct:.2f}%"
            elif pct<=-cut:
                should=True; reason=f"CUT {pct:.3f}%"
            if age>35 and pct>=0.09:
                should=True; reason=f"MAX 35s {pct:.3f}%"
            if age>75:
                should=True; reason=f"MAX 75s {pct:.3f}%"
            if should:
                if net_fut>0.08:
                    res="WIN"
                elif net_fut<-0.08:
                    res="LOSS"
                else:
                    res="SCRATCH" if age>=60 else None
                if res is None:
                    nw.append(t); continue
                if res!="SCRATCH":
                    fee+=fee_fut; cap+=net_fut; tot+=1
                    if res=="WIN":
                        wins+=1
                cn.append({'symbol':sym,'entry':entry,'net':round(net_fut,2) if res!="SCRATCH" else 0.0,'gross':round(gross,3),'result':res,'time':datetime.now().strftime("%H:%M:%S"),'hold':int(age),'pct':round(pct,4),'mode':tm,'price':real,'reason':reason,'pos':pos,'cap':round(cap,2)})
            else:
                if pct>t.get('peak',-999):
                    t['peak']=pct
                nw.append(t)
        for c in cn:
            cl.insert(0,c)
        cl=cl[:100]; o=nw
        cands=[]
        for s in prices.keys():
            if s in [x['symbol'] for x in o]:
                continue
            if s not in ticks or len(ticks[s])<5:
                continue
            tk=ticks[s]
            tr=[abs(tk[i]-tk[i-1])/tk[i-1]*100 for i in range(1,len(tk))] if len(tk)>1 else [0.01]
            atr=sum(tr[-5:])/5 if len(tr)>=5 else 0.005
            if atr<0.006:
                continue
            vwap=sum(tk[-10:])/10 if len(tk)>=10 else prices[s]
            dev=(prices[s]-vwap)/vwap*100 if vwap>0 else 0
            if abs(dev)<0.04:
                continue
            mode="SHORT" if dev>0 else "LONG"
            speed=atr*3 + abs(dev)
            cands.append((s,speed,atr,dev,mode))
        cands.sort(key=lambda x:x[1], reverse=True)
        max_open=5
        pos_each=round(min(200, max(150, cap/max_open)),1)
        for sym,speed,atr,dev,mode in cands[:max_open-len(o)]:
            o.append({'symbol':sym,'entry':prices[sym],'t':now,'mode':mode,'price':prices[sym],'peak':0,'pos':pos_each})
        save('OPEN',o); save('CLOSED',cl); save('CAP',cap); save('TOT',tot); save('WINS',wins); save('FEE',fee)
        return {"ok":True,"open":len(o),"cap":cap}
    except Exception as e:
        return {"ok":False,"err":str(e)[:120]}
@app.route('/api/state')
def state():
    return {"open":load('OPEN',[]),"closed":load('CLOSED',[]),"cap":load('CAP',1000.0),"total":load('TOT',0),"wins":load('WINS',0)}
@app.route('/')
def home():
    html = """
<html><head><meta name=viewport content="width=device-width,initial-scale=1">
<style>
body{background:#0d0d0d;color:#fff;font-family:system-ui;padding:16px}
.card{background:#1a1a1a;border:1px solid #333;border-radius:16px;padding:16px;margin:12px 0}
.btn{background:#00ff88;color:#000;border:0;padding:14px;border-radius:12px;font-weight:800;width:100%}
.k{background:#00331a;border:2px solid #00ff88}
.win{color:#00ff88}.loss{color:#ff4444}.m{color:#888;font-size:11px}
</style></head><body>
<h2>VENUS FINAL - 30SEC 5 COINS $1 PER TRADE</h2>
<div class="card k">
CAP $<span id=cap>1000</span> | WR <span id=wr>0%</span> | <span id=tot>0</span> | Open <span id=oc>0/5</span><br>
<span class=m>5 coins x $200 = $1000 every 30sec = 10 trades/min = $3.20/min = $192/hour = $1 per trade quick when $500 pos</span><br><br>
<button class=btn onclick="fetch('/api/cron').then(r=>r.json()).then(()=>load())">FORCE 30SEC 5 COINS $1</button>
</div>
<div class="card"><b>Open <span id=oc2>0/5</span></b><div id=open>Waiting</div></div>
<div class="card"><b>Closed</b><div id=closed>Waiting</div></div>
<div class="card m">
5 coins x $200 = $1000 total every 30sec = 10 trades/min<br>
$200 pos fee $0.08 target 0.20% gross $0.40 net $0.32 x10 = $3.20/min = $192/hour paper<br>
$500 pos 2 coins rotating 5 coins = 4 trades/min x $0.80 = $3.20/min = $1 per trade
</div>
<script>
async function load(){
 try{
  let r=await fetch('/api/state'); let j=await r.json();
  document.getElementById('cap').innerText=(j.cap||1000).toFixed(2);
  document.getElementById('oc').innerText=(j.open||[]).length+'/5';
  document.getElementById('oc2').innerText=(j.open||[]).length+'/5';
  let wr=j.total?Math.round(j.wins/j.total*100):0;
  document.getElementById('wr').innerText=wr+'%';
  document.getElementById('tot').innerText=j.wins+'W of '+j.total;
  document.getElementById('open').innerHTML=j.open.map(t=>'<div>'+t.mode+' '+t.symbol+' $'+t.pos+' '+Math.floor(Date.now()/1000 - t.t)+'s</div>').join('')||'Waiting';
  document.getElementById('closed').innerHTML=j.closed.map(c=>'<div>'+c.time+' '+c.mode+' '+c.symbol+' '+c.pct+'% net $'+c.net+' '+c.result+' '+c.reason+'</div>').join('')||'Waiting';
 }catch(e){}
}
setInterval(load,2500); load(); setInterval(()=>{fetch('/api/cron')},3000);
</script></body></html>
"""
    return html
