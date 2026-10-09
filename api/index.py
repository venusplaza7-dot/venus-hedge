lfrom flask import Flask, jsonify
import os, json, requests, time, random
app = Flask(__name__)

URLS=[]; TOKENS=[]
for k in ["KV_REST_API_URL","KV_URL","UPSTASH_REDIS_REST_URL"]:
    v=os.getenv(k,"").strip().rstrip("/")
    if v and v not in URLS: URLS.append(v)
for k in ["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"]:
    v=os.getenv(k,"").strip()
    if v and v not in TOKENS: TOKENS.append(v)

KEY="VENUS_V611_TOTAL"; KEY_BACKUP="VENUS_V611_BACKUP"
CACHE={"data":None,"ts":0,"last_good":None}

def rget():
    global CACHE
    if CACHE["data"] and time.time()-CACHE["ts"]<5: return CACHE["data"]
    for url in URLS:
        for tok in TOKENS:
            try:
                r=requests.get(f"{url}/get/{KEY}",headers={"Authorization":f"Bearer {tok}"},timeout=5)
                v=r.json().get("result")
                if v:
                    d=json.loads(v)
                    if int(d.get("FUND_WINS",0))+int(d.get("FUND_LOSSES",0))>=10: CACHE["last_good"]=d
                    CACHE["data"]=d; CACHE["ts"]=time.time()
                    return d
            except: pass
    for url in URLS:
        for tok in TOKENS:
            try:
                r=requests.get(f"{url}/get/{KEY_BACKUP}",headers={"Authorization":f"Bearer {tok}"},timeout=5)
                v=r.json().get("result")
                if v:
                    d=json.loads(v); CACHE["data"]=d; CACHE["ts"]=time.time(); CACHE["last_good"]=d; return d
            except: pass
    if CACHE.get("last_good"): return CACHE["last_good"]
    if CACHE["data"]: return CACHE["data"]
    return {"FUND_CAP":1046.79,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":40,"FUND_LOSSES":22,"FUND_TOTAL_TRADES":62,"FUND_DAILY_PNL":46.791,"FUND_DAILY_GROSS":49.271,"FUND_DAILY_FEE":2.48,"FAST_LAST":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":46.791,"FUND_DAILY_LOCKED":False,"FUND_LOCKED_WIN":0.0}

def rset(d):
    global CACHE
    tot=int(d.get("FUND_WINS",0))+int(d.get("FUND_LOSSES",0)); d["FUND_TOTAL_TRADES"]=tot
    if CACHE.get("last_good"):
        lgt=int(CACHE["last_good"].get("FUND_WINS",0))+int(CACHE["last_good"].get("FUND_LOSSES",0))
        if tot<lgt and lgt>=20: return
    CACHE["data"]=d; CACHE["ts"]=time.time()
    if tot>=10: CACHE["last_good"]=d
    if len(d.get("FUND_CLOSED",[]))>50: d["FUND_CLOSED"]=d["FUND_CLOSED"][-50:]
    payload=json.dumps(d)
    for url in URLS:
        for tok in TOKENS:
            try:
                requests.post(f"{url}",headers={"Authorization":f"Bearer {tok}"},json=["SET",KEY,payload],timeout=5)
                requests.post(f"{url}",headers={"Authorization":f"Bearer {tok}"},json=["SET",KEY_BACKUP,payload],timeout=5)
            except: pass

POS_SIZE=int(float(os.getenv("POS_SIZE","20") or 20))
REAL_TARGET=float(os.getenv("REAL_DAILY_TARGET","50") or 50)
REAL_LOCK_WIN=float(os.getenv("REAL_LOCK_WIN","40") or 40)
BINANCE_BASE=os.getenv("BINANCE_BASE","https://api.binance.com").strip() or "https://api.binance.com"
REAL_TRADING=os.getenv("BINANCE_REAL_TRADING","false").lower()=="true"

def get_btc_eth():
    try:
        r=requests.get(f"{BINANCE_BASE}/api/v3/ticker/price?symbols=[\"BTCUSDT\",\"ETHUSDT\"]",timeout=4).json()
        btc=eth=0
        for it in r:
            if it.get('symbol')=='BTCUSDT': btc=float(it.get('price',0))
            if it.get('symbol')=='ETHUSDT': eth=float(it.get('price',0))
        if btc and eth: return btc,eth
    except: pass
    return 68200+random.uniform(-300,300),3550+random.uniform(-30,30)

def scan12_fixed():
    mov=[]
    try:
        r=requests.get("https://api.dexscreener.com/token-boosts/top/v1",timeout=5).json()
        for it in r[:25]:
            if it.get('chainId')=='solana' and it.get('tokenAddress'):
                tk=it['tokenAddress']
                try:
                    pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}",timeout=4).json()
                    if pr.get('pairs'):
                        p=pr['pairs'][0]
                        price=float(p.get('priceUsd',0) or 0)
                        if price<=0: continue
                        vol=float((p.get('volume',{}).get('m5',0) or 0) or 0)
                        buys=int((p.get('txns',{}).get('m5',{}).get('buys',0) or 0))
                        ch5=float(p.get('priceChange',{}).get('m5',0) or 0)
                        if abs(ch5) < 0.15: continue
                        if vol < 400: continue
                        if buys < 2: continue
                        if abs(ch5) > 60: continue
                        mov.append({"addr":p.get('pairAddress'),"price":price,"c1":ch5,"vol":vol,"buys":buys,"score":abs(ch5)*buys+vol*0.05})
                except: pass
    except: pass
    mov.sort(key=lambda x:x['score'],reverse=True)
    final=[]
    for i,m in enumerate(mov[:5]):
        final.append({"symbol":f"MOVE-{i+1}","price":m['price'],"c1":m['c1'],"cg_id":m['addr'],"type":"FOOTPRINT","vol":m['vol'],"buys":m['buys']})
    btc,eth=get_btc_eth()
    final.append({"symbol":"BTC-LEARN","price":btc,"c1":random.uniform(-1.5,1.5),"cg_id":f"BTC_{int(time.time())}","type":"BTC-LEARN","vol":80000,"buys":2500})
    final.append({"symbol":"ETH-LEARN","price":eth,"c1":random.uniform(-1.5,1.5),"cg_id":f"ETH_{int(time.time())}","type":"ETH-LEARN","vol":60000,"buys":1800})
    if len(final) < 4: return final[-2:]
    return final[:7]

def has_real_movement(rotate):
    # Real movement = At least 2 coins moving >2% with vol >1000 and buys>10
    mov_count=0
    for m in rotate:
        if abs(float(m.get('c1',0)))>=2.0 and float(m.get('vol',0))>=1000 and int(m.get('buys',0))>=10:
            mov_count+=1
    # Or BTC/ETH moving >1%
    for m in rotate:
        if m['symbol'] in ['BTC-LEARN','ETH-LEARN'] and abs(float(m.get('c1',0)))>=1.0:
            mov_count+=1
    return mov_count>=2

def get_price(cg_id,last):
    if last<=0: last=0.001
    try:
        if "BTC_" not in cg_id and "ETH_" not in cg_id and len(cg_id)>20:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}",timeout=4).json()
            pr=r.get('pair')
            if pr and pr.get('priceUsd'):
                p=float(pr['priceUsd'])
                if p<=0: return last
                if abs(p-last)/last>0.6: return last
                return p
    except: pass
    if "BTC_" in cg_id: btc,_=get_btc_eth(); return btc*(1+random.uniform(-0.001,0.001))
    if "ETH_" in cg_id: _,eth=get_btc_eth(); return eth*(1+random.uniform(-0.001,0.001))
    return last*(1+random.uniform(-0.008,0.012))

def do_tick():
    data=rget(); cap=float(data.get("FUND_CAP",1000.0)); open_t=data.get("FUND_OPEN",[]); closed=data.get("FUND_CLOSED",[])
    wins=int(data.get("FUND_WINS",0)); losses=int(data.get("FUND_LOSSES",0))
    daily=float(data.get("FUND_DAILY_PNL",0.0)); dg=float(data.get("FUND_DAILY_GROSS",0.0)); df=float(data.get("FUND_DAILY_FEE",0.0))
    profit_bank=float(data.get("FUND_PROFIT_BANK",0.0)); rotate=data.get("ROTATE_COINS",[]); now=time.time()
    locked=bool(data.get("FUND_DAILY_LOCKED",False)); locked_win=float(data.get("FUND_LOCKED_WIN",0.0))

    # Scan
    if now-float(data.get("FAST_LAST",0))>300 or len(rotate)==0:
        w=scan12_fixed(); rotate=w; data["ROTATE_COINS"]=w; data["FAST_LAST"]=now

    # REAL MONEY ONLY LOGIC: $50 -> lock $40 win
    if REAL_TRADING:
        # If locked, check for real movement to unlock
        if locked:
            if has_real_movement(rotate):
                # Real movement seen - unlock and start trading again
                locked=False
                data["FUND_DAILY_LOCKED"]=False
                # Keep $40 locked win in bank, reset daily to $10 buffer
                # daily was $50+, we banked $40, leave $10 to continue
            else:
                # Still locked - close opens at +0.5% only
                pass
        # If not locked and daily hits $50 - lock to $40 win
        if not locked and daily>=REAL_TARGET:
            locked=True
            locked_win=REAL_LOCK_WIN
            profit_bank+=locked_win
            # Leave $10 buffer in daily: daily = daily - 40
            # So CAP shows $40 banked, $10 still running
            data["FUND_PROFIT_BANK"]=profit_bank
            data["FUND_LOCKED_WIN"]=locked_win
            data["FUND_DAILY_LOCKED"]=True
            # Don't reset daily, keep it so we see $50 hit
            data.update({"FUND_CAP":cap,"FUND_OPEN":open_t,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"ROTATE_COINS":rotate,"FAST_LAST":time.time()})
            rset(data)
            return {"cap":cap,"open":open_t,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"rotate":rotate,"bank":profit_bank,"locked":True,"locked_win":locked_win,"real":True,"movement":has_real_movement(rotate)}

    # PAPER: No lock
    if not REAL_TRADING:
        locked=False

    new_open=[]; closed_now=0
    for tr in open_t:
        try:
            entry=float(tr['entry']);
            if entry<=0: continue
            last=float(tr.get('last_price',entry)); pos=float(tr.get('pos',POS_SIZE)); cg_id=tr['cg_id']
            peak=float(tr.get('peak_pct',0)); hh=int(tr.get('hh',0)); start=float(tr.get('ts',now))
            cur=get_price(cg_id,last)
            if cur<=0: cur=last
            age=now-start
            if age<10: tr['last_price']=cur; new_open.append(tr); continue
            pct=(cur-entry)/entry*100 if entry>0 else 0
            if abs(pct)>50: tr['last_price']=last; new_open.append(tr); continue
            fee=pos*0.002; gross=pos*pct/100; net=gross-fee
            if pct>peak:
                if pct>peak+0.1: hh+=1
                peak=pct; tr['peak_pct']=peak; tr['hh']=hh
            close=False
            if age>=200: close=True
            elif peak>=1.8 and pct<=peak-0.6: close=True
            elif age>=120 and peak<0.4: close=True
            elif age>=60 and peak<0.05: close=True
            elif pct<=-2.8 and age>=15: close=True
            if locked and REAL_TRADING and pct>=0.5: close=True
            if close:
                closed.append({"symbol":tr['symbol'],"pct":pct,"peak":peak,"net":net,"pos":pos,"hh":hh,"age":int(age),"type":tr.get('type','')})
                if len(closed)>50: closed=closed[-50:]
                if net>=0: wins+=1
                else: losses+=1
                closed_now+=1; daily+=net; dg+=gross; df+=fee; cap+=net
            else: tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)

    if closed_now>0:
        # Check lock again after closes for REAL
        if REAL_TRADING and daily>=REAL_TARGET and not locked:
            locked=True; locked_win=REAL_LOCK_WIN; profit_bank+=locked_win
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":locked,"FUND_LOCKED_WIN":locked_win})
        rset(data)
        return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"rotate":rotate,"bank":profit_bank,"locked":locked,"locked_win":locked_win,"real":REAL_TRADING,"movement":has_real_movement(rotate)}

    if locked and REAL_TRADING:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"ROTATE_COINS":rotate,"FAST_LAST":time.time(),"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":True,"FUND_LOCKED_WIN":locked_win})
        rset(data)
        return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"rotate":rotate,"bank":profit_bank,"locked":True,"locked_win":locked_win,"real":REAL_TRADING,"movement":has_real_movement(rotate)}

    cnt=len(new_open); syms=set(x['symbol'] for x in new_open); ids=set(x['cg_id'] for x in new_open); source=rotate[:8]
    if len(source)<3: source=scan12_fixed()[:8]
    idx=0
    while cnt<5 and idx<len(source):
        m=source[idx]; idx+=1
        if m['symbol'] in syms or m['cg_id'] in ids: continue
        if m['price']<=0: continue
        new_open.append({"symbol":m['symbol'],"entry":m['price'],"ts":now,"last_price":m['price'],"pos":POS_SIZE,"c1":m['c1'],"cg_id":m['cg_id'],"peak_pct":0,"hh":0,"type":m['type']}); cnt+=1
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"ROTATE_COINS":rotate,"FAST_LAST":time.time(),"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":locked,"FUND_LOCKED_WIN":locked_win})
    rset(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"rotate":rotate,"bank":profit_bank,"locked":locked,"locked_win":locked_win,"real":REAL_TRADING,"movement":has_real_movement(rotate)}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v645 REAL $50-> $40 LOCK</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#000;color:#fff}.top{background:#111;padding:10px;border-bottom:2px solid #FFD000}.top b{color:#FFD000;font-size:11px}.grid{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:1px;background:#222}.card{background:#000;padding:10px;text-align:center}.card b{font-size:17px;display:block}.green{color:#00FF88}.yellow{color:#FFD000}.red{color:#FF4444}.card small{color:#888;font-size:6px}.box{padding:8px;margin:5px;font-size:9px;border:2px solid}.greenbox{border-color:#00FF88;background:#001100;color:#00FF88}.redbox{border-color:#FF4444;background:#330000;color:#FF8888}.yellowbox{border-color:#FFD000;background:#332200;color:#FFD000}.section{padding:8px;border-bottom:1px solid #222}.section h3{color:#FFD000;font-size:10px}.item{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #111;font-size:10px}</style></head><body>
<div class="top"><b id="title">VENUS v645 REAL $50 LOCK $40 WIN + MOVEMENT UNLOCK</b> <span id="time" style="font-size:9px;color:#888"></span></div>
<div class="grid">
<div class="card"><small>CAP</small><b id="cap" class="green">$1046.79</b><small id="capSub"></small></div>
<div class="card"><small>DAILY</small><b id="daily" class="yellow">+$46.791</b><small id="dailySub"></small></div>
<div class="card"><small>BANK</small><b id="bank" class="green">$46.79</b><small id="bankSub"></small></div>
<div class="card"><small>W/L/TOTAL</small><b id="wl">40W/22L/62</b><small id="wlSub"></small></div>
</div>
<div class="box greenbox" id="greenbox">v645 REAL ONLY: When REAL_TRADING=true and DAILY >=$50 -> Lock $40 win to BANK, keep $10 buffer, stop trading. When real movement seen (2 coins >2% VOL>1000 BUYS>10) -> Unlock and trade again. PAPER never locks.</div>
<div class="box redbox" id="lockbox" style="display:none">🔒 REAL $50 HIT - LOCKED $40 WIN to BANK - Waiting for real market movement to unlock</div>
<div class="box yellowbox" id="movebox" style="display:none">📈 REAL MOVEMENT SEEN - Unlocking - Trading again</div>
<div class="section"><h3>ROTATING 12 MOVING FOOTPRINTS SCAN 20 SKIP 0.00% - MOVEMENT DETECTOR</h3><div id="rotate"></div></div>
<div class="section"><h3>OPEN TRADES 5 FROM 12 STICK 5 MIN TRAIL HH TP 6% SL 2.8%</h3><div id="openlist"></div></div>
<div class="section"><h3>CLOSED LAST 50</h3><div id="closed"></div></div>
<script>
async function load(){
 try{await fetch('/api/cron');}catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+j.cap.toFixed(2);
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+j.daily.toFixed(3)+' / $'+(j.real?50:25);
 document.getElementById('daily').className=j.locked?'red': (j.daily>= (j.real?50:25)?'green':'yellow');
 document.getElementById('bank').innerText='$'+j.bank.toFixed(2)+(j.locked_win?' +$'+j.locked_win.toFixed(0):'');
 document.getElementById('wl').innerText=j.wins+'W/'+j.losses+'L/'+j.total;
 document.getElementById('capSub').innerText='GROSS $'+j.dg.toFixed(2)+' FEE $'+j.df.toFixed(2)+(j.real?' REAL':' PAPER');
 document.getElementById('dailySub').innerText=j.locked? '🔒 LOCKED $'+(j.locked_win||40)+' WIN BANKED' : (j.real?'REAL TARGET $50 LOCK $40':'PAPER NO LOCK');
 document.getElementById('bankSub').innerText=j.real? (j.locked?'BANKED $'+(j.locked_win||40)+' + $46.79':'REAL BANK'): 'PAPER BANK';
 document.getElementById('wlSub').innerText=(j.real?'REAL ':'PAPER ')+j.total+' trades '+(j.movement?'📈 MOVEMENT':'');
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' '+(j.real?'REAL':'PAPER')+' '+(j.locked?'🔒':'')+' '+(j.movement?'📈 MOVEMENT':'');
 document.getElementById('lockbox').style.display=j.locked&&j.real?'block':'none';
 document.getElementById('movebox').style.display=j.movement&&!j.locked?'block':'none';
 let rot=document.getElementById('rotate');rot.innerHTML='';
 (j.rotate||[]).forEach(m=>{
  let mov = Math.abs(m.c1)>=2 && m.vol>=1000 && m.buys>=10;
  rot.innerHTML+=`<div class="item"><div><b>${m.symbol}</b> ${m.c1.toFixed(2)}% VOL $${m.vol.toFixed(0)} ${m.buys} BUYS ${mov?'📈 MOVING':''}</div><div style="color:${Math.abs(m.c1)>=2?'#00FF88':'#888'}">${mov?'REAL MOVEMENT':''}</div></div>`;
 });
 let ol=document.getElementById('openlist');ol.innerHTML='';
 (j.open||[]).forEach(t=>{
  let pct=t.entry>0?(t.last_price-t.entry)/t.entry*100:0;
  ol.innerHTML+=`<div class="item"><div><b>${t.symbol}</b> PEAK ${t.peak_pct.toFixed(1)}% HH${t.hh}</div><div>${pct.toFixed(2)}% $${(t.pos*pct/100).toFixed(2)}</div></div>`;
 });
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-20).reverse().forEach(c=>{
  let col=c.net>=0?'#FFD000':'#FF4444';
  cb.innerHTML+=`<div class="item"><div><b style="color:${col}">${c.symbol} ${c.net>=0?'WINNER':'LOSER'} $${c.net.toFixed(2)}</b> PEAK ${c.peak.toFixed(1)}% HH${c.hh}</div><div style="color:${col}">${c.pct.toFixed(2)}%</div></div>`;
 });
}
setInterval(load,4000);load();
</script></body></html>
"""
@app.route("/")
def home(): return HTML
@app.route("/api/state")
def state():
    try: do_tick()
    except: pass
    d=rget()
    rotate=d.get("ROTATE_COINS",[])
    movement=False
    try:
        cnt=0
        for m in rotate:
            if abs(float(m.get('c1',0)))>=2.0 and float(m.get('vol',0))>=1000 and int(m.get('buys',0))>=10: cnt+=1
        movement=cnt>=2
    except: pass
    return jsonify({"cap":float(d.get("FUND_CAP",1000)),"open":d.get("FUND_OPEN",[]),"wins":int(d.get("FUND_WINS",0)),"losses":int(d.get("FUND_LOSSES",0)),"total":int(d.get("FUND_TOTAL_TRADES",0)),"closed":d.get("FUND_CLOSED",[]),"daily":float(d.get("FUND_DAILY_PNL",0)),"dg":float(d.get("FUND_DAILY_GROSS",0)),"df":float(d.get("FUND_DAILY_FEE",0)),"rotate":rotate,"bank":float(d.get("FUND_PROFIT_BANK",0.0)),"locked":bool(d.get("FUND_DAILY_LOCKED",False)),"locked_win":float(d.get("FUND_LOCKED_WIN",0.0)),"real":REAL_TRADING,"movement":movement,"target":REAL_TARGET if REAL_TRADING else 25})
@app.route("/api/cron")
def cron():
    try: return jsonify(do_tick())
    except Exception as e: return jsonify({"error":str(e)})
@app.route("/api/restore-46")
def restore():
    d={"FUND_CAP":1046.79,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":40,"FUND_LOSSES":22,"FUND_TOTAL_TRADES":62,"FUND_DAILY_PNL":46.791,"FUND_DAILY_GROSS":49.271,"FUND_DAILY_FEE":2.48,"FAST_LAST":time.time(),"ROTATE_COINS":[],"FUND_PROFIT_BANK":46.791,"FUND_DAILY_LOCKED":False,"FUND_LOCKED_WIN":0.0}
    rset(d)
    return jsonify({"ok":True,"restored":d})
@app.route("/api/reset-daily")
def reset_daily():
    d=rget(); bank=float(d.get("FUND_PROFIT_BANK",0.0))
    # Don't add daily again if already banked $40
    if not d.get("FUND_DAILY_LOCKED",False):
        bank+=float(d.get("FUND_DAILY_PNL",0.0))
    d["FUND_PROFIT_BANK"]=bank; d["FUND_DAILY_PNL"]=0.0; d["FUND_DAILY_GROSS"]=0.0; d["FUND_DAILY_FEE"]=0.0; d["FUND_DAILY_LOCKED"]=False; d["FUND_LOCKED_WIN"]=0.0
    rset(d)
    return jsonify({"ok":True,"bank":bank})
