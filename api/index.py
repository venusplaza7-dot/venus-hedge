from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)

UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = (os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").rstrip("")
SINGLE_KEY = "VENUS_V611_TOTAL" # NEVER CHANGE - THIS IS WHY TRACKING RESETS - KEEPS $1000.85 1W/0L
DAILY_GOAL = 100.0
DAILY_STOP = -15.0
CACHE = {"data": None, "ts": 0}

def rget():
    global CACHE
    now=time.time()
    if CACHE["data"] and now - CACHE["ts"] < 4: return CACHE["data"]
    # TRY UPSTASH FIRST - THIS KEEPS TOTAL FOREVER
    if UP_URL and UP_TOKEN:
        try:
            r=requests.get(f"{UP_URL}/get/{SINGLE_KEY}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=7)
            j=r.json()
            v=j.get("result")
            if v:
                data=json.loads(v)
                # FIX TRACKING - ENSURE ALL FIELDS EXIST
                data.setdefault("FUND_CAP", 1000.0)
                data.setdefault("FUND_WINS", 0)
                data.setdefault("FUND_LOSSES", 0)
                data.setdefault("FUND_TOTAL_TRADES", data["FUND_WINS"]+data["FUND_LOSSES"])
                data.setdefault("FUND_DAILY_PNL", 0)
                data.setdefault("FUND_DAILY_GROSS", 0)
                data.setdefault("FUND_DAILY_FEE", 0)
                data.setdefault("FUND_OPEN", [])
                data.setdefault("FUND_CLOSED", [])
                data.setdefault("LEARN_STATS", {})
                data.setdefault("LAST_LOSS_TIME", {})
                data.setdefault("LAST_LOSS_PEAK", {})
                data.setdefault("BLACKLIST", {})
                data.setdefault("FAST_WHALE", [])
                data.setdefault("ROTATE_COINS", [])
                CACHE["data"]=data; CACHE["ts"]=now
                return data
        except Exception as e:
            print(f"UPSTASH GET FAIL {e} URL:{UP_URL[:20]}")
    # FALLBACK TO CACHE ONLY
    return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_TOTAL_TRADES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"BLACKLIST":{},"FAST_WHALE":[],"FAST_LAST":0,"ROTATE_LAST":0,"ROTATE_COINS":[]}

def rset(data):
    global CACHE
    # ALWAYS UPDATE TOTAL
    data["FUND_TOTAL_TRADES"]=int(data.get("FUND_WINS",0))+int(data.get("FUND_LOSSES",0))
    CACHE["data"]=data; CACHE["ts"]=time.time()
    if UP_URL and UP_TOKEN:
        try:
            data["_last_save"]=time.time()
            requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(data)], timeout=8)
            print(f"SAVED TOTAL {data['FUND_WINS']}W/{data['FUND_LOSSES']}L TOTAL {data['FUND_TOTAL_TRADES']} CAP ${data['FUND_CAP']:.2f}")
        except Exception as e:
            print(f"UPSTASH SET FAIL {e}")

def scan_always_15():
    all_pairs=[]
    for q in ["BONK","WIF","POPCAT","MEW","BOME","WEN","JUP","RAY","PYTH","TRUMP","PEPE","MUMU","BODEN","FRANK","GARY","INU","SI276","PUTER","OWLNIGHT","SWORDCAT","SOL","JTO"]:
        try:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=4).json()
            if r.get('pairs'):
                for p in r['pairs'][:3]:
                    if p.get('chainId')=='solana': all_pairs.append(p)
        except: pass
    try:
        for url in ["https://api.dexscreener.com/token-boosts/top/v1","https://api.dexscreener.com/token-boosts/latest/v1"]:
            r=requests.get(url, timeout=5).json()
            if isinstance(r,list):
                for it in r[:100]:
                    if it.get('chainId')=='solana':
                        tk=it.get('tokenAddress')
                        if tk:
                            pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=3).json()
                            if pr.get('pairs'): all_pairs.extend(pr['pairs'][:1])
    except: pass
    data=CACHE["data"] or {}; last_loss=data.get("LAST_LOSS_TIME",{}); blacklist=data.get("BLACKLIST",{})
    now=time.time(); seen=set(); whales=[]
    for p in all_pairs:
        try:
            if p.get('chainId')!='solana': continue
            base=p.get('baseToken',{}).get('symbol','').upper()
            if base in ['SOL','USDC','USDT','WETH']: continue
            if base in blacklist and now-float(blacklist.get(base,0))<1200: continue
            if base in last_loss and now-float(last_loss.get(base,0))<150: continue
            addr=p.get('pairAddress')
            if not addr or addr in seen: continue
            seen.add(addr)
            price=float(p.get('priceUsd',0) or 0); liq=float(p.get('liquidity',{}).get('usd',0) or 0)
            if price==0 or not (18000<=liq<=700000): continue
            vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_h1=float(p.get('priceChange',{}).get('h1',0) or 0)
            txns=p.get('txns',{}); buys=int(txns.get('m5',{}).get('buys',0) or 0); sells=int(txns.get('m5',{}).get('sells',0) or 0); buys_h1=int(txns.get('h1',{}).get('buys',0) or 0)
            if vol_m5<250 or buys<5: continue
            if not (0.2<=ch_m5<=10) or not (0.2<=ch_h1<=75): continue
            ratio=buys/max(1,sells)
            if ratio<1.05: continue
            score=ch_m5*buys+vol_m5*0.08
            if 0.5<=ch_m5<=5.5: score*=2.8
            whales.append({"symbol":base[:12],"price":price,"c1":ch_m5,"ch1":ch_h1,"cg_id":addr,"vol_m5":vol_m5,"buys_m5":buys,"sells_m5":sells,"buys_h1":buys_h1,"score":score,"ratio":ratio,"liq":liq})
        except: continue
    whales.sort(key=lambda x: x['score'], reverse=True)
    return whales[:30]

def get_price(cg_id,last):
    try:
        if len(cg_id)>30:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}", timeout=4).json()
            pr=r.get('pair')
            if pr and pr.get('priceUsd'):
                p=float(pr['priceUsd'])
                if p>0 and last>0 and abs(p-last)/last<0.4: return p,"DEX"
                if p>0 and last==0: return p,"DEX"
    except: pass
    return last,"LAST"

def do_tick():
    data=rget()
    cap=float(data.get("FUND_CAP",1000)); open_t=data.get("FUND_OPEN",[]); closed=data.get("FUND_CLOSED",[])
    wins=int(data.get("FUND_WINS",0)); losses=int(data.get("FUND_LOSSES",0)); daily=float(data.get("FUND_DAILY_PNL",0)); dg=float(data.get("FUND_DAILY_GROSS",0)); df=float(data.get("FUND_DAILY_FEE",0))
    learn=data.get("LEARN_STATS",{}); last_loss=data.get("LAST_LOSS_TIME",{}); last_peak=data.get("LAST_LOSS_PEAK",{}); blacklist=data.get("BLACKLIST",{}); fast_whale=data.get("FAST_WHALE",[])
    rotate_last=float(data.get("ROTATE_LAST",0)); rotate_coins=data.get("ROTATE_COINS",[])
    now=time.time()
    if now-float(data.get("FAST_LAST",0))>5:
        w=scan_always_15()
        if w:
            fast_whale=w; data["FAST_WHALE"]=w; data["FAST_LAST"]=now
            if now-rotate_last>300 or len(rotate_coins)<2:
                rotate_coins=[{"symbol":x['symbol'],"cg_id":x['cg_id'],"price":x['price'],"c1":x['c1'],"ch1":x['ch1'],"score":x['score'],"vol":x['vol_m5'],"buys":x['buys_m5']} for x in w[:15]]
                data["ROTATE_COINS"]=rotate_coins; data["ROTATE_LAST"]=now; rotate_last=now
    base_pos=20.0
    if cap>=1015: base_pos=22
    new_open=[]; closed_now=0
    for tr in open_t:
        try:
            sym=tr['symbol']; entry=float(tr['entry']); last=float(tr.get('last_price',entry)); pos=float(tr.get('pos',20)); cg_id=tr['cg_id']
            peak=float(tr.get('peak_pct',0)); hh=int(tr.get('hh',0)); start=float(tr.get('ts',now))
            cur,src=get_price(cg_id,last)
            age=now-start; pct=(cur-entry)/entry*100; fee=pos*0.002; gross=pos*pct/100; net=gross-fee
            if pct>peak:
                if pct>peak+0.15: hh+=1
                peak=pct; tr['peak_pct']=peak; tr['hh']=hh
            close=False
            trail=-0.5
            if hh>=4: trail=-1.0
            elif hh>=2: trail=-0.6
            if age>=300: close=True
            elif peak>=2.5 and pct<=peak+trail: close=True
            elif age>=180 and peak<0.7: close=True
            elif age>=90 and peak<0.2: close=True
            elif pct<=-2.8: close=True
            if close:
                closed.append({"symbol":sym,"side":"LONG","entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":f"TOTAL HH {hh} {pct:.1f}% PEAK {peak:.1f}% AGE {int(age)}s {src}","ts":now,"pos":pos,"hh":hh})
                if len(closed)>500: closed=closed[-500:]
                if net>=0.15: wins+=1
                else: losses+=1
                closed_now+=1
                last_loss[sym]=now+200; last_peak[sym]=peak
                st=learn.get(sym,{'w':0,'l':0}); st['w' if net>=0.15 else 'l']=st.get('w' if net>=0.15 else 'l',0)+1; learn[sym]=st
                if st.get('l',0)>=3: blacklist[sym]=now
                daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)
    if closed_now>0:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak,"BLACKLIST":blacklist})
        rset(data)
        return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"rotate_coins":rotate_coins,"kv":f"v615 TOTAL {wins}W/{losses}L TOTAL {wins+losses} CAP ${cap:.2f} CLOSED {closed_now}"}
    cnt=len(new_open); open_syms=set(x['symbol'] for x in new_open); open_ids=set(x['cg_id'] for x in new_open)
    source=rotate_coins if len(rotate_coins)>=2 else fast_whale[:15]
    idx=0
    while cnt<5 and idx<len(source):
        m=source[idx]; idx+=1
        sym=m['symbol']; cg_id=m['cg_id']
        if sym in open_syms or cg_id in open_ids or sym in last_loss: continue
        new_open.append({"symbol":sym,"prod":f"{sym}-USD","entry":m['price'],"ts":now,"side":"LONG","reason":f"TOTAL {m['c1']:.1f}% M5 H1 {m['ch1']:.1f}% VOL {m['vol_m5']:.0f}","last_price":m['price'],"pos":base_pos,"c1":m['c1'],"cg_id":cg_id,"peak_pct":0,"hh":0})
        cnt+=1
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak,"BLACKLIST":blacklist,"ROTATE_COINS":rotate_coins,"ROTATE_LAST":rotate_last})
    rset(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"rotate_coins":rotate_coins,"rotate_age":int(now-rotate_last) if rotate_last else 0,"kv":f"v615 TOTAL {wins}W/{losses}L TOTAL {wins+losses} CAP ${cap:.2f} 15 COINS {int(now-rotate_last)}s/300s"}

@app.route("/")
def home():
    return """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>v615 TOTAL</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#0a0a0a;color:#00FF88}.top{background:#000;border-bottom:2px solid #FFD000;padding:8px}.top b{color:#FFD000;font-size:7px}.total{background:#001a00;border:2px solid #00FF88;padding:4px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#222}.card{background:#000;padding:10px}.card b{font-size:18px;color:#fff}.card b.big{font-size:22px}button{width:100%;padding:10px;font-weight:900;border:none}button.scan{background:linear-gradient(90deg,#FFD000,#00FF88);color:#000}button.clear{background:#FF0040;color:#fff}.rot{background:#1a1a00;border:2px solid #FFD000;padding:4px}</style></head><body>
<div class="top"><b>VENUS v615 TOTAL TRACK KEEPS TOTAL - SAME KEY V611_TOTAL NEVER CHANGE AGAIN - TRACKS WINS LOSSES TOTAL CAP DAILY GROSS FEE FOREVER - ALWAYS 15 COINS STICK 5 MIN THEN NEW 15 - REAL NEW MONEY - VOL 250+ BUYS 5+ M5 0.2-10% H1 0.2-75% - SAME KEY NEVER RESET - CHECK VERCEL ENV KV_REST_API_URL + TOKEN</b><div id="time" style="font-size:8px;color:#FFD000"></div></div>
<div class="total"><div style="font-size:11px;color:#00FF88">TOTAL TRACKING - <span id="totalInfo">LOADING</span> - NEVER RESET - KEY V611_TOTAL - KEEPS TOTAL FOREVER - ENV UPSTASH_REST_URL + TOKEN MUST BE SET IN VERCEL</div><div id="totalDetail" style="font-size:7px;color:#888"></div></div>
<div class="grid"><div class="card"><small>FUND CAP + GROSS - FEE = NET - KEEPS TOTAL FOREVER - SAME KEY V611_TOTAL</small><b id="cap" class="big">$1000</b><small id="capSub"></small></div><div class="card"><small>OPEN 5/5 FROM 15 - STICK 5 MIN - ALWAYS 15</small><b id="open">0/5</b><small id="wr"></small></div><div class="card"><small>DAILY GOAL $100 STOP -$15</small><b id="daily">+$0</b><small id="dailySub"></small></div><div class="card"><small>PERF WINS/LOSSES/TOTAL - NEVER RESET - SAME KEY</small><b id="wl" class="big">0W/0L TOTAL 0</b><small id="wlSub"></small></div></div>
<div class="rot"><div style="font-size:8px;color:#FFD000">ROTATING 15 COINS - <span id="rotateInfo"></span> - ALWAYS 15 - REAL NEW MONEY - KEEPS TOTAL</div><div id="rotatelist" style="display:flex;flex-wrap:wrap;gap:2px"></div></div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #00FF88"><div style="font-size:7px;color:#00FF88">TOP 25 ALWAYS 15 - VOL 250+ BUYS 5+ M5 0.2-10% H1 0.2-75% - ALWAYS 15 COINS - STICK 5 MIN THEN NEW 15 - REAL NEW MONEY - SAME KEY V611_TOTAL NEVER RESET - TRACKS TOTAL</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px"></div></div>
<div id="openlist"></div>
<button class="scan" onclick="tick()">SCAN TOTAL TRACK - KEEPS TOTAL FOREVER - SAME KEY V611_TOTAL - VOL 250+ BUYS 5+ M5 0.2-10% - 15 COINS 5MIN ROTATE - $100 GOAL - REAL NEW MONEY - ENV KV_REST_API_URL + TOKEN MUST BE SET</button>
<button class="clear" onclick="clearFake()">CLEAR DAILY ONLY - KEEPS WINS/LOSSES/TOTAL/CAP - SAME KEY V611_TOTAL - TOTAL STAYS - NEVER RESET</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88">CLOSED LAST 50 - TRACKS TOTAL FOREVER - SAME KEY V611_TOTAL</div><table style="width:100%;border-collapse:collapse"><tbody id="closed"></tbody></table></div>
<script>
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2)+' TOTAL '+j.total;
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' CAP $'+Number(j.cap||1000).toFixed(2)+' '+j.wins+'W/'+j.losses+'L TOTAL '+j.total+' NEVER RESET KEY V611_TOTAL';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/5 FROM 15 TOTAL '+j.rotate_coins.length+' COINS '+j.rotate_age+'s/300s TOTAL '+j.total;
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L TOTAL '+j.total+' CAP $'+Number(j.cap||1000).toFixed(2)+' NEVER RESET';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3)+' TOTAL '+j.total;
 document.getElementById('daily').style.color=j.daily>=0?'#FFD000':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' TOTAL '+j.total;
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L TOTAL '+j.total;
 document.getElementById('wlSub').innerText='WR '+wr+'% CAP $'+Number(j.cap||1000).toFixed(2)+' DAILY $'+Number(j.daily||0).toFixed(3)+' TOTAL '+j.total+' NEVER RESET KEY V611_TOTAL';
 document.getElementById('totalInfo').innerText=j.wins+'W/'+j.losses+'L TOTAL '+j.total+' CAP $'+Number(j.cap||1000).toFixed(2)+' DAILY $'+Number(j.daily||0).toFixed(3)+' NEVER RESET KEY V611_TOTAL';
 document.getElementById('totalDetail').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' CAP $'+Number(j.cap||1000).toFixed(2)+' WINS '+j.wins+' LOSSES '+j.losses+' TOTAL '+j.total+' NEVER RESET - ENV KV_REST_API_URL + TOKEN MUST BE SET IN VERCEL SETTINGS - SAME KEY V611_TOTAL';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' TOTAL '+j.wins+'W/'+j.losses+'L TOTAL '+j.total+' CAP $'+Number(j.cap||1000).toFixed(2);
 document.getElementById('rotateInfo').innerText=j.rotate_age+'s/300s - '+j.rotate_coins.length+' COINS - NEXT ROTATE IN '+(300-j.rotate_age)+'s - TOTAL '+j.total+' CAP $'+Number(j.cap||1000).toFixed(2);
 let rl=document.getElementById('rotatelist'); rl.innerHTML='';
 (j.rotate_coins||[]).forEach((m,i)=>{ rl.innerHTML+=`<div style="border:1px solid #FFD000;padding:2px 4px;font-size:7px;color:#FFD000">#${i+1} ${m.symbol} ${Number(m.c1||0).toFixed(2)}% M5 H1 ${Number(m.ch1||0).toFixed(2)}% VOL $${Number(m.vol||0).toFixed(0)} ${m.buys} BUYS TOTAL ${j.total}<br>STICK ${j.rotate_age}s</div>`; });
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).slice(0,25).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid #00FF88;padding:2px 4px;font-size:7px;color:#00FF88">#${i+1} ${m.symbol} ${Number(m.c1||0).toFixed(2)}% M5 H1 ${Number(m.ch1||0).toFixed(2)}% VOL $${Number(m.vol_m5||0).toFixed(0)} ${m.buys_m5} BUYS</div>`; });
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let peak=Number(t.peak_pct||0); let hh=Number(t.hh||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 60px 70px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:#FFD000">${t.symbol}</b> $${t.pos} HH ${hh} TOTAL ${j.total}</span><span>PEAK ${peak.toFixed(1)}%<br>HH ${hh}</span><span>AGE ${age}s</span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#FFD000;padding:10px">No open - TOTAL TRACK 15 COIN will fill 5/5 FROM 15 - ALWAYS 15 - STICK 5 MIN THEN NEW 15 - REAL NEW MONEY - SAME KEY V611_TOTAL NEVER RESET</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-50).reverse().forEach(c=>{
   cb.innerHTML+=`<tr><td style="padding:5px;border-bottom:1px solid #111;font-size:8px;color:#FFD000">${c.symbol} ${c.net>=0.15?'WINNER':'LOSER'} $${Number(c.net).toFixed(4)} PEAK ${Number(c.peak||0).toFixed(1)}% HH ${Number(c.hh||0)} TOTAL ${j.total} CAP $${Number(j.cap||1000).toFixed(2)}</td></tr>`;
 });
}
async function tick(){ await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR DAILY ONLY? KEEPS WINS/LOSSES/TOTAL/CAP - SAME KEY V611_TOTAL - TOTAL STAYS?')) return; await fetch('/api/clear_closed_fake'); await load(); }
setInterval(load,3000);load();
</script></body></html>"""

@app.route("/api/state")
def state():
    try: do_tick()
    except: pass
    data=rget()
    return jsonify({"cap":data.get("FUND_CAP",1000),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"total":data.get("FUND_TOTAL_TRADES",0),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",0),"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":data.get("FAST_WHALE",[]),"rotate_coins":data.get("ROTATE_COINS",[]),"rotate_age":int(time.time()-float(data.get("ROTATE_LAST",0) or 0)) if data.get("ROTATE_LAST") else 0,"kv":f"v615 TOTAL {data.get('FUND_WINS',0)}W/{data.get('FUND_LOSSES',0)}L TOTAL {data.get('FUND_TOTAL_TRADES',0)} CAP ${data.get('FUND_CAP',1000):.2f}"})

@app.route("/api/cron")
def cron(): return jsonify(do_tick())

@app.route("/api/debug")
def debug():
    data=rget()
    has_url=bool(UP_URL)
    has_token=bool(UP_TOKEN)
    return jsonify({"has_url":has_url,"has_token":has_token,"url_prefix":UP_URL[:25] if UP_URL else "MISSING","key":SINGLE_KEY,"cap":data.get("FUND_CAP"),"wins":data.get("FUND_WINS"),"losses":data.get("FUND_LOSSES"),"total":data.get("FUND_TOTAL_TRADES"),"daily":data.get("FUND_DAILY_PNL"),"open":len(data.get("FUND_OPEN",[])),"closed":len(data.get("FUND_CLOSED",[])),"kv":f"DEBUG {data.get('FUND_WINS',0)}W/{data.get('FUND_LOSSES',0)}L TOTAL {data.get('FUND_TOTAL_TRADES',0)} CAP ${data.get('FUND_CAP',0):.2f}"})

@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget()
    # KEEPS TOTAL - ONLY CLEARS DAILY/OPEN/CLOSED - FIXES TRACKING
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["LAST_LOSS_PEAK"]={}
    rset(data)
    return jsonify({"cleared":True,"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"total":data.get("FUND_TOTAL_TRADES",0),"cap":data.get("FUND_CAP",1000)})
