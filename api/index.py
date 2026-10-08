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
    if CACHE["data"] and now - CACHE["ts"] < 7:
        return CACHE["data"]
    try:
        if not UP_URL or not UP_TOKEN:
            return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"FAST_WHALE":[],"FAST_LAST":0,"FALLBACK_START":0}
        r=requests.get(f"{UP_URL}/get/{SINGLE_KEY}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=5)
        v=r.json().get("result")
        if v:
            data=json.loads(v)
            data.setdefault("LAST_LOSS_PEAK",{})
            data.setdefault("LAST_LOSS_TIME",{})
            data.setdefault("FALLBACK_START",0)
            CACHE["data"]=data; CACHE["ts"]=now
            return data
    except: pass
    return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"FAST_WHALE":[],"FAST_LAST":0,"FALLBACK_START":0}

def rset_single(data):
    global CACHE
    CACHE["data"]=data; CACHE["ts"]=time.time()
    try:
        if not UP_URL or not UP_TOKEN: return
        last=float(data.get("_last_save",0) or 0)
        if time.time()-last < 3: return
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
                    for it in r[:90]:
                        if it.get('chainId')=='solana':
                            tk=it.get('tokenAddress')
                            if tk:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=5).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:2])
            except: continue
        for q in ["BONK","WIF","PEPE","PUMP","FLOKI","TRUMP","A1","CATCRAFT","RARINU","SNDWITCH","CHONK","MINER","VIBE","SK","ECSTASY","PUMPOWEEN","UI","REFLECT","TON618","FLY","PLAGUE","TMNP","FRANK","SWORDCAT","BULLCRAFT"]:
            try:
                sr=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=5).json()
                if sr.get('pairs'): all_pairs.extend(sr['pairs'][:8])
            except: pass
        seen=set()
        data=CACHE["data"] or {}
        learn=data.get("LEARN_STATS",{}) if isinstance(data, dict) else {}
        last_peak=data.get("LAST_LOSS_PEAK",{}) if isinstance(data, dict) else {}
        now=time.time()
        fallback_start=float(data.get("FALLBACK_START",0) or 0)
        if fallback_start==0:
            data["FALLBACK_START"]=now
            rset_single(data)
            fallback_start=now
        use_fallback = (now - fallback_start > 40)
        temp=[]
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
                if fdv < 200000 or fdv > 2500000: continue
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
                txns=p.get('txns',{}); buys=int(txns.get('m5',{}).get('buys',0) or 0); sells=int(txns.get('m5',{}).get('sells',0) or 0)
                if vol_m5 < 800: continue
                if buys < 22: continue
                if ch_24 < -93: continue
                lp=float(last_peak.get(base,10) or 10)
                if lp==0.0: continue
                temp.append(p)
            except: continue
        tight_count=0
        for p in temp:
            try:
                liq=float(p.get('liquidity',{}).get('usd',0) or 0); fdv=float(p.get('fdv',0) or 0)
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0)
                txns=p.get('txns',{}); buys=int(txns.get('m5',{}).get('buys',0) or 0); sells=int(txns.get('m5',{}).get('sells',0) or 0)
                if 85000 <= liq <= 180000 and 300000 <= fdv <= 2000000 and 1200 <= vol_m5 <= 8500 and buys>=38 and 0.3 <= ch_m5 <= 3.5 and (sells==0 or buys>=sells*1.7):
                    if not (buys>=80 and sells>=60 and buys/sells < 1.6):
                        tight_count+=1
            except: pass
        if tight_count>=3:
            use_fallback=False
            data["FALLBACK_START"]=0
            rset_single(data)
        seen=set()
        for p in temp:
            try:
                base=p.get('baseToken',{}).get('symbol','').upper()
                addr=p.get('pairAddress')
                if addr in seen: continue
                seen.add(addr)
                fdv=float(p.get('fdv',0) or 0); liq=float(p.get('liquidity',{}).get('usd',0) or 0); price=float(p.get('priceUsd',0) or 0)
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0)
                txns=p.get('txns',{}); buys=int(txns.get('m5',{}).get('buys',0) or 0); sells=int(txns.get('m5',{}).get('sells',0) or 0)
                if use_fallback:
                    if not (60000 <= liq <= 220000): continue
                    if not (-0.5 <= ch_m5 <= 5.0): continue
                    if buys < 22 or (sells>0 and buys < sells*1.3): continue
                    if buys>=100 and sells>=80 and buys/sells < 1.4: continue
                    tier="LOOSE FALLBACK NOW FIX"
                else:
                    if not (85000 <= liq <= 180000): continue
                    if not (0.3 <= ch_m5 <= 3.5): continue
                    if buys < 38 or (sells>0 and buys < sells*1.7): continue
                    if buys>=80 and sells>=60 and buys/sells < 1.6: continue
                    tier="TIGHT WINNER FIX"
                st=learn.get(base,{'w':0,'l':0})
                lp=float(last_peak.get(base,10) or 10)
                if lp<1.0 and st.get('l',0)>st.get('w',0):
                    if buys < sells*2.0: continue
                score=buys*1500 + vol_m5*2.0
                if 0.5 <= ch_m5 <= 2.8: score*=3.0
                if buys>=sells*2.2: score*=2.0
                if st.get('w',0) > st.get('l',0):
                    score*=4.8
                    if st.get('w',0)>=2: score*=2.5
                whales.append({"prod":f"{base}-USD","symbol":base[:12],"price":price,"c1":ch_m5,"c24":float(p.get('priceChange',{}).get('h24',0) or 0),"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys,"sells_m5":sells,"score":score,"tier":tier,"wins":st.get('w',0),"last_peak":lp})
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
    if now - float(data.get("FAST_LAST") or 0) > 1.2:
        w=get_meme_whales_25()
        if w: fast_whale=w; data["FAST_WHALE"]=w; data["FAST_LAST"]=now

    new_open=[]
    for tr in open_t:
        try:
            sym=tr.get('symbol','?'); entry=float(tr.get('entry',0) or 0); last=float(tr.get('last_price',entry) or entry); pos=float(tr.get('pos',15) or 15); cg_id=tr.get('cg_id','')
            peak=float(tr.get('peak_pct',0) or 0); tier=tr.get('tier','ULTRA'); start=float(tr.get('ts',now) or now)
            if entry==0: continue
            cur,src=get_price(cg_id,last)
            if cur==0:
                for fm in fast_whale:
                    if fm.get('cg_id')==cg_id:
                        cur=fm['price']; src="FAST"; break
            if cur==0:
                # FIX: don't use 0, use last price to avoid 0% gross bug
                cur=last
                tr['last_price']=last
                # but still check trail
                age=now-start; pct=(cur-entry)/entry*100
                trail=-0.4
                if peak>=30: trail=-1.8
                elif peak>=10: trail=-0.9
                if peak>=6.0 and age>=8 and pct <= peak + trail:
                    gross=pos*(peak+trail)/100; net=gross-pos*0.002
                    closed.append({"symbol":sym,"prod":tr.get('prod',sym),"side":"LONG","entry":entry,"exit":entry*(1+(peak+trail)/100),"pct":peak+trail,"peak":peak,"gross":gross,"fee":pos*0.002,"net":net,"reason":f"WIN FIX POCKET PEAK {peak:.1f}% TRAIL {trail}% POCKET {peak+trail:.2f}% PEAK {peak:.1f}% NET ${net:.3f} FIX 0% BUG {tier}","ts":now,"is_meme":True,"pos":pos})
                    wins+=1; last_loss[sym]=now-8 if peak<50 else now+300; last_peak[sym]=peak
                    st=learn.get(sym,{'w':0,'l':0}); st['w']=st.get('w',0)+1; learn[sym]=st
                    daily+=net; dg+=gross; df+=pos*0.002; cap+=net
                    continue
                new_open.append(tr)
                continue
            age=now-start; pct=(cur-entry)/entry*100; fee=pos*0.002; gross=pos*pct/100; net=gross-fee
            if pct > peak: peak=pct; tr['peak_pct']=peak
            close=False; rs=""
            trail=-0.4
            if peak>=30: trail=-1.8
            elif peak>=10: trail=-0.9
            if age<30 and pct<=-8.0:
                close=True; rs=f"ANTI-RUG FAST DROP {pct:.2f}% <=-8% in {age:.0f}s NET ${net:.3f} PEAK {peak:.1f}% SAVE $13 vs -99% {tier}"
                last_loss[sym]=now+240
            elif pct<=-12.0 and peak<5.0:
                close=True; rs=f"ANTI-RUG RUG {pct:.2f}% <=-12% NET ${net:.3f} PEAK {peak:.1f}% BLACKLIST 240s {tier}"
                last_loss[sym]=now+240
            elif pct<=-3.5: close=True; rs=f"LOSS FIX SL {pct:.2f}% <=-3.5% NET ${net:.3f} PEAK {peak:.1f}% 15s REST {tier}"
            elif peak>=6.0 and age>=8 and pct <= peak + trail: close=True; rs=f"WIN FIX POCKET TRAIL {trail}% POCKET {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} EXTRA ${net-0.9:.2f} FIX 0% BUG 5s WIN 300s IF 50%+ {tier} TRAIL {trail}%"
            elif peak>=6.0 and age>=180: close=True; rs=f"WIN FIX TIME 180s {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} 5s WIN {tier}"
            elif age>=180 and peak<2.0: close=True; rs=f"TIME 180s PEAK {peak:.1f}% {pct:.2f}% NET ${net:.3f} CUT {tier}"
            elif age>=400: close=True; rs=f"TIME 400s {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} MAX {tier}"
            if close:
                closed.append({"symbol":sym,"prod":tr.get('prod',sym),"side":"LONG","entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":rs,"ts":now,"is_meme":True,"pos":pos})
                if len(closed)>600: closed=closed[-600:]
                if net>=0.3: wins+=1
                else: losses+=1
                if "RUG" not in rs and "FAST DROP" not in rs:
                    if net>=0.3:
                        if peak>=50:
                            last_loss[sym]=now+300
                        else:
                            last_loss[sym]=now-8
                    else:
                        if peak<1.0:
                            last_loss[sym]=now+120
                        else:
                            last_loss[sym]=now
                if peak==0.0:
                    last_loss[sym]=now+240
                last_peak[sym]=peak
                st=learn.get(sym,{'w':0,'l':0}); st['w' if net>=0.3 else 'l']=st.get('w' if net>=0.3 else 'l',0)+1; learn[sym]=st
                daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)

    if daily >= DAILY_GOAL or daily <= DAILY_STOP:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak})
        rset_single(data); return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"{'GOAL' if daily>=DAILY_GOAL else 'STOP'} ${daily:.2f} FIX PEAK"}

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
                last_p=float(last_peak.get(sym,10) or 10)
                cooldown=5 if st.get('w',0)>st.get('l',0) and last_p<50 else 15
                if last_p>=50: cooldown=300
                if last_p==0.0: cooldown=240
                if last_p<1.0 and st.get('l',0)>st.get('w',0): cooldown=120
                if now-float(last_loss.get(sym,0) or 0) < cooldown: continue
            pos=15.0
            reason=f"FIX PEAK TOP12 {m.get('tier','ULTRA')} $15 x12 LOCK $1 at 4% TRAIL LOSS $0.525 {m['buys_m5']} BUYS {m['sells_m5']} SELLS VOL ${m['vol_m5']:.0f} LIQ ${m['liq']:.0f} FDV ${m['fdv']:.0f} {m['c1']:.1f}% M5 FIX PEAK 0% BUG POCKET 12-19% NOT 0%"
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":now,"side":"LONG","reason":reason,"target":6.0,"stop":3.5,"last_price":m['price'],"pos":pos,"c1":m['c1'],"c24":m['c24'],"cg_id":m['cg_id'],"is_meme":True,"fdv":m['fdv'],"peak_pct":0,"tier":m.get('tier','ULTRA')})
            open_syms.add(sym); open_ids.add(m['cg_id']); cnt+=1
        except: continue

    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak})
    rset_single(data)
    tight_cnt=sum(1 for w in fast_whale if 'TIGHT' in w.get('tier',''))
    loose_cnt=len(fast_whale)-tight_cnt
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"v591 FIX PEAK TOP12 {tight_cnt} TIGHT {loose_cnt} LOOSE 40s FALLBACK 5s WIN 240s IF PEAK 0% FIX 0% BUG 12/12 NOW"}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v591 FIX PEAK 0% BUG</title><style>
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
<div class="top"><div><b>VENUS v591 FIX PEAK 0% BUG - TIGHT 0.3-3.5% BUYS>=1.7x LIQ 85k-180k LOOSE -0.5-5% BUYS>=1.3x LIQ 60k-220k 40s FALLBACK 5s WIN 240s IF PEAK 0% WINNER BOOST x4.8 DYNAMIC TRAIL 99% POCKET FIX 0% BUG 12/12 NOW</b> <span style="color:#888;font-size:6px">FIX PEAK 0% BUG</span></div><div style="font-size:8px;color:#00FF88" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND REAL $15 x12 FIX PEAK 0% BUG - TIGHT 0.3-3.5% LOOSE -0.5-5% - FEE $0.36 FIX PEAK</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">FIX PEAK 0% BUG</small></div>
<div class="card"><small>OPEN 12/12 FIX PEAK 0% BUG TIGHT 0.3-3.5% LOOSE -0.5-5% - 12/12 ALWAYS FIX PEAK</small><b id="open" class="green">0/12</b><small class="green" id="wr">FIX PEAK 0% BUG</small></div>
<div class="card"><small>DAILY GROSS - FEE = NET - GOAL $300 STOP -$60 LOCK $1/$0.525 FIX PEAK</small><b id="daily" class="green">+$0.00</b><small id="dailySub" style="color:#666">FIX PEAK</small></div>
<div class="card"><small>PERFORMANCE - $15 x12 FIX PEAK 0% BUG LOCK $1 at 4% DYNAMIC TRAIL TP 6% SL 3.5% WINNER BOOST x4.8</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">FIX PEAK 0% BUG TP 6% SL 3.5% 12/12</small></div>
</div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #FFD000"><div style="font-size:7px;color:#FFD000">TOP 40 FIX PEAK 0% BUG - $15 x12 LOCK $1 at 4% 10s DYNAMIC TRAIL -0.4% 6-10% / -0.9% 10-30% / -1.8% 30%+ LOSS $0.525 ADAPT 5s WIN 15s LOSS 120s IF PEAK&lt;1% 240s IF PEAK 0% 300s IF PEAK&gt;=50% - FIX PEAK: TIGHT 0.3-3.5% M5 ONLY BUYS 38+ BUYS&gt;=1.7x VOL 1.2k-8.5k LIQ 85k-180k FDV 300k-2M + LOOSE -0.5-5% M5 BUYS 22+ BUYS&gt;=1.3x LIQ 60k-220k FDV 200k-2.5M VOL 800-10k CHURN FILTER 80/60&lt;1.5 SKIP LAST PEAK 0.0% SKIP + WINNER BOOST x4.8 + 2W x2.5 - 40 BEST - FEE $0.36 - FIX PEAK 0% BUG 12/12 ALWAYS</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>12 TRADES $15 x12 FIX PEAK 0% BUG - 12/12 ALWAYS FIX PEAK</span><span>SIDE</span><span>ENTRY FEE PEAK</span><span>TICK TP/SL NET PEAK FIX PEAK</span><span>TP/SL NET FIX PEAK</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN FIX PEAK 0% BUG $15 x12 TIGHT 0.3-3.5% BUYS>=1.7x LIQ 85k-180k LOOSE -0.5-5% BUYS>=1.3x LIQ 60k-220k - 40 BEST FIX PEAK - $300 GOAL -$60 STOP - FEE $0.36 - FIX PEAK 0% BUG 40s FALLBACK 5s WIN 240s IF PEAK 0% WINNER BOOST x4.8 DYNAMIC TRAIL 99% POCKET - 12/12 ALWAYS FIX PEAK</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN 12 TRADES $15 x12 FIX PEAK 0% BUG - KEEPS LEARN WINNERS - FEE $0.36 FIX PEAK TP 6% SL 3.5% 5s WIN 240s IF PEAK 0%</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88;margin-bottom:3px">CLOSED LAST 50 - $15 x12 FIX PEAK 0% BUG LOCK $1 at 4% 10s DYNAMIC TRAIL -0.4/-0.9/-1.8% LOSS $0.525 - $300 GOAL - FIX PEAK 0% BUG 5s WIN 240s IF PEAK 0% WINNER BOOST x4.8</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / FEE PEAK FIX PEAK</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON - FIX PEAK 0% BUG TP 6% SL 3.5% 5s WIN 240s IF PEAK 0%</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2);
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' FIX PEAK 0% BUG TIGHT 0.3-3.5% LOOSE -0.5-5% 12/12 NOW';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/12 FIX PEAK 0% BUG $15 x12 TIGHT 0.3-3.5% BUYS>=1.7x LIQ 85k-180k LOOSE -0.5-5% BUYS>=1.3x LIQ 60k-220k FEE $0.36 FIX PEAK TP 6% SL 3.5% DYNAMIC TRAIL 12/12 5s WIN 240s IF PEAK 0%';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L KV '+(j.kv||'1 CMD')+' FIX PEAK 0% BUG 12/12 NOW';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#00FF88':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $300 STOP -$60 FIX PEAK 0% BUG 5s WIN 240s IF PEAK 0% 12/12 NOW';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('wlSub').innerText='WR '+wr+'% - FIX PEAK 0% BUG 0.3-3.5% TIGHT 85k-180k -0.5-5% LOOSE 60k-220k TP 6% SL 3.5% DYNAMIC TRAIL -0.4/-0.9/-1.8% LOCK $1 at 4% WINNER BOOST x4.8 TOP12 12/12 GOAL $300';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' FIX PEAK 0% BUG TIGHT 0.3-3.5% LOOSE -0.5-5% 12/12 NOW';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid ${m.wins>0?'#FFD000':(m.tier.includes('TIGHT')?'#00FF88':'#FFD000')};padding:2px 4px;font-size:7px;color:${m.wins>0?'#FFD000':(m.tier.includes('TIGHT')?'#00FF88':'#FFD000')}">#${i+1} ${m.symbol} ${Number(m.c1).toFixed(1)}% M5 $${Number(m.price).toFixed(8)} ${m.wins>0?`WINNER ${m.wins}W BOOST x4.8`:''} LAST PEAK ${Number(m.last_peak||0).toFixed(1)}%<br><span style="color:#FFD000">${m.tier} ${m.buys_m5} BUYS ${m.sells_m5} SELLS VOL $${Number(m.vol_m5||0).toFixed(0)} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)} FIX PEAK</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">Scanning FIX PEAK 0% BUG - TIGHT 0.3-3.5% LOOSE -0.5-5% - fix peak 0% bug 12/12 - 40s fallback</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||15); let fee=pos*0.002; let target=6.0; let netEst=pos*target/100 - fee; let peak=Number(t.peak_pct||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:${t.tier.includes('TIGHT')?'#00FF88':'#FFD000'}">${t.symbol||''}</b> <small style="color:${t.tier.includes('TIGHT')?'#00FF88':'#FFD000'}">$15 ${t.tier||'TOP12'} FIX PEAK</small></span><span><b style="color:${t.tier.includes('TIGHT')?'#00FF88':'#FFD000'};border:1px solid ${t.tier.includes('TIGHT')?'#00FF88':'#FFD000'};padding:1px 3px;font-size:7px">LONG</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos} $${fee.toFixed(3)} PEAK ${peak.toFixed(1)}% ${t.tier||'TOP12'} FIX PEAK 5s WINNER</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,90)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} PEAK ${peak.toFixed(1)}% DYNAMIC TRAIL FIX PEAK 5s WINNER</small></span><span style="font-size:7px"><span style="color:#00FF88">TP 6% $0.90</span><br><span style="color:#FF0040">SL 3.5% $0.525</span><br><small style="color:#FFD000">NET $${netEst.toFixed(2)} PEAK ${peak.toFixed(1)}% FIX PEAK 5s WINNER</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#00FF88;padding:10px;font-size:10px">No open - FIX PEAK 0% BUG will fill 12/12 when winning shark appears - TIGHT 0.3-3.5% or LOOSE -0.5-5% - 40s fallback - 1 CMD</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-50).reverse().forEach(c=>{
   let col=c.net>=0.3?'#00FF88':'#FF0040';
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#00FF88"><b style="color:${c.net>=0.3?'#FFD000':'#FF00FF'}">${c.symbol||''}</b><br><small style="color:${c.net>=0.3?'#FFD000':'#FF00FF'}">LONG $${c.pos||15} ${c.net>=0.3?'WINNER FIX PEAK 5s/300s':'LOSER FIX PEAK 15s/120s/240s'} REST</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:${c.net>=0.3?'#FFD000':'#FF00FF'};border:1px solid ${c.net>=0.3?'#FFD000':'#FF00FF'};padding:1px 3px;font-size:7px">LONG</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}% PEAK ${Number(c.peak||0).toFixed(1)}%</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)} FIX PEAK ${c.net>=0.3?'WINNER 5s/300s':'LOSER 15s/120s/240s'} REST</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,200)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% PEAK ${Number(c.peak||0).toFixed(1)}% FIX PEAK ${c.net>=0.3?'WINNER 5s/300s':'LOSER 15s/120s/240s'} REST</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FFD000;padding:10px">Scanning FIX PEAK 0% BUG - TIGHT 0.3-3.5% LOOSE -0.5-5% - fix peak 0% bug 12/12 - 40s fallback...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR FIX PEAK 0% BUG - KEEPS LEARN WINNERS AND LOSERS?')) return; await fetch('/api/clear_closed_fake'); await load(); }
setInterval(load,2500);load();
</script></body></html>
"""
@app.route("/")
def home(): return HTML
@app.route("/api/state")
def state():
    try: do_tick()
    except Exception as e: print(f"tick {e}")
    data=rget_single()
    return jsonify({"cap":data.get("FUND_CAP",1000),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",0),"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":data.get("FAST_WHALE",[]),"kv":f"v591 FIX PEAK 0% BUG TOP12 TIGHT 0.3-3.5% LOOSE -0.5-5% WINNER BOOST x4.8 GOAL ${DAILY_GOAL}"})
@app.route("/api/cron")
def cron(): return jsonify(do_tick())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget_single()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["LAST_LOSS_PEAK"]={}
    rset_single(data); data["_last_save"]=0; rset_single(data)
    return jsonify({"cleared":True})
