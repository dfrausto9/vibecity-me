"""Vibe City Kitchen: a mood-based recipe finder that hands off to RecipeScraperPro.

The page is self-contained (templates/index.html); this app only serves it.
The previous travel version of Vibe City lives on the travel-app-archive branch.
"""
from flask import Flask, make_response, send_from_directory

app = Flask(__name__, template_folder="templates", static_folder="static")
SITE_URL = "https://vibecity.me"


@app.route("/")
def home():
    resp = send_from_directory(app.template_folder, "index.html")
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@app.route("/robots.txt")
def robots_txt():
    resp = make_response(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    return resp


@app.route("/sitemap.xml")
def sitemap_xml():
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{SITE_URL}/</loc></url>\n"
        "</urlset>\n"
    )
    resp = make_response(body)
    resp.headers["Content-Type"] = "application/xml; charset=utf-8"
    return resp


@app.route("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    app.run(debug=True)
