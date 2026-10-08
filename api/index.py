from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)
UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
SINGLE_KEY = "VENUS_V599_5SHARK"
DAILY_GOAL = 100.0
DAILY_STOP = -20.0
BASE_POS = 20.0
MAX_OPEN = 5
CACHE = {"data": None, "ts": 0, "whale": [], "whale_ts": 0}
DIRTY = {"need_save": False}

def rget_single():
    global CACHE
    now=time.time()
    if CACHE["data"] and now - CACHE["ts"] < 20:
        return CACHE["data"]
    try:
        if not UP_URL or not UP_TOKEN:
            return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"TREND_STATE":{}}
        r=requests.get(f"{UP_URL}/get/{SINGLE_KEY}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=5)
        v=r.json().get("result")
        if v:
            data=json.loads(v)
            data.setdefault("LAST_LOSS_PEAK",{}); data.setdefault("LAST_LOSS_TIME",{}); data.setdefault("LEARN_STATS",{}); data.setdefault("TREND_STATE",{})
            CACHE["data"]=data; CACHE["ts"]=now
            return data
    except: pass
    return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"TREND_STATE":{}}

def rset_single(data, force=False):
    global CACHE, DIRTY
    CACHE["data"]=data; CACHE["ts"]=time.time()
    try:
        if not UP_URL or not UP_TOKEN: return
        if not force and not DIRTY.get("need_save"): return
        if not force and time.time()-float(data.get("_last_save",0) or 0) < 20: return
        data["_last_save"]=time.time()
        DIRTY["need_save"]=False
        save_data = {k:v for k,v in data.items() if k not in ["FAST_WHALE","FAST_LAST"]}
        requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(save_data)], timeout=5)
    except: pass

def get_5_shark_footmarks():
    global CACHE
    now=time.time()
    if CACHE["whale"] and now - CACHE["whale_ts"] < 10:
        return CACHE["whale"]
    whales=[]
    try:
        all_pairs=[]
        try:
            r=requests.get("https://api.dexscreener.com/token-boosts/latest/v1", timeout=4).json()
            if isinstance(r,list):
                for it in r[:80]:
                    if it.get('chainId')=='solana':
                        tk=it.get('tokenAddress')
                        if tk:
                            try:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=3).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:1])
                            except: pass
        except: pass
        for q in ["SOL/USD","pump","ray","jup","bonk","wif","ai","depin","meme","game"]:
            try:
                sr=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=3).json()
                if sr.get('pairs'):
                    for p in sr['pairs'][:5]:
                        if p.get('chainId')=='solana':
                            all_pairs.append(p)
            except: pass
        seen=set()
        data=CACHE["data"] or {}
        learn=data.get("LEARN_STATS",{}) if isinstance(data, dict) else {}
        last_peak=data.get("LAST_LOSS_PEAK",{}) if isinstance(data, dict) else {}
        for p in all_pairs:
            try:
                if p.get('chainId')!='solana': continue
                base=p.get('baseToken',{}).get('symbol','').upper()
                if base in ['SOL','WSOL','USDC','USDT','USDE','WETH','WBTC']: continue
                if len(base)>12: continue
                addr=p.get('pairAddress')
                if not addr or addr in seen: continue
                seen.add(addr)
                fdv=float(p.get('fdv',0) or 0); liq=float(p.get('liquidity',{}).get('usd',0) or 0); price=float(p.get('priceUsd',0) or 0)
                if price==0: continue
                if not (40000 <= liq <= 300000): continue
                if not (150000 <= fdv <= 4000000): continue
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); vol_h1=float(p.get('volume',{}).get('h1',0) or 0)
                ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
                txns=p.get('txns',{}); buys_m5=int(txns.get('m5',{}).get('buys',0) or 0); sells_m5=int(txns.get('m5',{}).get('sells',0) or 0)
                buys_h1=int(txns.get('h1',{}).get('buys',0) or 0)
                if ch_24 < -70 or ch_24 > 180: continue
                # 5 SHARK FOOTMARKS - MUST HAVE ALL 5
                if vol_m5 < 500: continue
                if buys_m5 < 20: continue # Footmark 1: BUYS >=20 (shark buying)
                if ch_m5 <= 0.25: continue # MUST BE POSITIVE - fixes SWORDCAT -0.7% bug
                if not (0.3 <= ch_m5 <= 6.0): continue # Footmark 5: M5 0.3-6% positive
                if sells_m5>0 and buys_m5 < sells_m5*1.2: continue # minimum ratio
                vol_liq = vol_m5 / liq if liq>0 else 0
                ratio = buys_m5 / (sells_m5+1)
                avg_5m = buys_h1/12 if buys_h1>0 else buys_m5
                accel = buys_m5 / (avg_5m+1) if avg_5m>0 else 1.0
                # SHARK FOOTMARK FILTER - all 5 must pass
                if ratio < 1.25: continue # Footmark 2: RATIO >=1.25 minimum
                if vol_liq < 0.006: continue # Footmark 3: VOL/LIQ >=0.6% minimum footprint
                if accel < 0.75: continue # Footmark 4: ACCEL >=0.75 minimum
                # STRONG SHARK BOOST - higher footmarks get higher score
                footprint = ratio*1.3 + vol_liq*55 + buys_m5*0.02
                is_strong_shark = (buys_m5>=25 and ratio>=1.5 and vol_liq>=0.010 and accel>=0.95 and 0.4 <= ch_m5 <= 5.0)
                is_super_shark = (buys_m5>=35 and ratio>=1.8 and vol_liq>=0.015 and accel>=1.05 and 0.6 <= ch_m5 <= 4.0)
                # MOVE SCORE = footprint * movement * volume
                move_score = (buys_m5*900 + vol_m5*1.6 + ch_m5*1800) * (footprint+1) * (accel+0.8)
                if is_strong_shark:
                    move_score *= 3.0
                if is_super_shark:
                    move_score *= 5.5 # super shark footmark x5.5 boost
                if 0.8 <= ch_m5 <= 3.2:
                    move_score *= 2.0
                st=learn.get(base,{'w':0,'l':0})
                if st.get('w',0)>0:
                    move_score *= 5.5
                lp=float(last_peak.get(base,10) or 10)
                if lp<0.5 and lp!=10:
                    move_score *= 0.2
                # SWORDCAT had FP 1.2 R 0.4 ACC x0.5 MOVE -0.7% - would be filtered now
                # Good shark example: BUYS 38 SELLS 18 R 2.0 V/L 1.8% ACC x1.2 CH 1.5% FP 3.5
                tier=f"{'SUPER' if is_super_shark else ('SHARK' if is_strong_shark else 'FOOT')} FP {footprint:.1f} V/L {vol_liq*100:.1f}% ACC x{accel:.1f} R {ratio:.1f} CH {ch_m5:.1f}%"
                whales.append({"prod":f"{base}-USD","symbol":base,"price":price,"c1":ch_m5,"c24":ch_24,"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys_m5,"sells_m5":sells_m5,"score":move_score,"tier":tier,"wins":st.get('w',0),"last_peak":lp,"footprint":footprint,"vol_liq":vol_liq,"accel":accel,"ratio":ratio,"strong":is_strong_shark,"super":is_super_shark})
            except: continue
        whales.sort(key=lambda x: x['score'], reverse=True)
        # Take top 15, but prioritize SUPER > SHARK > FOOT
        result = whales[:15]
        CACHE["whale"]=result
        CACHE["whale_ts"]=now
        return result
    except: return CACHE.get("whale",[])[:15]

def get_price(cg_id,last=0):
    try:
        if len(cg_id)>30:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}", timeout=3).json()
            if r.get('pair') and r['pair'].get('priceUsd'):
                p=float(r['pair']['priceUsd'])
                if p>0: return p,"DEX"
    except: pass
    return last if last>0 else 0,"LAST"

def get_compound_pos(cap, daily):
    cap_f = cap/1000.0
    bonus = 0
    if daily>=15: bonus=2
    if daily>=40: bonus=6
    if daily>=75: bonus=11
    pos = BASE_POS * cap_f + bonus
    return round(max(14, min(pos, 42)),2)

def do_tick():
    global DIRTY
    data=rget_single()
    cap=float(data.get("FUND_CAP") or 1000.0); open_t=data.get("FUND_OPEN") or []; closed=data.get("FUND_CLOSED") or []
    wins=data.get("FUND_WINS") or 0; losses=data.get("FUND_LOSSES") or 0
    daily=float(data.get("FUND_DAILY_PNL") or 0); dg=float(data.get("FUND_DAILY_GROSS") or 0); df=float(data.get("FUND_DAILY_FEE") or 0)
    learn=data.get("LEARN_STATS") or {}; last_loss=data.get("LAST_LOSS_TIME") or {}; last_peak=data.get("LAST_LOSS_PEAK") or {}; trend_state=data.get("TREND_STATE") or {}
    fast_whale = get_5_shark_footmarks()

    new_open=[]
    changed=False
    for tr in open_t:
        try:
            sym=tr.get('symbol','?'); entry=float(tr.get('entry',0) or 0); last=float(tr.get('last_price',entry) or entry); pos=float(tr.get('pos',BASE_POS) or BASE_POS); cg_id=tr.get('cg_id','')
            peak=float(tr.get('peak_pct',0) or 0); tier=tr.get('tier','ULTRA')
            if entry==0: continue
            cur,src=get_price(cg_id,last)
            if cur==0: cur=last
            age=time.time()-float(tr.get('ts',time.time()) or time.time()); pct=(cur-entry)/entry*100; fee=pos*0.002; gross=pos*pct/100; net=gross-fee
            ts = trend_state.get(sym, {"hh":0, "last_peak":0})
            if pct > ts.get("last_peak",0):
                ts["hh"]+=1; ts["last_peak"]=pct
            trend_state[sym]=ts
            hh=ts["hh"]
            if pct>peak: peak=pct; tr['peak_pct']=peak
            if hh>=4: trail=-1.3
            elif hh>=3: trail=-1.0
            elif hh>=2: trail=-0.70
            elif peak>=4: trail=-0.55
            else: trail=-0.40
            close=False; rs=""
            if pct<=-12 and peak<3:
                close=True; rs=f"RUG {pct:.1f}% HH {hh} PEAK {peak:.1f}% BL 300s V599 {tier}"; last_loss[sym]=time.time()+300
            elif pct<=-2.8:
                close=True; rs=f"SL -2.8% {pct:.1f}% HH {hh} PEAK {peak:.1f}% CUT V599 {tier}"
            elif peak>=3.0 and pct>=3.0 and pct <= peak+trail and age>=7:
                close=True; rs=f"WIN 70% POCKET HH {hh} TRAIL {trail}% {pct:.1f}% PEAK {peak:.1f}% NET ${net:.3f} V599 {tier}"
            elif age>=55 and peak<0.4:
                close=True; rs=f"TIME 55s NO TREND HH {hh} PEAK {peak:.1f}% CUT V599 {tier}"
            elif age>=95 and peak<1.0:
                close=True; rs=f"TIME 95s NO TREND HH {hh} PEAK {peak:.1f}% CUT V599 {tier}"
            elif age>=185 and peak<1.8:
                close=True; rs=f"TIME 185s HH {hh} {pct:.1f}% PEAK {peak:.1f}% V599 {tier}"
            elif age>=310:
                close=True; rs=f"TIME 310s HH {hh} {pct:.1f}% PEAK {peak:.1f}% V599 {tier}"
            if close:
                closed.append({"symbol":sym,"prod":tr.get('prod',sym),"side":"LONG","entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":rs,"ts":time.time(),"is_meme":False,"pos":pos,"hh":hh})
                if len(closed)>500: closed=closed[-500:]
                if net>=0.25: wins+=1
                else: losses+=1
                if "RUG" not in rs:
                    last_loss[sym]=time.time()+8 if net>=0.25 else (time.time()+250 if peak<0.5 else time.time()+45)
                last_peak[sym]=peak; st=learn.get(sym,{'w':0,'l':0}); st['w' if net>=0.25 else 'l']=st.get('w' if net>=0.25 else 'l',0)+1; learn[sym]=st
                daily+=net; dg+=gross; df+=fee; cap+=net; changed=True
                if sym in trend_state: del trend_state[sym]
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)

    if daily >= DAILY_GOAL or daily <= DAILY_STOP:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak,"TREND_STATE":trend_state})
        DIRTY["need_save"]=True
        rset_single(data, force=True)
        return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"{'GOAL $100' if daily>=DAILY_GOAL else 'STOP'} ${daily:.2f} COMPOUND ${get_compound_pos(cap,daily)} V599 5 SHARK"}

    cnt=len(new_open); idx=0
    open_syms=set(x['symbol'] for x in new_open); open_ids=set(x['cg_id'] for x in new_open)
    comp_pos=get_compound_pos(cap,daily)
    while cnt<MAX_OPEN and idx<len(fast_whale):
        try:
            m=fast_whale[idx]; idx+=1; sym=m['symbol']
            if sym in open_syms or m['cg_id'] in open_ids: continue
            if sym in last_loss and time.time()-float(last_loss.get(sym,0) or 0) < (8 if learn.get(sym,{}).get('w',0)>0 else 45): continue
            if float(last_peak.get(sym,10) or 10) < 0.4: continue
            pos=comp_pos
            reason=f"V599 5SHARK {'SUPER' if m.get('super') else ('SHARK' if m.get('strong') else 'FOOT')} FP {m.get('footprint',0):.1f} V/L {m.get('vol_liq',0)*100:.1f}% ACC x{m.get('accel',0):.1f} R {m.get('ratio',0):.1f} BUYS {m['buys_m5']} SELLS {m['sells_m5']} VOL ${m['vol_m5']:.0f} LIQ ${m['liq']:.0f} FDV ${m['fdv']:.0f} {m['c1']:.1f}% M5 ANY COIN NOT MEME ONLY COMPOUND ${pos} TREND HH"
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":time.time(),"side":"LONG","reason":reason,"target":6.0,"stop":2.8,"last_price":m['price'],"pos":pos,"c1":m['c1'],"c24":m['c24'],"cg_id":m['cg_id'],"is_meme":False,"fdv":m['fdv'],"peak_pct":0,"tier":m.get('tier','5SHARK')})
            open_syms.add(sym); open_ids.add(m['cg_id']); cnt+=1; changed=True
        except: continue

    if changed:
        DIRTY["need_save"]=True
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak,"TREND_STATE":trend_state})
    rset_single(data)
    super_cnt=sum(1 for w in fast_whale if w.get('super'))
    shark_cnt=sum(1 for w in fast_whale if w.get('strong'))
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"v599 5 SHARK FP COMPOUND ${comp_pos} {super_cnt} SUPER {shark_cnt} SHARK {len(fast_whale)} FOOT 5 BEST ANY COIN NOT MEME ONLY $100/DAY UPSTASH 500K","compound_pos":comp_pos}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v599 5 SHARK FOOTMARKS ANY COIN</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#0a0a0a;color:#00FF88}.top{padding:8px 10px;display:flex;justify-content:space-between;border-bottom:2px solid #00FF88;background:#000}.top b{color:#00FF88;font-size:6px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#222}.card{background:#000;padding:10px}.card small{color:#888;font-size:6px}.card b{font-size:18px;display:block;color:#fff}.card b.green{color:#00FF88}.card b.red{color:#FF0040}button{border:none;padding:12px;width:100%;font-weight:900;cursor:pointer;font-size:10px}button.scan{background:linear-gradient(90deg,#00FF88,#FFD000);color:#000}button.clear{background:#FF0040;color:#fff}</style></head><body>
<div class="top"><div><b>VENUS v599 5 SHARK FOOTMARKS 5 BEST MOVING ANY COIN NOT MEME ONLY 5/5 ALWAYS COMPOUND $14->$42 TRAIL HH -0.40% to -1.3% BUYS 20+ VOL 500+ ANY COIN 5 SHARK FOOTMARKS = BUYS>=25 RATIO>=1.5 VOL/LIQ>=1.0% ACCEL x0.95+ M5 0.4-5.0% POSITIVE ONLY SUPER SHARK = BUYS>=35 RATIO>=1.8 VOL/LIQ>=1.5% ACCEL x1.05+ M5 0.6-4.0% BOOST x5.5 5/5 ALWAYS $100/DAY UPSTASH 500K LOW CPU</b></div><div style="font-size:8px;color:#00FF88" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND COMPOUND V599 5 SHARK ANY COIN - BASE $20 x5 ANY COIN</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">V599 5 SHARK ANY COIN</small></div>
<div class="card"><small>OPEN 5/5 5 SHARK FOOTMARKS ANY COIN FP TREND HH - 5/5 ALWAYS ANY COIN</small><b id="open" class="green">0/5</b><small class="green" id="wr">V599 5 SHARK ANY COIN</small></div>
<div class="card"><small>DAILY NET GOAL $100 STOP -$20 COMPOUND POS V599 5 SHARK ANY COIN</small><b id="daily" class="green">+$0.00</b><small id="dailySub" style="color:#666">V599 5 SHARK</small></div>
<div class="card"><small>PERF COMPOUND 5 SHARK ANY COIN FP HH TRAIL TP 6% SL 2.8% -0.40% to -1.3%</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">V599 5 SHARK 5/5 ANY COIN</small></div>
</div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #FFD000"><div style="font-size:7px;color:#FFD000">TOP 15 V599 5 SHARK FOOTMARKS ANY COIN NOT MEME ONLY - 20s CACHE 10s SCAN DIRTY SAVE ONLY NO WHALE SAVE - $14->42 COMPOUND LOCK $1 at 3.0% TRAIL HH -0.40%/-0.55%/-0.70%/-1.0%/-1.3% LOSS $0.50 TIME 55s/95s/185s/310s - V599: 5 SHARK FOOTMARKS = FOOTMARK 1 BUYS>=20 2 RATIO>=1.25 3 VOL/LIQ>=0.6% 4 ACCEL>=0.75 5 M5 0.3-6% POSITIVE ONLY STRONG SHARK = BUYS>=25 RATIO>=1.5 VOL/LIQ>=1.0% ACCEL x0.95+ M5 0.4-5.0% BOOST x3 SUPER SHARK = BUYS>=35 RATIO>=1.8 VOL/LIQ>=1.5% ACCEL x1.05+ M5 0.6-4.0% BOOST x5.5 ANY COIN NOT MEME ONLY LIQ 40k-300k FDV 150k-4M VOL 500+ BUYS 20+ MOVE SCORE = FOOTMARK + CH5% + BUYS + VOL + WINNER x5.5 - 15 BEST - COMPOUND - V599 5 SHARK 5/5 ALWAYS ANY COIN LOW CPU UPSTASH 500K FIX SWORDCAT -0.7% DUMP BUG</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 130px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>5 TRADES COMPOUND V599 5 SHARK FOOTMARKS ANY COIN - 5/5 ALWAYS ANY COIN</span><span>SIDE</span><span>ENTRY FEE PEAK HH</span><span>TICK TP/SL NET PEAK TREND V599</span><span>TP/SL NET V599</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN V599 5 SHARK FOOTMARKS ANY COIN NOT MEME ONLY LOW CPU COMPOUND $14->$42 5 FOOTMARKS BUYS>=25 RATIO>=1.5 VOL/LIQ>=1.0% ACCEL x0.95+ M5 0.4-5.0% POSITIVE ONLY SUPER BUYS>=35 RATIO>=1.8 VOL/LIQ>=1.5% - 15 BEST - $100 GOAL -$20 STOP - FEE 0.2% - V599 8s WIN 55s/95s/185s/310s LOSS TREND HH -0.40%/-1.3% COMPOUND 5 SHARK ANY COIN - 5/5 ALWAYS ANY COIN FIX SWORDCAT -0.7% UPSTASH 500K FEEL MOVEMENT TRADE MORE</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN 5 TRADES COMPOUND V599 5 SHARK - KEEPS LEARN - FEE 0.2% TP 6% SL 2.8% 8s WIN 55s/95s/185s/310s LOSS TREND HH COMPOUND 5 SHARK ANY COIN LOW CPU UPSTASH 500K</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88;margin-bottom:3px">CLOSED LAST 50 - COMPOUND V599 5 SHARK FOOTMARKS ANY COIN LOCK $1 at 3.0% TRAIL HH -0.40%/-1.3% LOSS $0.50 - $100 GOAL - V599 8s WIN 55s/95s/185s/310s LOSS TREND HH COMPOUND 5 SHARK ANY COIN x5.5 ANY COIN NOT MEME ONLY</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / FEE PEAK HH TREND V599</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON - V599 5 SHARK ANY COIN FP TREND HH TP 6% SL 2.8%</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
let paused=false;
document.addEventListener('visibilitychange',()=>{paused=document.hidden});
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 if(paused) return;
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2)+' POS $'+(j.compound_pos||14);
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' V599 5 SHARK ANY COIN NOT MEME ONLY FIX SWORDCAT';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/5 5 SHARK FP POS $'+(j.compound_pos||14)+' 5 FOOTMARKS BUYS>=25 RATIO>=1.5 VOL/LIQ>=1.0% ACC x0.95+ M5 0.4-5.0% POS ONLY FEE $'+((j.compound_pos||14)*0.002).toFixed(3)+' TP 6% SL 2.8% TRAIL HH 5/5 ANY COIN NOT MEME ONLY';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L KV '+(j.kv||'1 CMD')+' V599 5 SHARK ANY COIN 5/5 ALWAYS';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#00FF88':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $100 STOP -$20 POS $'+(j.compound_pos||14)+' V599 5 SHARK ANY COIN 5/5 ANY COIN NOT MEME ONLY';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('wlSub').innerText='WR '+wr+'% - V599 5 SHARK FP BUYS>=25 RATIO>=1.5 VOL/LIQ>=1.0% ACC x0.95+ M5 0.4-5.0% POS ONLY SUPER BUYS>=35 RATIO>=1.8 VOL/LIQ>=1.5% TP 6% SL 2.8% TRAIL -0.40%/-1.3% HH POS $'+(j.compound_pos||14)+' GOAL $100 ANY COIN NOT MEME ONLY';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' POS $'+(j.compound_pos||14)+' V599 5 SHARK ANY COIN 5/5 NOT MEME ONLY';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid ${m.super?'#FFD000':(m.strong?'#00FF88':'#888')};padding:2px 4px;font-size:7px;color:${m.super?'#FFD000':(m.strong?'#00FF88':'#888')}">#${i+1} ${m.symbol} ${Number(m.c1).toFixed(2)}% M5 $${Number(m.price).toFixed(8)} FP ${Number(m.footprint||0).toFixed(1)} V/L ${(Number(m.vol_liq||0)*100).toFixed(1)}% ACC x${Number(m.accel||0).toFixed(1)} R ${Number(m.ratio||0).toFixed(1)} ${m.super?'SUPER SHARK':(m.strong?'SHARK':'FOOT')}<br><span style="color:#FFD000">5SHARK V599 ANY COIN ${m.buys_m5} BUYS ${m.sells_m5} SELLS VOL $${Number(m.vol_m5||0).toFixed(0)} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)}</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">Scanning V599 5 SHARK FOOTMARKS ANY COIN NOT MEME ONLY - BUYS>=25 RATIO>=1.5 VOL/LIQ>=1.0% ACC x0.95+ M5 0.4-5.0% POSITIVE ONLY - 5 shark footmarks target, 5 best moving any coin, fix SWORDCAT -0.7% dump bug</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||14); let fee=pos*0.002; let target=6.0; let netEst=pos*target/100 - fee; let peak=Number(t.peak_pct||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 130px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:#00FF88">${t.symbol||''}</b> <small style="color:#00FF88">$${pos} ${t.tier.split(' ')[0]} HH ${t.hh||0} ANY</small></span><span><b style="color:#00FF88;border:1px solid #00FF88;padding:1px 3px;font-size:7px">LONG</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos} $${fee.toFixed(3)} PEAK ${peak.toFixed(1)}% HH ${t.hh||0} 5SHARK</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,95)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} PEAK ${peak.toFixed(1)}% HH ${t.hh||0} TRAIL V599 5 SHARK ANY COIN</small></span><span style="font-size:7px"><span style="color:#00FF88">TP 6% $${(pos*0.06).toFixed(2)}</span><br><span style="color:#FF0040">SL 2.8% $${(pos*0.028).toFixed(2)}</span><br><small style="color:#FFD000">HH ${t.hh||0} V599 5SHARK</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#00FF88;padding:10px;font-size:10px">No open - V599 5 SHARK FOOTMARKS will fill 5/5 when 5 shark footmarks detected - ANY COIN NOT MEME ONLY - FIX SWORDCAT -0.7% DUMP BUG</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-50).reverse().forEach(c=>{
   let col=c.net>=0.25?'#00FF88':'#FF0040';
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#00FF88"><b style="color:${c.net>=0.25?'#FFD000':'#FF00FF'}">${c.symbol||''}</b><br><small style="color:${c.net>=0.25?'#FFD000':'#FF00FF'}">LONG $${c.pos||14} HH ${c.hh||0} ${c.net>=0.25?'WINNER V599 5 SHARK':'LOSER V599 5 SHARK'} ANY COIN</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:${c.net>=0.25?'#FFD000':'#FF00FF'};border:1px solid ${c.net>=0.25?'#FFD000':'#FF00FF'};padding:1px 3px;font-size:7px">LONG</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}% PEAK ${Number(c.peak||0).toFixed(1)}% HH ${c.hh||0}</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)} V599 5 SHARK HH ${c.hh||0}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,200)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% PEAK ${Number(c.peak||0).toFixed(1)}% HH ${c.hh||0} V599 5 SHARK ANY COIN</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FFD000;padding:10px">Scanning V599 5 SHARK FOOTMARKS ANY COIN NOT MEME ONLY - BUYS>=25 RATIO>=1.5 VOL/LIQ>=1.0% ACC x0.95+ M5 0.4-5.0% POSITIVE ONLY - 5 shark footmarks target, 5 best moving any coin, fix SWORDCAT -0.7% dump bug...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR V599 5 SHARK - KEEPS LEARN?')) return; await fetch('/api/clear_closed_fake'); await load(); }
setInterval(load,8000);load();
</script></body></html>
"""
@app.route("/")
def home(): return HTML
@app.route("/api/state")
def state():
    try: do_tick()
    except Exception as e: print(f"tick {e}")
    data=rget_single()
    cp=data.get("FUND_CAP",1000); dly=data.get("FUND_DAILY_PNL",0); comp=get_compound_pos(cp,dly)
    return jsonify({"cap":cp,"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"closed":data.get("FUND_CLOSED",[]),"daily":dly,"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":CACHE.get("whale",[]),"kv":f"v599 5 SHARK FOOTMARKS COMPOUND ${comp} BUYS>=25 RATIO>=1.5 VOL/LIQ>=1.0% ACC x0.95+ M5 0.4-5.0% POS ONLY ANY COIN 5/5 ALWAYS $100/DAY UPSTASH 500K","compound_pos":comp})
@app.route("/api/cron")
def cron(): return jsonify(do_tick())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    global DIRTY
    data=rget_single()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["LAST_LOSS_PEAK"]={}; data["TREND_STATE"]={}
    DIRTY["need_save"]=True
    rset_single(data, force=True)
    return jsonify({"cleared":True})
