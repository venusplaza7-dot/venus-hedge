from flask import Flask, request, Response
import os, json, time, urllib.request
app = Flask(__name__)
def env(k):
    for kk in k:
        v=os.environ.get(kk)
        if v: return v.strip().strip('"').strip("'")
    return ""
KV_URL=(env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"]) or "").rstrip("/")
if not KV_URL:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "URL" in kk and "upstash" in vv.lower(): KV_URL=vv.strip().strip('"').strip("'").rstrip("/"); break
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
if not KV_TOKEN:
    for kk,vv in os.environ.items():
        if "REDIS" in kk and "TOKEN" in kk and "upstash" in kk.lower(): KV_TOKEN=vv.strip().strip('"').strip("'"); break
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V808_SHARK100"
POS_FIXED=100.0; MAXP=3; FEE_PCT=0.15; MAX_DAILY_LOSS_PCT=4.5
SCAN_BATCH=10; TOP_N=100
def kv_get(k):
    if not KV_URL or not KV_TOKEN: return None
    try:
        body=json.dumps([["GET",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d=json.loads(r.read().decode()); res=d[0].get("result") if isinstance(d,list) and d else None
            if not res: return None
            return json.loads(res) if (res.startswith("{") or res.startswith("[")) else res
    except: return None
def kv_set(k,o):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["SET",k,json.dumps(o)]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r: return "OK" in r.read().decode()
    except Exception as e:
        print(f"KV SET FAIL {e}")
        return False
def kv_del(k):
    if not KV_URL or not KV_TOKEN: return False
    try:
        body=json.dumps([["DEL",k]]).encode()
        req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=5) as r: return True
    except: return False
def get_tickers():
    for url in ["https://api.binance.com/api/v3/ticker/24hr","https://data-api.binance.vision/api/v3/ticker/24hr"]:
        try:
            req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as r: 
                data=json.loads(r.read().decode())
                if data: return data
        except: continue
    return []
def load_state():
    s=kv_get(STATE_KEY)
    if not s:
        s={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}}
    s.setdefault("scan",0); s.setdefault("scan_offset",0); s.setdefault("full_scans",0)
    s.setdefault("open",[]); s.setdefault("closed",[]); s.setdefault("learn",{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}})
    L=s["learn"]; L.setdefault("blacklist",{}); L.setdefault("last_coins",{}); L.setdefault("pause_until",0)
    # AUTO-CLEAR if stuck too long
    now=int(time.time())
    L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}
    L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
    # If full_scans > 15, clear everything to unstick
    if s.get("full_scans",0) > 12:
        L["blacklist"]={}; L["last_coins"]={}
    return s
def do_cron():
    state=load_state(); L=state["learn"]; now_ts=int(time.time())
    scan=state.get("scan",0)
    # FIX: FORCE OFFSET ADVANCE BY SCAN COUNT - NEVER STUCK
    offset = (scan * SCAN_BATCH) % TOP_N  # 0,10,20,30...90,0,10...
    full_scans = scan // 10
    
    tickers=get_tickers()
    ticker_map={t.get("symbol",""):t for t in tickers}
    real=[]
    for t in tickers:
        sym=t.get("symbol","")
        if not sym.endswith("USDT"): continue
        base=sym.replace("USDT","")
        if len(base)>7 or len(base)<2: continue
        if base in ["USDC","FDUSD","TUSD","BUSD","DAI"]: continue
        try:
            qv=float(t.get("quoteVolume","0"))
            if qv < 2000000: continue
        except: continue
        real.append(t)
    real_sorted=sorted(real, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:TOP_N]
    
    if not real_sorted:
        return {"ok":False,"error":"Binance ticker empty - try again","offset":offset,"scan":scan}
    
    batch=real_sorted[offset:offset+SCAN_BATCH]
    # always advance
    next_offset = (offset + SCAN_BATCH) % TOP_N
    next_full = full_scans + (1 if next_offset==0 else 0)
    
    open_syms=[t["symbol"] for t in state.get("open",[])]
    candidates=[]
    # v812 ULTRA - ticker only, guaranteed fill
    # First try normal logic
    for t in batch:
        base=t.get("symbol","").replace("USDT","")
        if base in open_syms: continue
        if base in L.get("blacklist",{}): continue
        if base in L.get("last_coins",{}): continue
        price=float(t.get("lastPrice","0"))
        if price==0: continue
        try:
            change=float(t.get("priceChangePercent","0"))
            # Simple: any mover >0.8% is candidate
            if abs(change) > 0.5:
                side="LONG" if change < 0 else "SHORT" if change>1.2 else "LONG"
                # If long streak no fill, alternate sides
                if scan>50:
                    side="LONG" if len(candidates)%2==0 else "SHORT"
                candidates.append({"symbol":base,"side":side,"price":price,"score":abs(change)+10,"tp":1.0,"sl":0.65,"rsi":45 if side=="LONG" else 55,"reason":f"v812 TICKER {change:+.1f}% OFFSET {offset}-{offset+SCAN_BATCH}","shark":0})
        except: continue
    
    fallback=False
    if not candidates:
        # ULTRA FORCE - take top 3 from batch ignoring everything
        if scan >= 2:  # after 2 scans, FORCE
            for t in batch[:5]:
                base=t.get("symbol","").replace("USDT","")
                if base in open_syms: continue
                price=float(t.get("lastPrice","0"))
                side="LONG" if len(candidates)%2==0 else "SHORT"
                candidates.append({"symbol":base,"side":side,"price":price,"score":100,"tp":1.0,"sl":0.65,"rsi":50,"reason":f"v812 ULTRA FORCE {offset}-{offset+SCAN_BATCH} #{scan}","shark":0})
                fallback=True
                if len(candidates)>=3: break
    
    # Close logic
    closed=state.get("closed",[]); cap=state.get("cap",300.0); daily=state.get("daily",0.0); tot=state.get("total",0)
    final=[]
    for tr in state.get("open",[]):
        try:
            sym=tr["symbol"]+"USDT"
            price_now=float(ticker_map[sym].get("lastPrice",tr.get("price",tr.get("entry",0)))) if sym in ticker_map else tr.get("price",0)
            entry=tr.get("entry",price_now); side=tr.get("side","LONG")
            pct_gross=(price_now-entry)/entry*100 if side=="LONG" else (entry-price_now)/entry*100
            pct_net=pct_gross-0.15; pos=tr.get("pos",100); net_usd=pos*pct_net/100; age=now_ts-tr.get("ts",now_ts)
            peak=max(tr.get("peak_gross",0), pct_gross)
            tr["price"]=price_now; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["peak_gross"]=peak; tr["age"]=age; tr["net"]=net_usd
            tp=tr.get("tp",1.0); sl=tr.get("sl",0.65); should=None
            if pct_gross>=tp: should=f"TP {tp:.1f}% WIN +${net_usd:.2f}"
            elif pct_gross<=-sl: should=f"SL -{sl:.1f}% CUT"
            elif peak>=0.6 and pct_gross<=0.1: should=f"BE_PROTECT {peak:.1f}%->0.1%"
            elif age>45*60 and pct_gross<0.2: should=f"TIME 45m"
            if pct_net<-0.9: should=f"MAXLOSS -0.9%"
            if should:
                cap+=net_usd; daily+=net_usd; tot+=1
                closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"pos":pos})
                L["last_coins"][tr["symbol"]]=now_ts+300
            else: final.append(tr)
        except: final.append(tr)
    
    wins=sum(1 for c in closed if c.get("net",0)>0); loss=sum(1 for c in closed if c.get("net",0)<0)
    for sh in candidates:
        if len(final)>=3: break
        if sh["symbol"] in [t["symbol"] for t in final]: continue
        if cap<15: break
        pos=100 if cap>=100 else cap*0.9
        tr={"symbol":sh["symbol"],"side":sh["side"],"entry":sh["price"],"price":sh["price"],"pos":pos,"ts":now_ts,"peak_gross":0,"pct_gross":0,"pct":0,"net":0,"age":0,"score":sh["score"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"rsi":sh["rsi"],"shark":0}
        final.append(tr)
    
    state["open"]=final; state["closed"]=closed[:400]; state["cap"]=cap; state["daily"]=daily; state["wins"]=wins; state["loss"]=loss; state["total"]=tot
    state["scan"]=scan+1
    state["scan_offset"]=next_offset
    state["full_scans"]=next_full
    state["market"]={"regime":"RANGING","bias":"BOTH","btc_price":float(ticker_map.get("BTCUSDT",{}).get("lastPrice",84000)) if "BTCUSDT" in ticker_map else 84000,"reason":f"v812 FIXED OFFSET {offset}-{offset+SCAN_BATCH} SCAN {scan} -> {scan+1} FULL {next_full}x"}
    
    ok=kv_set(STATE_KEY, state)
    return {"ok":ok,"scan":scan+1,"open":len(final),"cap":cap,"candidates":len(candidates),"offset":offset,"next_offset":next_offset,"batch":f"{offset+1}-{offset+SCAN_BATCH}","fallback":fallback,"full":next_full,"kv_ok":ok}

def render(state):
    open_tr=state.get("open",[]); closed=state.get("closed",[]); cap=state.get("cap",300.0); daily=state.get("daily",0.0); wins=state.get("wins",0); loss=state.get("loss",0); tot=state.get("total",0); scan=state.get("scan",0); offset=state.get("scan_offset",0); full_scans=state.get("full_scans",0)
    winrate=int(wins/tot*100) if tot>0 else 0; unreal=sum([t.get("net",0) for t in open_tr]); invested=sum([t.get("pos",0) for t in open_tr])
    gross_profit=sum([c.get("net",0) for c in closed if c.get("net",0)>0]); gross_loss=sum([c.get("net",0) for c in closed if c.get("net",0)<0])
    pf=abs(gross_profit/gross_loss) if gross_loss!=0 else gross_profit; exp=(gross_profit+gross_loss)/tot if tot>0 else 0
    best = max(closed, key=lambda x: x.get("net",0)) if closed else None; best_sym=best.get('symbol','-') if best else '-'; best_net=best.get('net',0) if best else 0
    market=state.get("market",{"reason":f"SCAN {scan} OFFSET {offset} v812 UNSTUCK"})
    trade_html=""
    chart_init=""
    for tr in open_tr:
        sym=tr["symbol"]; side=tr.get("side","LONG"); entry=tr.get("entry",0); tp=entry*(1+tr.get("tp",1)/100) if side=="LONG" else entry*(1-tr.get("tp",1)/100); sl=entry*(1-tr.get("sl",0.65)/100) if side=="LONG" else entry*(1+tr.get("sl",0.65)/100); col="#0f8" if tr.get("pct",0)>=0 else "#f44"
        trade_html+=f"""
        <div style='border:2px solid {col};background:#151515;border-radius:16px;padding:12px;margin:10px 0;'>
          <div style='display:flex;justify-content:space-between'><b style='color:{col}'>{sym} {side} ${tr.get('pos',0):.0f}</b><button onclick='closeOne("{sym}")' style='background:#222;color:#fff;border:1px solid #444;border-radius:10px;padding:6px 10px'>✕</button></div>
          <div style='font-size:11px;color:#aaa'>ENTRY ${entry:.5f} TP ${tp:.5f} SL ${sl:.5f}</div>
          <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:8px 0;text-align:center'>
            <div style='background:#000;padding:6px;border-radius:8px'><div style='font-size:9px;color:#888'>PRICE</div><div id='live-price-{sym}' style='font-weight:900;color:{col}'>${tr.get('price',0):.4f}</div><div id='live-change-{sym}' style='font-size:10px'>{tr.get('pct_gross',0):+.2f}%</div></div>
            <div style='background:#000;padding:6px;border-radius:8px'><div style='font-size:9px;color:#888'>PNL</div><div id='live-pnl-{sym}' style='font-weight:900;color:{col}'>${tr.get('net',0):+.2f}</div><div style='font-size:10px'>PEAK {tr.get('peak_gross',0):.1f}%</div></div>
            <div style='background:#000;padding:6px;border-radius:8px'><div style='font-size:9px;color:#888'>AGE</div><div style='font-weight:900'>{int(tr.get('age',0)//60)}m</div><div style='font-size:10px'>TP to go {(tr.get('tp',0)-tr.get('pct_gross',0)):.1f}%</div></div>
          </div>
          <div style='background:#000;border-radius:10px;padding:6px'><canvas id='chart-{sym}' width='340' height='120' style='width:100%;height:120px'></canvas></div>
          <div style='font-size:10px;color:#888'>{tr.get('reason','')}</div>
        </div>"""
        chart_init+=f"initChart('{sym}',{entry},{tp},{sl},'{side}');\n"
    if not open_tr:
        trade_html=f"<div style='background:#111;padding:20px;border-radius:12px;text-align:center;color:#666'>No open trades.<br>v812 FIXED - offset moves by scan count, not KV. Tap CRON.<br>SCAN {scan} OFFSET {offset} -> next { (offset+10)%100 } FULL {full_scans}x</div>"
    html=f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1'>
    <style>body{{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}}.h{{background:linear-gradient(90deg,#0f8,#fc0,#0df);color:#000;padding:12px;text-align:center;font-weight:900;border-radius:12px;font-size:11px}}.g{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin:6px 0}}.c{{background:#1a1a1a;border:1px solid #333;padding:8px;text-align:center;border-radius:10px}}.btn-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}}.btn{{padding:14px 4px;border-radius:14px;border:0;font-weight:900;font-size:13px}}.btn-cron{{background:#0f8;color:#000}}.btn-close{{background:#fc0;color:#000}}.btn-reset{{background:#f44;color:#fff}}.badge{{padding:2px 6px;border-radius:10px;font-size:9px}}.long{{background:#0f8;color:#000}}.short{{background:#f44;color:#fff}}</style></head><body>
    <div class='h'>VENUS v812 UNSTUCK - SCAN #{scan} OFFSET {offset}-{offset+10} - ${cap:.2f} FULLx{full_scans} - {market.get('reason','')}</div>
    <div class='btn-row'><button class='btn btn-cron' onclick='callCron()'>⚡CRON 10 COINS<div id='cronStat' style='font-size:10px'>TAP {offset+1}-{offset+10}/100 SCAN {scan}</div></button><button class='btn btn-close' onclick='closeAll()'>💰CLOSE ALL<div style='font-size:10px'>{len(open_tr)} OPEN ${invested:.0f}</div></button><button class='btn btn-reset' onclick='callReset()'>🔄RESET<div style='font-size:10px'>CAP $300</div></button></div>
    <div class='g'><div class='c'>CAP<br><b style='font-size:18px;color:#fc0'>${cap:.2f}</b><br>WITH {cap+unreal:.2f}<br>UNREAL {unreal:+.2f}</div><div class='c'>TODAY<br><b style='font-size:18px;color:{ "#f44" if daily<0 else "#0f8"}'>${daily:+.2f}</b><br>W:{wins} L:{loss} {winrate}%<br>SCAN {offset}-{offset+10}</div><div class='c'>v812 UNSTUCK<br>BOTH<br>RANGING<br>BTC ${market.get('btc_price',0):.0f}<br>FULL {full_scans}x</div></div>
    <div style='background:#111;border:2px solid #fc0;padding:10px;border-radius:12px;margin:6px 0'><div style='color:#fc0;font-weight:900'>v812 FIX: offset = scan*10 %100 - never stuck at 0-10 - guarantees advance</div><div style='font-size:10px'>{market.get('reason','')}</div><div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px;font-size:11px'><div>SCAN: <b>{offset+1}-{offset+10}/100 x{full_scans}</b></div><div>OPEN: <b>{len(open_tr)}/3</b></div><div>TOTAL: {tot} W:{wins} L:{loss} {winrate}%</div><div>PF {pf:.2f} EXP ${exp:.3f}</div></div></div>
    <div id='openbox'>{trade_html}</div>
    <div style='background:#111;padding:10px;border-radius:10px;margin-top:8px'><div style='color:#fc0;font-weight:900'>CLOSED {len(closed)} W:{wins} L:{loss}</div>
    """
    for cl in closed[:15]:
        c="#0f8" if cl.get("net",0)>0 else "#f44"
        html+=f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')} {cl.get('side','')} ${cl.get('pos',100):.0f}</b> ${cl.get('net',0):+.2f} | {cl.get('reason','')}</div>"
    html+=f"""</div>
    <div style='margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:6px'>
      <button onclick='fixOffset()' style='background:#0df;color:#000;padding:12px;border-radius:10px;border:0;font-weight:900'>🔧 FIX OFFSET STUCK</button>
      <button onclick='clearBlacklist()' style='background:#fc0;color:#000;padding:12px;border-radius:10px;border:0;font-weight:900'>🧹 CLEAR COOLDOWN</button>
    </div>
<script>
const ADMIN_KEY="{ADMIN_KEY}";
async function callCron(){{const b=document.getElementById('cronStat'); b.innerText='SCANNING...'; try{{const r=await fetch('/api/cron?key='+ADMIN_KEY); const j=await r.json(); b.innerText=j.ok ? 'OK '+j.batch+' C:'+j.candidates+(j.fallback?' FORCE':'') : j.error||j.reason; setTimeout(()=>location.reload(),1000);}}catch(e){{b.innerText='ERR '+e;}}}}
async function callReset(){{if(!confirm('RESET?')) return; await fetch('/api/reset?key='+ADMIN_KEY); location.reload();}}
async function closeAll(){{if(!confirm('Close all?')) return; await fetch('/api/closeall?key='+ADMIN_KEY); location.reload();}}
async function closeOne(s){{if(!confirm('Close '+s+'?')) return; await fetch('/api/close?symbol='+s+'&key='+ADMIN_KEY); location.reload();}}
async function fixOffset(){{await fetch('/api/fix?key='+ADMIN_KEY); location.reload();}}
async function clearBlacklist(){{await fetch('/api/clear?key='+ADMIN_KEY); location.reload();}}
function initChart(sym,entry,tp,sl,side){{const cv=document.getElementById('chart-'+sym); if(!cv) return; const ctx=cv.getContext('2d'); let prices=[]; async function fetchK(){{try{{const r=await fetch('https://api.binance.com/api/v3/klines?symbol='+sym+'USDT&interval=1m&limit=40'); const d=await r.json(); prices=d.map(k=>parseFloat(k[4])); draw(); upd();}}catch(e){{}}}} function draw(){{if(!prices.length) return; const w=cv.width,h=cv.height; ctx.clearRect(0,0,w,h); const mn=Math.min(...prices,entry,tp,sl)*0.999,mx=Math.max(...prices,entry,tp,sl)*1.001,rg=mx-mn||1; function yF(p){{return h*0.9-((p-mn)/rg)*h*0.8;}} ctx.strokeStyle='#222'; for(let i=0;i<4;i++){{const y=h*0.1+i*h*0.8/3; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();}} ctx.strokeStyle='#0f8'; ctx.setLineDash([5,3]); ctx.beginPath(); ctx.moveTo(0,yF(tp)); ctx.lineTo(w,yF(tp)); ctx.stroke(); ctx.setLineDash([]); ctx.strokeStyle='#fc0'; ctx.beginPath(); ctx.moveTo(0,yF(entry)); ctx.lineTo(w,yF(entry)); ctx.stroke(); ctx.strokeStyle='#f44'; ctx.setLineDash([5,3]); ctx.beginPath(); ctx.moveTo(0,yF(sl)); ctx.lineTo(w,yF(sl)); ctx.stroke(); ctx.setLineDash([]); ctx.strokeStyle=side=='LONG'?'#0f8':'#f44'; ctx.lineWidth=2; ctx.beginPath(); prices.forEach((p,i)=>{{const x=i/(prices.length-1)*w,y=yF(p); if(i==0)ctx.moveTo(x,y); else ctx.lineTo(x,y);}}); ctx.stroke();}} function upd(){{if(!prices.length) return; const last=prices[prices.length-1]; const pct=side=='LONG'?(last-entry)/entry*100:(entry-last)/entry*100; const elP=document.getElementById('live-price-'+sym),elC=document.getElementById('live-change-'+sym),elPn=document.getElementById('live-pnl-'+sym); if(elP)elP.innerText='$'+last.toFixed(4); if(elC)elC.innerText=pct.toFixed(2)+'%'; if(elPn)elPn.innerText='$'+(100*(pct-0.15)/100).toFixed(2);}} fetchK(); setInterval(fetchK,5000);}}
window.addEventListener('load',()=>{{{chart_init}}});
</script></body></html>"""
    return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    key=request.args.get("key",""); p="/"+path
    if p.startswith("/api/cron"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        try: res=do_cron(); return Response(json.dumps(res), mimetype="application/json")
        except Exception as e: return Response(json.dumps({"ok":False,"error":str(e)[:400]}), mimetype="application/json", status=200)
    if p.startswith("/api/fix"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        s=load_state(); s["scan_offset"]=0; s["scan"]=0; s["full_scans"]=0; s["learn"]={"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}; kv_set(STATE_KEY,s); return Response(json.dumps({"ok":True,"fixed":True}), mimetype="application/json")
    if p.startswith("/api/clear"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        s=load_state(); s["learn"]["blacklist"]={}; s["learn"]["last_coins"]={}; kv_set(STATE_KEY,s); return Response(json.dumps({"ok":True}), mimetype="application/json")
    if p.startswith("/api/debug"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        return Response(json.dumps({"state":load_state()}), mimetype="application/json")
    if p.startswith("/api/reset"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        kv_del(STATE_KEY); new={"cap":300.0,"daily":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"scan_offset":0,"full_scans":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}}; kv_set(STATE_KEY,new); return Response(json.dumps({"ok":True}), mimetype="application/json")
    if p.startswith("/api/closeall"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        state=load_state(); cap=state.get("cap",300.0)
        for tr in state.get("open",[]): cap+=tr.get("net",0)
        state["open"]=[]; state["cap"]=cap; kv_set(STATE_KEY,state); return Response(json.dumps({"ok":True}), mimetype="application/json")
    if p.startswith("/api/close"):
        if key!=ADMIN_KEY: return Response("Forbidden", status=403)
        sym=request.args.get("symbol",""); state=load_state(); final=[]
        for tr in state.get("open",[]):
            if tr["symbol"]!=sym: final.append(tr)
        state["open"]=final; kv_set(STATE_KEY,state); return Response(json.dumps({"ok":True}), mimetype="application/json")
    try: st=load_state(); return Response(render(st), mimetype="text/html")
    except Exception as e:
        import traceback; return Response(f"<html>Error {e}<pre>{traceback.format_exc()[:1000]}</pre></html>", mimetype="text/html", status=200)
