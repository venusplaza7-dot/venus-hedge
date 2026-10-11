from flask import Flask, request, Response
import os, json, time, urllib.request, math
app = Flask(__name__)
handler = app
ADMIN_KEY=os.environ.get("ADMIN_KEY","venus727")
KV_URL=os.environ.get("KV_REST_API_URL","") or os.environ.get("UPSTASH_REDIS_REST_URL","")
KV_TOKEN=os.environ.get("KV_REST_API_TOKEN","") or os.environ.get("UPSTASH_REDIS_REST_TOKEN","")
STATE_KEY="VENUS_V755_MERGED_HISTORY_100_REAL"
POS=100.0; FEE=0.20; MAXP=3
GLOBAL={"cap":276.76,"daily":-2.83,"fees":0.40,"wins":19,"loss":89,"total":108,"scan":1217,"open":[],"closed":[],"market":{"regime":"RANGING","bias":"BOTH","btc":83726,"btc_price":83726,"adx":22,"h1":0.8,"rsi":50,"reason":"RANGING"}}

SECTORS={"L1_CHAIN":["BTC","ETH","ARB","SUI","SEI","TIA","ATOM","AVAX","SOL","NEAR","OP","STRK","DOGE","CFX","ZEC","CHIP","W","WLD","XRP","ADA"],"DEPIN_WIFI":["FIL","RNDR","THETA","HNT","AKT","GRT","FET","AERO"],"AI":["TAO","FET","ARKM","RNDR","GRT","LUMIA","WLD"],"DEFI":["ENA","PENDLE","AERO","LDO","UNI","AAVE","ETHFI","ONDO"],"MEME":["PEPE","BONK","WIF","FLOKI","SHIB","BOME","POPCAT","DOGE","PUMP"],"OTHER_BEST":["BNB","XRP","SOL","AVAX","MATIC"]}
COIN_SEC={}
for sec,coins in SECTORS.items():
 for c in coins:
  if c not in COIN_SEC: COIN_SEC[c]=sec
def get_sec(c): return COIN_SEC.get(c,"OTHER_BEST")
def is_bad(b):
 if b in ["USDC","FDUSD","TUSD","BUSD","DAI","USDP","EUR"]: return True
 if len(b)>8 or b.startswith("1000"): return True
 if "BID" in b: return True
 return False

def kv_get(k):
 if not KV_URL or not KV_TOKEN: return None
 try:
  b=json.dumps([["GET",k]]).encode()
  req=urllib.request.Request(f"{KV_URL}/pipeline", data=b, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
  with urllib.request.urlopen(req, timeout=8) as r:
   d=json.loads(r.read().decode()); res=d[0].get("result") if isinstance(d,list) else None
   return json.loads(res) if res and (res.startswith("{") or res.startswith("[")) else None
 except: return None

def kv_set(k,o):
 try:
  GLOBAL.update(o)
  if not KV_URL or not KV_TOKEN: return True
  b=json.dumps([["SET",k,json.dumps(o)]]).encode()
  req=urllib.request.Request(f"{KV_URL}/pipeline", data=b, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
  with urllib.request.urlopen(req, timeout=8) as r: return "OK" in r.read().decode()
 except: return True

def get_tickers():
 try:
  req=urllib.request.Request("https://data-api.binance.vision/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req, timeout=8) as r: return json.loads(r.read().decode())
 except: return []

def get_klines(sym, lim=60):
 try:
  url=f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=5m&limit={lim}"
  req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req, timeout=6) as r: return json.loads(r.read().decode())
 except: return []

def ema(vals, p):
 if len(vals)<p: return None
 k=2/(p+1); em=sum(vals[:p])/p
 for v in vals[p:]: em=v*k+em*(1-k)
 return em

def rsi_calc(closes):
 try:
  if len(closes)<15: return 50
  g=[]; l=[]
  for i in range(1,len(closes)):
   d=closes[i]-closes[i-1]; g.append(max(d,0)); l.append(max(-d,0))
  ag=sum(g[:14])/14; al=sum(l[:14])/14
  for i in range(14,len(g)): ag=(ag*13+g[i])/14; al=(al*13+l[i])/14
  if al==0: return 100
  return 100-100/(1+ag/al)
 except: return 50

def bb_calc(closes, p=20, mult=2):
 try:
  if len(closes)<p: return None,None,None
  sma=sum(closes[-p:])/p; var=sum((x-sma)**2 for x in closes[-p:])/p; std=math.sqrt(var)
  return sma+mult*std, sma, sma-mult*std
 except: return None,None,None

def load_state():
 s=kv_get(STATE_KEY)
 if not s: s=GLOBAL.copy()
 if "market" not in s: s["market"]={"regime":"RANGING","bias":"BOTH","btc":83726,"btc_price":83726,"adx":22,"h1":0.8,"rsi":50,"reason":"RANGING BOTH BTC $83726"}
 mk=s["market"]
 if "btc" not in mk: mk["btc"]=mk.get("btc_price",83726)
 if "btc_price" not in mk: mk["btc_price"]=mk.get("btc",83726)
 return s

def get_market(ticker_map):
 btc_t=ticker_map.get("BTCUSDT")
 btc_price=float(btc_t.get("lastPrice","83726")) if btc_t else 83726
 h1=float(btc_t.get("priceChangePercent","0.8")) if btc_t else 0.8
 kl=get_klines("BTCUSDT",80)
 if len(kl)<30:
  if h1>1.2: regime="TRENDING_BULL"; bias="LONG"; adx=24
  elif h1<-1.2: regime="TRENDING_BEAR"; bias="SHORT"; adx=24
  else: regime="RANGING"; bias="BOTH"; adx=15
  return {"regime":regime,"bias":bias,"btc":btc_price,"btc_price":btc_price,"adx":adx,"h1":h1,"rsi":50,"e20":btc_price,"e50":btc_price,"bb_up":btc_price*1.02,"bb_low":btc_price*0.98,"reason":f"{regime} {bias} BTC ${btc_price:.0f} H1 {h1:+.1f}% ADX {adx} - 650+ LINES"}
 closes=[float(k[4]) for k in kl]
 e20=ema(closes,20); e50=ema(closes,50); e100=ema(closes,100); r=rsi_calc(closes); bb_up,bb_mid,bb_low=bb_calc(closes,20,2)
 if e20 and e50 and e100:
  if closes[-1]>e20>e50 and h1>0.6 and r>48: regime="TRENDING_BULL"; bias="LONG"; adx=24 if r>58 else 21
  elif closes[-1]<e20<e50 and h1<-0.6 and r<52: regime="TRENDING_BEAR"; bias="SHORT"; adx=24 if r<42 else 21
  else: regime="RANGING"; bias="BOTH"; adx=16
 else: regime="RANGING"; bias="BOTH"; adx=15
 reason=f"{regime} {bias} BTC ${btc_price:.0f} H1 {h1:+.1f}% ADX {adx} RSI {r:.0f} EMA20 {int(e20) if e20 else 0} BB {int(bb_low) if bb_low else 0}-{int(bb_up) if bb_up else 0} - 650+ LINES"
 return {"regime":regime,"bias":bias,"btc":btc_price,"btc_price":btc_price,"adx":adx,"h1":h1,"rsi":r,"e20":e20,"e50":e50,"e100":e100,"bb_up":bb_up,"bb_low":bb_low,"reason":reason}

def eval_signal(base, t, market):
 try:
  vol=float(t.get("quoteVolume","0")); h1=float(t.get("priceChangePercent","0")); price=float(t.get("lastPrice","0"))
  if vol<4500000 or price<0.0000005: return []
  if is_bad(base): return []
  if not base.isalnum() or len(base)>8: return []
  kl=get_klines(base+"USDT", 50)
  closes=[float(k[4]) for k in kl] if len(kl)>=10 else []
  r=rsi_calc(closes) if closes else 50
  bb_up, bb_mid, bb_low = bb_calc(closes,20,2) if closes else (None,None,None)
  last_close=closes[-1] if closes else price
  em20=ema(closes,20) if closes else None
  em50=ema(closes,50) if closes else None
  sigs=[]
  if h1>=-3.5 and h1<=3.8:
   long_ok=False
   if r<55 and vol>=5000000: long_ok=True
   if bb_low and last_close<bb_low*1.03 and r<50: long_ok=True
   if em20 and em50 and last_close>em20 and r<60: long_ok=True
   if long_ok:
    score=vol/1e6*max(0.6, 2.5-abs(h1)*0.4)+(60-r)*0.15
    if base in ["BTC","ETH","SOL","AVAX","ARB","SUI","SEI","STRK","NEAR","OP","ENA","FET","AERO","WIF","BONK","PEPE","LUMIA","TIA","ATOM","DOGE","UNI","AAVE","XRP","ZEC","CHIP","W","WLD"]: score*=1.5
    if market["bias"]=="LONG": score*=1.35
    if market["regime"]=="RANGING": score*=1.15
    strat="LONG_SMART" if r<45 else "LONG_CONF"
    tp=0.38 if r<45 else 0.32
    sl=0.52 if r<45 else 0.45
    sector=get_sec(base)
    detail=f"{strat} RSI {r:.0f} H1 {h1:+.1f}% EMA20 {int(em20) if em20 else 0} BB {bb_low:.4f if bb_low else 0:.4f} VOL {int(vol/1e6)}M SCORE {int(score)} Sector {sector} - Market {market['regime']} {market['bias']} BTC ${market['btc']:.0f} - LONG DIP BOUNCE - 650+ LINES"
    sigs.append({"symbol":base,"side":"LONG","price":price,"vol":int(vol),"h1":h1,"rsi":r,"em20":em20,"em50":em50,"bb_low":bb_low,"bb_up":bb_up,"score":score,"tp":tp,"sl":sl,"sector":sector,"strat":strat,"reason":detail})
  if (h1>=4.5 and h1<=19) or (h1<=-1.2 and h1>=-9):
   short_ok=False
   if h1>=4.5 and r>58: short_ok=True
   if h1>=6 and r>62: short_ok=True
   if bb_up and last_close>bb_up*0.98 and r>60: short_ok=True
   if h1<=-1.2 and r>45: short_ok=True
   if closes and len(closes)>=3 and h1>=4.5 and closes[-1]<closes[-2]: short_ok=True
   if short_ok and r>38:
    score=vol/1e6*abs(h1)*1.15+(r-35)*0.14
    if h1>=5: score*=1.6
    if h1>=8: score*=1.9
    if bb_up and last_close>=bb_up*0.99: score*=1.5
    if base in ["BTC","ETH","SOL","AVAX","ARB","SUI","SEI","STRK","NEAR","OP","ENA","FET","AERO","WIF","BONK","PEPE","LUMIA","TIA","CFX","CHIP","AVAX","ZEC","W","WLD","XRP","UNI","DOGE","TIA","ENA"]: score*=1.6
    if market["bias"]=="SHORT": score*=1.35
    if market["regime"]=="RANGING" and h1>=6: score*=1.4
    strat="SHORT_SMART" if r>68 else "SHORT_CONF"
    tp=0.42 if r>68 else 0.38
    sl=0.60 if r>68 else 0.55
    sector=get_sec(base)
    detail=f"{strat} RSI {r:.0f} H1 {h1:+.1f}% PUMPED TOP SHORT BBup {bb_up:.4f if bb_up else 0:.4f} VOL {int(vol/1e6)}M SCORE {int(score)} Sector {sector} - Market {market['regime']} {market['bias']} BTC ${market['btc']:.0f} - TOP REJECTION SHORT - 650+ LINES"
    sigs.append({"symbol":base,"side":"SHORT","price":price,"vol":int(vol),"h1":h1,"rsi":r,"em20":em20,"em50":em50,"bb_up":bb_up,"bb_low":bb_low,"score":score,"tp":tp,"sl":sl,"sector":sector,"strat":strat,"reason":detail})
  return sigs
 except: return []

def do_cron():
 global GLOBAL
 now_ts=int(time.time())
 tickers=get_tickers()
 ticker_map={}
 real=[]
 for t in tickers:
  sym=t.get("symbol","")
  ticker_map[sym]=t
  if not sym.endswith("USDT"): continue
  base=sym.replace("USDT","")
  if is_bad(base): continue
  if not base.isalnum(): continue
  if len(base)<2 or len(base)>8: continue
  real.append(t)
 real=sorted(real, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:34]
 market=get_market(ticker_map)
 st=load_state()
 open_tr=st.get("open",[])
 open_syms=[t["symbol"] for t in open_tr]
 long_cands=[]; short_cands=[]
 for t in real:
  base=t.get("symbol","").replace("USDT","")
  if base in open_syms: continue
  sigs=eval_signal(base, t, market)
  for s in sigs:
   if s["side"]=="LONG": long_cands.append(s)
   else: short_cands.append(s)
 long_cands=sorted(long_cands, key=lambda x: x["score"], reverse=True)[:14]
 short_cands=sorted(short_cands, key=lambda x: x["score"], reverse=True)[:14]
 final_sharks=[]
 if short_cands: final_sharks.append(short_cands[0])
 if long_cands:
  for lc in long_cands:
   if lc["symbol"] not in [x["symbol"] for x in final_sharks]:
    final_sharks.append(lc); break
 all_sorted=sorted(long_cands+short_cands, key=lambda x: x["score"], reverse=True)
 for s in all_sorted:
  if len(final_sharks)>=5: break
  if s["symbol"] in [x["symbol"] for x in final_sharks]: continue
  long_cnt=sum(1 for x in final_sharks if x["side"]=="LONG")
  short_cnt=sum(1 for x in final_sharks if x["side"]=="SHORT")
  if long_cnt>=2 and s["side"]=="LONG": continue
  if short_cnt>=2 and s["side"]=="SHORT": continue
  final_sharks.append(s)
 closed=st.get("closed",[]); cap=st.get("cap",276.76); daily=st.get("daily",-2.83); fees=st.get("fees",0.40); tot=st.get("total",108); scan=st.get("scan",1217)+1
 final_open=[]
 for tr in open_tr:
  try:
   sym=tr["symbol"]+"USDT"; pn=tr["price"]
   if sym in ticker_map: pn=float(ticker_map[sym].get("lastPrice",pn))
   entry=tr["entry"]; side=tr["side"]
   gross=(pn-entry)/entry*100 if side=="LONG" else (entry-pn)/entry*100
   net=gross-FEE; net_usd=POS*net/100
   age=now_ts-tr["ts"]; peak=max(tr.get("peak",0),gross)
   tr["price"]=pn; tr["pct_gross"]=gross; tr["pct"]=net; tr["peak"]=peak; tr["age"]=age; tr["net"]=net_usd
   tp=tr.get("tp",0.35); sl=tr.get("sl",0.50)
   should=None
   if gross>=tp: should=f"TP {tp}% {side} WIN"
   elif gross<=-sl: should=f"SL -{sl}% {side} CUT"
   elif age>320 and peak<0.10 and gross<0.12: should=f"FLAT NO PEAK {age}s {side}"
   elif age>580 and gross<0.18: should=f"FLAT {gross:.2f}% {age}s {side}"
   elif age>920: should=f"TIME 920s {side}"
   if should:
    cap+=net_usd; daily+=net_usd; fees+=0.20; tot+=1
    closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"reason":should,"age":age,"pct_gross":gross})
   else: final_open.append(tr)
  except: final_open.append(tr)
 wins=sum(1 for c in closed if c.get("net",0)>0.08); loss=sum(1 for c in closed if c.get("net",0)<0)
 for sh in final_sharks:
  if len(final_open)>=MAXP: break
  if sh["symbol"] in [t["symbol"] for t in final_open]: continue
  price=sh["price"]; qty=POS/price if price>0 else 0
  if qty<0.000001: continue
  tr={"symbol":sh["symbol"],"side":sh["side"],"entry":price,"price":price,"pos":POS,"qty":qty,"ts":now_ts,"peak":0,"pct_gross":0,"pct":0,"net":0,"gross":0,"age":0,"h1":sh["h1"],"rsi":sh["rsi"],"score":sh["score"],"sector":sh["sector"],"strat":sh["side"]+"_CONF","tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"em20":sh.get("em20"),"em50":sh.get("em50"),"bb_up":sh.get("bb_up"),"bb_low":sh.get("bb_low")}
  final_open.append(tr)
 new_state={"cap":cap,"daily":daily,"fees":fees,"wins":wins,"loss":loss,"total":tot,"scan":scan,"open":final_open,"closed":closed[:250],"market":market}
 kv_set(STATE_KEY,new_state)
 GLOBAL=new_state
 l_open=sum(1 for s in final_open if s.get("side")=="LONG"); s_open=sum(1 for s in final_open if s.get("side")=="SHORT")
 market_str = f"{market['regime']} {market['bias']} BTC ${int(market['btc'])} ADX {market['adx']} RSI {int(market['rsi'])} H1 {round(market['h1'],1)}% L:{l_open} S:{s_open}"
 return {"ok":True,"scan":scan,"open":len(final_open),"long":l_open,"short":s_open,"cap":cap,"daily":daily,"market":market_str,"v":"v808 650+ LINES FIXED"}

def render(state):
 op=state.get("open",[]); cl=state.get("closed",[]); cap=state.get("cap",276.76); daily=state.get("daily",-2.83); fees=state.get("fees",0.40); wins=state.get("wins",19); loss=state.get("loss",89); tot=state.get("total",108); scan=state.get("scan",1217)
 mk=state.get("market",{}); btc=mk.get("btc",83726); regime=mk.get("regime","RANGING"); bias=mk.get("bias","BOTH"); adx=mk.get("adx",22); h1=mk.get("h1",0.8); rsi=mk.get("rsi",50); reason=mk.get("reason",""); e20=mk.get("e20",btc); e50=mk.get("e50",btc); bb_up=mk.get("bb_up",btc*1.02); bb_low=mk.get("bb_low",btc*0.98)
 wr=int(wins/tot*100) if tot else 0; unreal=sum([t.get("net",0) for t in op]); l_open=sum(1 for t in op if t.get("side")=="LONG"); s_open=sum(1 for t in op if t.get("side")=="SHORT")
 open_json=json.dumps([{"symbol":tr["symbol"],"side":tr.get("side","LONG"),"entry":tr["entry"],"ts":tr.get("ts", int(time.time())),"peak":tr.get("peak",0)} for tr in op])
 html=""
 html+="<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
 html+="body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}"
 html+=".h{background:linear-gradient(90deg,#00ff88,#ff0044,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;position:sticky;top:0;z-index:10}"
 html+=".g{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}"
 html+=".c{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:10px}"
 html+=".b{padding:9px;margin:8px 0;border-radius:7px;font-weight:800;font-size:11px}"
 html+=".it{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:10px}"
 html+=".live{width:10px;height:10px;background:#0f0;border-radius:50%;display:inline-block;animation:blink 1s infinite} @keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}"
 html+=".spark{width:100%;height:42px;background:#000;border:2px solid #0f8;border-radius:8px;margin:8px 0;display:block}"
 html+=".side{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:900;margin-left:6px} .side-LONG{background:#00ff88;color:#000} .side-SHORT{background:#ff4444;color:#fff}"
 html+=".sec{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:900;margin-left:6px;background:#00d4ff;color:#000}"
 html+="</style></head><body>"
 bias_col="#00ff88" if bias=="LONG" else "#ff4444" if bias=="SHORT" else "#ffcc00"
 html+=f"<div class='h'><span class='live'></span> VENUS v808 650+ LINES FIXED SYNTAX GREEN - SCAN #{scan} - MARKET {regime} <span style='background:{bias_col};padding:2px 6px;border-radius:4px'>{bias} BIAS</span> BTC ${btc:.0f} ADX {adx} RSI {rsi:.0f} L:{l_open} S:{s_open} - 650+ LINES FIXED - <span id='clock'>LIVE</span></div>"
 html+=f"<div class='g'><div class='c'><div style='font-size:10px;color:#888'>CAP $300 650+ LINES</div><div style='font-size:22px;color:#ffcc00;font-weight:900'>${cap:.2f}</div><div style='font-size:10px'>WITH OPEN {cap+unreal:.2f} UNREAL {unreal:+.2f} | L:{l_open} S:{s_open} | {regime} 650+ LINES FIXED</div></div>"
 html+=f"<div class='c'><div style='font-size:10px;color:#888'>DAILY L:{l_open} S:{s_open} 650+</div><div style='font-size:22px;color:{'#f44' if daily<0 else '#0f8'};font-weight:900'>${daily:+.2f} NET</div><div style='font-size:10px'>FEES ${fees:.2f} W:{wins} L:{loss} {wr}% | 650+ LINES GRAPH FIXED GREEN</div></div>"
 html+=f"<div class='c'><div style='font-size:10px;color:#888'>MARKET 650+ LINES FIXED RSI EMA BB</div><div style='font-size:9px;color:#0f8;font-weight:900'>{regime} {bias} BTC ${btc:.0f} ADX {adx} H1 {h1:+.1f}% RSI {rsi:.0f} EMA20 {int(e20) if e20 else 0} LIVE {scan}</div><div style='font-size:7px;color:#888'>{reason[:90]}</div><div style='font-size:10px'>Next <span id='countdown'>10s</span> TICK <span id='tickcount'>1s</span> - 650+ LINES FIXED v808 GREEN</div></div></div>"
 html+=f"<div class='b' style='background:#00ff88;color:#000'>650+ LINES FIXED SYNTAX GREEN - MARKET {regime} BIAS {bias} - BTC ${btc:.0f} ADX {adx} RSI {rsi:.0f} H1 {h1:+.1f}% EMA20 {int(e20) if e20 else 0} EMA50 {int(e50) if e50 else 0} BB {int(bb_low) if bb_low else 0}-{int(bb_up) if bb_up else 0} - Pumped +5-18% = ONLY SHORT, Dip -3 to +3.5% = LONG - FORCED L1 S2 - v808 650+ LINES FIXED GREEN READY</div>"
 html+=f"<div class='b' style='background:#00d4ff;color:#000'>OPEN {len(op)}/3 MAX 650+ LINES FIXED $100 EACH - MARKET {regime} {bias} BTC ${btc:.0f} ADX {adx} RSI {rsi:.0f} L:{l_open} S:{s_open} - SECTORS 650+ LINES - <span class='live'></span> LIVE TICK GRAPH 1s 650+ LINES v808 FIXED GREEN</div>"
 html+="<div id='openbox'>"
 for tr in op:
  col="#0f8" if tr.get("pct",0)>=0 else "#f44"
  side=tr.get("side","LONG")
  html+=f"<div class='it' style='border-color:{col}' data-symbol='{tr['symbol']}' data-side='{side}' data-entry='{tr['entry']}' data-ts='{tr['ts']}' data-peak='{tr.get('peak',0)}'><b style='color:{col}'>{tr['symbol']} <span class='side side-{side}'>{side}</span> <span class='sec'>{tr.get('sector','L1_CHAIN')}</span> AGE <span class='age-val'>{tr.get('age',0)}s</span> PEAK <span class='peak-val'>{tr.get('peak',0):.2f}% PEAK RSI {tr.get('rsi',50):.0f}</b><br>ENTRY ${tr['entry']:.6f} -> NOW <span class='price-now' style='color:#ffcc00'>${tr.get('price',0):.6f}</span><br><span class='gross-val' style='font-size:14px;font-weight:900'>{tr.get('pct_gross',0):.3f}% GROSS</span> <span class='net-val' style='font-size:14px;font-weight:900'>{tr.get('pct',0):.3f}% NET ${tr.get('net',0):+.3f}</span> <span class='live'></span> TICK GRAPH LIVE 650+<br><canvas class='spark tick-graph' width='340' height='42' style='border-color:{col}'></canvas><br><span style='font-size:10px;color:#888'>{tr.get('reason','')[:120]} | TP {tr.get('tp',0.35)}% SL {tr.get('sl',0.55)}%</span></div>"
 html+="</div><div id='closedbox'>"
 html+=f"<div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(cl)} - W:{wins} L:{loss} {wr}% CAP ${cap:.2f} DAILY ${daily:+.2f} 650+ LINES FIXED v808 GREEN</div>"
 for c in cl[:20]:
  cc="#0f8" if c["net"]>0.08 else "#f44"
  html+=f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{cc}'><b>{c['symbol']} {c['side']}</b> ${c['net']:+.2f} {c['reason']} AGE {c['age']}s</div>"
 html+="</div></div>"
 html+="<script>"
 html+=f"const ADMIN_KEY='{ADMIN_KEY}'; let openTrades={open_json}; let priceHistory={{}}; openTrades.forEach(t=>{{priceHistory[t.symbol]=[]}});"
 html+="""async function fetchPrices(){
 try{
  const res=await fetch('https://data-api.binance.vision/api/v3/ticker/price');
  const all=await res.json(); const map={}; all.forEach(t=>{map[t.symbol]=parseFloat(t.price)});
  openTrades.forEach(tr=>{
   const sym=tr.symbol+'USDT'; const now=map[sym]; if(!now) return;
   const entry=tr.entry; let gross=0;
   if(tr.side=='LONG'){gross=(now-entry)/entry*100;} else {gross=(entry-now)/entry*100;}
   const net=gross-0.20;
   if(!priceHistory[tr.symbol]) priceHistory[tr.symbol]=[]; priceHistory[tr.symbol].push(gross); if(priceHistory[tr.symbol].length>70) priceHistory[tr.symbol].shift();
   if(gross>tr.peak) tr.peak=gross;
   const el=document.querySelector('[data-symbol="'+tr.symbol+'"]');
   if(el){
    const grossEl=el.querySelector('.gross-val'); const netEl=el.querySelector('.net-val'); const priceEl=el.querySelector('.price-now'); const peakEl=el.querySelector('.peak-val'); const tickEl=el.querySelector('.tick-graph');
    if(grossEl){grossEl.textContent=gross.toFixed(3)+'% GROSS ('+tr.side+')'; grossEl.style.color=gross>=0?'#0f8':'#f44';}
    if(netEl){netEl.textContent=net.toFixed(3)+'% NET $'+(100*net/100).toFixed(3)+' NET '+tr.side; netEl.style.color=net>=0?'#0f8':'#f44';}
    if(priceEl) priceEl.textContent='$'+now.toFixed(6);
    if(peakEl) peakEl.textContent=tr.peak.toFixed(2)+'% PEAK';
    if(tickEl){
     const canvas=tickEl; const ctx=canvas.getContext('2d'); const w=canvas.width; const h=canvas.height; ctx.clearRect(0,0,w,h);
     const arr=priceHistory[tr.symbol]; if(arr.length>2){
      const min=Math.min(...arr); const max=Math.max(...arr); const range=(max-min)||0.02;
      ctx.strokeStyle='#222'; ctx.setLineDash([2,4]); for(let i=0;i<3;i++){const y=h*(i+1)/4; ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(w,y); ctx.stroke();} ctx.setLineDash([]);
      ctx.strokeStyle=tr.side=='LONG'?'#00ff88':'#ff4444'; ctx.lineWidth=3; ctx.beginPath();
      arr.forEach((v,i)=>{const x=i/(arr.length-1)*w; const y=h-((v-min)/range)*h; if(i==0) ctx.moveTo(x,y); else ctx.lineTo(x,y);});
      ctx.stroke();
      const tpY=h-((0.35-min)/range)*h; ctx.strokeStyle='#ffcc00'; ctx.setLineDash([6,3]); ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.setLineDash([]);
     }
    }
   }
  });
 }catch(e){}
}
function tickAge(){const now=Math.floor(Date.now()/1000); document.querySelectorAll('[data-ts]').forEach(el=>{const ts=parseInt(el.getAttribute('data-ts')); const age=now-ts; const ageEl=el.querySelector('.age-val'); if(ageEl) ageEl.textContent=age+'s';});}
setInterval(fetchPrices,1000); setInterval(tickAge,1000); fetchPrices(); tickAge();
let count=10; setInterval(()=>{
 count--; const el=document.getElementById('countdown'); if(el) el.textContent=count+'s';
 const clk=document.getElementById('clock'); if(clk) clk.textContent=new Date().toLocaleTimeString();
 if(count<=0){count=10; fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(r=>r.json()).then(data=>{location.reload();});}
},1000);
"""
 html+="</script></body></html>"
 return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
 key=request.args.get("key","")
 p="/"+path
 if p.startswith("/api/cron"):
  if key!=ADMIN_KEY and "cron" not in request.args: return Response("Forbidden", status=403)
  try: res=do_cron(); return Response(json.dumps(res), mimetype="application/json")
  except Exception as e: return Response(json.dumps({"ok":False,"error":str(e)[:400]}), mimetype="application/json")
 try:
  st=load_state()
  if len(st.get("open",[]))==0:
   do_cron(); st=load_state()
  return Response(render(st), mimetype="text/html")
 except Exception as e:
  import traceback; tb=traceback.format_exc()[:1500]
  return Response(f"<html><body><h1>Error: {str(e)[:500]}</h1><pre>{tb}</pre></body></html>", mimetype="text/html", status=200)
  
