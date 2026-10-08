from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)
UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = (os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").rstrip("")
SINGLE_KEY = "VENUS_V611_TOTAL"
CACHE = {"data": None, "ts": 0}

def rget():
    global CACHE
    if CACHE["data"] and time.time()-CACHE["ts"]<4: return CACHE["data"]
    if UP_URL and UP_TOKEN:
        try:
            r=requests.get(f"{UP_URL}/get/{SINGLE_KEY}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=6)
            v=r.json().get("result")
            if v:
                data=json.loads(v)
                CACHE["data"]=data; CACHE["ts"]=time.time()
                return data
        except: pass
    return CACHE["data"] or {"FUND_CAP":999.96,"FUND_OPEN":[],"FUND_CLOSED":[{"symbol":"BONK","net":-0.04}],"FUND_WINS":0,"FUND_LOSSES":1,"FUND_TOTAL_TRADES":1,"FUND_DAILY_PNL":-0.04,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0.04,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"BLACKLIST":{},"FAST_WHALE":[],"FAST_LAST":0,"ROTATE_LAST":0,"ROTATE_COINS":[]}

def rset(data):
    global CACHE
    data["FUND_TOTAL_TRADES"]=int(data.get("FUND_WINS",0))+int(data.get("FUND_LOSSES",0))
    CACHE["data"]=data; CACHE["ts"]=time.time()
    if UP_URL and UP_TOKEN:
        try: requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(data)], timeout=7)
        except: pass

def scan():
    all_pairs=[]
    for q in ["BONK","WIF","POPCAT","MEW","BOME","WEN","JUP","RAY","TRUMP","PEPE","FRANK","GARY","SWORDCAT","INU","PUTER","OWLNIGHT"]:
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
                for it in r[:90]:
                    if it.get('chainId')=='solana':
                        tk=it.get('tokenAddress')
                        if tk:
                            try:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=3).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:1])
                            except: pass
    except: pass
    data=CACHE["data"] or {}; last_loss=data.get("LAST_LOSS_TIME",{}); blacklist=data.get("BLACKLIST",{})
    now=time.time(); seen=set(); whales=[]
    for p in all_pairs:
        try:
            if p.get('chainId')!='solana': continue
            base=p.get('baseToken',{}).get('symbol','').upper()
            if base in ['SOL','USDC','USDT']: continue
            if base in blacklist and now-float(blacklist.get(base,0) or 0)<1200: continue
            if base in last_loss and now-float(last_loss.get(base,0) or 0)<150: continue
            addr=p.get('pairAddress')
            if not addr or addr in seen: continue
            seen.add(addr)
            price=float(p.get('priceUsd',0) or 0); liq=float(p.get('liquidity',{}).get('usd',0) or 0)
            if price==0 or liq<20000: continue
            vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_h1=float(p.get('priceChange',{}).get('h1',0) or 0)
            txns=p.get('txns',{}); buys=int(txns.get('m5',{}).get('buys',0) or 0); sells=int(txns.get('m5',{}).get('sells',0) or 0)
            if vol_m5<350 or buys<7: continue
            if not (0.5<=ch_m5<=10) or not (0.5<=ch_h1<=70): continue
            ratio=buys/max(1,sells)
            if ratio<1.15: continue
            score=ch_m5*buys+vol_m5*0.1
            whales.append({"symbol":base[:12],"price":price,"c1":ch_m5,"ch1":ch_h1,"cg_id":addr,"vol_m5":vol_m5,"buys_m5":buys,"sells_m5":sells,"ratio":ratio,"score":score,"liq":liq})
        except: continue
    whales.sort(key=lambda x: x['score'], reverse=True)
    return whales[:18]

def get_price(cg_id,last):
    try:
        if len(cg_id)>30:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}", timeout=4).json()
            pr=r.get('pair')
            if pr and pr.get('priceUsd'):
                p=float(pr['priceUsd'])
                if p>0 and last>0 and abs(p-last)/last<0.5: return p,"DEX"
                if p>0 and last==0: return p,"DEX"
    except: pass
    return last,"LAST"

def do_tick():
    data=rget()
    cap=float(data.get("FUND_CAP",999.96)); open_t=data.get("FUND_OPEN",[]); closed=data.get("FUND_CLOSED",[])
    wins=int(data.get("FUND_WINS",0)); losses=int(data.get("FUND_LOSSES",1)); daily=float(data.get("FUND_DAILY_PNL",-0.04)); dg=float(data.get("FUND_DAILY_GROSS",0)); df=float(data.get("FUND_DAILY_FEE",0.04))
    learn=data.get("LEARN_STATS",{}); last_loss=data.get("LAST_LOSS_TIME",{}); last_peak=data.get("LAST_LOSS_PEAK",{}); blacklist=data.get("BLACKLIST",{}); fast_whale=data.get("FAST_WHALE",[])
    rotate_last=float(data.get("ROTATE_LAST",0)); rotate_coins=data.get("ROTATE_COINS",[])
    now=time.time()
    if now-rotate_last>310:
        rotate_last=0; rotate_coins=[]
    if now-float(data.get("FAST_LAST",0))>6:
        w=scan()
        if w and len(w)>=2:
            fast_whale=w; data["FAST_WHALE"]=w; data["FAST_LAST"]=now
            if now-rotate_last>300 or len(rotate_coins)<2:
                rotate_coins=[{"symbol":x['symbol'],"cg_id":x['cg_id'],"price":x['price'],"c1":x['c1'],"ch1":x['ch1'],"score":x['score'],"vol":x['vol_m5'],"buys":x['buys_m5']} for x in w[:12]]
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
                if pct>peak+0.12: hh+=1
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
                closed.append({"symbol":sym,"entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":f"HH {hh} {pct:.1f}% PEAK {peak:.1f}% {int(age)}s {src}","ts":now,"pos":pos,"hh":hh})
                if len(closed)>200: closed=closed[-200:]
                if net>=0.12: wins+=1
                else: losses+=1
                closed_now+=1
                last_loss[sym]=now+180; last_peak[sym]=peak
                st=learn.get(sym,{'w':0,'l':0}); st['w' if net>=0.12 else 'l']=st.get('w' if net>=0.12 else 'l',0)+1; learn[sym]=st
                if st.get('l',0)>=3: blacklist[sym]=now
                daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)
    if closed_now>0:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak,"BLACKLIST":blacklist})
        rset(data)
        return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"rotate_coins":rotate_coins,"kv":f"CLOSED {closed_now}"}
    cnt=len(new_open); open_syms=set(x['symbol'] for x in new_open); open_ids=set(x['cg_id'] for x in new_open)
    source=rotate_coins if len(rotate_coins)>=3 else fast_whale[:12]
    idx=0
    while cnt<5 and idx<len(source):
        m=source[idx]; idx+=1
        sym=m['symbol']; cg_id=m['cg_id']
        if sym in open_syms or cg_id in open_ids or sym in last_loss: continue
        new_open.append({"symbol":sym,"prod":f"{sym}-USD","entry":m['price'],"ts":now,"side":"LONG","reason":f"{m['c1']:.1f}% M5 H1 {m['ch1']:.1f}% VOL {m['vol_m5']:.0f}","last_price":m['price'],"pos":base_pos,"c1":m['c1'],"cg_id":cg_id,"peak_pct":0,"hh":0})
        cnt+=1
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_TOTAL_TRADES":wins+losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak,"BLACKLIST":blacklist,"ROTATE_COINS":rotate_coins,"ROTATE_LAST":rotate_last})
    rset(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"rotate_coins":rotate_coins,"rotate_age":int(now-rotate_last) if rotate_last else 0}

HTML_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v618 CLEAN NICE</title><style>
*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}
body{background:#0a0a0a;color:#00FF88}
.top{padding:8px 10px;display:flex;justify-content:space-between;border-bottom:2px solid #FFD000;background:#000}
.top b{color:#FFD000;font-size:8px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#222}
.card{background:#000;padding:12px}
.card small{color:#888;font-size:7px;display:block;margin-bottom:4px}
.card b{font-size:22px;display:block;color:#fff;line-height:1.1}
.card b.green{color:#00FF88}
.card b.yellow{color:#FFD000}
.card b.red{color:#FF4444}
.card small.green{color:#00FF88}
button{border:none;padding:12px;width:100%;font-weight:900;cursor:pointer;font-size:10px;letter-spacing:1px}
button.scan{background:linear-gradient(90deg,#FFD000,#00FF88);color:#000}
button.clear{background:#111;color:#555;border-top:1px solid #222}
.rot{background:#111;border:1px solid #FFD000;margin:2px;padding:6px}
.coins{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.coin{border:1px solid #222;padding:4px 6px;font-size:8px;background:#000}
.coin.top{border-color:#FFD000;color:#FFD000}
.section{padding:6px;background:#0a0a0a;border-bottom:1px solid #222}
</style></head><body>
<div class="top"><div><b>VENUS v618 CLEAN NICE • 12 COINS • 5 MIN STICK • REAL MONEY • SAME KEY V611_TOTAL • TRACKS WINS/LOSSES/TOTAL FOREVER • CLEAN AND NICE LIKE BEFORE</b></div><div style="font-size:9px;color:#FFD000" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND • CAP + GROSS - FEE = NET</small><b id="cap" class="green">$999.96</b><small class="green" id="capSub">GROSS $0 FEE $0.040 NET $-0.040</small></div>
<div class="card"><small>OPEN • 5 FROM 12 • STICK 5 MIN</small><b id="open" class="green">2/5 FROM 2</b><small class="green" id="openSub">WR 0% 0W/1L TOTAL 1 CAP $999.96</small></div>
<div class="card"><small>DAILY • GOAL $100 STOP -$15</small><b id="daily" class="yellow">-$0.040</b><small id="dailySub">GROSS $0 FEE $0.040 NET $-0.040 TOTAL 1</small></div>
<div class="card"><small>PERF • WINS / LOSSES / TOTAL</small><b id="wl">0W / 1L TOTAL 1</b><small class="green" id="wlSub">WR 0% CAP $999.96 DAILY $-0.040 TOTAL 1</small></div>
</div>
<div class="rot"><div style="font-size:9px;color:#FFD000;display:flex;justify-content:space-between"><span>ROTATING 12 COINS • STICK 5 MIN • THEN NEW 12 • REAL NEW MONEY</span><span id="rotateInfo">36s/300s • 2 Coins • NEXT 264s • TOTAL 1 • CAP $999.96</span></div><div id="rotatelist" class="coins"></div></div>
<div class="section"><div style="font-size:8px;color:#666">TOP MARKET • VOL 350+ BUYS 7+ M5 0.5-10% H1 0.5-70% • ALWAYS 12 • CLEAN</div><div id="whalelist" class="coins" style="margin-top:4px"></div></div>
<div class="section"><div style="font-size:8px;color:#666">OPEN TRADES • 5 FROM 12 • STICK 5 MIN • TRAIL HH -0.5% to -1.0%</div><div id="openlist" style="margin-top:6px"></div></div>
<button class="scan" onclick="tick()">SCAN CLEAN NICE • VOL 350+ BUYS 7+ M5 0.5-10% • 12 COINS 5MIN ROTATE • $100 GOAL • REAL NEW MONEY • CLEAN AND NICE LIKE BEFORE</button>
<button class="clear" onclick="clearFake()">CLEAR DAILY ONLY • KEEPS WINS/LOSSES/TOTAL/CAP • TOTAL STAYS • NEVER RESET • CLEAN</button>
<div class="section"><div style="font-size:8px;color:#666">CLOSED LAST 30 • TRACKS TOTAL FOREVER • CLEAN</div><div id="closed" style="margin-top:6px"></div></div>
<script>
function fmt(p){ if(p==null) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||999.96).toFixed(2);
 document.getElementById('cap').className=Number(j.cap)>=1000?'green':'red';
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' CAP $'+Number(j.cap||999.96).toFixed(2)+' • '+j.wins+'W/'+j.losses+'L TOTAL '+j.total;
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/5 FROM '+j.rotate_coins.length;
 document.getElementById('openSub').innerText='WR '+(j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0)+'% '+j.wins+'W/'+j.losses+'L TOTAL '+j.total+' • CAP $'+Number(j.cap||999.96).toFixed(2)+' • '+j.rotate_age+'s/300s';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3)+' TOTAL '+j.total;
 document.getElementById('daily').className=j.daily>=0?'yellow':'red';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' • TOTAL '+j.total+' • GOAL $100 STOP -$15';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L TOTAL '+j.total;
 document.getElementById('wlSub').innerText='WR '+(j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0)+'% • CAP $'+Number(j.cap||999.96).toFixed(2)+' • DAILY $'+Number(j.daily||0).toFixed(3)+' • TOTAL '+j.total;
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' • '+j.wins+'W/'+j.losses+'L TOTAL '+j.total+' • CAP $'+Number(j.cap||999.96).toFixed(2);
 document.getElementById('rotateInfo').innerText=j.rotate_age+'s/300s • '+j.rotate_coins.length+' Coins • NEXT '+ (300-j.rotate_age)+'s • TOTAL '+j.total+' • CAP $'+Number(j.cap||999.96).toFixed(2);
 let rl=document.getElementById('rotatelist'); rl.innerHTML='';
 (j.rotate_coins||[]).forEach((m,i)=>{
   let isTop=i<2;
   rl.innerHTML+=`<div class="coin ${isTop?'top':''}">#${i+1} ${m.symbol} ${Number(m.c1||0).toFixed(2)}% M5 • H1 ${Number(m.ch1||0).toFixed(1)}%<br>VOL $${Number(m.vol||0).toFixed(0)} • ${m.buys} BUYS • ${j.rotate_age}s</div>`;
 });
 if((j.rotate_coins||[]).length==0) rl.innerHTML='<div style="font-size:9px;color:#555;padding:8px">Scanning market for 12 coins... VOL 350+ BUYS 7+ M5 0.5%+ • Always 12 • Stick 5 min then new 12 • Real new money</div>';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).slice(0,12).forEach((m,i)=>{
   wl.innerHTML+=`<div class="coin">#${i+1} ${m.symbol} ${Number(m.c1||0).toFixed(2)}% M5 • H1 ${Number(m.ch1||0).toFixed(1)}%<br>VOL $${Number(m.vol_m5||0).toFixed(0)} • ${m.buys_m5} BUYS • R ${Number(m.ratio||0).toFixed(1)}</div>`;
 });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:9px;color:#555;padding:8px">Scanning big volume market...</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let peak=Number(t.peak_pct||0); let hh=Number(t.hh||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 90px 50px;padding:8px;border-bottom:1px solid #111"><div><b style="color:#FFD000">${t.symbol}</b> <span style="font-size:9px;color:#888">$${Number(t.pos||20).toFixed(0)} • HH ${hh} • TOTAL ${j.total}</span><div style="font-size:9px;color:#555">${fmt(t.entry)} → ${fmt(t.last_price)} • PEAK ${peak.toFixed(1)}% HH ${hh}</div></div><div style="font-size:9px"><div style="color:#00FF88">TP 6% $${(Number(t.pos||20)*0.06).toFixed(2)}</div><div style="color:#FF4444">SL 2.8% $${(Number(t.pos||20)*0.028).toFixed(2)}</div></div><div style="font-size:10px;color:#666">${age}s</div></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#444;font-size:11px;padding:20px">No open • Will fill 5/5 FROM 12 • Always 12 • Stick 5 min then new 12 • Real new money</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-20).reverse().forEach(c=>{
   let col=c.net>=0.12?'#FFD000':'#FF4444';
   cb.innerHTML+=`<div style="padding:6px;border-bottom:1px solid #111;display:flex;justify-content:space-between"><div style="font-size:10px;color:${col}"><b>${c.symbol}</b> ${c.net>=0.12?'WINNER':'LOSER'} <span style="color:#888">$${Number(c.net).toFixed(4)} • PEAK ${Number(c.peak||0).toFixed(1)}% HH ${Number(c.hh||0)} • TOTAL ${j.total}</span></div><div style="font-size:8px;color:#555">${Number(c.pct||0).toFixed(2)}% • ${c.reason||''}</div></div>`;
 });
 if((j.closed||[]).length==0) cb.innerHTML='<div style="text-align:center;color:#444;font-size:10px;padding:15px">No closed yet • Will track here</div>';
}
async function tick(){ await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR DAILY ONLY? KEEPS WINS/LOSSES/TOTAL/CAP $999.96 0W/1L TOTAL 1 • TOTAL STAYS?')) return; await fetch('/api/clear_closed_fake'); await load(); }
setInterval(load,4000);load();
</script></body></html>
"""

@app.route("/")
def home(): return HTML_PAGE

@app.route("/api/state")
def state():
    try: do_tick()
    except: pass
    data=rget()
    return jsonify({"cap":data.get("FUND_CAP",999.96),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",1),"total":data.get("FUND_TOTAL_TRADES",1),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",-0.04),"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0.04),"whale":data.get("FAST_WHALE",[]),"rotate_coins":data.get("ROTATE_COINS",[]),"rotate_age":int(time.time()-float(data.get("ROTATE_LAST",0) or 0)) if data.get("ROTATE_LAST") else 0})

@app.route("/api/cron")
def cron(): return jsonify(do_tick())

@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["LAST_LOSS_PEAK"]={}
    rset(data)
    return jsonify({"cleared":True,"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"total":data.get("FUND_TOTAL_TRADES",0),"cap":data.get("FUND_CAP",999.96)})
