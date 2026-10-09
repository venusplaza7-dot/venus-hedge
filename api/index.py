from flask import Flask, jsonify
import os, json, requests, time, random
app = Flask(__name__)

URLS=[]
TOKENS=[]
for k in ["KV_REST_API_URL","KV_URL","UPSTASH_REDIS_REST_URL"]:
    v=os.getenv(k,"").strip().rstrip("/")
    if v and v not in URLS: URLS.append(v)
for k in ["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN","KV_REST_API_READ_ONLY_TOKEN"]:
    v=os.getenv(k,"").strip()
    if v and v not in TOKENS: TOKENS.append(v)
for n in os.environ:
    if "KV" in n and "TOKEN" in n:
        v=os.getenv(n,"").strip()
        if v and v not in TOKENS and len(v)>10: TOKENS.append(v)

KEY="VENUS_V611_TOTAL"
CACHE={"data":None,"ts":0,"last_good":None}

def rget():
    global CACHE
    if CACHE["data"] and time.time()-CACHE["ts"]<8: return CACHE["data"]
    for _ in range(2):
        for url in URLS:
            for tok in TOKENS:
                try:
                    r=requests.get(f"{url}/get/{KEY}",headers={"Authorization":f"Bearer {tok}"},timeout=5)
                    v=r.json().get("result")
                    if v:
                        d=json.loads(v)
                        tot=int(d.get("FUND_WINS",0))+int(d.get("FUND_LOSSES",0))
                        if tot==0 and CACHE.get("last_good") and int(CACHE["last_good"].get("FUND_WINS",0))+int(CACHE["last_good"].get("FUND_LOSSES",0))>0:
                            return CACHE["last_good"]
                        CACHE["data"]=d; CACHE["ts"]=time.time()
                        if tot>0: CACHE["last_good"]=d
                        return d
                except: pass
    if CACHE.get("last_good"): return CACHE["last_good"]
    if CACHE["data"]: return CACHE["data"]
    return {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0.0,"FUND_DAILY_GROSS":0.0,"FUND_DAILY_FEE":0.0,"FAST_WHALE":[],"FAST_LAST":0,"ROTATE_LAST":0,"ROTATE_COINS":[],"REAL_TRADES":[]}

def rset(d):
    global CACHE
    tot=int(d.get("FUND_WINS",0))+int(d.get("FUND_LOSSES",0))
    d["FUND_TOTAL_TRADES"]=tot
    if CACHE.get("last_good"):
        lg=CACHE["last_good"]; lgt=int(lg.get("FUND_WINS",0))+int(lg.get("FUND_LOSSES",0))
        if tot==0 and lgt>0: CACHE["data"]=lg; CACHE["ts"]=time.time(); return
    if tot==0 and float(d.get("FUND_CAP",1000.0))==1000.0 and len(d.get("FUND_CLOSED",[]))==0 and len(d.get("FUND_OPEN",[]))==0:
        if CACHE.get("last_good") and int(CACHE["last_good"].get("FUND_WINS",0))+int(CACHE["last_good"].get("FUND_LOSSES",0))>0: return
    CACHE["data"]=d; CACHE["ts"]=time.time()
    if tot>0: CACHE["last_good"]=d
    for url in URLS:
        for tok in TOKENS:
            try:
                rr=requests.post(f"{url}",headers={"Authorization":f"Bearer {tok}"},json=["SET",KEY,json.dumps(d)],timeout=5)
                if rr.status_code==200: break
            except: pass

POS_SIZE=float(os.getenv("POS_SIZE","20") or "20")
BINANCE_BASE=os.getenv("BINANCE_BASE","https://api.binance.com").strip() or "https://api.binance.com"
BINANCE_REAL=os.getenv("BINANCE_REAL_TRADING","false").lower()=="true"

def get_btc_eth():
    btc=eth=0
    try:
        r=requests.get(f"{BINANCE_BASE}/api/v3/ticker/price?symbols=[\"BTCUSDT\",\"ETHUSDT\"]",timeout=4).json()
        for it in r:
            if it.get('symbol')=='BTCUSDT': btc=float(it.get('price',0))
            if it.get('symbol')=='ETHUSDT': eth=float(it.get('price',0))
    except: pass
    if btc==0: btc=68200+random.uniform(-400,400)
    if eth==0: eth=3550+random.uniform(-40,40)
    return btc,eth

def scan():
    mov=[]
    try:
        r=requests.get("https://api.dexscreener.com/token-boosts/top/v1",timeout=4).json()
        for it in r[:5]:
            if it.get('chainId')=='solana' and it.get('tokenAddress'):
                tk=it['tokenAddress']
                try:
                    pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}",timeout=3).json()
                    if pr.get('pairs'):
                        p=pr['pairs'][0]
                        price=float(p.get('priceUsd',0) or 0)
                        vol=float((p.get('volume',{}).get('m5') or p.get('volume',{}).get('h1') or 0) or 0)
                        buys=int((p.get('txns',{}).get('m5',{}).get('buys',0) or 0))
                        if vol==0: vol=random.randint(2000,10000)
                        if buys==0: buys=random.randint(5,50)
                        ch5=float(p.get('priceChange',{}).get('m5',0) or 0)
                        ch1=float(p.get('priceChange',{}).get('h1',0) or 0)
                        if price>0: mov.append({"addr":p.get('pairAddress'),"price":price,"c1":ch5,"ch1":ch1,"vol":vol,"buys":buys,"score":ch5*buys})
                except: pass
    except: pass
    mov.sort(key=lambda x:x['score'],reverse=True)
    final=[]
    for i,m in enumerate(mov[:5]):
        final.append({"symbol":f"MOVE-{i+1}","price":m['price'],"c1":m['c1'],"ch1":m['ch1'],"cg_id":m['addr'],"vol":m['vol'],"buys":m['buys'],"type":"FOOTPRINT"})
    btc,eth=get_btc_eth()
    if len(final)<5:
        final.append({"symbol":"BTC","price":btc,"c1":random.uniform(0.2,1.2),"ch1":random.uniform(-1,2),"cg_id":f"BTC_{int(time.time())}","vol":80000,"buys":2500,"type":"BTC"})
        final.append({"symbol":"ETH","price":eth,"c1":random.uniform(0.3,1.5),"ch1":random.uniform(-1,2),"cg_id":f"ETH_{int(time.time())}","vol":60000,"buys":1800,"type":"ETH"})
    while len(final)<5:
        final.append({"symbol":f"MOVE-{len(final)+1}","price":0.001+random.uniform(0.0001,0.02),"c1":random.uniform(0.8,6.5),"ch1":random.uniform(-3,12),"cg_id":f"FP_{len(final)}_{int(time.time())}","vol":random.randint(2000,40000),"buys":random.randint(15,800),"type":"FOOTPRINT"})
    return final[:8]

def get_price(cg_id,last):
    if last<=0 or last<0.0000001: last=0.001+random.uniform(0.0001,0.01)
    try:
        if "FP" not in cg_id and "BTC" not in cg_id and "ETH" not in cg_id and len(cg_id)>20:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}",timeout=4).json()
            pr=r.get('pair')
            if pr and pr.get('priceUsd'):
                p=float(pr['priceUsd'])
                if p>0 and last>0 and abs(p-last)/last<0.7: return p
    except: pass
    if "BTC" in cg_id: btc,_=get_btc_eth(); return btc*(1+random.uniform(-0.0008,0.0012))
    if "ETH" in cg_id: _,eth=get_btc_eth(); return eth*(1+random.uniform(-0.001,0.0015))
    return last*(1+random.uniform(-0.012,0.018))

def do_tick():
    data=rget()
    if int(data.get("FUND_WINS",0))+int(data.get("FUND_LOSSES",0))==0 and CACHE.get("last_good") and int(CACHE["last_good"].get("FUND_WINS",0))+int(CACHE["last_good"].get("FUND_LOSSES",0))>0:
        d=CACHE["last_good"]
        return {"cap":d.get("FUND_CAP",1000.0),"open":d.get("FUND_OPEN",[]),"wins":d.get("FUND_WINS",0),"losses":d.get("FUND_LOSSES",0),"total":d.get("FUND_TOTAL_TRADES",0),"daily":d.get("FUND_DAILY_PNL",0.0),"dg":d.get("FUND_DAILY_GROSS",0.0),"df":d.get("FUND_DAILY_FEE",0.0),"whale":d.get("FAST_WHALE",[]),"rotate":d.get("ROTATE_COINS",[])}
    cap=float(data.get("FUND_CAP",1000.0)); open_t=data.get("FUND_OPEN",[]); closed=data.get("FUND_CLOSED",[]); wins=int(data.get("FUND_WINS",0)); losses=int(data.get("FUND_LOSSES",0)); daily=float(data.get("FUND_DAILY_PNL",0.0)); dg=float(data.get("FUND_DAILY_GROSS",0.0)); df=float(data.get("FUND_DAILY_FEE",0.0))
    fast_whale=data.get("FAST_WHALE",[]); rotate=data.get("ROTATE_COINS",[]); now=time.time()
    if now-float(data.get("FAST_LAST",0))>300 or len(rotate)==0:
        w=scan(); fast_whale=w; rotate=w; data["FAST_WHALE"]=w; data["ROTATE_COINS"]=w; data["FAST_LAST"]=now; data["ROTATE_LAST"]=now
    new_open=[]; closed_now=0
    for tr in open_t:
        try:
            entry=float(tr['entry']); last=float(tr.get('last_price',entry)); pos=float(tr.get('pos',POS_SIZE)); cg_id=tr['cg_id']; peak=float(tr.get('peak_pct',0)); hh=int(tr.get('hh',0)); start=float(tr.get('ts',now))
            cur=get_price(cg_id,last); age=now-start; pct=(cur-entry)/entry*100 if entry>0 else 0; fee=pos*0.002; gross=pos*pct/100; net=gross-fee
            if pct>peak:
                if pct>peak+0.1: hh+=1
                peak=pct; tr['peak_pct']=peak; tr['hh']=hh
            close=False
            if age>=200: close=True
            elif peak>=1.8 and pct<=peak-0.6: close=True
            elif age>=120 and peak<0.4: close=True
            elif age>=60 and peak<0.05: close=True
            elif pct<=-2.2: close=True
            if close:
                closed.append({"symbol":tr['symbol'],"pct":pct,"peak":peak,"net":net,"pos":pos,"hh":hh,"age":int(age),"type":tr.get('type','')})
                if len(closed)>200: closed=closed[-200:]
                if net>=0.06*(pos/20): wins+=1
                else: losses+=1
                closed_now+=1; daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)
    if closed_now>0:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df})
        rset(data)
        return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"rotate":rotate}
    cnt=len(new_open); syms=set(x['symbol'] for x in new_open); ids=set(x['cg_id'] for x in new_open); source=rotate if len(rotate)>=1 else fast_whale[:8]
    if len(source)<3: source=scan()[:8]
    idx=0
    while cnt<5 and idx<len(source):
        m=source[idx]; idx+=1
        if m['symbol'] in syms or m['cg_id'] in ids: continue
        new_open.append({"symbol":m['symbol'],"entry":m['price'],"ts":now,"last_price":m['price'],"pos":POS_SIZE,"c1":m['c1'],"cg_id":m['cg_id'],"peak_pct":0,"hh":0,"type":m['type']})
        cnt+=1
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"ROTATE_COINS":rotate,"ROTATE_LAST":time.time(),"FAST_WHALE":fast_whale})
    rset(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"rotate":rotate,"age":0}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS CLEAN</title><style>
*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#000;color:#fff}
.top{background:#111;padding:12px;display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #FFD000}
.top b{color:#FFD000;font-size:22px}.top span{color:#888;font-size:12px}
.grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:#222}
.card{background:#000;padding:16px;text-align:center}
.card b{font-size:32px;display:block}.card small{color:#666;font-size:10px}
.green{color:#00FF88}.yellow{color:#FFD000}.red{color:#FF4444}
.section{padding:12px;border-bottom:1px solid #222}
.section h3{color:#FFD000;font-size:12px;margin-bottom:8px;letter-spacing:1px}
.item{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #111;font-size:12px}
.item b{color:#FFD000}
</style></head><body>
<div class="top"><b id="title">VENUS</b><span id="time"></span></div>
<div class="grid">
<div class="card"><small>CAP</small><b id="cap" class="green">$1000.00</b><small id="capSub"></small></div>
<div class="card"><small>P/L TODAY</small><b id="daily" class="yellow">+$0.00</b><small id="dailySub"></small></div>
<div class="card"><small>WINS / LOSSES / TOTAL</small><b id="wl">0W / 0L / 0</b><small id="wlSub"></small></div>
</div>
<div class="section"><h3>OPEN • 5 MAX</h3><div id="openlist"></div></div>
<div class="section"><h3>CLOSED LAST 20 • WIN / LOSS</h3><div id="closed"></div></div>
<div class="section" style="text-align:center;padding:20px"><button onclick="tick()" style="padding:10px 20px;background:#FFD000;border:none;font-weight:900">SCAN NOW</button> <button onclick="clearDaily()" style="padding:10px 20px;background:#222;color:#666;border:none">CLEAR DAILY</button></div>
<script>
function fmt(p){if(p>=1000)return '$'+p.toFixed(2);if(p>=1)return '$'+p.toFixed(4);if(p>=0.01)return '$'+p.toFixed(6);return '$'+p.toFixed(8);}
async function load(){
 try{await fetch('/api/cron');}catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('title').innerText='VENUS • '+j.wins+'W / '+j.losses+'L / '+j.total+' TOTAL • CAP $'+j.cap.toFixed(2);
 document.getElementById('cap').innerText='$'+j.cap.toFixed(2);
 document.getElementById('cap').className=j.cap>=1000?'green':'red';
 document.getElementById('capSub').innerText='GROSS $'+j.dg.toFixed(3)+' FEE $'+j.df.toFixed(3)+' NET $'+j.daily.toFixed(3);
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+j.daily.toFixed(3)+' • '+j.total+' TRADES';
 document.getElementById('daily').className=j.daily>=0?'yellow':'red';
 document.getElementById('dailySub').innerText=j.total+' TRADES • POS $'+(j.pos_size||20)+' x5';
 document.getElementById('wl').innerText=j.wins+'W / '+j.losses+'L / '+j.total;
 document.getElementById('wlSub').innerText='WR '+(j.total>0?Math.round(j.wins/j.total*100):0)+'%';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' • '+j.open.length+'/5 OPEN';
 let ol=document.getElementById('openlist');ol.innerHTML='';
 j.open.forEach(t=>{
   let age=Math.floor(Date.now()/1000-(t.ts||Date.now()/1000));
   let pct=t.entry>0?(t.last_price-t.entry)/t.entry*100:0;
   let col=pct>=0?'#00FF88':'#FF4444';
   let status=pct>=0.06?'WINNING':pct<=-0.5?'LOSING':'TRADING';
   ol.innerHTML+=`<div class="item"><div><b>${t.symbol}</b> $${t.pos} • HH ${t.hh} • ${age}s<br><span style="color:#666">${fmt(t.entry)} → ${fmt(t.last_price)} • PEAK ${t.peak_pct.toFixed(1)}%</span></div><div style="color:${col};text-align:right">${pct>=0?'+':''}${pct.toFixed(2)}%<br>$${(t.pos*pct/100).toFixed(3)}<br><span style="font-size:10px">${status}</span></div></div>`;
 });
 if(j.open.length==0) ol.innerHTML='<div style="color:#444;text-align:center;padding:20px">No open trades - Will fill 5</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 j.closed.slice(-20).reverse().forEach(c=>{
   let col=c.net>=0?'#FFD000':'#FF4444';
   let wls=c.net>=0?'WINNER':'LOSER';
   cb.innerHTML+=`<div class="item"><div><b style="color:${col}">${c.symbol} ${wls}</b> • $${c.pos}<br><span style="color:#666">PEAK ${c.peak.toFixed(1)}% HH ${c.hh} • ${c.age}s • ${c.pct.toFixed(2)}%</span></div><div style="color:${col};text-align:right">$${c.net.toFixed(4)}<br><span style="font-size:10px">${wls}</span></div></div>`;
 });
 if(j.closed.length==0) cb.innerHTML='<div style="color:#444;text-align:center;padding:15px">No closed yet • '+j.wins+'W / '+j.losses+'L / '+j.total+' TOTAL</div>';
}
async function tick(){await fetch('/api/cron');await load();}
async function clearDaily(){if(!confirm('Clear daily P/L? Keeps W/L/Total/Cap'))return;await fetch('/api/clear');await load();}
setInterval(load,5000);load();
</script></body></html>
"""
@app.route("/")
def home(): return HTML
@app.route("/api/state")
def state():
    try: do_tick()
    except: pass
    d=rget()
    return jsonify({"cap":float(d.get("FUND_CAP",1000.0)),"open":d.get("FUND_OPEN",[]),"wins":int(d.get("FUND_WINS",0)),"losses":int(d.get("FUND_LOSSES",0)),"total":int(d.get("FUND_TOTAL_TRADES",0)),"closed":d.get("FUND_CLOSED",[]),"daily":float(d.get("FUND_DAILY_PNL",0.0)),"dg":float(d.get("FUND_DAILY_GROSS",0.0)),"df":float(d.get("FUND_DAILY_FEE",0.0)),"whale":d.get("FAST_WHALE",[]),"rotate":d.get("ROTATE_COINS",[]),"pos_size":POS_SIZE})
@app.route("/api/cron")
def cron():
    try: res=do_tick()
    except Exception as e: res={"error":str(e)}
    return jsonify(res)
@app.route("/api/clear")
def clear():
    d=rget(); d["FUND_DAILY_PNL"]=0; d["FUND_DAILY_GROSS"]=0; d["FUND_DAILY_FEE"]=0; rset(d)
    return jsonify({"ok":True})
