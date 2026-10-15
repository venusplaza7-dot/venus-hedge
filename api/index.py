from flask import Flask, jsonify, request
import time

# Initialize Flask instance required for Vercel serverless deployment
app = Flask(__name__)

# --- CONFIGURATION: $1,000 SCALED LOGIC ---
TOTAL_CAPITAL = 1000.00       # Scaled total bankroll
MAXP = 3                      # Maximum concurrent active slots ($333.33 per slot)
SLOT_CAPITAL = TOTAL_CAPITAL / MAXP  

GROSS_TARGET_NET = 0.50       # Target net profit per trade ($0.50)
TAKER_FEE_PCT = 0.0010        # ~0.10% round-trip taker fee on MEXC
SL_PCT = 0.0385               # 3.85% wide risk buffer
TP_PCT = 0.0067               # 0.67% optimized fast-execution target

# Mock state tracking for the testing dashboard
portfolio_state = {
    "total_capital": TOTAL_CAPITAL,
    "wins": 0,
    "losses": 0,
    "daily_pnl": 0.0,
    "active_slots": [
        {"coin": "NEAR", "allocated": SLOT_CAPITAL, "entry": 5.42, "pnl": 0.0},
        {"coin": "INJ", "allocated": SLOT_CAPITAL, "entry": 8.50, "pnl": 0.0},
        {"coin": "ZRO", "allocated": SLOT_CAPITAL, "entry": 2.10, "pnl": 0.0}
    ],
    "closed_trades": []
}

@app.route('/')
def dashboard_home():
    return jsonify({
        "status": "online",
        "strategy": "Fast Target Sniper (Scaled)",
        "total_capital": portfolio_state["total_capital"],
        "active_slots_count": len(portfolio_state["active_slots"]),
        "slot_allocation": SLOT_CAPITAL,
        "metrics": {
            "wins": portfolio_state["wins"],
            "losses": portfolio_state["losses"],
            "net_pnl": portfolio_state["daily_pnl"]
        }
    })

@app.route('/api/state', methods=['GET'])
def get_state():
    return jsonify(portfolio_state)

@app.route('/api/simulate-win', methods=['POST'])
def simulate_win():
    """Simulates hitting a target to test the $333 slot scaling metrics."""
    if portfolio_state["active_slots"]:
        completed_slot = portfolio_state["active_slots"].pop(0)
        net_gain = 0.50
        portfolio_state["total_capital"] += net_gain
        portfolio_state["daily_pnl"] += net_gain
        portfolio_state["wins"] += 1
        
        portfolio_state["closed_trades"].insert(0, {
            "coin": completed_slot["coin"],
            "net": net_gain,
            "status": "TP HIT +0.67%"
        })
        
        # Replenish slot with a new hyper-volatile symbol rotation
        new_coins = ["WAL", "CRCLB", "PYTH", "ZK", "STRK"]
        next_coin = new_coins[portfolio_state["wins"] % len(new_coins)]
        portfolio_state["active_slots"].append({
            "coin": next_coin,
            "allocated": SLOT_CAPITAL,
            "entry": 1.00,
            "pnl": 0.0
        })
        
    return jsonify(portfolio_state)

if __name__ == '__main__':
    app.run(debug=True)
