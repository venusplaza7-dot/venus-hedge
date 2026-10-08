from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)
UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
SINGLE_KEY = "VENUS_V593_ADAPTIVE"
DAILY_GOAL = 100.0
DAILY_STOP = -20.0
BASE_POS = 20.0
MAX_OPEN = 5
CACHE = {"data": None, "ts": 0}

def rget_single():
    global CACHE
    now=time.time()
    if CACHE["data"] and now - CACHE["ts"] < 6:
        return CACHE["data"]
    try:
        if not UP_URL or not UP_TOKEN:
            return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"FAST_WHALE":[],"FAST_LAST":0,"TREND_STATE":{}}
        r=requests.get(f"{UP_URL}/get/{SINGLE_KEY}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=5)
        v=r.json().get("result")
        if v:
            data=json.loads(v)
            data.setdefault("LAST_LOSS_PEAK",{}); data.setdefault("LAST_LOSS_TIME",{}); data.setdefault("LEARN_STATS",{}); data.setdefault("TREND_STATE",{})
            CACHE["data"]=data; CACHE["ts"]=now
            return data
    except: pass
    return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"FAST_WHALE":[],"FAST_LAST":0,"TREND_STATE":{}}

def rset_single(data):
    global CACHE
    CACHE["data"]=data; CACHE["ts"]=time.time()
    try:
        if not UP_URL or not UP_TOKEN: return
        if time.time()-float(data.get("_last_save",0) or 0) < 2: return
        data["_last_save"]=time.time()
        requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(data)], timeout=5)
    except: pass

def get_meme_whales_25():
    whales=[]
    try:
        all_pairs=[]
        for url in ["https://api.dexscreener.com/token-boosts/latest/v1","https://api.dexscreener.com/token-boosts/top/v1"]:
            try:
                r=requests.get(url, timeout=5).json()
                if isinstance(r,list):
                    for it in r[:70]:
                        if it.get('chainId')=='solana':
                            tk=it.get('tokenAddress')
                            if tk:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=3).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:1])
            except: continue
        for q in ["A1","SWORDCAT","PLAGUE","PUMPOWEEN","BONK","WIF","PEPE","PUMP","CHONK","VIBE","UI","GSI","MINER","ECSTASY","SK","FLY","BULLCRAFT","TRUMP"]:
            try:
                sr=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=3).json()
                if sr.get('pairs'): all_pairs.extend(sr['pairs'][:4])
            except: pass
        seen=set()
        data=CACHE["data"] or {}
        learn=data.get("LEARN_STATS",{}) if isinstance(data, dict) else {}
        last_peak=data.get("LAST_LOSS_PEAK",{}) if isinstance(data, dict) else {}
        # ADAPTIVE: if no whale for 90s, relax to find shark
        last_t = float(data.get("FAST_LAST",0) or 0)
        adaptive = (time.time() - last_t) > 90
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
                if not (85000 <= liq <= 175000): continue
                if not (320000 <= fdv <= 1600000): continue
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); vol_h1=float(p.get('volume',{}).get('h1',0) or 0)
                ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
                txns=p.get('txns',{}); buys_m5=int(txns.get('m5',{}).get('buys',0) or 0); sells_m5=int(txns.get('m5',{}).get('sells',0) or 0)
                buys_h1=int(txns.get('h1',{}).get('buys',0) or 0)
                if adaptive:
                    if not (1800 <= vol_m5 <= 8500): continue
                    if buys_m5 < 42: continue
                    if not (0.6 <= ch_m5 <= 3.2): continue
                    if sells_m5>0 and buys_m5 < sells_m5*1.75: continue
                    min_vl, max_vl, min_acc = 0.012, 0.10, 1.15
                else:
                    if not (2400 <= vol_m5 <= 7500): continue
                    if buys_m5 < 50: continue
                    if not (0.8 <= ch_m5 <= 2.9): continue
                    if sells_m5>0 and buys_m5 < sells_m5*1.9: continue
                    min_vl, max_vl, min_acc = 0.019, 0.085, 1.25
                if ch_24 < -35 or ch_24 > 100: continue
                if buys_m5>=70 and sells_m5>=55 and buys_m5/sells_m5 < 1.35: continue
                vol_liq = vol_m5 / liq if liq>0 else 0
                if not (min_vl <= vol_liq <= max_vl): continue
                avg_5m = buys_h1/12 if buys_h1>0 else buys_m5
                accel = buys_m5 / (avg_5m+1)
                if accel < min_acc: continue
                lp=float(last_peak.get(base,10) or 10)
                if lp<1.0: continue
                ratio = buys_m5 / (sells_m5+1)
                footprint = ratio*1.5 + vol_liq*90 + buys_m5*0.03
                score = (buys_m5*2200 + vol_m5*3.0) * footprint * accel
                if 1.1 <= ch_m5 <= 2.3: score*=3.5
                if ratio>=2.4: score*=2.4
                st=learn.get(base,{'w':0,'l':0})
                if st.get('w',0)>0: score*=7.0
                tier=f"{'ADAPT' if adaptive else 'SHARK'} FP {footprint:.1f} V/L {vol_liq*100:.1f}% ACC x{accel:.1f} R {ratio:.1f}"
                whales.append({"prod":f"{base}-USD","symbol":base[:12],"price":price,"c1":ch_m5,"c24":ch_24,"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys_m5,"sells_m5":sells_m5,"score":score,"tier":tier,"wins":st.get('w',0),"last_peak":lp,"footprint":footprint,"vol_liq":vol_liq,"accel":accel,"ratio":ratio,"adaptive":adaptive})
            except: continue
        whales.sort(key=lambda x: x['score'], reverse=True)
        return whales[:25]
    except: return []

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
    if daily>=25: bonus=3
    if daily>=55: bonus=6
    if daily>=85: bonus=10
    pos = BASE_POS * cap_f + bonus
    return round(max(18, min(pos, 48)),2)

def do_tick():
    data=rget_single()
    cap=float(data.get("FUND_CAP") or 1000.0); open_t=data.get("FUND_OPEN") or []; closed=data.get("FUND_CLOSED") or []
    wins=data.get("FUND_WINS") or 0; losses=data.get("FUND_LOSSES") or 0
    daily=float(data.get("FUND_DAILY_PNL") or 0); dg=float(data.get("FUND_DAILY_GROSS") or 0); df=float(data.get("FUND_DAILY_FEE") or 0)
    learn=data.get("LEARN_STATS") or {}; last_loss=data.get("LAST_LOSS_TIME") or {}; last_peak=data.get("LAST_LOSS_PEAK") or {}; fast_whale=data.get("FAST_WHALE") or []; trend_state=data.get("TREND_STATE") or {}
    now=time.time()
    if now - float(data.get("FAST_LAST") or 0) > 2:
        w=get_meme_whales_25()
        if w: fast_whale=w; data["FAST_WHALE"]=w; data["FAST_LAST"]=now

    new_open=[]
    for tr in open_t:
        try:
            sym=tr.get('symbol','?'); entry=float(tr.get('entry',0) or 0); last=float(tr.get('last_price',entry) or entry); pos=float(tr.get('pos',BASE_POS) or BASE_POS); cg_id=tr.get('cg_id','')
            peak=float(tr.get('peak_pct',0) or 0); tier=tr.get('tier','ULTRA')
            if entry==0: continue
            cur,src=get_price(cg_id,last)
            if cur==0: cur=last
            age=now-float(tr.get('ts',now) or now); pct=(cur-entry)/entry*100; fee=pos*0.002; gross=pos*pct/100; net=gross-fee
            ts = trend_state.get(sym, {"hh":0, "last_peak":0})
            if pct > ts.get("last_peak",0):
                ts["hh"]+=1; ts["last_peak"]=pct
            trend_state[sym]=ts
            hh=ts["hh"]
            if pct>peak: peak=pct; tr['peak_pct']=peak
            if hh>=4: trail=-1.4
            elif hh>=3: trail=-1.15
            elif hh>=2: trail=-0.85
            elif peak>=4: trail=-0.65
            else: trail=-0.5
            close=False; rs=""
            if pct<=-12 and peak<3:
                close=True; rs=f"RUG {pct:.1f}% HH {hh} PEAK {peak:.1f}% BL 300s V593 {tier}"; last_loss[sym]=now+300
            elif pct<=-2.0:
                close=True; rs=f"SL -2.0% {pct:.1f}% HH {hh} PEAK {peak:.1f}% CUT V593 {tier}"
            elif peak>=3.8 and pct>=3.8 and pct <= peak+trail and age>=7:
                close=True; rs=f"WIN 70% POCKET HH {hh} TRAIL {trail}% {pct:.1f}% PEAK {peak:.1f}% NET ${net:.3f} V593 {tier}"
            elif age>=85 and peak<1.3:
                close=True; rs=f"TIME 85s NO TREND HH {hh} PEAK {peak:.1f}% CUT V593 {tier}"
            elif age>=260:
                close=True; rs=f"TIME 260s HH {hh} {pct:.1f}% PEAK {peak:.1f}% V593 {tier}"
            if close:
                closed.append({"symbol":sym,"prod":tr.get('prod',sym),"side":"LONG","entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":rs,"ts":now,"is_meme":True,"pos":pos,"hh":hh})
                if len(closed)>500: closed=closed[-500:]
                if net>=0.35: wins+=1
                else: losses+=1
                if "RUG" not in rs:
                    last_loss[sym]=now+12 if net>=0.35 else (now+300 if peak<1 else now+80)
                last_peak[sym]=peak; st=learn.get(sym,{'w':0,'l':0}); st['w' if net>=0.35 else 'l']=st.get('w' if net>=0.35 else 'l',0)+1; learn[sym]=st
                daily+=net; dg+=gross; df+=fee; cap+=net
                if sym in trend_state: del trend_state[sym]
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)

    if daily >= DAILY_GOAL or daily <= DAILY_STOP:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak,"TREND_STATE":trend_state})
        rset_single(data); return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"{'GOAL $100' if daily>=DAILY_GOAL else 'STOP'} ${daily:.2f} COMPOUND ${get_compound_pos(cap,daily)} V593"}

    cnt=len(new_open); idx=0
    open_syms=set(x['symbol'] for x in new_open); open_ids=set(x['cg_id'] for x in new_open)
    comp_pos=get_compound_pos(cap,daily)
    while cnt<MAX_OPEN and idx<len(fast_whale):
        try:
            m=fast_whale[idx]; idx+=1; sym=m['symbol']
            if sym in open_syms or m['cg_id'] in open_ids: continue
            if sym in last_loss and now-float(last_loss.get(sym,0) or 0) < (15 if learn.get(sym,{}).get('w',0)>0 else 85): continue
            if float(last_peak.get(sym,10) or 10) < 1.0: continue
            pos=comp_pos
            reason=f"V593 {'ADAPT' if m.get('adaptive') else 'SHARK'} FP {m.get('footprint',0):.1f} V/L {m.get('vol_liq',0)*100:.1f}% ACC x{m.get('accel',0):.1f} R {m.get('ratio',0):.1f} BUYS {m['buys_m5']} SELLS {m['sells_m5']} VOL ${m['vol_m5']:.0f} LIQ ${m['liq']:.0f} FDV ${m['fdv']:.0f} {m['c1']:.1f}% M5 COMPOUND ${pos} TREND HH"
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":now,"side":"LONG","reason":reason,"target":6.0,"stop":2.0,"last_price":m['price'],"pos":pos,"c1":m['c1'],"c24":m['c24'],"cg_id":m['cg_id'],"is_meme":True,"fdv":m['fdv'],"peak_pct":0,"tier":m.get('tier','SHARK')})
            open_syms.add(sym); open_ids.add(m['cg_id']); cnt+=1
        except: continue

    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak,"TREND_STATE":trend_state})
    rset_single(data)
    adapt_cnt=sum(1 for w in fast_whale if w.get('adaptive'))
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"v593 ADAPTIVE SHARK COMPOUND ${comp_pos} {len(fast_whale)} SHARKS {adapt_cnt} ADAPT 0.6-3.2% HH TRAIL 5/5 $100/DAY","compound_pos":comp_pos}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v593 ADAPTIVE SHARK COMPOUND</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}body{background:#0a0a0a;color:#00FF88}.top{padding:8px 10px;display:flex;justify-content:space-between;border-bottom:2px solid #00FF88;background:#000}.top b{color:#00FF88;font-size:6px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#222}.card{background:#000;padding:10px}.card small{color:#888;font-size:6px}.card b{font-size:18px;display:block;color:#fff}.card b.green{color:#00FF88}.card b.red{color:#FF0040}button{border:none;padding:12px;width:100%;font-weight:900;cursor:pointer;font-size:10px}button.scan{background:linear-gradient(90deg,#00FF88,#FFD000);color:#000}button.clear{background:#FF0040;color:#fff}</style></head><body>
<div class="top"><div><b>VENUS v593 ADAPTIVE SHARK FP COMPOUND TREND HH 0.6-3.2% ADAPT 0.8-2.9% TIGHT V/L 1.2-10% ACC x1.15+ BUYS 42+ TIGHT 50+ COMPOUND $20->$48 TRAIL HH -0.5% to -1.4% 5/5 $100/DAY ADAPTIVE NO LOOSE</b></div><div style="font-size:8px;color:#00FF88" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND COMPOUND V593 ADAPTIVE - BASE $20 x5 NO LOOSE FALLBACK</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">V593 ADAPTIVE SHARK</small></div>
<div class="card"><small>OPEN 5/5 ADAPTIVE SHARK FP TREND HH - 5/5 ONLY SHARK ADAPTIVE</small><b id="open" class="green">0/5</b><small class="green" id="wr">V593 ADAPTIVE</small></div>
<div class="card"><small>DAILY NET GOAL $100 STOP -$20 COMPOUND POS V593 ADAPTIVE</small><b id="daily" class="green">+$0.00</b><small id="dailySub" style="color:#666">V593 ADAPTIVE</small></div>
<div class="card"><small>PERF COMPOUND ADAPTIVE SHARK FP HH TRAIL TP 6% SL 2.0% -0.5% to -1.4%</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">V593 ADAPTIVE 5/5</small></div>
</div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #FFD000"><div style="font-size:7px;color:#FFD000">TOP 25 V593 ADAPTIVE SHARK FOOTPRINT - NO LOOSE FALLBACK - $20->48 COMPOUND LOCK $1 at 3.8% TRAIL HH -0.5%/-0.65%/-0.85%/-1.15%/-1.4% LOSS $0.40 ADAPT 7s WIN 85s LOSS - V593: ADAPTIVE = After 90s no shark, relax to 0.6-3.2% BUYS 42+ V/L 1.2-10% ACC x1.15+ TIGHT = 0.8-2.9% BUYS 50+ V/L 1.9-8.5% ACC x1.25+ SHARK FP = BUYS/SELL RATIO + VOL/LIQ + ACCEL VOL 1.8k-8.5k LIQ 85k-175k FDV 320k-1.6M TREND HH COUNT + WINNER x7 - 25 BEST - COMPOUND - V593 ADAPTIVE SHARK FP 5/5 ALWAYS NO LOOSE</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 130px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>5 TRADES COMPOUND V593 ADAPTIVE SHARK FP - 5/5 ALWAYS ADAPTIVE NO LOOSE</span><span>SIDE</span><span>ENTRY FEE PEAK HH</span><span>TICK TP/SL NET PEAK TREND V593</span><span>TP/SL NET V593</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN V593 ADAPTIVE SHARK FP NO LOOSE COMPOUND $20->48 V/L 1.2-10% ACC x1.15+ 0.6-3.2% ADAPT 0.8-2.9% TIGHT BUYS 42+/50+ - 25 BEST - $100 GOAL -$20 STOP - FEE 0.2% - V593 7s WIN 85s LOSS TREND HH -0.5%/-1.4% COMPOUND ADAPTIVE - 5/5 ALWAYS ADAPTIVE NO LOOSE</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN 5 TRADES COMPOUND V593 ADAPTIVE - KEEPS LEARN - FEE 0.2% TP 6% SL 2.0% 7s WIN 85s LOSS TREND HH COMPOUND ADAPTIVE NO LOOSE</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88;margin-bottom:3px">CLOSED LAST 50 - COMPOUND V593 ADAPTIVE SHARK FP LOCK $1 at 3.8% TRAIL HH -0.5%/-1.4% LOSS $0.40 - $100 GOAL - V593 7s WIN 85s LOSS TREND HH COMPOUND ADAPTIVE NO LOOSE x7</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / FEE PEAK HH TREND V593</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON - V593 ADAPTIVE SHARK FP TREND HH TP 6% SL 2.0%</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2)+' POS $'+(j.compound_pos||20);
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' V593 ADAPTIVE SHARK FP NO LOOSE COMPOUND';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/5 ADAPTIVE SHARK FP POS $'+(j.compound_pos||20)+' 0.6-3.2% ADAPT 0.8-2.9% TIGHT V/L 1.2-10% ACC x1.15+ BUYS 42+/50+ FEE $'+((j.compound_pos||20)*0.002).toFixed(3)+' TP 6% SL 2.0% TRAIL HH 5/5 NO LOOSE ADAPTIVE';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L KV '+(j.kv||'1 CMD')+' V593 ADAPTIVE NO LOOSE 5/5';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#00FF88':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $100 STOP -$20 POS $'+(j.compound_pos||20)+' V593 ADAPTIVE SHARK FP NO LOOSE TREND HH 5/5';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('wlSub').innerText='WR '+wr+'% - V593 ADAPTIVE SHARK FP V/L 1.2-10% ADAPT 1.9-8.5% TIGHT ACC x1.15+/1.25+ 0.6-3.2% ADAPT 0.8-2.9% TIGHT BUYS 42+/50+ TP 6% SL 2.0% TRAIL -0.5%/-1.4% HH POS $'+(j.compound_pos||20)+' GOAL $100 NO LOOSE ADAPTIVE';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' POS $'+(j.compound_pos||20)+' V593 ADAPTIVE NO LOOSE 5/5';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid ${m.wins>0?'#FFD000':'#00FF88'};padding:2px 4px;font-size:7px;color:${m.wins>0?'#FFD000':'#00FF88'}">#${i+1} ${m.symbol} ${Number(m.c1).toFixed(1)}% M5 $${Number(m.price).toFixed(8)} FP ${Number(m.footprint||0).toFixed(1)} V/L ${(Number(m.vol_liq||0)*100).toFixed(1)}% ACC x${Number(m.accel||0).toFixed(1)} R ${Number(m.ratio||0).toFixed(1)} ${m.adaptive?'ADAPT':'TIGHT'}<br><span style="color:#FFD000">SHARK V593 ${m.buys_m5} BUYS ${m.sells_m5} SELLS VOL $${Number(m.vol_m5||0).toFixed(0)} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)}</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">Scanning V593 ADAPTIVE SHARK FOOTPRINT NO LOOSE 0.6-3.2% ADAPT 0.8-2.9% TIGHT V/L 1.2-10% ACC - ADAPTIVE - shark only no loose fallback</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||20); let fee=pos*0.002; let target=6.0; let netEst=pos*target/100 - fee; let peak=Number(t.peak_pct||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 130px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:#00FF88">${t.symbol||''}</b> <small style="color:#00FF88">$${pos} SHARK HH ${t.hh||0}</small></span><span><b style="color:#00FF88;border:1px solid #00FF88;padding:1px 3px;font-size:7px">LONG</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos} $${fee.toFixed(3)} PEAK ${peak.toFixed(1)}% HH ${t.hh||0} ADAPTIVE</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,95)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} PEAK ${peak.toFixed(1)}% HH ${t.hh||0} TRAIL V593 ADAPTIVE</small></span><span style="font-size:7px"><span style="color:#00FF88">TP 6% $${(pos*0.06).toFixed(2)}</span><br><span style="color:#FF0040">SL 2.0% $${(pos*0.02).toFixed(2)}</span><br><small style="color:#FFD000">HH ${t.hh||0} V593 ADAPTIVE</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#00FF88;padding:10px;font-size:10px">No open - V593 ADAPTIVE SHARK FP will fill 5/5 when shark footprint detected - ADAPTIVE NO LOOSE - COMPOUND TREND MODE ADAPTIVE</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-50).reverse().forEach(c=>{
   let col=c.net>=0.35?'#00FF88':'#FF0040';
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#00FF88"><b style="color:${c.net>=0.35?'#FFD000':'#FF00FF'}">${c.symbol||''}</b><br><small style="color:${c.net>=0.35?'#FFD000':'#FF00FF'}">LONG $${c.pos||20} HH ${c.hh||0} ${c.net>=0.35?'WINNER V593 ADAPTIVE':'LOSER V593 ADAPTIVE'} TREND</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:${c.net>=0.35?'#FFD000':'#FF00FF'};border:1px solid ${c.net>=0.35?'#FFD000':'#FF00FF'};padding:1px 3px;font-size:7px">LONG</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}% PEAK ${Number(c.peak||0).toFixed(1)}% HH ${c.hh||0}</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)} V593 ADAPTIVE HH ${c.hh||0}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,200)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% PEAK ${Number(c.peak||0).toFixed(1)}% HH ${c.hh||0} V593 ADAPTIVE</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FFD000;padding:10px">Scanning V593 ADAPTIVE SHARK FP NO LOOSE 0.6-3.2% ADAPT 0.8-2.9% TIGHT V/L 1.2-10% ACC - ADAPTIVE - NO LOOSE - ADAPTIVE...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR V593 ADAPTIVE - KEEPS LEARN?')) return; await fetch('/api/clear_closed_fake'); await load(); }
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
    cp=data.get("FUND_CAP",1000); dly=data.get("FUND_DAILY_PNL",0); comp=get_compound_pos(cp,dly)
    return jsonify({"cap":cp,"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"closed":data.get("FUND_CLOSED",[]),"daily":dly,"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":data.get("FAST_WHALE",[]),"kv":f"v593 ADAPTIVE SHARK FP COMPOUND ${comp} 0.6-3.2% ADAPT 0.8-2.9% TIGHT HH GOAL ${DAILY_GOAL}","compound_pos":comp})
@app.route("/api/cron")
def cron(): return jsonify(do_tick())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget_single()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["LAST_LOSS_PEAK"]={}; data["TREND_STATE"]={}
    rset_single(data); data["_last_save"]=0; rset_single(data)
    return jsonify({"cleared":True})
