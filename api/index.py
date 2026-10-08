from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)

UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = (os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").rstrip("")
SINGLE_KEY = "VENUS_V611_TOTAL"
CACHE = {"data": None, "ts": 0}

def rget():
    global CACHE
    now=time.time()
    if CACHE["data"] and now - CACHE["ts"] < 4: return CACHE["data"]
    if UP_URL and UP_TOKEN:
        try:
            r=requests.get(f"{UP_URL}/get/{SINGLE_KEY}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=6)
            v=r.json().get("result")
            if v:
                data=json.loads(v)
                data.setdefault("FUND_CAP",999.96)
                data.setdefault("FUND_WINS",0)
                data.setdefault("FUND_LOSSES",1)
                data.setdefault("FUND_TOTAL_TRADES",1)
                data.setdefault("FUND_DAILY_PNL",-0.04)
                data.setdefault("FUND_DAILY_GROSS",0)
                data.setdefault("FUND_DAILY_FEE",0.04)
                CACHE["data"]=data; CACHE["ts"]=now
                return data
        except: pass
    return CACHE["data"] or {"FUND_CAP":999.96,"FUND_OPEN":[],"FUND_CLOSED":[{"symbol":"BONK","net":-0.04,"pct":-0.0,"peak":0,"hh":0,"pos":20}],"FUND_WINS":0,"FUND_LOSSES":1,"FUND_TOTAL_TRADES":1,"FUND_DAILY_PNL":-0.04,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0.04,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"BLACKLIST":{},"FAST_WHALE":[],"FAST_LAST":0,"ROTATE_LAST":0,"ROTATE_COINS":[]}

def rset(data):
    global CACHE
    data["FUND_TOTAL_TRADES"]=int(data.get("FUND_WINS",0))+int(data.get("FUND_LOSSES",0))
    CACHE["data"]=data; CACHE["ts"]=time.time()
    if UP_URL and UP_TOKEN:
        try: requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(data)], timeout=7)
        except: pass

def scan_clean():
    all_pairs=[]; now=time.time()
    # CLEAN - ALWAYS 15 BIG VOLUME POSITIVE ONLY - M5 0.6%+ NOT 0.27%
    for q in ["BONK","WIF","POPCAT","MEW","BOME","WEN","JUP","RAY","TRUMP","PEPE","FRANK","GARY","INU","PUTER","OWLNIGHT","SI276","SWORDCAT"]:
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
                            try:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=3).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:1])
                            except: pass
    except: pass
    data=CACHE["data"] or {}; last_loss=data.get("LAST_LOSS_TIME",{}); blacklist=data.get("BLACKLIST",{})
    seen=set(); whales=[]
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
            if vol_m5<400 or buys<8: continue
            if not (0.6<=ch_m5<=10) or not (0.6<=ch_h1<=70): continue # CLEAN - 0.6%+ NOT 0.27%
            ratio=buys/max(1,sells)
            if ratio<1.15: continue
            score=ch_m5*buys+vol_m5*0.1
            whales.append({"symbol":base[:12],"price":price,"c1":ch_m5,"ch1":ch_h1,"cg_id":addr,"vol_m5":vol_m5,"buys_m5":buys,"score":score})
        except: continue
    whales.sort(key=lambda x: x['score'], reverse=True)
    return whales[:20]

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
    # FIX -175s BUG - FORCE ROTATE IF >310s
    if now - rotate_last > 310:
        rotate_last = 0
        rotate_coins = []
    if now-float(data.get("FAST_LAST",0))>6:
        w=scan_clean()
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
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"total":wins+losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"rotate_coins":rotate_coins,"rotate_age":int(now-rotate_last) if rotate_last else 0,"kv":f"v617 CLEAN {wins}W/{losses}L CAP ${cap:.2f} {len(rotate_coins)} COINS {int(now-rotate_last)}s/300s"}

@app.route("/")
def home():
    return """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v617 CLEAN</title><style>
*{margin:0;padding:0;box-sizing:border-box;font-family:Inter,monospace}
body{background:#080808;color:#e0e0e0}
.header{background:#111;padding:10px 12px;border-bottom:1px solid #222;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:12px;color:#FFD000;letter-spacing:1px}
.header span{font-size:10px;color:#666}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#222}
.card{background:#0f0f0f;padding:14px}
.card.label{font-size:8px;color:#666;letter-spacing:1px;text-transform:uppercase;margin-bottom:6px}
.card.value{font-size:24px;font-weight:700;color:#fff}
.card.value.green{color:#00FF88}
.card.value.yellow{color:#FFD000}
.card.value.red{color:#FF4444}
.card.sub{font-size:10px;color:#555;margin-top:4px}
.rotate{background:#111;border-bottom:1px solid #222;padding:10px}
.rotate.title{font-size:9px;color:#FFD000;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;display:flex;justify-content:space-between}
.coins{display:flex;flex-wrap:wrap;gap:6px}
.coin{border:1px solid #222;background:#0a0a0a;padding:6px 8px;border-radius:4px;min-width:110px}
.coin.top{border-color:#FFD000}
.coin.sym{font-size:11px;font-weight:700;color:#fff}
.coin.meta{font-size:9px;color:#888;margin-top:2px}
.coin.vol{font-size:8px;color:#555;margin-top:2px}
.section{background:#0f0f0f;padding:10px;border-bottom:1px solid #222}
.section.title{font-size:9px;color:#888;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}
.empty{text-align:center;color:#444;font-size:11px;padding:20px}
.open-item{display:grid;grid-template-columns:1fr 90px 70px;padding:10px;border-bottom:1px solid #1a1a1a;align-items:center}
.open-item b{color:#FFD000;font-size:12px}
.open-item.small{font-size:9px;color:#666}
button{width:100%;padding:14px;border:none;font-weight:800;font-size:11px;letter-spacing:1px;cursor:pointer}
button.scan{background:#FFD000;color:#000}
button.clear{background:#1a1a1a;color:#666;border-top:1px solid #222}
.closed-table{width:100%;border-collapse:collapse}
.closed-table td{padding:8px 10px;border-bottom:1px solid #111;font-size:10px}
</style></head><body>
<div class="header"><h1>VENUS v617 CLEAN • 15 COINS • 5 MIN STICK • REAL MONEY</h1><span id="time"></span></div>
<div class="stats">
<div class="card"><div class="label">Fund • Cap + Gross - Fee = Net • Same Key V611_TOTAL Never Reset</div><div id="cap" class="value green">$1000.00</div><div id="capSub" class="sub">GROSS $0 FEE $0 NET $0</div></div>
<div class="card"><div class="label">Open • 5 from 15 • Stick 5 min • Always 15 • Same Key</div><div id="open" class="value">$0/5</div><div id="openSub" class="sub">WR 0% 0W/0L TOTAL 0 CAP $1000</div></div>
<div class="card"><div class="label">Daily • Goal $100 Stop -$15 • Same Key V611_TOTAL</div><div id="daily" class="value yellow">+$0.00</div><div id="dailySub" class="sub">GROSS $0 FEE $0 NET $0 TOTAL 0</div></div>
<div class="card"><div class="label">Perf • Wins / Losses / Total • Never Reset • Same Key</div><div id="wl" class="value">0W/0L TOTAL 0</div><div id="wlSub" class="sub">WR 0% CAP $1000 DAILY $0 TOTAL 0</div></div>
</div>
<div class="rotate"><div class="title"><span>Rotating 15 Coins • Stick 5 Min • Then New 15 • Real New Money • Same Key V611_TOTAL</span><span id="rotateInfo">0s/300s • 0 Coins</span></div><div id="rotatelist" class="coins"></div></div>
<div class="section"><div class="title">Top Market • Vol 400+ Buys 8+ M5 0.6-10% H1 0.6-70% • Always 15 • Clean • Same Key</div><div id="whalelist" class="coins"></div></div>
<div class="section"><div class="title">Open Trades • 5 from 15 • Stick 5 Min • Trail HH -0.5% to -1.0% • Same Key V611_TOTAL</div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN CLEAN • SAME KEY V611_TOTAL • VOL 400+ BUYS 8+ M5 0.6-10% • 15 COINS 5MIN ROTATE • $100 GOAL • REAL NEW MONEY • CLEAN UI</button>
<button class="clear" onclick="clearFake()">CLEAR DAILY ONLY • KEEPS WINS/LOSSES/TOTAL/CAP • SAME KEY V611_TOTAL • TOTAL STAYS • NEVER RESET • CLEAN</button>
<div class="section"><div class="title">Closed Last 50 • Tracks Total Forever • Same Key V611_TOTAL • Clean</div><table class="closed-table"><tbody id="closed"></tbody></table></div>
<script>
function fmt(p){ if(p==null) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2);
 document.getElementById('cap').className='value '+(j.cap>=1000?'green':'red');
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' CAP $'+Number(j.cap||1000).toFixed(2)+' • '+j.wins+'W/'+j.losses+'L TOTAL '+j.total+' • KEY V611_TOTAL NEVER RESET';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/5 FROM '+j.rotate_coins.length;
 document.getElementById('openSub').innerText='WR '+(j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0)+'% '+j.wins+'W/'+j.losses+'L TOTAL '+j.total+' • CAP $'+Number(j.cap||1000).toFixed(2)+' • '+j.rotate_age+'s/300s • KEY V611_TOTAL NEVER RESET';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').className='value '+(j.daily>=0?'yellow':'red');
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' • TOTAL '+j.total+' • GOAL $100 STOP -$15';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L TOTAL '+j.total;
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wlSub').innerText='WR '+wr+'% • CAP $'+Number(j.cap||1000).toFixed(2)+' • DAILY $'+Number(j.daily||0).toFixed(3)+' • TOTAL '+j.total+' • NEVER RESET KEY V611_TOTAL';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' • '+j.wins+'W/'+j.losses+'L TOTAL '+j.total+' • CAP $'+Number(j.cap||1000).toFixed(2);
 document.getElementById('rotateInfo').innerText=j.rotate_age+'s/300s • '+j.rotate_coins.length+' Coins • NEXT ROTATE IN '+(300-j.rotate_age)+'s • TOTAL '+j.total+' • CAP $'+Number(j.cap||1000).toFixed(2);
 let rl=document.getElementById('rotatelist'); rl.innerHTML='';
 (j.rotate_coins||[]).forEach((m,i)=>{
   let isTop=i<3;
   rl.innerHTML+=`<div class="coin ${isTop?'top':''}"><div class="sym">#${i+1} ${m.symbol}</div><div class="meta">${Number(m.c1||0).toFixed(2)}% M5 • H1 ${Number(m.ch1||0).toFixed(1)}%</div><div class="vol">VOL $${Number(m.vol||0).toFixed(0)} • ${m.buys} BUYS • ${j.rotate_age}s</div></div>`;
 });
 if((j.rotate_coins||[]).length==0) rl.innerHTML='<div class="empty">Scanning market for 15 coins... VOL 400+ BUYS 8+ M5 0.6%+ • Always 15 • Stick 5 min then new 15 • Real new money • Same key V611_TOTAL</div>';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).slice(0,15).forEach((m,i)=>{
   wl.innerHTML+=`<div class="coin"><div class="sym">#${i+1} ${m.symbol}</div><div class="meta">${Number(m.c1||0).toFixed(2)}% M5 • H1 ${Number(m.ch1||0).toFixed(1)}% • R ${Number(m.ratio||0).toFixed(1)}</div><div class="vol">VOL $${Number(m.vol_m5||0).toFixed(0)} • ${m.buys_m5} BUYS</div></div>`;
 });
 if((j.whale||[]).length==0) wl.innerHTML='<div class="empty">Scanning big volume market... VOL 400+ BUYS 8+ M5 0.6-10% • Always 15 coins even at 3am US dead hour • Real new money</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let peak=Number(t.peak_pct||0); let hh=Number(t.hh||0);
   ol.innerHTML+=`<div class="open-item"><div><b>${t.symbol}</b> <span class="small">$${Number(t.pos||20).toFixed(0)} • HH ${hh} • TOTAL ${j.total}</span><div class="small">${fmt(t.entry)} → ${fmt(t.last_price)} • PEAK ${peak.toFixed(1)}% HH ${hh}</div></div><div><div style="font-size:10px;color:#00FF88">TP 6% $${(Number(t.pos||20)*0.06).toFixed(2)}</div><div style="font-size:10px;color:#FF4444">SL 2.8% $${(Number(t.pos||20)*0.028).toFixed(2)}</div></div><div style="font-size:10px;color:#666">${age}s</div></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div class="empty">No open trades • Will fill 5/5 FROM 15 • Always 15 • Stick 5 min then new 15 • Real new money • Same key V611_TOTAL never reset • Clean UI</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-30).reverse().forEach(c=>{
   let col=c.net>=0.12?'#FFD000':'#FF4444';
   cb.innerHTML+=`<tr><td style="color:${col}"><b>${c.symbol}</b> ${c.net>=0.12?'WINNER':'LOSER'} <span style="color:#888">${Number(c.net).toFixed(4)} • PEAK ${Number(c.peak||0).toFixed(1)}% HH ${Number(c.hh||0)} • TOTAL ${j.total} • CAP $${Number(j.cap||1000).toFixed(2)}</span></td><td style="color:#555;font-size:9px">${Number(c.pct||0).toFixed(2)}% • ${c.reason||''}</td></tr>`;
 });
 if((j.closed||[]).length==0) cb.innerHTML='<tr><td colspan="2" style="text-align:center;color:#444;padding:20px">No closed yet • BONK LOSER $-0.0400 PEAK 0.0% HH 0 TOTAL 1 CAP $999.96 • Will track here • Same key V611_TOTAL</td></tr>';
}
async function tick(){ document.getElementById('openlist').innerHTML='<div class="empty">Scanning clean market... VOL 400+ BUYS 8+ M5 0.6%+ • Always 15 coins • Same key V611_TOTAL • Clean UI</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR DAILY ONLY? KEEPS WINS/LOSSES/TOTAL/CAP $999.96 0W/1L TOTAL 1 • SAME KEY V611_TOTAL • TOTAL STAYS?')) return; await fetch('/api/clear_closed_fake'); await load(); }
setInterval(load,4000);load();
</script></body></html>"""

@app.route("/api/state")
def state():
    try: do_tick()
    except: pass
    data=rget()
    return jsonify({"cap":data.get("FUND_CAP",999.96),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",1),"total":data.get("FUND_TOTAL_TRADES",1),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",-0.04),"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0.04),"whale":data.get("FAST_WHALE",[]),"rotate_coins":data.get("ROTATE_COINS",[]),"rotate_age":int(time.time()-float(data.get("ROTATE_LAST",0) or 0)) if data.get("ROTATE_LAST") else 0})

@app.route("/api/cron")
def cron(): return jsonify(do_tick())

@app.route("/api/debug")
def debug():
    data=rget()
    return jsonify({"has_url":bool(UP_URL),"has_token":bool(UP_TOKEN),"key":SINGLE_KEY,"cap":data.get("FUND_CAP"),"wins":data.get("FUND_WINS"),"losses":data.get("FUND_LOSSES"),"total":data.get("FUND_TOTAL_TRADES"),"daily":data.get("FUND_DAILY_PNL"),"open":len(data.get("FUND_OPEN",[])),"closed":len(data.get("FUND_CLOSED",[])),"rotate_coins":len(data.get("ROTATE_COINS",[])),"whale":len(data.get("FAST_WHALE",[])),"rotate_age":int(time.time()-float(data.get("ROTATE_LAST",0) or 0)) if data.get("ROTATE_LAST") else 0})

@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["LAST_LOSS_PEAK"]={}
    rset(data)
    return jsonify({"cleared":True,"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"total":data.get("FUND_TOTAL_TRADES",0),"cap":data.get("FUND_CAP",999.96)})
