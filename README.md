# Crestron Flex – Guided Selling (Demo)

A Gradio web app that recommends Crestron Flex products for meeting rooms, generates a client‑ready PDF summary, and simulates a Salesforce “Get Quote” hand‑off via CSV. Designed as a polished interview/demo artifact.

> **Tech highlights:** Gradio UI, OpenAI chat completions, product URL + image resolution (Crestron catalog + Widen CDN scraping), CSV “lead” sink, ReportLab PDF generation, and custom CSS.

---

## Features

- **Guided configuration**: Pick *Room Type* (Huddle/Small/Medium/Large), *Platform* (Teams/Zoom/Audio/Other), and describe *User Needs*.
- **Structured AI recommendations**: The app asks an LLM for a strict JSON payload with:
  - A concise **rationale** (overview sentence + per‑product coaching lines).
  - **2–4 product cards** with `name`, `summary`, `product_url`, `image_url`, `price`, and `why_fit` bullets.
- **Smart product links**: Attempts to resolve real **Crestron catalog URLs** from product names/SKUs; falls back to site search when needed.
- **Best‑effort product imagery**: Scrapes OG or Widen CDN images from the product page; otherwise uses a placeholder.
- **“Get Quote” flow** (Salesforce simulated): Appends a row to `leads_demo.csv` with a generated `LEAD-YYYYMMDD-<epoch>` ID once contact details are provided.
- **PDF export**: Generates a branded, one‑page recommendation summary PDF with images, bullets, and “View on Crestron” links.
- **Polished UI**: Custom CSS (Crestron‑inspired palette) and responsive product cards.

---

## Architecture (at a glance)

- **UI layer**: `gradio.Blocks` with two panels: *Configure Your Space* and *Suggested Products & Rationale*; plus a *Buy from a Dealer* lead section and PDF export.
- **LLM adapter**: `llm_structured_reco()` uses OpenAI Chat Completions to prompt for **strict JSON** (enforced by a schema‑style system prompt).
- **URL & image resolver**:
  - SKU extraction (regex) → tries stable Crestron catalog paths → falls back to site search or DuckDuckGo query.
  - Widen/OG image scraping with graceful timeouts and logo filters.
- **Lead sink**: `submit_lead()` appends a CSV row to `leads_demo.csv` (created if missing).
- **PDF generator**: ReportLab layout with headings, table of inputs, rationale, product sections, and inline images.
- **Launch**: `demo.launch(server_name="0.0.0.0", server_port=$PORT||7860, ssr_mode=False)`.

---

## Requirements

- **Python** 3.9+ (tested with recent 3.10/3.11)
- System packages: none required beyond Python
- Python packages:
  - `gradio`
  - `python-dotenv`
  - `openai` (>=1.0)
  - `requests`
  - `beautifulsoup4`
  - `reportlab`

Create a minimal `requirements.txt`:

```
gradio
python-dotenv
openai>=1.0.0
requests
beautifulsoup4
reportlab
```

> If you’ll store large binaries (e.g., 3D assets), consider installing **Git LFS** separately.

---

## Setup

1. **Clone your repo / open the project** in VS Code or a terminal.
2. **Create and activate a virtual environment** (optional but recommended):
   ```powershell
   # PowerShell (Windows)
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   ```bash
   # macOS/Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Create `.env`** with your OpenAI API key:
   ```env
   OPENAI_API_KEY=sk-...
   ```
   > Keep this file out of git: add `.env` to `.gitignore`.
5. **Run the app**:
   ```bash
   python app.py
   ```
   The app will start on `http://127.0.0.1:7860/` (or `$PORT` if set).

---

## Using the App

1. In **Configure Your Space**, select:
   - **Room Type**: Huddle, Small, Medium, or Large.
   - **Preferred Platform**: Teams, Zoom, Audio, or Other.
   - **Describe Your Needs**: plain text (e.g., “dual displays, ceiling mics, BYOD”).  
2. Click **Generate Recommendation**.
3. Review **Suggested Products & Rationale**:
   - Each product card includes name, a short summary, price hint, “why fit” bullets, an image, and **View on Crestron** link.
4. To simulate a **dealer quote**:
   - Enter Contact Name + Email (and optional fields) and click **Get Quote**.
   - A row is appended to `leads_demo.csv`; you’ll see a **Lead ID** in the UI.
   - The **Generate PDF** button becomes visible.
5. Click **Generate PDF** to download a one‑page recommendation summary.

---

## Configuration Notes

- **Model**: Default is `gpt-4o-mini`. Update in `llm_structured_reco()` if needed.
- **Strict JSON**: The system prompt enforces a schema. The UI strips code fences and validates JSON before rendering.
- **Image fetch**: Uses HEAD/GET checks and avoids obvious logos; Widen assets are upscaled to a larger width when possible.
- **Timeouts**: Network helpers use short timeouts to keep the UI responsive.
- **CSV path**: `leads_demo.csv` is created in the working directory.
- **Branding**: Colors are Crestron‑inspired; the app displays clear “demo / no affiliation” disclaimers.

---

## Deployment

### Local workstation
Run `python app.py`. To share temporarily, you can use a tunneling tool (e.g., Cloudflare Tunnel or similar).

### Hugging Face Spaces (Gradio)
- Create a new Space, set SDK to **Gradio**, and push `app.py` + `requirements.txt`.
- Add `OPENAI_API_KEY` as a **Secret** in the Space settings.
- Spaces auto‑runs on start; no extra launch script is necessary.

### Docker (optional)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=7860
CMD ["python", "app.py"]
```

---

## Troubleshooting

- **“API key missing”**: The UI still loads, but recommendations won’t be generated. Add `OPENAI_API_KEY` to `.env`.
- **No images**: Some catalog pages block hotlinking or omit OG tags. The app falls back to a placeholder.
- **Wrong or 404 product links**: The resolver tries multiple Crestron paths, then search. For discontinued SKUs, links may route to legacy or “Inactive/Discontinued” paths.
- **Windows PowerShell execution policy**: If activating venv fails, open VS Code terminal as Administrator and run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (understand the implications first).

---

## Security & Privacy

- Do not commit `.env` or any secrets.
- All “Salesforce” behavior is simulated via CSV in this demo.
- The app performs HTTP requests to third‑party sites to resolve product details; review policies before production use.

---

## License / Attribution

This repository is intended for demo/interview use and has **no affiliation with Crestron**. Product names are the property of their respective owners.
