# app.py
import os
import csv
import time
import json
import base64
import re
import tempfile
from datetime import datetime
from html import escape
from typing import Optional, Any, List
from urllib.parse import urljoin, urlparse, quote_plus

import gradio as gr
from dotenv import load_dotenv

# PDF + image helpers
import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    ListFlowable, Table, TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# --- Load .env ---
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Lazy import OpenAI so the UI can load even if the key is missing
client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        client = None

# --- Branding (Crestron-inspired) ---
CRESTRON_BLUE = "#004A80"
CRESTRON_TEAL = "#007CA0"
CRESTRON_GRAY = "#41484F"
CRESTRON_RED  = "#EF373E"

HEADER_HTML = f"""
<div class="tk-header">
  <div class="tk-header-inner">
    <div class="tk-logo">Crestron Flex - Guided Selling (Demo)</div>
    <div class="tk-tag">Powered by Threekit</div>
  </div>
</div>
"""

CUSTOM_CSS = f"""
.gradio-container {{
  --radius-lg: 16px;
  --shadow-md: 0 8px 24px rgba(0,0,0,0.08);
  --crestron-blue: {CRESTRON_BLUE};
  --crestron-teal: {CRESTRON_TEAL};
  --crestron-gray: {CRESTRON_GRAY};
  --crestron-red: {CRESTRON_RED};
  font-family: 'Inter', system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
}}
.tk-header {{
  background: linear-gradient(90deg, var(--crestron-blue), var(--crestron-teal));
  color:#fff; padding:18px 20px; border-radius:16px; margin-bottom:16px;
}}
.tk-header-inner {{ display:flex; align-items:center; justify-content:space-between; }}
.tk-logo {{ font-weight:700; letter-spacing:.3px; font-size:18px; }}
.tk-tag {{ font-size:12px; opacity:.9; background:rgba(255,255,255,.15); padding:6px 10px; border-radius:999px; }}

.tk-card .gr-group, .tk-card .gr-box, .tk-card {{
  border-radius:16px !important; box-shadow: var(--shadow-md); border:1px solid rgba(0,0,0,.06);
}}
.tk-label {{ font-weight:600; color: var(--crestron-gray); }}

button, .gr-button {{ border-radius:999px !important; padding:10px 16px !important; font-weight:600 !important; }}
.gr-button-primary, button.primary {{ background: var(--crestron-blue) !important; border:1px solid var(--crestron-blue) !important; }}
.gr-button-secondary {{ background:#fff !important; color: var(--crestron-blue) !important; border:1px solid var(--crestron-blue) !important; }}

.gr-textbox, .gr-dropdown {{ border-radius:12px !important; }}

.tk-footer {{ margin-top:10px; font-size:12px; color:#6b7280; }}

.products-wrap {{ display:grid; grid-template-columns:1fr; gap:16px; }}
@media (min-width: 880px) {{
  .products-wrap {{ grid-template-columns:1fr 1fr; }}
}}
.product-card {{
  display:grid; grid-template-columns:140px 1fr; gap:16px; padding:14px; border-radius:16px;
  border:1px solid rgba(0,0,0,0.06); box-shadow: var(--shadow-md); background:#fff;
}}
.product-card img {{
  width:100%; height:100%; object-fit:contain; background:#f7fafc; border-radius:12px; border:1px solid rgba(0,0,0,0.05);
}}
.product-body h4 {{
  margin:0 0 6px 0; color: var(--crestron-blue); display:flex; align-items:center; gap:10px;
}}
.price-badge {{
  display:inline-block; background:#e8f2f7; color: var(--crestron-blue);
  border: 1px solid rgba(0,0,0,.06); padding:3px 8px; border-radius:999px; font-size:12px; font-weight:700;
}}
.product-body p {{ margin:0 0 8px 0; color:#333; }}
.product-body ul {{ margin:0 0 8px 18px; }}
.product-body a {{ color: var(--crestron-teal); text-decoration:none; font-weight:600; }}

/* Rationale box */
.rationale-card {{
  padding: 14px;
  border-radius: 16px;
  background: #f2f7fb;
  border: 1px solid rgba(0,0,0,0.05);
  margin-bottom: 12px;
  color: #1f2937;
  white-space: pre-line;
}}
.rationale-card strong {{ color: var(--crestron-blue); }}

/* Placeholder */
.placeholder-reco {{ color: var(--crestron-blue); font-weight: 600; }}
"""

# --- LLM prompt (with detailed rationale) ---
SYSTEM_PROMPT = """
You are a helpful assistant trained on Crestron Flex product offerings.

Given room type, platform, and user needs, respond ONLY with strict JSON in this schema:
{
  "rationale": "overview + per-product details",
  "products": [
    {
      "name": "Product name",
      "summary": "1-2 sentence summary",
      "product_url": "https://www.crestron.com/....",
      "image_url": "https://... (direct image URL if available; otherwise empty)",
      "price": "string like '$2,499' or 'Request quote' if pricing isn't public",
      "why_fit": ["bullet 1", "bullet 2", "bullet 3"]
    }
  ]
}

Write the rationale as follows:
- Start with ONE concise sentence that connects the room type, platform, and the user’s needs to the overall solution approach.
- Then include an ITEMIZED LIST, one line per product, written to coach a beginner. For each line use this pattern:
  "<Product Name>: what it is (in plain English), where it goes in the room, what it plugs into/controls, and why it’s needed for this setup."
  Use simple, non-jargon language. If you use an acronym, write it once as Full Term (ACRONYM). Keep each line ~20–30 words.

Formatting rules:
- Put the overview sentence first, then each product line on its own line within the same rationale string (use line breaks).
- Do NOT use markdown formatting inside the JSON values.
- Keep the rationale under ~120 words total.

Guidelines:
- Favor products that match the platform (Teams / Zoom / Audio / Other).
- Reflect any constraints in the user needs (e.g., dual displays, ceiling mics, BYOD).
- Prefer image URLs hosted on crestron.com if possible; if unknown, leave image_url empty.
- For pricing, use a brief string (e.g., '$1,999', 'Starting at $X', or 'Request quote').
- Keep product list to 2–4 items max.
- Do NOT include any extra keys, comments, markdown, or text outside the JSON.
"""


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

def _strip_code_fences(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 3:
            body = parts[1]
            if body.strip().startswith("json"):
                body = body.split("\n", 1)[1] if "\n" in body else ""
            return body
    return s

def llm_structured_reco(room_type: str, platform: str, user_needs: str) -> dict:
    if client is None:
        return {"error": "API key missing", "rationale": "", "products": []}
    user_prompt = f"""Room Type: {room_type}
Platform: {platform}
User Needs: {user_needs}"""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": user_prompt}],
            temperature=0.4,
            max_tokens=900,
        )
        raw = resp.choices[0].message.content  # type: ignore[assignment]
        payload = _strip_code_fences(raw or "")
        if not payload.strip():
            return {"error": "LLM returned empty response (expected JSON).", "rationale": "", "products": []}
        try:
            data = json.loads(payload)
        except Exception as e:
            return {"error": f"Could not parse LLM JSON: {e}", "rationale": "", "products": []}
        data.setdefault("rationale", "")
        data.setdefault("products", [])
        for p in data["products"]:
            p.setdefault("name", ""); p.setdefault("summary", "")
            p.setdefault("product_url", ""); p.setdefault("image_url", "")
            p.setdefault("price", "Request quote"); p.setdefault("why_fit", [])
        return data
    except Exception as e:
        return {"error": f"LLM error: {e}", "rationale": "", "products": []}

PLACEHOLDER_IMAGE = "https://upload.wikimedia.org/wikipedia/commons/3/3f/Placeholder_view_vector.svg"

# ---------- helpers for typing ----------
def to_str(val: Any) -> Optional[str]:
    if val is None: return None
    if isinstance(val, (list, tuple, dict)): return None
    try: return str(val)
    except Exception: return None

# ---------- URL & image helpers ----------
def _is_image_response(resp: requests.Response) -> bool:
    return "image/" in resp.headers.get("Content-Type", "")

def _head_or_get(url: str, referer: Optional[str] = None) -> Optional[requests.Response]:
    headers = {"User-Agent": UA,
               "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}
    if referer: headers["Referer"] = referer
    try:
        r = requests.head(url, timeout=8, allow_redirects=True, headers=headers)
        if r.ok and _is_image_response(r): return r
    except Exception: pass
    try:
        r = requests.get(url, timeout=8, stream=True, headers=headers)
        if r.ok and _is_image_response(r): return r
    except Exception: pass
    return None

def _fetch_og_image(page_url: str) -> Optional[str]:
    headers = {"User-Agent": UA,
               "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
               "Accept-Language": "en-US,en;q=0.9",
               "Referer": "https://www.crestron.com/"}
    try:
        r = requests.get(page_url, timeout=10, headers=headers)
        if not r.ok or "text/html" not in r.headers.get("Content-Type",""): return None
        soup = BeautifulSoup(r.text, "html.parser")
        for key in ("og:image", "twitter:image", "og:image:url"):
            tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
            if isinstance(tag, Tag):
                content = to_str(tag.get("content"))
                if content:
                    return urljoin(page_url, content)
    except Exception:
        return None
    return None

def _looks_like_logo(url: str) -> bool:
    l = url.lower()
    return any(x in l for x in ["logo", "favicon", "ogimage", "social", "icon"])

def _extract_crestron_best_image(page_url: str) -> Optional[str]:
    """Return the best Widen-hosted or OG image from a Crestron product page; avoid generic logos."""
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.crestron.com/"
    }
    try:
        r = requests.get(page_url, timeout=12, headers=headers)
        if not r.ok or "text/html" not in r.headers.get("Content-Type", ""):
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        candidates: List[str] = []

        # Prefer Widen CDN product imagery (most reliable)
        for img in soup.find_all("img"):
            if not isinstance(img, Tag): continue
            for attr in ("src", "data-src"):
                src = to_str(img.get(attr))
                if not src: continue
                absu = urljoin(page_url, src)
                if "embed.widencdn.net/img/crestron" in absu:
                    candidates.append(absu)

        for source in soup.find_all("source"):
            if not isinstance(source, Tag): continue
            srcset = to_str(source.get("srcset"))
            if not srcset: continue
            for part in srcset.split(","):
                url_part = part.strip().split(" ")[0]
                if not url_part: continue
                absu = urljoin(page_url, url_part)
                if "embed.widencdn.net/img/crestron" in absu:
                    candidates.append(absu)

        # If none, try OG/meta images (but avoid logos)
        if not candidates:
            og = _fetch_og_image(page_url)
            if og and not _looks_like_logo(og):
                candidates.append(og)

        # Deduplicate
        seen: set[str] = set(); uniq: List[str] = []
        for u in candidates:
            if u not in seen:
                seen.add(u); uniq.append(u)

        # Prefer large Widen asset
        for u in uniq:
            if "embed.widencdn.net/img/crestron" in u and not _looks_like_logo(u):
                u2 = re.sub(r"/(\d+)px@1x/", "/1000px@1x/", u)
                if _head_or_get(u2, referer=page_url):
                    return u2

        # Any valid non-logo
        for u in uniq:
            if not _looks_like_logo(u) and _head_or_get(u, referer=page_url):
                return u
    except Exception:
        return None
    return None

# --- Product URL resolution (improved) ---
URL_CACHE: dict[str, Optional[str]] = {}

SKU_REGEX = re.compile(r"\b[A-Z]{1,8}(?:-[A-Z0-9]{1,10}){1,8}\b")

def extract_sku(product_name: str) -> Optional[str]:
    matches = SKU_REGEX.findall(product_name.upper())
    if not matches:
        return None
    return sorted(matches, key=len, reverse=True)[0]

def try_known_catalog_paths(sku: str) -> Optional[str]:
    """Try a set of stable Crestron product URL patterns before using search."""
    bases = [
        # Workspace Solutions (often current)
        "https://www.crestron.com/Products/Workspace-Solutions/Unified-Communications/Crestron-Flex-Integrator-Kits/",
        "https://www.crestron.com/Products/Workspace-Solutions/Unified-Communications/Crestron-Flex-Tabletop-Conferencing-Systems/",
        "https://www.crestron.com/Products/Workspace-Solutions/Unified-Communications/Crestron-Flex-Wall-Mount-Conferencing-Systems/",
        "https://www.crestron.com/Products/Workspace-Solutions/Unified-Communications/Intelligent-Audio/",
        # Catalog (classic taxonomy)
        "https://www.crestron.com/Products/Catalog/Unified-Communications/Flex-Conferencing/Integrator-Kit/",
        "https://www.crestron.com/Products/Catalog/Unified-Communications/Flex-Conferencing/Tabletop/",
        "https://www.crestron.com/Products/Catalog/Unified-Communications/Flex-Conferencing/Wall-Mount/",
        "https://www.crestron.com/Products/Catalog/Unified-Communications/Intelligent-Audio/Distributed/",
        "https://www.crestron.com/Products/Catalog/Unified-Communications/Intelligent-Audio/USB/",
    ]
    headers = {"User-Agent": UA}
    for base in bases:
        url = base + sku
        try:
            r = requests.get(url, timeout=8, headers=headers, allow_redirects=True)
            if r.ok and "text/html" in r.headers.get("Content-Type", "") and "404" not in r.url:
                return r.url
        except Exception:
            continue
    # Discontinued catalog path pattern e.g., /Inactive/Discontinued/U/UC-C160-Z
    first = (sku[0] if sku else "U").upper()
    disc = f"https://www.crestron.com/Products/Catalog/Inactive/Discontinued/{first}/{sku}"
    try:
        r = requests.get(disc, timeout=8, headers=headers, allow_redirects=True)
        if r.ok and "text/html" in r.headers.get("Content-Type", "") and "404" not in r.url:
            return r.url
    except Exception:
        pass
    return None

def search_crestron_for_sku(sku: str) -> Optional[str]:
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    queries = [
        f"https://www.crestron.com/en-US/Search?q={quote_plus(sku)}",
        f"https://www.crestron.com/Search?q={quote_plus(sku)}",
    ]
    for q in queries:
        try:
            r = requests.get(q, timeout=12, headers=headers)
            if not r.ok or "text/html" not in r.headers.get("Content-Type",""):
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                if not isinstance(a, Tag): continue
                href = to_str(a.get("href"))
                if not href: continue
                abs_href = urljoin(q, href)
                if "/Products/" in abs_href and "/Catalog" in abs_href and sku in abs_href.upper():
                    return abs_href
        except Exception:
            continue
    return None

def search_catalog_via_duckduckgo(query: str) -> Optional[str]:
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", "Referer": "https://duckduckgo.com/"}
    urls = [
        f"https://duckduckgo.com/html/?q={quote_plus('site:crestron.com Products/Catalog ' + query)}",
        f"https://duckduckgo.com/html/?q={quote_plus('site:crestron.com ' + query)}",
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=12, headers=headers)
            if not r.ok or "text/html" not in r.headers.get("Content-Type",""): continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                if not isinstance(a, Tag): continue
                href = to_str(a.get("href"))
                if href and "crestron.com" in href and "/Products/" in href:
                    if "/Catalog/" in href or "/Workspace-Solutions/" in href:
                        return href
        except Exception:
            continue
    return None

def resolve_product_url(product_name: str, proposed_url: Optional[str]) -> Optional[str]:
    key = f"{product_name}||{proposed_url or ''}"
    if key in URL_CACHE:
        return URL_CACHE[key]

    headers = {"User-Agent": UA}
    # 1) Accept a good proposed URL
    if proposed_url:
        try:
            r = requests.get(proposed_url, timeout=8, headers=headers, allow_redirects=True)
            if r.ok and "text/html" in r.headers.get("Content-Type", "") and "404" not in r.url:
                URL_CACHE[key] = r.url
                return r.url
        except Exception:
            pass

    # 2) Try known Crestron paths for this SKU
    sku = extract_sku(product_name or "")
    if sku:
        direct = try_known_catalog_paths(sku)
        if direct:
            URL_CACHE[key] = direct
            return direct

    # 3) DDG catalog search
    query = sku or product_name
    if query:
        ddg = search_catalog_via_duckduckgo(query)
        if ddg:
            URL_CACHE[key] = ddg
            return ddg

    # 4) Crestron search page (last resort)
    fallback = f"https://www.crestron.com/en-US/Search?q={quote_plus(query or 'Crestron')}"
    URL_CACHE[key] = fallback
    return fallback

def resolve_image_url(image_url: Optional[str], product_url: Optional[str]) -> Optional[str]:
    # Try provided image first
    if image_url:
        test_url = image_url
        if product_url and (image_url.startswith("//") or image_url.startswith("/")):
            base = product_url if product_url.endswith("/") else product_url + "/"
            test_url = urljoin(base, image_url)
        try:
            if _head_or_get(test_url, referer=product_url) and not _looks_like_logo(test_url):
                return test_url
        except Exception:
            pass
    # Then product page scrape (prefer Widen)
    if product_url:
        host = urlparse(product_url).netloc.lower()
        if "crestron.com" in host:
            best = _extract_crestron_best_image(product_url)
            if best and not _looks_like_logo(best):
                return best
        og = _fetch_og_image(product_url)
        if og and not _looks_like_logo(og):
            try:
                if _head_or_get(og, referer=product_url):
                    return og
            except Exception:
                pass
    return None

def embed_image_data_uri(url: Optional[str], referer: Optional[str]) -> str:
    def _to_data_uri(content: bytes, content_type: str) -> str:
        b64 = base64.b64encode(content).decode("ascii")
        return f"data:{content_type};base64,{b64}"
    if url:
        headers = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}
        if referer: headers["Referer"] = referer
        try:
            r = requests.get(url, timeout=12, headers=headers)
            if r.ok and r.content and _is_image_response(r):
                ctype = r.headers.get("Content-Type", "image/jpeg")
                return _to_data_uri(r.content, ctype)
        except Exception:
            pass
    # Fallback placeholder (SVG data URI)
    try:
        r = requests.get(PLACEHOLDER_IMAGE, timeout=8)
        if r.ok and r.content:
            ctype = r.headers.get("Content-Type", "image/svg+xml")
            return _to_data_uri(r.content, ctype)
    except Exception:
        pass
    return PLACEHOLDER_IMAGE

# ----------------------------------------------------------

def render_products_html(structured: dict) -> str:
    if not structured or ("error" in structured and structured["error"]):
        err = escape(structured.get("error", "Unknown error"))
        return f'<div class="rationale-card">⚠️ {err}</div>'

    rationale = escape(structured.get("rationale", ""))
    products = structured.get("products", []) or []

    parts = []
    if rationale:
        parts.append(f'<div class="rationale-card"><strong>Rationale:</strong> {rationale}</div>')

    if not products:
        parts.append('<div class="rationale-card placeholder-reco">Your recommendations will appear here.</div>')
    else:
        parts.append('<div class="products-wrap">')
        for p in products:
            name = p.get("name", "") or ""
            summary = p.get("summary", "") or ""
            price = p.get("price", "Request quote") or "Request quote"

            product_url = resolve_product_url(name, p.get("product_url", ""))
            product_url_safe = escape(product_url or "")

            resolved_img = resolve_image_url(p.get("image_url", ""), product_url or None)
            img_src = embed_image_data_uri(resolved_img, product_url)
            safe_img = escape(img_src)

            why = p.get("why_fit", []) or []
            why_items = "".join(f"<li>{escape(str(item))}</li>" for item in why[:6])
            link_html = f'<a href="{product_url_safe}" target="_blank" rel="noopener">View on Crestron</a>' if product_url else ""

            parts.append(f"""
            <div class="product-card">
              <div class="product-img">
                <img src="{safe_img}" alt="{escape(name)}">
              </div>
              <div class="product-body">
                <h4>{escape(name)} <span class="price-badge">{escape(price)}</span></h4>
                <p>{escape(summary)}</p>
                <ul>{why_items}</ul>
                {link_html}
              </div>
            </div>
            """)
        parts.append('</div>')
    return "\n".join(parts)

def recommend(room_type: str, platform: str, user_needs: str):
    data = llm_structured_reco(room_type, platform, user_needs)
    html = render_products_html(data)
    json_blob = json.dumps(data, ensure_ascii=False)
    return html, json_blob

# --- Dummy Salesforce Lead Submission (CSV demo) ---
LEADS_FILE = "leads_demo.csv"

def ensure_leads_file():
    if not os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "created_at","lead_id","name","email","company","phone",
                "room_type","platform","notes","recommendation_json",
            ])

def submit_lead(name, email, company, phone, room_type, platform, notes, reco_json):
    ensure_leads_file()
    ts = int(time.time())
    lead_id = f"LEAD-{datetime.utcnow().strftime('%Y%m%d')}-{ts}"
    created_at = datetime.utcnow().isoformat()
    with open(LEADS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([created_at, lead_id, name or "", email or "", company or "", phone or "",
                         room_type or "", platform or "", notes or "", reco_json or ""])
    return f"✅ Lead sent to Salesforce (demo). **Lead ID:** `{lead_id}`\n\nA CSV row was appended to `{LEADS_FILE}`."

def send_lead_and_unlock_pdf(name, email, company, phone, room_type, platform, notes, reco_json):
    if not (name and email):
        return ("⚠️ Please fill in at least Contact Name and Email before requesting a quote.",
                gr.update(visible=False), gr.update(visible=False))
    try:
        data = json.loads(reco_json) if reco_json else {}
        has_products = bool(data.get("products"))
    except Exception:
        has_products = False
    if not has_products:
        return ("⚠️ Please generate recommendations before clicking Get Quote.",
                gr.update(visible=False), gr.update(visible=False))
    msg = submit_lead(name, email, company, phone, room_type, platform, notes, reco_json)
    return (msg, gr.update(visible=True), gr.update(visible=True))

# --- PDF generation ---
def _download_image_to_tmp(url: Optional[str], referer: Optional[str] = None) -> Optional[str]:
    if not url: return None
    headers = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}
    if referer: headers["Referer"] = referer
    try:
        r = requests.get(url, timeout=10, headers=headers)
        if r.ok and r.content:
            fd, tmp_path = tempfile.mkstemp(suffix=".img")
            with os.fdopen(fd, "wb") as f: f.write(r.content)
            return tmp_path
    except Exception: pass
    return None

def generate_pdf(room_type: str, platform: str, user_needs: str, reco_json: Optional[str]):
    reco_json_str = reco_json or "{}"
    try:
        data = json.loads(reco_json_str)
    except Exception:
        data = {}

    rationale = data.get("rationale", "")
    products = data.get("products", []) or []

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    pdf_path = os.path.join(tempfile.gettempdir(), f"crestron_flex_recommendation_{ts}.pdf")

    styles = getSampleStyleSheet()
    title_style = styles["Title"]; title_style.textColor = colors.HexColor(CRESTRON_BLUE)
    h2 = styles["Heading2"]; h2.textColor = colors.HexColor(CRESTRON_BLUE)
    h3 = styles["Heading3"]; h3.textColor = colors.HexColor(CRESTRON_TEAL)
    body = styles["BodyText"]
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#6b7280"))
    bold = ParagraphStyle("bold", parent=styles["Normal"], fontSize=11, textColor=colors.black, leading=14)

    doc = SimpleDocTemplate(pdf_path, pagesize=letter, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48)
    story = []

    story.append(Paragraph("Crestron Flex – Recommendation Summary", title_style))
    story.append(Spacer(1, 6))
    story.append(Paragraph(datetime.utcnow().strftime("Generated: %Y-%m-%d %H:%M UTC"), small))
    story.append(Spacer(1, 14))

    table = Table(
        [["Room Type", room_type or "-"],
         ["Platform", platform or "-"],
         ["User Needs", user_needs or "-"]],
        colWidths=[1.4*inch, 4.1*inch],
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#e5e7eb")),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.HexColor("#e5e7eb")),
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f9fafb")),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(table); story.append(Spacer(1, 14))

    story.append(Paragraph("Rationale", h2))
    story.append(Paragraph(rationale or "—", body))
    story.append(Spacer(1, 12))

    if products:
        story.append(Paragraph("Recommended Products", h2)); story.append(Spacer(1, 6))
        for p in products[:4]:
            name = p.get("name", "") or ""
            summary = p.get("summary", "") or ""
            price = p.get("price", "Request quote") or "Request quote"
            why = p.get("why_fit", []) or []
            product_url = resolve_product_url(name, p.get("product_url", ""))

            story.append(Paragraph(name or "Product", h3))
            story.append(Paragraph(f"Price: <b>{price}</b>", bold))
            story.append(Spacer(1, 4))

            resolved_img = resolve_image_url(p.get("image_url", ""), product_url or None)
            img_path = _download_image_to_tmp(resolved_img, referer=product_url)
            if img_path:
                try:
                    story.append(RLImage(img_path, width=2.6*inch, height=1.7*inch)); story.append(Spacer(1, 6))
                except Exception:
                    pass

            story.append(Paragraph(summary or "—", body))
            if why:
                bullet_items = [Paragraph(str(w), body) for w in why[:6]]
                story.append(ListFlowable(bullet_items, bulletType="bullet", bulletFontName="Helvetica"))
            if product_url:
                story.append(Paragraph(f'<link href="{product_url}">View on Crestron</link>', body))
            story.append(Spacer(1, 10))
    else:
        story.append(Paragraph("No products available. Generate recommendations in the app first.", body))

    story.append(Spacer(1, 16))
    story.append(Paragraph("This document is for demo purposes only. Pricing is indicative and may require a dealer quote. Salesforce integration simulated via CSV.", small))

    doc.build(story)
    return pdf_path

# --- UI ---
with gr.Blocks(css=CUSTOM_CSS, fill_height=True, title="Crestron Flex - Guided Selling (Demo)", analytics_enabled=False) as demo:
    gr.HTML(HEADER_HTML)

    last_reco_json = gr.State("")

    with gr.Row():
        with gr.Column(scale=1, min_width=360, elem_classes=["tk-card"]):
            gr.Markdown("### Configure Your Space")
            with gr.Row():
                room_type = gr.Dropdown(choices=["Huddle", "Small", "Medium", "Large"], value="Medium", label="Room Type", elem_classes=["tk-label"])
                platform = gr.Dropdown(choices=["Teams", "Zoom", "Audio", "Other"], value="Zoom", label="Preferred Platform", elem_classes=["tk-label"])
            user_needs = gr.Textbox(label="Describe Your Needs", placeholder="e.g., dual displays, ceiling mics, touch panel, BYOD, budget constraints…", lines=4)
            generate_btn = gr.Button("Generate Recommendation", variant="primary")

        with gr.Column(scale=2, elem_classes=["tk-card"]):
            gr.Markdown("### Suggested Products & Rationale")
            products_html = gr.HTML(value="<div class='rationale-card placeholder-reco'>Your recommendations will appear here.</div>")
            generate_btn.click(fn=recommend, inputs=[room_type, platform, user_needs], outputs=[products_html, last_reco_json])

    with gr.Row():
        with gr.Column(elem_classes=["tk-card"]):
            gr.Markdown("### Buy from a Dealer")
            lead_name    = gr.Textbox(label="Contact Name")
            lead_email   = gr.Textbox(label="Email")
            lead_company = gr.Textbox(label="Company")
            lead_phone   = gr.Textbox(label="Phone")
            lead_notes   = gr.Textbox(label="Project Notes", lines=3, placeholder="Optional context for the dealer / sales team")
            send_btn     = gr.Button("Get Quote", variant="primary")
            send_result  = gr.Markdown()

            gr.Markdown("### Download PDF Summary")
            pdf_btn  = gr.Button("Generate PDF", visible=False)
            pdf_file = gr.File(label="Your PDF will appear here", file_count="single", visible=False)

            send_btn.click(fn=send_lead_and_unlock_pdf,
                           inputs=[lead_name, lead_email, lead_company, lead_phone, room_type, platform, lead_notes, last_reco_json],
                           outputs=[send_result, pdf_btn, pdf_file])

            pdf_btn.click(fn=generate_pdf,
                          inputs=[room_type, platform, user_needs, last_reco_json],
                          outputs=pdf_file)

    gr.Markdown('<div class="tk-footer">Demo app for interview purposes. Pricing shown is indicative and may require a dealer quote. Brand colors inspired by Crestron public brand guidelines. No affiliation. Salesforce integration simulated via CSV.</div>')

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        show_error=True,
        ssr_mode=False
    )
