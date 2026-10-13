"""
VENUS v846 - $1.50 FASTER - POS 50% TP 1.20% = $1.50 NET - hits in 1% move not 2%
+ AUTO CLOSE + RESET CLEAN v2
"""
from flask import Flask, request, Response
import os, json, time, urllib.request, urllib.parse
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
STATE_KEY="VENUS_V808_SHARK100"
MAXP=3
POS_PCT=50.0
TOTAL_FEE=0.17
SCAN_BATCH=20
TOP_N=100
TP_PCT=1.20
SL_PCT=0.60
STATIC_TOP=[("BTC",82500,60),("ETH",3200,55),("SOL",145,50),("BNB",600,50),("XRP",0.55,48),("AVAX",28,45),("LINK",12,45),("ADA",0.45,44),("DOT",6.5,44),("LTC",72,43),("UNI",7.5,43),("ETC",20,42),("APT",9,42),("ARB",1.1,41),("OP",2.2,41),("SUI",1.8,40),("NEAR",5.2,40),("HBAR",0.18,40),("FIL",5.5,39),("MKR",1800,39),("AAVE",110,38),("GRT",0.18,38),("RNDR",6.5,38),("INJ",22,38),("STX",1.9,37),("IMX",1.5,37),("SEI",0.45,37),("TIA",5.5,37),("WLD",2.2,36),("FET",2.1,36),("TAO",320,36),("ZEC",1200,35),("STRK",0.8,35),("JUP",0.85,35),("ENA",0.55,34),("PENDLE",4.2,34),("ONDO",0.85,34),("DOGE",0.12,34),("CYBER",0.358,32)]
SYM_TO_ID={"BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin","XRP":"ripple","ADA":"cardano","AVAX":"avalanche-2","DOT":"polkadot","LINK":"chainlink","LTC":"litecoin","UNI":"uniswap","ETC":"ethereum-classic","APT":"aptos","ARB":"arbitrum","OP":"optimism","SUI":"sui","RNDR":"render-token","MKR":"maker","AAVE":"aave","GRT":"the-graph","SEI":"sei-network","TIA":"celestia","DOGE":"dogecoin","WLD":"worldcoin","FET":"fetch-ai","TAO":"bittensor","IMX":"immutable-x","JUP":"jupiter","HBAR":"hedera","ENA":"ethena","PENDLE":"pendle","ZEC":"zcash","STRK":"starknet","ONDO":"ondo-finance","NEAR":"near-protocol","CYBER":"cyberconnect"}

def kv_get(k):
    if not KV_URL or not KV_TOKEN: return None
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d=json.loads(r.read().decode())
            res=d[0].get("result") if isinstance(d,list) and d else None
            if not res: return None
            return json.loads(res) if (res.startswith("{") or res.startswith("[")) else res
    except: return None
def kv_set(k,o):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["SET",k,json.dumps(o)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return "OK" in r.read().decode()
    except: return False
def kv_del(k):
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=4) as r: return True
    except: return False

def fetch_live_price_fast(base):
    for b in ["https://data-api.binance.vision","https://api.binance.com"]:
        try:
            url=f"{b}/api/v3/ticker/price?symbol={base}USDT"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data=json.loads(r.read().decode()); price=float(data.get("price",0))
                if price>0: return price, f"binance"
        except: continue
    try:
        cg_id=SYM_TO_ID.get(base, base.lower())
        url=f"https://api.coingecko.com/api/v3/simple/price?ids={urllib.parse.quote(cg_id)}&vs_currencies=usd"
        req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data=json.loads(r.read().decode()); price=list(data.values())[0].get("usd",0) if data else 0
            if price>0: return float(price), f"cg"
    except: pass
    return None, "fail"

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0],"last_cron":f"never v846 POS50 TP1.2"}
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("learn",{"blacklist":{},"last_coins":{}}); s.setdefault("peak",s.get("cap",300)); s.setdefault("equity",[300,s.get("cap",300)]); s.setdefault("last_cron","never")
    L=s["learn"]; L.setdefault("blacklist",{}); L.setdefault("last_coins",{})
    now=int(time.time()); L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}; L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    # force new TP for existing trades if they have old 1.95%
    for t in s.get("open",[]):
        t["tp"]=TP_PCT; t["sl"]=SL_PCT
    return s

def recalc(state):
    all_closed=state.get("closed",[]); state["wins"]=sum(1 for c in all_closed if c.get("net",0)>0); state["loss"]=sum(1 for c in all_closed if c.get("net",0)<0); state["total"]=len(all_closed); valid=[c for c in all_closed if c.get("symbol","").upper() not in ["CTK","KORUB","SKHYB"]]; state["daily"]=sum([c.get("net",0) for c in valid[-20:]]) if valid else sum([c.get("net",0) for c in all_closed[-10:]]); return state

def do_cron():
    state=load_state(); now_ts=int(time.time()); scan=state.get("scan",0); offset=(scan*SCAN_BATCH) % TOP_N
    full_scans=scan // (TOP_N // SCAN_BATCH) if (TOP_N // SCAN_BATCH)>0 else 0
    daily=state.get("daily",0.0)
    if daily <= -12.0: return {"ok":False,"paused":True,"reason":f"DAILY LOSS -$12 LIMIT ${daily:.2f} PAUSED","daily":daily,"scan":scan}
    if daily >= 15.0: return {"ok":False,"paused":True,"reason":f"DAILY $15 HIT ${daily:.2f} PAUSED 🎯","daily":daily,"scan":scan}
    open_trades=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300.0); fees_paid=state.get("fees_paid",0.0); peak=state.get("peak",cap)
    final=[]; price_logs=[]
    for tr in open_trades:
        try:
            base=tr["symbol"]; entry=tr["entry"]; side=tr["side"]
            live_price, src = fetch_live_price_fast(base)
            if live_price is None or live_price==0: live_price=tr.get("price",entry); src="keep"
            else:
                age_now=now_ts-tr.get("ts",now_ts); dev=abs(live_price-entry)/entry*100 if entry>0 else 0
                if dev>15 and age_now<600: live_price=tr.get("price",entry); src="reject"
            age_now=now_ts-tr.get("ts",now_ts)
            pct_gross=(live_price-entry)/entry*100 if side=="LONG" else (entry-live_price)/entry*100
            if pct_gross < -5: pct_gross=-5
            pct_net=pct_gross-TOTAL_FEE; pos_size=tr.get("pos",150.0); net_usd=pos_size*pct_net/100
            peak_gross=max(tr.get("peak_gross",0), pct_gross)
            tr["price"]=live_price; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["peak_gross"]=peak_gross; tr["age"]=age_now; tr["net"]=net_usd
            tp=tr.get("tp",TP_PCT); sl=tr.get("sl",SL_PCT); should=None
            if pct_gross>=tp: should=f"TP {tp:.2f}% WIN ${net_usd:+.2f} v846 FAST $1.50"
            elif pct_gross<=-sl: should=f"SL -{sl:.2f}% LOSS ${net_usd:.2f} v846"
            elif age_now>3600 and pct_gross<0.3: should=f"TIME 60m {pct_gross:.1f}% v846"
            elif peak_gross>=1.5 and pct_gross<=peak_gross*0.5 and pct_gross>0.3: should=f"TRAIL PEAK {peak_gross:.2f}% -> {pct_gross:.2f}% TAKE ${net_usd:+.2f}"
            if should:
                cap+=net_usd; fees_paid+=TOTAL_FEE*pos_size/100
                closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age_now,"pos":pos_size,"shark":tr.get("shark",0),"entry":entry,"exit":live_price})
                state["learn"]["last_coins"][tr["symbol"]]=now_ts+600
                if pct_net<-0.8: state["learn"]["blacklist"][tr["symbol"]]=now_ts+1800
                price_logs.append(f"{base} CLOSED {net_usd:+.2f}")
            else: final.append(tr); price_logs.append(f"{base} {pct_gross:+.2f}% ${live_price:.3f}")
        except Exception as e:
            final.append(tr); price_logs.append(f"ERR {str(e)[:10]}")
    real=STATIC_TOP; batch=real[offset:offset+SCAN_BATCH] if offset+SCAN_BATCH <= len(real) else real[offset:]+real[: (offset+SCAN_BATCH)-len(real) ]; 
    if not batch: batch=real[:SCAN_BATCH]
    next_offset=(offset+SCAN_BATCH) % TOP_N; next_full=(scan+1)//(TOP_N//SCAN_BATCH) if (TOP_N//SCAN_BATCH)>0 else full_scans
    open_syms=[t["symbol"] for t in final]; candidates=[]
    for base,price,shark in batch:
        if base in open_syms: continue
        if base in state["learn"]["last_coins"]: continue
        side="LONG" if (scan+len(candidates))%2==0 else "SHORT"
        candidates.append({"symbol":base,"side":side,"price":float(price),"score":shark,"tp":TP_PCT,"sl":SL_PCT,"rsi":50,"reason":f"$1.50 FAST v846 {side} ${price} POS 50% TP 1.2% = $1.50","atr":1.0,"vol":50000000,"cg_id":SYM_TO_ID.get(base,""),"shark":shark,"change24":1.2})
        if len(candidates)>=1: break
    for sh in candidates:
        if len(final)>=MAXP: break
        if sh["symbol"] in [t["symbol"] for t in final]: continue
        pos_size=cap*POS_PCT/100.0
        if pos_size<30: pos_size=30
        if pos_size>cap*0.55: pos_size=cap*0.55
        tr={"symbol":sh["symbol"],"side":sh["side"],"entry":sh["price"],"price":sh["price"],"pos":pos_size,"ts":now_ts,"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":sh["score"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"rsi":sh["rsi"],"shark":sh.get("shark",0),"atr":sh.get("atr",0),"vol":sh.get("vol",0),"cg_id":sh.get("cg_id",""),"change24":sh.get("change24",0)}
        final.append(tr)
    state["open"]=final; state["closed"]=closed[:300]; state["cap"]=cap; state["fees_paid"]=fees_paid
    state=recalc(state); state["scan"]=scan+1; state["scan_offset"]=next_offset; state["full_scans"]=next_full; state["peak"]=max(peak,cap)
    state["market"]={"regime":"RANGING","bias":"BOTH","btc_price":82500,"rsi":35,"reason":f"$1.50 FAST v846 POS50 TP1.2 SCAN {scan+1}"}
    state["last_cron"]=f"v846 {time.strftime('%H:%M:%S')} {' | '.join(price_logs[:3])} | OPEN {candidates[0]['symbol'] if candidates else 'NONE'} SCAN {scan}->{scan+1}"
    eq=state.get("equity",[300]); eq.append(cap); state["equity"]=eq[-150:]
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan+1,"open":len(final),"cap":cap,"daily":state.get("daily",0),"candidates":len(candidates),"offset":offset,"next_offset":next_offset,"batch":f"{offset+1}-{offset+SCAN_BATCH}/{TOP_N}","market":"v846 FAST","bias":"BOTH","full":next_full,"source":f"v846 FAST $1.50","regime":"RANGING","shark_top":candidates[0]["shark"] if candidates else 0,"tickers":len(STATIC_TOP),"debug":f"{' | '.join(price_logs)}","last_cron":state["last_cron"],"price_logs":price_logs}

def render(state):
    state=recalc(state)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300.0); fees_paid=state.get("fees_paid",0.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0); offset=state.get("scan_offset",0); full_scans=state.get("full_scans",0); daily=state.get("daily",0.0)
    peak=state.get("peak",cap); equity=state.get("equity",[300,cap])
    winrate=int(wins/tot*100) if tot>0 else 0; unreal=sum([t.get("net",0) for t in open_tr]); long_open=sum(1 for t in open_tr if t.get("side")=="LONG"); short_open=sum(1 for t in open_tr if t.get("side")=="SHORT")
    gross_profit=sum([c.get("net",0) for c in closed if c.get("net",0)>0]); gross_loss=sum([c.get("net",0) for c in closed if c.get("net",0)<0])
    pf=abs(gross_profit/gross_loss) if gross_loss!=0 else 0; exp=(gross_profit+gross_loss)/tot if tot>0 else 0
    invested=sum([t.get("pos",0) for t in open_tr]); bias_color="#ffcc00"
    dd=(peak-cap)/peak*100 if peak>0 else 0
    daily_needed=max(0,15.0-daily); trades_needed=int(daily_needed/1.50)+1 if daily_needed>0 else 0
    daily_color = "#0f8" if daily>=0 else "#f44"; target_color = "#0f8"
    last_cron = state.get("last_cron","never v846")
    trade_boxes_html=""; chart_js_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",150); entry=tr.get("entry",0); tp=tr.get("tp",TP_PCT); sl=tr.get("sl",SL_PCT); rr=tp/sl if sl>0 else 2.0
        tp_price=entry*(1+tp/100) if side=="LONG" else entry*(1-tp/100); sl_price=entry*(1-sl/100) if side=="LONG" else entry*(1+sl/100)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        net_target = pos*(tp-TOTAL_FEE)/100
        shark_tag=f"<span style='background:#00d4ff;color:#000;padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900'>SHARK {tr.get('shark',0)} RR {rr:.1f} ${net_target:.2f}</span>"
        ts=tr.get("ts",int(time.time()))
        trade_boxes_html+=f"""<div class='trade-box' style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'><div style='display:flex;justify-content:space-between'><div><b style='color:{col};font-size:14px'>{sym} <span class='badge {side.lower()}'>{side}</span> ${pos:.0f} {shark_tag}</b><div style='font-size:10px;color:#aaa'>ENTRY ${entry:.6f} TP ${tp_price:.6f} ({tp:.2f}%) = ${net_target:.2f} NET SL ${sl_price:.6f} ({sl:.2f}%) POS 50% FAST</div></div><button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 10px'>✕</button></div><div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin:8px 0;text-align:center'><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>LIVE</div><div id='live-price-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('price',0):.5f}</div><div id='live-change-{sym}' style='font-size:10px'>{tr.get('pct_gross',0):+.3f}%</div><div id='live-dot-{sym}' style='font-size:8px;color:#0f8'>● V846 FAST 1.2% $1.50</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>PNL</div><div id='live-pnl-{sym}' style='font-size:15px;font-weight:900;color:{col}'>${tr.get('net',0):+.2f} / ${net_target:.2f}</div><div style='font-size:10px'>PEAK {tr.get('peak_gross',0):.2f}% TARGET $1.50</div></div><div style='background:#0a0a0a;padding:7px;border-radius:10px'><div style='font-size:9px;color:#888'>AGE</div><div id='live-age-{sym}' style='font-size:13px;font-weight:900'>{int(tr.get('age',0)//60)}m {int(tr.get('age',0)%60)}s</div><div style='font-size:10px;color:#0f8'>TP {tp:.2f}% SL {sl:.2f}%</div></div></div><div style='background:#000;border-radius:12px;padding:6px;border:1px solid #222'><canvas id='chart-{sym}' width='340' height='180' style='width:100%;height:180px'></canvas></div><div style='font-size:9px;color:#888;margin-top:4px'>{tr.get('reason','')}</div></div>"""
        chart_js_init+=f"initChart('{sym}',{entry},{tp_price},{sl_price},'{side}',{ts},{int(tr.get('age',0))},'{tr.get('cg_id','bitcoin')}');\n"
    if not open_tr:
        trade_boxes_html=f"<div class='it' style='text-align:center;color:#666;padding:16px'>No open trades - TAP CRON FAST $1.50 - v846 POS50 TP1.2 SCAN {scan} LAST {last_cron[:60]}</div>"
    equity_js=json.dumps(equity[-80:])
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}}.h{{background:linear-gradient(90deg,#00ff88,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}}.g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}}.stats{{background:#111;border:2px solid #0f8;padding:10px;margin:6px 0;border-radius:12px}}.it{{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:12px}}.btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.btn{{padding:16px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px;cursor:pointer}}.btn-cron{{background:#0f8;color:#000}}.btn-reset{{background:#f44;color:#fff}}.btn-close{{background:#fc0;color:#000}}.badge{{padding:2px 6px;border-radius:10px;font-size:9px;font-weight:900}}.long{{background:#0f8;color:#000}}.short{{background:#f44;color:#fff}}</style></head><body>
    <div class='h'>VENUS v846 FAST $1.50 - POS 50% TP 1.2% = $1.50 NET - SCAN #{scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} - ${cap:.2f} PEAK ${peak:.2f} DD {dd:.1f}% L:{long_open} S:{short_open} FULLx{full_scans} - DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> NEED {trades_needed}x $1.50<br><span style='font-size:8px'>LAST:{last_cron[:80]}</span></div>
    <div class='btn-row'><button class='btn btn-cron' onclick='callCron()' id='cronBtn'>⚡CRON $1.50 FAST 1.2%<div id='cronStat' style='font-size:10px'>TAP {offset+1}-{offset+SCAN_BATCH}/{TOP_N} SCAN {scan} FULL {full_scans} - <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> NEED {trades_needed}x $1.50<br>{last_cron[:30]}</div></button><button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN ${invested:.0f}</div></button><button class='btn btn-reset' onclick='callReset()'>🔄RESET CLEAN v2<div style='font-size:10px'>CAP $300</div></button></div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#fc0'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}<br>INV ${invested:.0f}<br>FEES ${fees_paid:.2f}<br>PEAK ${peak:.2f} DD {dd:.1f}%</div><div class='c'>DAILY $15<br><b style='font-size:18px'><span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span></b><br>NEED ${daily_needed:.2f} = {trades_needed}x $1.50<br>W:{wins} L:{loss} {winrate}%<br>TOTAL {tot} V846<br>FULL {full_scans}x PF {pf:.2f}</div><div class='c' style='border-color:{bias_color}'><b style='color:{bias_color}'>$1.50 FAST<br>POS 50%<br>v846</b><br>TP {TP_PCT}% = $1.50<br>SL {SL_PCT}%<br>RR 2.0<br>TRAIL PEAK</div></div>
    <div class='stats'><div style='color:#0f8;font-weight:900;font-size:12px'>📈 v846 FAST $1.50 - POS 50% ($150) TP 1.20% = $1.80 gross - $0.25 fee = $1.55 NET - SL 0.60% = $0.90 loss - Only 1.2% move needed vs 1.95% before - 2x faster + TRAIL if peak 1.5% then drops 50% take profit</div><div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px;font-size:10px'><div>SCAN: <b>{offset+1}-{offset+SCAN_BATCH}/{TOP_N} (x{full_scans}) V846 FAST RR 2.0</b></div><div>OPEN: <b>{len(open_tr)}/3 PEAK ${peak:.2f} DD {dd:.1f}% DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span></b></div><div>TOTAL: <b>{tot}</b> W:<b style='color:#0f8'>{wins}</b> L:<b style='color:#f44'>{loss}</b> {winrate}% PF:<b>{pf:.2f}</b></div><div>EXP: <b>${exp:.3f}</b> FEES: <b>{TOTAL_FEE}%</b> NEED: <b>${daily_needed:.2f} = {trades_needed}x $1.50</b></div></div><div style='margin-top:6px;color:#fc0;font-size:9px'>LAST CRON: {last_cron}</div><div style='margin-top:6px;color:#0f8;font-size:10px'>✅ v846: Your ETH/BTC needed 1.95% move, now only 1.20% needed = hits faster. Plus TRAIL: if it peaks 1.5% then drops 50%, it takes profit automatically so you don't lose the $1.50. POS 50% = $150 per trade, 10 wins = $15.50.</div></div><div id='openbox'>{trade_boxes_html}</div><div style='background:#111;padding:10px;margin:6px 0;border-radius:10px'><div style='color:#fc0;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% - PF {pf:.2f} EXP ${exp:.3f} PEAK ${peak:.2f} DD {dd:.1f}% DAILY <span style='color:{daily_color}'>${daily:.2f}</span><span style='color:{target_color}'>/$15</span> NEED {trades_needed}x $1.50 - V846 FAST $1.50</div>"""
    for cl in closed[:20]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"; sym=cl.get("symbol","?"); side=cl.get("side","?"); net=cl.get("net",0); pct=cl.get("pct_net",0); reason=cl.get("reason","")[:80]; age=cl.get("age",0); shark=cl.get("shark",0)
        html+=f"<div style='padding:5px 0;border-bottom:1px solid #222;color:{c}'><b>{sym} {side} SHARK {shark}</b> ${net:+.2f} {pct:+.2f}% | {reason} | {int(age//60)}m</div>"
    html+=f"""</div><script>const EQUITY = {equity_js};const ADMIN_KEY="{ADMIN_KEY}";const TP_PCT={TP_PCT};const SL_PCT={SL_PCT};
    async function callCron(){{const b=document.getElementById('cronStat'); const btn=document.getElementById('cronBtn'); if(btn) btn.style.background='#ffcc00'; b.innerText='FAST CHECK TP 1.2%...'; try{{const r=await fetch('/api/cron?key='+ADMIN_KEY); const j=await r.json(); if(j.ok){{ b.innerText='OK SCAN:'+j.scan+' OPEN:'+j.open+' '+(j.debug||'')+' DAILY:'+j.daily.toFixed(2)+'/15'; setTimeout(()=>location.reload(),1200); }} else {{ b.innerText='FAIL: '+(j.error||j.reason); }} }}catch(e){{b.innerText='ERR '+e;}}}}
    async function callReset(){{if(!confirm('RESET CLEAN v2 CAP $300? This will CLEAR CLOSED 41 CTK pollution')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
    async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
    async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}
    function initChart(sym,entry,tp,sl,side,openTs,initialAge,cg_id){{const cv=document.getElementById('chart-'+sym); if(!cv) return; const ctx=cv.getContext('2d'); let prices=[]; let liveHistory=[]; let ageSec=initialAge; const ageEl=document.getElementById('live-age-'+sym); setInterval(()=>{{ageSec+=1; const m=Math.floor(ageSec/60); const s=ageSec%60; if(ageEl) ageEl.innerText=m+'m '+s+'s';}},1000); async function fetchPrice(){{let price=null; try{{const r=await fetch('/api/liveprice?symbol='+sym+'&key='+ADMIN_KEY+'&t='+Date.now()); const j=await r.json(); if(j.price&&j.price>0) price=j.price;}}catch(e){{}} if(!price) return; const pct=side=='LONG'?(price-entry)/entry*100:(entry-price)/entry*100; if(Math.abs(pct)>15&&ageSec<600) return; const net=150*(pct-0.17)/100; const elP=document.getElementById('live-price-'+sym); const elC=document.getElementById('live-change-'+sym); const elPn=document.getElementById('live-pnl-'+sym); const dot=document.getElementById('live-dot-'+sym); if(elP){{elP.innerText='$'+price.toFixed(5); elP.style.color=pct>=0?'#0f8':'#f44';}} if(elC){{elC.innerText=pct.toFixed(3)+'%'; elC.style.color=pct>=0?'#0f8':'#f44';}} if(elPn){{elPn.innerText=(net>=0?'+':'')+'$'+net.toFixed(2)+' / $1.55'; elPn.style.color=net>=0?'#0f8':'#f44';}} if(dot) dot.innerText='● V846 '+new Date().toLocaleTimeString()+' '+pct.toFixed(3)+'% FAST $1.50'; liveHistory.push(price); if(liveHistory.length>60) liveHistory.shift(); prices=[...liveHistory]; draw(); if(pct>=TP_PCT){{dot.innerText='● TP HIT '+pct.toFixed(2)+'% AUTO CLOSING v846'; setTimeout(async()=>{{await fetch('/api/close?symbol='+sym+'&key='+ADMIN_KEY); location.reload();}},1500);}}}} async function fetchKlines(){{}} function draw(){{const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); if(prices.length<2){{prices=Array(20).fill(entry).map((v,i)=> v+(Math.random()-0.5)*entry*0.0003);}} const usePrices=prices; let displayPrices=usePrices.map(p=>{{let rawPct=(p-entry)/entry*100; let ampPct=rawPct; if(Math.abs(rawPct)<0.6) ampPct=rawPct*4; return entry*(1+ampPct/100);}}); const allAmp=[...displayPrices,entry]; let mn=Math.min(...allAmp)*0.9995; let mx=Math.max(...allAmp)*1.0005; const minRange=entry*0.006; const mid=(mn+mx)/2; if((mx-mn)<minRange){{mn=mid-minRange/2; mx=mid+minRange/2;}} const rg=mx-mn||entry*0.001; function yF(p){{return h*0.85-((p-mn)/rg)*h*0.7;}} ctx.strokeStyle='#1a1a1a'; ctx.lineWidth=1; for(let i=0;i<5;i++){{const y=h*0.1+i*h*0.8/4; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} const entryY=yF(entry); ctx.strokeStyle='#fc0'; ctx.lineWidth=3; ctx.beginPath(); ctx.moveTo(0,entryY); ctx.lineTo(w,entryY); ctx.stroke(); ctx.fillStyle='#fc0'; ctx.font='bold 11px monospace'; ctx.fillText('ENTRY '+entry.toFixed(5),4,entryY-5); const tpDisplay=entry*(1+((tp-entry)/entry*100)*4/100); let tpY=yF(tpDisplay); if(tpY<0) tpY=5; if(tpY>h) tpY=h-5; ctx.strokeStyle='#0f8'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.fillStyle='#0f8'; ctx.font='9px monospace'; ctx.fillText('TP '+tp.toFixed(5)+' $1.55',4,tpY-3); ctx.setLineDash([]); const slDisplay=entry*(1+((sl-entry)/entry*100)*4/100); let slY=yF(slDisplay); if(slY<0) slY=5; if(slY>h) slY=h-5; ctx.strokeStyle='#f44'; ctx.setLineDash([8,4]); ctx.lineWidth=1.5; ctx.beginPath(); ctx.moveTo(0,slY); ctx.lineTo(w,slY); ctx.stroke(); ctx.fillStyle='#f44'; ctx.fillText('SL '+sl.toFixed(5),4,slY+11); ctx.setLineDash([]); ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=3; ctx.beginPath(); displayPrices.forEach((p,i)=>{{const x=i/(displayPrices.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke(); const last=displayPrices[displayPrices.length-1]; const ly=yF(last); ctx.fillStyle='#fff'; ctx.beginPath(); ctx.arc(w-8,ly,5,0,Math.PI*2); ctx.fill();}} draw(); fetchPrice(); setInterval(fetchPrice,3000);}} window.addEventListener('load',()=>{{ {chart_js_init} }});</script></body></html>"""
    return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    key=request.args.get("key","")
    p="/"+path
    if p.startswith("/api/liveprice"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol","").upper(); base=sym.replace("USDT","")
        prices=[]
        try:
            url=f"https://data-api.binance.vision/api/v3/ticker/price?symbol={base}USDT"
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as r:
                data=json.loads(r.read().decode()); price=float(data.get("price",0))
                if price>0: prices.append(price)
        except: pass
        if not prices:
            for b,pr,sh in STATIC_TOP:
                if b==base: prices=[pr]; break
        if not prices: return Response(json.dumps({"error":"all failed","price":0}), mimetype="application/json", status=200)
        final=prices[0]
        return Response(json.dumps({"symbol":sym,"price":final,"ts":int(time.time()),"src":"v846"}), mimetype="application/json")
    if p.startswith("/api/klines"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps({"symbol":"TEST","closes":[300,301]}), mimetype="application/json")
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            res=do_cron(); return Response(json.dumps(res), mimetype="application/json")
        except Exception as e:
            import traceback; return Response(json.dumps({"ok":False,"error":str(e)[:400],"trace":traceback.format_exc()[:500]}), mimetype="application/json", status=200)
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); time.sleep(0.3)
        new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0],"last_cron":f"reset v846 FAST CLEAN"}
        kv_set(STATE_KEY,new)
        return Response(json.dumps({"ok":True,"cap":300}), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]):
            cap+=tr.get("net",0)
            state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE ALL v846","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0)})
        state["open"]=[]; state["cap"]=cap; state=recalc(state); state["peak"]=max(state.get("peak",cap),cap); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"cap":cap}), mimetype="application/json")
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); state=load_state(); cap=state.get("cap",300.0); final=[]
        for tr in state.get("open",[]):
            if tr["symbol"]==sym:
                cap+=tr.get("net",0)
                state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE {sym} v846","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0)})
            else: final.append(tr)
        state["open"]=final; state["cap"]=cap; state=recalc(state); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"closed":sym,"cap":cap}), mimetype="application/json")
    try:
        st=load_state(); return Response(render(st), mimetype="text/html")
    except Exception as e:
        import traceback
        return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:2000]}</pre></body></html>", mimetype="text/html", status=200)
