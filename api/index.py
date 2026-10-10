from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)
URLS=[]; TOKENS=[]
for k in ["KV_REST_API_URL","KV_URL","UPSTASH_REDIS_REST_URL"]:
    v=os.getenv(k,"").strip().rstrip("/")
    if v and v not in URLS: URLS.append(v)
for k in ["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"]:
    v=os.getenv(k,"").strip()
    if v and v not in TOKENS: TOKENS.append(v)
KEY="VENUS_V726_PROFIT"; KEY_BACKUP="VENUS_V726_PROFIT_BAK"
OLD=["VENUS_V725_SHARKFIX","VENUS_V724_SHARK"]
CACHE={"data":None,"ts":0,"last_good":None}
def raw_get(k):
    for url in URLS:
        for tok in TOKENS:
            try:
                r=requests.get(f"{url}/get/{k}",headers={"Authorization":f"Bearer {tok}"},timeout=5)
                v=r.json().get("result")
                if v: return json.loads(v)
            except: pass
    return None
def rget():
    global CACHE
    if CACHE["data"] and time.time()-CACHE["ts"]<3: return CACHE["data"]
    for k in [KEY,KEY_BACKUP]:
        d=raw_get(k)
        if d:
            if float(d.get("FUND_CAP",0))<990: d["FUND_DAILY_LOCKED"]=False; d["FREE_ZONE"]=False
            CACHE["data"]=d; CACHE["ts"]=time.time(); CACHE["last_good"]=d; return d
    best=None
    for k in OLD:
        d=raw_get(k)
        if d and (not best or float(d.get("FUND_CAP",0))>float(best.get("FUND_CAP",0))):
            best=d
    if best:
        if float(best.get("FUND_CAP",0))<990: best["FUND_DAILY_LOCKED"]=False; best["FREE_ZONE"]=False
        CACHE["data"]=best; CACHE["ts"]=time.time(); CACHE["last_good"]=best; return best
    return {"FUND_CAP":968.56,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":0,"FUND_DAILY_LOCKED":False,"FREE_ZONE":False,"FREE_ZONE_100_COUNT":0,"REGIME":"NEUTRAL","BTC_CH":0,"FREE_ZONE_START":0,"SCAN_COUNT":1,"SHARK_HITS":5}
def rset(d):
    global CACHE
    CACHE["data"]=d; CACHE["ts"]=time.time(); CACHE["last_good"]=d
    if len(d.get("FUND_CLOSED",[]))>100: d["FUND_CLOSED"]=d["FUND_CLOSED"][-100:]
    payload=json.dumps(d)
    for url in URLS:
        for tok in TOKENS:
            try:
                requests.post(f"{url}",headers={"Authorization":f"Bearer {tok}"},json=["SET",KEY,payload],timeout=5)
                requests.post(f"{url}",headers={"Authorization":f"Bearer {tok}"},json=["SET",KEY_BACKUP,payload],timeout=5)
            except: pass
POS_SIZE=10; REAL_TARGET=10; BASE=os.getenv("BINANCE_BASE","https://data-api.binance.vision")
def fees(chain,pos,pct):
    if pct<-5: pct=-5
    if pct>15: pct=15
    if chain=="binance": return pos*pct/100, pos*0.002, pos*pct/100-pos*0.002
    else: return pos*pct/100, pos*0.008+0.02, pos*pct/100-(pos*0.008+0.02)
def get_sharks():
    btc=0; bins=[]
    try:
        r=requests.get(f"{BASE}/api/v3/ticker/24hr",timeout=5).json()
        if isinstance(r,list):
            m=[]
            for it in r:
                try:
                    s=it.get('symbol','')
                    if not s.endswith('USDT') or any(x in s for x in ['UP','DOWN','BEAR','BULL']): continue
                    pr=float(it.get('lastPrice',0)); ch=float(it.get('priceChangePercent',0)); vol=float(it.get('quoteVolume',0)); tr=int(it.get('count',0))
                    if s=='BTCUSDT': btc=ch
                    if pr>0 and vol>1500000 and abs(ch)>0.5 and tr>3000:
                        score=abs(ch)*(vol/1000000)*(tr/1000)
                        m.append({"symbol":s.replace('USDT',''),"price":pr,"c1":ch/6,"vol":vol,"cg_id":s,"chain":"binance","score":score,"liquidity":vol,"shark_score":score,"reason":f"SHARK VOL {vol/1000000:.1f}M CH {ch:.1f}% TR {tr}"})
                except: pass
            m.sort(key=lambda x:x['score'],reverse=True)
            bins=m[:4]
    except: pass
    sols=[]
    try:
        r=requests.get("https://api.dexscreener.com/token-boosts/top/v1",timeout=5).json()
        for it in r[:25]:
            if it.get('chainId')!='solana' or not it.get('tokenAddress'): continue
            try:
                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{it['tokenAddress']}",timeout=3).json()
                if not pr.get('pairs'): continue
                p=pr['pairs'][0]
                price=float(p.get('priceUsd',0) or 0); ch5=float(p.get('priceChange',{}).get('m5',0) or 0); vol=float(p.get('volume',{}).get('m5',0) or 0); buys=int(p.get('txns',{}).get('m5',{}).get('buys',0) or 0); sells=int(p.get('txns',{}).get('m5',{}).get('sells',0) or 0); liq=float(p.get('liquidity',{}).get('usd',0) or 0)
                sym=p.get('baseToken',{}).get('symbol','SOL')[:10]
                if 'samur' in sym.lower() and vol<30000: continue
                if price>0 and vol>6000 and abs(ch5)>1 and liq>20000:
                    br=buys/(sells+1); sc=0
                    if br>1.3: sc+=br*8
                    if vol>12000: sc+=vol/1000
                    if 1.5<abs(ch5)<15: sc+=abs(ch5)*4
                    if sc>12: sols.append({"symbol":sym,"price":price,"c1":ch5,"vol":vol,"cg_id":p.get('pairAddress'),"token":it['tokenAddress'],"chain":"solana","score":sc,"liquidity":liq,"shark_score":sc,"reason":f"SHARK B {buys}/{sells} VOL {vol/1000:.0f}k M5 {ch5:.1f}% LIQ ${liq/1000:.0f}k"})
            except: pass
    except: pass
    sols.sort(key=lambda x:x['shark_score'],reverse=True)
    bins.sort(key=lambda x:x['shark_score'],reverse=True)
    mixed=bins[:3]+sols[:2]
    if len(mixed)<3: mixed=bins[:5]
    regime="BEAR" if btc<-0.8 else "BULL_JUMP" if btc>0.4 else "BULL" if btc>0.2 else "NEUTRAL"
    return mixed[:5], regime, btc
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
        except: pass
    return last
def do_tick():
    data=rget(); now=time.time()
    cap=float(data.get("FUND_CAP",968.56)); open_t=data.get("FUND_OPEN",[]); closed=data.get("FUND_CLOSED",[]); wins=int(data.get("FUND_WINS",0)); losses=int(data.get("FUND_LOSSES",0)); daily=float(data.get("FUND_DAILY_PNL",0.0)); dg=float(data.get("FUND_DAILY_GROSS",0.0)); df=float(data.get("FUND_DAILY_FEE",0.0)); profit_bank=float(data.get("FUND_PROFIT_BANK",0.0)); rotate=data.get("ROTATE_COINS",[]); locked=bool(data.get("FUND_DAILY_LOCKED",False)); free_zone=bool(data.get("FREE_ZONE",False)); count100=int(data.get("FREE_ZONE_100_COUNT",0)); fz_start=float(data.get("FREE_ZONE_START",0)); scan_count=int(data.get("SCAN_COUNT",0)); shark_hits=int(data.get("SHARK_HITS",0))
    if cap<990: locked=False; free_zone=False
    try: btc_q=float(requests.get(f"{BASE}/api/v3/ticker/24hr?symbol=BTCUSDT",timeout=2).json().get('priceChangePercent',0))
    except: btc_q=data.get("BTC_CH",0)
    if now-float(data.get("FAST_LAST",0))>10 or len(rotate)==0:
        w,regime,btc_ch=get_sharks(); rotate=w; scan_count+=1; shark_hits+=len(w); data["ROTATE_COINS"]=w; data["FAST_LAST"]=now; data["REGIME"]=regime; data["BTC_CH"]=btc_ch
    else: regime=data.get("REGIME","NEUTRAL"); btc_ch=btc_q if btc_q!=0 else data.get("BTC_CH",0)
    if not locked and daily>=REAL_TARGET:
        profit_bank+=REAL_TARGET; cap+=REAL_TARGET; count100+=1
        data.update({"FUND_CAP":cap,"FUND_OPEN":[],"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":True,"FREE_ZONE":True,"FREE_ZONE_100_COUNT":count100,"REGIME":regime,"BTC_CH":btc_ch,"FREE_ZONE_START":now,"SCAN_COUNT":scan_count,"SHARK_HITS":shark_hits})
        rset(data); return {"cap":cap,"open":[],"wins":wins,"losses":losses,"total":wins+losses,"daily":0,"dg":0,"df":0,"rotate":rotate,"bank":profit_bank,"locked":True,"free_zone":True,"count100":count100,"regime":regime,"btc_ch":btc_ch,"fz_start":now,"scan":scan_count,"shark":shark_hits}
    new_open=[]
    for tr in list(open_t):
        cur=get_price(tr['cg_id'],tr.get('chain','binance'),float(tr.get('last_price',tr['entry'])),tr.get('token')); age=now-float(tr.get('ts',now)); pct=(cur-float(tr['entry']))/float(tr['entry'])*100 if float(tr['entry'])>0 else 0; peak=float(tr.get('peak_pct',0))
        if pct>peak: peak=pct; tr['peak_pct']=peak
        gross,fee,net=fees(tr.get('chain','binance'),float(tr.get('pos',POS_SIZE)),pct)
        close=False; reason=""; sl=-2.0; tp=4.0
        if pct<=sl: close=True; reason=f"SL {sl}% NET ${net:.3f}"
        elif pct>=tp: close=True; reason=f"TP {tp}% SHARK PROFIT ${net:.3f} GROSS ${gross:.3f}"
        elif pct>=1.5 and peak>=2.2 and pct<=peak-0.6: close=True; reason=f"TRAIL LOCK {peak:.1f}->{pct:.1f}% NET ${net:.3f}"
        elif age>=240: close=True; reason=f"TIME 240s {pct:.2f}% NET ${net:.3f} MAX HOLD"
        if close:
            closed.append({"symbol":tr['symbol'],"pct":pct,"gross":gross,"fee":fee,"net":net,"peak":peak,"pos":float(tr.get('pos',POS_SIZE)),"age":int(age),"type":tr.get('type',''),"chain":tr.get('chain'),"reason":reason})
            wins+=1 if net>=0 else 0; losses+=0 if net>=0 else 1; daily+=net; dg+=gross; df+=fee; cap+=net
        else: tr['last_price']=cur; new_open.append(tr)
    if len(new_open)<3:
        syms=set(x['symbol'] for x in new_open)
        for m in rotate:
            if len(new_open)>=3: break
            if m['symbol'] in syms or abs(m['c1'])<0.4: continue
            new_open.append({"symbol":m['symbol'],"entry":m['price'],"ts":now,"last_price":m['price'],"pos":POS_SIZE,"c1":m['c1'],"cg_id":m['cg_id'],"token":m.get('token'),"chain":m.get('chain','binance'),"peak_pct":0,"type":m.get('type',''),"liquidity":m.get('liquidity',0),"shark_reason":m.get('reason','')})
        if len(new_open)==0 and len(rotate)>0 and len(open_t)==0:
            m=rotate[0]
            if m['symbol'] not in syms: new_open.append({"symbol":m['symbol'],"entry":m['price'],"ts":now,"last_price":m['price'],"pos":POS_SIZE,"c1":m['c1'],"cg_id":m['cg_id'],"token":m.get('token'),"chain":m.get('chain','binance'),"peak_pct":0,"type":m.get('type',''),"liquidity":m.get('liquidity',0),"shark_reason":m.get('reason','')})
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":locked,"FREE_ZONE":free_zone,"FREE_ZONE_100_COUNT":count100,"REGIME":regime,"BTC_CH":btc_ch,"FREE_ZONE_START":fz_start,"SCAN_COUNT":scan_count,"SHARK_HITS":shark_hits})
    rset(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"rotate":rotate,"bank":profit_bank,"locked":locked,"free_zone":free_zone,"count100":count100,"regime":regime,"btc_ch":btc_ch,"fz_start":fz_start,"scan":scan_count,"shark":shark_hits}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v726 PROFIT</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#000;color:#fff}.top{background:#111;padding:10px;border-bottom:2px solid #00FF88}.grid{display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr 1fr;gap:1px;background:#222}.card{background:#000;padding:8px;text-align:center}.card b{font-size:12px;display:block}.green{color:#00FF88}.yellow{color:#FFD000}.red{color:#FF4444}.card small{color:#888;font-size:9px}.box{padding:8px;margin:5px;font-size:9px;border:2px solid}.greenbox{border-color:#00FF88;background:#002211;color:#00FF88}.section{padding:8px;border-bottom:1px solid #222}.section h3{color:#00FF88;font-size:10px}.item{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #111;font-size:9px}.shark{color:#00FFFF;font-weight:bold;background:#003333;padding:1px 3px}</style></head><body>
<div class="top"><b>VENUS v726 PROFIT CIRCUIT - 240s hold for TP 4% $0.40</b> <span id="time"></span></div>
<div class="grid">
<div class="card"><small>CAP TEST</small><b id="cap" class="green">$1000</b></div>
<div class="card"><small>DAILY NET</small><b id="daily" class="green">+$0</b></div>
<div class="card"><small>GROSS</small><b id="gross" class="yellow">$0</b></div>
<div class="card"><small>FEE REAL</small><b id="fee" class="red">$0</b></div>
<div class="card"><small>W/L/TOTAL</small><b id="wl">0W/0L/0</b></div>
<div class="card"><small>BANK</small><b id="bank" class="green">$0</b></div>
</div>
<div class="box greenbox" id="fzbox">PROFIT CIRCUIT: 240s hold, TRAIL locks profit, TP 4% $0.40, Scan every 10s</div>
<div class="section"><h3>SHARK FOOTPRINTS <span id="scancnt"></span></h3><div id="rotate"></div></div>
<div class="section"><h3>OPEN - HUNTING</h3><div id="openlist"></div></div>
<div class="section"><h3>CLOSED - PROFITS</h3><div id="closed"></div></div>
<script>
async function load(){
 try{await fetch('/api/cron');}catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+j.cap.toFixed(2);
 let d=document.getElementById('daily');
 if(j.daily>=0){ d.className='green'; d.innerText='+$'+j.daily.toFixed(2)+' NET'; }
 else { d.className='red'; d.innerText='-$'+Math.abs(j.daily).toFixed(2)+' NET'; }
 document.getElementById('gross').innerText='$'+j.dg.toFixed(2);
 document.getElementById('fee').innerText='$'+j.df.toFixed(2);
 document.getElementById('wl').innerText=j.wins+'W/'+j.losses+'L/'+j.total;
 document.getElementById('bank').innerText='$'+j.bank.toFixed(2);
 document.getElementById('scancnt').innerText=' - SCAN #'+(j.scan||0)+' SHARKS '+ (j.shark||0) +' every 10s';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' BTC '+ (j.btc_ch||0).toFixed(2)+'% '+j.regime+(j.locked?' LOCKED':'')+(j.free_zone?` FREEZE ${Math.floor((Date.now()/1000-(j.fz_start||0))/60)}min`:'');
 document.getElementById('fzbox').innerText=j.cap<990?`RECOVERY $${j.cap.toFixed(2)} - Scan #${j.scan||0} Sharks ${j.shark||0} - Hold 240s for TP 4% $0.40`:`PROFIT CIRCUIT - Scan #${j.scan||0} BTC ${(j.btc_ch||0).toFixed(2)}% ${j.regime} - 240s hold TP 4%`;
 let rot=document.getElementById('rotate');rot.innerHTML='';
 (j.rotate||[]).forEach(m=>{
  let shark=m.shark_score>20?'<span class="shark"> SHARK!</span>':'';
  rot.innerHTML+=`<div class="item"><div><b>${m.symbol} ${m.chain.toUpperCase()}</b> ${m.c1.toFixed(2)}% VOL ${(m.vol/1000).toFixed(0)}k${shark}<br><small style="color:#0FF">${m.reason||''}</small></div><div>LIQ $${(m.liquidity/1000).toFixed(0)}k<br>Score ${Math.floor(m.shark_score||0)}</div></div>`;
 });
 let ol=document.getElementById('openlist');ol.innerHTML='';
 if((j.open||[]).length==0){ ol.innerHTML='<div class="item"><div><b>Scanning...</b></div></div>'; }
 (j.open||[]).forEach(t=>{
  let pct=t.entry>0?(t.last_price-t.entry)/t.entry*100:0; if(pct<-5) pct=-5; let fee=0.02; let gross=t.pos*pct/100; let net=gross-fee;
  let age=Math.floor(Date.now()/1000-t.ts); if(age<0) age=0;
  ol.innerHTML+=`<div class="item"><div><b>${t.symbol}</b> ${pct.toFixed(2)}% NET $${net.toFixed(3)} AGE ${age}s<br><small style="color:#0FF">${t.shark_reason||''}</small></div><div>NET $${net.toFixed(3)}</div></div>`;
 });
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-20).reverse().forEach(c=>{
  let col=c.net>=0?'#00FF88':'#FF4444';
  cb.innerHTML+=`<div class="item"><div><b style="color:${col}">${c.symbol} NET $${c.net.toFixed(3)}</b> ${c.reason||''}</div><div style="color:${col}">${c.pct.toFixed(2)}% NET $${c.net.toFixed(3)}</div></div>`;
 });
}
setInterval(load,2000);load();
</script></body></html>
"""
@app.route("/")
def home(): return HTML
@app.route("/api/state")
def state():
    try: data=do_tick()
    except Exception as e:
        import traceback; traceback.print_exc()
        data={"cap":968.56,"open":[],"wins":0,"losses":0,"total":0,"closed":[],"daily":0,"dg":0,"df":0,"rotate":[],"bank":0,"locked":False,"free_zone":False,"count100":0,"regime":"NEUTRAL","btc_ch":0,"fz_start":0,"scan":1,"shark":5}
    d=rget()
    if d is None: d={"FUND_CAP":968.56,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":0,"FUND_DAILY_LOCKED":False,"FREE_ZONE":False,"FREE_ZONE_100_COUNT":0,"REGIME":"NEUTRAL","BTC_CH":0,"FREE_ZONE_START":0,"SCAN_COUNT":1,"SHARK_HITS":5}
    return jsonify({"cap":float(data.get("cap",d.get("FUND_CAP",968.56))),"open":data.get("open",d.get("FUND_OPEN",[])),"wins":int(data.get("wins",d.get("FUND_WINS",0))),"losses":int(data.get("losses",d.get("FUND_LOSSES",0))),"total":int(data.get("total",d.get("FUND_TOTAL_TRADES",0))),"closed":d.get("FUND_CLOSED",[]),"daily":float(data.get("daily",d.get("FUND_DAILY_PNL",0))),"dg":float(data.get("dg",d.get("FUND_DAILY_GROSS",0))),"df":float(data.get("df",d.get("FUND_DAILY_FEE",0))),"rotate":data.get("rotate",d.get("ROTATE_COINS",[])),"bank":float(data.get("bank",d.get("FUND_PROFIT_BANK",0.0))),"locked":bool(data.get("locked",d.get("FUND_DAILY_LOCKED",False))),"free_zone":bool(data.get("free_zone",d.get("FREE_ZONE",False))),"count100":int(data.get("count100",d.get("FREE_ZONE_100_COUNT",0))),"regime":data.get("regime",d.get("REGIME","NEUTRAL")),"btc_ch":float(data.get("btc_ch",d.get("BTC_CH",0))),"locked_tab":bool(data.get("locked_tab",False)),"fz_start":float(data.get("fz_start",d.get("FREE_ZONE_START",0))),"scan":int(data.get("scan",d.get("SCAN_COUNT",0))),"shark":int(data.get("shark",d.get("SHARK_HITS",0)))})
@app.route("/api/cron")
def cron():
    try: return jsonify(do_tick())
    except Exception as e: return jsonify({"error":str(e)})
@app.route("/api/reset")
def reset():
    d={"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":0,"FUND_DAILY_LOCKED":False,"FREE_ZONE":False,"FREE_ZONE_100_COUNT":0,"REGIME":"NEUTRAL","BTC_CH":0,"FREE_ZONE_START":0,"SCAN_COUNT":1,"SHARK_HITS":5}
    rset(d)
    return jsonify({"ok":True,"msg":"v726 PROFIT - READY"})
