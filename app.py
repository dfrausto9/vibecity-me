import os
import stripe
import uuid
import requests
from flask import Flask, jsonify, request, render_template
from supabase import create_client, Client

# --- IMPORTANT: Import your new scraper ---
from scraper import extract_vibes

app = Flask(__name__, template_folder='templates')

# --- Config & Clients ---
STRIPE_KEY      = os.environ.get("STRIPE_SECRET_KEY")
ENDPOINT_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
SUPA_URL        = os.environ.get("SUPABASE_URL")
SUPA_KEY        = os.environ.get("SUPABASE_KEY")
GOOGLE_MAPS_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")

stripe.api_key = STRIPE_KEY
supabase: Client = create_client(SUPA_URL, SUPA_KEY)

SEARCH_COST = 0.10

# ... (VIBE_TWINS and get_vibe_results logic remains the same) ...

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/check_balance', methods=['GET'])
def check_balance():
    api_key = request.args.get('key')
    if not api_key: return jsonify(balance=0.00)
    res = supabase.table('user_credits').select('balance').eq('api_key', api_key).execute()
    balance = res.data[0]['balance'] if res.data else 0.00
    return jsonify(balance=balance)

@app.route('/scrape', methods=['POST'])
def scrape():
    """Finalized Scrape Route with Credit Deduction"""
    data = request.json
    user_input = data.get('url') 
    hot_springs_mode = data.get('hot_springs', False) 
    api_key = data.get('api_key')

    if not api_key or not user_input:
        return jsonify({"error": "Missing key or search term"}), 400

    try:
        # 1. VERIFY BALANCE
        res = supabase.table('user_credits').select('balance').eq('api_key', api_key).execute()
        if not res.data or float(res.data[0]['balance']) < SEARCH_COST:
            return jsonify({"error": "Insufficient funds. Please top up!"}), 402

        # 2. RUN THE SCRAPER (The 'Secret Weapon')
        result = extract_vibes(user_input, hot_springs_only=hot_springs_mode)

        if "error" in result:
            return jsonify({"error": result["error"]})

        # 3. DEDUCT CREDIT ONLY ON SUCCESS
        current_balance = float(res.data[0]['balance'])
        new_balance = round(current_balance - SEARCH_COST, 2)
        
        supabase.table('user_credits').update({'balance': new_balance}).eq('api_key', api_key).execute()

        return jsonify({
            "result": result,
            "new_balance": new_balance
        })

    except Exception as e:
        return jsonify({"error": f"Internal Error: {str(e)}"}), 500

# =============================================================================
# --- Billing & User Management ---
# =============================================================================

@app.route('/generate_key', methods=['POST'])
def generate_key():
    new_key = str(uuid.uuid4())
    supabase.table('user_credits').insert({'api_key': new_key, 'balance': 0.00}).execute()
    return jsonify(api_key=new_key), 200

@app.route('/create_checkout', methods=['POST'])
def create_checkout():
    data = request.get_json() or {}
    api_key, amount = data.get('api_key'), data.get('amount')
    if not api_key or not amount:
        return jsonify(error="Missing details"), 400

    checkout_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'unit_amount': int(amount) * 100,
                'product_data': {'name': f'VibeCity Credits — ${amount}'},
            },
            'quantity': 1,
        }],
        mode='payment',
        client_reference_id=api_key,
        success_url='https://vibecity.me/?payment=success', # Replace with your Render URL
        cancel_url='https://vibecity.me/',
    )
    return jsonify(url=checkout_session.url), 200

@app.route('/stripe_webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, ENDPOINT_SECRET)
    except Exception as e:
        return jsonify(success=False), 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        api_key = session.client_reference_id
        amount_paid = round(float(session.amount_total) / 100, 2)
        
        # Get current balance
        res = supabase.table('user_credits').select('balance').eq('api_key', api_key).execute()
        old_balance = float(res.data[0]['balance']) if res.data else 0.00
        
        # Update with new balance
        new_total = round(old_balance + amount_paid, 2)
        supabase.table('user_credits').upsert({'api_key': api_key, 'balance': new_total}).execute()

    return jsonify(success=True), 200

if __name__ == '__main__':
    app.run(debug=True)
