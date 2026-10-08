from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)
UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
SINGLE_KEY = "VENUS_V600_DATA"
DAILY_GOAL = 100.0
DAILY_STOP = -20.0
CACHE = {"data": None, "ts": 0}

def rget_single():
    global CACHE
    now=time.time()
    if CACHE["data"] and now - CACHE["ts"] < 12:
        return CACHE["data"]
    try:
        if not UP_URL or not UP_TOKEN:
            return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"FAST_WHALE":[],"FAST_LAST":0}
        r=requests.get(f"{UP_URL}/get/{SINGLE_KEY}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=5)
        v=r.json().get("result")
        if v:
            data=json.loads(v)
            CACHE["data"]=data; CACHE["ts"]=now
            return data
    except: pass
    return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"FAST_WHALE":[],"FAST_LAST":0}

def rset_single(data):
    global CACHE
    CACHE["data"]=data; CACHE["ts"]=time.time()
    try:
        if not UP_URL or not UP_TOKEN: return
        last=float(data.get("_last_save",0) or 0)
        if time.time()-last < 6: return
        data["_last_save"]=time.time()
        requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(data)], timeout=5)
    except: pass

def get_whales():
    whales=[]
    try:
        all_pairs=[]
        try:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q=SOL", timeout=8).json()
            if r.get('pairs'): all_pairs.extend(r['pairs'][:40])
        except: pass
        for url in ["https://api.dexscreener.com/token-boosts/latest/v1","https://api.dexscreener.com/token-boosts/top/v1"]:
            try:
                r=requests.get(url, timeout=7).json()
                if isinstance(r,list):
                    for it in r[:120]:
                        if it.get('chainId')=='solana':
                            tk=it.get('tokenAddress')
                            if tk:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=5).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:1])
            except: pass
        for q in ["SWORDCAT","MISTAKE","BONK","WIF","POPCAT","MEW","MUMU","PUMP","TRUMP","BODEN","WEN","JUP","RAY","JTO","PYTH","BOME","SLERF","CAT","DOG","PEPE"]:
            try:
                sr=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=5).json()
                if sr.get('pairs'): all_pairs.extend(sr['pairs'][:3])
            except: pass
        seen=set()
        data=CACHE["data"] or {}
        learn=data.get("LEARN_STATS",{}) if isinstance(data, dict) else {}
        for p in all_pairs:
            try:
                if p.get('chainId')!='solana': continue
                base=p.get('baseToken',{}).get('symbol','').upper()
                if base in ['SOL','USDC','USDT','WETH','WBTC','WSOL']: continue
                addr=p.get('pairAddress')
                if not addr or addr in seen: continue
                seen.add(addr)
                fdv=float(p.get('fdv',0) or 0); liq=float(p.get('liquidity',{}).get('usd',0) or 0); price=float(p.get('priceUsd',0) or 0)
                if price==0: continue
                if not (15000 <= liq <= 500000): continue
                if not (80000 <= fdv <= 8000000): continue
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0)
                txns=p.get('txns',{}); buys=int(txns.get('m5',{}).get('buys',0) or 0); sells=int(txns.get('m5',{}).get('sells',0) or 0)
                if vol_m5 < 150: continue
                if buys < 3: continue
                if ch_m5 < -5 or ch_m5 > 60: continue
                move = buys * max(1,vol_m5) * max(0.1,abs(ch_m5)) * 0.01
                ratio = buys / max(1,sells)
                v_l = vol_m5 / max(1,liq) * 100
                fp = ratio*1.5 + v_l
                st=learn.get(base,{'w':0,'l':0})
                score = move + fp*30 + buys*10 + abs(ch_m5)*80 + vol_m5*0.1
                if st.get('w',0)>0: score*=5.5
                if ch_m5>=1.5: score*=1.6
                if vol_m5>=800: score*=1.2
                tier="5 BEST WIDE"
                whales.append({"prod":f"{base}-USD","symbol":base[:12],"price":price,"c1":ch_m5,"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys,"sells_m5":sells,"score":score,"tier":tier,"wins":st.get('w',0),"move":move,"fp":fp,"ratio":ratio,"vl":v_l})
            except: continue
        whales.sort(key=lambda x: x['score'], reverse=True)
        return whales[:20]
    except: return []

def get_price(cg_id,last=0):
    try:
        if len(cg_id)>30:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}", timeout=4).json()
            if r.get('pair') and r['pair'].get('priceUsd'):
                p=float(r['pair']['priceUsd'])
                if p>0: return p,"DEX"
    except: pass
    return 0,"FAIL"

def do_tick():
    data=rget_single()
    cap=float(data.get("FUND_CAP") or 1000.0); open_t=data.get("FUND_OPEN") or []; closed=data.get("FUND_CLOSED") or []
    wins=data.get("FUND_WINS") or 0; losses=data.get("FUND_LOSSES") or 0
    daily=float(data.get("FUND_DAILY_PNL") or 0); dg=float(data.get("FUND_DAILY_GROSS") or 0); df=float(data.get("FUND_DAILY_FEE") or 0)
    learn=data.get("LEARN_STATS") or {}; last_loss=data.get("LAST_LOSS_TIME") or {}; last_peak=data.get("LAST_LOSS_PEAK") or {}; fast_whale=data.get("FAST_WHALE") or []
    now=time.time()
    if now - float(data.get("FAST_LAST") or 0) > 8:
        w=get_whales()
        if w: fast_whale=w; data["FAST_WHALE"]=w; data["FAST_LAST"]=now
    base_pos=20.14
    if cap>=1015: base_pos=24.0
    if cap>=1050: base_pos=30.0
    if cap>=1100: base_pos=38.0
    new_open=[]
    for tr in open_t:
        try:
            sym=tr.get('symbol','?'); entry=float(tr.get('entry',0) or 0); last=float(tr.get('last_price',entry) or entry); pos=float(tr.get('pos',base_pos) or base_pos); cg_id=tr.get('cg_id','')
            peak=float(tr.get('peak_pct',0) or 0); hh=int(tr.get('hh',0) or 0); start=float(tr.get('ts',now) or now)
            if entry==0: continue
            cur,src=get_price(cg_id,last)
            if cur==0:
                for fm in fast_whale:
                    if fm.get('cg_id')==cg_id:
                        cur=fm['price']; src="FAST"; break
            if cur==0: cur=last
            age=now-start; pct=(cur-entry)/entry*100; fee=pos*0.002; gross=pos*pct/100; net=gross-fee
            if pct > peak:
                if pct > peak+0.1: hh+=1
                peak=pct; tr['peak_pct']=peak; tr['hh']=hh
            close=False
            trail=-0.40
            if hh>=7: trail=-1.3
            elif hh>=5: trail=-1.0
            elif hh>=3: trail=-0.70
            elif hh>=2: trail=-0.55
            if age<50 and pct<=-2.8 and hh==0: close=True
            elif age>=300: close=True
            elif age>=180 and peak<1.2: close=True
            elif age>=90 and peak<0.5: close=True
            elif peak>=3.0 and pct <= peak + trail: close=True
            elif pct<=-2.8: close=True
            if close:
                closed.append({"symbol":sym,"prod":tr.get('prod',sym),"side":"LONG","entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":f"V600 WIDE HH {hh} {pct:.1f}% PEAK {peak:.1f}%","ts":now,"is_meme":False,"pos":pos,"hh":hh})
                if len(closed)>500: closed=closed[-500:]
                if net>=0.2: wins+=1
                else: losses+=1
                last_loss[sym]=now+8 if net>=0.2 else now+30
                last_peak[sym]=peak
                st=learn.get(sym,{'w':0,'l':0}); st['w' if net>=0.2 else 'l']=st.get('w' if net>=0.2 else 'l',0)+1; learn[sym]=st
                daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)
    if daily >= DAILY_GOAL or daily <= DAILY_STOP:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak})
        rset_single(data); return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"{'GOAL' if daily>=DAILY_GOAL else 'STOP'} ${daily:.2f} V600 WIDE"}
    cnt=len(new_open); idx=0
    open_syms=set(x['symbol'] for x in new_open)
    open_ids=set(x['cg_id'] for x in new_open)
    force = len(fast_whale)>=1
    while cnt<5 and idx<len(fast_whale):
        try:
            m=fast_whale[idx]; idx+=1; sym=m['symbol']
            if sym in open_syms and not force: continue
            if m['cg_id'] in open_ids and not force: continue
            if sym in last_loss and not force:
                if now-float(last_loss.get(sym,0) or 0) < 30: continue
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":now,"side":"LONG","reason":f"WIDE V600","target":6.0,"stop":2.8,"last_price":m['price'],"pos":base_pos,"c1":m['c1'],"cg_id":m['cg_id'],"is_meme":False,"fdv":m['fdv'],"peak_pct":0,"hh":0,"tier":m.get('tier','WIDE')})
            open_syms.add(sym); open_ids.add(m['cg_id']); cnt+=1
        except: continue
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak})
    rset_single(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"v600 WIDE SCAN 20 BEST VOL 150+ BUYS 3+ ANY COIN 5/5 ALWAYS FORCE 45s GOAL ${DAILY_GOAL}"}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v600 WIDE SCAN</title><style>
*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}
body{background:#0a0a0a;color:#00FF88}
.top{padding:8px 10px;display:flex;justify-content:space-between;border-bottom:2px solid #00FF88;background:#000}
.top b{color:#00FF88;font-size:6px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#222}
.card{background:#000;padding:10px}
.card small{color:#888;font-size:7px}
.card b{font-size:18px;display:block;color:#fff}
button{border:none;padding:10px;width:100%;font-weight:900;cursor:pointer;font-size:10px}
button.scan{background:linear-gradient(90deg,#00FF88,#FFD000);color:#000}
button.clear{background:#FF0040;color:#fff}
</style></head><body>
<div class="top"><div><b>VENUS v600 WIDE SCAN 5 BEST ANY COIN NOT MEME ONLY 5/5 ALWAYS COMPOUND $14->$42 TRAIL HH -0.40% to -1.3% BUYS 3+ VOL 150+ ANY COIN 20 BEST FORCE 5/5 AFTER 45s FEEL MOVEMENT</b></div><div style="font-size:8px;color:#00FF88" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND COMPOUND WIDE SCAN 5 BEST ANY COIN - BASE $20 x5 ANY COIN - $14->$42 COMPOUND</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">WIDE SCAN</small></div>
<div class="card"><small>OPEN 5/5 WIDE SCAN 5 BEST MOVING ANY COIN</small><b id="open" class="green">0/5</b><small class="green" id="wr">WIDE SCAN</small></div>
<div class="card"><small>DAILY NET GOAL $100 STOP -$20 COMPOUND POS</small><b id="daily" class="green">+$0.000</b><small id="dailySub" style="color:#666">WIDE SCAN</small></div>
<div class="card"><small>PERF COMPOUND 5 BEST ANY COIN FP HH TRAIL</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">WIDE SCAN</small></div>
</div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #FFD000"><div style="font-size:7px;color:#FFD000">TOP 20 WIDE SCAN 5 BEST MOVING ANY COIN NOT MEME ONLY - $14->42 COMPOUND LOCK $1 at 3.0% TRAIL HH -0.40%/-0.55%/-0.70%/-1.0%/-1.3% LOSS $0.50 TIME 50s/90s/180s/300s - WIDE SCAN: 5 BEST MOVING ANY COIN - ANY SYMBOL EXCEPT STABLE SOL/USDC/USDT LIQ 15k-500k FDV 80k-8M VOL 150+ BUYS 3+ MOVE SCORE = BUYS*VOL*CH5% + FOOTMARK (RATIO + V/L) + WINNER x5 - 20 BEST - COMPOUND - WIDE SCAN 5 BEST 5/5 ALWAYS ANY COIN LOW CPU</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>5 TRADES SIDE COMPOUND WIDE SCAN 5 BEST MOVING - 5/5 ALWAYS ANY COIN</span><span>SIDE</span><span>ENTRY FEE PEAK HH TICK TP/SL NET PEAK TREND</span><span>TP/SL NET AGE</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN WIDE SCAN 5 BEST MOVING ANY COIN NOT MEME ONLY LOW CPU COMPOUND $14->$42 ANY COIN VOL 150+ BUYS 3+ - 20 BEST - $100 GOAL -$20 STOP - FEE 0.2% - 8s WIN 30s LOSS TREND HH -0.40%/-1.3% COMPOUND 5 BEST ANY COIN - 5/5 ALWAYS ANY COIN FORCE AFTER 45s FEEL MOVEMENT TRADE MORE</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN 5 TRADES COMPOUND WIDE SCAN 5 BEST - KEEPS LEARN - FEE 0.2% TP 6% SL 2.8% 8s WIN 30s LOSS TREND HH COMPOUND 5 BEST ANY COIN LOW CPU</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88;margin-bottom:3px">CLOSED LAST 50 - COMPOUND WIDE SCAN 5 BEST MOVING ANY COIN LOCK $1 at 3.0% TRAIL HH -0.40%/-1.3% LOSS $0.50 - $100 GOAL - 8s WIN 30s LOSS TREND HH COMPOUND 5 BEST ANY COIN x5 ANY COIN NOT MEME ONLY</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / FEE PEAK HH TREND</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2)+' POS $'+(j.open_trades&&j.open_trades[0]?Number(j.open_trades[0].pos||20.14).toFixed(2):'20.14');
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' WIDE SCAN 5 BEST ANY COIN';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/5 WIDE SCAN 5 BEST ANY COIN VOL 150+ BUYS 3+ MOVE SCORE FEE $0.040 TP 6% SL 2.8% TRAIL HH 5/5 ALWAYS FORCE AFTER 45s';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L KV '+(j.kv||'1 CMD')+' WIDE SCAN 5 BEST ANY COIN COMPOUND $20.14 ANY COIN 5/5 ALWAYS FORCE 45s GOAL $100';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#00FF88':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $100 STOP -$20 POS $'+(j.open_trades&&j.open_trades[0]?Number(j.open_trades[0].pos||20.14).toFixed(2):'20.14')+' WIDE SCAN 5 BEST ANY COIN 5/5 ANY COIN';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' POS $'+(j.open_trades&&j.open_trades[0]?Number(j.open_trades[0].pos||20.14).toFixed(2):'20.14')+' WIDE SCAN 5 BEST ANY COIN 5/5 ALWAYS FORCE AFTER 45s';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid ${m.wins>0?'#FFD000':'#00FF88'};padding:2px 4px;font-size:7px;color:${m.wins>0?'#FFD000':'#00FF88'}">#${i+1} ${m.symbol} ${Number(m.c1||0).toFixed(2)}% M5 $${Number(m.price||0).toFixed(8)} FP ${Number(m.fp||0).toFixed(1)} V/L ${Number(m.vl||0).toFixed(1)}% R ${Number(m.ratio||0).toFixed(1)} MOVE +${Number(m.move||0).toFixed(1)}%<br><span style="color:#FFD000">WIDE SCAN ${m.buys_m5} BUYS ${m.sells_m5} SELLS VOL $${Number(m.vol_m5||0).toFixed(0)} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)} WIDE SCAN</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">Scanning WIDE SCAN 5 BEST ANY COIN NOT MEME ONLY - ANY COIN VOL 150+ BUYS 3+ MOVE SCORE = BUYS*VOL*CH5% + FOOTMARK (RATIO + V/L) + WINNER x5 - 20 BEST - COMPOUND - WIDE SCAN 5 BEST 5/5 ALWAYS ANY COIN LOW CPU</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||20.14); let fee=pos*0.002; let target=6.0; let netEst=pos*target/100 - fee; let peak=Number(t.peak_pct||0); let hh=Number(t.hh||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:#00FF88">${t.symbol||''}</b> <small style="color:#00FF88">$${pos.toFixed(2)} SHARK HH ${hh} ANY</small></span><span><b style="color:#00FF88;border:1px solid #00FF88;padding:1px 3px;font-size:7px">LONG</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos.toFixed(2)} $${fee.toFixed(3)} PEAK ${peak.toFixed(1)}% HH ${hh} ANY COIN</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,90)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} PEAK ${peak.toFixed(1)}% TREND HH ${hh} WIDE SCAN</small></span><span style="font-size:7px"><span style="color:#00FF88">TP 6% $${(pos*0.06).toFixed(2)}</span><br><span style="color:#FF0040">SL 2.8% $${(pos*0.028).toFixed(2)}</span><br><small style="color:#FFD000">NET $${netEst.toFixed(2)} PEAK ${peak.toFixed(1)}% HH ${hh} WIDE SCAN 5s WINNER</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#00FF88;padding:10px;font-size:10px">No open - WIDE SCAN 5 BEST MOVING ANY COIN NOT MEME ONLY will fill 5/5 ALWAYS AFTER 45s - 1 CMD</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-50).reverse().forEach(c=>{
   let col=c.net>=0.2?'#00FF88':'#FF0040';
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#00FF88"><b style="color:${c.net>=0.2?'#FFD000':'#FF00FF'}">${c.symbol||''}</b><br><small style="color:${c.net>=0.2?'#FFD000':'#FF00FF'}">LONG $${Number(c.pos||20.14).toFixed(2)} HH ${Number(c.hh||0)} ${c.net>=0.2?'WINNER WIDE SCAN':'LOSER WIDE SCAN'}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:${c.net>=0.2?'#FFD000':'#FF00FF'};border:1px solid ${c.net>=0.2?'#FFD000':'#FF00FF'};padding:1px 3px;font-size:7px">LONG</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}% PEAK ${Number(c.peak||0).toFixed(1)}% HH ${Number(c.hh||0)}</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)} WIDE SCAN HH ${Number(c.hh||0)}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,200)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% PEAK ${Number(c.peak||0).toFixed(1)}% HH ${Number(c.hh||0)} WIDE SCAN</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FFD000;padding:10px">Scanning WIDE SCAN 5 BEST MOVING ANY COIN NOT MEME ONLY - 5/5 ALWAYS ANY COIN FORCE AFTER 45s - FEEL MOVEMENT TRADE MORE...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR WIDE SCAN 5 BEST MOVING ANY COIN NOT MEME ONLY - KEEPS LEARN?')) return; await fetch('/api/clear_closed_fake'); await load(); }
setInterval(load,3000);load();
</script></body></html>
"""
@app.route("/")
def home(): return HTML
@app.route("/api/state")
def state():
    try: do_tick()
    except Exception as e: print(f"tick {e}")
    data=rget_single()
    return jsonify({"cap":data.get("FUND_CAP",1000),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",0),"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":data.get("FAST_WHALE",[]),"kv":f"v600 WIDE SCAN 20 BEST VOL 150+ BUYS 3+ 5/5 ALWAYS FORCE 45s GOAL ${DAILY_GOAL}"})
@app.route("/api/cron")
def cron(): return jsonify(do_tick())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget_single()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["LAST_LOSS_PEAK"]={}
    rset_single(data); data["_last_save"]=0; rset_single(data)
    return jsonify({"cleared":True})
