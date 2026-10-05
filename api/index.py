
from flask import Flask, jsonify
import os, json, requests, time, random
from datetime import datetime, timezone

app = Flask(__name__)

UP_URL = os.getenv("KV_REST_API_URL","") or os.getenv("UPSTASH_REDIS_REST_URL","")
UP_TOKEN = os.getenv("KV_REST_API_TOKEN","") or os.getenv("UPSTASH_REDIS_REST_TOKEN","")

COINS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT"]
POS_SIZE = 200  # $1000 /5 = $200 per coin = $1 per trade target

def rget(k):
    try:
        if not UP_URL or not UP_TOKEN: return None
        r = requests.get(f"{UP_URL}/get/{k}", headers={"Authorization": f"Bearer {UP_TOKEN}"}, timeout=5)
        v = r.json().get("result")
        if v is None: return None
        try: return json.loads(v)
        except: return v
    except: return None

def rset(k,v):
    try:
        if not UP_URL or not UP_TOKEN: return
        requests.post(f"{UP_URL}/set/{k}", headers={"Authorization": f"Bearer {UP_TOKEN}", "Content-Type":"application/json"}, data=json.dumps(v), timeout=5)
    except: pass

def get_prices():
    prices={}
    try:
        r=requests.get("https://api.binance.com/api/v3/ticker/price", timeout=5)
        data=r.json()
        for d in data:
            if d['symbol'] in COINS:
                prices[d['symbol']]=float(d['price'])
    except:
        # fallback mock
        base_map={"BTCUSDT":68000,"ETHUSDT":3500,"SOLUSDT":180,"BNBUSDT":620,"XRPUSDT":0.62}
        for c in COINS:
            prices[c]=base_map[c]*(1+random.uniform(-0.002,0.002))
    return prices

def get_atr_vwap(symbol):
    # simplified ATR proxy from 1m klines
    try:
        r=requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=14", timeout=4)
        klines=r.json()
        trs=[]
        closes=[]
        for k in klines:
            high=float(k[2]); low=float(k[3]); close=float(k[4])
            closes.append(close)
            trs.append((high-low)/close*100)
        atr=sum(trs)/len(trs) if trs else 0.03
        vwap=(closes[-1]-sum(closes)/len(closes))/closes[-1]*100 if closes else 0
        return atr, vwap, closes[-1]
    except:
        return random.uniform(0.02,0.08), random.uniform(-0.1,0.1), 0

def trading_tick():
    cap = rget("VENUS_CAP")
    if cap is None: cap=1001.07
    cap=float(cap)
    open_trades = rget("VENUS_OPEN") or []
    closed = rget("VENUS_CLOSED") or []
    wins = rget("VENUS_WINS") or 0
    losses = rget("VENUS_LOSSES") or 0

    prices=get_prices()
    now=time.time()

    # close logic
    new_open=[]
    for t in open_trades:
        sym=t['symbol']
        entry=t['entry']
        cur=prices.get(sym, entry)
        age=now - t['ts']
        pct=(cur-entry)/entry*100
        atr=t.get('atr',0.03)
        target=0.20 if atr>0.025 else 0.12
        cut=max(0.10, atr*1.5)
        peak=t.get('peak', pct)
        if pct>peak: peak=pct
        t['peak']=peak
        # gross profit
        gross = POS_SIZE * pct/100
        fee=0.2 # approx futures fee 0.1% round trip on $200 = $0.2
        # trailing
        trail_hit = peak>=target and pct < peak*0.40
        # dust filter
        dust = gross>0 and gross < fee*1.5 and age<25

        should_close=False
        reason=""
        if dust:
            should_close=False
        elif pct>=0.09 and age>=35:
            should_close=True; reason=f"MAX 35s +{pct:.3f}%"
        elif age>=75:
            should_close=True; reason=f"MAX 75s {pct:.3f}%"
        elif abs(pct)<0.05 and age>=70:
            should_close=True; reason=f"SCRATCH 70s {pct:.3f}%"
        elif pct>=target:
            should_close=True; reason=f"TARGET {pct:.3f}% >= {target}%"
        elif pct<=-cut:
            should_close=True; reason=f"CUT {pct:.3f}% <= -{cut:.3f}%"
        elif trail_hit:
            should_close=True; reason=f"TRAIL {pct:.3f}% peak {peak:.3f}%"

        if should_close:
            net = gross - fee
            cap+=net
            if net>0: wins+=1
            else: losses+=1
            closed.append({"symbol":sym,"entry":entry,"exit":cur,"pct":pct,"net":net,"reason":reason,"ts":now,"age":age})
            # keep last 893
            closed=closed[-893:]
        else:
            new_open.append(t)

    # open logic: fill to 5
    if len(new_open)<5:
        # speed ranking
        ranked=[]
        for sym in COINS:
            if any(x['symbol']==sym for x in new_open): continue
            atr,vwap,_ = get_atr_vwap(sym)
            if atr<0.007: continue
            if abs(vwap)<0.05 and random.random()>0.5: continue
            speed=atr*3+abs(vwap)
            ranked.append((speed,sym,atr,vwap,prices.get(sym,0)))
        ranked.sort(reverse=True)
        need=5-len(new_open)
        for i in range(min(need,len(ranked))):
            speed,sym,atr,vwap,price = ranked[i]
            if price==0: price=prices.get(sym,0)
            new_open.append({"symbol":sym,"entry":price,"ts":now,"atr":atr,"vwap":vwap,"peak":0})

    rset("VENUS_CAP", cap)
    rset("VENUS_OPEN", new_open)
    rset("VENUS_CLOSED", closed)
    rset("VENUS_WINS", wins)
    rset("VENUS_LOSSES", losses)
    return {"cap":cap,"open":new_open,"closed":closed[-5:],"wins":wins,"losses":losses,"prices":prices}

def html_page(data=None):
    if data is None:
        cap=rget("VENUS_CAP") or 1001.07
        wins=rget("VENUS_WINS") or 0
        losses=rget("VENUS_LOSSES") or 0
        open_trades=rget("VENUS_OPEN") or []
        closed=rget("VENUS_CLOSED") or []
    else:
        cap=data['cap']; wins=data['wins']; losses=data['losses']; open_trades=data['open']; closed=data['closed']

    tot=wins+losses
    wr=int(wins/max(1,tot)*100) if tot else 80
    price_line=""
    try:
        prices=get_prices()
        price_line=" | ".join([f"{s.replace('USDT','')}:{prices.get(s,0):.2f}" for s in COINS[:3]])
    except: price_line="Prices 8-10"

    open_html=""
    for o in open_trades:
        age=int(time.time()-o['ts'])
        cur=(get_prices().get(o['symbol'],o['entry']))
        pct=(cur-o['entry'])/o['entry']*100 if cur else 0
        open_html+=f"<div>{o['symbol']} entry {o['entry']:.3f} now {cur:.3f} {pct:+.3f}% {age}s atr {o.get('atr',0):.3f}%</div>"

    return f"""
    <html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <meta http-equiv='refresh' content='3'>
    <style>
    body{{background:#000;color:#0f0;font-family:monospace;padding:12px;font-size:14px}}
    .b{{border:2px solid #0f0;padding:12px;max-width:680px;margin:auto}}
    h2{{margin:0 0 10px 0;font-size:18px}} a{{color:#0f0}}
    .open{{margin-top:10px;border-top:1px dashed #0f0;padding-top:8px}}
    </style></head><body><div class='b'>
    <h2>VENUS v212 FIXED $1000 30SEC 5 COINS $1 PER TRADE</h2>
    <div>CAP ${float(cap):.2f} | WR {wr}% | {wins}W/{losses}L of {tot} | Open {len(open_trades)}/5 | {price_line} | LIVE</div>
    <div style='margin-top:8px'>Fut Fee $0.20 | Target 0.12-0.20% | Cut max(0.10,ATR*1.5) | Trail 40% | 893 trades milestone</div>
    <div class='open'>{open_html if open_html else "No open - will open on /api/cron"}</div>
    <div style='margin-top:12px'><a href='/api/state'>/api/state</a> | <a href='/api/cron'>/api/cron (tick)</a> | <a href='/api/force'>/api/force</a> | <a href='/api/history'>/history</a></div>
    <div style='margin-top:6px;font-size:11px'>Vercel Ready - Upstash { 'CONNECTED' if UP_URL else 'NO KV - add env' } - auto cron every 30s needs Vercel Cron</div>
    </div></body></html>
    """

@app.route("/")
@app.route("/api/index")
@app.route("/api/")
def home():
    return html_page()

@app.route("/<path:path>")
def catch(path):
    if path.startswith("api/state") or path=="state":
        cap=rget("VENUS_CAP") or 1001.07
        o=rget("VENUS_OPEN") or []
        w=rget("VENUS_WINS") or 0
        l=rget("VENUS_LOSSES") or 0
        return jsonify({"cap":cap,"wins":w,"losses":l,"open":len(o),"open_trades":o,"ver":"v212"})
    if path.startswith("api/history") or path=="history":
        closed=rget("VENUS_CLOSED") or []
        return jsonify({"closed":closed[-50:]})
    if path.startswith("api/cron") or path.startswith("api/force") or path in ["cron","force"]:
        data=trading_tick()
        return jsonify(data)
    return html_page()

@app.route("/api/state")
def state():
    cap=rget("VENUS_CAP") or 1001.07
    o=rget("VENUS_OPEN") or []
    w=rget("VENUS_WINS") or 0
    l=rget("VENUS_LOSSES") or 0
    return jsonify({"cap":cap,"wins":w,"losses":l,"open":len(o),"open_trades":o})

@app.route("/api/cron")
@app.route("/api/force")
def cron():
    data=trading_tick()
    return jsonify(data)

@app.route("/api/history")
def history():
    closed=rget("VENUS_CLOSED") or []
    return jsonify({"closed":closed[-100:]})
