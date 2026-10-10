from flask import Flask, jsonify
import os, json, requests, time, urllib.parse
app = Flask(__name__)

URLS=[]; TOKENS=[]
for k in ["KV_REST_API_URL","KV_URL","UPSTASH_REDIS_REST_URL"]:
    v=os.getenv(k,"").strip().rstrip("/")
    if v and v not in URLS: URLS.append(v)
for k in ["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"]:
    v=os.getenv(k,"").strip()
    if v and v not in TOKENS: TOKENS.append(v)

KEY="VENUS_V722_RECOVER"; KEY_BACKUP="VENUS_V722_RECOVER_BAK"
OLD_KEYS=["VENUS_V721_SLFIX","VENUS_V721_SLFIX_BAK","VENUS_V720_FINAL","VENUS_V712_FEES_FIXED"]
CACHE={"data":None,"ts":0,"last_good":None,"last_tick":0}

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
    if CACHE["data"] and time.time()-CACHE["ts"]<10: return CACHE["data"]
    for k in [KEY, KEY_BACKUP]:
        d=raw_get(k)
        if d:
            # FORCE UNLOCK if CAP <990 (recovery mode)
            if float(d.get("FUND_CAP",0))<990:
                d["FUND_DAILY_LOCKED"]=False; d["FREE_ZONE"]=False; d["FREE_ZONE_START"]=0
            CACHE["data"]=d; CACHE["ts"]=time.time(); CACHE["last_good"]=d; return d
    best=None
    for k in OLD_KEYS:
        d=raw_get(k)
        if d:
            if not best or float(d.get("FUND_CAP",0))>float(best.get("FUND_CAP",0)):
                best=d
    if best:
        if float(best.get("FUND_CAP",0))<990:
            best["FUND_DAILY_LOCKED"]=False; best["FREE_ZONE"]=False; best["FREE_ZONE_START"]=0
        CACHE["data"]=best; CACHE["ts"]=time.time(); CACHE["last_good"]=best; return best
    return {"FUND_CAP":968.56,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":0,"FUND_DAILY_LOCKED":False,"FREE_ZONE":False,"FREE_ZONE_100_COUNT":0,"REGIME":"NEUTRAL","BTC_CH":0,"FREE_ZONE_START":0}

def rset(d):
    global CACHE
    # Never allow $1000 overwrite $968
    existing=raw_get(KEY) or raw_get(KEY_BACKUP)
    if not existing:
        for k in OLD_KEYS:
            dd=raw_get(k)
            if dd and float(dd.get("FUND_CAP",0))>900:
                existing=dd; break
    if CACHE.get("last_good") and (not existing or float(CACHE["last_good"].get("FUND_CAP",0))>float(existing.get("FUND_CAP",0))):
        existing=CACHE["last_good"]
    if existing:
        ecap=float(existing.get("FUND_CAP",0))
        ncap=float(d.get("FUND_CAP",0)); ntotal=int(d.get("FUND_TOTAL_TRADES",0))
        if ecap>900 and ncap<=1000.6 and ntotal<=1 and ecap>ncap+5:
            CACHE["data"]=existing; CACHE["last_good"]=existing
            return
    CACHE["data"]=d; CACHE["ts"]=time.time(); CACHE["last_good"]=d; CACHE["last_tick"]=time.time()
    if len(d.get("FUND_CLOSED",[]))>50: d["FUND_CLOSED"]=d["FUND_CLOSED"][-50:]
    payload=json.dumps(d)
    for url in URLS:
        for tok in TOKENS:
            try:
                requests.post(f"{url}",headers={"Authorization":f"Bearer {tok}"},json=["SET",KEY,payload],timeout=5)
                requests.post(f"{url}",headers={"Authorization":f"Bearer {tok}"},json=["SET",KEY_BACKUP,payload],timeout=5)
            except: pass

POS_SIZE=10; REAL_TARGET=10
BINANCE_BASE=os.getenv("BINANCE_BASE","https://data-api.binance.vision")

def calc_fees(chain, pos_usd, gross_pct):
    if gross_pct<-5: gross_pct=-5
    if chain=="binance": return pos_usd*gross_pct/100, pos_usd*0.002, pos_usd*gross_pct/100-pos_usd*0.002, 0.2
    else: return pos_usd*gross_pct/100, pos_usd*0.008+0.02, pos_usd*gross_pct/100-(pos_usd*0.008+0.02), 0.8

def get_real_prices():
    binance_coins=[]; btc_ch_global=0
    try:
        coins=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT"]
        sym_param=urllib.parse.quote(json.dumps(coins))
        r=requests.get(f"{BINANCE_BASE}/api/v3/ticker/24hr?symbols={sym_param}",timeout=6).json()
        if isinstance(r, dict) and r.get('code'):
            r=[]
            for s in coins:
                try:
                    t=requests.get(f"{BINANCE_BASE}/api/v3/ticker/24hr?symbol={s}",timeout=4).json()
                    if t.get('symbol'): r.append(t)
                except: pass
        for it in r:
            try:
                price=float(it.get('lastPrice',0)); ch=float(it.get('priceChangePercent',0)); vol=float(it.get('quoteVolume',0))
                if it.get('symbol')=='BTCUSDT': btc_ch_global=ch
                if price>0 and vol>500000:
                    binance_coins.append({"symbol":it['symbol'].replace('USDT',''),"price":price,"c1":ch/6,"vol":vol,"cg_id":it['symbol'],"type":"BINANCE_REAL","chain":"binance","score":abs(ch),"liquidity":vol})
            except: pass
    except: pass
    binance_coins.sort(key=lambda x:abs(x['c1']),reverse=True)
    mixed=binance_coins[:4]
    btc_ch=btc_ch_global if btc_ch_global!=0 else next((x['c1']*6 for x in binance_coins if x['symbol']=='BTC'),0)
    regime="BEAR_FREEZE" if btc_ch<-0.8 else "BULL_JUMP_100" if btc_ch>0.4 else "BULL" if btc_ch>0.2 else "NEUTRAL"
    return mixed[:4], regime, btc_ch

def get_price_real(cg_id, chain, last, token=None):
    if chain=="binance":
        try:
            r=requests.get(f"{BINANCE_BASE}/api/v3/ticker/price?symbol={cg_id}",timeout=2).json()
            p=float(r.get('price',0))
            if p>0: return p
        except: pass
    return last

def do_tick():
    global CACHE
    data=rget()
    now=time.time()
    if data is None: return {"cap":968,"open":[],"wins":0,"losses":0,"total":0,"daily":0,"dg":0,"df":0,"rotate":[],"bank":0,"locked":False,"free_zone":False,"count100":0,"regime":"NEUTRAL","btc_ch":0,"locked_tab":False,"fz_start":0}
    if now - CACHE.get("last_tick",0) < 8 and CACHE.get("last_tick",0)!=0:
        return {"cap":float(data.get("FUND_CAP",1000.0)),"open":data.get("FUND_OPEN",[]),"wins":int(data.get("FUND_WINS",0)),"losses":int(data.get("FUND_LOSSES",0)),"total":int(data.get("FUND_TOTAL_TRADES",0)),"daily":float(data.get("FUND_DAILY_PNL",0.0)),"dg":float(data.get("FUND_DAILY_GROSS",0.0)),"df":float(data.get("FUND_DAILY_FEE",0.0)),"rotate":data.get("ROTATE_COINS",[]),"bank":float(data.get("FUND_PROFIT_BANK",0.0)),"locked":bool(data.get("FUND_DAILY_LOCKED",False)),"free_zone":bool(data.get("FREE_ZONE",False)),"count100":int(data.get("FREE_ZONE_100_COUNT",0)),"regime":data.get("REGIME","NEUTRAL"),"btc_ch":float(data.get("BTC_CH",0)),"locked_tab":False,"fz_start":float(data.get("FREE_ZONE_START",0))}
    cap=float(data.get("FUND_CAP",1000.0)); open_t=data.get("FUND_OPEN",[]); closed=data.get("FUND_CLOSED",[])
    wins=int(data.get("FUND_WINS",0)); losses=int(data.get("FUND_LOSSES",0))
    daily=float(data.get("FUND_DAILY_PNL",0.0)); dg=float(data.get("FUND_DAILY_GROSS",0.0)); df=float(data.get("FUND_DAILY_FEE",0.0))
    profit_bank=float(data.get("FUND_PROFIT_BANK",0.0)); rotate=data.get("ROTATE_COINS",[]); locked=bool(data.get("FUND_DAILY_LOCKED",False)); free_zone=bool(data.get("FREE_ZONE",False)); count100=int(data.get("FREE_ZONE_100_COUNT",0)); fz_start=float(data.get("FREE_ZONE_START",0))
    # FORCE UNLOCK for recovery
    if cap<990:
        locked=False; free_zone=False
    try:
        quick_ch=requests.get(f"{BINANCE_BASE}/api/v3/ticker/24hr?symbol=BTCUSDT",timeout=2).json()
        btc_ch_quick=float(quick_ch.get('priceChangePercent',0))
    except: btc_ch_quick=data.get("BTC_CH",0)
    if free_zone and (btc_ch_quick>0.4 or now - fz_start > 1800):
        free_zone=False; locked=False
    if now-float(data.get("FAST_LAST",0))>120 or len(rotate)==0:
        w,regime,btc_ch=get_real_prices(); rotate=w; data["ROTATE_COINS"]=w; data["FAST_LAST"]=now; data["REGIME"]=regime; data["BTC_CH"]=btc_ch
    else:
        regime=data.get("REGIME","NEUTRAL"); btc_ch=btc_ch_quick if btc_ch_quick!=0 else data.get("BTC_CH",0)
    if not locked and daily>=REAL_TARGET:
        profit_bank+=REAL_TARGET; cap+=REAL_TARGET; count100+=1
        data.update({"FUND_CAP":cap,"FUND_OPEN":[],"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":True,"FREE_ZONE":True,"FREE_ZONE_100_COUNT":count100,"REGIME":regime,"BTC_CH":btc_ch,"FREE_ZONE_START":now})
        rset(data); return {"cap":cap,"open":[],"wins":wins,"losses":losses,"total":wins+losses,"daily":0,"dg":0,"df":0,"rotate":rotate,"bank":profit_bank,"locked":True,"free_zone":True,"count100":count100,"regime":regime,"btc_ch":btc_ch,"fz_start":now}
    if free_zone or locked:
        for tr in open_t:
            cur=get_price_real(tr['cg_id'],tr.get('chain','binance'),float(tr.get('last_price',tr['entry'])),tr.get('token'))
            pct=(cur-float(tr['entry']))/float(tr['entry'])*100 if float(tr['entry'])>0 else 0
            if pct<-5: pct=-5
            gross,fee,net,fee_pct=calc_fees(tr.get('chain','binance'),float(tr.get('pos',POS_SIZE)),pct)
            closed.append({"symbol":tr['symbol'],"pct":pct,"gross":gross,"fee":fee,"net":net,"fee_pct":fee_pct,"peak":float(tr.get('peak_pct',0)),"pos":float(tr.get('pos',POS_SIZE)),"age":int(now-float(tr.get('ts',now))),"type":tr.get('type',''),"chain":tr.get('chain'),"reason":"FREEZE CLOSE"})
            if net>=0: wins+=1
            else: losses+=1
            daily+=net; dg+=gross; df+=fee; cap+=net
        data.update({"FUND_CAP":cap,"FUND_OPEN":[],"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":locked,"FREE_ZONE":free_zone,"FREE_ZONE_100_COUNT":count100,"REGIME":regime,"BTC_CH":btc_ch,"FREE_ZONE_START":fz_start})
        rset(data); return {"cap":cap,"open":[],"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"rotate":rotate,"bank":profit_bank,"locked":locked,"free_zone":free_zone,"count100":count100,"regime":regime,"btc_ch":btc_ch,"fz_start":fz_start}
    new_open=[]
    for tr in list(open_t):
        cur=get_price_real(tr['cg_id'],tr.get('chain','binance'),float(tr.get('last_price',tr['entry'])),tr.get('token')); age=now-float(tr.get('ts',now))
        if age<0: age=0
        pct=(cur-float(tr['entry']))/float(tr['entry'])*100 if float(tr['entry'])>0 else 0
        if pct<-5: pct=-5
        peak=float(tr.get('peak_pct',0))
        if pct>peak: peak=pct; tr['peak_pct']=peak
        gross,fee,net,fee_pct=calc_fees(tr.get('chain','binance'),float(tr.get('pos',POS_SIZE)),pct)
        close=False; reason=""; sl=-2.0; tp=3.0
        if pct<=sl: close=True; reason=f"SL {sl}% NET ${net:.3f}"
        elif pct>=tp: close=True; reason=f"TP {tp}% NET ${net:.3f}"
        elif pct>=1.0 and peak>=1.5 and pct<=peak-0.4: close=True; reason=f"TRAIL {peak:.1f}->{pct:.1f}%"
        elif age>=90: close=True; reason=f"TIME 90s NET ${net:.3f}"
        if close:
            closed.append({"symbol":tr['symbol'],"pct":pct,"gross":gross,"fee":fee,"net":net,"fee_pct":fee_pct,"peak":peak,"pos":float(tr.get('pos',POS_SIZE)),"age":int(age),"type":tr.get('type',''),"chain":tr.get('chain'),"reason":reason})
            if net>=0: wins+=1
            else: losses+=1
            daily+=net; dg+=gross; df+=fee; cap+=net
        else: tr['last_price']=cur; new_open.append(tr)
    if len(new_open)<3:
        syms=set(x['symbol'] for x in new_open)
        for m in rotate:
            if len(new_open)>=3: break
            if m['symbol'] in syms: continue
            new_open.append({"symbol":m['symbol'],"entry":m['price'],"ts":now,"last_price":m['price'],"pos":POS_SIZE,"c1":m['c1'],"cg_id":m['cg_id'],"token":m.get('token'),"chain":m.get('chain','binance'),"peak_pct":0,"type":m['type'],"liquidity":m.get('liquidity',0)})
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":locked,"FREE_ZONE":free_zone,"FREE_ZONE_100_COUNT":count100,"REGIME":regime,"BTC_CH":btc_ch,"FREE_ZONE_START":fz_start})
    rset(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"rotate":rotate,"bank":profit_bank,"locked":locked,"free_zone":free_zone,"count100":count100,"regime":regime,"btc_ch":btc_ch,"fz_start":fz_start}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v722 RECOVER</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#000;color:#fff}.top{background:#111;padding:10px;border-bottom:2px solid #00FF88}.grid{display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr 1fr;gap:1px;background:#222}.card{background:#000;padding:8px;text-align:center}.card b{font-size:12px;display:block}.green{color:#00FF88}.yellow{color:#FFD000}.red{color:#FF4444}.card small{color:#888;font-size:9px}.box{padding:8px;margin:5px;font-size:9px;border:2px solid}.greenbox{border-color:#00FF88;background:#002211;color:#00FF88}.section{padding:8px;border-bottom:1px solid #222}.section h3{color:#00FF88;font-size:10px}.item{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #111;font-size:9px}</style></head><body>
<div class="top"><b>VENUS v722 RECOVER $968 -> $1000 - Binance only, SL -2% max $0.22 loss</b> <span id="time"></span></div>
<div class="grid">
<div class="card"><small>CAP TEST</small><b id="cap" class="green">$1000</b></div>
<div class="card"><small>DAILY NET</small><b id="daily" class="green">+$0</b></div>
<div class="card"><small>GROSS</small><b id="gross" class="yellow">$0</b></div>
<div class="card"><small>FEE REAL</small><b id="fee" class="red">$0</b></div>
<div class="card"><small>W/L/TOTAL</small><b id="wl">0W/0L/0</b></div>
<div class="card"><small>BANK</small><b id="bank" class="green">$0</b></div>
</div>
<div class="box greenbox" id="fzbox">RECOVERY MODE: CAP<990 auto unlock, Binance only, TP 3% SL -2% TIME 90s</div>
<div class="section"><h3>REAL PRICE + REAL FEES</h3><div id="rotate"></div></div>
<div class="section"><h3>OPEN</h3><div id="openlist"></div></div>
<div class="section"><h3>CLOSED</h3><div id="closed"></div></div>
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
 document.getElementById('wl').innerText=j.wins+'W/'+j.losses+'L/'+j.total+(j.locked_tab?' LOCKED':'');
 document.getElementById('bank').innerText='$'+j.bank.toFixed(2);
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' BTC '+ (j.btc_ch||0).toFixed(2)+'% '+j.regime+(j.locked?' LOCKED':'')+(j.free_zone?` FREEZE ${Math.floor((Date.now()/1000-(j.fz_start||0))/60)}min`:'');
 document.getElementById('fzbox').innerText=j.cap<990?`RECOVERY MODE CAP $${j.cap.toFixed(2)}<990 - Auto unlocked - Trading to $1000 - BTC ${(j.btc_ch||0).toFixed(2)}%`:`TRADING - BTC ${(j.btc_ch||0).toFixed(2)}% ${j.regime} - v722 Binance only SL -2%`;
 let rot=document.getElementById('rotate');rot.innerHTML='';
 (j.rotate||[]).forEach(m=>{ rot.innerHTML+=`<div class="item"><div><b>${m.symbol} ${m.chain.toUpperCase()}</b> ${m.c1.toFixed(2)}% VOL ${(m.vol/1000).toFixed(0)}k</div><div>LIQ $${(m.liquidity/1000).toFixed(0)}k</div></div>`; });
 let ol=document.getElementById('openlist');ol.innerHTML='';
 if((j.open||[]).length==0){ ol.innerHTML='<div class="item"><div><b>No open - Recovering</b></div></div>'; }
 (j.open||[]).forEach(t=>{
  let pct=t.entry>0?(t.last_price-t.entry)/t.entry*100:0; if(pct<-5) pct=-5; let fee=0.02; let gross=t.pos*pct/100; let net=gross-fee;
  let age=Math.floor(Date.now()/1000-t.ts); if(age<0) age=0;
  ol.innerHTML+=`<div class="item"><div><b>${t.symbol}</b> ${pct.toFixed(2)}% NET $${net.toFixed(3)} AGE ${age}s</div><div>NET $${net.toFixed(3)}</div></div>`;
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
        data={"cap":968,"open":[],"wins":0,"losses":0,"total":0,"closed":[],"daily":0,"dg":0,"df":0,"rotate":[],"bank":0,"locked":False,"free_zone":False,"count100":0,"regime":"NEUTRAL","btc_ch":0,"fz_start":0}
    d=rget()
    if d is None: d={"FUND_CAP":968.56,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":0,"FUND_DAILY_LOCKED":False,"FREE_ZONE":False,"FREE_ZONE_100_COUNT":0,"REGIME":"NEUTRAL","BTC_CH":0,"FREE_ZONE_START":0}
    return jsonify({"cap":float(data.get("cap",d.get("FUND_CAP",1000))),"open":data.get("open",d.get("FUND_OPEN",[])),"wins":int(data.get("wins",d.get("FUND_WINS",0))),"losses":int(data.get("losses",d.get("FUND_LOSSES",0))),"total":int(data.get("total",d.get("FUND_TOTAL_TRADES",0))),"closed":d.get("FUND_CLOSED",[]),"daily":float(data.get("daily",d.get("FUND_DAILY_PNL",0))),"dg":float(data.get("dg",d.get("FUND_DAILY_GROSS",0))),"df":float(data.get("df",d.get("FUND_DAILY_FEE",0))),"rotate":data.get("rotate",d.get("ROTATE_COINS",[])),"bank":float(data.get("bank",d.get("FUND_PROFIT_BANK",0.0))),"locked":bool(data.get("locked",d.get("FUND_DAILY_LOCKED",False))),"free_zone":bool(data.get("free_zone",d.get("FREE_ZONE",False))),"count100":int(data.get("count100",d.get("FREE_ZONE_100_COUNT",0))),"regime":data.get("regime",d.get("REGIME","NEUTRAL")),"btc_ch":float(data.get("btc_ch",d.get("BTC_CH",0))),"locked_tab":bool(data.get("locked_tab",False)),"fz_start":float(data.get("fz_start",d.get("FREE_ZONE_START",0)))})
@app.route("/api/cron")
def cron():
    try: return jsonify(do_tick())
    except Exception as e: return jsonify({"error":str(e)})
@app.route("/api/reset")
def reset():
    d={"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":0,"FUND_DAILY_LOCKED":False,"FREE_ZONE":False,"FREE_ZONE_100_COUNT":0,"REGIME":"NEUTRAL","BTC_CH":0,"FREE_ZONE_START":0}
    rset(d)
    return jsonify({"ok":True,"msg":"v722 RECOVER - READY"})
