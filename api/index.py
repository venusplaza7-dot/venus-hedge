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

KEY="VENUS_V710_TEST"; KEY_BACKUP="VENUS_V710_TEST_BACKUP"
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
    return {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":0,"FUND_DAILY_LOCKED":False,"FREE_ZONE":False,"FREE_ZONE_100_COUNT":0,"FUND_LOCKED_WIN":0.0,"FROZEN":False,"REGIME":"NEUTRAL","BTC_CH":0,"AVG_MOVE":0}

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
JUPITER_PRICE="https://price.jup.ag/v6/price?ids={}"

def get_real_prices():
    # 1. Binance real top coins
    binance_coins=[]
    try:
        coins=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT"]
        r=requests.get(f"{BINANCE_BASE}/api/v3/ticker/24hr?symbols={json.dumps(coins)}",timeout=6).json()
        for it in r:
            try:
                price=float(it.get('lastPrice',0)); ch=float(it.get('priceChangePercent',0)); vol=float(it.get('quoteVolume',0))
                if price<=0 or vol<1000000: continue
                binance_coins.append({"symbol":it['symbol'].replace('USDT',''),"price":price,"c1":ch/6,"vol":vol,"buys":int(float(it.get('count',0))/2),"cg_id":it['symbol'],"type":"BINANCE_REAL","chain":"binance","score":abs(ch),"liquidity":vol})
            except: pass
    except: pass

    # 2. Solana real top movers via DexScreener + Jupiter real price check (NO SWAP, only price)
    sol_coins=[]
    try:
        r=requests.get("https://api.dexscreener.com/token-boosts/top/v1",timeout=6).json()
        for it in r[:20]:
            if it.get('chainId')=='solana' and it.get('tokenAddress'):
                token=it['tokenAddress']
                try:
                    pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}",timeout=4).json()
                    if not pr.get('pairs'): continue
                    p=pr['pairs'][0]
                    price=float(p.get('priceUsd',0) or 0); ch5=float(p.get('priceChange',{}).get('m5',0) or 0)
                    vol=float((p.get('volume',{}).get('m5',0) or 0) or 0); buys=int((p.get('txns',{}).get('m5',{}).get('buys',0) or 0))
                    sells=int((p.get('txns',{}).get('m5',{}).get('sells',0) or 0)); liq=float(p.get('liquidity',{}).get('usd',0) or 0)
                    # TEST FILTER: Only VOL>$5000 and buys+sells>20 and liquidity>$10000 - Your 2037 VOL fails, 8365 passes
                    if price<=0 or vol<5000 or buys+sells<20 or liq<10000 or abs(ch5)>50: continue
                    # Jupiter real price check (test mode - no swap, just price)
                    try:
                        jp=requests.get(f"https://price.jup.ag/v6/price?ids={token}",timeout=3).json()
                        jprice=float(jp.get('data',{}).get(token,{}).get('price',0) or price)
                        if jprice>0: price=jprice
                    except: pass
                    score=abs(ch5)*(buys+sells)
                    sol_coins.append({"symbol":p.get('baseToken',{}).get('symbol','MOVE')[:8],"price":price,"c1":ch5,"vol":vol,"buys":buys,"sells":sells,"cg_id":p.get('pairAddress'),"token":token,"type":"SOLANA_REAL","chain":"solana","score":score,"liquidity":liq})
                except: pass
    except: pass

    sol_coins.sort(key=lambda x:x['score'],reverse=True)
    binance_coins.sort(key=lambda x:abs(x['c1']),reverse=True)
    # Mix: 3 Binance real + 3 Solana real high vol
    mixed=binance_coins[:3]+sol_coins[:3]
    # Regime
    btc_ch=next((x['c1']*6 for x in binance_coins if x['symbol']=='BTC'),0)
    avg_move=sum([x['c1'] for x in mixed[:3]])/3 if mixed else 0
    if btc_ch < -0.8: regime="BEAR_FREEZE"
    elif btc_ch > 0.4 and mixed and mixed[0]['vol']>5000: regime="BULL_JUMP_100"
    elif btc_ch > 0.2: regime="BULL"
    else: regime="NEUTRAL"
    return mixed[:6], regime, btc_ch, avg_move

def get_real_price(cg_id, chain, last, token=None):
    if chain=="binance":
        try:
            r=requests.get(f"{BINANCE_BASE}/api/v3/ticker/price?symbol={cg_id}",timeout=3).json()
            p=float(r.get('price',0))
            if p>0 and abs(p-last)/last<0.15: return p
        except: pass
    elif chain=="solana" and token:
        try:
            # Jupiter real price - test mode
            r=requests.get(f"https://price.jup.ag/v6/price?ids={token}",timeout=3).json()
            p=float(r.get('data',{}).get(token,{}).get('price',0) or 0)
            if p>0 and abs(p-last)/last<0.30: return p # Allow 30% move for Solana
        except: pass
        try:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}",timeout=3).json()
            pr=r.get('pair')
            if pr and pr.get('priceUsd'):
                p=float(pr['priceUsd'])
                if p>0 and abs(p-last)/last<0.30: return p
        except: pass
    return last

def do_tick():
    data=rget(); cap=float(data.get("FUND_CAP",1000.0)); open_t=data.get("FUND_OPEN",[]); closed=data.get("FUND_CLOSED",[])
    wins=int(data.get("FUND_WINS",0)); losses=int(data.get("FUND_LOSSES",0))
    daily=float(data.get("FUND_DAILY_PNL",0.0)); profit_bank=float(data.get("FUND_PROFIT_BANK",0.0))
    rotate=data.get("ROTATE_COINS",[]); now=time.time()
    locked=bool(data.get("FUND_DAILY_LOCKED",False)); free_zone=bool(data.get("FREE_ZONE",False)); count100=int(data.get("FREE_ZONE_100_COUNT",0))

    if now-float(data.get("FAST_LAST",0))>300 or len(rotate)==0:
        w,regime,btc_ch,avg_move=get_real_prices(); rotate=w; data["ROTATE_COINS"]=w; data["FAST_LAST"]=now; data["REGIME"]=regime; data["BTC_CH"]=btc_ch; data["AVG_MOVE"]=avg_move
        if free_zone and regime=="BULL_JUMP_100": free_zone=False; locked=False; data["FREE_ZONE"]=False; data["FUND_DAILY_LOCKED"]=False
    else:
        regime=data.get("REGIME","NEUTRAL"); btc_ch=data.get("BTC_CH",0); avg_move=data.get("AVG_MOVE",0)

    if not locked and daily>=REAL_TARGET:
        profit_bank+=REAL_TARGET; cap+=REAL_TARGET; count100+=1
        for tr in open_t:
            cur=get_real_price(tr['cg_id'],tr.get('chain','binance'),float(tr.get('last_price',tr['entry'])),tr.get('token'))
            pct=(cur-float(tr['entry']))/float(tr['entry'])*100 if float(tr['entry'])>0 else 0
            closed.append({"symbol":tr['symbol'],"pct":pct,"peak":float(tr.get('peak_pct',0)),"net":float(tr.get('pos',POS_SIZE))*pct/100,"pos":float(tr.get('pos',POS_SIZE)),"hh":0,"age":0,"type":tr.get('type',''),"reason":f"${REAL_TARGET} PRESERVED #{count100} TEST"})
        data.update({"FUND_CAP":cap,"FUND_OPEN":[],"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":True,"FREE_ZONE":True,"FREE_ZONE_100_COUNT":count100,"FUND_LOCKED_WIN":REAL_TARGET,"REGIME":regime,"BTC_CH":btc_ch,"AVG_MOVE":avg_move})
        rset(data)
        return {"cap":cap,"open":[],"wins":wins,"losses":losses,"total":wins+losses,"daily":0,"rotate":rotate,"bank":profit_bank,"locked":True,"free_zone":True,"count100":count100,"regime":regime,"btc_ch":btc_ch,"avg_move":avg_move,"preserved":True}

    if free_zone or locked:
        new_open=[]
        for tr in open_t:
            cur=get_real_price(tr['cg_id'],tr.get('chain','binance'),float(tr.get('last_price',tr['entry'])),tr.get('token')); age=now-float(tr.get('ts',now))
            if age>60:
                pct=(cur-float(tr['entry']))/float(tr['entry'])*100
                closed.append({"symbol":tr['symbol'],"pct":pct,"peak":float(tr.get('peak_pct',0)),"net":float(tr.get('pos',POS_SIZE))*pct/100,"pos":float(tr.get('pos',POS_SIZE)),"hh":0,"age":int(age),"type":tr.get('type',''),"reason":"FREE ZONE CLOSE TEST"})
                if pct>=0: wins+=1
                else: losses+=1
                daily+=float(tr.get('pos',POS_SIZE))*pct/100; cap+=float(tr.get('pos',POS_SIZE))*pct/100
            else:
                tr['last_price']=cur; new_open.append(tr)
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":locked,"FREE_ZONE":free_zone,"FREE_ZONE_100_COUNT":count100,"REGIME":regime,"BTC_CH":btc_ch,"AVG_MOVE":avg_move})
        rset(data)
        return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"rotate":rotate,"bank":profit_bank,"locked":locked,"free_zone":free_zone,"count100":count100,"regime":regime,"btc_ch":btc_ch,"avg_move":avg_move}

    new_open=[]
    for tr in list(open_t):
        cur=get_real_price(tr['cg_id'],tr.get('chain','binance'),float(tr.get('last_price',tr['entry'])),tr.get('token')); age=now-float(tr.get('ts',now))
        if age<8: tr['last_price']=cur; new_open.append(tr); continue
        pct=(cur-float(tr['entry']))/float(tr['entry'])*100 if float(tr['entry'])>0 else 0
        peak=float(tr.get('peak_pct',0))
        if pct>peak: peak=pct; tr['peak_pct']=peak
        close=False; reason=""
        # Solana needs wider SL due to slippage
        sl = -4.0 if tr.get('chain')=='solana' else -2.0
        tp = 6.0 if tr.get('chain')=='solana' else 4.0
        if pct<=sl: close=True; reason=f"HARD SL {sl}% {pct:.1f}%"
        elif pct>=tp: close=True; reason=f"TP {tp}% {pct:.1f}%"
        elif pct>=2.0 and peak>=2.5 and pct<=peak-0.6: close=True; reason=f"TRAIL {peak:.1f}->{pct:.1f}%"
        elif age>=180: close=True; reason="TIME 180s"
        if close:
            closed.append({"symbol":tr['symbol'],"pct":pct,"peak":peak,"net":float(tr.get('pos',POS_SIZE))*pct/100,"pos":float(tr.get('pos',POS_SIZE)),"hh":0,"age":int(age),"type":tr.get('type',''),"reason":reason,"chain":tr.get('chain')})
            if pct>=0: wins+=1
            else: losses+=1
            daily+=float(tr.get('pos',POS_SIZE))*pct/100; cap+=float(tr.get('pos',POS_SIZE))*pct/100
        else:
            tr['last_price']=cur; new_open.append(tr)

    if len(new_open)<3:
        syms=set(x['symbol'] for x in new_open)
        for m in rotate:
            if len(new_open)>=3: break
            if m['symbol'] in syms: continue
            new_open.append({"symbol":m['symbol'],"entry":m['price'],"ts":now,"last_price":m['price'],"pos":POS_SIZE,"c1":m['c1'],"cg_id":m['cg_id'],"token":m.get('token'),"chain":m.get('chain','binance'),"peak_pct":0,"type":m['type'],"liquidity":m.get('liquidity',0)})

    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FAST_LAST":now,"ROTATE_COINS":rotate,"FUND_PROFIT_BANK":profit_bank,"FUND_DAILY_LOCKED":locked,"FREE_ZONE":free_zone,"FREE_ZONE_100_COUNT":count100,"REGIME":regime,"BTC_CH":btc_ch,"AVG_MOVE":avg_move})
    rset(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"rotate":rotate,"bank":profit_bank,"locked":locked,"free_zone":free_zone,"count100":count100,"regime":regime,"btc_ch":btc_ch,"avg_move":avg_move}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v710 TEST - REAL PRICE NO FUNDS</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#000;color:#fff}.top{background:#111;padding:10px;border-bottom:2px solid #00FF88}.grid{display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr;gap:1px;background:#222}.card{background:#000;padding:10px;text-align:center}.card b{font-size:14px;display:block}.green{color:#00FF88}.yellow{color:#FFD000}.red{color:#FF4444}.blue{color:#00AAFF}.purple{color:#AA88FF}.card small{color:#888;font-size:5px}.box{padding:8px;margin:5px;font-size:8px;border:2px solid}.greenbox{border-color:#00FF88;background:#001100;color:#00FF88}.bluebox{border-color:#00AAFF;background:#001133;color:#00AAFF}.purplebox{border-color:#AA00FF;background:#110033;color:#CC88FF}.yellowbox{border-color:#FFD000;background:#332200;color:#FFD000}.section{padding:8px;border-bottom:1px solid #222}.section h3{color:#00FF88;font-size:9px}.item{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #111;font-size:9px}</style></head><body>
<div class="top"><b>VENUS v710 TEST MODE - REAL JUPITER + REAL BINANCE - 0 FUNDS - PAPER SIM</b> <span id="time" style="font-size:9px;color:#888"></span></div>
<div class="grid">
<div class="card"><small>CAP TEST</small><b id="cap" class="green">$1000</b><small id="capSub"></small></div>
<div class="card"><small>DAILY</small><b id="daily" class="green">+$0</b><small id="dailySub"></small></div>
<div class="card"><small>BANK SAFE TEST</small><b id="bank" class="green">$0</b><small id="bankSub"></small></div>
<div class="card"><small>W/L/TOTAL</small><b id="wl">0W/0L/0</b><small id="wlSub"></small></div>
<div class="card"><small>$10 RETAINED TEST</small><b id="count100" class="blue">0x $10</b><small id="count100Sub"></small></div>
</div>
<div class="box yellowbox">⚠️ TEST MODE - 0 FUNDS - Real Jupiter price + Real Binance price - Paper simulation only - No Phantom key - No swap - When green 3h, then inject $20 burner</div>
<div class="box purplebox" id="freezonebox" style="display:none">🛡️ FREE ZONE TEST - $10 PRESERVED - NOT LOOSING - <span id="fz_count">0x $10</span> - Waiting BULL_JUMP_100 for next $10</div>
<div class="box greenbox">v710 TEST: BINANCE BTC ETH SOL + SOLANA HIGH VOL>5000 LIQ>10k + BUYS>20 + Jupiter real price + TP SOL 6% SL -4% / BINANCE TP 4% SL -2% / $10 PRESERVE FREE ZONE / AGE min 8s / 5 min rotate / 1 TAB ONLY</div>
<div class="section"><h3>REAL PRICE TEST - BINANCE VOL>1M + SOLANA VOL>5000 LIQ>10k - 100% REAL PRICE NO SWAP</h3><div id="rotate"></div></div>
<div class="section"><h3>OPEN 3 MAX TEST - REAL PRICE - NO FUNDS</h3><div id="openlist"></div></div>
<div class="section"><h3>CLOSED - REAL PRICE TEST - BEFORE FUNDS</h3><div id="closed"></div></div>
<script>
async function load(){
 try{await fetch('/api/cron');}catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+j.cap.toFixed(2);
 let d=document.getElementById('daily');
 if(j.free_zone){ d.className='blue'; d.innerText='🛡️ +$'+j.daily.toFixed(2)+' SAFE TEST'; }
 else if(j.daily>=0){ d.className='green'; d.innerText='+$'+j.daily.toFixed(2)+' TEST'; }
 else { d.className='red'; d.innerText='-$'+Math.abs(j.daily).toFixed(2)+' TEST'; }
 document.getElementById('bank').innerText='$'+j.bank.toFixed(2)+' TEST';
 document.getElementById('wl').innerText=j.wins+'W/'+j.losses+'L/'+j.total;
 document.getElementById('count100').innerText=(j.count100||0)+'x $10 TEST';
 document.getElementById('capSub').innerText='TEST MODE - NO FUNDS - '+(j.regime||'')+' BTC '+ (j.btc_ch||0).toFixed(2)+'%';
 document.getElementById('dailySub').innerText=j.free_zone?'🛡️ SAFE TEST - NOT LOOSING - '+(j.count100||0)+'x $10': (j.daily>=0?'✅ WINNING TEST - NOT LOOSING':'⚠️ LOSING TEST - SL');
 document.getElementById('bankSub').innerText='TEST BANK - NO FUNDS YET';
 document.getElementById('wlSub').innerText=j.total+' trades TEST REAL PRICE';
 document.getElementById('count100Sub').innerText='$'+((j.count100||0)*10)+' TEST RETAINED';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' TEST NO FUNDS '+(j.regime||'')+' BTC '+ (j.btc_ch||0).toFixed(2)+'%';
 document.getElementById('freezonebox').style.display=j.free_zone?'block':'none';
 document.getElementById('fz_count').innerText=(j.count100||0)+'x $10 = $'+((j.count100||0)*10)+' TEST';
 let rot=document.getElementById('rotate');rot.innerHTML='';
 (j.rotate||[]).forEach(m=>{
  let chainColor = m.chain=='solana'?'#AA88FF':'#00FF88';
  let liq = m.liquidity? ' LIQ $'+(m.liquidity/1000).toFixed(1)+'k' : ' VOL $'+(m.vol/1000000).toFixed(1)+'M';
  rot.innerHTML+=`<div class="item"><div><b style="color:${chainColor}">${m.symbol} ${m.chain.toUpperCase()} REAL</b> ${m.c1.toFixed(2)}%${liq} ${m.buys}B/${m.sells||0}S ${m.type} ${m.chain=='solana'?'VOL>5000 LIQ>10k PASS':'BINANCE REAL'}</div><div style="color:${chainColor}">${m.chain=='solana'?'🟣 SOL REAL PRICE':'🟢 BIN REAL'}</div></div>`;
 });
 let ol=document.getElementById('openlist');ol.innerHTML='';
 if(j.free_zone){ ol.innerHTML='<div class="item" style="color:#AA00FF">🛡️ FREE ZONE TEST - $'+j.bank+' SAFE TEST - No funds yet - Waiting BULL_JUMP_100 for next $10</div>';}
 if((j.open||[]).length==0 &&!j.free_zone) ol.innerHTML='<div class="item">No open TEST - Ready - No funds</div>';
 (j.open||[]).forEach(t=>{
  let pct=t.entry>0?(t.last_price-t.entry)/t.entry*100:0;
  let chainColor = t.chain=='solana'?'#AA88FF':'#00FF88';
  ol.innerHTML+=`<div class="item"><div><b style="color:${chainColor}">${t.symbol} ${t.chain?.toUpperCase()} TEST</b> PEAK ${t.peak_pct.toFixed(1)}% AGE ${Math.floor((Date.now()/1000 - t.ts))}s LIQ $${(t.liquidity||0/1000).toFixed(0)}k</div><div style="color:${pct>=0?'#00FF88':'#FF4444'}">${pct.toFixed(2)}% $${(t.pos*pct/100).toFixed(2)} TEST</div></div>`;
 });
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-20).reverse().forEach(c=>{
  let col=c.net>=0?'#00FF88':'#FF4444';
  let chainTag = c.chain? c.chain.toUpperCase() : '';
  cb.innerHTML+=`<div class="item"><div><b style="color:${col}">${c.symbol} ${chainTag} ${c.net>=0?'WINNER':'LOSER'} $${c.net.toFixed(2)} TEST</b> ${c.reason||''} PEAK ${c.peak.toFixed(1)}%</div><div style="color:${col}">${c.pct.toFixed(2)}% TEST</div></div>`;
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
    return jsonify({"cap":float(d.get("FUND_CAP",1000)),"open":d.get("FUND_OPEN",[]),"wins":int(d.get("FUND_WINS",0)),"losses":int(d.get("FUND_LOSSES",0)),"total":int(d.get("FUND_TOTAL_TRADES",0)),"closed":d.get("FUND_CLOSED",[]),"daily":float(d.get("FUND_DAILY_PNL",0)),"rotate":d.get("ROTATE_COINS",[]),"bank":float(d.get("FUND_PROFIT_BANK",0.0)),"locked":bool(d.get("FUND_DAILY_LOCKED",False)),"free_zone":bool(d.get("FREE_ZONE",False)),"count100":int(d.get("FREE_ZONE_100_COUNT",0)),"regime":d.get("REGIME","NEUTRAL"),"btc_ch":float(d.get("BTC_CH",0)),"avg_move":float(d.get("AVG_MOVE",0))})
@app.route("/api/cron")
def cron():
    try: return jsonify(do_tick())
    except Exception as e: return jsonify({"error":str(e)})
@app.route("/api/reset")
def reset():
    d={"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"FAST_LAST":0,"ROTATE_COINS":[],"FUND_PROFIT_BANK":0,"FUND_DAILY_LOCKED":False,"FREE_ZONE":False,"FREE_ZONE_100_COUNT":0,"FUND_LOCKED_WIN":0.0,"FROZEN":False,"REGIME":"NEUTRAL","BTC_CH":0,"AVG_MOVE":0}
    rset(d)
    return jsonify({"ok":True,"msg":"v710 TEST RESET - $1000 TEST - 0 FUNDS - REAL PRICE ONLY - NO SWAP"})
@app.route("/api/status")
def status():
    d=rget()
    return jsonify({"mode":"TEST - 0 FUNDS","cap":d.get("FUND_CAP"),"daily":d.get("FUND_DAILY_PNL"),"wins":d.get("FUND_WINS"),"losses":d.get("FUND_LOSSES"),"total":d.get("FUND_TOTAL_TRADES"),"rotate_count":len(d.get("ROTATE_COINS",[])),"msg":"TEST MODE - Real Jupiter + Real Binance price, paper sim, no Phantom key needed. When CAP $1000 -> $1005 in 3h with 10W/8L, then inject $20 burner."})
