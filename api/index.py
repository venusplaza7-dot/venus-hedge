from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)
UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
SINGLE_KEY = "VENUS_V570_DATA"
DAILY_GOAL = 300.0
DAILY_STOP = -150.0
CACHE = {"data": None, "ts": 0}

def rget_single():
    global CACHE
    now=time.time()
    if CACHE["data"] and now - CACHE["ts"] < 40:
        return CACHE["data"]
    try:
        if not UP_URL or not UP_TOKEN:
            return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"FAST_WHALE":[],"FAST_LAST":0}
        r=requests.get(f"{UP_URL}/get/{SINGLE_KEY}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=5)
        v=r.json().get("result")
        if v:
            data=json.loads(v)
            CACHE["data"]=data; CACHE["ts"]=now
            return data
    except: pass
    return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"FAST_WHALE":[],"FAST_LAST":0}

def rset_single(data):
    global CACHE
    CACHE["data"]=data; CACHE["ts"]=time.time()
    try:
        if not UP_URL or not UP_TOKEN: return
        last=float(data.get("_last_save",0) or 0)
        if time.time()-last < 25: return
        data["_last_save"]=time.time()
        requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(data)], timeout=5)
    except: pass

def get_meme_whales_25():
    whales=[]
    try:
        all_pairs=[]
        for url in ["https://api.dexscreener.com/token-boosts/latest/v1","https://api.dexscreener.com/token-boosts/top/v1"]:
            try:
                r=requests.get(url, timeout=8).json()
                if isinstance(r,list):
                    for it in r[:40]:
                        if it.get('chainId')=='solana':
                            tk=it.get('tokenAddress')
                            if tk:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{tk}", timeout=7).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:2])
            except: continue
        for q in ["SOL","BONK","WIF","PEPE","PUMP","FLOKI","DOGE","SNDWITCH","ECSTASY","A1","REFLECT"]:
            try:
                sr=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=8).json()
                if sr.get('pairs'): all_pairs.extend(sr['pairs'][:15])
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
                if not (5000 <= liq <= 400000): continue
                if not (20000 <= fdv <= 3000000): continue
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
                txns=p.get('txns',{}); buys=int(txns.get('m5',{}).get('buys',0) or 0)
                if vol_m5 < 800: continue
                if buys < 1: continue
                if ch_24 < -90: continue
                if ch_m5 > 600: continue
                if ch_m5 < -70: continue
                score=vol_m5*(1+ch_m5/100)+buys*500
                if ch_m5>8: score*=1.8
                if ch_m5>15: score*=1.5
                if buys>=100: score*=1.7
                whales.append({"prod":f"{base}-USD","symbol":base[:12],"price":price,"c1":ch_m5,"c24":ch_24,"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys,"whale_usd":vol_m5*0.65,"score":score})
            except: continue
        whales.sort(key=lambda x: x['score'], reverse=True)
        return whales[:25]
    except: return []

def get_price(cg_id,last=0):
    try:
        if len(cg_id)>30:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}", timeout=5).json()
            if r.get('pair') and r['pair'].get('priceUsd'):
                p=float(r['pair']['priceUsd'])
                if p>0 and last>0 and abs(p-last)/last*100>75: return p,"JUMP FORCE"
                if p>0: return p,"DEX"
    except: pass
    return 0,"FAIL"

def do_tick():
    data=rget_single()
    cap=float(data.get("FUND_CAP") or 1000.0); open_t=data.get("FUND_OPEN") or []; closed=data.get("FUND_CLOSED") or []
    wins=data.get("FUND_WINS") or 0; losses=data.get("FUND_LOSSES") or 0
    daily=float(data.get("FUND_DAILY_PNL") or 0); dg=float(data.get("FUND_DAILY_GROSS") or 0); df=float(data.get("FUND_DAILY_FEE") or 0)
    learn=data.get("LEARN_STATS") or {}; last_loss=data.get("LAST_LOSS_TIME") or {}; fast_whale=data.get("FAST_WHALE") or []
    now=time.time()
    if now - float(data.get("FAST_LAST") or 0) > 15:
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
                    if fm.get('cg_id')==cg_id or fm.get('symbol')==sym:
                        cur=fm['price']; src="FAST"; break
            if cur==0:
                tr['last_price']=last; new_open.append(tr); continue
            age=now-float(tr.get('ts',now) or now); pct=(cur-entry)/entry*100; fee=pos*0.002; gross=pos*pct/100; net=gross-fee
            # track peak for trailing
            if pct > peak: peak=pct; tr['peak_pct']=peak
            close=False; rs=""
            # LOCK LOGIC: LOSS $1 = SL 6.6% and WIN $2 LOCK 10 sec + TRAIL
            if "FORCE" in src: close=True; rs=f"FORCE {pct:.2f}% NET ${net:.3f} PEAK {peak:.1f}%"
            elif pct<=-6.6: close=True; rs=f"REAL LOSS LOCK $1 SL {pct:.2f}% <=-6.6% NET ${net:.3f} LOCK $1 IMMEDIATE 60s PEAK {peak:.1f}%"
            elif peak>=13.5 and age>=10 and pct <= peak - 2.0: close=True; rs=f"REAL WIN LOCK $2+ TRAIL POCKET {pct:.2f}% PEAK {peak:.1f}% TRAIL -2% NET ${net:.3f} LOCK $2 10s POCKET ${net-2:.2f} EXTRA"
            elif pct>=13.5 and age>=10 and age>=180: close=True; rs=f"REAL WIN LOCK $2 TIME 180s {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} LOCK $2 10s"
            elif pct>=13.5 and age>=10: # hold for trail, don't close yet unless trail hits, but also lock $2 after 10s if no higher
                # if age > 600 and still >=13.5% lock $2
                if age>=600: close=True; rs=f"REAL WIN LOCK $2 TIME 600s {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} LOCK $2"
                else: tr['last_price']=cur; new_open.append(tr); continue
            elif age>=1800 and pct>=2.0 and net>=0.5: close=True; rs=f"WIN TIME {age:.0f}s {pct:.2f}% PEAK {peak:.1f}% NET ${net:.3f} LOCK"
            elif age>=1800 and pct<0: close=True; rs=f"LOSS TIME {age:.0f}s {pct:.2f}% NET ${net:.3f} LOCK $1"
            if close:
                closed.append({"symbol":sym,"prod":tr.get('prod',sym),"side":"LONG","entry":entry,"exit":cur,"pct":pct,"peak":peak,"gross":gross,"fee":fee,"net":net,"reason":rs,"ts":now,"is_meme":True,"pos":pos})
                if len(closed)>500: closed=closed[-500:]
                if net>=0.5: wins+=1
                else: losses+=1
                st=learn.get(sym,{'w':0,'l':0});
                if net>=0.5: st['w']=st.get('w',0)+1
                else: st['l']=st.get('l',0)+1; last_loss[sym]=now
                learn[sym]=st; daily+=net; dg+=gross; df+=fee; cap+=net
            else:
                tr['last_price']=cur; new_open.append(tr)
        except: new_open.append(tr)

    if daily >= DAILY_GOAL:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss})
        rset_single(data); return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"GOAL HIT ${daily:.2f} >=${DAILY_GOAL} LOCK $2/$1"}
    if daily <= DAILY_STOP:
        data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss})
        rset_single(data); return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"STOP LOSS ${daily:.2f} <=${DAILY_STOP} LOCK $1"}

    cnt=len([x for x in new_open if x.get('is_meme')]); idx=0
    while cnt<20 and idx<len(fast_whale):
        try:
            m=fast_whale[idx]; idx+=1; sym=m['symbol']
            if any(x['symbol']==sym for x in new_open): continue
            if any(x.get('cg_id')==m['cg_id'] for x in new_open): continue
            if sym in last_loss and now-float(last_loss.get(sym,0) or 0)<60: continue
            if m['fdv']<20000 or m['fdv']>3000000: continue
            if m['liq']<5000: continue
            pos=15.0
            reason=f"SHARK $15 x20 LOCK $2 10s TRAIL POCKET LOSS $1 WHALE {m['buys_m5']} BUYS VOL M5 ${m['vol_m5']:.0f} WHALE ${m['whale_usd']:.0f} FDV ${m['fdv']:.0f} LIQ ${m['liq']:.0f} {m['c1']:.1f}% M5 LOCK $2 10s POCKET TRAIL -2% $1 LOSS"
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":now,"side":"LONG","reason":reason,"target":13.5,"stop":6.6,"last_price":m['price'],"pos":pos,"c1":m['c1'],"c24":m['c24'],"cg_id":m['cg_id'],"is_meme":True,"whale_usd":m['whale_usd'],"fdv":m['fdv'],"peak_pct":0})
            cnt+=1
        except: continue

    data.update({"FUND_CAP":cap,"FUND_OPEN":new_open,"FUND_CLOSED":closed,"FUND_WINS":wins,"FUND_LOSSES":losses,"FUND_DAILY_PNL":daily,"FUND_DAILY_GROSS":dg,"FUND_DAILY_FEE":df,"LEARN_STATS":learn,"LAST_LOSS_TIME":last_loss})
    rset_single(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"kv":f"v573.3 LOCK $2 10s TRAIL POCKET LOSS $1 20/20 GOAL ${DAILY_GOAL} STOP ${DAILY_STOP}"}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v573.3 LOCK $2 TRAIL $1 LOSS</title><style>
*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}
body{background:#0a0a0a;color:#00FF88}
.top{padding:8px 10px;display:flex;justify-content:space-between;border-bottom:2px solid #00FF88;background:#000}
.top b{color:#00FF88;font-size:9px}
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
<div class="top"><div><b>VENUS v573.3 LOCK $2 10s TRAIL POCKET + LOSS $1 - $15 x20 - $300 GOAL -$150 STOP</b> <span style="color:#888;font-size:7px">LOCK $2 TRAIL POCKET $1 LOSS</span></div><div style="font-size:8px;color:#00FF88" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND REAL $15 x20 LOCK $2 TRAIL $1 LOSS - FEE $0.60</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">LOCK $2 TRAIL $1</small></div>
<div class="card"><small>OPEN 20/20 WHALE $15 x20 LOCK $2 TRAIL $1 LOSS</small><b id="open" class="green">0/20</b><small class="green" id="wr">LOCK $2 10s TRAIL POCKET LOSS $1</small></div>
<div class="card"><small>DAILY GROSS - FEE = NET - GOAL $300 STOP -$150 LOCK $2/$1</small><b id="daily" class="green">+$0.00</b><small id="dailySub" style="color:#666">LOCK $2 TRAIL</small></div>
<div class="card"><small>PERFORMANCE - $15 x20 LOCK $2 TRAIL $1 LOSS</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">LOCK $2 10s TRAIL -2% LOSS $1</small></div>
</div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #FF00FF"><div style="font-size:7px;color:#FF00FF">TOP 25 WHALE MEME - $15 x20 LOCK $2 10s TRAIL POCKET LOSS $1 - VOL $800+ - 20/20 ALWAYS - FEE $0.60 - PEAK TRACK</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>20 TRADES $15 x20 LOCK $2 10s TRAIL POCKET LOSS $1 - PEAK TRACK</span><span>SIDE</span><span>ENTRY FEE PEAK</span><span>TICK TP/SL NET PEAK</span><span>TP/SL NET</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN $15 x20 LOCK $2 10s TRAIL POCKET LOSS $1 - 25 BEST POOL - $300 GOAL -$150 STOP - FEE $0.60 - 1 CMD - 20/20 ALWAYS</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN 20 TRADES $15 x20 LOCK $2 TRAIL $1 - KEEPS LEARN - FEE $0.60 - 1 CMD</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88;margin-bottom:3px">CLOSED LAST 50 - $15 x20 LOCK $2 10s TRAIL POCKET LOSS $1 - $300 GOAL</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / FEE PEAK</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON - LOCK $2 TRAIL POCKET $1 LOSS - 1 CMD</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2);
 document.getElementById('capSub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' LOCK $2 TRAIL $1';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/20 WHALE $15 x20 LOCK $2 TRAIL $1 LOSS FEE $0.60';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L KV '+(j.kv||'1 CMD')+' LOCK $2 TRAIL LOSS $1 20/20';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#00FF88':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $300 STOP -$150 LOCK $2/$1';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('wlSub').innerText='WR '+wr+'% - LOCK $2 10s TRAIL -2% POCKET LOSS $1 $15 x20 20/20 GOAL $300';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' LOCK $2 TRAIL LOSS $1 GOAL $300';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid #FF00FF;padding:2px 4px;font-size:7px;color:#FF00FF">#${i+1} ${m.symbol} ${Number(m.c1).toFixed(1)}% M5 $${Number(m.price).toFixed(8)}<br><span style="color:#FFD000">WHALE $${Number(m.whale_usd||0).toFixed(0)} ${m.buys_m5} BUYS VOL $${Number(m.vol_m5||0).toFixed(0)} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)} LOCK $2/$1</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">Scanning 25 best - LOCK $2 TRAIL $1</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||15); let fee=pos*0.002; let target=13.5; let netEst=pos*target/100 - fee; let peak=Number(t.peak_pct||0);
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 120px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:#FF00FF">${t.symbol||''}</b> <small style="color:#FF00FF">$15 LOCK $2/$1</small></span><span><b style="color:#FF00FF;border:1px solid #FF00FF;padding:1px 3px;font-size:7px">LONG</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos} $${fee.toFixed(3)} PEAK ${peak.toFixed(1)}%</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,90)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} PEAK ${peak.toFixed(1)}% TRAIL -2%</small></span><span style="font-size:7px"><span style="color:#FF00FF">TP 13.5% $2</span><br><span style="color:#FF0040">SL 6.6% $1</span><br><small style="color:#FFD000">NET $${netEst.toFixed(2)} PEAK ${peak.toFixed(1)}%</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#00FF88;padding:10px;font-size:10px">No open - LOCK $2 TRAIL $1 will fill 20/20 - 1 CMD</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-50).reverse().forEach(c=>{
   let col=c.net>=0.5?'#00FF88':'#FF0040';
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#00FF88"><b style="color:#FF00FF">${c.symbol||''}</b><br><small style="color:#FF00FF">LONG $15 LOCK $2/$1</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:#FF00FF;border:1px solid #FF00FF;padding:1px 3px;font-size:7px">LONG</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}% PEAK ${Number(c.peak||0).toFixed(1)}%</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,200)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% PEAK ${Number(c.peak||0).toFixed(1)}%</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FF00FF;padding:10px">Scanning 25 best LOCK $2 TRAIL $1 - filling 20/20...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR LOCK $2 TRAIL $1 - KEEPS LEARN?')) return; await fetch('/api/clear_closed_fake'); await load(); }
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
    return jsonify({"cap":data.get("FUND_CAP",1000),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",0),"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":data.get("FAST_WHALE",[]),"kv":f"v573.3 LOCK $2 TRAIL $1 FEE $0.60 GOAL ${DAILY_GOAL} STOP ${DAILY_STOP}"})
@app.route("/api/cron")
def cron(): return jsonify(do_tick())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget_single()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}
    rset_single(data); data["_last_save"]=0; rset_single(data)
    return jsonify({"cleared":True})
