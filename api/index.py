from flask import Flask, request, Response
import os, json, time, urllib.request, math, random
app = Flask(__name__)
handler = app

def env(k):
 for kk in k:
  v=os.environ.get(kk)
  if v: return v.strip().strip('"').strip("'")
 return ""
KV_URL=(env(["KV_REST_API_URL","UPSTASH_REDIS_REST_URL"]) or "").rstrip("/")
if not KV_URL:
 for kk,vv in os.environ.items():
  if "REDIS" in kk and "URL" in kk and "upstash" in vv.lower():
   KV_URL=vv.strip().strip('"').strip("'").rstrip("/")
   break
KV_TOKEN=env(["KV_REST_API_TOKEN","UPSTASH_REDIS_REST_TOKEN"])
if not KV_TOKEN:
 for kk,vv in os.environ.items():
  if "REDIS" in kk and "TOKEN" in kk and "upstash" in kk.lower():
   KV_TOKEN=vv.strip().strip('"').strip("'")
   break
ADMIN_KEY=env(["ADMIN_KEY"]) or "venus727"
STATE_KEY="VENUS_V755_MERGED_HISTORY_100_REAL"
POS=100.0
FEE_PCT=0.20
FEE_USD=0.20
MAXP=3

SECTORS={
 "L1_CHAIN":["BTC","ETH","ETC","ARB","SUI","SEI","APT","TIA","ATOM","AVAX","SOL","NEAR","OP","STRK","ZK","SAGA","DOGE","CFX","ZEC","CHIP","SUI","ARB","LUMIA","ENA"],
 "DEPIN_WIFI":["FIL","RNDR","THETA","IOTX","AR","STORJ","HNT","AKT","GRT","FET","AERO","W","JASMY"],
 "AI":["EIGEN","TAO","FET","ARKM","RNDR","GRT","LUMIA","ZEC","CFX","WLD","AGIX"],
 "DEFI":["ENA","PENDLE","AERO","LDO","UNI","AAVE","ETHFI","BTC","ETH","AVAX","ONDO","LUMIA","NEAR","MKR","COMP","CRV"],
 "MEME":["PEPE","BONK","WIF","FLOKI","SHIB","BOME","POPCAT","BRETT","DOGE","PUMP","TRUMP","MEW"],
 "RWA_GAMING":["IMX","RONIN","GALA","BEAM","PIXEL","ETC","BTC","APE","SAND","MANA","AXS"]
}
COIN_SECTOR={}
for sec, coins in SECTORS.items():
 for c in coins:
  if c not in COIN_SECTOR: COIN_SECTOR[c]=sec
BAD_EXACT=set(["USDC","FDUSD","TUSD","BUSD","DAI","USDP","EUR","BIDR","IDRT","TRY","BRL","BRLT","BVND","VAI","USDB","USD1","BFUSD","TRYT","PLN","UAH","NGN","BKRW","ZAR","JPY","GBP","AUD","UAHT","MATICBIDR","SOLBIDR","XRPBIDR","BUSDBIDR","STRKTRY","IDRT","BUSDTRY","BTCBIDR","USD1","1000PEPE","1000BONK","1000FLOKI","1000SHIB"])
BAD_CONTAINS=["BIDR","IDRT","TRYB","EURT","EURS","BVND","BRLT","BIDR"]
def is_bad(b):
 if b in BAD_EXACT: return True
 for bad in BAD_CONTAINS:
  if bad in b: return True
 if len(b)>8 or b.startswith("1000"): return True
 if "BID" in b: return True
 return False
def get_sector(c): return COIN_SECTOR.get(c,"OTHER_BEST")

def kv_get(k):
 if not KV_URL or not KV_TOKEN: return None
 try:
  body=json.dumps([["GET",k]]).encode()
  req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
  with urllib.request.urlopen(req, timeout=8) as r:
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
  with urllib.request.urlopen(req, timeout=8) as r:
   return "OK" in r.read().decode()
 except: return False

def kv_del(k):
 if not KV_URL or not KV_TOKEN: return False
 try:
  body=json.dumps([["DEL",k]]).encode()
  req=urllib.request.Request(f"{KV_URL}/pipeline", data=body, headers={"Authorization":f"Bearer {KV_TOKEN}","Content-Type":"application/json"})
  with urllib.request.urlopen(req, timeout=8) as r:
   return True
 except: return False

def get_tickers():
 try:
  req=urllib.request.Request("https://data-api.binance.vision/api/v3/ticker/24hr", headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req, timeout=8) as r:
   return json.loads(r.read().decode())
 except: return []

def get_klines(sym, lim=60):
 try:
  url=f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=5m&limit={lim}"
  req=urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req, timeout=6) as r:
   return json.loads(r.read().decode())
 except: return []

def ema(vals, p):
 if len(vals)<p: return None
 k=2/(p+1)
 em=sum(vals[:p])/p
 for v in vals[p:]:
  em=v*k+em*(1-k)
 return em

def rsi_calc(closes):
 try:
  if len(closes)<15: return 50
  gains=[]; losses=[]
  for i in range(1,len(closes)):
   d=closes[i]-closes[i-1]
   gains.append(max(d,0)); losses.append(max(-d,0))
  ag=sum(gains[:14])/14; al=sum(losses[:14])/14
  for i in range(14,len(gains)):
   ag=(ag*13+gains[i])/14; al=(al*13+losses[i])/14
  if al==0: return 100
  rs=ag/al
  return 100-100/(1+rs)
 except:
  return 50

def bb_calc(closes, p=20, mult=2):
 try:
  if len(closes)<p: return None,None,None
  sma=sum(closes[-p:])/p
  var=sum((x-sma)**2 for x in closes[-p:])/p
  std=math.sqrt(var)
  return sma+mult*std, sma, sma-mult*std
 except:
  return None,None,None

def load_state():
 s=kv_get(STATE_KEY)
 if not s:
  s={"cap":300.0,"daily":0.0,"daily_gross":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":"","last_coins":{}}}
 if "learn" not in s: s["learn"]={"blacklist":{},"pause_until":0,"last_date":"","last_coins":{}}
 L=s["learn"]
 L.setdefault("blacklist",{}); L.setdefault("pause_until",0); L.setdefault("last_date",""); L.setdefault("last_coins",{})
 today=time.strftime("%Y-%m-%d")
 if L.get("last_date")!=today:
  s["daily"]=0.0; s["daily_gross"]=0.0; s["fees_paid"]=0.0; L["last_date"]=today; L["pause_until"]=0; L["last_coins"]={}
 now=int(time.time())
 L["blacklist"]={k:v for k,v in L["blacklist"].items() if v>now}
 L["last_coins"]={k:v for k,v in L["last_coins"].items() if v>now}
 # fix old market keys
 mk=s.get("market",{})
 if mk:
  if "btc" not in mk: mk["btc"]=mk.get("btc_price",83660)
  if "btc_price" not in mk: mk["btc_price"]=mk.get("btc",83660)
  if "regime" not in mk: mk["regime"]="RANGING"
  if "bias" not in mk: mk["bias"]="BOTH"
  if "h1" not in mk: mk["h1"]=0
  if "adx" not in mk: mk["adx"]=16
  if "reason" not in mk: mk["reason"]="RANGING"
  s["market"]=mk
 return s

def get_market(ticker_map):
 btc_ticker=ticker_map.get("BTCUSDT")
 btc_price=float(btc_ticker.get("lastPrice","83660")) if btc_ticker else 83660
 h1=float(btc_ticker.get("priceChangePercent","0")) if btc_ticker else 0
 kl=get_klines("BTCUSDT", 80)
 if len(kl)<30:
  if h1>1.0: regime="TRENDING_BULL"; bias="LONG"; adx=22
  elif h1<-1.0: regime="TRENDING_BEAR"; bias="SHORT"; adx=22
  else: regime="RANGING"; bias="BOTH"; adx=15
  return {"regime":regime,"bias":bias,"btc":btc_price,"btc_price":btc_price,"adx":adx,"h1":h1,"reason":f"{regime} {bias} BTC ${btc_price:.0f} H1 {h1:+.1f}% SHORT PUMP +5-18% = ONLY SHORT, DIP -3 to +3.5% = LONG - FORCED L1 S2"}
 closes=[float(k[4]) for k in kl]
 e20=ema(closes,20); e50=ema(closes,50); e100=ema(closes,100)
 r=rsi_calc(closes)
 if e20 and e50 and e100:
  if closes[-1]>e20>e50 and h1>0.5 and r>45: regime="TRENDING_BULL"; bias="LONG"; adx=24 if r>55 else 21
  elif closes[-1]<e20<e50 and h1<-0.5 and r<55: regime="TRENDING_BEAR"; bias="SHORT"; adx=24 if r<45 else 21
  else: regime="RANGING"; bias="BOTH"; adx=16
 else:
  regime="RANGING"; bias="BOTH"; adx=15
 reason=f"{regime} {bias} BTC ${btc_price:.0f} H1 {h1:+.1f}% RSI {r:.0f} ADX {adx} {'EMA '+str(int(e20))+' > '+str(int(e50)) if e20 and e50 else ''} - Pumped +5-18% = ONLY SHORT, Dip -3 to +3.5% = LONG - FORCED L1 S2 - v805 600+ lines"
 return {"regime":regime,"bias":bias,"btc":btc_price,"btc_price":btc_price,"adx":adx,"h1":h1,"rsi":r,"e20":e20,"e50":e50,"reason":reason}

def eval_signal(base, t, market):
 try:
  vol=float(t.get("quoteVolume","0")); h1=float(t.get("priceChangePercent","0")); price=float(t.get("lastPrice","0"))
  if vol<4500000 or price<0.0000005: return []
  if is_bad(base): return []
  if not base.isalnum() or len(base)>8: return []
  kl=get_klines(base+"USDT", 50)
  closes=[float(k[4]) for k in kl] if len(kl)>=10 else []
  r=rsi_calc(closes) if closes else 50
  bb_up, bb_mid, bb_low = bb_calc(closes, 20, 2) if closes else (None,None,None)
  last_close=closes[-1] if closes else price
  em20=ema(closes,20) if closes else None
  em50=ema(closes,50) if closes else None
  sigs=[]
  # LONG signals - dip bounce
  if h1>=-3.5 and h1<=3.8:
   long_ok=False
   if r<55 and vol>=5000000: long_ok=True
   if bb_low and last_close<bb_low*1.02 and r<48: long_ok=True
   if em20 and em50 and last_close>em20 and r<60 and h1>=-2: long_ok=True
   if long_ok:
    score=vol/1e6*max(0.6, 2.5-abs(h1)*0.4)+(60-r)*0.15
    if base in ["BTC","ETH","SOL","AVAX","ARB","SUI","SEI","STRK","NEAR","OP","ENA","FET","AERO","WIF","BONK","PEPE","LUMIA","TIA","ATOM","DOGE","UNI","AAVE"]: score*=1.5
    if market["bias"]=="LONG": score*=1.35
    if market["regime"]=="TRENDING_BULL" and h1>=-1: score*=1.2
    if bb_low and last_close<=bb_low: score*=1.3
    strat="LONG_SMART" if r<45 else "LONG_CONF"
    tp=0.35 if r<45 else 0.32
    sl=0.50 if r<45 else 0.45
    sigs.append({"symbol":base,"side":"LONG","price":price,"vol":int(vol),"h1":h1,"rsi":r,"em20":em20,"em50":em50,"bb_low":bb_low,"score":score,"tp":tp,"sl":sl,"sector":get_sector(base),"strat":strat,"reason":f"{strat} RSI {r:.0f} H1 {h1:+.1f}% EMA {int(em20) if em20 else 0} BB {bb_low:.4f if bb_low else 0:.4f} Market {market['regime']} {market['bias']} BTC ${market['btc']:.0f} VOL {int(vol/1e6)}M"})
  # SHORT signals - pumped top
  if (h1>=4.5 and h1<=19) or (h1<=-1.2 and h1>=-9):
   short_ok=False
   if h1>=4.5 and r>58: short_ok=True
   if h1>=6 and r>62: short_ok=True
   if bb_up and last_close>bb_up*0.98 and r>60: short_ok=True
   if h1<=-1.2 and r>45: short_ok=True
   # confirmation: need red candle or high rsi
   if closes and len(closes)>=3:
    if h1>=4.5:
     # last 5m red or doji
     if closes[-1]<closes[-2] or r>65: short_ok=True
   if short_ok and r>38:
    score=vol/1e6*abs(h1)*1.1+(r-35)*0.12
    if h1>=5: score*=1.6
    if h1>=8: score*=1.8
    if bb_up and last_close>=bb_up*0.99: score*=1.4
    if base in ["BTC","ETH","SOL","AVAX","ARB","SUI","SEI","STRK","NEAR","OP","ENA","FET","AERO","WIF","BONK","PEPE","LUMIA","TIA","CFX","CHIP","AVAX","ZEC","W","WLD"]: score*=1.6
    if market["bias"]=="SHORT": score*=1.35
    if market["regime"]=="TRENDING_BEAR": score*=1.2
    if market["regime"]=="TRENDING_BULL" and h1>=7: score*=1.3
    strat="SHORT_SMART" if r>68 else "SHORT_CONF"
    tp=0.40 if r>68 else 0.36
    sl=0.58 if r>68 else 0.52
    sigs.append({"symbol":base,"side":"SHORT","price":price,"vol":int(vol),"h1":h1,"rsi":r,"em20":em20,"em50":em50,"bb_up":bb_up,"score":score,"tp":tp,"sl":sl,"sector":get_sector(base),"strat":strat,"reason":f"{strat} RSI {r:.0f} H1 {h1:+.1f}% PUMPED TOP SHORT BBup {bb_up:.4f if bb_up else 0:.4f} Market {market['regime']} {market['bias']} BTC ${market['btc']:.0f} VOL {int(vol/1e6)}M TOP REJECTION"})
  return sigs
 except Exception as e:
  return []

def do_cron():
 state=load_state()
 L=state["learn"]
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
 real=sorted(real, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:32]
 market=get_market(ticker_map)
 open_tr=state.get("open",[])
 open_syms=[t["symbol"] for t in open_tr]
 long_cands=[]
 short_cands=[]
 for t in real:
  base=t.get("symbol","").replace("USDT","")
  if base in open_syms: continue
  if base in L.get("blacklist",{}): continue
  if base in L.get("last_coins",{}): continue
  sigs=eval_signal(base, t, market)
  for s in sigs:
   if s["side"]=="LONG": long_cands.append(s)
   else: short_cands.append(s)
 long_cands=sorted(long_cands, key=lambda x: x["score"], reverse=True)[:12]
 short_cands=sorted(short_cands, key=lambda x: x["score"], reverse=True)[:12]
 final_sharks=[]
 if short_cands:
  final_sharks.append(short_cands[0])
 if long_cands:
  for lc in long_cands:
   if lc["symbol"] not in [x["symbol"] for x in final_sharks]:
    final_sharks.append(lc)
    break
 long_in_final=sum(1 for x in final_sharks if x["side"]=="LONG")
 short_in_final=sum(1 for x in final_sharks if x["side"]=="SHORT")
 all_sorted=sorted(long_cands+short_cands, key=lambda x: x["score"], reverse=True)
 for s in all_sorted:
  if len(final_sharks)>=5: break
  if s["symbol"] in [x["symbol"] for x in final_sharks]: continue
  if long_in_final>=2 and s["side"]=="LONG": continue
  if short_in_final>=2 and s["side"]=="SHORT": continue
  final_sharks.append(s)
  if s["side"]=="LONG": long_in_final+=1
  else: short_in_final+=1
 if len(final_sharks)<3:
  for s in all_sorted:
   if len(final_sharks)>=3: break
   if s["symbol"] in [x["symbol"] for x in final_sharks]: continue
   final_sharks.append(s)
 closed=state.get("closed",[])
 cap=state.get("cap",300.0)
 daily=state.get("daily",0.0)
 daily_gross=state.get("daily_gross",0.0)
 fees_paid=state.get("fees_paid",0.0)
 tot=state.get("total",0)
 scan=state.get("scan",0)+1
 final=[]
 for tr in open_tr:
  try:
   sym=tr["symbol"]+"USDT"
   price_now=tr.get("price", tr.get("entry",0))
   if sym in ticker_map:
    price_now=float(ticker_map[sym].get("lastPrice",price_now))
   entry=tr.get("entry", price_now)
   side=tr.get("side","LONG")
   if side=="LONG":
    pct_gross=(price_now-entry)/entry*100 if entry else 0
   else:
    pct_gross=(entry-price_now)/entry*100 if entry else 0
   pct_net=pct_gross - FEE_PCT
   net_usd=POS*pct_net/100
   gross_usd=POS*pct_gross/100
   age=now_ts-tr.get("ts",now_ts)
   peak_gross=max(tr.get("peak_gross",0), pct_gross)
   tr["price"]=price_now; tr["pct_gross"]=pct_gross; tr["pct"]=pct_net; tr["peak_gross"]=peak_gross; tr["peak"]=peak_gross-FEE_PCT; tr["age"]=age; tr["net"]=net_usd; tr["gross"]=gross_usd
   tp=tr.get("tp",0.35); sl=tr.get("sl",0.50)
   should=None
   if pct_gross>=tp:
    should=f"TP {tp}% {side} {tr.get('strat','')} +${net_usd:+.2f} NET WIN +{pct_gross:.2f}% GROSS"
   elif pct_gross<=-sl:
    should=f"SL -{sl}% {side} CUT FAST -{pct_gross:.2f}% GROSS"
   elif peak_gross>=0.30 and pct_gross<peak_gross-0.13 and pct_net>=0.05:
    should=f"TRAIL PEAK {peak_gross:.2f}%->{pct_gross:.2f}% -0.13% JUMP {side} LOCK PROFIT"
   elif age>300 and peak_gross<0.10 and pct_gross<0.12:
    should=f"NO PEAK 0.10% {age}s FLAT CUT {side} 300s TIMEOUT"
   elif age>550 and pct_gross<0.18 and peak_gross<0.25:
    should=f"FLAT {pct_gross:.2f}% PEAK {peak_gross:.2f}% {age}s CUT {side} FLAT TIMEOUT"
   elif age>900:
    should=f"TIME 900s FORCE {side} {pct_gross:.2f}% TIMEOUT"
   if should:
    cap+=net_usd; daily+=net_usd; daily_gross+=gross_usd; fees_paid+=FEE_USD; tot+=1
    closed.insert(0,{"symbol":tr["symbol"],"side":side,"net":net_usd,"gross":gross_usd,"fee":FEE_USD,"reason":should,"pct_gross":pct_gross,"pct_net":pct_net,"age":age,"sector":get_sector(tr["symbol"]),"strat":tr.get("strat",""),"rsi":tr.get("rsi",50),"h1":tr.get("h1",0)})
    L["last_coins"][tr["symbol"]]=now_ts+400
    if pct_net<-0.50:
     L["blacklist"][tr["symbol"]]=now_ts+1800
   else:
    final.append(tr)
  except:
   final.append(tr)
 wins=sum(1 for c in closed if c.get("net",0)>0.08)
 loss=sum(1 for c in closed if c.get("net",0)<0)
 for sh in final_sharks:
  if len(final)>=MAXP: break
  if sh["symbol"] in [t["symbol"] for t in final]: continue
  if sh["symbol"] in L.get("blacklist",{}): continue
  if sh["symbol"] in L.get("last_coins",{}): continue
  price=sh["price"]; qty=POS/price if price>0 else 0
  if qty<0.000001: continue
  tr={"symbol":sh["symbol"],"side":sh["side"],"entry":price,"price":price,"pos":POS,"qty":qty,"ts":now_ts,"peak_gross":0,"peak":0,"pct_gross":0,"pct":0,"net":0,"gross":0,"age":0,"h1":sh["h1"],"rsi":sh["rsi"],"score":sh["score"],"sector":sh["sector"],"strat":sh["side"]+"_CONF" if sh["side"]=="SHORT" else sh["side"]+"_CONF","tp":sh["tp"],"sl":sh["sl"],"reason":sh["reason"],"em20":sh.get("em20"),"em50":sh.get("em50")}
  final.append(tr)
 state["open"]=final; state["closed"]=closed[:250]; state["cap"]=cap; state["daily"]=daily; state["daily_gross"]=daily_gross; state["fees_paid"]=fees_paid; state["wins"]=wins; state["loss"]=loss; state["total"]=tot; state["scan"]=scan; state["market"]=market
 kv_set(STATE_KEY, state)
 long_c=sum(1 for s in final if s.get("side")=="LONG")
 short_c=sum(1 for s in final if s.get("side")=="SHORT")
 return {"ok":True,"scan":scan,"open":len(final),"long":long_c,"short":short_c,"cap":cap,"daily":daily,"sharks_long":len(long_cands),"sharks_short":len(short_cands),"total":tot,"wins":wins,"loss":loss,"market":market["regime"]+" "+market["bias"]+" BTC $"+str(int(market["btc"]))+" ADX "+str(market["adx"])+" H1 "+str(round(market["h1"],1))+"% L:"+str(long_c)+" S:"+str(short_c),"v":"v805 620 LINES FULL UI GRAPH SECTORS RSI EMA BB"}

def render(state):
 open_tr=state.get("open",[])
 closed=state.get("closed",[])
 cap=state.get("cap",300.0)
 daily=state.get("daily",0.0)
 daily_gross=state.get("daily_gross",0.0)
 fees_paid=state.get("fees_paid",0.0)
 wins=state.get("wins",0)
 loss=state.get("loss",0)
 tot=state.get("total",0)
 scan=state.get("scan",0)
 market=state.get("market",{"regime":"RANGING","bias":"BOTH","btc":83660,"btc_price":83660,"adx":22,"h1":0.8,"rsi":50,"reason":"RANGING"})
 winrate=int(wins/tot*100) if tot>0 else 0
 unreal=sum([t.get("net",0) for t in open_tr])
 long_open=sum(1 for t in open_tr if t.get("side")=="LONG")
 short_open=sum(1 for t in open_tr if t.get("side")=="SHORT")
 try:
  tickers=get_tickers()
  real=[]
  for t in tickers:
   sym=t.get("symbol","")
   if not sym.endswith("USDT"): continue
   base=sym.replace("USDT","")
   if is_bad(base): continue
   if not base.isalnum(): continue
   if len(base)>8: continue
   real.append(t)
  real=sorted(real, key=lambda x: float(x.get("quoteVolume","0")), reverse=True)[:12]
  sharks=[]
  for t in real:
   base=t["symbol"].replace("USDT","")
   h1=float(t.get("priceChangePercent","0"))
   vol=int(float(t.get("quoteVolume","0")))
   sector=get_sector(base)
   score=float(t.get("quoteVolume","0"))*abs(float(t.get("priceChangePercent","0")))/1e6
   side="SHORT" if h1>=4.5 else "LONG" if h1>=-3 else "HOLD"
   sharks.append({"symbol":base,"h1":h1,"vol":vol,"sector":sector,"score":score,"side":side})
 except:
  sharks=[]; used_sectors=set()
 else:
  used_sectors=set([get_sector(t["symbol"]) for t in open_tr])
 btc=market.get("btc", market.get("btc_price",83660))
 regime=market.get("regime","RANGING")
 bias=market.get("bias","BOTH")
 adx=market.get("adx",22)
 h1_m=market.get("h1",0)
 rsi_m=market.get("rsi",50)
 reason=market.get("reason","")
 html=""
 html+="<html><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"
 html+="body{background:#0a0a0a;color:#eee;font-family:monospace;font-size:12px;margin:0;padding:8px}"
 html+=".h{background:linear-gradient(90deg,#00ff88,#ff0044,#00d4ff);color:#000;padding:12px;text-align:center;font-weight:900;font-size:11px;position:sticky;top:0;z-index:10}"
 html+=".g{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:8px 0}"
 html+=".c{background:#1a1a1a;border:1px solid #333;padding:10px;text-align:center;border-radius:10px}"
 html+=".b{padding:9px;margin:8px 0;border-radius:7px;font-weight:800;font-size:11px}"
 html+=".by{background:#ffcc00;color:#000} .bb{background:#00d4ff;color:#000} .bd{background:#222;color:#888} .bg{background:#00ff88;color:#000} .bp{background:#ff00ff;color:#fff} .br{background:#ff4444;color:#fff}"
 html+=".it{background:#111;border:1px solid #333;padding:10px;margin:6px 0;border-radius:10px;position:relative;overflow:hidden}"
 html+=".live{width:10px;height:10px;background:#0f0;border-radius:50%;display:inline-block;animation:blink 1s infinite} @keyframes blink{0%,100%{opacity:1}50%{opacity:0.3}}"
 html+=".spark{width:100%;height:36px;background:#0a0a0a;border:1px solid #222;border-radius:6px;margin:6px 0}"
 html+=".sec{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:900;margin-left:6px}"
 html+=".strat{padding:2px 6px;border-radius:4px;font-size:8px;font-weight:900;margin-left:4px;background:#333;color:#fff}"
 html+=".side{padding:2px 6px;border-radius:4px;font-size:9px;font-weight:900;margin-left:6px} .side-LONG{background:#00ff88;color:#000} .side-SHORT{background:#ff4444;color:#fff}"
 html+=".s-L1_CHAIN{background:#00d4ff;color:#000} .s-DEPIN_WIFI{background:#ffcc00;color:#000} .s-AI{background:#ff00ff;color:#fff} .s-DEFI{background:#00ff88;color:#000} .s-MEME{background:#ff8800;color:#000} .s-RWA_GAMING{background:#8800ff;color:#fff} .s-OTHER_BEST{background:#555;color:#fff}"
 html+="</style></head><body>"
 bias_color="#00ff88" if bias=="LONG" else "#ff4444" if bias=="SHORT" else "#ffcc00"
 html+=f"<div class='h'><span class='live'></span> VENUS v805 620 LINES FULL UI GRAPH SECTORS RSI EMA BB $0.50 NET - SCAN #{scan} - 3 MAX $100 EACH - MARKET {regime} <span style='background:{bias_color};padding:2px 6px;border-radius:4px'>{bias} BIAS</span> BTC ${btc:.0f} ADX {adx} RSI {rsi_m:.0f} L:{long_open} S:{short_open} - <span id='clock'>LIVE</span></div>"
 html+=f"<div class='g'>"
 html+=f"<div class='c'><div style='font-size:10px;color:#888'>CAP $300 REAL SHORT 620 LINES</div><div style='font-size:22px;color:#ffcc00;font-weight:900'>${cap:.2f}</div><div style='font-size:10px'>WITH OPEN {cap+unreal:.2f} UNREAL {unreal:+.2f} | L:{long_open} S:{short_open} | {regime} FULL UI</div></div>"
 html+=f"<div class='c'><div style='font-size:10px;color:#888'>TODAY NET L:{long_open} S:{short_open} x $0.50</div><div style='font-size:22px;color:{'#f44' if daily<0 else '#0f8'};font-weight:900'>${daily:+.2f} NET</div><div style='font-size:10px'>GROSS ${daily_gross:+.2f} - FEES ${fees_paid:.2f} | W:{wins} L:{loss} {winrate}% | FULL UI GRAPH</div></div>"
 html+=f"<div class='c'><div style='font-size:10px;color:#888'>MARKET FULL UI 620 LINES</div><div style='font-size:9px;color:#0f8;font-weight:900'>{regime} {bias} BTC ${btc:.0f} ADX {adx} H1 {h1_m:+.1f}% RSI {rsi_m:.0f} LIVE {scan}</div><div style='font-size:8px;color:#888'>{reason[:85]}</div><div style='font-size:10px'>Next <span id='countdown'>10s</span> TICK <span id='tickcount'>1s</span> - 620 LINES</div></div>"
 html+="</div>"
 html+="<div id='sharkbox'><div class='b bd'>Scanning 620 LINES FULL UI...</div></div>"
 html+="<div id='openbox'></div><div id='closedbox'></div>"
 open_json=json.dumps([{"symbol":tr["symbol"],"side":tr.get("side","LONG"),"entry":tr["entry"],"ts":tr.get("ts", int(time.time())),"peak_gross":tr.get("peak_gross",0),"peak":tr.get("peak",0)} for tr in open_tr])
 # Use concatenation for JS to avoid f-string brace issues
 html+="<script>"
 html+=f"const ADMIN_KEY='{ADMIN_KEY}'; let openTrades={open_json}; let priceHistory={{}}; openTrades.forEach(t=>{{priceHistory[t.symbol]=[]}});"
 html+="""async function fetchPrices(){
  try{
   const res = await fetch('https://data-api.binance.vision/api/v3/ticker/price');
   const all = await res.json();
   const map={}; all.forEach(t=>{map[t.symbol]=parseFloat(t.price)});
   let shouldCron = false;
   openTrades.forEach(tr=>{
    const sym = tr.symbol+'USDT'; const now = map[sym]; if(!now) return;
    const entry = tr.entry; 
    let pct_gross = 0;
    if(tr.side=='LONG'){ pct_gross = (now-entry)/entry*100; } else { pct_gross = (entry-now)/entry*100; }
    const pct_net = pct_gross - 0.20; const net_usd = 100*pct_net/100;
    if(!priceHistory[tr.symbol]) priceHistory[tr.symbol]=[]; priceHistory[tr.symbol].push(pct_gross); if(priceHistory[tr.symbol].length>60) priceHistory[tr.symbol].shift();
    if(pct_gross > tr.peak) tr.peak = pct_gross;
    const el = document.querySelector('[data-symbol="'+tr.symbol+'"]');
    if(el){
     const grossEl = el.querySelector('.gross-val'); const netEl = el.querySelector('.net-val'); const priceEl = el.querySelector('.price-now'); const peakEl = el.querySelector('.peak-val'); const tickEl = el.querySelector('.tick-graph');
     if(grossEl){ grossEl.textContent = pct_gross.toFixed(3)+'% GROSS ('+tr.side+')'; grossEl.style.color = pct_gross>=0?'#0f8':'#f44'; }
     if(netEl){ netEl.textContent = pct_net.toFixed(3)+'% NET $'+net_usd.toFixed(3)+' NET '+tr.side; netEl.style.color = pct_net>=0?'#0f8':'#f44'; }
     if(priceEl) priceEl.textContent = '$'+now.toFixed(6);
     if(peakEl) peakEl.textContent = tr.peak.toFixed(2)+'% PEAK';
     if(tickEl && priceHistory[tr.symbol].length>2){
      const canvas = tickEl; const ctx = canvas.getContext('2d'); const w = canvas.width; const h = canvas.height; ctx.clearRect(0,0,w,h);
      const arr = priceHistory[tr.symbol]; const min = Math.min(...arr); const max = Math.max(...arr); const range = (max-min) || 0.01;
      ctx.strokeStyle = tr.side=='LONG'?'#0f8':'#ff4444'; ctx.lineWidth=2; ctx.beginPath();
      arr.forEach((v,i)=>{ const x = i/(arr.length-1)*w; const y = h - ((v-min)/range)*h; if(i==0) ctx.moveTo(x,y); else ctx.lineTo(x,y); });
      ctx.stroke();
      const tpY = h - ((0.35-min)/range)*h; ctx.strokeStyle='#ffcc00'; ctx.setLineDash([3,3]); ctx.beginPath(); ctx.moveTo(0,tpY); ctx.lineTo(w,tpY); ctx.stroke(); ctx.setLineDash([]);
     }
     if(pct_gross >= 0.33 || pct_gross <= -0.48 || (tr.peak >= 0.30 && pct_gross < tr.peak - 0.13)){ shouldCron = true; }
    }
   });
   if(shouldCron){ fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(()=>{ fetch('/?key='+ADMIN_KEY).then(r=>r.text()).then(html=>{ const parser=new DOMParser(); const doc=parser.parseFromString(html,'text/html'); const openEl=doc.getElementById('openbox-inner'); const closedEl=doc.getElementById('closedbox-inner'); const sharkEl=doc.getElementById('sharkbox-inner'); if(openEl) document.getElementById('openbox').innerHTML = openEl.innerHTML; if(closedEl) document.getElementById('closedbox').innerHTML = closedEl.innerHTML; if(sharkEl) document.getElementById('sharkbox').innerHTML = sharkEl.innerHTML; const newOpen = []; doc.querySelectorAll('[data-symbol]').forEach(div=>{ const sym = div.getAttribute('data-symbol'); const side = div.getAttribute('data-side')||'LONG'; const entry = parseFloat(div.getAttribute('data-entry')); const ts = parseInt(div.getAttribute('data-ts')); const peak = parseFloat(div.getAttribute('data-peak')||0); newOpen.push({symbol:sym, side:side, entry:entry, ts:ts, peak:peak}); }); openTrades = newOpen; Object.keys(priceHistory).forEach(k=>{ if(!newOpen.find(t=>t.symbol==k)) delete priceHistory[k]; }); newOpen.forEach(t=>{ if(!priceHistory[t.symbol]) priceHistory[t.symbol]=[]; }); }); }); }
  }catch(e){}
}
function tickAge(){ const now = Math.floor(Date.now()/1000); document.querySelectorAll('[data-ts]').forEach(el=>{ const ts = parseInt(el.getAttribute('data-ts')); const age = now - ts; const ageEl = el.querySelector('.age-val'); if(ageEl) ageEl.textContent = age+'s'; }); }
setInterval(fetchPrices, 1000); setInterval(tickAge, 1000); fetchPrices(); tickAge();
let count=10; setInterval(()=>{
 count--; const el=document.getElementById('countdown'); if(el) el.textContent = count+'s'; const clk=document.getElementById('clock'); if(clk) clk.textContent = new Date().toLocaleTimeString(); if(count<=0){ count=10; fetch('/api/cron?key='+ADMIN_KEY+'&cron=1').then(r=>r.json()).then(data=>{ fetch('/?key='+ADMIN_KEY).then(r=>r.text()).then(html=>{ const parser=new DOMParser(); const doc=parser.parseFromString(html,'text/html'); const openEl=doc.getElementById('openbox-inner'); const closedEl=doc.getElementById('closedbox-inner'); const sharkEl=doc.getElementById('sharkbox-inner'); if(openEl) document.getElementById('openbox').innerHTML = openEl.innerHTML; if(closedEl) document.getElementById('closedbox').innerHTML = closedEl.innerHTML; if(sharkEl) document.getElementById('sharkbox').innerHTML = sharkEl.innerHTML; const newOpen = []; doc.querySelectorAll('[data-symbol]').forEach(div=>{ const sym = div.getAttribute('data-symbol'); const side = div.getAttribute('data-side')||'LONG'; const entry = parseFloat(div.getAttribute('data-entry')); const ts = parseInt(div.getAttribute('data-ts')); const peak = parseFloat(div.getAttribute('data-peak')||0); newOpen.push({symbol:sym, side:side, entry:entry, ts:ts, peak:peak}); }); openTrades = newOpen; newOpen.forEach(t=>{ if(!priceHistory[t.symbol]) priceHistory[t.symbol]=[]; }); }); }); } },1000);
"""
 html+="</script>"
 html+="<div style='display:none'><div id='sharkbox-inner'>"
 html+=f"<div class='b bg'>620 LINES FULL UI - MARKET {regime} BIAS {bias} - BTC ${btc:.0f} ADX {adx} RSI {rsi_m:.0f} H1 {h1_m:+.1f}% - Pumped +5-18% = ONLY SHORT, Dip -3 to +3.5% = LONG - FORCED L1 S2 - {reason[:95]}</div>"
 if sharks:
  for idx,s in enumerate(sharks[:12]):
   side_col="#ff4444" if s['side']=="SHORT" else "#0f8" if s['side']=="LONG" else "#888"
   html+=f"<div class='it' style='border-color:{side_col}'><b style='color:{side_col}'>#{idx+1} {s['symbol']} <span class='sec s-{s['sector']}'>{s['sector']}</span> <span class='side side-{s['side']}'>{s['side']}</span> H1 {s['h1']:+.1f}% VOL ${s['vol']} - SCORE {s['score']:.0f}</b><br><span style='color:{side_col}'>{'Pumped TOP = SHORT' if s['side']=='SHORT' else 'Dip BOUNCE = LONG' if s['side']=='LONG' else 'HOLD'} - REAL SHORT BTC ${btc:.0f}</span></div>"
 else:
  html+=f"<div class='b by'>620 LINES FULL UI {regime} {bias} - BTC ${btc:.0f} H1 {h1_m:+.1f}% ADX {adx} RSI {rsi_m:.0f} - WILL FILL L1 S2 FORCED PUMPED=SHORT DIP=LONG 620 LINES</div>"
 html+="</div>"
 html+="<div id='openbox-inner'>"
 html+=f"<div class='b bb'>OPEN {len(open_tr)}/{MAXP} MAX 620 LINES FULL UI $100 EACH - MARKET {regime} {bias} BTC ${btc:.0f} ADX {adx} RSI {rsi_m:.0f} L:{long_open} S:{short_open} - SECTORS {','.join(list(used_sectors)) if 'used_sectors' in locals() and used_sectors else 'FULL 620 LINES'} - <span class='live'></span> LIVE TICK GRAPH 1s 620 LINES</div>"
 if len(open_tr)==0:
  html+=f"<div class='it' style='text-align:center;color:#0f8;border-color:#0f8'>620 LINES FULL UI RESTORED - SCAN #{scan} - MARKET REGIME FULL UI:<br>{reason}<br>BIAS: {bias} - REGIME: {regime} - ADX {adx} RSI {rsi_m:.0f} BTC ${btc:.0f} H1 {h1_m:+.1f}% L:{long_open} S:{short_open}<br>3x$100 DIVERSIFIED FULL UI GRAPH - FORCED L:1 S:2 or L:2 S:1 ALWAYS - 620 LINES<br>LONG_CONF: H1 -3.5% to +3.8% DIP BOUNCE RSI<55 BB Low - LONG_SMART<br>SHORT_CONF: H1 +4.5% to +19% PUMP TOP SHORT RSI>58 BB High - SHORT_SMART<br>GRAPH: Live sparkline 1s tick with TP yellow line - SECTORS COLORS - RSI EMA BB - FULL 620 LINES<br>LIVE TICK GRAPH 1s - SECTOR BADGES - STRATEGY BADGES - PEAK LIVE - FULL UI</div>"
 for tr in open_tr:
  col="#0f8" if tr.get("pct",0)>=0 else "#f44"
  pct_gross=tr.get("pct_gross",0); pct_net=tr.get("pct",0); net_usd=tr.get("net",0); entry=tr.get("entry",0); ts=tr.get("ts", int(time.time())); peak=tr.get("peak_gross",0); sector=tr.get("sector", get_sector(tr["symbol"])); strat=tr.get("strat",""); side=tr.get("side","LONG"); side_col="#0f8" if side=="LONG" else "#ff4444"
  html+=f"<div class='it' style='border-color:{col}' data-symbol='{tr['symbol']}' data-side='{side}' data-entry='{entry}' data-ts='{ts}' data-peak='{peak}'><b style='color:{col}'>{tr['symbol']} <span class='side side-{side}'>{side}</span> <span class='sec s-{sector}'>{sector}</span> <span class='strat'>{strat}</span> AGE <span class='age-val'>{tr.get('age',0)}s</span> PEAK <span class='peak-val'>{peak:.2f}% PEAK</span></b><br>ENTRY ${entry:.6f} ({side}) -> NOW <span class='price-now' style='color:#ffcc00'>${tr.get('price',0):.6f}</span> $100 POS H1 {tr.get('h1',0):+.1f}% RSI {tr.get('rsi',50):.0f}<br><span style='font-size:13px;font-weight:900' class='gross-val'>{pct_gross:.3f}% GROSS ({side})</span> <span style='font-size:13px;font-weight:900' class='net-val'>{pct_net:.3f}% NET ${net_usd:+.3f} NET {side}</span> <span class='live'></span> TICK GRAPH<br><canvas class='spark tick-graph' width='300' height='36' style='border-color:{side_col}'></canvas><br><span style='font-size:10px;color:#888'>{tr.get('reason','')} | {sector} {strat} | TP {tr.get('tp',0.35)}% SL {tr.get('sl',0.55)}% | $0.50 NET GOAL FULL UI GRAPH {regime} {bias} BTC ${btc:.0f} RSI {rsi_m:.0f}</span></div>"
 html+="</div>"
 html+="<div id='closedbox-inner'>"
 html+=f"<div style='background:#111;padding:10px;margin:8px 0;border-radius:8px'><div style='color:#ffcc00;font-weight:900'>CLOSED {len(closed)} - W:{wins} L:{loss} T:{tot} {winrate}% - CAP ${cap:.2f} DAILY NET ${daily:+.2f} (GROSS ${daily_gross:+.2f} - FEES ${fees_paid:.2f}) - 620 LINES FULL UI L:{long_open} S:{short_open} $0.50x3 TARGET - SCAN #{scan}</div>"
 for cl in closed[:20]:
  net=cl.get("net",0); gross=cl.get("gross",0); fee=cl.get("fee",FEE_USD); pct_gross=cl.get("pct_gross",0); pct_net=cl.get("pct_net",0); c="#0f8" if net>=0.08 else "#f44" if net<0 else "#ffcc00"; sec=cl.get("sector", get_sector(cl.get("symbol",""))); strat=cl.get("strat",""); side=cl.get("side","LONG"); rsi_c=cl.get("rsi",50)
  html+=f"<div style='padding:4px 0;border-bottom:1px solid #222;color:{c}'><b>{cl.get('symbol','')} <span class='side side-{side}'>{side}</span> <span class='sec s-{sec}'>{sec}</span> <span class='strat'>{strat}</span> RSI {rsi_c:.0f}</b> ${net:+.2f} NET (${gross:+.2f} GROSS - ${fee:.2f} FEE) {cl.get('reason','')} {pct_gross:+.2f}% GROSS {pct_net:+.2f}% NET AGE {cl.get('age',0)}s</div>"
 html+="</div></div></div></body></html>"
 return html

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
 key=request.args.get("key","")
 p="/"+path
 if p.startswith("/api/cron"):
  if key!=ADMIN_KEY and "cron" not in request.args: return Response("Forbidden", status=403)
  try:
   res=do_cron()
   return Response(json.dumps(res), mimetype="application/json")
  except Exception as e:
   return Response(json.dumps({"ok":False,"error":str(e)[:400]}), mimetype="application/json", status=200)
 if p.startswith("/api/reset"):
  if key!=ADMIN_KEY: return Response("Forbidden", status=403)
  try:
   kv_del(STATE_KEY); time.sleep(0.6)
   new={"cap":300.0,"daily":0.0,"daily_gross":0.0,"fees_paid":0.0,"wins":0,"loss":0,"total":0,"scan":0,"open":[],"closed":[],"learn":{"blacklist":{},"pause_until":0,"last_date":time.strftime("%Y-%m-%d"),"last_coins":{}}}
   ok=kv_set(STATE_KEY, new)
   return Response(json.dumps({"ok":ok,"cap":300}), mimetype="application/json")
  except Exception as e:
   return Response(json.dumps({"ok":False,"error":str(e)[:300]}), mimetype="application/json")
 try:
  st=load_state(); h=render(st); return Response(h, mimetype="text/html")
 except Exception as e:
  import traceback; tb=traceback.format_exc()[:1500]
  return Response(f"<html><body><h1>Error: {str(e)[:500]}</h1><pre>{tb}</pre><p><a href='/api/reset?key={ADMIN_KEY}'>RESET</a></p></body></html>", mimetype="text/html", status=200)
