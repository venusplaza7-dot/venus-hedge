from flask import Flask, jsonify, request, abort
import os, json, requests, time
from threading import RLock

app = Flask(__name__)
LOCK = RLock()

URLS=[]; TOKENS=[]
for k in ["KV_REST_API_URL","KV_URL","UPSTASH_REDIS_REST_URL"]:
    v=os.getenv(k,"").strip().rstrip("/")
    if v and v not in URLS: URLS.append(v)
for k in ["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"]:
    v=os.getenv(k,"").strip()
    if v and v not in TOKENS: TOKENS.append(v)

KEY="VENUS_V727_PROFIT"
KEY_BACKUP="VENUS_V727_PROFIT_BAK"
CACHE={"data":None,"ts":0}
ADMIN_KEY=os.getenv("ADMIN_KEY","venus727")

POS_SIZE=float(os.getenv("POS_SIZE","10"))
TP_PCT=float(os.getenv("TP_PCT","0.8"))
SL_PCT=float(os.getenv("SL_PCT","-1.2"))
TRAIL_TRIGGER=0.6
TRAIL_DROP=0.25
MAX_HOLD=240
REAL_TARGET=10
BASE=os.getenv("BINANCE_BASE","https://data-api.binance.vision")

def raw_get(k):
    for url in URLS:
        for tok in TOKENS:
            try:
                r=requests.get(f"{url}/get/{k}",headers={"Authorization":f"Bearer {tok}"},timeout=5)
                v=r.json().get("result")
                if v: return json.loads(v)
            except: pass
    return None

def raw_set(k,payload):
    ok=False
    for url in URLS:
        for tok in TOKENS:
            try:
                r=requests.post(f"{url}",headers={"Authorization":f"Bearer {tok}"},json=["SET",k,payload],timeout=5)
                if r.status_code==200: ok=True
            except: pass
    return ok

def rget_nolock():
    if CACHE["data"] and time.time()-CACHE["ts"]<2:
        return CACHE["data"]
    for k in [KEY,KEY_BACKUP]:
        d=raw_get(k)
        if d and isinstance(d,dict) and "FUND_CAP" in d:
            CACHE["data"]=d
            CACHE["ts"]=time.time()
            return d
    return {
        "FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],
        "FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,
        "FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,
        "FAST_LAST":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":0,
        "FUND_DAILY_LOCKED":False,"FREE_ZONE":False,"FREE_ZONE_100_COUNT":0,
        "REGIME":"NEUTRAL","BTC_CH":0,"FREE_ZONE_START":0,"SCAN_COUNT":0,"SHARK_HITS":0,
        "FUND_DAILY_START":time.time()
    }

def rget():
    with LOCK:
        return rget_nolock()

def rset(d):
    with LOCK:
        if len(d.get("FUND_CLOSED",[]))>150:
            d["FUND_CLOSED"]=d["FUND_CLOSED"][-150:]
        payload=json.dumps(d)
        CACHE["data"]=d
        CACHE["ts"]=time.time()
        raw_set(KEY,payload)
        raw_set(KEY_BACKUP,payload)

def fees(chain,pos,pct):
    if pct<-10: pct=-10
    if pct>20: pct=20
    if chain=="binance":
        fee=pos*0.001
        gross=pos*pct/100
        return gross, fee, gross-fee
    else:
        fee=pos*0.02
        gross=pos*pct/100
        return gross, fee, gross-fee

def get_sharks():
    btc=0; bins=[]; raw_count=0
    try:
        r=requests.get(f"{BASE}/api/v3/ticker/24hr",timeout=8).json()
        if isinstance(r,list):
            raw_count=len(r)
            m=[]
            for it in r:
                try:
                    s=it.get('symbol','')
                    if not s.endswith('USDT'): continue
                    if any(x in s for x in ['UP','DOWN','BEAR','BULL']): continue
                    pr=float(it.get('lastPrice',0))
                    ch=float(it.get('priceChangePercent',0))
                    vol=float(it.get('quoteVolume',0))
                    tr=int(it.get('count',0))
                    if s=='BTCUSDT': btc=ch
                    if pr>0 and vol>1500000 and abs(ch)>0.7 and tr>500:
                        if abs(ch)>45: continue
                        score=abs(ch)*(vol/1000000)
                        m.append({"symbol":s.replace('USDT',''),"price":pr,"c1":ch/6,"vol":vol,"cg_id":s,"chain":"binance","score":score,"liquidity":vol,"shark_score":score,"reason":f"VOL {vol/1000000:.1f}M CH {ch:.1f}% TR {tr}"})
                except: continue
            m.sort(key=lambda x:x['score'],reverse=True)
            bins=m[:8]
    except Exception as e:
        print(f"binance err {e}")

    sols=[]
    try:
        r=requests.get("https://api.dexscreener.com/token-boosts/top/v1",timeout=5).json()
        for it in r[:30]:
            if it.get('chainId')!='solana' or not it.get('tokenAddress'): continue
            try:
                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{it['tokenAddress']}",timeout=4).json()
                if not pr.get('pairs'): continue
                pairs=sorted(pr['pairs'], key=lambda x: float(x.get('liquidity',{}).get('usd',0) or 0), reverse=True)
                if not pairs: continue
                p=pairs[0]
                price=float(p.get('priceUsd',0) or 0)
                ch5=float(p.get('priceChange',{}).get('m5',0) or 0)
                vol=float(p.get('volume',{}).get('m5',0) or 0)
                buys=int(p.get('txns',{}).get('m5',{}).get('buys',0) or 0)
                sells=int(p.get('txns',{}).get('m5',{}).get('sells',0) or 0)
                liq=float(p.get('liquidity',{}).get('usd',0) or 0)
                sym=p.get('baseToken',{}).get('symbol','SOL')[:12]
                if price>0 and vol>3000 and abs(ch5)>0.5 and liq>10000 and buys>=1:
                    sc=vol/1000 + abs(ch5)*2
                    if sc>5:
                        sols.append({"symbol":sym,"price":price,"c1":ch5,"vol":vol,"cg_id":p.get('pairAddress'),"token":it['tokenAddress'],"chain":"solana","score":sc,"liquidity":liq,"shark_score":sc,"reason":f"B {buys}/{sells} VOL {vol/1000:.0f}k M5 {ch5:.1f}% LIQ ${liq/1000:.0f}k"})
            except: continue
    except: pass

    sols.sort(key=lambda x:x['shark_score'],reverse=True)
    bins.sort(key=lambda x:x['shark_score'],reverse=True)
    mixed=bins[:3]+sols[:2]
    if len(mixed)==0 and bins:
        mixed=bins[:3]
    if len(mixed)==0 and raw_count>0:
        mixed=bins[:3] if bins else []
    regime="BEAR" if btc<-1.0 else "BULL_JUMP" if btc>0.6 else "BULL" if btc>0.2 else "NEUTRAL"
    return mixed[:5], regime, btc, raw_count

def get_price(cg,chain,last,token=None):
    if chain=="binance":
        try:
            r=requests.get(f"{BASE}/api/v3/ticker/price?symbol={cg}",timeout=2).json()
            p=float(r.get('price',0))
            if p>0: return p
        except: pass
    else:
        try:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg}",timeout=3).json()
            if r.get('pair') and r['pair'].get('priceUsd'):
                p=float(r['pair']['priceUsd'])
                if p>0: return p
            if token:
                r2=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}",timeout=3).json()
                if r2.get('pairs'):
                    p=float(r2['pairs'][0].get('priceUsd',0) or 0)
                    if p>0: return p
        except: pass
    return last

def do_tick():
    with LOCK:
        data=rget_nolock()
        now=time.time()
        cap=float(data.get("FUND_CAP",1000.0))
        open_t=data.get("FUND_OPEN",[])
        closed=data.get("FUND_CLOSED",[])
        wins=int(data.get("FUND_WINS",0))
        losses=int(data.get("FUND_LOSSES",0))
        daily=float(data.get("FUND_DAILY_PNL",0.0))
        dg=float(data.get("FUND_DAILY_GROSS",0.0))
        df=float(data.get("FUND_DAILY_FEE",0.0))
        profit_bank=float(data.get("FUND_PROFIT_BANK",0.0))
        rotate=data.get("ROTATE_COINS",[])
        locked=bool(data.get("FUND_DAILY_LOCKED",False))
        free_zone=bool(data.get("FREE_ZONE",False))
        count100=int(data.get("FREE_ZONE_100_COUNT",0))
        fz_start=float(data.get("FREE_ZONE_START",0))
        scan_count=int(data.get("SCAN_COUNT",0))
        shark_hits=int(data.get("SHARK_HITS",0))
        daily_start=float(data.get("FUND_DAILY_START",now))
        if now-daily_start > 86400:
            daily=0; dg=0; df=0; locked=False; free_zone=False
            data["FUND_DAILY_START"]=now
        if cap<900:
            locked=True
        if now-float(data.get("FAST_LAST",0))>12 or len(rotate)==0:
            w,regime,btc_ch,raw=get_sharks()
            rotate=w
            scan_count+=1
            shark_hits+=len(w)
            data["ROTATE_COINS"]=w
            data["FAST_LAST"]=now
            data["REGIME"]=regime
            data["BTC_CH"]=btc_ch
            data["SCAN_COUNT"]=scan_count
            data["SHARK_HITS"]=shark_hits
        else:
            regime=data.get("REGIME","NEUTRAL")
            btc_ch=data.get("BTC_CH",0)
        if not locked and daily>=REAL_TARGET:
            profit_bank+=REAL_TARGET
            cap+=REAL_TARGET
            count100+=1
            locked=True; free_zone=True; fz_start=now
            data.update({"FUND_CAP":cap,"FUND_OPEN":[],"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":True,"FREE_ZONE":True,"FREE_ZONE_100_COUNT":count100,"REGIME":regime,"BTC_CH":btc_ch,"FREE_ZONE_START":now,"SCAN_COUNT":scan_count,"SHARK_HITS":shark_hits})
            rset(data)
            return data
        new_open=[]
        for tr in list(open_t):
            cur=get_price(tr['cg_id'],tr.get('chain','binance'),float(tr.get('last_price',tr['entry'])),tr.get('token'))
            age=now-float(tr.get('ts',now))
            entry=float(tr['entry'])
            pct=(cur-entry)/entry*100 if entry>0 else 0
            peak=float(tr.get('peak_pct',0))
            if pct>peak:
                peak=pct
                tr['peak_pct']=peak
            gross,fee,net=fees(tr.get('chain','binance'),float(tr.get('pos',POS_SIZE)),pct)
            close=False; reason=""
            if pct<=SL_PCT: close=True; reason=f"SL {SL_PCT}% NET ${net:.3f}"
            elif pct>=TP_PCT: close=True; reason=f"TP {TP_PCT}% PROFIT ${net:.3f}"
            elif pct>=TRAIL_TRIGGER and peak>=TRAIL_TRIGGER and pct<=peak-TRAIL_DROP: close=True; reason=f"TRAIL {peak:.2f}->{pct:.2f}% NET ${net:.3f}"
            elif age>=MAX_HOLD: close=True; reason=f"TIME {MAX_HOLD}s {pct:.2f}% NET ${net:.3f}"
            if close:
                closed.append({"symbol":tr['symbol'],"pct":pct,"gross":gross,"fee":fee,"net":net,"peak":peak,"pos":float(tr.get('pos',POS_SIZE)),"age":int(age),"chain":tr.get('chain'),"reason":reason})
                if net>=0: wins+=1
                else: losses+=1
                daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur
                new_open.append(tr)
        if len(new_open)<3 and not locked:
            syms=set(x['symbol'] for x in new_open)
            for m in rotate:
                if len(new_open)>=3: break
                if m['symbol'] in syms: continue
                if abs(m['c1'])<0.2: continue
                new_open.append({"symbol":m['symbol'],"entry":m['price'],"ts":now,"last_price":m['price'],"pos":POS_SIZE,"c1":m['c1'],"cg_id":m['cg_id'],"token":m.get('token'),"chain":m.get('chain','binance'),"peak_pct":0,"liquidity":m.get('liquidity',0),"shark_reason":m.get('reason','')})
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":locked,"FREE_ZONE":free_zone,"FREE_ZONE_100_COUNT":count100,"REGIME":regime,"BTC_CH":btc_ch,"FREE_ZONE_START":fz_start,"SCAN_COUNT":scan_count,"SHARK_HITS":shark_hits})
        rset(data)
        return data

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v727 PROFIT</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#000;color:#fff}.top{background:#111;padding:10px;border-bottom:2px solid #00FF88}.grid{display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr 1fr;gap:1px;background:#222}.card{background:#000;padding:8px;text-align:center}.card b{font-size:12px;display:block}.green{color:#00FF88}.yellow{color:#FFD000}.red{color:#FF4444}.card small{color:#888;font-size:9px}.box{padding:8px;margin:5px;font-size:9px;border:2px solid}.greenbox{border-color:#00FF88;background:#002211;color:#00FF88}.redbox{border-color:#FF4444;background:#220000;color:#FF4444}.section{padding:8px;border-bottom:1px solid #222}.section h3{color:#00FF88;font-size:10px}.item{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #111;font-size:9px}.shark{color:#00FFFF;font-weight:bold;background:#003333;padding:1px 3px}</style></head><body>
<div class="top"><b>VENUS v727.2 PROFIT - TP 0.8% $0.08 | 240s hold | <span id="regime"></span></b> <span id="time"></span></div>
<div class="grid"><div class="card"><small>CAP TEST</small><b id="cap" class="green">$1000</b></div><div class="card"><small>DAILY NET</small><b id="daily" class="green">+$0</b></div><div class="card"><small>GROSS</small><b id="gross" class="yellow">$0</b></div><div class="card"><small>FEE REAL</small><b id="fee" class="red">$0</b></div><div class="card"><small>W/L/TOTAL</small><b id="wl">0W/0L/0</b></div><div class="card"><small>BANK</small><b id="bank" class="green">$0</b></div></div>
<div class="box greenbox" id="fzbox">LOADING...</div>
<div class="section"><h3>SHARK FOOTPRINTS <span id="scancnt"></span></h3><div id="rotate"></div></div>
<div class="section"><h3>OPEN - HUNTING</h3><div id="openlist"></div></div>
<div class="section"><h3>CLOSED - PROFITS (last 30)</h3><div id="closed"></div></div>
<script>
async function load(){
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+j.cap.toFixed(2);
 document.getElementById('cap').className=j.cap>=1000?'green':j.cap<950?'red':'yellow';
 let d=document.getElementById('daily');
 if(j.daily>=0){ d.className='green'; d.innerText='+$'+j.daily.toFixed(2)+' NET'; } else { d.className='red'; d.innerText='-$'+Math.abs(j.daily).toFixed(2)+' NET'; }
 document.getElementById('gross').innerText='$'+j.dg.toFixed(2);
 document.getElementById('fee').innerText='$'+j.df.toFixed(2);
 document.getElementById('wl').innerText=j.wins+'W/'+j.losses+'L/'+j.total;
 document.getElementById('bank').innerText='$'+j.bank.toFixed(2);
 document.getElementById('scancnt').innerText=' - SCAN #'+(j.scan||0)+' SHARKS '+ (j.shark||0) +' every 12s';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' BTC '+ (j.btc_ch||0).toFixed(2)+'% '+(j.locked?' LOCKED':'');
 document.getElementById('regime').innerText=j.regime;
 let box=document.getElementById('fzbox');
 if(j.locked && j.cap>=1000){ box.className='box greenbox'; box.innerText=`LOCKED PROFIT $${j.bank.toFixed(2)} - FREEZE ${Math.floor((Date.now()/1000-(j.fz_start||0))/60)}min - CAP $${j.cap.toFixed(2)}`; }
 else if(j.cap<990){ box.className='box redbox'; box.innerText=`RECOVERY $${j.cap.toFixed(2)} - Scan #${j.scan||0} Sharks ${j.shark||0} - TP 0.8% $0.08 | SL -1.2%`; }
 else { box.className='box greenbox'; box.innerText=`PROFIT CIRCUIT - Scan #${j.scan||0} BTC ${(j.btc_ch||0).toFixed(2)}% ${j.regime} - TP 0.8% TRAIL 0.6%`; }
 let rot=document.getElementById('rotate');rot.innerHTML='';
 (j.rotate||[]).forEach(m=>{let shark=m.shark_score>10?'<span class="shark"> SHARK!</span>':'';rot.innerHTML+=`<div class="item"><div><b>${m.symbol} ${m.chain.toUpperCase()}</b> ${m.c1.toFixed(2)}% VOL ${(m.vol/1000).toFixed(0)}k${shark}<br><small style="color:#0FF">${m.reason||''}</small></div><div>LIQ $${(m.liquidity/1000).toFixed(0)}k<br>Score ${Math.floor(m.shark_score||0)}</div></div>`;});
 let ol=document.getElementById('openlist');ol.innerHTML='';if((j.open||[]).length==0){ ol.innerHTML='<div class="item"><div><b>Waiting for sharks...</b></div></div>'; }
 (j.open||[]).forEach(t=>{let pct=t.entry>0?(t.last_price-t.entry)/t.entry*100:0;let fee=t.chain=='binance'?t.pos*0.001:t.pos*0.02;let gross=t.pos*pct/100;let net=gross-fee;let age=Math.floor(Date.now()/1000-t.ts);if(age<0) age=0;let col=net>=0?'#00FF88':'#FF8888';ol.innerHTML+=`<div class="item"><div><b>${t.symbol}</b> <span style="color:${col}">${pct.toFixed(2)}% NET $${net.toFixed(3)}</span> AGE ${age}s<br><small style="color:#0FF">${t.shark_reason||''}</small></div><div style="color:${col}">NET $${net.toFixed(3)}<br>PEAK ${(t.peak_pct||0).toFixed(2)}%</div></div>`;});
 let cb=document.getElementById('closed');cb.innerHTML='';(j.closed||[]).slice(-30).reverse().forEach(c=>{let col=c.net>=0?'#00FF88':'#FF4444';cb.innerHTML+=`<div class="item"><div><b style="color:${col}">${c.symbol} NET $${c.net.toFixed(3)}</b> ${c.reason||''}</div><div style="color:${col}">${c.pct.toFixed(2)}% NET $${c.net.toFixed(3)}</div></div>`;});
}
setInterval(load,2000);load();
</script></body></html>
"""

@app.route("/")
def home(): return HTML

@app.route("/api/state")
def state():
    try:
        d=rget()
        return jsonify({"cap":float(d.get("FUND_CAP",1000)),"open":d.get("FUND_OPEN",[]),"wins":int(d.get("FUND_WINS",0)),"losses":int(d.get("FUND_LOSSES",0)),"total":int(d.get("FUND_TOTAL_TRADES",0)),"closed":d.get("FUND_CLOSED",[]),"daily":float(d.get("FUND_DAILY_PNL",0)),"dg":float(d.get("FUND_DAILY_GROSS",0)),"df":float(d.get("FUND_DAILY_FEE",0)),"rotate":d.get("ROTATE_COINS",[]),"bank":float(d.get("FUND_PROFIT_BANK",0)),"locked":bool(d.get("FUND_DAILY_LOCKED",False)),"free_zone":bool(d.get("FREE_ZONE",False)),"count100":int(d.get("FREE_ZONE_100_COUNT",0)),"regime":d.get("REGIME","NEUTRAL"),"btc_ch":float(d.get("BTC_CH",0)),"fz_start":float(d.get("FREE_ZONE_START",0)),"scan":int(d.get("SCAN_COUNT",0)),"shark":int(d.get("SHARK_HITS",0))})
    except Exception as e:
        return jsonify({"error":str(e),"cap":1000,"open":[],"wins":0,"losses":0,"total":0,"closed":[],"daily":0,"dg":0,"df":0,"rotate":[],"bank":0,"locked":False,"free_zone":False,"count100":0,"regime":"NEUTRAL","btc_ch":0,"fz_start":0,"scan":0,"shark":0})

@app.route("/api/cron")
def cron():
    if request.args.get("key","")!= ADMIN_KEY:
        if request.headers.get("x-vercel-cron") is None and request.args.get("cron","")!="1":
            pass
    try:
        data=do_tick()
        return jsonify({"ok":True,"cap":data.get("FUND_CAP"),"open":len(data.get("FUND_OPEN",[])),"scan":data.get("SCAN_COUNT"),"sharks":len(data.get("ROTATE_COINS",[]))})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error":str(e)}),500

@app.route("/api/debug")
def debug():
    if request.args.get("key","")!= ADMIN_KEY: abort(403)
    try:
        w,regime,btc,raw=get_sharks()
        return jsonify({"ok":True,"raw_binance_count":raw,"found":len(w),"sharks":w,"regime":regime,"btc":btc,"base":BASE,"has_kv":bool(URLS)})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error":str(e)}),500

@app.route("/api/reset")
def reset():
    if request.args.get("key","")!= ADMIN_KEY: abort(403)
    d={"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":0,"FUND_DAILY_LOCKED":False,"FREE_ZONE":False,"FREE_ZONE_100_COUNT":0,"REGIME":"NEUTRAL","BTC_CH":0,"FREE_ZONE_START":0,"SCAN_COUNT":0,"SHARK_HITS":0,"FUND_DAILY_START":time.time()}
    rset(d)
    return jsonify({"ok":True,"msg":"v727.2 READY - CAP $1000"})
