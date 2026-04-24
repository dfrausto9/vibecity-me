import json
import requests
from bs4 import BeautifulSoup

def google_search(query):
    """Searches Google and returns the first relevant non-ad link."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    }
    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    
    try:
        response = requests.get(search_url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for the primary search result links
        for a in soup.find_all('a', href=True):
            href = a['href']
            if "url?q=" in href: # Clean up Google's redirect links
                href = href.split("url?q=")[1].split("&sa=")[0]
            
            if "google.com" not in href and "http" in href:
                return href
        return None
    except Exception as e:
        print(f"Search failed: {e}")
        return None

def extract_vibes(user_input, hot_springs_only=False):
    """
    The Saturn Engine 'Travel' Scraper.
    Works for destinations (Brazil, LA) or specific niches (Hot Springs).
    """
    # 1. Format the Search Query
    if hot_springs_only:
        query = f"reputable natural hot springs in {user_input} list"
    else:
        query = f"top unique things to do and hidden gems in {user_input}"

    # 2. Find the best 'Source' via Google
    target_url = google_search(query)
    
    if not target_url:
        return {"error": "The engine couldn't find a reliable source for this vibe."}

    # 3. Scrape the Content (The Secret Weapon)
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(target_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        findings = []
        # We look for headers (h2, h3) and list items where travel spots are usually named
        for item in soup.find_all(['h2', 'h3', 'strong', 'li']):
            text = item.get_text(strip=True)
            # Filter for text that looks like a location/activity name (not too long, not too short)
            if 4 < len(text) < 80:
                # Basic cleanup to remove numbers like '1. ' from list items
                clean_text = ''.join([i for i in text if not i.isdigit()]).lstrip('. ')
                if clean_text not in findings:
                    findings.append(clean_text)

        return {
            "location": user_input,
            "source_url": target_url,
            "recommendations": findings[:12], # Return the top 12 vibes
            "mode": "Hot Springs ♨️" if hot_springs_only else "General Exploration"
        }
    except Exception as e:
        return {"error": str(e)}
