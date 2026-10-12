from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse, random, math
app = Flask(__name__)
def env(k):
    for kk in k:
        v=os.environ.get(kk)
        if v: return v.strip().strip('"').strip("'")
    return ""
KV_URL=(env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"]) or "").rstrip("/")
if not KV_URL:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "URL" in kk and "upstash" in vv.lower():
            KV_URL=vv.strip().strip('"').strip("'").rstrip("/"); break
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
if not KV_TOKEN:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "TOKEN" in kk and "upstash" in kk.lower():
            KV_TOKEN=vv.strip().strip('"').strip("'"); break
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V823_WINNER"
POS_PCT=20.0  # 20% cap per trade, max 2 trades = 40% invested
MAXP=2
FEE=0.12; SLIP=0.05; TOTAL_FEE=0.17
MIN_SL=0.80; MAX_SL=1.80; MIN_TP=1.60; MAX_TP=4.0; MIN_RR=2.0
TIME_EXIT=90
TOP_N=30  # only top 30, not 100

def kv_get(k):
    if not KV_URL or not KV_TOKEN: return None
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=6) as r:
            d=json.loads(r.read().decode()); res=d[0].get("result") if isinstance(d,list) and d else None
            if not res: return None
            return json.loads(res) if (res.startswith("{") or res.startswith("[")) else res
    except: return None
def kv_set(k,o):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["SET",k,json.dumps(o)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=6) as r: return "OK" in r.read().decode()
    except: return False
def kv_del(k):
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r: return True
    except: return False

# ONLY WINNER COINS - top liquidity, no shitcoins
WINNER_IDS=["bitcoin","ethereum","solana","binancecoin","ripple","dogecoin","cardano","avalanche-2","shiba-inu","polkadot","chainlink","litecoin","matic-network","uniswap","cosmos","stellar","ethereum-classic","filecoin","aptos","arbitrum","optimism","injective-protocol","sui","render-token","maker","aave","the-graph","fantom","algorand","near-protocol","internet-computer","starknet"]
SYM_TO_ID={"BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin","XRP":"ripple","DOGE":"dogecoin","ADA":"cardano","AVAX":"avalanche-2","SHIB":"shiba-inu","DOT":"polkadot","LINK":"chainlink","LTC":"litecoin","MATIC":"matic-network","UNI":"uniswap","ATOM":"cosmos","XLM":"stellar","ETC":"ethereum-classic","FIL":"filecoin","APT":"aptos","ARB":"arbitrum","OP":"optimism","INJ":"injective-protocol","SUI":"sui","RNDR":"render-token","MKR":"maker","AAVE":"aave","GRT":"the-graph","FTM":"fantom","ALGO":"algorand","NEAR":"near-protocol","ICP":"internet-computer","STRK":"starknet"}
ID_TO_SYM={v:k for k,v in SYM_TO_ID.items()}

def get_top_coins():
    try:
        cached=kv_get("CG_TOP30_V823")
        if cached and isinstance(cached, dict) and cached.get("ts",0) > int(time.time())-30:
            return cached.get("data",[])
        ids=",".join(WINNER_IDS[:30])
        url=f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}&order=market_cap_desc&per_page=30&page=1&price_change_percentage=24h,7d&sparkline=false"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data=json.loads(r.read().decode())
            tickers=[]
            for c in data:
                price=c.get("current_price",0)
                vol=c.get("total_volume",0)
                if price==0 or vol < 20000000: continue  # <20M vol skip
                change24=c.get("price_change_percentage_24h",0) or 0
                change7=c.get("price_change_percentage_7d_in_currency",0) or 0
                tickers.append({
                    "symbol": (c.get("symbol","").upper())+"USDT",
                    "base": c.get("symbol","").upper(),
                    "lastPrice": str(price),
                    "price": price,
                    "vol": vol,
                    "change24": change24,
                    "change7": change7,
                    "cg_id": c.get("id","")
                })
            kv_set("CG_TOP30_V823", {"ts":int(time.time()),"data":tickers})
            return tickers
    except Exception as e:
        print(f"CG top fail {e}")
        return []

def get_chart(cg_id, days=1):
    try:
        url=f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart?vs_currency=usd&days={days}"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data=json.loads(r.read().decode())
            prices=data.get("prices",[])  # [[ts,price]]
            if len(prices)<30: return []
            closes=[p[1] for p in prices]
            # FILTER V-DROPS: remove 0, null, jumps >15% in 1 step
            filtered=[]
            for i,c in enumerate(closes):
                if c==0 or c is None: continue
                if filtered:
                    prev=filtered[-1]
                    if prev>0 and abs(c-prev)/prev > 0.15:  # >15% jump = glitch
                        # skip this glitch point, keep prev
                        continue
                filtered.append(c)
            return filtered[-60:]  # last 60 points
    except: return []

def calc_rsi(closes, period=14):
    if len(closes) < period+1: return 50
    gains=losses=0
    for i in range(1, period+1):
        diff=closes[-i]-closes[-i-1]
        if diff>=0: gains+=diff
        else: losses+=-diff
    if losses==0: return 70 if gains>0 else 50
    rs=gains/losses if losses!=0 else 0
    return 100 - (100/(1+rs))

def calc_ema(closes, period):
    if len(closes) < period: return sum(closes)/len(closes) if closes else 0
    k=2/(period+1); ema=closes[0]
    for c in closes[1:]: ema=c*k + ema*(1-k)
    return ema

def calc_atr(closes, period=14):
    if len(closes) < period+1: return closes[-1]*0.01 if closes else 0.01
    trs=[]
    for i in range(1, len(closes)):
        tr=abs(closes[i]-closes[i-1])
        trs.append(tr)
    atr=sum(trs[-period:])/period if trs else closes[-1]*0.01
    return atr/closes[-1]*100  # return %

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        # migrate from old
        old=kv_get("VENUS_V808_SHARK100")
        if old and old.get("cap",0)>0:
            cap=old.get("cap",300); closed=old.get("closed",[]); tot=len([c for c in closed if c.get("symbol","").isascii()])
            s={"cap":cap,"daily":0,"fees":0,"wins":0,"loss":0,"total":tot,"scan":0,"open":[],"closed":closed[:50],"learn":{},"peak":cap,"equity":[cap]}
            # recalc
            wins=sum(1 for c in closed if c.get("net",0)>0); loss=tot-wins
            s["wins"]=wins; s["loss"]=loss; s["total"]=tot; s["peak"]=max(cap,300)
            kv_set(STATE_KEY,s)
            return s
        s={"cap":300.0,"daily":0,"fees":0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{},"peak":300,"equity":[300]}
    s.setdefault("cap",300); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("scan",0); s.setdefault("peak",300); s.setdefault("equity",[300])
    s["open"]=[t for t in s["open"] if t.get("symbol","").isascii() and t.get("price",0)>0]
    # recalc
    closed=[c for c in s.get("closed",[]) if c.get("symbol","").isascii()]
    tot=len(closed); wins=sum(1 for c in closed if c.get("net",0)>0); loss=tot-wins
    cap=300+sum(c.get("net",0) for c in closed)
    s["cap"]=cap; s["wins"]=wins; s["loss"]=loss; s["total"]=tot
    s["peak"]=max(s.get("peak",300), cap)
    s["closed"]=closed[:100]
    kv_set(STATE_KEY,s)
    return s

def do_cron():
    state=load_state(); scan=state.get("scan",0)
    tickers=get_top_coins()
    if not tickers or len(tickers)<10:
        return {"ok":False,"error":"no tickers","scan":scan}
    # BTC trend filter
    btc=None
    for t in tickers:
        if t["base"]=="BTC": btc=t; break
    btc_change24=btc["change24"] if btc else 0
    btc_change7=btc["change7"] if btc else 0
    # Regime: if BTC down >3% last 24h, avoid longs
    regime="RANGING"
    bias="BOTH"
    if btc_change24 > 1.5 and btc_change7 > 2: regime="BULL"; bias="LONG_ONLY"
    elif btc_change24 < -1.5 and btc_change7 < -2: regime="BEAR"; bias="SHORT_ONLY"
    else: regime="RANGING"; bias="BOTH"

    open_syms=[t["symbol"] for t in state.get("open",[])]
    candidates=[]
    for t in tickers:
        base=t["base"]
        if base in open_syms: continue
        if base in ["SHIB","DOGE"]: continue  # meme too noisy
        chart=get_chart(t["cg_id"], 1)
        if len(chart)<30: continue
        rsi=calc_rsi(chart,14)
        atr_pct=calc_atr(chart,14)  # % volatility
        ema20=calc_ema(chart,20); ema50=calc_ema(chart,50)
        price=chart[-1]
        # FILTERS - winner only
        if atr_pct < 0.5 or atr_pct > 5.0: continue  # too dead or too crazy
        if t["vol"] < 30000000: continue  # need 30M vol
        # EMA trend
        above_ema = price > ema20 and ema20 > ema50
        below_ema = price < ema20 and ema20 < ema50
        side=None; reason=""
        if bias=="LONG_ONLY" or bias=="BOTH":
            if rsi < 35 and above_ema and atr_pct>0.8:
                side="LONG"; reason=f"LONG RSI {rsi:.0f}<35 + EMA up ATR {atr_pct:.1f}% BULL"
            elif rsi < 28:  # oversold mean reversion even if not above EMA
                side="LONG"; reason=f"LONG OVERSOLD RSI {rsi:.0f}<28 ATR {atr_pct:.1f}%"
        if not side and (bias=="SHORT_ONLY" or bias=="BOTH"):
            if rsi > 65 and below_ema and atr_pct>0.8:
                side="SHORT"; reason=f"SHORT RSI {rsi:.0f}>65 + EMA down ATR {atr_pct:.1f}% BEAR"
            elif rsi > 72:
                side="SHORT"; reason=f"SHORT OVERBOUGHT RSI {rsi:.0f}>72 ATR {atr_pct:.1f}%"
        if not side: continue
        # ATR based SL/TP
        sl_pct=max(MIN_SL, min(MAX_SL, atr_pct*1.5))
        tp_pct=max(MIN_TP, min(MAX_TP, sl_pct*2.2))  # RR 2.2
        if tp_pct/sl_pct < MIN_RR: tp_pct=sl_pct*MIN_RR
        # Score: lower RSI for long = higher score, higher RSI for short = higher score, plus ATR
        score=0
        if side=="LONG": score=(40 - rsi)*2 + atr_pct*5
        else: score=(rsi - 60)*2 + atr_pct*5
        score+= t["vol"]/10000000  # volume bonus
        if bias!="BOTH": score+=10
        candidates.append({"base":base,"symbol":base,"price":price,"side":side,"sl":sl_pct,"tp":tp_pct,"rsi":rsi,"atr":atr_pct,"score":score,"reason":reason,"vol":t["vol"],"change24":t["change24"],"cg_id":t["cg_id"],"chart":chart})

    candidates=sorted(candidates, key=lambda x: x["score"], reverse=True)[:3]
    closed=state.get("closed",[]); cap=state.get("cap",300); peak=state.get("peak",300)
    final=[]
    now=int(time.time())
    # close open
    for tr in state.get("open",[]):
        try:
            # get live price
            live=None
            for tk in tickers:
                if tk["base"]==tr["symbol"]: live=tk["price"]; break
            if not live: live=tr.get("price",tr.get("entry",0))
            entry=tr.get("entry",live); side=tr.get("side","LONG")
            pct=(live-entry)/entry*100 if side=="LONG" else (entry-live)/entry*100
            net=tr.get("pos",60)* (pct - TOTAL_FEE)/100
            age=now - tr.get("ts",now)
            peak_gross=max(tr.get("peak_gross",0), pct)
            tr["price"]=live; tr["pct"]=pct-TOTAL_FEE; tr["pct_gross"]=pct; tr["net"]=net; tr["age"]=age; tr["peak_gross"]=peak_gross
            should=None
            if pct >= tr.get("tp",1.6): should=f"TP {tr.get('tp',0):.1f}% WIN +${net:.2f} RSI {tr.get('rsi',0):.0f}"
            elif pct <= -tr.get("sl",0.8): should=f"SL -{tr.get('sl',0):.1f}% CUT ${net:.2f}"
            elif peak_gross >= tr.get("tp",0)*0.6 and pct <= peak_gross*0.4: should=f"TRAIL {peak_gross:.1f}%->{pct:.1f}%"
            elif age > TIME_EXIT*60 and pct < 0.3: should=f"TIME {TIME_EXIT}m"
            if net < -tr.get("pos",60)*0.015: should=f"MAXLOSS -1.5% ${net:.2f}"  # -1.5% max
            if should:
                cap+=net
                closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net,"reason":should,"pct":pct-TOTAL_FEE,"pct_gross":pct,"age":age,"pos":tr.get("pos",0),"rsi":tr.get("rsi",0),"atr":tr.get("atr",0),"rr":tr.get("rr",0)})
            else:
                final.append(tr)
        except Exception as e:
            final.append(tr)

    # open new
    for c in candidates:
        if len(final)>=MAXP: break
        if c["base"] in [t["symbol"] for t in final]: continue
        if cap < 50: break
        pos=cap * POS_PCT/100
        if pos < 20: pos=20
        if pos > cap*0.4: pos=cap*0.4
        tr={"symbol":c["base"],"side":c["side"],"entry":c["price"],"price":c["price"],"pos":pos,"ts":now,"peak_gross":0,"pct":0,"pct_gross":0,"net":0,"age":0,"sl":c["sl"],"tp":c["tp"],"rr":c["tp"]/c["sl"] if c["sl"]>0 else 2,"rsi":c["rsi"],"atr":c["atr"],"reason":c["reason"],"vol":c["vol"],"cg_id":c["cg_id"]}
        final.append(tr)

    state["open"]=final; state["closed"]=closed[:100]; state["cap"]=cap; state["scan"]=scan+1; state["peak"]=max(peak,cap)
    # equity
    eq=state.get("equity",[300]); eq.append(cap); state["equity"]=eq[-100:]
    state["regime"]=regime; state["bias"]=bias; state["btc_change24"]=btc_change24; state["btc_change7"]=btc_change7
    kv_set(STATE_KEY,state)
    return {"ok":True,"scan":scan+1,"open":len(final),"cap":cap,"candidates":len(candidates),"regime":regime,"bias":bias,"btc24":btc_change24,"btc7":btc_change7,"source":"COINGECKO WINNER TOP30"}

def render(state):
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300); peak=state.get("peak",300); scan=state.get("scan",0)
    wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); regime=state.get("regime","RANGING"); bias=state.get("bias","BOTH")
    btc24=state.get("btc_change24",0); btc7=state.get("btc_change7",0)
    wr=int(wins/tot*100) if tot>0 else 0; unreal=sum(t.get("net",0) for t in open_tr); gross_p=sum(c.get("net",0) for c in closed if c.get("net",0)>0); gross_l=sum(c.get("net",0) for c in closed if c.get("net",0)<0)
    pf=abs(gross_p/gross_l) if gross_l!=0 else (gross_p if gross_p>0 else 0); exp=(gross_p+gross_l)/tot if tot>0 else 0; dd=(peak-cap)/peak*100 if peak>0 else 0
    best=max(closed, key=lambda x: x.get("net",0)) if closed else None; worst=min(closed, key=lambda x: x.get("net",0)) if closed else None
    equity=state.get("equity",[300]); equity_js=json.dumps(equity[-60:])
    boxes=""; js=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr["side"]; entry=tr["entry"]; pos=tr["pos"]; sl=tr["sl"]; tp=tr["tp"]; rr=tr.get("rr",2)
        tp_price=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100)
        sl_price=entry*(1-sl/100) if side=="LONG" else entry*(1+sl/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        boxes+=f"""<div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'>
        <div style='display:flex;justify-content:space-between'><div><b style='color:{col}'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f} RR {rr:.1f}</b><div style='font-size:10px;color:#aaa'>ENTRY ${entry:.5f} TP ${tp_price:.5f} ({tp:.2f}%) SL ${sl_price:.5f} ({sl:.2f}%) | {tr.get('reason','')}</div></div><button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 10px'>✕</button></div>
        <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin:8px 0;text-align:center'>
        <div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>LIVE</div><div id='live-price-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('price',0):.5f}</div><div id='live-change-{sym}' style='font-size:10px'>{tr.get('pct_gross',0):+.2f}%</div><div id='live-dot-{sym}' style='font-size:8px;color:#0f8'>● CG WINNER LIVE</div></div>
        <div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>UNREAL</div><div id='live-pnl-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f}</div><div style='font-size:10px'>PEAK {tr.get('peak_gross',0):.2f}% RR {rr:.1f}</div></div>
        <div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>AGE / TP</div><div id='live-age-{sym}' style='font-size:13px;font-weight:900' data-ts='{tr.get('ts',0)}'>{int(tr.get('age',0)//60)}m</div><div style='font-size:10px;color:#0f8'>RSI {tr.get('rsi',0):.0f} ATR {tr.get('atr',0):.1f}%</div></div></div>
        <div style='position:relative;background:#000;border-radius:12px;padding:6px;border:1px solid #222'><canvas id='chart-{sym}' width='340' height='180' style='width:100%;height:180px'></canvas><div style='font-size:8px;color:#666' id='chart-info-{sym}'>WINNER FILTERED - no V drops</div></div>
        <div style='font-size:9px;color:#888;margin-top:4px'>{tr.get('reason','')} | VOL ${tr.get('vol',0)/1e6:.1f}M RR {rr:.1f} RSI {tr.get('rsi',0):.0f}</div></div>"""
        js+=f"initChart('{sym}',{entry},{tp_price},{sl_price},'{side}',{tr.get('ts',0)},{int(tr.get('age',0))},{tr.get('cg_id','bitcoin')});\n"
    if not open_tr:
        boxes=f"<div class='it' style='text-align:center;color:#666;padding:16px'>No open - WINNER TOP30 only<br>SCAN {scan} {regime} {bias} BTC 24h {btc24:+.1f}% 7d {btc7:+.1f}%<br>Need RSI <35 LONG >65 SHORT + EMA trend + ATR 0.5-5% + VOL 30M+<br>CAP ${cap:.2f} PF {pf:.2f}</div>"
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>
    body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}}
    .h{{background:linear-gradient(90deg,#00ff88,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}}
    .g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}}
    .stats{{background:#111;border:2px solid #0f8;padding:10px;margin:6px 0;border-radius:12px}}
    .it{{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:12px}}
    .btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.btn{{padding:16px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px;cursor:pointer}}.btn-cron{{background:#0f8;color:#000}}.btn-reset{{background:#f44;color:#fff}}.btn-close{{background:#fc0;color:#000}}.badge{{padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900}}.long{{background:#0f8;color:#000}}.short{{background:#f44;color:#fff}}
    </style></head><body>
    <div class='h'>VENUS v823 WINNER - SCAN #{scan} - ${cap:.2f} PEAK ${peak:.2f} DD {dd:.1f}% - {regime} {bias} BTC {btc24:+.1f}% - TOP30 ONLY - PF {pf:.2f}</div>
    <div style='background:#000;border-radius:12px;padding:8px;margin:6px 0;border:1px solid #333'><div style='font-size:9px;color:#888'>EQUITY CURVE CAP $300 → ${cap:.2f} PEAK ${peak:.2f} - WINNER STRATEGY</div><canvas id='equityChart' width='340' height='80' style='width:100%;height:80px'></canvas></div>
    <div class='btn-row'><button class='btn btn-cron' onclick='callCron()'>⚡CRON WINNER<div id='cronStat' style='font-size:10px'>TOP30 VOL 30M+ SCAN {scan}</div></button><button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN</div></button><button class='btn btn-reset' onclick='callReset()'>🔄RESET<div style='font-size:10px'>$300 WINNER</div></button></div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#fc0'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}<br>PEAK ${peak:.2f}<br>DD {dd:.1f}%</div>
    <div class='c'>TODAY<br><b style='font-size:18px;color:{"#f44" if cap<300 else "#0f8"}'>${cap-300:+.2f}</b><br>W:{wins} L:{loss} {wr}%<br>PF {pf:.2f} EXP ${exp:.3f}<br>TOTAL {tot}</div>
    <div class='c'>MARKET<br><b style='color:#0f8'>{regime}</b><br>{bias}<br>BTC 24h {btc24:+.1f}%<br>7d {btc7:+.1f}%<br>TOP30 ONLY</div></div>
    <div class='stats'><div style='color:#0f8;font-weight:900'>📈 v823 WINNER STRATEGY - {regime} BTC 24h {btc24:+.1f}% 7d {btc7:+.1f}% → {bias} - TOP30 VOL 30M+ RSI<35 LONG >65 SHORT EMA20/50 ATR 0.5-5% SL 0.8-1.8% TP 1.6-4% RR>2.0 POS 20% CAP MAX 2 - NO SHITCOINS NO V-DROPS</div>
    <div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px;font-size:10px'><div>TOTAL: <b>{tot} W:{wins} L:{loss} {wr}% PF {pf:.2f}</b></div><div>BEST: <b>{best.get('symbol','-') if best else '-'} ${best.get('net',0):+.2f} {best.get('reason','')[:20] if best else ''}</b></div><div>FEES: <b>{TOTAL_FEE}% per trade SLIP included</b></div><div>WORST: <b>{worst.get('symbol','-') if worst else '-'} ${worst.get('net',0):+.2f}</b></div></div>
    <div style='margin-top:6px;color:#0f8;font-size:10px'>✅ WINNER FIXES: 1) SL min 0.80% not 0.37% 2) TP min 1.6% RR>2.0 3) FILTER V-drops >15% jump removed 4) TOP30 only VOL 30M+ 5) RSI<35 LONG >65 SHORT + EMA trend 6) POS 20% CAP MAX2 7) TIME 90m 8) NO MANUAL CLOSE - let system close</div></div>
    <div id='openbox'>{boxes}</div>
    <div style='background:#111;padding:10px;margin:6px 0;border-radius:10px'><div style='color:#fc0;font-weight:900'>CLOSED {len(closed)} W:{wins} L:{loss} {wr}% PF {pf:.2f} EXP ${exp:.3f} PEAK ${peak:.2f} DD {dd:.1f}% - WINNER</div>"""
    for cl in closed[:30]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"; rr=cl.get("rr",0)
        html+=f"<div style='padding:5px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')} {cl.get('side','')} ${cl.get('pos',0):.0f} RR {rr:.1f} RSI {cl.get('rsi',0):.0f}</b> ${cl.get('net',0):+.2f} {cl.get('pct',0):+.2f}% | {cl.get('reason','')[:50]} | {int(cl.get('age',0)//60)}m</div>"
    html+=f"""</div><script>
const EQUITY={equity_js}; const ADMIN_KEY="{ADMIN_KEY}";
function drawEquity(){{const cv=document.getElementById('equityChart'); if(!cv||!EQUITY.length) return; const ctx=cv.getContext('2d'); const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...EQUITY)*0.999, mx=Math.max(...EQUITY)*1.001, rg=mx-mn||1; function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}} ctx.strokeStyle='#222'; for(let i=0;i<3;i++){{const y=h*0.1+i*h*0.8/2; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const y300=yF(300); ctx.strokeStyle='#444'; ctx.setLineDash([4,4]); ctx.beginPath(); ctx.moveTo(0,y300); ctx.lineTo(w,y300); ctx.stroke(); ctx.setLineDash([]); ctx.strokeStyle='#0f8'; ctx.lineWidth=2; ctx.beginPath(); EQUITY.forEach((p,i)=>{{const x=i/(EQUITY.length-1)*w, y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=EQUITY[EQUITY.length-1]; ctx.fillStyle='#fc0'; ctx.beginPath(); ctx.arc(w-4,yF(last),3,0,Math.PI*2); ctx.fill();}}
async function callCron(){{const b=document.getElementById('cronStat'); b.innerText='SCANNING WINNER TOP30...'; try{{const r=await fetch('/api/cron?key='+ADMIN_KEY); const j=await r.json(); b.innerText=j.ok ? 'OK '+j.regime+' '+j.bias+' C:'+j.candidates : j.error; setTimeout(()=>location.reload(),800);}}catch(e){{b.innerText='ERR '+e;}}}}
async function callReset(){{if(!confirm('RESET WINNER $300?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
async function closeAll(){{if(!confirm('Close all? Let system close is better!')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}
function initChart(sym,entry,tp,sl,side,ts,age,cg_id){{const cv=document.getElementById('chart-'+sym); if(!cv) return; const ctx=cv.getContext('2d'); let prices=[]; let liveHistory=[]; let lastPrice=entry; let ageSec=age; const ageEl=document.getElementById('live-age-'+sym); setInterval(()=>{{ageSec+=1; const m=Math.floor(ageSec/60); const s=ageSec%60; if(ageEl) ageEl.innerText=m+'m '+s+'s';}},1000); async function fetchPrice(){{try{{const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const j=await r.json(); if(j.price&&j.price>0){{const price=j.price; lastPrice=price; const pct=side=='LONG'?(price-entry)/entry*100:(entry-price)/entry*100; const net=60*(pct-0.17)/100; const elP=document.getElementById('live-price-'+sym); const elC=document.getElementById('live-change-'+sym); const elPn=document.getElementById('live-pnl-'+sym); const dot=document.getElementById('live-dot-'+sym); if(elP){{elP.innerText='$'+price.toFixed(5); elP.style.color=pct>=0?'#0f8':'#f44';}} if(elC){{elC.innerText=pct.toFixed(2)+'%'; elC.style.color=pct>=0?'#0f8':'#f44';}} if(elPn){{elPn.innerText=(net>=0?'+':'')+'$'+net.toFixed(2); elPn.style.color=net>=0?'#0f8':'#f44';}} if(dot) dot.innerText='● CG WINNER '+new Date().toLocaleTimeString()+' '+pct.toFixed(2)+'%'; liveHistory.push(price); if(liveHistory.length>60) liveHistory.shift(); draw();}}}}catch(e){{}}}}
  async function fetchKlines(){{try{{const r=await fetch('/api/klines?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const j=await r.json(); if(j.closes&&j.closes.length>10){{let kl=j.closes.filter(p=>p>0); kl=kl.filter((p,i)=>{{if(i==0) return true; const prev=kl[i-1]; return Math.abs(p-prev)/prev < 0.15;}}); prices=kl.slice(-40); if(liveHistory.length<5){{liveHistory=[...prices];}} draw();}}}}catch(e){{}}}} function draw(){{const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); let usePrices = liveHistory.length>5 ? liveHistory : prices; if(usePrices.length<2) usePrices=Array(20).fill(entry); let display=usePrices.map(p=>{{let raw=(p-entry)/entry*100; let amp=raw; if(Math.abs(raw)<0.6) amp=raw*4; return entry*(1+amp/100);}}); const all=[...display,entry,tp,sl]; let mn=Math.min(...all)*0.9995, mx=Math.max(...all)*1.0005; const minRange=entry*0.006; const mid=(mn+mx)/2; if((mx-mn)<minRange){{mn=mid-minRange/2; mx=mid+minRange/2;}} const rg=mx-mn||entry*0.001; function yF(p){{return h*0.85-((p-mn)/rg)*h*0.7;}} ctx.strokeStyle='#1a1a1a'; ctx.lineWidth=1; for(let i=0;i<5;i++){{const y=h*0.1+i*h*0.8/4; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const entryY=yF(entry); ctx.strokeStyle='#fc0'; ctx.lineWidth=3; ctx.beginPath(); ctx.moveTo(0,entryY); ctx.lineTo(w,entryY); ctx.stroke(); ctx.fillStyle='#fc0'; ctx.font='bold 11px monospace'; ctx.fillText('ENTRY '+entry.toFixed(5),4,entryY-5); const tpY=yF(tp); ctx.strokeStyle='#0f8'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.fillStyle='#0f8'; ctx.font='9px monospace'; ctx.fillText('TP '+tp.toFixed(5),4,tpY-3); ctx.setLineDash([]); const slY=yF(sl); ctx.strokeStyle='#f44'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,slY); ctx.lineTo(w,slY); ctx.stroke(); ctx.fillStyle='#f44'; ctx.fillText('SL '+sl.toFixed(5),4,slY+11); ctx.setLineDash([]); ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=3; ctx.beginPath(); display.forEach((p,i)=>{{const x=i/(display.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=display[display.length-1]; const ly=yF(last); ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(w-8,ly,5,0,Math.PI*2); ctx.fill(); ctx.fillStyle=last>=entry?'#0f8':'#f44'; ctx.beginPath(); ctx.arc(w-8,ly,3.5,0,Math.PI*2); ctx.fill();}}
  draw(); fetchKlines(); fetchPrice(); setInterval(fetchPrice,3000); setInterval(fetchKlines,20000);}}
window.addEventListener('load',()=>{{drawEquity(); {js}}});
</script></body></html>"""
    return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    key=request.args.get("key",""); p="/"+path
    if p.startswith("/api/liveprice"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper(); base=sym.replace("USDT",""); cg_id=SYM_TO_ID.get(base,base.lower())
        try:
            url=f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data=json.loads(r.read().decode())
                price=list(data.values())[0].get("usd",0) if data else 0
                if price>0: return Response(json.dumps({"symbol":sym,"price":price,"src":"coingecko_winner"}), mimetype="application/json")
        except: pass
        return Response(json.dumps({"price":0}), mimetype="application/json")
    if p.startswith("/api/klines"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper(); base=sym.replace("USDT",""); cg_id=SYM_TO_ID.get(base,base.lower())
        chart=get_chart(cg_id,1)
        return Response(json.dumps({"closes":chart}), mimetype="application/json")
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try: res=do_cron(); return Response(json.dumps(res), mimetype="application/json")
        except Exception as e: import traceback; return Response(json.dumps({"ok":False,"error":str(e)[:400],"trace":traceback.format_exc()[:500]}), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); kv_del("CG_TOP30_V823"); time.sleep(0.5)
        new={"cap":300.0,"daily":0,"fees":0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{},"peak":300,"equity":[300]}
        kv_set(STATE_KEY,new); return Response(json.dumps({"ok":True,"cap":300}), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        s=load_state(); cap=s.get("cap",300)
        for tr in s.get("open",[]): cap+=tr.get("net",0); s["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"CLOSE ALL {tr.get('pct',0):+.2f}% RR {tr.get('rr',0):.1f}","pct":tr.get("pct",0),"pct_gross":tr.get("pct_gross",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"rsi":tr.get("rsi",0),"rr":tr.get("rr",0)})
        s["open"]=[]; s["cap"]=cap; kv_set(STATE_KEY,s); return Response(json.dumps({"ok":True}), mimetype="application/json")
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); s=load_state(); cap=s.get("cap",300); final=[]
        for tr in s.get("open",[]):
            if tr["symbol"]==sym: cap+=tr.get("net",0); s["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"CLOSE {sym} {tr.get('pct',0):+.2f}% RR {tr.get('rr',0):.1f}","pct":tr.get("pct",0),"pct_gross":tr.get("pct_gross",0),"age":tr.get("age",0),"pos":tr.get("pos",0),"rsi":tr.get("rsi",0),"rr":tr.get("rr",0)})
            else: final.append(tr)
        s["open"]=final; s["cap"]=cap; kv_set(STATE_KEY,s); return Response(json.dumps({"ok":True}), mimetype="application/json")
    if p.startswith("/api/debug"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps(load_state(), indent=2), mimetype="application/json")
    try: st=load_state(); return Response(render(st), mimetype="text/html")
    except Exception as e: import traceback; return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:2000]}</pre></body></html>", mimetype="text/html")
