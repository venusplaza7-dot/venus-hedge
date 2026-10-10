def get_sharks():
    btc=0; bins=[]; raw_count=0
    try:
        r=requests.get(f"{BASE}/api/v3/ticker/24hr",timeout=8).json()
        if isinstance(r,list):
            raw_count=len(r)
            m=[]
            for it in r:
                try:
                    s=it.get('symbol','')
                    if not s.endswith('USDT'): continue
                    if any(x in s for x in ['UP','DOWN','BEAR','BULL']): continue
                    pr=float(it.get('lastPrice',0))
                    ch=float(it.get('priceChangePercent',0))
                    vol=float(it.get('quoteVolume',0))
                    tr=int(it.get('count',0))
                    if s=='BTCUSDT': btc=ch
                    # LOOSENED FOR FLAT MARKET - back to 1.5M but not top
                    if pr>0 and vol>1500000 and abs(ch)>0.8 and tr>800:
                        if abs(ch) > 45: continue # don't buy insane pump
                        score=abs(ch)*(vol/1000000)
                        if abs(ch)>5: score*=2
                        m.append({
                            "symbol":s.replace('USDT',''),"price":pr,"c1":ch/6,
                            "vol":vol,"cg_id":s,"chain":"binance",
                            "score":score,"liquidity":vol,
                            "shark_score":score,
                            "reason":f"VOL {vol/1000000:.1f}M CH {ch:.1f}% TR {tr}"
                        })
                except: continue
            m.sort(key=lambda x:x['score'],reverse=True)
            bins=m[:8]
    except Exception as e:
        print(f"binance error {e}")

    sols=[]
    try:
        r=requests.get("https://api.dexscreener.com/token-boosts/top/v1",timeout=5).json()
        for it in r[:30]:
            if it.get('chainId')!='solana' or not it.get('tokenAddress'): continue
            try:
                pr=requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{it['tokenAddress']}",timeout=4).json()
                if not pr.get('pairs'): continue
                pairs=sorted(pr['pairs'], key=lambda x: float(x.get('liquidity',{}).get('usd',0) or 0), reverse=True)
                if not pairs: continue
                p=pairs[0]
                price=float(p.get('priceUsd',0) or 0)
                ch5=float(p.get('priceChange',{}).get('m5',0) or 0)
                vol=float(p.get('volume',{}).get('m5',0) or 0)
                buys=int(p.get('txns',{}).get('m5',{}).get('buys',0) or 0)
                sells=int(p.get('txns',{}).get('m5',{}).get('sells',0) or 0)
                liq=float(p.get('liquidity',{}).get('usd',0) or 0)
                sym=p.get('baseToken',{}).get('symbol','SOL')[:12]
                # LOOSENED
                if price>0 and vol>4000 and abs(ch5)>0.8 and liq>15000 and buys>=2:
                    br=buys/(sells+1)
                    sc=vol/1000 + abs(ch5)*2
                    if br>1.2: sc+=br*5
                    if sc>8:
                        sols.append({
                            "symbol":sym,"price":price,"c1":ch5,"vol":vol,
                            "cg_id":p.get('pairAddress'),"token":it['tokenAddress'],
                            "chain":"solana","score":sc,"liquidity":liq,
                            "shark_score":sc,
                            "reason":f"B {buys}/{sells} VOL {vol/1000:.0f}k M5 {ch5:.1f}% LIQ ${liq/1000:.0f}k"
                        })
            except: continue
    except: pass

    sols.sort(key=lambda x:x['shark_score'],reverse=True)
    bins.sort(key=lambda x:x['shark_score'],reverse=True)
    
    # ALWAYS return something - if filter too strict, return top movers anyway
    mixed=bins[:3]+sols[:2]
    if len(mixed)==0 and len(bins)>0:
        mixed=bins[:3] # fallback to binance only
    if len(mixed)==0:
        # emergency fallback - force 3 from raw binance even if low vol
        mixed=bins[:3] if bins else []

    regime="BEAR" if btc<-1.0 else "BULL_JUMP" if btc>0.6 else "BULL" if btc>0.2 else "NEUTRAL"
    return mixed[:5], regime, btc, raw_count
