import os
import stripe
import uuid
import requests
from flask import Flask, jsonify, request, render_template
from supabase import create_client, Client

app = Flask(__name__, template_folder='templates')

# --- Config & Clients ---
# Using .get() ensures the app doesn't crash immediately if a key is missing
STRIPE_KEY      = os.environ.get("STRIPE_SECRET_KEY")
ENDPOINT_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
SUPA_URL        = os.environ.get("SUPABASE_URL")
SUPA_KEY        = os.environ.get("SUPABASE_KEY")
GOOGLE_MAPS_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")

stripe.api_key = STRIPE_KEY
supabase: Client = create_client(SUPA_URL, SUPA_KEY)

# Monetization Config
SEARCH_COST = 0.10

# =============================================================================
# --- Discovery Engine Data ---
# =============================================================================

VIBE_TWINS = {
    "paris": {
        "twin": "Marseille", 
        "vibe_type": "Artistic & Urban",
        "pitch": "Trade the Eiffel Tower for the Mediterranean sun and a grittier, authentic French soul."
    },
    "tulum": {
        "twin": "Sayulita", 
        "vibe_type": "Boho-Chic",
        "pitch": "Less 'scene', more surf. The same jungle-meets-ocean energy without the crowds."
    },
    "san diego": {
        "twin": "Ensenada", 
        "vibe_type": "Coastal Adventure",
        "pitch": "Love the SD coastline? Head south for world-class food and rugged Pacific vibes."
    }
}

# =============================================================================
# --- Helper Functions ---
# =============================================================================

def get_vibe_results(city, mood, budget="any"):
    """Fetches real spots from Google Places API based on user mood."""
    query = f"best {mood} spots in {city}"
    if budget != "any":
        query += f" with {budget} budget"
    
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": GOOGLE_MAPS_KEY}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        results = response.json().get('results', [])
        
        return [{
            "name": p.get("name"),
            "address": p.get("formatted_address"),
            "rating": p.get("rating"),
            "price_level": p.get("price_level", "N/A"),
            "place_id": p.get("place_id")
        } for p in results[:5]]
    except Exception as e:
        print(f"Maps Error: {e}")
        return []

# =============================================================================
# --- Core Routes ---
# =============================================================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/check_vibe', methods=['POST'])
def check_vibe():
    """Checks if the searched city has a 'Hidden Gem' twin."""
    data = request.get_json() or {}
    city_input = data.get('city', '').lower().strip()
    
    if city_input in VIBE_TWINS:
        return jsonify({
            "status": "pivot",
            "suggestion": VIBE_TWINS[city_input]
        })
    return jsonify({"status": "proceed"})

@app.route('/get_vibes', methods=['POST'])
def get_vibes():
    """Handles the actual search and credit deduction."""
    data = request.get_json() or {}
    api_key = data.get('api_key')
    city = data.get('city')
    mood = data.get('mood')
    budget = data.get('budget', 'any')

    if not all([api_key, city, mood]):
        return jsonify({"error": "Missing parameters"}), 400

    try:
        # 1. Verify Balance
        res = supabase.table('user_credits').select('balance').eq('api_key', api_key).execute()
        if not res.data or float(res.data[0]['balance']) < SEARCH_COST:
            return jsonify({"error": "Insufficient funds"}), 402

        # 2. Fetch Data
        vibe_data = get_vibe_results(city, mood, budget)

        # 3. Deduct Credit
        new_balance = round(float(res.data[0]['balance']) - SEARCH_COST, 2)
        supabase.table('user_credits').update({'balance': new_balance}).eq('api_key', api_key).execute()

        return jsonify({
            "status": "success", 
            "results": vibe_data, 
            "remaining_balance": new_balance
        })

    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

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
        success_url='https://vibecity.me/?payment=success',
        cancel_url='https://vibecity.me/',
    )
    return jsonify(url=checkout_session.url), 200

@app.route('/stripe_webhook', methods=['POST'])
def stripe_webhook():
    payload, sig_header = request.data, request.headers.get('Stripe-Signature')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, ENDPOINT_SECRET)
    except:
        return jsonify(success=False), 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        api_key, amount_paid = session.client_reference_id, round(float(session.amount_total) / 100, 2)
        
        res = supabase.table('user_credits').select('balance').eq('api_key', api_key).execute()
        new_total = amount_paid + (float(res.data[0]['balance']) if res.data else 0)
        
        supabase.table('user_credits').upsert({'api_key': api_key, 'balance': round(new_total, 2)}).execute()

    return jsonify(success=True), 200

if __name__ == '__main__':
    app.run(debug=True)
