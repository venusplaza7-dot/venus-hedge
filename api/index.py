from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)
UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
SINGLE_KEY = "VENUS_V570_DATA"
DAILY_GOAL = 300.0
DAILY_STOP = -80.0
CACHE = {"data": None, "ts": 0}

def rget_single():
    global CACHE
    now=time.time()
    if CACHE["data"] and now - CACHE["ts"] < 30:
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
        if time.time()-last < 15: return
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
                    for it in r[:40]:
                        if it.get('chainId')=='solana':
                            tk=it.get('tokenAddress')
                            if tk:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=5).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:2])
            except: continue
        for q in ["BONK","WIF","PEPE","PUMP","FLOKI","SNDWITCH","RARINU","A1","CATCRAFT","PUMPOWEEN","ECSTASY","CHONK","VIBE","MINER"]:
            try:
                sr=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=6).json()
                if sr.get('pairs'): all_pairs.extend(sr['pairs'][:10])
            except: pass
        seen=set()
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
                if not (60000 <= liq <= 350000): continue
                if not (200000 <= fdv <= 2500000): continue
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
                txns=p.get('txns',{}); buys=int(txns.get('m5',{}).get('buys',0) or 0); sells=int(txns.get('m5',{}).get('sells',0) or 0)
                if not (1500 <= vol_m5 <= 12000): continue
                if buys < 40: continue
                if buys <= sells: continue
                if ch_24 < -90: continue
                if not (0.3 <= ch_m5 <= 4.5): continue
                score=buys*1000 + vol_m5*1.5
                if 0.8 <= ch_m5 <= 3.0: score*=2.0
                whales.append({"prod":f"{base}-USD","symbol":base[:12],"price":price,"c1":ch_m5,"c24":ch_24,"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys,"sells_m5":sells,"score":score})
            except: continue
        whales.sort(key=lambda x: x['score'], reverse=True)
        return whales[:25]
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
    if now - float(data.get("FAST_LAST") or 0) > 6:
        w=get_meme_whales_25()
        if w: fast_whale=w; data["FAST_WHALE"]=w; data["FAST_LAST"]=now

    new_open=[]
    for tr in open_t:
        try:
            sym=tr.get('symbol','?'); entry=float(tr.get('entry',0) or 0); last=float(tr.get('last_price',entry) or entry); pos=float(tr.get('pos',15) or 15); cg_id=tr.get('cg_id','')
            peak=float(tr.get('peak_pct',0) or 0)
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
            if pct<=-5.0: close=True; rs=f"LOSS SHARK LOOSE SL {pct:.2f}% <=-5% NET ${net:.3f} PEAK {peak:.1f}% SHARK LOOSE 15/60s"
            elif peak>=13.5 and age>=10 and pct <= peak - 0.8: close=True; rs=f"WIN SHARK LOOSE LOCK $2+ TRAIL -0.8% POCKET {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} EXTRA ${net-2:.2f} SHARK"
            elif peak>=13.5 and age>=10 and age>=240: close=True; rs=f"WIN SHARK LOOSE LOCK $2 TIME 240s {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} SHARK"
            elif age>=240 and peak<5.0: close=True; rs=f"TIME 240s SHARK PEAK {peak:.1f}% {pct:.2f}% NET ${net:.3f} NO PUMP CUT"
            elif age>=600: close=True; rs=f"TIME 600s SHARK {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} MAX"
            if close:
                closed.append({"symbol":sym,"prod":tr.get('prod',sym),"side":"LONG","entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":rs,"ts":now,"is_meme":True,"pos":pos})
                if len(closed)>400: closed=closed[-400:]
                if net>=0.3: wins+=1
                else: losses+=1; last_loss[sym]=now; last_peak[sym]=peak
                st=learn.get(sym,{'w':0,'l':0}); st['w' if net>=0.3 else 'l']=st.get('w' if net>=0.3 else 'l',0)+1; learn[sym]=st
                daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)

    if daily >= DAILY_GOAL or daily <= DAILY_STOP:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak})
        rset_single(data); return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"{'GOAL' if daily>=DAILY_GOAL else 'STOP'} ${daily:.2f} SHARK LOOSE"}

    cnt=len(new_open); idx=0
    open_syms=set(x['symbol'] for x in new_open)
    open_ids=set(x['cg_id'] for x in new_open)
    while cnt<12 and idx<len(fast_whale):
        try:
            m=fast_whale[idx]; idx+=1; sym=m['symbol']
            if sym in open_syms: continue
            if m['cg_id'] in open_ids: continue
            if sym in last_loss:
                pk=float(last_peak.get(sym,0) or 0)
                cd=15 if pk>=8 else 60
                if now-float(last_loss.get(sym,0) or 0) < cd: continue
            pos=15.0
            reason=f"SHARK LOOSE $15 x12 LOCK $2 10s TRAIL -0.8% LOSS $0.75 SHARK {m['buys_m5']} BUYS {m['sells_m5']} SELLS VOL M5 ${m['vol_m5']:.0f} LIQ ${m['liq']:.0f} FDV ${m['fdv']:.0f} {m['c1']:.1f}% M5 BEFORE PUMP SHARK MARK LOOSE"
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":now,"side":"LONG","reason":reason,"target":13.5,"stop":5.0,"last_price":m['price'],"pos":pos,"c1":m['c1'],"c24":m['c24'],"cg_id":m['cg_id'],"is_meme":True,"fdv":m['fdv'],"peak_pct":0})
            open_syms.add(sym); open_ids.add(m['cg_id']); cnt+=1
        except: continue

    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss,"LAST_LOSS_PEAK":last_peak})
    rset_single(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"v578 SHARK LOOSE 0.3-4.5% M5 BUYS 40+ VOL 1.5k-12k LIQ 60k+ FDV 200k-2.5M LOCK $2 10s TRAIL -0.8% LOSS $0.75 12/12"}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v578 SHARK LOOSE TRADING</title><style>
*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}
body{background:#0a0a0a;color:#00FF88}
.top{padding:8px 10px;display:flex;justify-content:space-between;border-bottom:2px solid #00FF88;background:#000}
.top b{color:#00FF88;font-size:8px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#222}
.card{background:#000;padding:10px}
.card small{color:#888;font-size:7px}
.card b{font-size:18px;display:block;color:#fff}
.card b.green{color:#00FF88}
.card b.red{color:#FF0040}
button{border:none;padding:10px;width:100%;font-weight:900;cursor:pointer;font-size:10px}
button.scan{background:linear-gradient(90deg,#00FF88,#FF00FF);color:#000}
button.clear{background:#FF0040;color:#fff}
</style></head><body>
<div class="top"><div><b>VENUS v578 SHARK LOOSE TRADING 0.3-4.5% M5 BUYS 40+ VOL 1.5k-12k LIQ 60k+ BEFORE PUMP</b> <span style="color:#888;font-size:6px">SHARK LOOSE TRADING NOW</span></div><div style="font-size:8px;color:#00FF88" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND REAL $15 x12 SHARK LOOSE 0.3-4.5% BUYS 40+ VOL 1.5k-12k - FEE $0.36 TRADING</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">SHARK LOOSE TRADING NOW</small></div>
<div class="card"><small>OPEN 12/12 SHARK LOOSE 0.3-4.5% M5 BUYS 40+ VOL 1.5k-12k LIQ 60k+ TRADING</small><b id="open" class="green">0/12</b><small class="green" id="wr">SHARK LOOSE 0.3-4.5% M5 BEFORE PUMP TRADING NOW</small></div>
<div class="card"><small>DAILY GROSS - FEE = NET - GOAL $300 STOP -$80 LOCK $2/$0.75 SHARK LOOSE</small><b id="daily" class="green">+$0.00</b><small id="dailySub" style="color:#666">SHARK LOOSE TRADING</small></div>
<div class="card"><small>PERFORMANCE - $15 x12 SHARK LOOSE LOCK $2 TRAIL -0.8% TRADING</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">SHARK LOOSE 0.3-4.5% M5 BUYS 40+ VOL 1.5k-12k LIQ 60k+ FDV 200k-2.5M TRADING NOW</small></div>
</div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #FF00FF"><div style="font-size:7px;color:#FF00FF">TOP 25 SHARK LOOSE TRADING - $15 x12 LOCK $2 10s TRAIL -0.8% LOSS $0.75 ADAPT 15/60s - 0.3-4.5% M5 BUYS 40+ VOL 1.5k-12k LIQ 60k+ FDV 200k-2.5M BUYS>SELLS - 12/12 ALWAYS - FEE $0.36 - BEFORE PUMP SHARK MARK LOOSE TRADING NOW</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>12 TRADES $15 x12 SHARK LOOSE 0.3-4.5% M5 BUYS 40+ VOL 1.5k-12k - BEFORE PUMP TRADING NOW</span><span>SIDE</span><span>ENTRY FEE PEAK</span><span>TICK TP/SL NET PEAK SHARK</span><span>TP/SL NET SHARK</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN SHARK LOOSE TRADING $15 x12 0.3-4.5% M5 BUYS 40+ VOL 1.5k-12k LIQ 60k+ FDV 200k-2.5M - 25 BEST BEFORE PUMP - $300 GOAL -$80 STOP - FEE $0.36 - SHARK MARK LOOSE - 12/12 ALWAYS TRADING NOW</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN 12 TRADES $15 x12 SHARK LOOSE 0.3-4.5% M5 - KEEPS LEARN - FEE $0.36 SHARK TRADING NOW</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88;margin-bottom:3px">CLOSED LAST 50 - $15 x12 SHARK LOOSE 0.3-4.5% M5 LOCK $2 10s TRAIL -0.8% LOSS $0.75 - $300 GOAL - SHARK LOOSE TRADING NOW</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / FEE PEAK SHARK LOOSE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON - SHARK LOOSE BEFORE PUMP TRADING NOW</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2);
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' SHARK LOOSE TRADING NOW';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/12 SHARK LOOSE $15 x12 0.3-4.5% M5 BUYS 40+ VOL 1.5k-12k LIQ 60k+ FDV 200k-2.5M FEE $0.36 SHARK MARK LOOSE TRADING NOW';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L KV '+(j.kv||'1 CMD')+' SHARK LOOSE 0.3-4.5% M5 BEFORE PUMP TRADING NOW 12/12';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#00FF88':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $300 STOP -$80 SHARK LOOSE TRADING NOW';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('wlSub').innerText='WR '+wr+'% - SHARK LOOSE 0.3-4.5% M5 BUYS 40+ VOL 1.5k-12k LIQ 60k+ FDV 200k-2.5M BUYS>SELLS SHARK MARK LOOSE TRADING NOW 12/12 GOAL $300';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' SHARK LOOSE TRADING NOW 0.3-4.5% M5 BEFORE PUMP';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid #FF00FF;padding:2px 4px;font-size:7px;color:#FF00FF">#${i+1} ${m.symbol} ${Number(m.c1).toFixed(1)}% M5 $${Number(m.price).toFixed(8)}<br><span style="color:#FFD000">SHARK LOOSE ${m.buys_m5} BUYS ${m.sells_m5} SELLS VOL $${Number(m.vol_m5||0).toFixed(0)} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)} BEFORE PUMP TRADING</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">Scanning SHARK LOOSE 0.3-4.5% M5 BEFORE PUMP TRADING NOW - looking for shark mark loose</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||15); let fee=pos*0.002; let target=13.5; let netEst=pos*target/100 - fee; let peak=Number(t.peak_pct||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:#FF00FF">${t.symbol||''}</b> <small style="color:#FF00FF">$15 SHARK LOOSE</small></span><span><b style="color:#FF00FF;border:1px solid #FF00FF;padding:1px 3px;font-size:7px">LONG</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos} $${fee.toFixed(3)} PEAK ${peak.toFixed(1)}% SHARK LOOSE</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,90)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} PEAK ${peak.toFixed(1)}% TRAIL -0.8% SHARK</small></span><span style="font-size:7px"><span style="color:#FF00FF">TP 13.5% $2</span><br><span style="color:#FF0040">SL 5% $0.75</span><br><small style="color:#FFD000">NET $${netEst.toFixed(2)} PEAK ${peak.toFixed(1)}% SHARK LOOSE</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#00FF88;padding:10px;font-size:10px">No open - SHARK LOOSE 0.3-4.5% M5 BEFORE PUMP TRADING NOW will fill 12/12 when shark mark loose appears - 1 CMD</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-50).reverse().forEach(c=>{
   let col=c.net>=0.3?'#00FF88':'#FF0040';
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#00FF88"><b style="color:#FF00FF">${c.symbol||''}</b><br><small style="color:#FF00FF">LONG $${c.pos||15} SHARK LOOSE</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:#FF00FF;border:1px solid #FF00FF;padding:1px 3px;font-size:7px">LONG</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}% PEAK ${Number(c.peak||0).toFixed(1)}%</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)} SHARK LOOSE</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,200)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% PEAK ${Number(c.peak||0).toFixed(1)}% SHARK LOOSE</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FF00FF;padding:10px">Scanning SHARK LOOSE TRADING NOW 0.3-4.5% M5 BEFORE PUMP - looking for shark mark loose...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR SHARK LOOSE TRADING NOW - KEEPS LEARN?')) return; await fetch('/api/clear_closed_fake'); await load(); }
setInterval(load,5000);load();
</script></body></html>
"""
@app.route("/")
def home(): return HTML
@app.route("/api/state")
def state():
    try: do_tick()
    except Exception as e: print(f"tick {e}")
    data=rget_single()
    return jsonify({"cap":data.get("FUND_CAP",1000),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",0),"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":data.get("FAST_WHALE",[]),"kv":f"v578 SHARK LOOSE TRADING NOW 0.3-4.5% M5 BUYS 40+ VOL 1.5k-12k LIQ 60k+ FDV 200k-2.5M LOCK $2 TRAIL -0.8% LOSS $0.75 12/12 GOAL ${DAILY_GOAL}"})
@app.route("/api/cron")
def cron(): return jsonify(do_tick())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget_single()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["LAST_LOSS_PEAK"]={}
    rset_single(data); data["_last_save"]=0; rset_single(data)
    return jsonify({"cleared":True})
