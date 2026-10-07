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
    if CACHE["data"] and now - CACHE["ts"] < 50:
        return CACHE["data"]
    try:
        if not UP_URL or not UP_TOKEN:
            return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"FAST_PUMP":[],"FAST_TOP":[],"FAST_DUMP":[],"FAST_WHALE":[],"BTC_PRICE":0,"BTC_1H":0,"FAST_LAST":0,"DAILY_GOAL_HIT":0}
        r=requests.get(f"{UP_URL}/get/{SINGLE_KEY}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=5)
        v=r.json().get("result")
        if v:
            data=json.loads(v)
            CACHE["data"]=data
            CACHE["ts"]=now
            return data
    except Exception as e:
        print(f"rget_single fail {e}")
    return CACHE["data"] or {"FUND_CAP":1000.0,"FUND_OPEN":[],"FUND_CLOSED":[],"FUND_WINS":0,"FUND_LOSSES":0,"FUND_DAILY_PNL":0,"FUND_DAILY_GROSS":0,"FUND_DAILY_FEE":0,"LEARN_STATS":{},"LAST_LOSS_TIME":{},"FAST_PUMP":[],"FAST_TOP":[],"FAST_DUMP":[],"FAST_WHALE":[],"BTC_PRICE":0,"BTC_1H":0,"FAST_LAST":0,"DAILY_GOAL_HIT":0}

def rset_single(data):
    global CACHE
    CACHE["data"]=data
    CACHE["ts"]=time.time()
    try:
        if not UP_URL or not UP_TOKEN: return
        last_save=float(data.get("_last_save",0) or 0)
        if time.time() - last_save < 55:
            return
        data["_last_save"]=time.time()
        requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", SINGLE_KEY, json.dumps(data)], timeout=5)
    except Exception as e:
        print(f"rset_single fail {e}")

def get_movers_10_profitable():
    try:
        rp=requests.get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=price_change_percentage_1h_desc&per_page=150&page=1&price_change_percentage=1h,24h&sparkline=false", timeout=12).json()
        btc_p=0; btc_1h=0
        for c in rp:
            if c.get('symbol','').upper()=='BTC': btc_p=c.get('current_price',0); btc_1h=c.get('price_change_percentage_1h_in_currency',0)
        return [],[],[],btc_p,btc_1h
    except:
        return [],[],[],0,0

def get_meme_whales_25():
    whales=[]
    try:
        all_pairs=[]
        for url in ["https://api.dexscreener.com/token-boosts/latest/v1","https://api.dexscreener.com/token-boosts/top/v1"]:
            try:
                r=requests.get(url, timeout=8).json()
                if isinstance(r, list):
                    for item in r[:40]:
                        if item.get('chainId')=='solana':
                            token=item.get('tokenAddress')
                            if token:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}", timeout=7).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:2])
            except: continue
        for q in ["SOL","BONK","WIF","PEPE","PUMP","FLOKI","DOGE"]:
            try:
                sr=requests.get(f"https://api.dexscreener.com/latest/dex/search/?q={q}", timeout=8).json()
                if sr.get('pairs'): all_pairs.extend(sr['pairs'][:25])
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
                if not (5000 <= liq <= 250000): continue
                if not (20000 <= fdv <= 2000000): continue
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
                txns=p.get('txns',{}); buys_m5=int(txns.get('m5',{}).get('buys',0) or 0)
                if vol_m5 < 800: continue
                if buys_m5 < 1: continue
                if ch_24 < -80: continue
                if ch_m5 > 500: continue
                if ch_m5 < -60: continue
                whale_est=vol_m5*0.65; score=vol_m5*(1+ch_m5/100)+buys_m5*400
                if ch_m5>10: score*=1.6
                if ch_m5>20: score*=1.4
                if buys_m5>=100: score*=1.5
                whales.append({"prod":f"{base}-USD","symbol":base[:12],"price":price,"c1":ch_m5,"c24":ch_24,"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys_m5,"sells_m5":int(txns.get('m5',{}).get('sells',0) or 0),"whale_usd":whale_est,"score":score,"chain":"solana","pair_url":p.get('url',''),"is_meme_whale":True})
            except: continue
        whales.sort(key=lambda x: x['score'], reverse=True)
        return whales[:25]
    except Exception as e:
        print(f"whale 25 err {e}")
        return []

def get_price(cg_id, last=0):
    try:
        if len(cg_id)>30:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}", timeout=5).json()
            if r.get('pair') and r['pair'].get('priceUsd'):
                p=float(r['pair']['priceUsd'])
                if p>0 and last>0 and abs(p-last)/last*100>70:
                    return p,"JUMP MEME FORCE"
                if p>0: return p,"DEX WHALE"
    except: pass
    return 0,"FAIL"

def do_tick_10_fee():
    data=rget_single()
    cap=float(data.get("FUND_CAP") or 1000.0)
    open_t=data.get("FUND_OPEN") or []
    closed=data.get("FUND_CLOSED") or []
    wins=data.get("FUND_WINS") or 0
    losses=data.get("FUND_LOSSES") or 0
    daily=float(data.get("FUND_DAILY_PNL") or 0)
    dg=float(data.get("FUND_DAILY_GROSS") or 0)
    df=float(data.get("FUND_DAILY_FEE") or 0)
    learn=data.get("LEARN_STATS") or {}
    last_loss=data.get("LAST_LOSS_TIME") or {}
    fast_whale=data.get("FAST_WHALE") or []
    btc_p=float(data.get("BTC_PRICE") or 0)
    btc_1h=float(data.get("BTC_1H") or 0)
    now=time.time()
    if now - float(data.get("FAST_LAST") or 0) > 30:
        w=get_meme_whales_25()
        _,_,_,bp,bh=get_movers_10_profitable()
        if w:
            fast_whale=w; btc_p=bp; btc_1h=bh
            data["FAST_WHALE"]=w; data["FAST_LAST"]=now; data["BTC_PRICE"]=bp; data["BTC_1H"]=bh

    new_open=[]
    for tr in open_t:
        try:
            sym=tr.get('symbol','?'); prod=tr.get('prod',sym); entry=float(tr.get('entry',0) or 0); last=float(tr.get('last_price',entry) or entry); pos=float(tr.get('pos',60) or 60); side=tr.get('side','LONG')
            cg_id=tr.get('cg_id',''); is_meme=tr.get('is_meme',True)
            if entry==0: continue
            cur,src=get_price(cg_id,last) if cg_id else (0,"FAIL")
            if cur==0:
                for fm in fast_whale:
                    if fm.get('prod')==prod or fm.get('symbol')==sym or fm.get('cg_id')==cg_id:
                        cur=fm['price']; src="FAST"; break
            if cur==0:
                tr['last_price']=last
                new_open.append(tr)
                continue
            age=now-float(tr.get('ts',now) or now)
            pct=(cur-entry)/entry*100 if side=="LONG" else (entry-cur)/entry*100
            fee_rt=pos*0.001*2.0; gross=pos*pct/100.0; net=gross-fee_rt
            tp=12.0; sl=6.0; tlimit=1800
            close=False; rs=""
            if "FORCE" in src:
                close=True; rs=f"FORCE CLOSE {src} {pct:.2f}% NET ${net:.3f}"
            elif pct>=tp and age>=15 and net>=0.05:
                close=True; rs=f"REAL WIN MEME WHALE TP {pct:.2f}% >= {tp}% NET ${net:.3f} COVERS FEE"
            elif pct<= -sl:
                close=True; rs=f"REAL LOSS MEME WHALE SL {pct:.2f}% <= -{sl}% NET ${net:.3f} SL {sl}%"
            elif age>=tlimit and pct>=0.10 and net>=0.05:
                close=True; rs=f"REAL WIN TIME {age:.0f}s {pct:.2f}% NET ${net:.3f}"
            elif age>=tlimit and pct<0:
                close=True; rs=f"REAL LOSS TIME {age:.0f}s {pct:.2f}% < 0% NET ${net:.3f}"
            if close:
                closed.append({"symbol":sym,"prod":prod,"side":side,"entry":entry,"exit":cur,"pct":pct,"gross":gross,"fee":fee_rt,"net":net,"reason":rs,"ts":now,"is_meme":is_meme,"pos":pos})
                if len(closed)>400: closed=closed[-400:]
                if net>=0.05: wins+=1
                else: losses+=1
                st=learn.get(sym, {'w':0,'l':0})
                if net>=0.05: st['w']=st.get('w',0)+1
                else: st['l']=st.get('l',0)+1; last_loss[sym]=now
                learn[sym]=st
                daily+=net; dg+=gross; df+=fee_rt; cap+=net
            else:
                tr['last_price']=cur
                new_open.append(tr)
        except:
            new_open.append(tr)

    if daily >= DAILY_GOAL:
        data["FUND_CAP"]=cap; data["FUND_OPEN"]=new_open; data["FUND_CLOSED"]=closed; data["FUND_WINS"]=wins; data["FUND_LOSSES"]=losses; data["FUND_DAILY_PNL"]=daily; data["FUND_DAILY_GROSS"]=dg; data["FUND_DAILY_FEE"]=df; data["LEARN_STATS"]=learn; data["LAST_LOSS_TIME"]=last_loss; data["DAILY_GOAL_HIT"]=daily
        rset_single(data)
        return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"btc":btc_p,"btc1h":btc_1h,"kv":f"GOAL HIT ${daily:.2f} >= ${DAILY_GOAL} - STOPPED TILL NEXT DAY - $300 DONE"}
    if daily <= DAILY_STOP:
        data["FUND_CAP"]=cap; data["FUND_OPEN"]=new_open; data["FUND_CLOSED"]=closed; data["FUND_WINS"]=wins; data["FUND_LOSSES"]=losses; data["FUND_DAILY_PNL"]=daily; data["FUND_DAILY_GROSS"]=dg; data["FUND_DAILY_FEE"]=df; data["LEARN_STATS"]=learn; data["LAST_LOSS_TIME"]=last_loss; data["DAILY_GOAL_HIT"]=daily
        rset_single(data)
        return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"btc":btc_p,"btc1h":btc_1h,"kv":f"STOP LOSS ${daily:.2f} <= ${DAILY_STOP} - PROTECT TILL NEXT DAY"}

    whale_open=len([x for x in new_open if x.get('is_meme')])
    widx=0
    while whale_open<5 and widx<len(fast_whale):
        try:
            m=fast_whale[widx]; widx+=1
            sym=m['symbol']
            if any(x['symbol']==sym for x in new_open): continue
            if any(x.get('cg_id')==m['cg_id'] for x in new_open): continue
            if m['fdv']<20000 or m['fdv']>2000000: continue
            if m['liq']<5000: continue
            if sym in last_loss and now-float(last_loss.get(sym,0) or 0)<1800: continue
            pos=60.0
            reason=f"SHARK $60 x5 WHALE {m.get('buys_m5',0)} BUYS VOL M5 ${m.get('vol_m5',0):.0f} WHALE ${m.get('whale_usd',0):.0f} FDV ${m.get('fdv',0):.0f} LIQ ${m.get('liq',0):.0f} {m.get('c1',0):.1f}% M5 TP 12% SL 6% $60"
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":now,"side":"LONG","reason":reason,"target":12.0,"stop":6.0,"last_price":m['price'],"pos":pos,"c1":m['c1'],"c24":m['c24'],"cg_id":m['cg_id'],"is_meme":True,"whale_usd":m.get('whale_usd',0),"fdv":m.get('fdv',0)})
            whale_open+=1
        except: continue

    data["FUND_CAP"]=cap; data["FUND_OPEN"]=new_open; data["FUND_CLOSED"]=closed; data["FUND_WINS"]=wins; data["FUND_LOSSES"]=losses; data["FUND_DAILY_PNL"]=daily; data["FUND_DAILY_GROSS"]=dg; data["FUND_DAILY_FEE"]=df; data["LEARN_STATS"]=learn; data["LAST_LOSS_TIME"]=last_loss
    rset_single(data)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"whale":fast_whale,"btc":btc_p,"btc1h":btc_1h,"kv":f"SHARK v572 25 BEST WHALE $60 x5 - GOAL ${DAILY_GOAL} STOP ${DAILY_STOP}"}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v572 $60 x5 $300 GOAL</title><style>
*{margin:0;padding:0;box-sizing:border-box;font-family:monospace}
body{background:#0a0a0a;color:#00FF88}
.top{padding:8px 10px;display:flex;justify-content:space-between;border-bottom:2px solid #00FF88;background:#000}
.top b{color:#00FF88;font-size:10px}
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
<div class="top"><div><b>VENUS v572 $60 x5 WHALE ONLY - 25 BEST POOL - $300/DAY GOAL -$150 STOP TILL NEXT DAY</b> <span style="color:#888;font-size:7px">SHARK $60 x5</span></div><div style="font-size:8px;color:#00FF88" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND REAL $60 x5 WHALE ONLY - 25 POOL - SINGLE KEY</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">COVERS FEE - $60 x5</small></div>
<div class="card"><small>OPEN 5/5 WHALE $60 x5 - 25 BEST POOL</small><b id="open" class="green">0/5</b><small class="green" id="wr">COVERS FEE - KV OK</small></div>
<div class="card"><small>DAILY GROSS - FEE = NET - GOAL $300 STOP -$150 TILL NEXT DAY</small><b id="daily" class="green">+$0.00</b><small id="dailySub" style="color:#666">COVERS FEE</small></div>
<div class="card"><small>PERFORMANCE - $60 x5 WHALE ONLY</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">COVERS FEE + PROFIT</small></div>
</div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #FF00FF"><div style="font-size:7px;color:#FF00FF">TOP 25 WHALE MEME DETECTED - $60 x5 - VOL $800+ - $300 GOAL -$150 STOP - 25 BEST POOL PICKS 5 OPEN</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 110px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>5 TRADES $60 x5 WHALE ONLY - 25 BEST POOL - $300 GOAL</span><span>SIDE</span><span>ENTRY FEE</span><span>TICK TP/SL NET</span><span>TP/SL NET</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN $60 x5 WHALE ONLY - 25 BEST POOL - $300 GOAL -$150 STOP - 1 CMD</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN 5 TRADES $60 x5 - KEEPS LEARN - 1 CMD</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88;margin-bottom:3px">CLOSED LAST 40 - $60 x5 WHALE ONLY - $300 GOAL</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / FEE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON - $60 x5 - 1 CMD</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2);
 document.getElementById('capSub').innerText='1 CMD MODE GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' BTC '+Number(j.btc1h||0).toFixed(2)+'%';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/5 WHALE $60 x5 POOL 25';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L BTC '+Number(j.btc1h||0).toFixed(2)+'% KV '+(j.kv||'1 CMD')+' - $60 x5';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#00FF88':'#FF0040';
 document.getElementById('dailySub').innerText='1 CMD GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $300 STOP -$150 BTC '+Number(j.btc1h||0).toFixed(2)+'%';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('wlSub').innerText='WR '+wr+'% - TP 12% SL 6% $60 x5 BTC '+Number(j.btc1h||0).toFixed(2)+'% GOAL $300';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' GOAL $300 BTC $'+Number(j.btc||0).toFixed(0)+' 1H '+Number(j.btc1h||0).toFixed(2)+'% $60 x5';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid #FF00FF;padding:2px 4px;font-size:7px;color:#FF00FF">#${i+1} WHALE ${m.symbol} ${Number(m.c1).toFixed(1)}% M5 $${Number(m.price).toFixed(8)}<br><span style="color:#FFD000">WHALE $${Number(m.whale_usd||0).toFixed(0)} ${m.buys_m5} BUYS VOL M5 $${Number(m.vol_m5||0).toFixed(0)} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)} POT 3000% $60</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">No whale buys now - $60 x5 MODE scanning 25 best Solana every 30s - VOL $800 - GOAL $300</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||60); let fee=pos*0.002; let target=Number(t.target||12); let netEst=pos*target/100 - fee;
   let side=t.side||'LONG'; let sideColor=side=='LONG'?'#00FF88':'#FF0040'; sideColor='#FF00FF';
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 110px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:${sideColor}">${t.symbol||''}</b> <small style="color:#FF00FF">WHALE $60 x5</small></span><span><b style="color:${sideColor};border:1px solid ${sideColor};padding:1px 3px;font-size:7px">${side}</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos} $${fee.toFixed(3)}</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,90)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} COVERS FEE</small></span><span style="font-size:7px"><span style="color:#FF00FF">TP +12%</span><br><span style="color:#FF0040">SL 6%</span><br><small style="color:#FFD000">NET $${netEst.toFixed(2)}</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#00FF88;padding:10px;font-size:10px">GOAL HIT $300 or STOP -$150 or No open - $60 x5 WHALE ONLY - 25 BEST POOL - 1 CMD</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-40).reverse().forEach(c=>{
   let col=c.net>=0.05?'#00FF88':'#FF0040'; let side=c.side||'LONG'; let sideColor='#FF00FF';
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#00FF88"><b style="color:${sideColor}">${c.symbol||''}</b><br><small style="color:${sideColor}">${side} $60 x5</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:${sideColor};border:1px solid ${sideColor};padding:1px 3px;font-size:7px">${side}</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}%</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,180)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% ${c.net>=0.05?'COVERS':'NOT COVER'}</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FF00FF;padding:10px">Scanning 25 best whale $60 x5 - $300 GOAL...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR - $60 x5 - KEEPS LEARN?')) return; await fetch('/api/clear_closed_fake'); await load(); }
setInterval(load,8000);load();
</script></body></html>
"""
@app.route("/")
def home():
    return HTML
@app.route("/api/state")
def state():
    try: do_tick_10_fee()
    except Exception as e: print(f"tick err {e}")
    data=rget_single()
    return jsonify({"cap":data.get("FUND_CAP",1000),"open_trades":data.get("FUND_OPEN",[]),"wins":data.get("FUND_WINS",0),"losses":data.get("FUND_LOSSES",0),"closed":data.get("FUND_CLOSED",[]),"daily":data.get("FUND_DAILY_PNL",0),"dg":data.get("FUND_DAILY_GROSS",0),"df":data.get("FUND_DAILY_FEE",0),"whale":data.get("FAST_WHALE",[]),"btc":data.get("BTC_PRICE",0),"btc1h":data.get("BTC_1H",0),"kv":f"SHARK v572 $60 x5 WHALE ONLY 25 BEST - GOAL ${DAILY_GOAL} STOP ${DAILY_STOP}"})
@app.route("/api/cron")
def cron():
    return jsonify(do_tick_10_fee())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    data=rget_single()
    data["FUND_CLOSED"]=[]; data["FUND_DAILY_PNL"]=0; data["FUND_DAILY_GROSS"]=0; data["FUND_DAILY_FEE"]=0; data["FUND_OPEN"]=[]; data["LAST_LOSS_TIME"]={}; data["DAILY_GOAL_HIT"]=0
    rset_single(data)
    data["_last_save"]=0
    rset_single(data)
    return jsonify({"cleared":True,"msg":"Cleared v572 $60 x5 $300 GOAL"})
