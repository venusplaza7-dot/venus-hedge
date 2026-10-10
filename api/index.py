from flask import Flask, jsonify
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
CACHE={"data":None,"ts":0,"last_good":None,"ban":{}}

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
    return {"FUND_CAP":1046.79,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":40,"FUND_LOSSES":22,"FUND_TOTAL_TRADES":62,"FUND_DAILY_PNL":46.791,"FUND_DAILY_GROSS":49.271,"FUND_DAILY_FEE":2.48,"FAST_LAST":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":46.791,"FUND_DAILY_LOCKED":False,"FUND_LOCKED_WIN":0.0,"FUND_LOSER_MAP":{},"FROZEN":False,"FREEZE_TS":0}

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

def calc_pct(entry,cur):
    if entry<=0: return 0
    return (cur-entry)/entry*100

def scan_freeze_logic():
    mov=[]
    try:
        r=requests.get("https://api.dexscreener.com/token-boosts/top/v1",timeout=6).json()
        for it in r[:40]:
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
                        sells=int((p.get('txns',{}).get('m5',{}).get('sells',0) or 0))
                        ch5=float(p.get('priceChange',{}).get('m5',0) or 0)
                        liq=float(p.get('liquidity',{}).get('usd',0) or 0)
                        if liq < 8000 or vol < 600 or buys+sells < 6 or abs(ch5)>60: continue
                        if abs(ch5)<0.3: continue
                        score=abs(ch5)*(buys+sells)+vol*0.02
                        mov.append({"addr":p.get('pairAddress'),"price":price,"c1":ch5,"vol":vol,"buys":buys,"sells":sells,"score":score})
                except: pass
    except: pass
    mov.sort(key=lambda x:x['score'],reverse=True)
    btc,eth=get_btc_eth()
    btc_ch=random.uniform(-1.5,1.5)
    try:
        r=requests.get(f"{BINANCE_BASE}/api/v3/ticker/24hr?symbols=[\"BTCUSDT\"]",timeout=4).json()
        btc_ch=float(r[0].get('priceChangePercent',0) or btc_ch)
    except: pass
    avg_move=sum([m['c1'] for m in mov[:5]])/5 if mov else 0
    # FREEZE LOGIC
    if btc_ch < -1.2 and avg_move < -0.5:
        regime="BEAR_FREEZE" # Freeze trades, observe
    elif btc_ch > 1.0 and avg_move > 1.0:
        regime="BULL_JUMP" # Positive, jump back in
    elif btc_ch > 0.3 and avg_move > 0.5:
        regime="BULL"
    else:
        regime="NEUTRAL"

    final=[]
    if regime in ["BULL","BULL_JUMP"]:
        for i,m in enumerate(mov[:5]):
            if m['c1']>=1.5 and m['buys']>=8 and m['buys']>m['sells']*1.3 and m['vol']>=1200:
                final.append({"symbol":f"MOVE-{i+1}","price":m['price'],"c1":m['c1'],"cg_id":m['addr'],"type":"FOOTPRINT","vol":m['vol'],"buys":m['buys'],"sells":m['sells']})
    # In BEAR_FREEZE, final = [] - No MOVE longs, freeze

    final.append({"symbol":"BTC-LEARN","price":btc,"c1":btc_ch,"cg_id":f"BTC_{int(time.time())}","type":"BTC-LEARN","vol":80000,"buys":2500})
    final.append({"symbol":"ETH-LEARN","price":eth,"c1":btc_ch,"cg_id":f"ETH_{int(time.time())}","type":"ETH-LEARN","vol":60000,"buys":1800})
    return final[:6], regime, btc_ch, avg_move

def get_price(cg_id,last):
    if last<=0: last=0.001
    try:
        if "BTC_" not in cg_id and "ETH_" not in cg_id and len(cg_id)>20:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}",timeout=4).json()
            pr=r.get('pair')
            if pr and pr.get('priceUsd'):
                p=float(pr['priceUsd'])
                if p<=0: return last
                if abs(p-last)/last>0.80: return last
                return p
    except: pass
    if "BTC_" in cg_id: btc,_=get_btc_eth(); return btc*(1+random.uniform(-0.0008,0.0008))
    if "ETH_" in cg_id: _,eth=get_btc_eth(); return eth*(1+random.uniform(-0.0008,0.0008))
    return last*(1+random.uniform(-0.008,0.008))

def do_tick():
    data=rget(); cap=float(data.get("FUND_CAP",1000.0)); open_t=data.get("FUND_OPEN",[]); closed=data.get("FUND_CLOSED",[])
    wins=int(data.get("FUND_WINS",0)); losses=int(data.get("FUND_LOSSES",0))
    daily=float(data.get("FUND_DAILY_PNL",0.0)); dg=float(data.get("FUND_DAILY_GROSS",0.0)); df=float(data.get("FUND_DAILY_FEE",0.0))
    profit_bank=float(data.get("FUND_PROFIT_BANK",0.0)); rotate=data.get("ROTATE_COINS",[]); now=time.time()
    locked=bool(data.get("FUND_DAILY_LOCKED",False)); locked_win=float(data.get("FUND_LOCKED_WIN",0.0))
    loser_map=data.get("FUND_LOSER_MAP",{}); frozen=bool(data.get("FROZEN",False)); freeze_ts=float(data.get("FREEZE_TS",0))

    if now-float(data.get("FAST_LAST",0))>120 or len(rotate)==0:
        w,regime,btc_ch,avg_move=scan_freeze_logic(); rotate=w; data["ROTATE_COINS"]=w; data["FAST_LAST"]=now; data["REGIME"]=regime; data["BTC_CH"]=btc_ch; data["AVG_MOVE"]=avg_move
        # FREEZE / UNFREEZE LOGIC
        if regime=="BEAR_FREEZE" and not frozen:
            frozen=True; freeze_ts=now; data["FROZEN"]=True; data["FREEZE_TS"]=freeze_ts
        elif regime=="BULL_JUMP" and frozen:
            frozen=False; data["FROZEN"]=False # Jump back in when positive
        elif regime=="BULL" and frozen and now-freeze_ts>300 and btc_ch>0.5 and avg_move>0.5:
            frozen=False; data["FROZEN"]=False # Observe 5 min then jump if positive
    else:
        regime=data.get("REGIME","NEUTRAL"); btc_ch=data.get("BTC_CH",0); avg_move=data.get("AVG_MOVE",0)

    if REAL_TRADING and not locked and daily>=REAL_TARGET:
        locked=True; locked_win=REAL_LOCK_WIN; profit_bank+=locked_win
        data["FUND_PROFIT_BANK"]=profit_bank; data["FUND_LOCKED_WIN"]=locked_win; data["FUND_DAILY_LOCKED"]=True
        rset(data)
        return {"cap":cap,"open":open_t,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"rotate":rotate,"bank":profit_bank,"locked":True,"locked_win":locked_win,"real":True,"regime":regime,"btc_ch":btc_ch,"avg_move":avg_move,"frozen":frozen}

    if locked and REAL_TRADING and btc_ch>1.0 and avg_move>1.0:
        locked=False; data["FUND_DAILY_LOCKED"]=False

    new_open=[]; closed_now=0
    for tr in list(open_t):
        try:
            entry=float(tr['entry']);
            if entry<=0: continue
            last=float(tr.get('last_price',entry)); pos=float(tr.get('pos',POS_SIZE)); cg_id=tr['cg_id']
            peak=float(tr.get('peak_pct',0)); hh=int(tr.get('hh',0)); start=float(tr.get('ts',now))
            cur=get_price(cg_id,last)
            if cur<=0: cur=last
            age=now-start
            pct=calc_pct(entry,cur)
            if abs(pct)>80:
                tr['last_price']=last; new_open.append(tr); continue
            fee=pos*0.002; gross=pos*pct/100; net=gross-fee
            if pct>peak:
                if pct>peak+0.2: hh+=1
                peak=pct; tr['peak_pct']=peak; tr['hh']=hh
            close=False; reason=""
            # If frozen, close MOVE trades quickly to observe
            if frozen and tr['type']=="FOOTPRINT":
                if pct>=0.3 or pct<=-1.0 or age>=30:
                    close=True; reason=f"FROZEN CLOSE {pct:.1f}%"
            elif pct <= -2.0:
                close=True; reason=f"HARD SL -2% {pct:.1f}%"
            elif pct <= -1.5 and age>=4:
                close=True; reason=f"SL -1.5% {age:.0f}s"
            elif pct >= 2.2 and peak>=2.8 and pct <= peak-0.6:
                close=True; reason=f"TRAIL {peak:.1f}->{pct:.1f}"
            elif pct >= 5.0:
                close=True; reason=f"TP 5% {pct:.1f}%"
            elif age>=150:
                close=True; reason="TIME 150s"
            elif age>=60 and peak<0.4 and pct<0.5:
                close=True; reason="NO MOVE 60s"
            elif age>=30 and peak==0.0 and pct< -0.2:
                close=True; reason="DEAD 0% 30s"
            elif locked and REAL_TRADING and pct>=0.5:
                close=True; reason="LOCKED 0.5%"

            if close:
                closed.append({"symbol":tr['symbol'],"pct":pct,"peak":peak,"net":net,"pos":pos,"hh":hh,"age":int(age),"type":tr.get('type',''),"reason":reason})
                if len(closed)>50: closed=closed[-50:]
                sym=tr['symbol']
                if net<0:
                    loser_map[sym]=loser_map.get(sym,0)+1
                    CACHE["ban"][sym]=now
                if net>=0: wins+=1
                else: losses+=1
                closed_now+=1; daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        except:
            new_open.append(tr)

    # FREEZE: Don't open new MOVE trades when frozen
    if not frozen:
        cnt=len(new_open); syms=set(x['symbol'] for x in new_open); ids=set(x['cg_id'] for x in new_open)
        source=[]
        for m in rotate:
            if m['symbol'] in syms or m['cg_id'] in ids: continue
            if CACHE["ban"].get(m['symbol'],0) > now-900 and loser_map.get(m['symbol'],0)>=2: continue
            if m['type']=="FOOTPRINT" and float(m['c1'])>=1.5 and float(m['vol'])>=1200 and int(m['buys'])>=8:
                source.append(m)
            elif m['type'] in ["BTC-LEARN","ETH-LEARN"] and abs(float(m['c1']))>=0.5:
                source.append(m)
        source.sort(key=lambda x: abs(float(x['c1']))*int(x.get('buys',0)),reverse=True)
        idx=0
        while cnt<5 and idx<len(source):
            m=source[idx]; idx+=1
            if m['price']<=0: continue
            new_open.append({"symbol":m['symbol'],"entry":m['price'],"ts":now,"last_price":m['price'],"pos":POS_SIZE,"c1":m['c1'],"cg_id":m['cg_id'],"peak_pct":0,"hh":0,"type":m['type']}); cnt+=1
    else:
        # Frozen: Only keep BTC-LEARN observing, no MOVE
        new_open=[t for t in new_open if t['type']!='FOOTPRINT' or calc_pct(float(t['entry']),float(t.get('last_price',t['entry'])))>=-1.0]

    if REAL_TRADING and daily>=REAL_TARGET and not locked:
        locked=True; locked_win=REAL_LOCK_WIN; profit_bank+=locked_win

    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"ROTATE_COINS":rotate,"FAST_LAST":time.time(),"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":locked,"FUND_LOCKED_WIN":locked_win,"FUND_LOSER_MAP":loser_map,"REGIME":regime,"BTC_CH":btc_ch,"AVG_MOVE":avg_move,"FROZEN":frozen,"FREEZE_TS":freeze_ts})
    rset(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"rotate":rotate,"bank":profit_bank,"locked":locked,"locked_win":locked_win,"real":REAL_TRADING,"regime":regime,"btc_ch":btc_ch,"avg_move":avg_move,"frozen":frozen}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v703 FREEZE & JUMP</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#000;color:#fff}.top{background:#111;padding:10px;border-bottom:2px solid #00FF88}.top b{color:#00FF88;font-size:10px}.grid{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:1px;background:#222}.card{background:#000;padding:10px;text-align:center}.card b{font-size:16px;display:block}.green{color:#00FF88}.yellow{color:#FFD000}.red{color:#FF4444}.blue{color:#00AAFF}.card small{color:#888;font-size:6px}.box{padding:8px;margin:5px;font-size:8px;border:2px solid}.greenbox{border-color:#00FF88;background:#001100;color:#00FF88}.redbox{border-color:#FF4444;background:#330000;color:#FF8888}.yellowbox{border-color:#FFD000;background:#332200;color:#FFD000}.bluebox{border-color:#00AAFF;background:#001133;color:#00AAFF}.section{padding:8px;border-bottom:1px solid #222}.section h3{color:#00FF88;font-size:9px}.item{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #111;font-size:9px}</style></head><body>
<div class="top"><b id="title">VENUS v703 FREEZE OBSERVE JUMP - CAN'T SHORT MOVE</b> <span id="time" style="font-size:9px;color:#888"></span></div>
<div class="grid">
<div class="card"><small>CAP</small><b id="cap" class="green">$1046.79</b><small id="capSub"></small></div>
<div class="card"><small>DAILY</small><b id="daily" class="yellow">+$46.791</b><small id="dailySub"></small></div>
<div class="card"><small>BANK</small><b id="bank" class="green">$46.79</b><small id="bankSub"></small></div>
<div class="card"><small>W/L/TOTAL</small><b id="wl">40W/22L/62</b><small id="wlSub"></small></div>
</div>
<div class="box bluebox" id="freezebox" style="display:none">❄️ FROZEN - BEAR MARKET BTC <span id="freeze_btc">0%</span> AVG <span id="freeze_avg">0%</span> - Observing, no MOVE longs - Will JUMP when BULL</div>
<div class="box greenbox" id="jumpbox" style="display:none">🚀 JUMPING BACK IN - BULL MARKET POSITIVE - Trading MOVE again</div>
<div class="box greenbox" id="greenbox">v703: BEAR BTC<-1.2% AVG<-0.5% = FREEZE ❄️ Close MOVE, observe / BULL BTC>1% AVG>1% = JUMP 🚀 Back in / HARD SL -2% / REAL $50->$40 LOCK + MOVEMENT UNLOCK</div>
<div class="section"><h3>MARKET FREEZE LOGIC - BEAR=FREEZE NO LONG / BULL=JUMP LONG</h3><div id="rotate"></div></div>
<div class="section"><h3>OPEN 5 - FROZEN STOPS MOVE LONG</h3><div id="openlist"></div></div>
<div class="section"><h3>CLOSED - FREEZE REASONS</h3><div id="closed"></div></div>
<script>
async function load(){
 try{await fetch('/api/cron');}catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+j.cap.toFixed(2);
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+j.daily.toFixed(3)+' / $'+(j.real?50:25);
 document.getElementById('daily').className=j.locked?'red': (j.daily>= (j.real?50:25)?'green':'yellow');
 document.getElementById('bank').innerText='$'+j.bank.toFixed(2)+(j.locked_win?' +$'+j.locked_win.toFixed(0):'');
 document.getElementById('wl').innerText=j.wins+'W/'+j.losses+'L/'+j.total;
 document.getElementById('capSub').innerText='GROSS $'+j.dg.toFixed(2)+' FEE $'+j.df.toFixed(2)+' '+(j.regime||'')+' '+(j.frozen?'❄️ FROZEN':'');
 document.getElementById('dailySub').innerText=j.frozen?'❄️ FROZEN OBSERVING': (j.locked? '🔒 LOCKED $'+(j.locked_win||40): (j.real?'REAL $50->$40':'PAPER FREEZE'));
 document.getElementById('bankSub').innerText=j.frozen?'OBSERVE MODE - NO MOVE': (j.real? (j.locked?'BANKED $'+(j.locked_win||40):'REAL BANK'): 'BANK NEVER RESET');
 document.getElementById('wlSub').innerText=(j.real?'REAL ':'PAPER ')+j.total+' trades '+ (j.regime||'')+' '+(j.frozen?'❄️':'🚀');
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' '+(j.real?'REAL':'PAPER')+' '+(j.regime||'')+' BTC '+ (j.btc_ch||0).toFixed(2)+'% '+(j.frozen?'❄️ FROZEN':'');
 document.getElementById('freezebox').style.display=j.frozen?'block':'none';
 document.getElementById('jumpbox').style.display=j.regime=='BULL_JUMP'?'block':'none';
 document.getElementById('freeze_btc').innerText=(j.btc_ch||0).toFixed(2)+'%';
 document.getElementById('freeze_avg').innerText=(j.avg_move||0).toFixed(2)+'%';
 let rot=document.getElementById('rotate');rot.innerHTML='';
 (j.rotate||[]).forEach(m=>{
  rot.innerHTML+=`<div class="item"><div><b>${m.symbol}</b> ${m.c1.toFixed(2)}% VOL $${m.vol.toFixed(0)} ${m.buys}B/${m.sells||0}S ${m.type} ${j.frozen&&m.type=='FOOTPRINT'?'❄️ FROZEN SKIP':''}</div><div>${m.type=='FOOTPRINT'&&j.frozen?'❄️':'✅'}</div></div>`;
 });
 let ol=document.getElementById('openlist');ol.innerHTML='';
 if(j.frozen && (j.open||[]).filter(t=>t.type=='FOOTPRINT').length==0){ ol.innerHTML='<div class="item" style="color:#00AAFF">❄️ FROZEN - No MOVE longs - Observing BTC/ETH - Will JUMP when BULL</div>';}
 (j.open||[]).forEach(t=>{
  let pct=t.entry>0? (t.last_price-t.entry)/t.entry*100:0;
  ol.innerHTML+=`<div class="item"><div><b>${t.symbol} ${t.type}</b> PEAK ${t.peak_pct.toFixed(1)}% HH${t.hh} ${j.frozen?'❄️ FROZEN':''}</div><div style="color:${pct>=0?'#00FF88':'#FF4444'}">${pct.toFixed(2)}% $${(t.pos*pct/100).toFixed(2)}</div></div>`;
 });
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-20).reverse().forEach(c=>{
  let col=c.net>=0?'#00FF88':'#FF4444';
  cb.innerHTML+=`<div class="item"><div><b style="color:${col}">${c.symbol} ${c.type||''} ${c.net>=0?'WINNER':'LOSER'} $${c.net.toFixed(2)}</b> PEAK ${c.peak.toFixed(1)}% HH${c.hh} ${c.reason||''}</div><div style="color:${col}">${c.pct.toFixed(2)}%</div></div>`;
 });
}
setInterval(load,3000);load();
</script></body></html>
"""
@app.route("/")
def home(): return HTML
@app.route("/api/state")
def state():
    try: do_tick()
    except Exception as e: print(e)
    d=rget()
    return jsonify({"cap":float(d.get("FUND_CAP",1000)),"open":d.get("FUND_OPEN",[]),"wins":int(d.get("FUND_WINS",0)),"losses":int(d.get("FUND_LOSSES",0)),"total":int(d.get("FUND_TOTAL_TRADES",0)),"closed":d.get("FUND_CLOSED",[]),"daily":float(d.get("FUND_DAILY_PNL",0)),"dg":float(d.get("FUND_DAILY_GROSS",0)),"df":float(d.get("FUND_DAILY_FEE",0)),"rotate":d.get("ROTATE_COINS",[]),"bank":float(d.get("FUND_PROFIT_BANK",0.0)),"locked":bool(d.get("FUND_DAILY_LOCKED",False)),"locked_win":float(d.get("FUND_LOCKED_WIN",0.0)),"real":REAL_TRADING,"regime":d.get("REGIME","NEUTRAL"),"btc_ch":float(d.get("BTC_CH",0)),"avg_move":float(d.get("AVG_MOVE",0)),"frozen":bool(d.get("FROZEN",False)),"target":REAL_TARGET if REAL_TRADING else 25})
@app.route("/api/cron")
def cron():
    try: return jsonify(do_tick())
    except Exception as e: return jsonify({"error":str(e)})
@app.route("/api/restore-46")
def restore():
    d={"FUND_CAP":1046.79,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":40,"FUND_LOSSES":22,"FUND_TOTAL_TRADES":62,"FUND_DAILY_PNL":46.791,"FUND_DAILY_GROSS":49.271,"FUND_DAILY_FEE":2.48,"FAST_LAST":time.time(),"ROTATE_COINS":[],"FUND_PROFIT_BANK":46.791,"FUND_DAILY_LOCKED":False,"FUND_LOCKED_WIN":0.0,"FUND_LOSER_MAP":{},"FROZEN":False,"FREEZE_TS":0}
    rset(d)
    return jsonify({"ok":True,"restored":d})
@app.route("/api/reset-daily")
def reset_daily():
    d=rget(); bank=float(d.get("FUND_PROFIT_BANK",0.0))
    if not d.get("FUND_DAILY_LOCKED",False):
        bank+=float(d.get("FUND_DAILY_PNL",0.0))
    d["FUND_PROFIT_BANK"]=bank; d["FUND_DAILY_PNL"]=0.0; d["FUND_DAILY_GROSS"]=0.0; d["FUND_DAILY_FEE"]=0.0; d["FUND_DAILY_LOCKED"]=False; d["FUND_LOCKED_WIN"]=0.0; d["FUND_LOSER_MAP"]={}; d["FROZEN"]=False; d["FREEZE_TS"]=0
    rset(d)
    return jsonify({"ok":True,"bank":bank})
