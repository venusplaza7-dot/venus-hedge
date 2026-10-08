from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)
UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
SINGLE_KEY = "VENUS_V590_DATA"
DAILY_GOAL = 100.0
DAILY_STOP = -25.0
POS_SIZE = 20.0
MAX_OPEN = 5
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
            data.setdefault("LEARN_STATS",{})
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
        if time.time()-last < 4: return
        data["_last_save"]=time.time()
        requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(data)], timeout=5)
    except: pass

def get_meme_whales_25():
    whales=[]
    try:
        all_pairs=[]
        for url in ["https://api.dexscreener.com/token-boosts/latest/v1","https://api.dexscreener.com/token-boosts/top/v1"]:
            try:
                r=requests.get(url, timeout=6).json()
                if isinstance(r,list):
                    for it in r[:80]:
                        if it.get('chainId')=='solana':
                            tk=it.get('tokenAddress')
                            if tk:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=4).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:2])
            except: continue
        for q in ["BONK","WIF","PEPE","PUMP","FLOKI","TRUMP","DOGE","SHIB","A1","CATCRAFT","RARINU","SNDWITCH","CHONK","MINER","VIBE","SK","ECSTASY","PUMPOWEEN","UI","REFLECT","GSI","TON618","FLY","PLAGUE","BULLCRAFT","TMNP","FRANK","SWORDCAT","LMAO"]:
            try:
                sr=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=4).json()
                if sr.get('pairs'): all_pairs.extend(sr['pairs'][:6])
            except: pass
        seen=set()
        data=CACHE["data"] or {}
        learn=data.get("LEARN_STATS",{}) if isinstance(data, dict) else {}
        last_peak=data.get("LAST_LOSS_PEAK",{}) if isinstance(data, dict) else {}
        for p in all_pairs:
            try:
                if p.get('chainId')!='solana': continue
                base=p.get('baseToken',{}).get('symbol','').upper()
                if base in ['SOL','USDC','USDT','WETH','WBTC','JUP','RAY']: continue
                addr=p.get('pairAddress')
                if not addr or addr in seen: continue
                seen.add(addr)
                fdv=float(p.get('fdv',0) or 0); liq=float(p.get('liquidity',{}).get('usd',0) or 0); price=float(p.get('priceUsd',0) or 0)
                if price==0: continue
                # V590 TIGHT SHARK FILTER - WINNING RANGE
                if not (90000 <= liq <= 160000): continue
                if not (400000 <= fdv <= 1400000): continue
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
                txns=p.get('txns',{}); buys=int(txns.get('m5',{}).get('buys',0) or 0); sells=int(txns.get('m5',{}).get('sells',0) or 0)
                if not (2500 <= vol_m5 <= 7000): continue
                if buys < 50: continue
                if ch_24 < -40 or ch_24 > 120: continue
                # GOLDEN: 0.8-2.8% BEFORE PUMP - this is where A1 was winning
                if not (0.8 <= ch_m5 <= 2.8): continue
                if sells>0 and buys < sells*1.9: continue
                # CHURN FILTER - remove CATCRAFT type
                if buys>=70 and sells>=55 and buys/sells < 1.35: continue
                if buys>=150 and sells>=130 and buys/sells < 1.55: continue
                lp=float(last_peak.get(base,10) or 10)
                st=learn.get(base,{'w':0,'l':0})
                if lp<1.0 and st.get('l',0)>st.get('w',0):
                    if buys < sells*2.3: continue
                # SCORING - BOOST WINNERS x6
                score=buys*2000 + vol_m5*2.5
                if 1.0 <= ch_m5 <= 2.2: score*=3.5
                if buys>=sells*2.5: score*=2.5
                if base in ["A1","SWORDCAT","PLAGUE","PUMPOWEEN","PUMP"]: score*=1.8
                if st.get('w',0) > st.get('l',0):
                    score*=6.0
                    if st.get('w',0)>=2: score*=2.5
                    if st.get('w',0)>=3: score*=1.8
                tier="TIGHT SHARK V590"
                whales.append({"prod":f"{base}-USD","symbol":base[:12],"price":price,"c1":ch_m5,"c24":ch_24,"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys,"sells_m5":sells,"score":score,"tier":tier,"wins":st.get('w',0),"last_peak":lp})
            except: continue
        whales.sort(key=lambda x: x['score'], reverse=True)
        return whales[:35]
    except: return []

def get_price(cg_id,last=0):
    try:
        if len(cg_id)>30:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}", timeout=3).json()
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
            sym=tr.get('symbol','?'); entry=float(tr.get('entry',0) or 0); last=float(tr.get('last_price',entry) or entry); pos=float(tr.get('pos',POS_SIZE) or POS_SIZE); cg_id=tr.get('cg_id','')
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
            # V590 EXIT LOGIC - 70% POCKET
            if pct <= -12.0 and peak < 3.0:
                close=True; rs=f"RUG DETECT {pct:.2f}% <=-12% NET ${net:.3f} PEAK {peak:.1f}% BLACKLIST 300s V590 {tier}"
                last_loss[sym]=now+300
            elif pct <= -2.2: # TIGHT SL -2.2% not -3.5% - saves money from FRANK/TMNP losses
                close=True; rs=f"LOSS V590 SL {pct:.2f}% <=-2.2% NET ${net:.3f} PEAK {peak:.1f}% CUT FAST 90s REST {tier}"
            elif peak >= 4.0 and pct >= 4.0:
                # LOCK $1 at 4% - your winning move
                trail = -0.7 if peak < 6 else -0.9
                if peak >= 4.0 and age >= 8 and pct <= peak + trail:
                    close=True; rs=f"WIN V590 LOCK $1+ TRAIL {trail}% POCKET 70% {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} EXTRA ${net-0.8:.2f} V590 8s WINNER {tier}"
            elif peak >= 6.0 and age >= 120:
                close=True; rs=f"WIN V590 TIME 120s LOCK {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} V590 70% POCKET {tier}"
            elif age >= 90 and peak < 1.5: # Cut fast if not moving in 90s
                close=True; rs=f"TIME 90s V590 PEAK {peak:.1f}% {pct:.2f}% NET ${net:.3f} CUT FAST V590 8s WINNER {tier}"
            elif age >= 300:
                close=True; rs=f"TIME 300s V590 MAX {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} V590 {tier}"
            if close:
                closed.append({"symbol":sym,"prod":tr.get('prod',sym),"side":"LONG","entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":rs,"ts":now,"is_meme":True,"pos":pos})
                if len(closed)>600: closed=closed[-600:]
                if net >= 0.35: wins+=1
                else: losses+=1
                if "RUG" not in rs:
                    if net >= 0.35:
                        if peak >= 8.0:
                            last_loss[sym]=now+180
                        else:
                            last_loss[sym]=now+15
                    else:
                        if peak < 1.0:
                            last_loss[sym]=now+300
                        else:
                            last_loss[sym]=now+90
                last_peak[sym]=peak
                st=learn.get(sym,{'w':0,'l':0}); st['w' if net>=0.35 else 'l']=st.get('w' if net>=0.35 else 'l',0)+1; learn[sym]=st
                daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)

    if daily >= DAILY_GOAL or daily <= DAILY_STOP:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak})
        rset_single(data); return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"{'GOAL $100 HIT' if daily>=DAILY_GOAL else 'STOP -$25 HIT'} ${daily:.2f} V590"}

    cnt=len(new_open); idx=0
    open_syms=set(x['symbol'] for x in new_open)
    open_ids=set(x['cg_id'] for x in new_open)
    while cnt < MAX_OPEN and idx < len(fast_whale):
        try:
            m=fast_whale[idx]; idx+=1; sym=m['symbol']
            if sym in open_syms: continue
            if m['cg_id'] in open_ids: continue
            if sym in last_loss:
                st=learn.get(sym,{'w':0,'l':0})
                last_p=float(last_peak.get(sym,10) or 10)
                cooldown=15 if st.get('w',0)>st.get('l',0) else 90
                if last_p>=8: cooldown=180
                if last_p<1.0 and st.get('l',0)>st.get('w',0): cooldown=300
                if now-float(last_loss.get(sym,0) or 0) < cooldown: continue
            pos=POS_SIZE
            reason=f"V590 TIGHT SHARK $20 x5 LOCK $1 at 4% TRAIL -0.7%/-0.9% LOSS $0.44 {m['buys_m5']} BUYS {m['sells_m5']} SELLS VOL M5 ${m['vol_m5']:.0f} LIQ ${m['liq']:.0f} FDV ${m['fdv']:.0f} {m['c1']:.1f}% M5 V590 0.8-2.8% ONLY BUYS>=1.9x VOL 2.5k-7k LIQ 90k-160k FDV 400k-1.4M 8s WIN 90s LOSS 70% POCKET WINNER BOOST x6"
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":now,"side":"LONG","reason":reason,"target":6.0,"stop":2.2,"last_price":m['price'],"pos":pos,"c1":m['c1'],"c24":m['c24'],"cg_id":m['cg_id'],"is_meme":True,"fdv":m['fdv'],"peak_pct":0,"tier":m.get('tier','ULTRA')})
            open_syms.add(sym); open_ids.add(m['cg_id']); cnt+=1
        except: continue

    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak})
    rset_single(data)
    tight_cnt=sum(1 for w in fast_whale if 'TIGHT' in w.get('tier',''))
    winner_cnt=sum(1 for w in fast_whale if learn.get(w['symbol'],{}).get('w',0)>learn.get(w['symbol'],{}).get('l',0))
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"v590 TIGHT SHARK $100/DAY {tight_cnt} TIGHT {winner_cnt} WINNERS 0.8-2.8% M5 BUYS>=1.9x 8s WIN 90s LOSS 70% POCKET x6 BOOST 5/5"}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v590 $100/DAY TIGHT SHARK</title><style>
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
button{border:none;padding:12px;width:100%;font-weight:900;cursor:pointer;font-size:11px}
button.scan{background:linear-gradient(90deg,#00FF88,#FFD000);color:#000}
button.clear{background:#FF0040;color:#fff}
</style></head><body>
<div class="top"><div><b>VENUS v590 $100/DAY TIGHT SHARK 0.8-2.8% M5 ONLY BUYS>=1.9x VOL 2.5k-7k LIQ 90k-160k FDV 400k-1.4M 8s WIN 90s LOSS 70% POCKET WINNER BOOST x6 5/5</b></div><div style="font-size:8px;color:#00FF88" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND REAL $20 x5 TIGHT SHARK V590 - FEE $0.20 V590 $100/DAY</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">V590 $100/DAY TIGHT SHARK</small></div>
<div class="card"><small>OPEN 5/5 V590 TIGHT SHARK 0.8-2.8% ONLY - 5/5 ALWAYS V590</small><b id="open" class="green">0/5</b><small class="green" id="wr">V590 $100/DAY</small></div>
<div class="card"><small>DAILY GROSS - FEE = NET - GOAL $100 STOP -$25 LOCK $1/$0.44 V590 $100/DAY</small><b id="daily" class="green">+$0.00</b><small id="dailySub" style="color:#666">V590 $100/DAY</small></div>
<div class="card"><small>PERFORMANCE - $20 x5 V590 LOCK $1 at 4% TRAIL -0.7%/-0.9% TP 6% SL 2.2% BOOST x6</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">V590 TP 6% SL 2.2% 5/5</small></div>
</div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #FFD000"><div style="font-size:7px;color:#FFD000">TOP 35 V590 $100/DAY TIGHT SHARK - $20 x5 LOCK $1 at 4% TRAIL -0.7%/-0.9% LOSS $0.44 ADAPT 8s WIN 90s LOSS 300s IF PEAK<1% 180s IF PEAK>=8% - V590: 0.8-2.8% M5 ONLY BEFORE PUMP BUYS 50+ BUYS>=1.9x VOL 2.5k-7k LIQ 90k-160k FDV 400k-1.4M CHURN FILTER + WINNER BOOST x6 + PROVEN A1/SWORDCAT x1.8 - 35 BEST - FEE $0.20 - V590 $100/DAY 5/5 ALWAYS</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>5 TRADES $20 x5 V590 - 5/5 ALWAYS V590 $100/DAY</span><span>SIDE</span><span>ENTRY FEE PEAK</span><span>TICK TP/SL NET PEAK V590</span><span>TP/SL NET V590</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN V590 $20 x5 0.8-2.8% ONLY BUYS>=1.9x LIQ 90k-160k FDV 400k-1.4M VOL 2.5k-7k - 35 BEST V590 - $100 GOAL -$25 STOP - FEE $0.20 - V590 8s WIN 90s LOSS 70% POCKET x6 BOOST - 5/5 ALWAYS V590 $100/DAY</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN 5 TRADES $20 x5 V590 - KEEPS LEARN WINNERS - FEE $0.20 V590 TP 6% SL 2.2% 8s WIN 90s LOSS 70% POCKET</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88;margin-bottom:3px">CLOSED LAST 50 - $20 x5 V590 LOCK $1 at 4% TRAIL -0.7%/-0.9% LOSS $0.44 - $100 GOAL - V590 8s WIN 90s LOSS 70% POCKET x6 BOOST</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / FEE PEAK V590</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON - V590 TP 6% SL 2.2% 8s WIN 90s LOSS 70% POCKET</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2);
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' V590 TIGHT SHARK 0.8-2.8% ONLY';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/5 V590 $20 x5 0.8-2.8% ONLY BUYS>=1.9x LIQ 90k-160k FDV 400k-1.4M FEE $0.20 TP 6% SL 2.2% TRAIL -0.7%/-0.9% 5/5 8s WIN 90s LOSS 70% POCKET';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L KV '+(j.kv||'1 CMD')+' V590 $100/DAY 5/5';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#00FF88':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $100 STOP -$25 V590 8s WIN 90s LOSS 70% POCKET 5/5';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('wlSub').innerText='WR '+wr+'% - V590 0.8-2.8% ONLY BUYS>=1.9x LIQ 90k-160k FDV 400k-1.4M TP 6% SL 2.2% TRAIL -0.7%/-0.9% LOCK $1 at 4% BOOST x6 5/5 GOAL $100';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' V590 $100/DAY 5/5';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid ${m.wins>0?'#FFD000':'#00FF88'};padding:2px 4px;font-size:7px;color:${m.wins>0?'#FFD000':'#00FF88'}">#${i+1} ${m.symbol} ${Number(m.c1).toFixed(1)}% M5 $${Number(m.price).toFixed(8)} ${m.wins>0?`WINNER ${m.wins}W BOOST x6`:''} PEAK ${Number(m.last_peak||0).toFixed(1)}%<br><span style="color:#FFD000">TIGHT SHARK V590 ${m.buys_m5} BUYS ${m.sells_m5} SELLS VOL $${Number(m.vol_m5||0).toFixed(0)} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)} V590</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">Scanning V590 TIGHT SHARK 0.8-2.8% ONLY BUYS>=1.9x - $100/day strategy</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||20); let fee=pos*0.002; let target=6.0; let netEst=pos*target/100 - fee; let peak=Number(t.peak_pct||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:#00FF88">${t.symbol||''}</b> <small style="color:#00FF88">$20 TIGHT SHARK V590</small></span><span><b style="color:#00FF88;border:1px solid #00FF88;padding:1px 3px;font-size:7px">LONG</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos} $${fee.toFixed(3)} PEAK ${peak.toFixed(1)}% V590 8s WINNER</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,90)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} PEAK ${peak.toFixed(1)}% TRAIL -0.7%/-0.9% V590</small></span><span style="font-size:7px"><span style="color:#00FF88">TP 6% $${(pos*0.06).toFixed(2)}</span><br><span style="color:#FF0040">SL 2.2% $${(pos*0.022).toFixed(2)}</span><br><small style="color:#FFD000">NET $${netEst.toFixed(2)} PEAK ${peak.toFixed(1)}% V590 8s WINNER</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#00FF88;padding:10px;font-size:10px">No open - V590 TIGHT SHARK will fill 5/5 when 0.8-2.8% M5 shark appears - $100/DAY MODE</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-50).reverse().forEach(c=>{
   let col=c.net>=0.35?'#00FF88':'#FF0040';
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#00FF88"><b style="color:${c.net>=0.35?'#FFD000':'#FF00FF'}">${c.symbol||''}</b><br><small style="color:${c.net>=0.35?'#FFD000':'#FF00FF'}">LONG $${c.pos||20} ${c.net>=0.35?'WINNER V590 8s/180s':'LOSER V590 90s/300s'} REST</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:${c.net>=0.35?'#FFD000':'#FF00FF'};border:1px solid ${c.net>=0.35?'#FFD000':'#FF00FF'};padding:1px 3px;font-size:7px">LONG</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}% PEAK ${Number(c.peak||0).toFixed(1)}%</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)} V590 ${c.net>=0.35?'WINNER':'LOSER'} REST</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,200)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% PEAK ${Number(c.peak||0).toFixed(1)}% V590 ${c.net>=0.35?'WINNER':'LOSER'} REST</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FFD000;padding:10px">Scanning V590 TIGHT SHARK 0.8-2.8% ONLY - $100/day strategy...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR V590 - KEEPS LEARN WINNERS AND LOSERS?')) return; await fetch('/api/clear_closed_fake'); await load(); }
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
    return jsonify({"cap":data.get("FUND_CAP",1000),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",0),"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":data.get("FAST_WHALE",[]),"kv":f"v590 $100/DAY TIGHT SHARK 0.8-2.8% BUYS>=1.9x x6 BOOST GOAL ${DAILY_GOAL}"})
@app.route("/api/cron")
def cron(): return jsonify(do_tick())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget_single()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["LAST_LOSS_PEAK"]={}
    rset_single(data); data["_last_save"]=0; rset_single(data)
    return jsonify({"cleared":True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 3000)))
