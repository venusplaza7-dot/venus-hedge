from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__) # TOP-LEVEL - KEEPS BUILD GREEN

UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
SINGLE_KEY = "VENUS_V602_BEST_DAY"
DAILY_GOAL = 100.0
DAILY_STOP = -20.0
CACHE = {"data": None, "ts": 0}

def rget_single():
    global CACHE
    now=time.time()
    if CACHE["data"] and now - CACHE["ts"] < 10:
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
        if time.time()-last < 5: return
        data["_last_save"]=time.time()
        requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(data)], timeout=5)
    except: pass

def get_best_movers_daytime():
    whales=[]; all_pairs=[]
    try:
        for q in ["SOL","BONK","WIF","POPCAT","MEW","BOME","WEN","JUP","RAY","TRUMP","PEPE","MISTAKE","SWORDCAT","FRANK","SWORDOWL","ECSTASY"]:
            try:
                r=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=6).json()
                if r.get('pairs'):
                    for p in r['pairs'][:5]:
                        if p.get('chainId')=='solana': all_pairs.append(p)
            except: pass
        for url in ["https://api.dexscreener.com/token-boosts/top/v1","https://api.dexscreener.com/token-boosts/latest/v1"]:
            try:
                r=requests.get(url, timeout=7).json()
                if isinstance(r,list):
                    for it in r[:100]:
                        if it.get('chainId')=='solana':
                            tk=it.get('tokenAddress')
                            if tk:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=5).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:1])
            except: pass
    except: pass
    seen=set(); data=CACHE["data"] or {}; learn=data.get("LEARN_STATS",{}) if isinstance(data, dict) else {}; last_peak=data.get("LAST_LOSS_PEAK",{}) if isinstance(data, dict) else {}
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
            if not (50000 <= liq <= 350000): continue
            if not (200000 <= fdv <= 6000000): continue
            vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_h1=float(p.get('priceChange',{}).get('h1',0) or 0); ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
            txns=p.get('txns',{}); buys=int(txns.get('m5',{}).get('buys',0) or 0); sells=int(txns.get('m5',{}).get('sells',0) or 0); buys_h1=int(txns.get('h1',{}).get('buys',0) or 0)
            if vol_m5 < 1000: continue
            if buys < 25: continue
            if ch_m5 < 0.8 or ch_m5 > 25: continue
            if ch_24 < -80: continue
            if buys_h1 < 40: continue
            ratio = buys / max(1,sells)
            if ratio < 1.25: continue
            v_l = vol_m5 / max(1,liq) * 100
            if not (0.8 <= v_l <= 20): continue
            lp=float(last_peak.get(base,10) or 10)
            if lp==0.0: continue
            score = ch_m5 * buys * v_l * 0.5 + vol_m5*0.1
            if ch_h1>0: score*=1.5
            if 1.5 <= ch_m5 <= 8: score*=2.0
            st=learn.get(base,{'w':0,'l':0})
            if st.get('w',0)>st.get('l',0): score*=5.0
            if buys>=80 and sells>=60 and buys/sells < 1.2: continue
            whales.append({"prod":f"{base}-USD","symbol":base[:12],"price":price,"c1":ch_m5,"ch1":ch_h1,"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys,"sells_m5":sells,"buys_h1":buys_h1,"score":score,"tier":"BEST DAY TIME","wins":st.get('w',0),"ratio":ratio,"vl":v_l})
        except: continue
    whales.sort(key=lambda x: x['score'], reverse=True)
    return whales[:20]

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
    if now - float(data.get("FAST_LAST") or 0) > 7:
        w=get_best_movers_daytime()
        if w: fast_whale=w; data["FAST_WHALE"]=w; data["FAST_LAST"]=now
    base_pos=20.0
    if cap>=1020: base_pos=24.0
    if cap>=1060: base_pos=32.0
    if cap>=1120: base_pos=42.0
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
                if pct > peak+0.15: hh+=1
                peak=pct; tr['peak_pct']=peak; tr['hh']=hh
            close=False
            trail=-0.5
            if hh>=6: trail=-1.3
            elif hh>=4: trail=-1.0
            elif hh>=2: trail=-0.7
            if age>=300: close=True
            elif age>=180 and peak<1.0: close=True
            elif age>=90 and peak<0.4: close=True
            elif peak>=3.0 and pct <= peak + trail: close=True
            elif pct<=-2.8: close=True
            if close:
                closed.append({"symbol":sym,"prod":tr.get('prod',sym),"side":"LONG","entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":f"BEST DAY HH {hh} {pct:.1f}% PEAK {peak:.1f}%","ts":now,"is_meme":False,"pos":pos,"hh":hh})
                if len(closed)>500: closed=closed[-500:]
                if net>=0.25: wins+=1
                else: losses+=1
                last_loss[sym]=now+8 if net>=0.25 else now+40
                last_peak[sym]=peak
                st=learn.get(sym,{'w':0,'l':0}); st['w' if net>=0.25 else 'l']=st.get('w' if net>=0.25 else 'l',0)+1; learn[sym]=st
                daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)
    if daily >= DAILY_GOAL or daily <= DAILY_STOP:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak})
        rset_single(data); return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"{'GOAL' if daily>=DAILY_GOAL else 'STOP'} ${daily:.2f} BEST DAY"}
    cnt=len(new_open); idx=0
    open_syms=set(x['symbol'] for x in new_open); open_ids=set(x['cg_id'] for x in new_open)
    should_force = (now - float(data.get("FAST_LAST",now) or now) > 60) and len(fast_whale)>=2
    while cnt<5 and idx<len(fast_whale):
        try:
            m=fast_whale[idx]; idx+=1; sym=m['symbol']
            if sym in open_syms and not should_force: continue
            if m['cg_id'] in open_ids and not should_force: continue
            if sym in last_loss and not should_force:
                if now-float(last_loss.get(sym,0) or 0) < 35: continue
            pos=base_pos
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":now,"side":"LONG","reason":f"BEST DAY {m['tier']} {m['c1']:.1f}% M5 H1 {m['ch1']:.1f}%","target":6.0,"stop":2.8,"last_price":m['price'],"pos":pos,"c1":m['c1'],"cg_id":m['cg_id'],"is_meme":False,"fdv":m['fdv'],"peak_pct":0,"hh":0,"tier":m.get('tier','BEST')})
            open_syms.add(sym); open_ids.add(m['cg_id']); cnt+=1
        except: continue
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak})
    rset_single(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"v602 BEST DAY TIME 5 BEST ANY COIN VOL 1000+ BUYS 25+ M5 0.8-25% H1 TREND 20 BEST"}

HTML_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v602 BEST DAY TIME</title><style>
*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}
body{background:#0a0a0a;color:#00FF88}
.top{padding:8px 10px;display:flex;justify-content:space-between;border-bottom:2px solid #00FF88;background:#000}
.top b{color:#00FF88;font-size:6px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#222}
.card{background:#000;padding:10px}
.card small{color:#888;font-size:7px}
.card b{font-size:18px;display:block;color:#fff}
.card b.green{color:#00FF88}
.card b.red{color:#FF0040}
button{border:none;padding:10px;width:100%;font-weight:900;cursor:pointer;font-size:10px}
button.scan{background:linear-gradient(90deg,#00FF88,#FFD000);color:#000}
button.clear{background:#FF0040;color:#fff}
</style></head><body>
<div class="top"><div><b>VENUS v602 BEST DAY TIME 5 BEST ANY COIN NOT MEME ONLY 5/5 ALWAYS COMPOUND $20->$42 TRAIL HH -0.5% to -1.3% BUYS 25+ VOL 1000+ M5 0.8-25% H1 TREND R>=1.25 V/L 0.8-20% 20 BEST FORCE 5/5 AFTER 60s FEEL MOVEMENT TRADE BEST</b></div><div style="font-size:8px;color:#00FF88" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND COMPOUND BEST DAY TIME 5 BEST ANY COIN - BASE $20 x5 ANY COIN - $20->$42 COMPOUND - $100 GOAL -$20 STOP - FEE 0.2%</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">BEST DAY TIME</small></div>
<div class="card"><small>OPEN 5/5 BEST DAY TIME 5 BEST MOVING ANY COIN</small><b id="open" class="green">0/5</b><small class="green" id="wr">BEST DAY TIME</small></div>
<div class="card"><small>DAILY NET GOAL $100 STOP -$20 COMPOUND POS</small><b id="daily" class="green">+$0.000</b><small id="dailySub" style="color:#666">BEST DAY TIME</small></div>
<div class="card"><small>PERF COMPOUND 5 BEST ANY COIN FP HH TRAIL</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">BEST DAY TIME</small></div>
</div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #FFD000"><div style="font-size:7px;color:#FFD000">TOP 20 BEST DAY TIME 5 BEST MOVING ANY COIN NOT MEME ONLY - $20->$42 COMPOUND LOCK $1 at 3.0% TRAIL HH -0.5%/-0.7%/-1.0%/-1.3% LOSS $0.50 TIME 50s/90s/180s/300s - BEST DAY TIME: 5 BEST MOVING ANY COIN - ANY SYMBOL EXCEPT STABLE SOL/USDC/USDT LIQ 50k-350k FDV 200k-6M VOL 1000+ BUYS 25+ M5 0.8-25% H1 TREND POSITIVE BUYS H1 40+ R>=1.25 V/L 0.8-20% + WINNER x5 + SHARK BOOST x2 IF 1.5-8% M5 - 20 BEST - COMPOUND - BEST DAY TIME 5/5 ALWAYS ANY COIN LOW CPU</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>5 TRADES SIDE COMPOUND BEST DAY TIME 5 BEST MOVING - 5/5 ALWAYS ANY COIN</span><span>SIDE</span><span>ENTRY FEE PEAK HH TICK TP/SL NET PEAK TREND</span><span>TP/SL NET AGE</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN BEST DAY TIME 5 BEST MOVING ANY COIN NOT MEME ONLY LOW CPU COMPOUND $20->$42 ANY COIN VOL 1000+ BUYS 25+ M5 0.8-25% H1 TREND - 20 BEST - $100 GOAL -$20 STOP - FEE 0.2% - 8s WIN 35s LOSS TREND HH -0.5%/-1.3% COMPOUND 5 BEST ANY COIN - 5/5 ALWAYS ANY COIN FORCE AFTER 60s FEEL MOVEMENT TRADE BEST</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN 5 TRADES COMPOUND BEST DAY TIME 5 BEST - KEEPS LEARN - FEE 0.2% TP 6% SL 2.8% 8s WIN 35s LOSS TREND HH COMPOUND 5 BEST ANY COIN LOW CPU</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88;margin-bottom:3px">CLOSED LAST 50 - COMPOUND BEST DAY TIME 5 BEST MOVING ANY COIN LOCK $1 at 3.0% TRAIL HH -0.5%/-1.3% LOSS $0.50 - $100 GOAL - 8s WIN 35s LOSS TREND HH COMPOUND 5 BEST ANY COIN x5 ANY COIN NOT MEME ONLY</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / FEE PEAK HH TREND</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2)+' POS $'+(j.open_trades&&j.open_trades[0]?Number(j.open_trades[0].pos||20).toFixed(2):'20');
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' BEST DAY TIME 5 BEST ANY COIN';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/5 BEST DAY TIME 5 BEST ANY COIN VOL 1000+ BUYS 25+ M5 0.8-25% H1 TREND FEE $0.040 TP 6% SL 2.8% TRAIL HH 5/5 ALWAYS FORCE AFTER 60s';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L KV '+(j.kv||'1 CMD')+' BEST DAY TIME 5 BEST ANY COIN COMPOUND $20 ANY COIN 5/5 ALWAYS FORCE 60s GOAL $100';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#00FF88':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $100 STOP -$20 POS $'+(j.open_trades&&j.open_trades[0]?Number(j.open_trades[0].pos||20).toFixed(2):'20')+' BEST DAY TIME 5 BEST ANY COIN 5/5 ANY COIN';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' POS $'+(j.open_trades&&j.open_trades[0]?Number(j.open_trades[0].pos||20).toFixed(2):'20')+' BEST DAY TIME 5 BEST ANY COIN 5/5 ALWAYS FORCE AFTER 60s';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid ${m.wins>0?'#FFD000':'#00FF88'};padding:2px 4px;font-size:7px;color:${m.wins>0?'#FFD000':'#00FF88'}">#${i+1} ${m.symbol} ${Number(m.c1||0).toFixed(2)}% M5 H1 ${Number(m.ch1||0).toFixed(2)}% $${Number(m.price||0).toFixed(8)} R ${Number(m.ratio||0).toFixed(1)} V/L ${Number(m.vl||0).toFixed(1)}% VOL $${Number(m.vol_m5||0).toFixed(0)}<br><span style="color:#FFD000">BEST DAY ${m.buys_m5} BUYS ${m.sells_m5} SELLS BUYS H1 ${m.buys_h1||0} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)} ${m.tier}</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">Scanning BEST DAY TIME 5 BEST ANY COIN NOT MEME ONLY - ANY COIN VOL 1000+ BUYS 25+ M5 0.8-25% H1 TREND POSITIVE BUYS H1 40+ R>=1.25 V/L 0.8-20% + WINNER x5 - 20 BEST - COMPOUND - BEST DAY TIME 5/5 ALWAYS ANY COIN LOW CPU - DAY TIME BEST MOVERS</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||20); let fee=pos*0.002; let target=6.0; let netEst=pos*target/100 - fee; let peak=Number(t.peak_pct||0); let hh=Number(t.hh||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:#00FF88">${t.symbol||''}</b> <small style="color:#00FF88">$${pos.toFixed(2)} SHARK HH ${hh} BEST DAY</small></span><span><b style="color:#00FF88;border:1px solid #00FF88;padding:1px 3px;font-size:7px">LONG</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos.toFixed(2)} $${fee.toFixed(3)} PEAK ${peak.toFixed(1)}% HH ${hh} BEST DAY</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,90)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} PEAK ${peak.toFixed(1)}% TREND HH ${hh} BEST DAY</small></span><span style="font-size:7px"><span style="color:#00FF88">TP 6% $${(pos*0.06).toFixed(2)}</span><br><span style="color:#FF0040">SL 2.8% $${(pos*0.028).toFixed(2)}</span><br><small style="color:#FFD000">NET $${netEst.toFixed(2)} PEAK ${peak.toFixed(1)}% HH ${hh} BEST DAY 5s WINNER</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#00FF88;padding:10px;font-size:10px">No open - BEST DAY TIME 5 BEST MOVING ANY COIN NOT MEME ONLY will fill 5/5 ALWAYS AFTER 60s - 1 CMD</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-50).reverse().forEach(c=>{
   let col=c.net>=0.25?'#00FF88':'#FF0040';
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#00FF88"><b style="color:${c.net>=0.25?'#FFD000':'#FF00FF'}">${c.symbol||''}</b><br><small style="color:${c.net>=0.25?'#FFD000':'#FF00FF'}">LONG $${Number(c.pos||20).toFixed(2)} HH ${Number(c.hh||0)} ${c.net>=0.25?'WINNER BEST DAY':'LOSER BEST DAY'}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:${c.net>=0.25?'#FFD000':'#FF00FF'};border:1px solid ${c.net>=0.25?'#FFD000':'#FF00FF'};padding:1px 3px;font-size:7px">LONG</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}% PEAK ${Number(c.peak||0).toFixed(1)}% HH ${Number(c.hh||0)}</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)} BEST DAY HH ${Number(c.hh||0)}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,200)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% PEAK ${Number(c.peak||0).toFixed(1)}% HH ${Number(c.hh||0)} BEST DAY</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FFD000;padding:10px">Scanning BEST DAY TIME 5 BEST MOVING ANY COIN NOT MEME ONLY - 5/5 ALWAYS ANY COIN FORCE AFTER 60s - FEEL MOVEMENT TRADE BEST - DAY TIME BEST MOVERS...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR BEST DAY TIME 5 BEST MOVING ANY COIN NOT MEME ONLY - KEEPS LEARN?')) return; await fetch('/api/clear_closed_fake'); await load(); }
setInterval(load,3000);load();
</script></body></html>
"""

@app.route("/")
def home():
    return HTML_PAGE

@app.route("/api/state")
def state():
    try: do_tick()
    except Exception as e: print(f"tick {e}")
    data=rget_single()
    return jsonify({"cap":data.get("FUND_CAP",1000),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",0),"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":data.get("FAST_WHALE",[]),"kv":f"v602 BEST DAY TIME 5 BEST ANY COIN VOL 1000+ BUYS 25+ M5 0.8-25% H1 TREND 20 BEST FORCE 5/5 AFTER 60s GOAL ${DAILY_GOAL}"})
@app.route("/api/cron")
def cron(): return jsonify(do_tick())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget_single()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["LAST_LOSS_PEAK"]={}
    rset_single(data); data["_last_save"]=0; rset_single(data)
    return jsonify({"cleared":True})
