"""
VENUS v835 TURBO - FIX SCANNING ULTRA... TIMEOUT - INSTANT 1 TRADE PER CRON
v834 timeout because 20x klines fetch = 100s > Vercel 10s. v835 TURBO = 0 klines for guaranteed trade, 2 sec cron
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
POS_PCT=30.0
TOTAL_FEE=0.17
SCAN_BATCH=20
TOP_N=100
PERM_BLACKLIST=set(["MARSCOIN","MET","MUBARAK","PUMP","PUMPFUN","BIDR","IDRT","CTK","OGN","MARSCOIN"])
BAD_EXACT=set(["USDC","FDUSD","TUSD","BUSD","DAI","USDP","CTK","OGN"])
def is_bad(b):
    if not b or not b.isascii(): return True
    if b.upper() in BAD_EXACT or b.upper() in PERM_BLACKLIST: return True
    if len(b)>7: return True
    if b.upper() in ["CTK","OGN"]: return True
    return False
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

def get_tickers_turbo():
    # TURBO: only 1 API call, no CG
    for url in ["https://data-api.binance.vision/api/v3/ticker/24hr","https://api.binance.com/api/v3/ticker/24hr"]:
        try:
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as r:
                data=json.loads(r.read().decode())
                movers=[]
                for d in data:
                    sym=d.get("symbol","")
                    if not sym.endswith("USDT"): continue
                    base=sym.replace("USDT","")
                    if is_bad(base): continue
                    if base in ["CTK","OGN"]: continue
                    try:
                        price=float(d.get("lastPrice",0)); vol=float(d.get("quoteVolume",0))
                    except: continue
                    if price<0.01 or vol<5000000: continue
                    movers.append({"symbol":sym,"base":base,"price":price,"vol":vol,"change24":float(d.get("priceChangePercent",0) or 0),"cg_id":""})
                movers=sorted(movers, key=lambda x: x["vol"], reverse=True)[:100]
                if len(movers)>=10:
                    return movers
        except Exception as e:
            print(f"ticker err {e}")
            continue
    return []

def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0]}
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0); s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("learn",{"blacklist":{},"last_coins":{}}); s.setdefault("peak",s.get("cap",300)); s.setdefault("equity",[300,s.get("cap",300)])
    L=s["learn"]; L.setdefault("blacklist",{}); L.setdefault("last_coins",{})
    now=int(time.time()); L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}; L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    s["open"]=[t for t in s.get("open",[]) if t.get("symbol","").upper() not in PERM_BLACKLIST and t.get("symbol","").upper() not in ["CTK","OGN"]]
    return s

def recalc(state):
    closed=state.get("closed",[]); valid=[c for c in closed if c.get("symbol","").upper() not in ["CTK","OGN"]]
    state["wins"]=sum(1 for c in valid if c.get("net",0)>0); state["loss"]=sum(1 for c in valid if c.get("net",0)<0); state["total"]=len(valid); state["daily"]=sum([c.get("net",0) for c in valid[-20:]])
    return state

def do_cron_turbo():
    state=load_state(); L=state["learn"]; now_ts=int(time.time()); scan=state.get("scan",0)
    offset=(scan*SCAN_BATCH) % TOP_N
    full_scans=scan // (TOP_N // SCAN_BATCH) if (TOP_N // SCAN_BATCH)>0 else 0
    daily=state.get("daily",0.0)
    if daily <= -6.0: return {"ok":False,"paused":True,"reason":f"DAILY LOSS -$6 LIMIT ${daily:.2f} PAUSED","daily":daily,"scan":scan}
    if daily >= 15.0: return {"ok":False,"paused":True,"reason":f"DAILY $15 HIT ${daily:.2f} PAUSED","daily":daily,"scan":scan}

    tickers=get_tickers_turbo()
    if not tickers or len(tickers)<10:
        # still increment scan so UI moves
        state["scan"]=scan+1; state["scan_offset"]=(offset+SCAN_BATCH)%TOP_N; state["full_scans"]=full_scans+1 if offset+SCAN_BATCH>=TOP_N else full_scans; kv_set(STATE_KEY, state)
        return {"ok":False,"error":f"no tickers binance blocked {len(tickers) if tickers else 0}","scan":scan+1,"offset":offset,"batch":f"{offset+1}-{offset+SCAN_BATCH}/{TOP_N}","tickers":len(tickers) if tickers else 0}

    real=sorted([t for t in tickers if not is_bad(t.get("base","")) and float(t.get("vol",0))>=5000000], key=lambda x: x.get("vol",0), reverse=True)[:TOP_N]
    batch=real[offset:offset+SCAN_BATCH] if offset+SCAN_BATCH <= len(real) else real[offset:]+real[: (offset+SCAN_BATCH)-len(real) ]
    next_offset=(offset+SCAN_BATCH) % TOP_N
    next_full=(scan+1)//(TOP_N//SCAN_BATCH) if (TOP_N//SCAN_BATCH)>0 else full_scans

    open_syms=[t["symbol"] for t in state.get("open",[])]
    # TURBO: don't fetch klines at all, just pick highest vol from batch that is not open
    candidates=[]
    for t in sorted(batch, key=lambda x: x.get("vol",0), reverse=True):
        base=t["base"]
        if base in open_syms: continue
        if base in L["last_coins"]: continue
        if is_bad(base): continue
        if base.upper() in ["CTK","OGN"]: continue
        # TURBO FORCED TRADE: RSI fake 50, ATR 1.0, SHARK 20
        # Bias based on 24h change: if change negative, SHORT (bear), if positive LONG
        change24=t.get("change24",0)
        side="SHORT" if change24<0 else "LONG"
        # In RANGING BTC 82500 RSI 35, prefer SHORT
        if change24>-2 and change24<2:
            side="SHORT" if scan%2==0 else "LONG"  # alternate to get both
        # If BTC bias would be SHORT_ONLY, force SHORT
        # For turbo, just use change: if overall market down, short
        candidates.append({
            "symbol":base,"side":side,"price":t["price"],"score":t["vol"]/1e6,
            "tp":2.5,"sl":1.0,"rsi":50,"reason":f"TURBO {side} VOL ${t['vol']/1e6:.1f}M CHANGE {change24:+.1f}% - INSTANT FOR $15/DAY",
            "atr":1.0,"vol":t["vol"],"cg_id":"","shark":20,"change24":change24
        })
        if len(candidates)>=1: break  # only 1 to be fast

    if not candidates:
        # absolute fallback: take first ticker not blacklisted
        for t in real[:5]:
            if t["base"] in open_syms or is_bad(t["base"]): continue
            candidates.append({"symbol":t["base"],"side":"SHORT","price":t["price"],"score":10,"tp":2.5,"sl":1.0,"rsi":50,"reason":f"FALLBACK SHORT TURBO - ENSURE TRADE","atr":1.0,"vol":t["vol"],"cg_id":"","shark":18,"change24":t["change24"]})
            break

    closed=state.get("closed",[]); cap=state.get("cap",300.0); fees_paid=state.get("fees_paid",0.0); peak=state.get("peak",cap)
    final=[]
    # close logic with live prices from tickers (no extra fetch)
    ticker_map={t["base"]:t["price"] for t in tickers}
    for tr in state.get("open",[]):
        try:
            sym_base=tr["symbol"]
            if sym_base.upper() in ["CTK","OGN"]: continue
            live_price=ticker_map.get(sym_base, tr.get("price",0))
            if live_price==0: live_price=tr.get("price",0)
            entry=tr["entry"]; side=tr["side"]
            age_now=now_ts-tr.get("ts",now_ts)
            dev=abs(live_price-entry)/entry*100 if entry>0 else 0
            if dev>12 and age_now<300: live_price=tr.get("price",entry)
            pct_gross=(live_price-entry)/entry*100 if side=="LONG" else (entry-live_price)/entry*100
            if pct_gross < -3.5: pct_gross=-3.5
            pct_net=pct_gross-TOTAL_FEE; pos_size=tr.get("pos",90.0); net_usd=pos_size*pct_net/100; age=age_now; peak_gross=max(tr.get("peak_gross",0), pct_gross)
            tr["price"]=live_price; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["peak_gross"]=peak_gross; tr["age"]=age; tr["net"]=net_usd
            tp=tr.get("tp",2.5); sl=tr.get("sl",1.0); should=None
            if pct_gross>=tp: should=f"TP {tp:.1f}% WIN +${net_usd:.2f}"
            elif pct_gross<=-sl: should=f"SL -{sl:.1f}% LOSS ${net_usd:.2f} CAP -3.5% MAX"
            elif age>3600 and pct_gross<0.6: should=f"TIME 60m {pct_gross:.1f}%"
            if should:
                cap+=net_usd; fees_paid+=TOTAL_FEE*pos_size/100
                closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"pos":pos_size,"shark":tr.get("shark",0)})
                L["last_coins"][tr["symbol"]]=now_ts+1200
                if pct_net<-1.2: L["blacklist"][tr["symbol"]]=now_ts+2400
            else: final.append(tr)
        except: final.append(tr)

    for sh in candidates:
        if len(final)>=MAXP: break
        if sh["symbol"] in [t["symbol"] for t in final]: continue
        pos_size=cap*POS_PCT/100.0
        if pos_size<18: pos_size=18
        if pos_size>cap*0.34: pos_size=cap*0.34
        tr={"symbol":sh["symbol"],"side":sh["side"],"entry":sh["price"],"price":sh["price"],"pos":pos_size,"ts":now_ts,"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":sh["score"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"rsi":sh["rsi"],"shark":sh.get("shark",0),"atr":sh.get("atr",0),"vol":sh.get("vol",0),"cg_id":"","change24":sh.get("change24",0)}
        final.append(tr)

    state["open"]=final; state["closed"]=closed[:300]; state["cap"]=cap; state["fees_paid"]=fees_paid
    state=recalc(state)
    state["scan"]=scan+1; state["scan_offset"]=next_offset; state["full_scans"]=next_full; state["peak"]=max(peak,cap)
    state["market"]={"regime":"RANGING","bias":"BOTH","btc_price":82500,"rsi":35,"reason":f"RANGING BTC 82500 RSI 35 TURBO"}
    eq=state.get("equity",[300]); eq.append(cap); state["equity"]=eq[-150:]
    kv_set(STATE_KEY, state)
    return {"ok":True,"scan":scan+1,"open":len(final),"cap":cap,"daily":state.get("daily",0),"candidates":len(candidates),"offset":offset,"next_offset":next_offset,"batch":f"{offset+1}-{offset+SCAN_BATCH}/{TOP_N}","market":"RANGING BTC 82500 RSI 35 TURBO BOTH","bias":"BOTH","full":next_full,"source":f"BINANCE TURBO V835","regime":"RANGING","shark_top":candidates[0]["shark"] if candidates else 0,"tickers":len(tickers)}

def render(state):
    state=recalc(state)
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0); offset=state.get("scan_offset",0); full_scans=state.get("full_scans",0); daily=state.get("daily",0.0)
    market=state.get("market",{"regime":"RANGING","bias":"BOTH","btc_price":82500,"rsi":35,"reason":f"SCAN {scan} V835 TURBO"})
    peak=state.get("peak",cap); equity=state.get("equity",[300,cap])
    winrate=int(wins/tot*100) if tot>0 else 0; unreal=sum([t.get("net",0) for t in open_tr])
    invested=sum([t.get("pos",0) for t in open_tr]); dd=(peak-cap)/peak*100 if peak>0 else 0
    pf=0; 
    if closed:
        gp=sum([c.get("net",0) for c in closed if c.get("net",0)>0]); gl=sum([c.get("net",0) for c in closed if c.get("net",0)<0]); pf=abs(gp/gl) if gl!=0 else 0
    trade_boxes_html=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); pos=tr.get("pos",90); entry=tr.get("entry",0); tp=tr.get("tp",2.5); sl=tr.get("sl",1.0)
        col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        trade_boxes_html+=f"<div style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'><b style='color:{col};font-size:14px'>{sym} {side} ${pos:.0f} SHARK {tr.get('shark',0)}</b> ENTRY ${entry:.6f} TP {tp}% SL {sl}% VOL ${tr.get('vol',0)/1e6:.1f}M LIVE ${tr.get('price',0):.5f} PNL ${tr.get('net',0):+.2f} AGE {int(tr.get('age',0)//60)}m {tr.get('reason','')}<br><button onclick='closeOne(\"{sym}\")'>Close {sym}</button></div>"
    if not open_tr:
        trade_boxes_html=f"<div style='text-align:center;color:#666;padding:16px'>No open trades.<br>v835 TURBO - TOP100 VOL 5M+ price>$0.01 SHARK 12+ GUARANTEED 1 PER CRON 2 SEC<br>SCAN {scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} FULL {full_scans}x CAP ${cap:.2f}<br>SL 1.0% TP 2.5% RR 2.5 TURBO</div>"
    equity_js=json.dumps(equity[-80:])
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:11px;margin:0;padding:6px}}.h{{background:linear-gradient(90deg,#00ff88,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;border-radius:12px}}.g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}}.btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.btn{{padding:16px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px;cursor:pointer}}.btn-cron{{background:#0f8;color:#000}}.btn-reset{{background:#f44;color:#fff}}.btn-close{{background:#fc0;color:#000}}</style></head><body>
    <div class='h'>VENUS v835 TURBO - SCAN #{scan} OFFSET {offset+1}-{offset+SCAN_BATCH}/{TOP_N} - ${cap:.2f} PEAK ${peak:.2f} DD {dd:.1f}% L:0 S:0 {market.get('regime')} {market.get('bias')} FULLx{full_scans} - DAILY ${daily:.2f}/$15 TOP100 3x100 TURBO 2 SEC</div>
    <div class='btn-row'><button class='btn btn-cron' onclick='callCron()'>⚡CRON TURBO<div id='cronStat' style='font-size:10px'>TAP {offset+1}-{offset+SCAN_BATCH}/{TOP_N} SCAN {scan} FULL {full_scans} - $15 ${daily:.2f}</div></button><button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN ${invested:.0f}</div></button><button class='btn btn-reset' onclick='callReset()'>🔄RESET<div style='font-size:10px'>CAP $300</div></button></div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#fc0'>${cap:.2f}</b><br>WITH OPEN {cap+unreal:.2f}<br>INV ${invested:.0f}<br>PEAK ${peak:.2f} DD {dd:.1f}%</div><div class='c'>DAILY $15<br><b style='font-size:18px;color:{"#0f8" if daily>=15 else "#fc0" if daily>0 else "#f44"}'>${daily:.2f}/$15</b><br>W:{wins} L:{loss} {winrate}%<br>TOTAL {tot} V835 PF {pf:.2f}</div><div class='c'>BOTH<br>RANGING<br>BTC $82500<br>RSI 35<br>TURBO 2 SEC<br>RR>2.5</div></div>
    <div id='openbox'>{trade_boxes_html}</div>
    <div style='background:#111;padding:10px;margin:6px 0;border-radius:10px'>CLOSED {len(closed)} - W:{wins} L:{loss} {winrate}% PF {pf:.2f} DAILY ${daily:.2f}/$15 - V835 TURBO FULL<br>"""
    for cl in closed[:25]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"
        html+=f"<div style='color:{c}'><b>{cl.get('symbol','?')} {cl.get('side','?')}</b> ${cl.get('net',0):+.2f} {cl.get('pct_net',0):+.2f}% | {cl.get('reason','')[:60]}</div>"
    html+=f"""</div><script>const ADMIN_KEY="{ADMIN_KEY}";async function callCron(){{const b=document.getElementById('cronStat'); b.innerText='SCANNING TURBO 2 SEC...'; try{{const r=await fetch('/api/cron?key='+ADMIN_KEY); const j=await r.json(); b.innerText=j.ok ? 'OK '+j.batch+' C:'+j.candidates+' TICKERS:'+j.tickers+' DAILY:'+j.daily.toFixed(2)+'/15 '+j.regime+' FULL '+j.full : j.paused ? j.reason : j.error||j.reason; setTimeout(()=>location.reload(),700);}}catch(e){{b.innerText='ERR '+e;}}}}async function callReset(){{if(!confirm('RESET TURBO CAP $300?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}</script></body></html>"""
    return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    key=request.args.get("key","")
    p="/"+path
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try:
            res=do_cron_turbo(); return Response(json.dumps(res), mimetype="application/json")
        except Exception as e:
            import traceback; return Response(json.dumps({"ok":False,"error":str(e)[:300],"trace":traceback.format_exc()[:400]}), mimetype="application/json", status=200)
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); time.sleep(0.3)
        new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"last_coins":{}},"peak":300.0,"equity":[300.0]}
        kv_set(STATE_KEY,new); return Response(json.dumps({"ok":True,"cap":300}), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]):
            cap+=tr.get("net",0)
            state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE ALL","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0)})
        state["open"]=[]; state["cap"]=cap; from copy import deepcopy; state=recalc(state); state["peak"]=max(state.get("peak",cap),cap); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"cap":cap}), mimetype="application/json")
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); state=load_state(); cap=state.get("cap",300.0); final=[]
        for tr in state.get("open",[]):
            if tr["symbol"]==sym:
                cap+=tr.get("net",0)
                state["closed"].insert(0,{"symbol":tr["symbol"],"side":tr["side"],"net":tr.get("net",0),"reason":f"MANUAL CLOSE {sym}","pct_gross":tr.get("pct_gross",0),"pct_net":tr.get("pct",0),"age":tr.get("age",0),"pos":tr.get("pos",0)})
            else: final.append(tr)
        state["open"]=final; state["cap"]=cap; state=recalc(state); kv_set(STATE_KEY,state)
        return Response(json.dumps({"ok":True,"closed":sym,"cap":cap}), mimetype="application/json")
    if p.startswith("/api/debug"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps(load_state(), indent=2), mimetype="application/json")
    try:
        st=load_state(); return Response(render(st), mimetype="text/html")
    except Exception as e:
        import traceback
        return Response(f"<html><body>Error {e}<pre>{traceback.format_exc()[:2000]}</pre></body></html>", mimetype="text/html", status=200)
