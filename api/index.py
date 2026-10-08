from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)
UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
SINGLE_KEY = "VENUS_V597_FINAL"
DAILY_GOAL = 100.0
DAILY_STOP = -20.0
BASE_POS = 20.0
MAX_OPEN = 5
# UPSTASH OPTIMIZED: 20 sec cache, not 7 sec
CACHE = {"data": None, "ts": 0, "whale": [], "whale_ts": 0}
DIRTY = {"need_save": False}

def rget_single():
    global CACHE
    now=time.time()
    # 20 sec cache = 3 GET/min not 24/min = 302k/month not 4M/month
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
            # FAST_WHALE not stored in Upstash - local only to save commands
            CACHE["data"]=data; CACHE["ts"]=now
            return data
    except: pass
    return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"TREND_STATE":{}}

def rset_single(data, force=False):
    global CACHE, DIRTY
    CACHE["data"]=data; CACHE["ts"]=time.time()
    try:
        if not UP_URL or not UP_TOKEN: return
        # UPSTASH OPTIMIZED: Only save if dirty + 20 sec passed, not every tick
        if not force and not DIRTY.get("need_save"): return
        if not force and time.time()-float(data.get("_last_save",0) or 0) < 20: return
        data["_last_save"]=time.time()
        DIRTY["need_save"]=False
        # Don't save whale list to Upstash - saves 50% payload + commands
        save_data = {k:v for k,v in data.items() if k not in ["FAST_WHALE","FAST_LAST"]}
        requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(save_data)], timeout=5)
    except: pass

def get_meme_whales_25():
    global CACHE
    now=time.time()
    # LOW CPU: 12 sec scan, not 2 sec
    if CACHE["whale"] and now - CACHE["whale_ts"] < 12:
        return CACHE["whale"]
    whales=[]
    try:
        all_pairs=[]
        try:
            r=requests.get("https://api.dexscreener.com/token-boosts/latest/v1", timeout=4).json()
            if isinstance(r,list):
                for it in r[:50]:
                    if it.get('chainId')=='solana':
                        tk=it.get('tokenAddress')
                        if tk:
                            try:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=3).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:1])
                            except: pass
        except: pass
        for q in ["A1","SWORDCAT","PUMP","BONK","WIF","PEPE","TRUMP","FLOKI"]:
            try:
                sr=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=3).json()
                if sr.get('pairs'): all_pairs.extend(sr['pairs'][:3])
            except: pass
        seen=set()
        data=CACHE["data"] or {}
        learn=data.get("LEARN_STATS",{}) if isinstance(data, dict) else {}
        last_peak=data.get("LAST_LOSS_PEAK",{}) if isinstance(data, dict) else {}
        last_t = CACHE["whale_ts"]
        no_trade_sec = now - last_t if last_t>0 else 0
        adaptive = no_trade_sec > 60
        emergency = no_trade_sec > 120
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
                if not (55000 <= liq <= 210000): continue
                if not (180000 <= fdv <= 2400000): continue
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); vol_h1=float(p.get('volume',{}).get('h1',0) or 0)
                ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
                txns=p.get('txns',{}); buys_m5=int(txns.get('m5',{}).get('buys',0) or 0); sells_m5=int(txns.get('m5',{}).get('sells',0) or 0)
                buys_h1=int(txns.get('h1',{}).get('buys',0) or 0)
                if ch_24 < -65 or ch_24 > 150: continue
                if emergency:
                    if not (600 <= vol_m5 <= 12000): continue
                    if buys_m5 < 22: continue
                    if not (-0.3 <= ch_m5 <= 5.0): continue
                    if ch_m5 <= 0: continue # MUST be positive momentum - fix SWORDCAT -1.6% bug
                    if sells_m5>0 and buys_m5 < sells_m5*1.15: continue
                    min_vl, max_vl, min_acc = 0.004, 0.16, 0.80
                elif adaptive:
                    if not (1000 <= vol_m5 <= 10000): continue
                    if buys_m5 < 28: continue
                    if not (0.2 <= ch_m5 <= 4.2): continue
                    if sells_m5>0 and buys_m5 < sells_m5*1.30: continue
                    min_vl, max_vl, min_acc = 0.007, 0.14, 0.95
                else:
                    if not (1500 <= vol_m5 <= 9000): continue
                    if buys_m5 < 35: continue
                    if not (0.4 <= ch_m5 <= 3.6): continue
                    if sells_m5>0 and buys_m5 < sells_m5*1.50: continue
                    min_vl, max_vl, min_acc = 0.010, 0.12, 1.05
                if buys_m5>=80 and sells_m5>=65 and buys_m5/sells_m5 < 1.25: continue
                vol_liq = vol_m5 / liq if liq>0 else 0
                if not (min_vl <= vol_liq <= max_vl): continue
                avg_5m = buys_h1/12 if buys_h1>0 else buys_m5
                accel = buys_m5 / (avg_5m+1)
                if accel < min_acc: continue
                lp=float(last_peak.get(base,10) or 10)
                if lp<0.8 and lp!=10: continue
                ratio = buys_m5 / (sells_m5+1)
                if not adaptive and not emergency and ch_m5<0.3: continue
                footprint = ratio*1.3 + vol_liq*65 + buys_m5*0.022
                score = (buys_m5*1600 + vol_m5*2.4) * (footprint+1) * (accel+0.6)
                if 0.6 <= ch_m5 <= 2.8: score*=2.8
                if ratio>=1.7: score*=1.7
                st=learn.get(base,{'w':0,'l':0})
                if st.get('w',0)>0: score*=6.0
                tier=f"{'EMER' if emergency else ('MOVE' if adaptive else 'TIGHT')} FP {footprint:.1f} V/L {vol_liq*100:.1f}% ACC x{accel:.1f} R {ratio:.1f}"
                whales.append({"prod":f"{base}-USD","symbol":base[:12],"price":price,"c1":ch_m5,"c24":ch_24,"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys_m5,"sells_m5":sells_m5,"score":score,"tier":tier,"wins":st.get('w',0),"last_peak":lp,"footprint":footprint,"vol_liq":vol_liq,"accel":accel,"ratio":ratio,"adaptive":adaptive,"emergency":emergency})
            except: continue
        whales.sort(key=lambda x: x['score'], reverse=True)
        CACHE["whale"]=whales[:20]
        CACHE["whale_ts"]=now
        return CACHE["whale"]
    except: return CACHE.get("whale",[])

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
    return round(max(15, min(pos, 42)),2)

def do_tick():
    global DIRTY
    data=rget_single()
    cap=float(data.get("FUND_CAP") or 1000.0); open_t=data.get("FUND_OPEN") or []; closed=data.get("FUND_CLOSED") or []
    wins=data.get("FUND_WINS") or 0; losses=data.get("FUND_LOSSES") or 0
    daily=float(data.get("FUND_DAILY_PNL") or 0); dg=float(data.get("FUND_DAILY_GROSS") or 0); df=float(data.get("FUND_DAILY_FEE") or 0)
    learn=data.get("LEARN_STATS") or {}; last_loss=data.get("LAST_LOSS_TIME") or {}; last_peak=data.get("LAST_LOSS_PEAK") or {}; trend_state=data.get("TREND_STATE") or {}
    fast_whale = get_meme_whales_25()

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
                close=True; rs=f"RUG {pct:.1f}% HH {hh} PEAK {peak:.1f}% BL 300s V597 {tier}"; last_loss[sym]=time.time()+300
            elif pct<=-2.5:
                close=True; rs=f"SL -2.5% {pct:.1f}% HH {hh} PEAK {peak:.1f}% CUT V597 {tier}"
            elif peak>=3.2 and pct>=3.2 and pct <= peak+trail and age>=8:
                close=True; rs=f"WIN 70% POCKET HH {hh} TRAIL {trail}% {pct:.1f}% PEAK {peak:.1f}% NET ${net:.3f} V597 {tier}"
            elif age>=45 and peak<0.5 and "EMER" in tier:
                close=True; rs=f"TIME 45s EMER NO TREND HH {hh} PEAK {peak:.1f}% CUT V597 {tier}"
            elif age>=75 and peak<0.8 and "MOVE" in tier:
                close=True; rs=f"TIME 75s MOVE NO TREND HH {hh} PEAK {peak:.1f}% CUT V597 {tier}"
            elif age>=90 and peak<1.1:
                close=True; rs=f"TIME 90s TIGHT NO TREND HH {hh} PEAK {peak:.1f}% CUT V597 {tier}"
            elif age>=260:
                close=True; rs=f"TIME 260s HH {hh} {pct:.1f}% PEAK {peak:.1f}% V597 {tier}"
            if close:
                closed.append({"symbol":sym,"prod":tr.get('prod',sym),"side":"LONG","entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":rs,"ts":time.time(),"is_meme":True,"pos":pos,"hh":hh})
                if len(closed)>500: closed=closed[-500:]
                if net>=0.30: wins+=1
                else: losses+=1
                if "RUG" not in rs:
                    last_loss[sym]=time.time()+10 if net>=0.30 else (time.time()+300 if peak<0.8 else time.time()+60)
                last_peak[sym]=peak; st=learn.get(sym,{'w':0,'l':0}); st['w' if net>=0.30 else 'l']=st.get('w' if net>=0.30 else 'l',0)+1; learn[sym]=st
                daily+=net; dg+=gross; df+=fee; cap+=net; changed=True
                if sym in trend_state: del trend_state[sym]
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)

    if daily >= DAILY_GOAL or daily <= DAILY_STOP:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak,"TREND_STATE":trend_state})
        DIRTY["need_save"]=True
        rset_single(data, force=True)
        return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"{'GOAL $100' if daily>=DAILY_GOAL else 'STOP'} ${daily:.2f} COMPOUND ${get_compound_pos(cap,daily)} V597"}

    cnt=len(new_open); idx=0
    open_syms=set(x['symbol'] for x in new_open); open_ids=set(x['cg_id'] for x in new_open)
    comp_pos=get_compound_pos(cap,daily)
    while cnt<MAX_OPEN and idx<len(fast_whale):
        try:
            m=fast_whale[idx]; idx+=1; sym=m['symbol']
            if sym in open_syms or m['cg_id'] in open_ids: continue
            if sym in last_loss and time.time()-float(last_loss.get(sym,0) or 0) < (10 if learn.get(sym,{}).get('w',0)>0 else 60): continue
            if float(last_peak.get(sym,10) or 10) < 0.8: continue
            pos=comp_pos
            reason=f"V597 {'EMER' if m.get('emergency') else ('MOVE' if m.get('adaptive') else 'TIGHT')} FP {m.get('footprint',0):.1f} V/L {m.get('vol_liq',0)*100:.1f}% ACC x{m.get('accel',0):.1f} R {m.get('ratio',0):.1f} BUYS {m['buys_m5']} SELLS {m['sells_m5']} VOL ${m['vol_m5']:.0f} LIQ ${m['liq']:.0f} FDV ${m['fdv']:.0f} {m['c1']:.1f}% M5 COMPOUND ${pos} TREND HH"
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":time.time(),"side":"LONG","reason":reason,"target":6.0,"stop":2.5,"last_price":m['price'],"pos":pos,"c1":m['c1'],"c24":m['c24'],"cg_id":m['cg_id'],"is_meme":True,"fdv":m['fdv'],"peak_pct":0,"tier":m.get('tier','SHARK')})
            open_syms.add(sym); open_ids.add(m['cg_id']); cnt+=1; changed=True
        except: continue

    if changed:
        DIRTY["need_save"]=True
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak,"TREND_STATE":trend_state})
    rset_single(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"v597 UPSTASH 500K COMPOUND ${comp_pos} {len(fast_whale)} SHARKS TIGHT 0.4-3.6% 5/5 $100/DAY LOW CPU UPSTASH","compound_pos":comp_pos}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v597 UPSTASH 500K</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#0a0a0a;color:#00FF88}.top{padding:8px 10px;display:flex;justify-content:space-between;border-bottom:2px solid #00FF88;background:#000}.top b{color:#00FF88;font-size:6px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#222}.card{background:#000;padding:10px}.card small{color:#888;font-size:6px}.card b{font-size:18px;display:block;color:#fff}.card b.green{color:#00FF88}.card b.red{color:#FF0040}button{border:none;padding:12px;width:100%;font-weight:900;cursor:pointer;font-size:10px}button.scan{background:linear-gradient(90deg,#00FF88,#FFD000);color:#000}button.clear{background:#FF0040;color:#fff}</style></head><body>
<div class="top"><div><b>VENUS v597 FINAL UPSTASH 500K LOW CPU 20s CACHE 12s SCAN NO WHALE SAVE DIRTY SAVE ONLY COMPOUND $20->$42 TRAIL HH -0.40% to -1.3% 5/5 $100/DAY UPSTASH 500K + VERCEL FREE FEEL MOVEMENT</b></div><div style="font-size:8px;color:#00FF88" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND COMPOUND V597 UPSTASH 500K - BASE $20 x5 UPSTASH OPTIMIZED</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">V597 UPSTASH 500K</small></div>
<div class="card"><small>OPEN 5/5 UPSTASH 500K SHARK FP TREND HH - 5/5 ONLY</small><b id="open" class="green">0/5</b><small class="green" id="wr">V597 UPSTASH</small></div>
<div class="card"><small>DAILY NET GOAL $100 STOP -$20 COMPOUND POS V597 UPSTASH 500K</small><b id="daily" class="green">+$0.00</b><small id="dailySub" style="color:#666">V597 UPSTASH</small></div>
<div class="card"><small>PERF COMPOUND UPSTASH 500K SHARK FP HH TRAIL TP 6% SL 2.5% -0.40% to -1.3%</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">V597 UPSTASH 5/5</small></div>
</div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #FFD000"><div style="font-size:7px;color:#FFD000">TOP 20 V597 UPSTASH 500K - 20s CACHE 12s SCAN DIRTY SAVE ONLY NO WHALE SAVE - $20->42 COMPOUND LOCK $1 at 3.2% TRAIL HH -0.40%/-0.55%/-0.70%/-1.0%/-1.3% LOSS $0.50 TIME 45s EMER 75s MOVE 90s TIGHT - V597: TIGHT 0.4-3.6% BUYS 35+ V/L 1.0-12% ACC x1.05+ R 1.5x MOVE 60s+ 0.2-4.2% BUYS 28+ V/L 0.7-14% ACC x0.95+ R 1.3x EMER 120s+ -0.3-5.0% BUYS 22+ V/L 0.4-16% ACC x0.80+ R 1.15x POSITIVE M5 ONLY UPSTASH 500K = 20s CACHE 3 GET/min 3 SET/min 302k/month NOT 4M/month VERCEL LOW CPU = 12s SCAN + PAUSE WHEN HIDDEN SHARK FP = BUYS/SELL RATIO + VOL/LIQ + ACCEL + MOVEMENT + WINNER x6 - 20 BEST - COMPOUND - V597 UPSTASH 500K 5/5 ALWAYS LOW CPU UPSTASH 500K</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 130px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>5 TRADES COMPOUND V597 UPSTASH 500K SHARK FP - 5/5 ALWAYS UPSTASH 500K LOW CPU</span><span>SIDE</span><span>ENTRY FEE PEAK HH</span><span>TICK TP/SL NET PEAK TREND V597</span><span>TP/SL NET V597</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN V597 UPSTASH 500K LOW CPU COMPOUND $20->$42 V/L 0.4-16% ACC x0.80+ -0.3-5.0% EMER 0.4-3.6% TIGHT BUYS 22+/35+ - 20 BEST - $100 GOAL -$20 STOP - FEE 0.2% - V597 8s WIN 45s/75s/90s LOSS TREND HH -0.40%/-1.3% COMPOUND UPSTASH 500K - 5/5 ALWAYS UPSTASH 500K LOW CPU UPSTASH 500K FEEL MOVEMENT</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN 5 TRADES COMPOUND V597 UPSTASH 500K - KEEPS LEARN - FEE 0.2% TP 6% SL 2.5% 8s WIN 45s/75s/90s LOSS TREND HH COMPOUND UPSTASH 500K LOW CPU UPSTASH 500K</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88;margin-bottom:3px">CLOSED LAST 50 - COMPOUND V597 UPSTASH 500K SHARK FP LOCK $1 at 3.2% TRAIL HH -0.40%/-1.3% LOSS $0.50 - $100 GOAL - V597 8s WIN 45s/75s/90s LOSS TREND HH COMPOUND UPSTASH 500K LOW CPU x6</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / FEE PEAK HH TREND V597</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON - V597 UPSTASH 500K SHARK FP TREND HH TP 6% SL 2.5%</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
let paused=false;
document.addEventListener('visibilitychange',()=>{paused=document.hidden});
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 if(paused) return;
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2)+' POS $'+(j.compound_pos||15);
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' V597 UPSTASH 500K LOW CPU UPSTASH 500K FEEL MOVEMENT';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/5 UPSTASH 500K FP POS $'+(j.compound_pos||15)+' 0.4-3.6% TIGHT 0.2-4.2% MOVE -0.3-5.0% EMER V/L 0.4-16% BUYS 22+/35+ FEE $'+((j.compound_pos||15)*0.002).toFixed(3)+' TP 6% SL 2.5% TRAIL HH 5/5 UPSTASH 500K LOW CPU BALANCED';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L KV '+(j.kv||'1 CMD')+' V597 UPSTASH 500K 5/5 TRADE MORE';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#00FF88':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $100 STOP -$20 POS $'+(j.compound_pos||15)+' V597 UPSTASH 500K TREND HH 5/5 UPSTASH 500K';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('wlSub').innerText='WR '+wr+'% - V597 UPSTASH 500K FP V/L 0.4-16% ACC x0.80+ -0.3-5.0% EMER 0.4-3.6% TIGHT BUYS 22+/35+ TP 6% SL 2.5% TRAIL -0.40%/-1.3% HH POS $'+(j.compound_pos||15)+' GOAL $100 UPSTASH 500K';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' POS $'+(j.compound_pos||15)+' V597 UPSTASH 500K 5/5 UPSTASH 500K';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid ${m.wins>0?'#FFD000':'#00FF88'};padding:2px 4px;font-size:7px;color:${m.wins>0?'#FFD000':'#00FF88'}">#${i+1} ${m.symbol} ${Number(m.c1).toFixed(1)}% M5 $${Number(m.price).toFixed(8)} FP ${Number(m.footprint||0).toFixed(1)} V/L ${(Number(m.vol_liq||0)*100).toFixed(1)}% ACC x${Number(m.accel||0).toFixed(1)} R ${Number(m.ratio||0).toFixed(1)} ${m.emergency?'EMER':(m.adaptive?'MOVE':'TIGHT')}<br><span style="color:#FFD000">SHARK V597 UPSTASH ${m.buys_m5} BUYS ${m.sells_m5} SELLS VOL $${Number(m.vol_m5||0).toFixed(0)} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)}</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">Scanning V597 UPSTASH 500K 0.4-3.6% TIGHT 0.2-4.2% MOVE -0.3-5.0% EMER V/L 0.4-16% - UPSTASH 500K - 20s CACHE 12s SCAN DIRTY SAVE ONLY - trades movement, low Upstash, low CPU</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||15); let fee=pos*0.002; let target=6.0; let netEst=pos*target/100 - fee; let peak=Number(t.peak_pct||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 130px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:#00FF88">${t.symbol||''}</b> <small style="color:#00FF88">$${pos} ${t.tier.split(' ')[0]} HH ${t.hh||0}</small></span><span><b style="color:#00FF88;border:1px solid #00FF88;padding:1px 3px;font-size:7px">LONG</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos} $${fee.toFixed(3)} PEAK ${peak.toFixed(1)}% HH ${t.hh||0} UPSTASH</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,95)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} PEAK ${peak.toFixed(1)}% HH ${t.hh||0} TRAIL V597 UPSTASH</small></span><span style="font-size:7px"><span style="color:#00FF88">TP 6% $${(pos*0.06).toFixed(2)}</span><br><span style="color:#FF0040">SL 2.5% $${(pos*0.025).toFixed(2)}</span><br><small style="color:#FFD000">HH ${t.hh||0} V597 UPSTASH</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#00FF88;padding:10px;font-size:10px">No open - V597 UPSTASH 500K will fill 5/5 when movement detected - UPSTASH 500K LOW CPU - FEELS MOVEMENT TRADE MORE - 20s CACHE DIRTY SAVE ONLY</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-50).reverse().forEach(c=>{
   let col=c.net>=0.30?'#00FF88':'#FF0040';
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#00FF88"><b style="color:${c.net>=0.30?'#FFD000':'#FF00FF'}">${c.symbol||''}</b><br><small style="color:${c.net>=0.30?'#FFD000':'#FF00FF'}">LONG $${c.pos||15} HH ${c.hh||0} ${c.net>=0.30?'WINNER V597 UPSTASH':'LOSER V597 UPSTASH'} TREND</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:${c.net>=0.30?'#FFD000':'#FF00FF'};border:1px solid ${c.net>=0.30?'#FFD000':'#FF00FF'};padding:1px 3px;font-size:7px">LONG</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}% PEAK ${Number(c.peak||0).toFixed(1)}% HH ${c.hh||0}</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)} V597 UPSTASH HH ${c.hh||0}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,200)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% PEAK ${Number(c.peak||0).toFixed(1)}% HH ${c.hh||0} V597 UPSTASH</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FFD000;padding:10px">Scanning V597 UPSTASH 500K 0.4-3.6% TIGHT 0.2-4.2% MOVE -0.3-5.0% EMER V/L 0.4-16% - UPSTASH 500K - 20s CACHE 12s SCAN DIRTY SAVE ONLY - trades movement, low Upstash, low CPU, feels movement...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR V597 UPSTASH 500K - KEEPS LEARN?')) return; await fetch('/api/clear_closed_fake'); await load(); }
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
    return jsonify({"cap":cp,"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"closed":data.get("FUND_CLOSED",[]),"daily":dly,"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":CACHE.get("whale",[]),"kv":f"v597 UPSTASH 500K COMPOUND ${comp} 0.4-3.6% TIGHT 0.2-4.2% MOVE -0.3-5.0% EMER HH GOAL ${DAILY_GOAL} UPSTASH 500K LOW CPU","compound_pos":comp})
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
