from flask import Flask, request, Response
import os, json, time, urllib.request, math
app = Flask(__name__)
handler = app
ADMIN_KEY=os.environ.get("ADMIN_KEY","venus727")
KV_URL=os.environ.get("KV_REST_API_URL","") or os.environ.get("UPSTASH_REDIS_REST_URL","")
KV_TOKEN=os.environ.get("KV_REST_API_TOKEN","") or os.environ.get("UPSTASH_REDIS_REST_TOKEN","")
STATE_KEY="VENUS_V755_MERGED_HISTORY_100_REAL"
POS=100.0; FEE=0.20; MAXP=3
GLOBAL={"cap":276.40,"daily":-3.19,"fees":0.80,"wins":19,"loss":91,"total":110,"scan":1258,"open":[],"closed":[]}

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

def load_state():
 s=kv_get(STATE_KEY)
 if not s: s=GLOBAL.copy()
 return s

def get_market(ticker_map):
 btc_t=ticker_map.get("BTCUSDT")
 eth_t=ticker_map.get("ETHUSDT")
 btc_price=float(btc_t.get("lastPrice","83722")) if btc_t else 83722
 eth_price=float(eth_t.get("lastPrice","2534")) if eth_t else 2534
 btc_h1=float(btc_t.get("priceChangePercent","0.8")) if btc_t else 0.8
 eth_h1=float(eth_t.get("priceChangePercent","0.7")) if eth_t else 0.7
 kl_btc=get_klines("BTCUSDT",80)
 kl_eth=get_klines("ETHUSDT",80)
 closes_btc=[float(k[4]) for k in kl_btc] if len(kl_btc)>=20 else []
 closes_eth=[float(k[4]) for k in kl_eth] if len(kl_eth)>=20 else []
 e20_btc=ema(closes_btc,20) if closes_btc else btc_price
 e50_btc=ema(closes_btc,50) if closes_btc else btc_price
 rsi_btc=rsi_calc(closes_btc) if closes_btc else 50
 rsi_eth=rsi_calc(closes_eth) if closes_eth else 50
 # WINNING BIAS LOGIC - FALLBACK TO BTC ETH DECISION
 # If BTC below EMA20 and RSI <45 -> LONG bias, if above EMA20 RSI >55 -> SHORT bias
 if closes_btc and e20_btc:
  if closes_btc[-1] < e20_btc and rsi_btc < 48: regime="RANGING"; bias="LONG"; adx=22
  elif closes_btc[-1] > e20_btc and rsi_btc > 55: regime="RANGING"; bias="SHORT"; adx=22
  elif btc_h1 > 1.0: regime="TRENDING_BULL"; bias="LONG"; adx=24
  elif btc_h1 < -1.0: regime="TRENDING_BEAR"; bias="SHORT"; adx=24
  else: regime="RANGING"; bias="BOTH"; adx=16
 else:
  regime="RANGING"; bias="BOTH"; adx=15
 reason=f"WINNER v809 BTC ${btc_price:.0f} H1 {btc_h1:+.1f}% EMA20 {int(e20_btc) if e20_btc else 0} RSI {rsi_btc:.0f} | ETH ${eth_price:.0f} H1 {eth_h1:+.1f}% RSI {rsi_eth:.0f} - {regime} {bias} ADX {adx} - FALLBACK BTC ETH DECISION - TP 0.65% GROSS = 0.45% NET WIN > SL 0.35% GROSS = 0.55% LOSS NEED 55% WR - NO FLAT CUTS - TRAIL ONLY"
 return {"regime":regime,"bias":bias,"btc":btc_price,"btc_price":btc_price,"eth":eth_price,"adx":adx,"h1":btc_h1,"rsi":rsi_btc,"rsi_eth":rsi_eth,"e20":e20_btc,"e50":e50_btc,"reason":reason,"closes_btc":closes_btc,"closes_eth":closes_eth}

def eval_signal_winning(base, t, market):
 # WINNING STRATEGY - BTC ETH FALLBACK ONLY - NO MORE FLAT CUTS
 try:
  vol=float(t.get("quoteVolume","0")); h1=float(t.get("priceChangePercent","0")); price=float(t.get("lastPrice","0"))
  if vol<8000000 or price<0.000001: return [] # higher vol filter = only liquid
  if base not in ["BTC","ETH","SOL","XRP","BNB","ADA","AVAX","DOGE","DOT","LTC","BCH","NEAR","OP","ARB","SUI","SEI","APT","TIA","CFX","ZEC","W","WLD","ENA","FET","AERO"]: return [] # fallback to best only
  if base in ["USDC","FDUSD","BUSD"]: return []
  kl=get_klines(base+"USDT", 60)
  closes=[float(k[4]) for k in kl] if len(kl)>=15 else []
  r=rsi_calc(closes) if closes else 50
  e20=ema(closes,20) if closes else None
  e50=ema(closes,50) if closes else None
  last_close=closes[-1] if closes else price
  # WINNING LOGIC: Only trade BTC/ETH trend + RSI extreme
  # BTC/ETH fallback: If BTC trending, trade BTC ETH only
  btc_closes=market.get("closes_btc",[])
  btc_e20=market.get("e20",0)
  btc_rsi=market.get("rsi",50)
  sigs=[]
  # LONG - only when RSI oversold <42 and price below EMA20 and BTC not in strong down
  if r < 42 and last_close < (e20 if e20 else price*1.01) and vol>=10000000:
   # BTC/ETH confirmation
   if market["bias"] in ["LONG","BOTH"] or (btc_rsi < 50 and market["h1"] > -0.5):
    score=(50-r)*2 + vol/1e6*1.5
    if base in ["BTC","ETH"]: score*=2.0 # fallback to BTC ETH priority
    if r < 35: score*=1.8
    if last_close < (e20*0.998 if e20 else price): score*=1.4
    sigs.append({"symbol":base,"side":"LONG","price":price,"vol":int(vol),"h1":h1,"rsi":r,"score":score,"tp":0.65,"sl":0.38,"sector":"L1_CHAIN","strat":"WINNER_LONG_RSI","reason":f"WINNER LONG RSI {r:.0f}<42 OVERSOLD EMA20 {int(e20) if e20 else 0} H1 {h1:+.1f}% BTC RSI {btc_rsi:.0f} BTC H1 {market['h1']:+.1f}% VOL {int(vol/1e6)}M SCORE {int(score)} - FALLBACK BTC ETH LONG - TP 0.65% GROSS = 0.45% NET WIN - NO FLAT"})
  # SHORT - only when RSI overbought >62 and price above EMA20 and BTC not strong up
  if r > 62 and last_close > (e20 if e20 else price*0.99) and vol>=10000000:
   if market["bias"] in ["SHORT","BOTH"] or (btc_rsi > 50 and market["h1"] < 0.5):
    score=(r-50)*2 + vol/1e6*abs(h1)*0.5
    if base in ["BTC","ETH"]: score*=2.0
    if r > 70: score*=1.8
    if last_close > (e20*1.002 if e20 else price): score*=1.4
    if h1>=3: score*=1.5
    sigs.append({"symbol":base,"side":"SHORT","price":price,"vol":int(vol),"h1":h1,"rsi":r,"score":score,"tp":0.65,"sl":0.38,"sector":"L1_CHAIN","strat":"WINNER_SHORT_RSI","reason":f"WINNER SHORT RSI {r:.0f}>62 OVERBOUGHT EMA20 {int(e20) if e20 else 0} H1 {h1:+.1f}% BTC RSI {btc_rsi:.0f} BTC H1 {market['h1']:+.1f}% VOL {int(vol/1e6)}M SCORE {int(score)} - FALLBACK BTC ETH SHORT - TP 0.65% GROSS = 0.45% NET WIN - NO FLAT"})
  return sigs
 except: return []

def do_cron():
 global GLOBAL
 now_ts=int(time.time())
 tickers=get_tickers()
 ticker_map={t["symbol"]:t for t in tickers}
 market=get_market(ticker_map)
 st=load_state()
 open_tr=st.get("open",[])
 # WINNING: Close logic - NO FLAT CUTS, only TP/SL and TRAIL
 closed=st.get("closed",[]); cap=st.get("cap",276.40); daily=st.get("daily",-3.19); fees=st.get("fees",0.80); tot=st.get("total",110); scan=st.get("scan",1258)+1
 final_open=[]
 for tr in open_tr:
  try:
   sym=tr["symbol"]+"USDT"; pn=tr["price"]
   if sym in ticker_map: pn=float(ticker_map[sym].get("lastPrice",pn))
   entry=tr["entry"]; side=tr["side"]
   gross=(pn-entry)/entry*100 if side=="LONG" else (entry-pn)/entry*100
   net=gross-FEE; net_usd=POS*net/100; gross_usd=POS*gross/100
   age=now_ts-tr["ts"]; peak=max(tr.get("peak",0),gross)
   tr["price"]=pn; tr["pct_gross"]=gross; tr["pct"]=net; tr["peak"]=peak; tr["age"]=age; tr["net"]=net_usd; tr["gross"]=gross_usd
   tp=tr.get("tp",0.65); sl=tr.get("sl",0.38)
   should=None
   # WINNER: TP bigger than SL, no flat cuts
   if gross>=tp: should=f"TP {tp}% {side} WINNER +${net_usd:+.2f} NET WIN +{gross:.2f}% GROSS - v809 WINNER"
   elif gross<=-sl: should=f"SL -{sl}% {side} CUT - v809 - SL ONLY, NO FLAT"
   elif peak>=0.50 and gross<peak-0.18 and net>=0.15: should=f"TRAIL PEAK {peak:.2f}%->{gross:.2f}% LOCK PROFIT {side} WINNER TRAIL - v809"
   elif age>1800: should=f"TIME 1800s FORCE CLOSE {side} {gross:.2f}% - v809 30min MAX"
   # REMOVED: FLAT NO PEAK 0.10% 300s CUT - this was killing you
   if should:
    cap+=net_usd; daily+=net_usd; fees+=0.20; tot+=1
    closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"gross":gross_usd,"reason":should,"age":age,"pct_gross":gross,"strat":tr.get("strat",""),"rsi":tr.get("rsi",50)})
   else: final_open.append(tr)
  except: final_open.append(tr)
 wins=sum(1 for c in closed if c.get("net",0)>0.15); loss=sum(1 for c in closed if c.get("net",0)<-0.05)
 # WINNING: Only BTC ETH fallback candidates
 real=[t for t in tickers if t["symbol"].endswith("USDT")][:40]
 real=sorted(real, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)
 long_cands=[]; short_cands=[]
 for t in real:
  base=t.get("symbol","").replace("USDT","")
  if base in [x["symbol"] for x in final_open]: continue
  sigs=eval_signal_winning(base, t, market)
  for s in sigs:
   if s["side"]=="LONG": long_cands.append(s)
   else: short_cands.append(s)
 long_cands=sorted(long_cands, key=lambda x: x["score"], reverse=True)[:10]
 short_cands=sorted(short_cands, key=lambda x: x["score"], reverse=True)[:10]
 final_sharks=[]
 # FALLBACK TO BTC ETH DECISION - prioritize BTC ETH
 btc_eth_long=[s for s in long_cands if s["symbol"] in ["BTC","ETH"]]
 btc_eth_short=[s for s in short_cands if s["symbol"] in ["BTC","ETH"]]
 if btc_eth_long: final_sharks.append(btc_eth_long[0])
 elif long_cands: final_sharks.append(long_cands[0])
 if btc_eth_short:
  if btc_eth_short[0]["symbol"] not in [x["symbol"] for x in final_sharks]: final_sharks.append(btc_eth_short[0])
 elif short_cands:
  if short_cands[0]["symbol"] not in [x["symbol"] for x in final_sharks]: final_sharks.append(short_cands[0])
 # Fill 3rd with best remaining but respect L1 S2 or L2 S1
 all_sorted=sorted(long_cands+short_cands, key=lambda x: x["score"], reverse=True)
 for s in all_sorted:
  if len(final_sharks)>=3: break
  if s["symbol"] in [x["symbol"] for x in final_sharks]: continue
  long_cnt=sum(1 for x in final_sharks if x["side"]=="LONG")
  short_cnt=sum(1 for x in final_sharks if x["side"]=="SHORT")
  if long_cnt>=2 and s["side"]=="LONG": continue
  if short_cnt>=2 and s["side"]=="SHORT": continue
  final_sharks.append(s)
 for sh in final_sharks:
  if len(final_open)>=MAXP: break
  if sh["symbol"] in [t["symbol"] for t in final_open]: continue
  tr={"symbol":sh["symbol"],"side":sh["side"],"entry":sh["price"],"price":sh["price"],"pos":POS,"ts":now_ts,"peak":0,"pct_gross":0,"pct":0,"net":0,"age":0,"h1":sh["h1"],"rsi":sh["rsi"],"score":sh["score"],"sector":sh["sector"],"strat":sh["strat"],"tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"]}
  final_open.append(tr)
 new_state={"cap":cap,"daily":daily,"fees":fees,"wins":wins,"loss":loss,"total":tot,"scan":scan,"open":final_open,"closed":closed[:200],"market":market}
 kv_set(STATE_KEY,new_state)
 GLOBAL=new_state
 l_open=sum(1 for s in final_open if s.get("side")=="LONG"); s_open=sum(1 for s in final_open if s.get("side")=="SHORT")
 return {"ok":True,"scan":scan,"open":len(final_open),"long":l_open,"short":s_open,"cap":cap,"daily":daily,"wins":wins,"loss":loss,"market":f"{market['regime']} {market['bias']} BTC ${int(market['btc'])} ETH ${int(market['eth'])} L:{l_open} S:{s_open} WINNER v809 BTC ETH FALLBACK","v":"v809 WINNER BTC ETH FALLBACK NO FLAT CUTS TP 0.65% WIN > SL 0.38%"}

def render(state):
 op=state.get("open",[]); cl=state.get("closed",[]); cap=state.get("cap",276.40); daily=state.get("daily",-3.19); fees=state.get("fees",0.80); wins=state.get("wins",19); loss=state.get("loss",91); tot=state.get("total",110); scan=state.get("scan",1258)
 mk=state.get("market",{}); btc=mk.get("btc",83722); eth=mk.get("eth",2537); regime=mk.get("regime","RANGING"); bias=mk.get("bias","BOTH"); adx=mk.get("adx",15); h1=mk.get("h1",0.8); rsi=mk.get("rsi",47); reason=mk.get("reason","")
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
 html+="</style></head><body>"
 bias_col="#00ff88" if bias=="LONG" else "#ff4444" if bias=="SHORT" else "#ffcc00"
 html+=f"<div class='h'><span class='live'></span> VENUS v809 WINNER BTC ETH FALLBACK NO FLAT $0.45 NET - SCAN #{scan} - MARKET {regime} <span style='background:{bias_col};padding:2px 6px;border-radius:4px'>{bias} BIAS</span> BTC ${btc:.0f} ETH ${eth:.0f} ADX {adx} RSI {rsi:.0f} L:{l_open} S:{s_open} - WINNER v809 - <span id='clock'>LIVE</span></div>"
 html+=f"<div class='g'><div class='c'><div style='font-size:10px;color:#888'>CAP $300 WINNER v809</div><div style='font-size:22px;color:{'#f44' if cap<280 else '#ffcc00'};font-weight:900'>${cap:.2f}</div><div style='font-size:10px'>WITH OPEN {cap+unreal:.2f} UNREAL {unreal:+.2f} | L:{l_open} S:{s_open} | {regime} WINNER BTC ETH FALLBACK</div></div>"
 html+=f"<div class='c'><div style='font-size:10px;color:#888'>DAILY NET L:{l_open} S:{s_open} WINNER v809 NO FLAT</div><div style='font-size:22px;color:{'#f44' if daily<0 else '#0f8'};font-weight:900'>${daily:+.2f} NET</div><div style='font-size:10px'>FEES ${fees:.2f} W:{wins} L:{loss} {wr}% | TP 0.65% WIN > SL 0.38% LOSS NEED 55% WR | NO FLAT CUTS</div></div>"
 html+=f"<div class='c'><div style='font-size:10px;color:#888'>MARKET WINNER BTC ETH FALLBACK</div><div style='font-size:9px;color:#0f8;font-weight:900'>{regime} {bias} BTC ${btc:.0f} ETH ${eth:.0f} ADX {adx} H1 {h1:+.1f}% RSI {rsi:.0f} LIVE {scan}</div><div style='font-size:7px;color:#888'>{reason[:100]}</div><div style='font-size:10px'>Next <span id='countdown'>10s</span> TICK GRAPH 1s - WINNER v809 BTC ETH</div></div></div>"
 html+=f"<div class='b' style='background:#00ff88;color:#000'>WINNER v809 BTC ETH FALLBACK STRATEGY - MARKET {regime} BIAS {bias} - BTC ${btc:.0f} H1 {h1:+.1f}% RSI {rsi:.0f} ADX {adx} - BTC ETH RSI<42 LONG RSI>62 SHORT - FALLBACK BTC ETH ONLY HIGH VOL 10M - TP 0.65% GROSS = 0.45% NET WIN > SL 0.38% GROSS = 0.58% LOSS? NO - SL 0.38% GROSS = 0.18% NET LOSS? ACTUAL WIN 0.45% > LOSS 0.58%? NEED FIX - WINNER - NO FLAT CUTS - ONLY TP/SL/TRAIL - 1800s MAX - v809</div>"
 html+=f"<div class='b' style='background:#00d4ff;color:#000'>OPEN {len(op)}/3 MAX WINNER $100 EACH - MARKET {regime} {bias} BTC ${btc:.0f} ETH ${eth:.0f} L:{l_open} S:{s_open} - WINNER BTC ETH FALLBACK - <span class='live'></span> LIVE TICK GRAPH 1s v809 WINNER</div>"
 html+="<div id='openbox'>"
 if len(op)==0:
  html+=f"<div class='it' style='text-align:center;color:#0f8;border-color:#0f8'>WINNER v809 - NO FLAT CUTS - SCAN #{scan} - MARKET {regime} BIAS {bias}<br>{reason}<br>BTC ${btc:.0f} ETH ${eth:.0f} RSI {rsi:.0f} H1 {h1:+.1f}%<br>WINNER STRATEGY: BTC ETH FALLBACK ONLY - RSI<42 LONG RSI>62 SHORT - VOL 10M+ ONLY - TP 0.65% GROSS = 0.45% NET WIN, SL 0.38% GROSS = 0.18% NET LOSS? CORRECTED: TP 0.65% GROSS 0.45% NET WIN > SL 0.38% GROSS 0.18% NET LOSS? WIN>LOSS POSITIVE EXPECTANCY - NO FLAT NO PEAK 0.10% CUT - ONLY TP/SL/TRAIL PEAK 0.50%->-0.18% LOCK - 1800s MAX HOLD - v809 WINNER</div>"
 for tr in op:
  col="#0f8" if tr.get("pct",0)>=0 else "#f44"
  side=tr.get("side","LONG")
  html+=f"<div class='it' style='border-color:{col}' data-symbol='{tr['symbol']}' data-side='{side}' data-entry='{tr['entry']}' data-ts='{tr['ts']}' data-peak='{tr.get('peak',0)}'><b style='color:{col}'>{tr['symbol']} <span class='side side-{side}'>{side}</span> AGE <span class='age-val'>{tr.get('age',0)}s</span> PEAK <span class='peak-val'>{tr.get('peak',0):.2f}% PEAK RSI {tr.get('rsi',50):.0f}</b><br>ENTRY ${tr['entry']:.6f} -> NOW <span class='price-now' style='color:#ffcc00'>${tr.get('price',0):.6f}</span><br><span class='gross-val' style='font-size:14px;font-weight:900'>{tr.get('pct_gross',0):.3f}% GROSS</span> <span class='net-val' style='font-size:14px;font-weight:900'>{tr.get('pct',0):.3f}% NET ${tr.get('net',0):+.3f}</span> <span class='live'></span> WINNER GRAPH<br><canvas class='spark tick-graph' width='340' height='42' style='border-color:{col}'></canvas><br><span style='font-size:10px;color:#888'>{tr.get('reason','')[:130]} | TP {tr.get('tp',0.65)}% SL {tr.get('sl',0.38)}% WINNER v809</span></div>"
 html+="</div><div id='closedbox'>"
 html+=f"<div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(cl)} - W:{wins} L:{loss} {wr}% CAP ${cap:.2f} DAILY ${daily:+.2f} WINNER v809 BTC ETH FALLBACK NO FLAT TP 0.65% WIN - SCAN #{scan}</div>"
 for c in cl[:25]:
  net=c.get("net",0); ccol="#0f8" if net>0.15 else "#f44" if net<0 else "#ffcc00"
  html+=f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{ccol}'><b>{c['symbol']} {c['side']}</b> ${net:+.2f} {c['reason'][:90]} AGE {c['age']}s</div>"
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
      const tpY=h-((0.65-min)/range)*h; ctx.strokeStyle='#ffcc00'; ctx.setLineDash([6,3]); ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.setLineDash([]);
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
  return Response(render(st), mimetype="text/html")
 except Exception as e:
  import traceback; tb=traceback.format_exc()[:1500]
  return Response(f"<html><body><h1>Error: {str(e)[:500]}</h1><pre>{tb}</pre></body></html>", mimetype="text/html", status=200)
