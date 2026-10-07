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
    # v566 WHALE MODE - Dexscreener Solana low cap whale buys
    whales=[]
    try:
        # Get boosted + trending Solana pairs - where whales pay to boost before pump
        urls=[
            "https://api.dexscreener.com/token-boosts/latest/v1",
            "https://api.dexscreener.com/token-boosts/top/v1",
        ]
        all_pairs=[]
        for url in urls:
            try:
                r=requests.get(url, timeout=8).json()
                # token-boosts returns list of {chainId, tokenAddress}
                if isinstance(r, list):
                    for item in r[:30]:
                        if item.get('chainId')=='solana':
                            token=item.get('tokenAddress')
                            if token:
                                # Get pairs for token
                                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{token}", timeout=8).json()
                                if pr.get('pairs'):
                                    all_pairs.extend(pr['pairs'][:2])
                time.sleep(0.2)
            except: continue
        
        # Also direct search for new solana pairs with volume
        try:
            sr=requests.get("https://api.dexscreener.com/latest/dex/search/?q=SOL", timeout=8).json()
            if sr.get('pairs'):
                all_pairs.extend(sr['pairs'][:50])
        except: pass

        seen=set()
        for p in all_pairs:
            try:
                if p.get('chainId')!='solana': continue
                base=p.get('baseToken',{}).get('symbol','').upper()
                quote=p.get('quoteToken',{}).get('symbol','')
                if base in ['SOL','USDC','USDT','WETH','WBTC','BONK','WIF','PEPE','FLOKI']: continue
                pair_addr=p.get('pairAddress')
                if not pair_addr or pair_addr in seen: continue
                seen.add(pair_addr)
                fdv=float(p.get('fdv',0) or 0)
                liq=float(p.get('liquidity',{}).get('usd',0) or 0)
                price=float(p.get('priceUsd',0) or 0)
                if price==0: continue
                if not (15000 <= liq <= 120000): continue
                if not (60000 <= fdv <= 800000): continue
                if fdv==0: continue
                # m5 volume and change - whale footprint
                vol_m5=float(p.get('volume',{}).get('m5',0) or 0)
                vol_h1=float(p.get('volume',{}).get('h1',0) or 0)
                ch_m5=float(p.get('priceChange',{}).get('m5',0) or 0)
                ch_h1=float(p.get('priceChange',{}).get('h1',0) or 0)
                ch_24=float(p.get('priceChange',{}).get('h24',0) or 0)
                txns=p.get('txns',{})
                buys_m5=int(txns.get('m5',{}).get('buys',0) or 0)
                sells_m5=int(txns.get('m5',{}).get('sells',0) or 0)
                # WHALE FILTER: volume spike + buys dominate + not too dumped
                # Whale buys $3k+ in 5m = vol_m5 > 3000 and buys > sells
                if vol_m5 < 2500: continue
                if buys_m5 < 3: continue
                if sells_m5 > 0 and buys_m5 / max(sells_m5,1) < 0.8: continue
                # Avoid rugs that already dumped -80%
                if ch_24 < -60: continue
                # Must have some momentum but not already +300% (too late)
                if ch_m5 > 200: continue
                if ch_m5 < -40: continue
                # Estimate whale buy size
                whale_est = vol_m5 * 0.6  # assume 60% of vol is whale
                # Score whale
                score = vol_m5 * (1 + ch_m5/100) + buys_m5*500
                if ch_m5>20: score*=1.5
                if ch_m5>50: score*=1.5
                whales.append({
                    "prod": f"{base}-USD",
                    "symbol": base[:12],
                    "price": price,
                    "c1": ch_m5,  # use m5 as c1
                    "c24": ch_24,
                    "cg_id": pair_addr,  # use pair address as id for price fetch
                    "fdv": fdv,
                    "liq": liq,
                    "vol_m5": vol_m5,
                    "vol_h1": vol_h1,
                    "buys_m5": buys_m5,
                    "sells_m5": sells_m5,
                    "whale_usd": whale_est,
                    "score": score,
                    "chain": "solana",
                    "pair_url": p.get('url',''),
                    "is_meme_whale": True
                })
            except: continue
        whales.sort(key=lambda x: x['score'], reverse=True)
        return whales[:10]
    except Exception as e:
        print(f"whale err {e}")
        return []

def get_price(cg_id, last=0):
    # cg_id can be coingecko id or solana pair address
    try:
        if len(cg_id)>30:  # likely solana pair address
            r=requests.get(f"https://api.dexscreener.com/latest/dex/pairs/solana/{cg_id}", timeout=5).json()
            if r.get('pair') and r['pair'].get('priceUsd'):
                p=float(r['pair']['priceUsd'])
                if p>0 and last>0 and abs(p-last)/last*100>80: return 0,"JUMP MEME"
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
            st=learn.get(sym, {'w':0,'l':0})
            tot=st.get('w',0)+st.get('l',0)
            if tot>=5 and st.get('w',0)/tot < 0.40: return True
        except: pass
        return False
    def is_blacklisted(sym):
        try:
            t=float(last_loss.get(sym,0) or 0)
            if time.time() - t < 7200: return True
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
                        cur=fm['price']; src="FAST 10 FEE"
                        break
            if cur==0: cur=last
            age=now-float(tr.get('ts',now) or now)
            pct=(cur-entry)/entry*100 if side=="LONG" else (entry-cur)/entry*100
            fee_rt=pos*0.001*2.0; gross=pos*pct/100.0; net=gross-fee_rt
            if is_meme:
                tp=15.0; hold=8.0; sl=25.0; tlimit=3600
            else:
                tp=float(tr.get('target',0.80) or 0.80); hold=0.60; sl=0.35; tlimit=1800
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
                # learn
                st=learn.get(sym, {'w':0,'l':0})
                if net>=0.08: st['w']=st.get('w',0)+1
                else: st['l']=st.get('l',0)+1; last_loss[sym]=now
                learn[sym]=st
                daily+=net; dg+=gross; df+=fee_rt
                cap+=net
            else:
                tr['last_price']=cur
                new_open.append(tr)
        except Exception as e:
            print(f"open err {e}")
            new_open.append(tr)

    # OPEN new trades - 10 stable + 5 whale
    # count how many stable open
    stable_open=len([x for x in new_open if not x.get('is_meme')])
    whale_open=len([x for x in new_open if x.get('is_meme')])
    # Fill stable to 10
    candidates=fast_pump+fast_top+fast_dump
    idx=0
    while stable_open<10 and idx<len(candidates):
        try:
            m=candidates[idx]; idx+=1
            sym=m['symbol']
            if any(x['symbol']==sym for x in new_open): continue
            if is_blacklisted(sym): continue
            if sym in last_loss and now-float(last_loss.get(sym,0) or 0)<1800: continue
            # opposite invert
            side="LONG" if m in fast_pump else "SHORT"
            if should_invert(sym):
                side="SHORT" if side=="LONG" else "LONG"
                reason=f"OPPOSITE LEARNED INVERT {sym} WR<40% - WAS {'LONG' if side=='SHORT' else 'SHORT'} NOW {side} - "
            else:
                reason=f"SMART 10 OPPOSITE {side} {'PUMP' if side=='LONG' else 'DUMP'} "
            reason+=f"{m.get('c1',0):.2f}% - FDV ${m.get('fdv',0):.0f} - COVERS FEE TP 0.80% SL 0.35% NET $0.18"
            new_open.append({
                "symbol":sym,"prod":m['prod'],"entry":m['price'],"last_price":m['price'],"pos":30,"side":side,
                "cg_id":m['cg_id'],"ts":now,"target":0.80,"reason":reason,"is_meme":False
            })
            stable_open+=1
        except: continue
    # Fill whale to 5
    widx=0
    while whale_open<5 and widx<len(fast_whale):
        try:
            m=fast_whale[widx]; widx+=1
            sym=m['symbol']
            if any(x['symbol']==sym for x in new_open): continue
            if any(x.get('cg_id')==m['cg_id'] for x in new_open): continue
            if m['fdv']<50000 or m['fdv']>900000: continue
            if m['liq']<10000: continue
            # meme always LONG - whale buying
            side="LONG"
            reason=f"WHALE MEME DETECTED {m.get('buys_m5',0)} BUYS M5 VOL ${m.get('vol_m5',0):.0f} WHALE EST ${m.get('whale_usd',0):.0f} FDV ${m.get('fdv',0):.0f} LIQ ${m.get('liq',0):.0f} {m.get('c1',0):.1f}% M5 - POTENTIAL 3000% - TP 15% SL 25%"
            new_open.append({
                "symbol":sym,"prod":m['prod'],"entry":m['price'],"last_price":m['price'],"pos":30,"side":side,
                "cg_id":m['cg_id'],"ts":now,"target":15.0,"reason":reason,"is_meme":True,"whale_usd":m.get('whale_usd',0),"fdv":m.get('fdv',0)
            })
            whale_open+=1
        except: continue

    rset("FUND_OPEN", new_open); rset("FUND_CLOSED", closed); rset("FUND_WINS", wins); rset("FUND_LOSSES", losses)
    rset("FUND_CAP", cap); rset("FUND_DAILY_PNL", daily); rset("FUND_DAILY_GROSS", dg); rset("FUND_DAILY_FEE", df)
    rset("LEARN_STATS", learn); rset("LAST_LOSS_TIME", last_loss)
    return {"open":len(new_open),"stable":stable_open,"whale":whale_open,"wins":wins,"losses":losses,"daily":daily,"cap":cap}

HTML = """
<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{background:#000;color:#0F0;font-family:monospace;font-size:8px;margin:0;padding:4px}
h1{font-size:11px;color:#FF00FF}
.card{border:1px solid #333;padding:4px;margin:2px 0}
.g{color:#00FF88}.r{color:#FF0040}.y{color:#FFD000}.o{color:#FF8800}.p{color:#FF00FF}
</style></head><body>
<h1>VENUS v566 WHALE MODE - 10 STABLE + 5 MEME WHALE - 3000% POTENTIAL - OPPOSITE LEARNED</h1>
<div id="stats"></div>
<div id="whale" class="card"><b style="color:#FF00FF">TOP 10 WHALE MEME DETECTED - WHALES BUYING NOW - 3000% POTENTIAL</b><div id="whalelist"></div></div>
<div style="display:grid;grid-template-columns:1fr 1fr"><div class="card"><b>TOP 12 LONG PUMP 0.80-2.2% OPPOSITE FILTER</b><div id="pumplist"></div></div><div class="card"><b>TOP 6 SHORT TOP +2.2%+ OPPOSITE</b><div id="toplist"></div></div></div>
<div class="card"><b>TOP 15 SHORT DUMP -0.80% to -3% OPPOSITE LEARNED</b><div id="dumplist"></div></div>
<div class="card"><b>OPEN TRADES - 10 STABLE 0.80% TP SL 0.35% + 5 WHALE MEME 15% TP SL 25% - 3000% POTENTIAL</b><div id="openlist"></div></div>
<div class="card"><b>CLOSED 25 - WHALE + STABLE - COVERS FEE + PROFIT</b><table id="closed" style="width:100%"></table></div>
<div style="margin:10px 0"><button onclick="tick()" style="background:#00FF88;color:#000;padding:8px 12px">SCAN WHALES NOW</button> <button onclick="clearFake()" style="background:#FF0040;color:#fff;padding:8px 12px">CLEAR START CLEAN</button></div>
<script>
function fmtPrice(p){ if(p>=1) return '$'+Number(p).toFixed(4); if(p>=0.01) return '$'+Number(p).toFixed(6); return '$'+Number(p).toFixed(8); }
async function load(){
 let r=await fetch('/api/state'); let j=await r.json();
 document.getElementById('stats').innerHTML=`<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px">
 <div class="card"><span class="g">FUND $${Number(j.cap||0).toFixed(2)}</span><br>DAILY <span style="color:${Number(j.daily||0)>=0?'#00FF88':'#FF0040'}">$${Number(j.daily||0).toFixed(3)}</span> GROSS $${Number(j.dg||0).toFixed(2)} FEE $${Number(j.df||0).toFixed(2)}<br>${j.wins||0}W/${j.losses||0}L WR ${j.wins+j.losses>0?Math.round(j.wins/(j.wins+j.losses)*100):0}%</div>
 <div class="card"><span class="g">OPEN ${j.open||0}/15</span> STABLE ${j.stable||0}/10 WHALE ${j.whale||0}/5<br>BTC $${Number(j.btc||0).toFixed(0)} ${Number(j.btc1h||0).toFixed(2)}% 1H<br>WHALE MODE ACTIVE - SCANNING SOLANA</div></div>`;
 let wl=document.getElementById('whalelist'); wl.innerHTML='';
 (j.whale_list||[]).forEach((m,i)=>{
   wl.innerHTML+=`<div style="border:1px solid #FF00FF;padding:3px;margin:2px 0"><b style="color:#FF00FF">#${i+1} ${m.symbol} $${Number(m.price).toFixed(8)} +${Number(m.c1).toFixed(1)}% M5</b><br><small style="color:#FFD000">WHALE $${Number(m.whale_usd||0).toFixed(0)} BOUGHT ${m.buys_m5} BUYS VOL M5 $${Number(m.vol_m5||0).toFixed(0)} LIQ $${Number(m.liq||0).toFixed(0)} FDV $${Number(m.fdv||0).toFixed(0)} POTENTIAL 3000%</small><br><small style="color:#888">${m.pair_url||''}</small></div>`;
 });
 if((j.whale_list||[]).length==0) wl.innerHTML='<div style="color:#666">No whale buys now - scanning Dexscreener Solana every 25s - whales buy $3k+ in low cap < $800k FDV - wait for signal</div>';
 let pl=document.getElementById('pumplist'); pl.innerHTML='';
 (j.pump||[]).forEach((m,i)=>{ pl.innerHTML+=`<div style="border:1px solid #00FF88;padding:2px;margin:1px">#${i+1} LONG ${m.symbol} +${Number(m.c1).toFixed(2)}%</div>`; });
 let tl=document.getElementById('toplist'); tl.innerHTML='';
 (j.top||[]).forEach((m,i)=>{ tl.innerHTML+=`<div style="border:1px solid #FF8800;padding:2px;margin:1px">#${i+1} SHORT TOP ${m.symbol} +${Number(m.c1).toFixed(2)}%</div>`; });
 let dl=document.getElementById('dumplist'); dl.innerHTML='';
 (j.dump||[]).forEach((m,i)=>{ dl.innerHTML+=`<div style="border:1px solid #FF0040;padding:2px;margin:1px">#${i+1} SHORT ${m.symbol} ${Number(m.c1).toFixed(2)}%</div>`; });
 let ol=document.getElementById('openlist'); ol.innerHTML='';
 (j.open_trades||[]).forEach(t=>{
   let age=Math.floor(Date.now()/1000 - (t.ts||Date.now()/1000));
   let isMeme=t.is_meme; let col=isMeme?'#FF00FF':(t.side=='LONG'?'#00FF88':'#FF0040');
   ol.innerHTML+=`<div style="display:grid;grid-template-columns:70px 40px 70px 1fr 50px 30px;border-bottom:1px solid #111;padding:3px"><span style="color:${col}"><b>${t.symbol||''}</b><br><small>${isMeme?'WHALE MEME':'STABLE'}</small></span><span style="color:${col};border:1px solid ${col};padding:1px 2px;font-size:7px">${t.side}</span><span>${fmtPrice(t.entry)}<br><small>${fmtPrice(t.last_price)}</small><br><small>$${t.pos} $${(t.pos*0.002).toFixed(3)}</small></span><span style="font-size:6px;color:#888">${(t.reason||'').substring(0,120)}</span><span style="font-size:7px;color:${col}">TP ${t.target}%<br>SL ${isMeme?'25%':'0.35%'}</span><span>${age}s</span></div>`;
 });
 let cb=document.getElementById('closed');cb.innerHTML='';
 (j.closed||[]).slice(-30).reverse().forEach(c=>{
   let col=c.net>=0.08?'#00FF88':'#FF0040'; let isM=c.is_meme;
   cb.innerHTML+=`<tr><td style="border-bottom:1px solid #111;padding:3px;font-size:8px;color:${isM?'#FF00FF':'#00FF88'}"><b>${c.symbol||''}</b><br><small>${c.side}${isM?' WHALE':''}</small></td><td style="border-bottom:1px solid #111;padding:3px;font-size:8px;color:${col}">${c.net>=0?'+':''}$${Number(c.net).toFixed(4)}<br><small>${Number(c.pct||0).toFixed(2)}%</small></td><td style="border-bottom:1px solid #111;padding:3px;font-size:6px;color:#888">${(c.reason||'').substring(0,140)}</td></tr>`;
 });
}
async function tick(){ document.getElementById('openlist').innerHTML='<div style="color:#FF00FF;padding:10px">Scanning Dexscreener Solana whales - 10 stable + 5 whale meme...</div>'; await fetch('/api/cron'); await load(); }
async function clearFake(){ if(!confirm('CLEAR v566 WHALE MODE - KEEPS LEARNED STATS?')) return; await fetch('/api/clear_closed_fake'); await load(); }
setInterval(load,5000);load();
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
    stable=len([x for x in o if not x.get('is_meme')]); wh=len([x for x in o if x.get('is_meme')])
    return jsonify({"cap":cap,"open":len(o),"stable":stable,"whale":wh,"open_trades":o,"wins":w,"losses":l,"closed":c,"daily":d,"dg":dg,"df":df,"pump":p,"top":t,"dump":dump,"whale_list":whale,"btc":btc,"btc1h":btc1h})
@app.route("/api/cron")
def cron():
    return jsonify(do_tick_10_fee())
@app.route("/api/clear_closed_fake")
def clear_closed_fake():
    rset("FUND_CLOSED", []); rset("FUND_DAILY_PNL", 0); rset("FUND_DAILY_GROSS", 0); rset("FUND_DAILY_FEE", 0); rset("FUND_OPEN", []); rset("LAST_LOSS_TIME", {})
    return jsonify({"cleared":True,"msg":"Cleared v566 whale mode"})
