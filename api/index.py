from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)
UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
SINGLE_KEY = "VENUS_V570_DATA"
DAILY_GOAL = 300.0
DAILY_STOP = -60.0
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
            data.setdefault("LAST_LOSS_PEAK",{})
            data.setdefault("LAST_LOSS_TIME",{})
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

def get_meme_whales_25():
    whales=[]
    try:
        all_pairs=[]
        for url in ["https://api.dexscreener.com/token-boosts/latest/v1","https://api.dexscreener.com/token-boosts/top/v1"]:
            try:
                r=requests.get(url, timeout=7).json()
                if isinstance(r,list):
                    for it in r[:80]:
                        if it.get('chainId')=='solana':
                            tk=it.get('tokenAddress')
                            if tk:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=5).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:2])
            except: continue
        for q in ["BONK","WIF","PEPE","PUMP","FLOKI","TRUMP","DOGE","SHIB","A1","CATCRAFT","RARINU","SNDWITCH","CHONK","MINER","VIBE","SK","ECSTASY","PUMPOWEEN","UI","REFLECT","GSI","TON618","FLY","PLAGUE","BULLCRAFT","SOL","RAY","JUP","POPCAT","MEW"]:
            try:
                sr=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=5).json()
                if sr.get('pairs'): all_pairs.extend(sr['pairs'][:8])
            except: pass
        seen=set()
        data=CACHE["data"] or {}
        learn=data.get("LEARN_STATS",{}) if isinstance(data, dict) else {}
        for p in all_pairs:
            try:
                if p.get('chainId')!='solana': continue
                base=p.get('baseToken',{}).get('symbol','').upper()
                if base in ['SOL','USDC','USDT','WETH','WBTC']: continue
                addr=p.get('pairAddress')
                if not addr or addr in seen: continue
                seen.add(addr)
                fdv=float(p.get('fdv',0) or 0); liq=float(p.get('liquidity',{}).get('usd',0) or 0); price=float(p.get('priceUsd',0) or 0)
                if price==0: continue
                if liq < 60000: continue
                if fdv < 80000 or fdv > 4500000: continue
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
                txns=p.get('txns',{}); buys=int(txns.get('m5',{}).get('buys',0) or 0); sells=int(txns.get('m5',{}).get('sells',0) or 0)
                if vol_m5 < 700: continue
                if buys < 18: continue
                if ch_24 < -92: continue
                if not (-1.5 <= ch_m5 <= 7.5): continue
                if buys < sells*0.7: continue
                st=learn.get(base,{'w':0,'l':0})
                score=buys*1100 + vol_m5*1.4
                if 0.3 <= ch_m5 <= 4.0: score*=2.3
                if buys>=sells*1.5: score*=1.6
                # CRACK CODE: WINNER MORE OFTEN x4
                if st.get('w',0) > st.get('l',0):
                    score*=4.0
                    if st.get('w',0)>=2: score*=2.0
                    if st.get('w',0)>=3: score*=1.5
                tier="ULTRA TOP12"
                if 70000 <= liq <= 300000 and 300000 <= fdv <= 2500000 and 1000 <= vol_m5 <= 10000 and buys>=40 and 0.3 <= ch_m5 <= 4.5 and buys>=sells*1.4:
                    tier="TIGHT SHARK CRACK"
                whales.append({"prod":f"{base}-USD","symbol":base[:12],"price":price,"c1":ch_m5,"c24":ch_24,"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys,"sells_m5":sells,"score":score,"tier":tier,"wins":st.get('w',0)})
            except: continue
        whales.sort(key=lambda x: x['score'], reverse=True)
        return whales[:40]
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
    if now - float(data.get("FAST_LAST") or 0) > 2.5:
        w=get_meme_whales_25()
        if w: fast_whale=w; data["FAST_WHALE"]=w; data["FAST_LAST"]=now

    new_open=[]
    for tr in open_t:
        try:
            sym=tr.get('symbol','?'); entry=float(tr.get('entry',0) or 0); last=float(tr.get('last_price',entry) or entry); pos=float(tr.get('pos',15) or 15); cg_id=tr.get('cg_id','')
            peak=float(tr.get('peak_pct',0) or 0); tier=tr.get('tier','ULTRA')
            if entry==0: continue
            cur,src=get_price(cg_id,last)
            if cur==0:
                for fm in fast_whale:
                    if fm.get('cg_id')==cg_id:
                        cur=fm['price']; src="FAST"; break
            if cur==0:
                tr['last_price']=last; new_open.append(tr); continue
            age=now-float(tr.get('ts',now) or now); pct=(cur-entry)/entry*100; fee=pos*0.002; gross=pos*pct/100; net=gross-fee
            if pct > peak: peak=pct; tr['peak_pct']=peak
            close=False; rs=""
            # DYNAMIC TRAIL CRACK: 6% = -0.4%, 10%+ = -0.8%, 20%+ = -1.5% to catch FLY 70%
            trail=-0.4
            if peak>=20: trail=-1.5
            elif peak>=10: trail=-0.8
            if pct<=-12.0 and peak<5.0:
                close=True; rs=f"RUG DETECT {pct:.2f}% <=-12% NET ${net:.3f} PEAK {peak:.1f}% RUG BLACKLIST 90s CRACK {tier}"
                last_loss[sym]=now+90
            elif pct<=-3.5: close=True; rs=f"LOSS CRACK SL {pct:.2f}% <=-3.5% NET ${net:.3f} PEAK {peak:.1f}% CRACK 15s REST {tier}"
            elif peak>=6.0 and age>=10 and pct <= peak + trail: close=True; rs=f"WIN CRACK LOCK $1+ TRAIL {trail}% POCKET {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} EXTRA ${net-0.9:.2f} CRACK 5s WIN IMMEDIATE MORE OFTEN {tier} TRAIL {trail}%"
            elif peak>=6.0 and age>=180: close=True; rs=f"WIN CRACK LOCK $1 TIME 180s {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} CRACK 5s WIN IMMEDIATE MORE OFTEN {tier}"
            elif age>=180 and peak<2.2: close=True; rs=f"TIME 180s CRACK PEAK {peak:.1f}% {pct:.2f}% NET ${net:.3f} CUT FAST CRACK 15s REST {tier}"
            elif age>=400: close=True; rs=f"TIME 400s CRACK {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} MAX CRACK 15s REST {tier}"
            if close:
                closed.append({"symbol":sym,"prod":tr.get('prod',sym),"side":"LONG","entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":rs,"ts":now,"is_meme":True,"pos":pos})
                if len(closed)>600: closed=closed[-600:]
                if net>=0.3: wins+=1
                else: losses+=1
                if "RUG" not in rs:
                    if net>=0.3:
                        last_loss[sym]=now-10
                    else:
                        last_loss[sym]=now
                last_peak[sym]=peak
                st=learn.get(sym,{'w':0,'l':0}); st['w' if net>=0.3 else 'l']=st.get('w' if net>=0.3 else 'l',0)+1; learn[sym]=st
                daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)

    if daily >= DAILY_GOAL or daily <= DAILY_STOP:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak})
        rset_single(data); return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"{'GOAL' if daily>=DAILY_GOAL else 'STOP'} ${daily:.2f} CRACK 5s/15s"}

    cnt=len(new_open); idx=0
    open_syms=set(x['symbol'] for x in new_open)
    open_ids=set(x['cg_id'] for x in new_open)
    while cnt<12 and idx<len(fast_whale):
        try:
            m=fast_whale[idx]; idx+=1; sym=m['symbol']
            if sym in open_syms: continue
            if m['cg_id'] in open_ids: continue
            if sym in last_loss:
                st=learn.get(sym,{'w':0,'l':0})
                cooldown=5 if st.get('w',0)>st.get('l',0) else 15
                if now-float(last_loss.get(sym,0) or 0) < cooldown: continue
            pos=15.0
            reason=f"CRACK TOP12 {m.get('tier','ULTRA')} $15 x12 LOCK $1 at 4% 10s TRAIL DYNAMIC -0.4/-0.8/-1.5% LOSS $0.525 {m['buys_m5']} BUYS {m['sells_m5']} SELLS VOL M5 ${m['vol_m5']:.0f} LIQ ${m['liq']:.0f} FDV ${m['fdv']:.0f} {m['c1']:.1f}% M5 CRACK IMMEDIATE WINNER MORE OFTEN 5s WIN 15s LOSS WINNER BOOST x4 KEEP SCANNING"
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":now,"side":"LONG","reason":reason,"target":6.0,"stop":3.5,"last_price":m['price'],"pos":pos,"c1":m['c1'],"c24":m['c24'],"cg_id":m['cg_id'],"is_meme":True,"fdv":m['fdv'],"peak_pct":0,"tier":m.get('tier','ULTRA')})
            open_syms.add(sym); open_ids.add(m['cg_id']); cnt+=1
        except: continue

    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak})
    rset_single(data)
    tight_cnt=sum(1 for w in fast_whale if 'TIGHT' in w.get('tier',''))
    winner_cnt=sum(1 for w in fast_whale if learn.get(w['symbol'],{}).get('w',0)>learn.get(w['symbol'],{}).get('l',0))
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"v584 CRACK TOP12 {tight_cnt} TIGHT {winner_cnt} WINNERS 5s WIN 15s LOSS WINNER BOOST x4 DYNAMIC TRAIL -0.4/-0.8/-1.5% 70% POCKET 12/12"}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v584 CRACK TOP12 IMMEDIATE WINNER MORE OFTEN</title><style>
*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}
body{background:#0a0a0a;color:#00FF88}
.top{padding:8px 10px;display:flex;justify-content:space-between;border-bottom:2px solid #00FF88;background:#000}
.top b{color:#00FF88;font-size:7px}
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
<div class="top"><div><b>VENUS v584 CRACK TOP12 SHARK IMMEDIATE WINNER MORE OFTEN 5s WIN 15s LOSS WINNER BOOST x4 DYNAMIC TRAIL -0.4/-0.8/-1.5% LOCK $1 at 4% 70% POCKET</b> <span style="color:#888;font-size:6px">CRACK TOP12 WINNER MORE OFTEN</span></div><div style="font-size:8px;color:#00FF88" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND REAL $15 x12 CRACK TOP12 IMMEDIATE WINNER MORE OFTEN 5s WIN 15s LOSS - FEE $0.36 CRACK</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">CRACK TOP12 WINNER MORE OFTEN</small></div>
<div class="card"><small>OPEN 12/12 CRACK TOP12 IMMEDIATE WINNER MORE OFTEN 5s WIN 15s LOSS - 12/12 ALWAYS CRACK</small><b id="open" class="green">0/12</b><small class="green" id="wr">CRACK TOP12 IMMEDIATE WINNER MORE OFTEN</small></div>
<div class="card"><small>DAILY GROSS - FEE = NET - GOAL $300 STOP -$60 LOCK $1/$0.525 CRACK IMMEDIATE WINNER</small><b id="daily" class="green">+$0.00</b><small id="dailySub" style="color:#666">CRACK TOP12 IMMEDIATE WINNER</small></div>
<div class="card"><small>PERFORMANCE - $15 x12 CRACK TOP12 IMMEDIATE WINNER MORE OFTEN LOCK $1 at 4% DYNAMIC TRAIL TP 6% SL 3.5% WINNER BOOST x4</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">CRACK TOP12 IMMEDIATE WINNER MORE OFTEN TP 6% SL 3.5% 12/12</small></div>
</div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #FFD000"><div style="font-size:7px;color:#FFD000">TOP 40 CRACK TOP12 IMMEDIATE WINNER MORE OFTEN - $15 x12 LOCK $1 at 4% 10s DYNAMIC TRAIL -0.4% 6-10% / -0.8% 10-20% / -1.5% 20%+ LOSS $0.525 ADAPT 5s WIN 15s LOSS - TOP12 SHARK LIQ 60k+ FDV 80k-4.5M VOL 700+ BUYS 18+ M5 -1.5 to 7.5% BUYS>=0.7x + TIGHT SHARK 0.3-4.5% BUYS 40+ VOL 1k-10k LIQ 70k+ BUYS>=1.4x + WINNER BOOST x4 + 2W x2 + 3W x1.5 - 40 BEST - FEE $0.36 - CRACK TOP12 IMMEDIATE WINNER MORE OFTEN KEEP SCANNING 12/12 ALWAYS</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>12 TRADES $15 x12 CRACK TOP12 IMMEDIATE WINNER MORE OFTEN - 12/12 ALWAYS CRACK</span><span>SIDE</span><span>ENTRY FEE PEAK</span><span>TICK TP/SL NET PEAK CRACK WINNER</span><span>TP/SL NET CRACK WINNER</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN CRACK TOP12 IMMEDIATE WINNER MORE OFTEN $15 x12 LIQ 60k+ TP 6% SL 3.5% DYNAMIC TRAIL -0.4/-0.8/-1.5% LOCK $1 at 4% - 40 BEST TOP12 SHARK - $300 GOAL -$60 STOP - FEE $0.36 - CRACK TOP12 IMMEDIATE WINNER MORE OFTEN 5s WIN 15s LOSS WINNER BOOST x4 KEEP SCANNING 70% POCKET - 12/12 ALWAYS CRACK</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN 12 TRADES $15 x12 CRACK TOP12 IMMEDIATE WINNER MORE OFTEN - KEEPS LEARN WINNERS - FEE $0.36 CRACK TP 6% SL 3.5% 5s WIN 15s LOSS</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88;margin-bottom:3px">CLOSED LAST 50 - $15 x12 CRACK TOP12 IMMEDIATE WINNER MORE OFTEN LOCK $1 at 4% 10s DYNAMIC TRAIL -0.4/-0.8/-1.5% LOSS $0.525 - $300 GOAL - CRACK TOP12 IMMEDIATE WINNER 5s WIN 15s LOSS WINNER BOOST x4</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / FEE PEAK CRACK WINNER</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON - CRACK TOP12 IMMEDIATE WINNER MORE OFTEN TP 6% SL 3.5% 5s WIN 15s LOSS DYNAMIC TRAIL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2);
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' CRACK TOP12 IMMEDIATE WINNER MORE OFTEN 5s WIN 15s LOSS';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/12 CRACK TOP12 IMMEDIATE WINNER MORE OFTEN $15 x12 LIQ 60k+ WINNER BOOST x4 FEE $0.36 CRACK TP 6% SL 3.5% DYNAMIC TRAIL 12/12 5s WIN 15s LOSS';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L KV '+(j.kv||'1 CMD')+' CRACK TOP12 IMMEDIATE WINNER MORE OFTEN 12/12';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#00FF88':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $300 STOP -$60 CRACK TOP12 IMMEDIATE WINNER 5s WIN 15s LOSS 12/12';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('wlSub').innerText='WR '+wr+'% - CRACK TOP12 IMMEDIATE WINNER MORE OFTEN LIQ 60k+ TP 6% SL 3.5% DYNAMIC TRAIL -0.4/-0.8/-1.5% LOCK $1 at 4% WINNER BOOST x4 TOP12 12/12 GOAL $300';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' CRACK TOP12 IMMEDIATE WINNER MORE OFTEN 12/12 5s WIN 15s LOSS';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid ${m.wins>0?'#FFD000':(m.tier.includes('TIGHT')?'#00FF88':'#FF00FF')};padding:2px 4px;font-size:7px;color:${m.wins>0?'#FFD000':(m.tier.includes('TIGHT')?'#00FF88':'#FF00FF')}">#${i+1} ${m.symbol} ${Number(m.c1).toFixed(1)}% M5 $${Number(m.price).toFixed(8)} ${m.wins>0?`WINNER ${m.wins}W BOOST x4`:''}<br><span style="color:#FFD000">${m.tier} ${m.buys_m5} BUYS ${m.sells_m5} SELLS VOL $${Number(m.vol_m5||0).toFixed(0)} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)} CRACK TOP12</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">Scanning CRACK TOP12 IMMEDIATE WINNER MORE OFTEN - looking for top 12 shark immediate winner</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||15); let fee=pos*0.002; let target=6.0; let netEst=pos*target/100 - fee; let peak=Number(t.peak_pct||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:${t.tier.includes('TIGHT')?'#00FF88':'#FFD000'}">${t.symbol||''}</b> <small style="color:${t.tier.includes('TIGHT')?'#00FF88':'#FFD000'}">$15 ${t.tier||'TOP12'} CRACK WINNER</small></span><span><b style="color:${t.tier.includes('TIGHT')?'#00FF88':'#FFD000'};border:1px solid ${t.tier.includes('TIGHT')?'#00FF88':'#FFD000'};padding:1px 3px;font-size:7px">LONG</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos} $${fee.toFixed(3)} PEAK ${peak.toFixed(1)}% ${t.tier||'TOP12'} CRACK 5s WINNER</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,90)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} PEAK ${peak.toFixed(1)}% DYNAMIC TRAIL CRACK 5s WINNER</small></span><span style="font-size:7px"><span style="color:#00FF88">TP 6% $0.90</span><br><span style="color:#FF0040">SL 3.5% $0.525</span><br><small style="color:#FFD000">NET $${netEst.toFixed(2)} PEAK ${peak.toFixed(1)}% CRACK 5s WINNER</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#00FF88;padding:10px;font-size:10px">No open - CRACK TOP12 IMMEDIATE WINNER MORE OFTEN will fill 12/12 when top 12 shark appears - 1 CMD</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-50).reverse().forEach(c=>{
   let col=c.net>=0.3?'#00FF88':'#FF0040';
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#00FF88"><b style="color:${c.net>=0.3?'#FFD000':'#FF00FF'}">${c.symbol||''}</b><br><small style="color:${c.net>=0.3?'#FFD000':'#FF00FF'}">LONG $${c.pos||15} ${c.net>=0.3?'WINNER CRACK 5s':'AUTO 15s'} REST</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:${c.net>=0.3?'#FFD000':'#FF00FF'};border:1px solid ${c.net>=0.3?'#FFD000':'#FF00FF'};padding:1px 3px;font-size:7px">LONG</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}% PEAK ${Number(c.peak||0).toFixed(1)}%</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)} CRACK ${c.net>=0.3?'WINNER 5s REST':'15s REST'}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,200)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% PEAK ${Number(c.peak||0).toFixed(1)}% CRACK ${c.net>=0.3?'WINNER 5s':'15s'} REST</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FFD000;padding:10px">Scanning CRACK TOP12 IMMEDIATE WINNER MORE OFTEN - finding top 12 shark and immediate winner re-trade 5s...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR CRACK TOP12 IMMEDIATE WINNER MORE OFTEN - KEEPS LEARN WINNERS?')) return; await fetch('/api/clear_closed_fake'); await load(); }
setInterval(load,3500);load();
</script></body></html>
"""
@app.route("/")
def home(): return HTML
@app.route("/api/state")
def state():
    try: do_tick()
    except Exception as e: print(f"tick {e}")
    data=rget_single()
    return jsonify({"cap":data.get("FUND_CAP",1000),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",0),"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":data.get("FAST_WHALE",[]),"kv":f"v584 CRACK TOP12 IMMEDIATE WINNER MORE OFTEN 5s WIN 15s LOSS WINNER BOOST x4 DYNAMIC TRAIL GOAL ${DAILY_GOAL}"})
@app.route("/api/cron")
def cron(): return jsonify(do_tick())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget_single()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["LAST_LOSS_PEAK"]={}
    rset_single(data); data["_last_save"]=0; rset_single(data)
    return jsonify({"cleared":True})
