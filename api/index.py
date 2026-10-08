from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)

UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
SINGLE_KEY = "VENUS_V608_ADAPTIVE_15"
DAILY_GOAL = 100.0
DAILY_STOP = -15.0
CACHE = {"data": None, "ts": 0}

def rget():
    global CACHE
    now=time.time()
    if CACHE["data"] and now - CACHE["ts"] < 6: return CACHE["data"]
    try:
        if not UP_URL or not UP_TOKEN: return {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"BLACKLIST":{},"FAST_WHALE":[],"FAST_LAST":0,"ROTATE_LAST":0,"ROTATE_COINS":[]}
        r=requests.get(f"{UP_URL}/get/{SINGLE_KEY}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=5)
        v=r.json().get("result")
        if v:
            data=json.loads(v)
            CACHE["data"]=data; CACHE["ts"]=now
            return data
    except: pass
    return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"LAST_LOSS_PEAK":{},"BLACKLIST":{},"FAST_WHALE":[],"FAST_LAST":0,"ROTATE_LAST":0,"ROTATE_COINS":[]}

def rset(data):
    global CACHE
    CACHE["data"]=data; CACHE["ts"]=time.time()
    try:
        if not UP_URL or not UP_TOKEN: return
        last=float(data.get("_last_save",0) or 0)
        if time.time()-last < 3: return
        data["_last_save"]=time.time()
        requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(data)], timeout=5)
    except: pass

def scan_adaptive_big_volume():
    all_pairs=[]
    try:
        for q in ["SOL","BONK","WIF","POPCAT","MEW","BOME","WEN","JUP","RAY","PYTH","TRUMP","PEPE","MUMU","BODEN","MISTAKE","SWORDCAT","FRANK","GARY","SWORDOWL","CAT","DOG","MOON","PEPE2"]:
            try:
                r=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=5).json()
                if r.get('pairs'):
                    for p in r['pairs'][:4]:
                        if p.get('chainId')=='solana': all_pairs.append(p)
            except: pass
        for url in ["https://api.dexscreener.com/token-boosts/top/v1","https://api.dexscreener.com/token-boosts/latest/v1"]:
            try:
                r=requests.get(url, timeout=6).json()
                if isinstance(r,list):
                    for it in r[:90]:
                        if it.get('chainId')=='solana':
                            tk=it.get('tokenAddress')
                            if tk:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=4).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:1])
            except: pass
    except: pass

    data=CACHE["data"] or {}; learn=data.get("LEARN_STATS",{}); last_loss=data.get("LAST_LOSS_TIME",{}); last_peak=data.get("LAST_LOSS_PEAK",{}); blacklist=data.get("BLACKLIST",{})
    now=time.time()
    seen=set()
    candidates=[]

    for p in all_pairs:
        try:
            if p.get('chainId')!='solana': continue
            base=p.get('baseToken',{}).get('symbol','').upper()
            if base in ['SOL','USDC','USDT','WETH','WBTC','WSOL']: continue
            if base in blacklist and now - float(blacklist.get(base,0) or 0) < 1500: continue
            addr=p.get('pairAddress')
            if not addr or addr in seen: continue
            seen.add(addr)
            fdv=float(p.get('fdv',0) or 0); liq=float(p.get('liquidity',{}).get('usd',0) or 0); price=float(p.get('priceUsd',0) or 0)
            if price==0: continue
            if not (30000 <= liq <= 500000): continue
            if not (120000 <= fdv <= 8000000): continue
            vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_h1=float(p.get('priceChange',{}).get('h1',0) or 0); ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
            txns=p.get('txns',{}); buys=int(txns.get('m5',{}).get('buys',0) or 0); sells=int(txns.get('m5',{}).get('sells',0) or 0); buys_h1=int(txns.get('h1',{}).get('buys',0) or 0)
            if vol_m5 < 400: continue
            if buys < 10: continue
            ratio = buys / max(1,sells)
            v_l = vol_m5 / max(1,liq) * 100
            lp=float(last_peak.get(base,10) or 10)
            st=learn.get(base,{'w':0,'l':0})
            candidates.append({"prod":f"{base}-USD","symbol":base[:12],"price":price,"c1":ch_m5,"ch1":ch_h1,"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys,"sells_m5":sells,"buys_h1":buys_h1,"ratio":ratio,"vl":v_l,"lp":lp,"st":st,"last_loss":float(last_loss.get(base,0) or 0)})
        except: continue

    # ADAPTIVE FILTER - ALWAYS FINDS 15 COINS - REAL NEW MONEY
    whales=[]
    # LEVEL 1 STRICT - BIG VOLUME REAL - LIKE YOUR WINNER FRANK 5.58% M5 64 BUYS VOL $2903
    for c in candidates:
        if c['last_loss'] and now - c['last_loss'] < 250: continue
        if c['lp']==0.0: continue
        if c['lp']>14 and now - c['last_loss'] < 500: continue
        if c['st'].get('l',0)>=3: continue
        if c['vol_m5'] < 1500: continue
        if c['buys_m5'] < 30: continue
        if c['buys_h1'] < 60: continue
        if not (1.0 <= c['c1'] <= 8.0): continue
        if not (2 <= c['ch1'] <= 50): continue
        if c['ratio'] < 1.4: continue
        if not (0.8 <= c['vl'] <= 13): continue
        score = c['c1'] * c['buys_m5'] * c['vl'] * 0.8 + c['vol_m5']*0.2
        if 1.8 <= c['c1'] <= 5.5: score*=3.0
        if 4 <= c['ch1'] <= 30: score*=2.2
        if c['st'].get('w',0)>0: score*=6.0
        if c['vol_m5']>=4000: score*=1.4
        c['score']=score
        whales.append(c)

    # LEVEL 2 RELAXED - IF <8 FOUND, RELAX TO FIND BIG VOLUME AT DEAD HOUR 11:33pm
    if len(whales)<8:
        for c in candidates:
            if c in whales: continue
            if c['last_loss'] and now - c['last_loss'] < 180: continue
            if c['lp']==0.0: continue
            if c['st'].get('l',0)>=3: continue
            if c['vol_m5'] < 800: continue
            if c['buys_m5'] < 20: continue
            if not (0.7 <= c['c1'] <= 12): continue
            if not (-3 <= c['ch1'] <= 70): continue
            if c['ratio'] < 1.2: continue
            if not (0.6 <= c['vl'] <= 18): continue
            score = c['c1'] * c['buys_m5'] * c['vl'] * 0.5 + c['vol_m5']*0.12
            if c['st'].get('w',0)>0: score*=4.0
            if c['c1']>0: score=abs(score)
            else: score*=0.3
            c['score']=score
            whales.append(c)

    # LEVEL 3 LOOSEST - IF STILL <5, TAKE ANY BIG VOLUME - ALWAYS SOMETHING TRADING
    if len(whales)<5:
        for c in candidates:
            if c in whales: continue
            if c['vol_m5'] < 500: continue
            if c['buys_m5'] < 12: continue
            if abs(c['c1'])>20: continue
            if c['ratio'] < 1.0: continue
            score = abs(c['c1']) * c['buys_m5'] + c['vol_m5']*0.1
            if c['st'].get('w',0)>0: score*=2.0
            c['score']=score
            whales.append(c)

    whales.sort(key=lambda x: x['score'], reverse=True)
    return whales[:30]

def get_price(cg_id,last=0):
    try:
        if len(cg_id)>30:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}", timeout=5).json()
            pair=r.get('pair')
            if pair and pair.get('priceUsd'):
                p=float(pair['priceUsd'])
                if p>0 and last>0 and abs(p-last)/last*100 < 40:
                    return p,"DEX"
                elif p>0 and last==0:
                    return p,"DEX"
    except: pass
    return last,"LAST"

def do_tick():
    data=rget()
    cap=float(data.get("FUND_CAP") or 1000.0); open_t=data.get("FUND_OPEN") or []; closed=data.get("FUND_CLOSED") or []
    wins=data.get("FUND_WINS") or 0; losses=data.get("FUND_LOSSES") or 0
    daily=float(data.get("FUND_DAILY_PNL") or 0); dg=float(data.get("FUND_DAILY_GROSS") or 0); df=float(data.get("FUND_DAILY_FEE") or 0)
    learn=data.get("LEARN_STATS") or {}; last_loss=data.get("LAST_LOSS_TIME") or {}; last_peak=data.get("LAST_LOSS_PEAK") or {}; blacklist=data.get("BLACKLIST") or {}; fast_whale=data.get("FAST_WHALE") or []
    rotate_last=float(data.get("ROTATE_LAST") or 0); rotate_coins=data.get("ROTATE_COINS") or []
    now=time.time()
    if now - float(data.get("FAST_LAST") or 0) > 8:
        w=scan_adaptive_big_volume()
        if w:
            fast_whale=w
            data["FAST_WHALE"]=w
            data["FAST_LAST"]=now
            data["BLACKLIST"]=blacklist
            if now - rotate_last > 300 or len(rotate_coins)==0:
                top15 = w[:15]
                rotate_coins = [{"symbol":x['symbol'],"cg_id":x['cg_id'],"price":x['price'],"c1":x['c1'],"ch1":x['ch1'],"score":x.get('score',0),"vol":x['vol_m5'],"buys":x['buys_m5']} for x in top15]
                data["ROTATE_COINS"]=rotate_coins
                data["ROTATE_LAST"]=now
                rotate_last=now
            # If still 0 coins, force rotate with whatever we have
            if len(rotate_coins)==0 and len(w)>=3:
                top15 = w[:15]
                rotate_coins = [{"symbol":x['symbol'],"cg_id":x['cg_id'],"price":x['price'],"c1":x['c1'],"ch1":x['ch1'],"score":x.get('score',0),"vol":x['vol_m5'],"buys":x['buys_m5']} for x in top15]
                data["ROTATE_COINS"]=rotate_coins
                data["ROTATE_LAST"]=now
                rotate_last=now
    base_pos=20.0
    if cap>=1015: base_pos=22.0
    if cap>=1050: base_pos=28.0
    new_open=[]
    for tr in open_t:
        try:
            sym=tr.get('symbol','?'); entry=float(tr.get('entry',0) or 0); last=float(tr.get('last_price',entry) or entry); pos=float(tr.get('pos',base_pos) or base_pos); cg_id=tr.get('cg_id','')
            peak=float(tr.get('peak_pct',0) or 0); hh=int(tr.get('hh',0) or 0); start=float(tr.get('ts',now) or now)
            if entry==0: continue
            cur,src=get_price(cg_id,last)
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
            elif peak>=3.0 and pct <= peak + trail: close=True
            elif age>=200 and peak<1.0: close=True
            elif age>=110 and peak<0.4: close=True
            elif pct<=-2.8: close=True
            elif age>=70 and pct==0 and peak==0: close=True
            if close:
                closed.append({"symbol":sym,"prod":tr.get('prod',sym),"side":"LONG","entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":f"ADAPT 15COIN HH {hh} {pct:.1f}% PEAK {peak:.1f}% AGE {int(age)}s SRC {src}","ts":now,"is_meme":False,"pos":pos,"hh":hh})
                if len(closed)>500: closed=closed[-500:]
                if net>=0.15: wins+=1
                else: losses+=1
                last_loss[sym]=now+300
                last_peak[sym]=peak
                st=learn.get(sym,{'w':0,'l':0}); st['w' if net>=0.15 else 'l']=st.get('w' if net>=0.15 else 'l',0)+1; learn[sym]=st
                if st.get('l',0)>=3: blacklist[sym]=now
                daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)
    if daily >= DAILY_GOAL or daily <= DAILY_STOP:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak,"BLACKLIST":blacklist})
        rset(data); return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"rotate_coins":rotate_coins,"rotate_last":rotate_last,"kv":f"{'GOAL' if daily>=DAILY_GOAL else 'STOP'} ${daily:.2f} ADAPT 15"}
    cnt=len(new_open)
    open_syms=set(x['symbol'] for x in new_open)
    open_ids=set(x['cg_id'] for x in new_open)
    source_coins = rotate_coins if len(rotate_coins)>=2 else fast_whale[:15]
    idx=0
    while cnt<5 and idx<len(source_coins):
        try:
            m=source_coins[idx]; idx+=1
            sym=m['symbol'] if isinstance(m,dict) and 'symbol' in m else m.get('symbol')
            cg_id=m['cg_id'] if isinstance(m,dict) and 'cg_id' in m else m.get('cg_id')
            if not sym or not cg_id: continue
            if sym in open_syms: continue
            if cg_id in open_ids: continue
            if sym in last_loss: continue
            if sym in blacklist and now - float(blacklist.get(sym,0) or 0) < 1500: continue
            full=None
            for fw in fast_whale:
                if fw['cg_id']==cg_id:
                    full=fw; break
            if not full:
                price=m.get('price',0) if isinstance(m,dict) else 0
                if price==0: continue
                full={"prod":f"{sym}-USD","symbol":sym,"price":price,"c1":m.get('c1',0),"ch1":m.get('ch1',0),"cg_id":cg_id,"fdv":0}
            pos=base_pos
            new_open.append({"symbol":sym,"prod":full['prod'],"entry":full['price'],"ts":now,"side":"LONG","reason":f"ADAPT 15COIN {full.get('c1',0):.1f}% M5 H1 {full.get('ch1',0):.1f}% VOL {full.get('vol_m5',0):.0f}","target":6.0,"stop":2.8,"last_price":full['price'],"pos":pos,"c1":full.get('c1',0),"cg_id":cg_id,"is_meme":False,"fdv":full.get('fdv',0),"peak_pct":0,"hh":0,"tier":"ADAPT 15"})
            open_syms.add(sym); open_ids.add(cg_id); cnt+=1
        except: continue
    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak,"BLACKLIST":blacklist,"ROTATE_COINS":rotate_coins,"ROTATE_LAST":rotate_last})
    rset(data)
    rotate_age = int(now - rotate_last) if rotate_last>0 else 0
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"rotate_coins":rotate_coins,"rotate_last":rotate_last,"rotate_age":rotate_age,"kv":f"v608 ADAPTIVE 15COIN 5MIN STICK VOL 1500->500 BUYS 30->12 M5 1-8% ADAPT 15 COINS {rotate_age}s/300s GOAL ${DAILY_GOAL}"}

HTML_PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v608 ADAPTIVE 15</title><style>
*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}
body{background:#0a0a0a;color:#00FF88}
.top{padding:8px 10px;display:flex;justify-content:space-between;border-bottom:2px solid #FFD000;background:#000}
.top b{color:#FFD000;font-size:7px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#222}
.card{background:#000;padding:10px}
.card small{color:#888;font-size:7px}
.card b{font-size:18px;display:block;color:#fff}
button{border:none;padding:10px;width:100%;font-weight:900;cursor:pointer;font-size:10px}
button.scan{background:linear-gradient(90deg,#FFD000,#00FF88);color:#000}
button.clear{background:#FF0040;color:#fff}
.rot{background:#1a1a00;border:2px solid #FFD000;padding:4px;margin:2px 0}
</style></head><body>
<div class="top"><div><b>VENUS v608 ADAPTIVE 15 COIN - ALWAYS BIG VOLUME - ADAPTIVE VOL 1500->500 BUYS 30->12 M5 0.8-12% H1 -5-70% - 15 COINS AT A TIME STICK 5 MIN THEN NEW 15 - REAL NEW MONEY - CONTINUOUS SCAN - LEARNS GARY 151% TOP</b></div><div style="font-size:8px;color:#FFD000" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND ADAPTIVE 15 COIN - ALWAYS FINDS 15 - BIG VOLUME - REAL NEW MONEY</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">ADAPTIVE 15</small></div>
<div class="card"><small>OPEN 5/5 FROM 15 ADAPTIVE - STICK 5 MIN - BLACKLIST 3L</small><b id="open" class="green">0/5</b><small class="green" id="wr">ADAPTIVE 15</small></div>
<div class="card"><small>DAILY NET GOAL $100 STOP -$15 - ADAPTIVE 15 - REAL NEW MONEY</small><b id="daily" class="green">+$0.000</b><small id="dailySub" style="color:#666">ADAPTIVE 15</small></div>
<div class="card"><small>PERF ADAPTIVE 15 - 5 MIN STICK - BLACKLIST GARY 151% - FRANK 6.5% WINNER</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">ADAPTIVE 15</small></div>
</div>
<div class="rot"><div style="font-size:8px;color:#FFD000">ADAPTIVE ROTATING 15 COINS - STICK 5 MIN - CURRENT 15 - <span id="rotateInfo">0s/300s</span> - REAL NEW MONEY - ALWAYS FINDS 15 - VOL 1500->500 ADAPTIVE</div><div id="rotatelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #00FF88"><div style="font-size:7px;color:#00FF88">TOP 30 ADAPTIVE BIG VOLUME MARKET - ALWAYS SOMETHING TRADING BIG VOLUME - ADAPTIVE: LEVEL1 VOL 1500+ BUYS 30+ M5 1-8% H1 2-50% R>=1.4 LEVEL2 VOL 800+ BUYS 20+ M5 0.7-12% H1 -3-70% R>=1.2 LEVEL3 VOL 500+ BUYS 12+ M5 0.5-15% - ALWAYS FINDS 15 - 15 COINS AT A TIME - STICK 5 MIN - THEN NEW 15 - REAL NEW MONEY - SCAN 30 PICK 15 - CONTINUOUS SCAN 8s - ROTATE 300s</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>5 TRADES FROM 15 ADAPTIVE - STICK 5 MIN - REAL NEW MONEY - NO 5x SAME</span><span>SIDE</span><span>ENTRY PEAK HH TRAIL NET</span><span>TP/SL NET AGE</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN ADAPTIVE 15 COIN - ALWAYS BIG VOLUME - ADAPTIVE VOL 1500->500 BUYS 30->12 - ALWAYS FINDS 15 - 15 AT A TIME STICK 5 MIN THEN NEW 15 - VOL 1500+ BUYS 30+ M5 1-8% H1 2-45% - 15 COINS - 5MIN ROTATE - $100 GOAL -$15 STOP - REAL NEW MONEY - CONTINUOUS SCAN - 15 AT A TIME - 5 MIN STICK - THEN NEW COIN - FEEL MOVEMENT TRADE BIG VOLUME</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN ADAPTIVE 15 - KEEPS LEARN + BLACKLIST + ROTATE - FEE 0.2% TP 6% SL 2.8% 15 COINS 5 MIN STICK REAL NEW MONEY - ALWAYS FINDS 15</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#FFD000;margin-bottom:3px">CLOSED LAST 50 - ADAPTIVE 15 COIN ROTATE - STICK 5 MIN - REAL NEW MONEY - 15 AT A TIME - 5 MIN ROTATE - ALWAYS BIG VOLUME - ADAPTIVE - ALWAYS FINDS 15</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / PEAK HH AGE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2)+' POS $'+(j.open_trades&&j.open_trades[0]?Number(j.open_trades[0].pos||20).toFixed(2):'20');
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' ADAPTIVE '+j.rotate_coins.length+' COINS '+j.rotate_age+'s/300s';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/5 FROM 15 ADAPTIVE '+j.rotate_coins.length+' COINS '+j.rotate_age+'s/300s VOL 1500->500 BUYS 30->12 ADAPTIVE FEE $0.040 TP 6% SL 2.8% TRAIL HH';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L KV '+(j.kv||'1 CMD')+' ADAPTIVE 15COIN '+j.rotate_age+'s/300s BIG VOLUME REAL NEW MONEY';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#FFD000':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $100 STOP -$15 POS $'+(j.open_trades&&j.open_trades[0]?Number(j.open_trades[0].pos||20).toFixed(2):'20')+' ADAPTIVE '+j.rotate_age+'s/300s';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' POS $'+(j.open_trades&&j.open_trades[0]?Number(j.open_trades[0].pos||20).toFixed(2):'20')+' ADAPTIVE 15COIN '+j.rotate_age+'s/300s '+j.rotate_coins.length+' COINS';
 document.getElementById('rotateInfo').innerText=j.rotate_age+'s/300s - '+j.rotate_coins.length+' COINS - NEXT ROTATE IN '+(300-j.rotate_age)+'s - ADAPTIVE - ALWAYS FINDS 15 - VOL 1500->500';
 let rl=document.getElementById('rotatelist'); rl.innerHTML='';
 (j.rotate_coins||[]).forEach((m,i)=>{ rl.innerHTML+=`<div style="border:1px solid #FFD000;padding:2px 4px;font-size:7px;color:#FFD000">#${i+1} ${m.symbol} ${Number(m.c1||0).toFixed(2)}% M5 H1 ${Number(m.ch1||0).toFixed(2)}% VOL $${Number(m.vol||0).toFixed(0)} ${m.buys} BUYS<br><span style="color:#00FF88">ADAPTIVE 15COIN ${m.score?Number(m.score).toFixed(0):''} STICK ${j.rotate_age}s</span></div>`; });
 if((j.rotate_coins||[]).length==0) rl.innerHTML='<div style="font-size:7px;color:#666">Loading ADAPTIVE 15 COINS - ALWAYS FINDS 15 - ADAPTIVE VOL 1500->500 BUYS 30->12 - 15 AT A TIME - STICK 5 MIN - THEN NEW 15 - REAL NEW MONEY...</div>';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).slice(0,30).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid ${m.wins>0?'#FFD000':'#00FF88'};padding:2px 4px;font-size:7px;color:${m.wins>0?'#FFD000':'#00FF88'}">#${i+1} ${m.symbol} ${Number(m.c1||0).toFixed(2)}% M5 H1 ${Number(m.ch1||0).toFixed(2)}% $${Number(m.price||0).toFixed(8)} R ${Number(m.ratio||0).toFixed(1)} V/L ${Number(m.vl||0).toFixed(1)}% VOL $${Number(m.vol_m5||0).toFixed(0)}<br><span style="color:#FFD000">ADAPTIVE ${m.buys_m5} BUYS ${m.sells_m5} SELLS BUYS H1 ${m.buys_h1||0} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)} ${m.tier||'ADAPT'}</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">Scanning ADAPTIVE BIG VOLUME MARKET - ALWAYS SOMETHING TRADING BIG VOLUME - ADAPTIVE VOL 1500->500 BUYS 30->12 - ALWAYS FINDS 15 - 15 COINS AT A TIME - STICK 5 MIN - THEN NEW 15 - REAL NEW MONEY - LEVEL1 VOL 1500+ BUYS 30+ LEVEL2 VOL 800+ BUYS 20+ LEVEL3 VOL 500+ BUYS 12+</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||20); let fee=pos*0.002; let target=6.0; let netEst=pos*target/100 - fee; let peak=Number(t.peak_pct||0); let hh=Number(t.hh||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:#FFD000">${t.symbol||''}</b> <small style="color:#00FF88">$${pos.toFixed(2)} HH ${hh} ADAPT ${j.rotate_age}s</small></span><span><b style="color:#00FF88;border:1px solid #00FF88;padding:1px 3px;font-size:7px">LONG</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos.toFixed(2)} $${fee.toFixed(3)} PEAK ${peak.toFixed(1)}% HH ${hh} ADAPT</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,90)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} PEAK ${peak.toFixed(1)}% HH ${hh} ADAPT ${j.rotate_age}s</small></span><span style="font-size:7px"><span style="color:#00FF88">TP 6% $${(pos*0.06).toFixed(2)}</span><br><span style="color:#FF0040">SL 2.8% $${(pos*0.028).toFixed(2)}</span><br><small style="color:#FFD000">NET $${netEst.toFixed(2)} PEAK ${peak.toFixed(1)}% HH ${hh} ADAPT</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#FFD000;padding:10px;font-size:10px">No open - ADAPTIVE 15 COIN will fill 5/5 FROM 15 - STICK 5 MIN - REAL NEW MONEY - ALWAYS FINDS 15 - ADAPTIVE VOL 1500->500 - 1 CMD</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-50).reverse().forEach(c=>{
   let col=c.net>=0.15?'#FFD000':'#FF0040';
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000"><b style="color:${c.net>=0.15?'#FFD000':'#FF00FF'}">${c.symbol||''}</b><br><small style="color:${c.net>=0.15?'#FFD000':'#FF00FF'}">LONG $${Number(c.pos||20).toFixed(2)} HH ${Number(c.hh||0)} ${c.net>=0.15?'WINNER ADAPT':'LOSER ADAPT'}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:${c.net>=0.15?'#FFD000':'#FF00FF'};border:1px solid ${c.net>=0.15?'#FFD000':'#FF00FF'};padding:1px 3px;font-size:7px">LONG</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}% PEAK ${Number(c.peak||0).toFixed(1)}% HH ${Number(c.hh||0)} AGE ${c.reason.match(/AGE (\\d+)s/)?c.reason.match(/AGE (\\d+)s/)[1]:''}s</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)} ADAPT HH ${Number(c.hh||0)}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,200)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% PEAK ${Number(c.peak||0).toFixed(1)}% HH ${Number(c.hh||0)} ADAPT</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FFD000;padding:10px">Scanning ADAPTIVE 15 COIN - ALWAYS BIG VOLUME - ALWAYS FINDS 15 - ADAPTIVE VOL 1500->500 - 15 AT A TIME - STICK 5 MIN - THEN NEW 15 - REAL NEW MONEY...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR ADAPTIVE 15 - KEEPS LEARN + BLACKLIST + ROTATE?')) return; await fetch('/api/clear_closed_fake'); await load(); }
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
    data=rget()
    return jsonify({"cap":data.get("FUND_CAP",1000),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",0),"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":data.get("FAST_WHALE",[]),"rotate_coins":data.get("ROTATE_COINS",[]),"rotate_age":int(time.time()-float(data.get("ROTATE_LAST",0) or 0)) if data.get("ROTATE_LAST") else 0,"kv":f"v608 ADAPTIVE 15COIN 5MIN STICK VOL 1500->500 BUYS 30->12 ADAPT ALWAYS FINDS 15 GOAL ${DAILY_GOAL}"})
@app.route("/api/cron")
def cron(): return jsonify(do_tick())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["LAST_LOSS_PEAK"]={}
    rset(data); data["_last_save"]=0; rset(data)
    return jsonify({"cleared":True})
