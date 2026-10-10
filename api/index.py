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

KEY="VENUS_V712_FEES_FIXED"; KEY_BACKUP="VENUS_V712_FEES_BACKUP"
CACHE={"data":None,"ts":0,"last_good":None}

def rget():
    global CACHE
    if CACHE["data"] and time.time()-CACHE["ts"]<10: return CACHE["data"]
    for url in URLS:
        for tok in TOKENS:
            try:
                r=requests.get(f"{url}/get/{KEY}",headers={"Authorization":f"Bearer {tok}"},timeout=5)
                v=r.json().get("result")
                if v:
                    d=json.loads(v); CACHE["data"]=d; CACHE["ts"]=time.time(); CACHE["last_good"]=d; return d
            except: pass
    if CACHE.get("last_good"): return CACHE["last_good"]
    if CACHE["data"]: return CACHE["data"]
    return {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":0,"FUND_DAILY_LOCKED":False,"FREE_ZONE":False,"FREE_ZONE_100_COUNT":0,"REGIME":"NEUTRAL","BTC_CH":0}

def rset(d):
    global CACHE
    CACHE["data"]=d; CACHE["ts"]=time.time(); CACHE["last_good"]=d
    if len(d.get("FUND_CLOSED",[]))>50: d["FUND_CLOSED"]=d["FUND_CLOSED"][-50:]
    payload=json.dumps(d)
    for url in URLS:
        for tok in TOKENS:
            try:
                requests.post(f"{url}",headers={"Authorization":f"Bearer {tok}"},json=["SET",KEY,payload],timeout=5)
                requests.post(f"{url}",headers={"Authorization":f"Bearer {tok}"},json=["SET",KEY_BACKUP,payload],timeout=5)
            except: pass

POS_SIZE=10
REAL_TARGET=10
BINANCE_BASE="https://api.binance.com"

def calc_fees(chain, pos_usd, gross_pct):
    if chain=="binance":
        fee_usd=pos_usd*0.002
        gross_usd=pos_usd*gross_pct/100
        net_usd=gross_usd-fee_usd
        return gross_usd, fee_usd, net_usd, 0.2
    else:
        fee_usd=pos_usd*0.008+0.02
        gross_usd=pos_usd*gross_pct/100
        net_usd=gross_usd-fee_usd
        return gross_usd, fee_usd, net_usd, 0.8

def get_real_prices():
    binance_coins=[]
    try:
        coins=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT"]
        # FIX 1: URL encode symbols array for Binance
        sym_param=urllib.parse.quote(json.dumps(coins))
        url=f"{BINANCE_BASE}/api/v3/ticker/24hr?symbols={sym_param}"
        r=requests.get(url,timeout=6).json()
        # Fallback if Binance returns error with symbols param
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
                if price<=0 or vol<1000000: continue
                binance_coins.append({"symbol":it['symbol'].replace('USDT',''),"price":price,"c1":ch/6,"vol":vol,"cg_id":it['symbol'],"type":"BINANCE_REAL","chain":"binance","score":abs(ch),"liquidity":vol})
            except: pass
    except Exception as e:
        print(f"Binance err {e}")

    sol_coins=[]
    try:
        r=requests.get("https://api.dexscreener.com/token-boosts/top/v1",timeout=6).json()
        for it in r[:15]:
            if it.get('chainId')=='solana' and it.get('tokenAddress'):
                token=it['tokenAddress']
                try:
                    pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}",timeout=4).json()
                    if not pr.get('pairs'): continue
                    p=pr['pairs'][0]
                    price=float(p.get('priceUsd',0) or 0)
                    ch5=float(p.get('priceChange',{}).get('m5',0) or 0)
                    vol=float(p.get('volume',{}).get('m5',0) or 0)
                    buys=int(p.get('txns',{}).get('m5',{}).get('buys',0) or 0)
                    sells=int(p.get('txns',{}).get('m5',{}).get('sells',0) or 0)
                    liq=float(p.get('liquidity',{}).get('usd',0) or 0)
                    if price<=0 or vol<5000 or buys+sells<20 or liq<10000 or abs(ch5)>50: continue
                    # FIX 2: Jupiter v6 with fallback to Dex price
                    try:
                        jp=requests.get(f"https://price.jup.ag/v6/price?ids={token}",timeout=3).json()
                        jprice=float(jp.get('data',{}).get(token,{}).get('price',0) or 0)
                        if jprice>0 and abs(jprice-price)/price<0.3: price=jprice
                    except: pass
                    sol_coins.append({"symbol":p.get('baseToken',{}).get('symbol','SOL')[:8],"price":price,"c1":ch5,"vol":vol,"buys":buys,"sells":sells,"cg_id":p.get('pairAddress'),"token":token,"type":"SOLANA_REAL","chain":"solana","score":abs(ch5)*(buys+sells),"liquidity":liq})
                except: pass
    except Exception as e:
        print(f"Sol err {e}")

    sol_coins.sort(key=lambda x:x['score'],reverse=True)
    binance_coins.sort(key=lambda x:abs(x['c1']),reverse=True)
    mixed=binance_coins[:2]+sol_coins[:2]
    btc_ch=next((x['c1']*6 for x in binance_coins if x['symbol']=='BTC'),0)
    regime="BEAR_FREEZE" if btc_ch<-0.8 else "BULL_JUMP_100" if btc_ch>0.4 else "BULL" if btc_ch>0.2 else "NEUTRAL"
    return mixed[:4], regime, btc_ch, 0

def get_price_real(cg_id, chain, last, token=None):
    if chain=="binance":
        try:
            r=requests.get(f"{BINANCE_BASE}/api/v3/ticker/price?symbol={cg_id}",timeout=3).json()
            p=float(r.get('price',0))
            if p>0 and last>0 and abs(p-last)/last<0.15: return p
        except: pass
    elif chain=="solana" and token:
        try:
            r=requests.get(f"https://price.jup.ag/v6/price?ids={token}",timeout=3).json()
            p=float(r.get('data',{}).get(token,{}).get('price',0) or 0)
            if p>0 and last>0 and abs(p-last)/last<0.30: return p
        except: pass
    return last

def do_tick():
    data=rget(); cap=float(data.get("FUND_CAP",1000.0)); open_t=data.get("FUND_OPEN",[]); closed=data.get("FUND_CLOSED",[])
    wins=int(data.get("FUND_WINS",0)); losses=int(data.get("FUND_LOSSES",0))
    daily=float(data.get("FUND_DAILY_PNL",0.0)); dg=float(data.get("FUND_DAILY_GROSS",0.0)); df=float(data.get("FUND_DAILY_FEE",0.0))
    profit_bank=float(data.get("FUND_PROFIT_BANK",0.0)); rotate=data.get("ROTATE_COINS",[]); now=time.time()
    locked=bool(data.get("FUND_DAILY_LOCKED",False)); free_zone=bool(data.get("FREE_ZONE",False)); count100=int(data.get("FREE_ZONE_100_COUNT",0))
    if now-float(data.get("FAST_LAST",0))>300 or len(rotate)==0:
        w,regime,btc_ch,avg=get_real_prices(); rotate=w; data["ROTATE_COINS"]=w; data["FAST_LAST"]=now; data["REGIME"]=regime; data["BTC_CH"]=btc_ch
        if free_zone and regime=="BULL_JUMP_100": free_zone=False; locked=False; data["FREE_ZONE"]=False; data["FUND_DAILY_LOCKED"]=False
    else:
        regime=data.get("REGIME","NEUTRAL"); btc_ch=data.get("BTC_CH",0)
    if not locked and daily>=REAL_TARGET:
        profit_bank+=REAL_TARGET; cap+=REAL_TARGET; count100+=1
        data.update({"FUND_CAP":cap,"FUND_OPEN":[],"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":True,"FREE_ZONE":True,"FREE_ZONE_100_COUNT":count100,"REGIME":regime,"BTC_CH":btc_ch})
        rset(data)
        return {"cap":cap,"open":[],"wins":wins,"losses":losses,"total":wins+losses,"daily":0,"dg":0,"df":0,"rotate":rotate,"bank":profit_bank,"locked":True,"free_zone":True,"count100":count100,"regime":regime,"btc_ch":btc_ch}
    if free_zone or locked:
        new_open=[]
        for tr in open_t:
            cur=get_price_real(tr['cg_id'],tr.get('chain','binance'),float(tr.get('last_price',tr['entry'])),tr.get('token')); age=now-float(tr.get('ts',now))
            if age>60:
                pct=(cur-float(tr['entry']))/float(tr['entry'])*100
                gross,fee,net,fee_pct=calc_fees(tr.get('chain','binance'),float(tr.get('pos',POS_SIZE)),pct)
                closed.append({"symbol":tr['symbol'],"pct":pct,"gross":gross,"fee":fee,"net":net,"fee_pct":fee_pct,"peak":float(tr.get('peak_pct',0)),"pos":float(tr.get('pos',POS_SIZE)),"age":int(age),"type":tr.get('type',''),"chain":tr.get('chain'),"reason":"FREE ZONE CLOSE"})
                if net>=0: wins+=1
                else: losses+=1
                daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":locked,"FREE_ZONE":free_zone,"FREE_ZONE_100_COUNT":count100,"REGIME":regime,"BTC_CH":btc_ch})
        rset(data)
        return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"rotate":rotate,"bank":profit_bank,"locked":locked,"free_zone":free_zone,"count100":count100,"regime":regime,"btc_ch":btc_ch}
    new_open=[]
    for tr in list(open_t):
        cur=get_price_real(tr['cg_id'],tr.get('chain','binance'),float(tr.get('last_price',tr['entry'])),tr.get('token')); age=now-float(tr.get('ts',now))
        if age<8: tr['last_price']=cur; new_open.append(tr); continue
        pct=(cur-float(tr['entry']))/float(tr['entry'])*100 if float(tr['entry'])>0 else 0
        peak=float(tr.get('peak_pct',0))
        if pct>peak: peak=pct; tr['peak_pct']=peak
        gross,fee,net,fee_pct=calc_fees(tr.get('chain','binance'),float(tr.get('pos',POS_SIZE)),pct)
        close=False; reason=""
        sl=-4.0 if tr.get('chain')=='solana' else -2.0
        tp=6.0 if tr.get('chain')=='solana' else 4.0
        if pct<=sl: close=True; reason=f"SL {sl}% NET ${net:.2f} FEE ${fee:.2f}"
        elif pct>=tp: close=True; reason=f"TP {tp}% GROSS ${gross:.2f} FEE ${fee:.2f} NET ${net:.2f}"
        elif pct>=2.0 and peak>=2.5 and pct<=peak-0.6: close=True; reason=f"TRAIL {peak:.1f}->{pct:.1f}% NET ${net:.2f}"
        elif age>=180: close=True; reason=f"TIME 180s NET ${net:.2f}"
        if close:
            closed.append({"symbol":tr['symbol'],"pct":pct,"gross":gross,"fee":fee,"net":net,"fee_pct":fee_pct,"peak":peak,"pos":float(tr.get('pos',POS_SIZE)),"age":int(age),"type":tr.get('type',''),"chain":tr.get('chain'),"reason":reason})
            if net>=0: wins+=1
            else: losses+=1
            daily+=net; dg+=gross; df+=fee; cap+=net
        else:
            tr['last_price']=cur; new_open.append(tr)
    if len(new_open)<3:
        syms=set(x['symbol'] for x in new_open)
        for m in rotate:
            if len(new_open)>=3: break
            if m['symbol'] in syms: continue
            new_open.append({"symbol":m['symbol'],"entry":m['price'],"ts":now,"last_price":m['price'],"pos":POS_SIZE,"c1":m['c1'],"cg_id":m['cg_id'],"token":m.get('token'),"chain":m.get('chain','binance'),"peak_pct":0,"type":m['type'],"liquidity":m.get('liquidity',0)})
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":locked,"FREE_ZONE":free_zone,"FREE_ZONE_100_COUNT":count100,"REGIME":regime,"BTC_CH":btc_ch})
    rset(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"rotate":rotate,"bank":profit_bank,"locked":locked,"free_zone":free_zone,"count100":count100,"regime":regime,"btc_ch":btc_ch}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v712 FEES FIXED</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#000;color:#fff}.top{background:#111;padding:10px;border-bottom:2px solid #00FF88}.grid{display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr 1fr;gap:1px;background:#222}.card{background:#000;padding:8px;text-align:center}.card b{font-size:12px;display:block}.green{color:#00FF88}.yellow{color:#FFD000}.red{color:#FF4444}.blue{color:#00AAFF}.card small{color:#888;font-size:9px}.box{padding:8px;margin:5px;font-size:9px;border:2px solid}.yellowbox{border-color:#FFD000;background:#332200;color:#FFD000}.section{padding:8px;border-bottom:1px solid #222}.section h3{color:#00FF88;font-size:10px}.item{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #111;font-size:9px}</style></head><body>
<div class="top"><b>VENUS v712 FEES FIXED - GROSS FEE NET - TEST 0 FUNDS</b> <span id="time"></span></div>
<div class="grid">
<div class="card"><small>CAP TEST</small><b id="cap" class="green">$1000</b><small id="capSub"></small></div>
<div class="card"><small>DAILY NET</small><b id="daily" class="green">+$0</b><small id="dailySub"></small></div>
<div class="card"><small>GROSS</small><b id="gross" class="yellow">$0</b><small>GROSS</small></div>
<div class="card"><small>FEE REAL</small><b id="fee" class="red">$0</b><small>BIN 0.2% SOL 0.8%</small></div>
<div class="card"><small>W/L/TOTAL</small><b id="wl">0W/0L/0</b><small id="wlSub"></small></div>
<div class="card"><small>BANK TEST</small><b id="bank" class="green">$0</b><small>BANK</small></div>
</div>
<div class="box yellowbox">FEES REAL: BINANCE 0.2% ($0.02/$10) | SOLANA 0.8%+ $0.02 ($0.10/$10) - GROSS FEE NET - TP SOL 6% = NET 5.2% | TP BINANCE 4% = NET 3.8% | 1 TAB ONLY | VOL>5000 LIQ>10k</div>
<div class="section"><h3>REAL PRICE + REAL FEES</h3><div id="rotate"></div></div>
<div class="section"><h3>OPEN - GROSS FEE NET</h3><div id="openlist"></div></div>
<div class="section"><h3>CLOSED - NET AFTER FEES</h3><div id="closed"></div></div>
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
 document.getElementById('capSub').innerText='GROSS $'+j.dg.toFixed(2)+' FEE $'+j.df.toFixed(2)+' NET $'+j.daily.toFixed(2);
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' FEES REAL BTC '+ (j.btc_ch||0).toFixed(2)+'% REGIME '+j.regime;
 let rot=document.getElementById('rotate');rot.innerHTML='';
 (j.rotate||[]).forEach(m=>{
  let fee=m.chain=='solana'?'FEE 0.8%':'FEE 0.2%';
  rot.innerHTML+=`<div class="item"><div><b>${m.symbol} ${m.chain.toUpperCase()}</b> ${m.c1.toFixed(2)}% VOL ${(m.vol/1000).toFixed(0)}k ${fee}</div><div>${m.chain} LIQ $${(m.liquidity/1000).toFixed(0)}k</div></div>`;
 });
 if((j.rotate||[]).length==0) rot.innerHTML='<div class="item" style="color:#666">Scanning Binance + Solana... wait 5s</div>';
 let ol=document.getElementById('openlist');ol.innerHTML='';
 (j.open||[]).forEach(t=>{
  let pct=t.entry>0?(t.last_price-t.entry)/t.entry*100:0;
  let gross=t.pos*pct/100;
  let fee=t.chain=='solana'?t.pos*0.008+0.02:t.pos*0.002;
  let net=gross-fee;
  ol.innerHTML+=`<div class="item"><div><b>${t.symbol}</b> ${pct.toFixed(2)}% GROSS $${gross.toFixed(3)} FEE $${fee.toFixed(3)} NET $${net.toFixed(3)} AGE ${Math.floor(Date.now()/1000-t.ts)}s</div><div>NET $${net.toFixed(3)}</div></div>`;
 });
 if((j.open||[]).length==0) ol.innerHTML='<div class="item" style="color:#444">No open - will fill 3 from REAL feed</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-20).reverse().forEach(c=>{
  let col=c.net>=0?'#00FF88':'#FF4444';
  cb.innerHTML+=`<div class="item"><div><b style="color:${col}">${c.symbol} NET $${c.net.toFixed(3)}</b> GROSS $${(c.gross||0).toFixed(3)} FEE $${(c.fee||0).toFixed(3)} ${c.reason||''}</div><div style="color:${col}">${c.pct.toFixed(2)}% NET $${c.net.toFixed(3)}</div></div>`;
 });
 if((j.closed||[]).length==0) cb.innerHTML='<div class="item" style="color:#444">No closed yet - waiting real ticks</div>';
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
    return jsonify({"cap":float(d.get("FUND_CAP",1000)),"open":d.get("FUND_OPEN",[]),"wins":int(d.get("FUND_WINS",0)),"losses":int(d.get("FUND_LOSSES",0)),"total":int(d.get("FUND_TOTAL_TRADES",0)),"closed":d.get("FUND_CLOSED",[]),"daily":float(d.get("FUND_DAILY_PNL",0)),"dg":float(d.get("FUND_DAILY_GROSS",0)),"df":float(d.get("FUND_DAILY_FEE",0)),"rotate":d.get("ROTATE_COINS",[]),"bank":float(d.get("FUND_PROFIT_BANK",0.0)),"locked":bool(d.get("FUND_DAILY_LOCKED",False)),"free_zone":bool(d.get("FREE_ZONE",False)),"count100":int(d.get("FREE_ZONE_100_COUNT",0)),"regime":d.get("REGIME","NEUTRAL"),"btc_ch":float(d.get("BTC_CH",0))})
@app.route("/api/cron")
def cron():
    try: return jsonify(do_tick())
    except Exception as e: return jsonify({"error":str(e)})
@app.route("/api/reset")
def reset():
    d={"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":0,"FUND_DAILY_LOCKED":False,"FREE_ZONE":False,"FREE_ZONE_100_COUNT":0,"REGIME":"NEUTRAL","BTC_CH":0}
    rset(d)
    return jsonify({"ok":True,"msg":"v712 FEES FIXED - READY - 1 TAB ONLY"})
