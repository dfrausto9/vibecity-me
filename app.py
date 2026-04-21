import os, stripe, uuid, requests
from flask import Flask, jsonify, request, render_template
from supabase import create_client, Client

app = Flask(__name__, template_folder='templates')

# --- Config & Clients ---
STRIPE_KEY      = os.environ.get("STRIPE_SECRET_KEY")
ENDPOINT_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
SUPA_URL        = os.environ.get("SUPABASE_URL")
SUPA_KEY        = os.environ.get("SUPABASE_KEY")
GOOGLE_MAPS_KEY = os.environ.get("GOOGLE_MAPS_API_KEY") # You'll add this to Render

stripe.api_key = STRIPE_KEY
supabase: Client = create_client(SUPA_URL, SUPA_KEY)

# Each "Vibe Search" costs 1 credit (e.g., $0.10)
SEARCH_COST = 0.10

# =============================================================================
# --- Vibe Engine Logic ---
# =============================================================================

def get_vibe_results(city, mood, budget):
    """
    Translates the user's mood into a Google Maps query.
    """
    # This is where the 'translation' happens
    query = f"best {mood} spots in {city} with {budget} budget"
    
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": query,
        "key": GOOGLE_MAPS_KEY
    }
    
    try:
        response = requests.get(url, params=params)
        results = response.json().get('results', [])
        
        # We'll just grab the top 5 to keep it curated
        top_5 = []
        for place in results[:5]:
            top_5.append({
                "name": place.get("name"),
                "address": place.get("formatted_address"),
                "rating": place.get("rating"),
                "user_ratings_total": place.get("user_ratings_total"),
                "price_level": place.get("price_level", "N/A"),
                "place_id": place.get("place_id")
            })
        return top_5
    except Exception as e:
        raise Exception(f"Google Maps Error: {str(e)}")

# The "Discovery Engine" Data
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
        "pitch": "Love the SD coastline? Head south for world-class food and rugged Pacific vibes at a fraction of the cost."
    }
}

@app.route('/check_vibe', methods=['POST'])
def check_vibe():
    data = request.get_json()
    city_input = data.get('city', '').lower()
    
    if city_input in VIBE_TWINS:
        return jsonify({
            "status": "pivot",
            "suggestion": VIBE_TWINS[city_input]
        })
    return jsonify({"status": "proceed"})

# =============================================================================
# --- Routes ---
# =============================================================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/generate_key', methods=['POST'])
def generate_key():
    new_key = str(uuid.uuid4())
    try:
        supabase.table('user_credits').insert({'api_key': new_key, 'balance': 0.00}).execute()
        return jsonify(api_key=new_key), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/create_checkout', methods=['POST'])
def create_checkout():
    data = request.get_json() or {}
    amount = data.get('amount')
    api_key = data.get('api_key')

    if not api_key or not amount:
        return jsonify(error="Missing api_key or amount"), 400

    try:
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
            success_url='https://vibecity.me/?payment=success', # Updated to your new domain!
            cancel_url='https://vibecity.me/',
        )
        return jsonify(url=checkout_session.url), 200
    except Exception as e:
        return jsonify(error=str(e)), 500

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
        try:
            amount_paid = round(float(session.amount_total) / 100, 2)
            api_key = session.client_reference_id
            
            res = supabase.table('user_credits').select('balance').eq('api_key', api_key).execute()
            if res.data:
                new_total = round(float(res.data[0]['balance']) + amount_paid, 2)
                supabase.table('user_credits').update({'balance': new_total}).eq('api_key', api_key).execute()
            else:
                supabase.table('user_credits').insert({'api_key': api_key, 'balance': amount_paid}).execute()
        except Exception as e:
            return jsonify(success=False), 500

    return jsonify(success=True), 200

@app.route('/check_balance')
def check_balance():
    key = request.args.get('key')
    res = supabase.table('user_credits').select('balance').eq('api_key', key).execute()
    if res.data:
        return jsonify(balance=res.data[0]['balance']), 200
    return jsonify(error="Invalid Key"), 404

@app.route('/get_vibes', methods=['POST'])
def get_vibes():
    data = request.get_json() or {}
    api_key = data.get('api_key')
    city = data.get('city')
    mood = data.get('mood')
    budget = data.get('budget', 'any')

    if not all([api_key, city, mood]):
        return jsonify({"error": "Missing parameters"}), 400

    try:
        # Check Balance
        res = supabase.table('user_credits').select('balance').eq('api_key', api_key).execute()
        if not res.data or float(res.data[0]['balance']) < SEARCH_COST:
            return jsonify({"error": "Insufficient funds"}), 402

        # Get the Vibe!
        vibe_data = get_vibe_results(city, mood, budget)

        # Deduct Credit
        new_balance = round(float(res.data[0]['balance']) - SEARCH_COST, 2)
        supabase.table('user_credits').update({'balance': new_balance}).eq('api_key', api_key).execute()

        return jsonify({
            "status": "success", 
            "city": city,
            "vibe": mood,
            "results": vibe_data, 
            "remaining_balance": new_balance
        })

    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
