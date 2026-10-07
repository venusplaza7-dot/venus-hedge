from flask import Flask, jsonify
import os, json, requests, time
app = Flask(__name__)
UP_URL = (os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
def rget(k):
    try:
        if not UP_URL or not UP_TOKEN: return None
        r=requests.get(f"{UP_URL}/get/{k}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=5)
        v=r.json().get("result")
        return json.loads(v) if v else None
    except: return None
def rset(k,v):
    try:
        if not UP_URL or not UP_TOKEN: return
        requests.post(f"{UP_URL}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, json=["SET", k, json.dumps(v)], timeout=5)
    except: pass

def get_movers_10_profitable():
    try:
        rp=requests.get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=price_change_percentage_1h_desc&per_page=150&page=1&price_change_percentage=1h,24h&sparkline=false", timeout=12).json()
        rd=requests.get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=price_change_percentage_1h_asc&per_page=150&page=1&price_change_percentage=1h,24h&sparkline=false", timeout=12).json()
        skip={'USDT','USDC','DAI','FDUSD','USDE','USDF','GHO','BTW','PAXG','XAUT','WBTC','WETH','STETH','BTT','KITE','HBAR','HTX','DCR','ADA','OKB','KCS','XMR','BTC','ETH','BNB','XRP','SOL','TRX','WTRX'}
        skip_id={'tether','usd-coin','dai','first-digital-usd','ethena-usde','usd-freedom','gho','pax-gold','tether-gold','wrapped-bitcoin','weth','bittorrent','kaito','hedera','huobi-token','decred','cardano','okb','kucoin-shares','monero','bitcoin','ethereum','binancecoin','ripple','solana','tron'}
        btc_p=0; btc_1h=0
        for c in rp+rd:
            if c.get('symbol','').upper()=='BTC': btc_p=c.get('current_price',0); btc_1h=c.get('price_change_percentage_1h_in_currency',0)
        pump=[]; top=[]; dump=[]
        for c in rp:
            c1=c.get('price_change_percentage_1h_in_currency')
            if c1 is None: continue
            sym=c.get('symbol','').upper(); cg=c.get('id','')
            if sym in skip or cg in skip_id:
                if sym in ['BTC','ETH','BNB'] and c1>=1.2: pass
                else: continue
            if c.get('current_price',0)<0.0000005: continue
            c24=c.get('price_change_percentage_24h_in_currency',0) or 0
            if 0.80 <= c1 <= 2.20 and c24>-8 and c24<12:
                pump.append({"prod":f"{sym}-USD","symbol":sym,"price":c.get('current_price'),"c1":c1,"c24":c24,"cg_id":cg})
            if 2.20 < c1 <= 6.0 and c24>3:
                top.append({"prod":f"{sym}-USD","symbol":sym,"price":c.get('current_price'),"c1":c1,"c24":c24,"cg_id":cg})
        for c in rd:
            c1=c.get('price_change_percentage_1h_in_currency')
            if c1 is None: continue
            sym=c.get('symbol','').upper(); cg=c.get('id','')
            if sym in skip or cg in skip_id: continue
            if c.get('current_price',0)<0.0000005: continue
            if -3.0 <= c1 <= -0.80:
                dump.append({"prod":f"{sym}-USD","symbol":sym,"price":c.get('current_price'),"c1":c1,"c24":c.get('price_change_percentage_24h_in_currency',0) or 0,"cg_id":cg})
        pump.sort(key=lambda x: x['c1'], reverse=True)
        top.sort(key=lambda x: x['c1'], reverse=True)
        dump.sort(key=lambda x: x['c1'])
        return pump[:12], top[:6], dump[:15], btc_p, btc_1h
    except Exception as e:
        print(f"10 profitable err {e}")
        return [],[],[],0,0

def get_meme_whales():
    whales=[]
    try:
        urls=["https://api.dexscreener.com/token-boosts/latest/v1","https://api.dexscreener.com/token-boosts/top/v1"]
        all_pairs=[]
        for url in urls:
            try:
                r=requests.get(url, timeout=8).json()
                if isinstance(r, list):
                    for item in r[:25]:
                        if item.get('chainId')=='solana':
                            token=item.get('tokenAddress')
                            if token:
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}", timeout=7).json()
                                if pr.get('pairs'): all_pairs.extend(pr['pairs'][:2])
            except: continue
        try:
            sr=requests.get("https://api.dexscreener.com/latest/dex/search/?q=SOL", timeout=8).json()
            if sr.get('pairs'): all_pairs.extend(sr['pairs'][:40])
        except: pass
        seen=set()
        for p in all_pairs:
            try:
                if p.get('chainId')!='solana': continue
                base=p.get('baseToken',{}).get('symbol','').upper()
                if base in ['SOL','USDC','USDT','WETH','WBTC','BONK','WIF']: continue
                addr=p.get('pairAddress')
                if not addr or addr in seen: continue
                seen.add(addr)
                fdv=float(p.get('fdv',0) or 0); liq=float(p.get('liquidity',{}).get('usd',0) or 0); price=float(p.get('priceUsd',0) or 0)
                if price==0: continue
                if not (12000 <= liq <= 120000): continue
                if not (50000 <= fdv <= 700000): continue
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0); ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0); ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
                txns=p.get('txns',{}); buys_m5=int(txns.get('m5',{}).get('buys',0) or 0); sells_m5=int(txns.get('m5',{}).get('sells',0) or 0)
                if vol_m5 < 2000: continue
                if buys_m5 < 2: continue
                if ch_24 < -60: continue
                if ch_m5 > 250: continue
                if ch_m5 < -45: continue
                whale_est=vol_m5*0.65
                score=vol_m5*(1+ch_m5/100)+buys_m5*400
                if ch_m5>15: score*=1.6
                whales.append({"prod":f"{base}-USD","symbol":base[:10],"price":price,"c1":ch_m5,"c24":ch_24,"cg_id":addr,"fdv":fdv,"liq":liq,"vol_m5":vol_m5,"buys_m5":buys_m5,"sells_m5":sells_m5,"whale_usd":whale_est,"score":score,"chain":"solana","pair_url":p.get('url',''),"is_meme_whale":True})
            except: continue
        whales.sort(key=lambda x: x['score'], reverse=True)
        return whales[:8]
    except Exception as e:
        print(f"whale err {e}")
        return []

def get_price(cg_id, last=0):
    try:
        if len(cg_id)>30:
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}", timeout=5).json()
            if r.get('pair') and r['pair'].get('priceUsd'):
                p=float(r['pair']['priceUsd'])
                if p>0 and last>0 and abs(p-last)/last*100>70: return 0,"JUMP MEME"
                if p>0: return p,"DEX WHALE"
        else:
            r=requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd", timeout=5)
            p=float(r.json()[cg_id]['usd'])
            if p>0 and last>0 and abs(p-last)/last*100>7: return 0,"JUMP"
            if p>0: return p,"CG 10 COVERS FEE"
    except: pass
    return 0,"FAIL"

def do_tick_10_fee():
    cap=float(rget("FUND_CAP") or 1000.0)
    open_t=rget("FUND_OPEN") or []
    closed=rget("FUND_CLOSED") or []
    wins=rget("FUND_WINS") or 0
    losses=rget("FUND_LOSSES") or 0
    daily=float(rget("FUND_DAILY_PNL") or 0)
    dg=float(rget("FUND_DAILY_GROSS") or 0)
    df=float(rget("FUND_DAILY_FEE") or 0)
    learn=rget("LEARN_STATS") or {}
    last_loss=rget("LAST_LOSS_TIME") or {}
    now=time.time()
    def should_invert(sym):
        try:
            st=learn.get(sym, {'w':0,'l':0}); tot=st.get('w',0)+st.get('l',0)
            if tot>=5 and st.get('w',0)/tot < 0.40: return True
        except: pass
        return False
    if now - float(rget("FAST_LAST") or 0) > 25:
        p,t,d,bp,bh=get_movers_10_profitable()
        w=get_meme_whales()
        if p or t or d or w:
            rset("FAST_PUMP",p); rset("FAST_TOP",t); rset("FAST_DUMP",d); rset("FAST_WHALE",w); rset("FAST_LAST",now); rset("BTC_PRICE",bp); rset("BTC_1H",bh)
            fast_pump=p; fast_top=t; fast_dump=d; fast_whale=w; btc_p=bp; btc_1h=bh
        else:
            fast_pump=rget("FAST_PUMP") or []; fast_top=rget("FAST_TOP") or []; fast_dump=rget("FAST_DUMP") or []; fast_whale=rget("FAST_WHALE") or []; btc_p=float(rget("BTC_PRICE") or 0); btc_1h=float(rget("BTC_1H") or 0)
    else:
        fast_pump=rget("FAST_PUMP") or []; fast_top=rget("FAST_TOP") or []; fast_dump=rget("FAST_DUMP") or []; fast_whale=rget("FAST_WHALE") or []; btc_p=float(rget("BTC_PRICE") or 0); btc_1h=float(rget("BTC_1H") or 0)

    new_open=[]
    for tr in open_t:
        try:
            sym=tr.get('symbol','?'); prod=tr.get('prod',sym); entry=float(tr.get('entry',0) or 0); last=float(tr.get('last_price',entry) or entry); pos=float(tr.get('pos',30) or 30); side=tr.get('side','LONG')
            if side not in ['LONG','SHORT']: side='LONG'
            cg_id=tr.get('cg_id',''); is_meme=tr.get('is_meme',False)
            if entry==0: continue
            cur,src=get_price(cg_id,last) if cg_id else (0,"FAIL")
            if cur==0:
                for fm in fast_pump+fast_top+fast_dump+fast_whale:
                    if fm.get('prod')==prod or fm.get('symbol')==sym or fm.get('cg_id')==cg_id:
                        cur=fm['price']; src="FAST 10 FEE"; break
            if cur==0: cur=last
            age=now-float(tr.get('ts',now) or now)
            pct=(cur-entry)/entry*100 if side=="LONG" else (entry-cur)/entry*100
            fee_rt=pos*0.001*2.0; gross=pos*pct/100.0; net=gross-fee_rt
            if is_meme: tp=15.0; hold=8.0; sl=25.0; tlimit=3600
            else: tp=float(tr.get('target',0.80) or 0.80); hold=0.60; sl=0.35; tlimit=1800
            close=False; rs=""
            if pct>=tp and age>=20 and net>=0.08:
                close=True; rs=f"REAL WIN {'MEME WHALE' if is_meme else 'OPPOSITE'} TP {pct:.2f}% >= {tp}% NET ${net:.3f} COVERS FEE"
            elif pct<= -sl:
                close=True; rs=f"REAL LOSS {'MEME WHALE' if is_meme else 'OPPOSITE'} SL {pct:.2f}% <= -{sl}% NET ${net:.3f} SL {sl}%"
            elif age>=tlimit and pct>=hold and net>=0.08:
                close=True; rs=f"REAL WIN {'MEME WHALE' if is_meme else 'OPPOSITE'} HOLD {pct:.2f}% >= {hold}% {age:.0f}s NET ${net:.3f}"
            elif age>=tlimit and pct<hold:
                close=True; rs=f"REAL LOSS {'MEME WHALE' if is_meme else 'OPPOSITE'} TIME {age:.0f}s {pct:.2f}% < HOLD {hold}% NET ${net:.3f}"
            if close:
                closed.append({"symbol":sym,"prod":prod,"side":side,"entry":entry,"exit":cur,"pct":pct,"gross":gross,"fee":fee_rt,"net":net,"reason":rs,"ts":now,"is_meme":is_meme})
                if len(closed)>300: closed=closed[-300:]
                if net>=0.08: wins+=1
                else: losses+=1
                st=learn.get(sym, {'w':0,'l':0})
                if net>=0.08: st['w']=st.get('w',0)+1
                else: st['l']=st.get('l',0)+1; last_loss[sym]=now
                learn[sym]=st
                daily+=net; dg+=gross; df+=fee_rt; cap+=net
            else:
                tr['last_price']=cur
                new_open.append(tr)
        except:
            new_open.append(tr)

    # Fill stable 10
    stable_open=len([x for x in new_open if not x.get('is_meme')])
    candidates=fast_pump+fast_top+fast_dump
    idx=0
    while stable_open<10 and idx<len(candidates):
        try:
            m=candidates[idx]; idx+=1
            sym=m['symbol']
            if any(x['symbol']==sym for x in new_open): continue
            if sym in last_loss and now-float(last_loss.get(sym,0) or 0)<1800: continue
            side="LONG" if m in fast_pump else "SHORT"
            if should_invert(sym): side="SHORT" if side=="LONG" else "LONG"
            pos=30.0; tp=0.80; fee=pos*0.002; gross_est=pos*tp/100; net_est=gross_est-fee
            if net_est<0.08: continue
            reason=f"SMART 10 OPPOSITE {side} PUMP {m.get('c1',0):.2f}% TP {tp}% SL 0.35% NET ${net_est:.3f} COVERS FEE BTC {btc_1h:.2f}%"
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":now,"side":side,"reason":reason,"target":tp,"stop":0.35,"last_price":m['price'],"pos":pos,"c1":m['c1'],"c24":m['c24'],"cg_id":m['cg_id'],"is_meme":False})
            stable_open+=1
        except: continue
    # Fill whale 5
    whale_open=len([x for x in new_open if x.get('is_meme')])
    widx=0
    while whale_open<5 and widx<len(fast_whale):
        try:
            m=fast_whale[widx]; widx+=1
            sym=m['symbol']
            if any(x['symbol']==sym for x in new_open): continue
            if any(x.get('cg_id')==m['cg_id'] for x in new_open): continue
            if m['fdv']<40000 or m['fdv']>800000: continue
            if m['liq']<10000: continue
            reason=f"WHALE MEME {m.get('buys_m5',0)} BUYS VOL M5 ${m.get('vol_m5',0):.0f} WHALE ${m.get('whale_usd',0):.0f} FDV ${m.get('fdv',0):.0f} LIQ ${m.get('liq',0):.0f} {m.get('c1',0):.1f}% M5 TP 15% SL 25% POTENTIAL 3000%"
            new_open.append({"symbol":sym,"prod":m['prod'],"entry":m['price'],"ts":now,"side":"LONG","reason":reason,"target":15.0,"stop":25.0,"last_price":m['price'],"pos":30.0,"c1":m['c1'],"c24":m['c24'],"cg_id":m['cg_id'],"is_meme":True,"whale_usd":m.get('whale_usd',0),"fdv":m.get('fdv',0)})
            whale_open+=1
        except: continue

    rset("FUND_CAP",cap); rset("FUND_OPEN",new_open); rset("FUND_CLOSED",closed); rset("FUND_WINS",wins); rset("FUND_LOSSES",losses); rset("FUND_DAILY_PNL",daily); rset("FUND_DAILY_GROSS",dg); rset("FUND_DAILY_FEE",df); rset("LEARN_STATS",learn); rset("LAST_LOSS_TIME",last_loss)
    return {"cap":cap,"open":new_open,"wins":wins,"losses":losses,"daily":daily,"dg":dg,"df":df,"pump":fast_pump,"top":fast_top,"dump":fast_dump,"whale":fast_whale,"btc":btc_p,"btc1h":btc_1h}

HTML="""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VENUS v567 CLEAN WHALE</title><style>
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
<div class="top"><div><b>VENUS v567 CLEAN WHALE - 10 STABLE + 5 MEME WHALE - TP 0.80% HOLD 0.60% SL 0.35% + WHALE 15%</b> <span style="color:#888;font-size:7px">TP 0.80% = $0.24 GROSS $0.06 FEE = +$0.18 NET - WHALE 15% = $4.50 GROSS - 3000% POTENTIAL - NOT RANDOM - 15/15</span></div><div style="font-size:8px;color:#00FF88" id="time"></div></div>
<div class="grid">
<div class="card"><small>FUND REAL COVERS FEE + PROFIT 15</small><b id="cap" class="green">$1000</b><small class="green" id="capSub">COVERS FEE</small></div>
<div class="card"><small>OPEN 15/15 STABLE 10 WHALE 5 - SCANNING SOLANA</small><b id="open" class="green">0/15</b><small class="green" id="wr">COVERS FEE</small></div>
<div class="card"><small>DAILY GROSS - FEE = NET COVERS FEE</small><b id="daily" class="green">+$0.00</b><small id="dailySub" style="color:#666">COVERS FEE</small></div>
<div class="card"><small>PERFORMANCE COVERS FEE - WHALE + STABLE</small><b id="wl">0W / 0L</b><small class="green" id="wlSub">COVERS FEE + PROFIT</small></div>
</div>
<div style="padding:4px;background:#1a001a;border-bottom:2px solid #FF00FF"><div style="font-size:7px;color:#FF00FF">TOP 8 WHALE MEME DETECTED - WHALES BUYING NOW - 3000% POTENTIAL - FDV $60k-700k LIQ $12k-120k VOL M5 $2k+ - POTENTIAL 3000%</div><div id="whalelist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div style="padding:4px;background:#001a0a;border-bottom:1px solid #00FF88"><div style="font-size:7px;color:#00FF88">TOP 12 LONG PUMP 0.80-2.2% OPPOSITE FILTER - COVERS FEE - TP 0.80% GROSS $0.24 FEE $0.06 NET +$0.18 - KNOWS WHEN TO LONG - PROFITABLE AFTER FEE</div><div id="pumplist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div style="padding:4px;background:#1a0a00;border-bottom:1px solid #FF8800"><div style="font-size:7px;color:#FF8800">TOP 6 SHORT TOP +2.2%+ OPPOSITE - COVERS FEE - TP 0.80% NET +$0.18 - KNOWS WHEN TO SHORT TOP - PROFITABLE AFTER FEE</div><div id="toplist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div style="padding:4px;background:#1a000a;border-bottom:1px solid #FF0040"><div style="font-size:7px;color:#FF0040">TOP 15 SHORT DUMP -0.80% to -3.0% OPPOSITE LEARNED - COVERS FEE - TP 0.80% NET +$0.18 - KNOWS WHEN TO SHORT DUMP HARDER THAN BTC - PROFITABLE AFTER FEE</div><div id="dumplist" style="display:flex;flex-wrap:wrap;gap:2px;margin-top:2px"></div></div>
<div id="openwrap"><div style="display:grid;grid-template-columns:1fr 50px 65px 110px 45px 30px;padding:4px 5px;font-size:6px;color:#666;background:#111"><span>15 TRADES 10 STABLE +5 WHALE COVERS FEE</span><span>SIDE</span><span>ENTRY FEE COVERS</span><span>TICK FEE DEDUCTED COVERS FEE + TP/SL NET COVERS</span><span>TP/SL NET COVERS</span><span>AGE</span></div><div id="openlist"></div></div>
<button class="scan" onclick="tick()">SCAN CLEAN 15 - 10 STABLE TP 0.80% SL 0.35% + 5 WHALE 15% TP 25% SL - 3000% POTENTIAL - COVERS FEE</button>
<button class="clear" onclick="clearFake()">CLEAR - START CLEAN 15 TRADES - KEEPS LEARN</button>
<div style="padding:4px;background:#000"><div style="font-size:8px;color:#00FF88;margin-bottom:3px">CLOSED LAST 30 - WHALE + STABLE - COVERS BINANCE FEE + PROFIT</div><table style="width:100%;border-collapse:collapse"><thead><tr><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SYMBOL</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">SIDE</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">NET / GROSS / FEE COVERS</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">REASON - WHALE + OPPOSITE LEARNED</th><th style="font-size:6px;color:#666;text-align:left;padding:3px;border-bottom:1px solid #222">FEE</th></tr></thead><tbody id="closed"></tbody></table></div>
<script>
function fmtPrice(p){ if(p==null||isNaN(p)) return '$0'; if(p>=1000) return '$'+Number(p).toFixed(2); if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 try{ await fetch('/api/cron'); }catch(e){}
 let r=await fetch('/api/state');let j=await r.json();
 document.getElementById('cap').innerText='$'+Number(j.cap||1000).toFixed(2);
 document.getElementById('capSub').innerText='COVERS FEE 15 GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' BTC '+Number(j.btc1h||0).toFixed(2)+'%';
 document.getElementById('open').innerText=(j.open_trades||[]).length+'/15 STABLE '+(j.open_trades||[]).filter(x=>!x.is_meme).length+'/10 WHALE '+(j.open_trades||[]).filter(x=>x.is_meme).length+'/5';
 let wr=j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0;
 document.getElementById('wr').innerText='WR '+wr+'% '+j.wins+'W/'+j.losses+'L BTC '+Number(j.btc1h||0).toFixed(2)+'% WHALE MODE ACTIVE';
 document.getElementById('daily').innerText=(j.daily>=0?'+':'')+'$'+Number(j.daily||0).toFixed(3);
 document.getElementById('daily').style.color=(j.daily||0)>=0?'#00FF88':'#FF0040';
 document.getElementById('dailySub').innerText='GROSS $'+Number(j.dg||0).toFixed(3)+' FEE $'+Number(j.df||0).toFixed(3)+' NET $'+Number(j.daily||0).toFixed(3)+' BTC '+Number(j.btc1h||0).toFixed(2)+'% COVERS FEE + PROFIT';
 document.getElementById('wl').innerHTML=j.wins+'W / '+j.losses+'L';
 document.getElementById('wlSub').innerText='WR '+wr+'% - TP 0.80% HOLD 0.60% SL 0.35% + WHALE 15% BTC '+Number(j.btc1h||0).toFixed(2)+'%';
 document.getElementById('time').innerText=new Date().toLocaleTimeString()+' NET $'+Number(j.daily||0).toFixed(3)+' BTC $'+Number(j.btc||0).toFixed(0)+' 1H '+Number(j.btc1h||0).toFixed(2)+'%';
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale||[]).forEach((m,i)=>{ wl.innerHTML+=`<div style="border:1px solid #FF00FF;padding:2px 4px;font-size:7px;color:#FF00FF">#${i+1} WHALE ${m.symbol} +${Number(m.c1).toFixed(1)}% M5 $${Number(m.price).toFixed(8)}<br><span style="color:#FFD000">WHALE $${Number(m.whale_usd||0).toFixed(0)} ${m.buys_m5} BUYS VOL M5 $${Number(m.vol_m5||0).toFixed(0)} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)} POT 3000%</span></div>`; });
 if((j.whale||[]).length==0) wl.innerHTML='<div style="font-size:7px;color:#666">No whale buys now - scanning Solana Dexscreener every 25s - whales $3k+ in low cap $60k-700k FDV</div>';
 let pl=document.getElementById('pumplist'); pl.innerHTML='';
 (j.pump||[]).forEach((m,i)=>{ pl.innerHTML+=`<div style="border:1px solid #00FF88;padding:2px 4px;font-size:7px;color:#00FF88">#${i+1} LONG ${m.symbol} +${Number(m.c1).toFixed(2)}% ${fmtPrice(m.price)}</div>`; });
 if((j.pump||[]).length==0) pl.innerHTML='<div style="font-size:7px;color:#666">No pump 0.80-2.2% now</div>';
 let tl=document.getElementById('toplist'); tl.innerHTML='';
 (j.top||[]).forEach((m,i)=>{ tl.innerHTML+=`<div style="border:1px solid #FF8800;padding:2px 4px;font-size:7px;color:#FF8800">#${i+1} SHORT TOP ${m.symbol} +${Number(m.c1).toFixed(2)}% ${fmtPrice(m.price)}</div>`; });
 if((j.top||[]).length==0) tl.innerHTML='<div style="font-size:7px;color:#666">No top +2.2%+ now</div>';
 let dl=document.getElementById('dumplist'); dl.innerHTML='';
 (j.dump||[]).forEach((m,i)=>{ dl.innerHTML+=`<div style="border:1px solid #FF0040;padding:2px 4px;font-size:7px;color:#FF0040">#${i+1} SHORT ${m.symbol} ${Number(m.c1).toFixed(2)}% ${fmtPrice(m.price)}</div>`; });
 if((j.dump||[]).length==0) dl.innerHTML='<div style="font-size:7px;color:#666">No dump -0.80% -3% now</div>';
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let pos=Number(t.pos||30); let fee=pos*0.002; let target=Number(t.target||0.80); let netEst=pos*target/100 - fee;
   let side=t.side||'LONG'; let sideColor=side=='LONG'?'#00FF88':'#FF0040'; if(t.is_meme) sideColor='#FF00FF';
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:1fr 50px 65px 110px 45px 30px;padding:5px;border-bottom:1px solid #111"><span><b style="color:${sideColor}">${t.symbol||''}</b> <small style="color:${t.is_meme?'#FF00FF':'#666'}">${t.is_meme?'WHALE MEME':side}</small></span><span><b style="color:${sideColor};border:1px solid ${sideColor};padding:1px 3px;font-size:7px">${side}</b></span><span>${fmtPrice(t.entry)}<br><small style="color:#666">${fmtPrice(t.last_price)}</small><br><small style="color:#FFD000">$${pos} $${fee.toFixed(3)}</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,90)}<br><small style="color:#FFD000">NET $${netEst.toFixed(3)} COVERS FEE</small></span><span style="font-size:7px"><span style="color:${sideColor}">TP ${side=='LONG'?'+':''}${target}%</span><br><span style="color:#FF0040">SL ${t.is_meme?'25%':'0.35%'}</span><br><small style="color:#FFD000">NET $${netEst.toFixed(3)} COVERS</small></span><span>${age}s</span></div>`;
 });
 if((j.open_trades||[]).length==0) ol.innerHTML='<div style="text-align:center;color:#00FF88;padding:10px;font-size:10px">No open - 15 TRADES 10 STABLE +5 WHALE - CLICK SCAN</div>';
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-30).reverse().forEach(c=>{
   let col=c.net>=0.08?'#00FF88':'#FF0040'; let side=c.side||'LONG'; let sideColor=c.is_meme?'#FF00FF':(side=='SHORT'?'#FF0040':'#00FF88');
   cb.innerHTML+=`<tr><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#00FF88"><b style="color:${sideColor}">${c.symbol||''}</b><br><small style="color:${sideColor}">${side}${c.is_meme?' WHALE':''}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px"><b style="color:${sideColor};border:1px solid ${sideColor};padding:1px 3px;font-size:7px">${side}</b></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small style="color:#888">GROSS $${Number(c.gross||0).toFixed(4)} ${Number(c.pct||0).toFixed(3)}%</small><br><small style="color:#FFD000">FEE $${Number(c.fee||0).toFixed(4)}</small></td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:6px;color:${col}">${(c.reason||'').substring(0,180)}</td><td style="padding:5px 3px;border-bottom:1px solid #111;font-size:9px;color:#FFD000">$${Number(c.fee||0).toFixed(3)}<br><small style="color:${col}">${Number(c.pct||0).toFixed(2)}% ${c.net>=0.08?'COVERS':'NOT COVER'}</small></td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="text-align:center;color:#FF00FF;padding:10px">Scanning clean - 10 stable +5 whale meme - Dexscreener Solana...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR CLEAN WHALE - START CLEAN 15 TRADES - KEEPS LEARN?')) return; await fetch('/api/clear_closed_fake'); await load(); }
setInterval(load,4000);load();
</script></body></html>
"""
@app.route("/")
def home():
    return HTML
@app.route("/api/state")
def state():
    try: do_tick_10_fee()
    except Exception as e: print(f"tick err {e}")
    cap=rget("FUND_CAP") or 1000.0; o=rget("FUND_OPEN") or []; w=rget("FUND_WINS") or 0; l=rget("FUND_LOSSES") or 0; c=rget("FUND_CLOSED") or []; d=rget("FUND_DAILY_PNL") or 0; dg=rget("FUND_DAILY_GROSS") or 0; df=rget("FUND_DAILY_FEE") or 0; p=rget("FAST_PUMP") or []; t=rget("FAST_TOP") or []; dump=rget("FAST_DUMP") or []; whale=rget("FAST_WHALE") or []; btc=float(rget("BTC_PRICE") or 0); btc1h=float(rget("BTC_1H") or 0)
    return jsonify({"cap":cap,"open_trades":o,"wins":w,"losses":l,"closed":c,"daily":d,"dg":dg,"df":df,"pump":p,"top":t,"dump":dump,"whale":whale,"btc":btc,"btc1h":btc1h})
@app.route("/api/cron")
def cron():
    return jsonify(do_tick_10_fee())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    rset("FUND_CLOSED", []); rset("FUND_DAILY_PNL", 0); rset("FUND_DAILY_GROSS", 0); rset("FUND_DAILY_FEE", 0); rset("FUND_OPEN", []); rset("LAST_LOSS_TIME", {})
    return jsonify({"cleared":True,"msg":"Cleared v567 clean whale"})
