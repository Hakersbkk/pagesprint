# PageSprint — one-page websites business

Sells professional one-page websites to local businesses for a flat fee, delivered in 24h.
Zero-cost stack: a local LLM gateway writes pitches and builds every site; MIT themes from Start Bootstrap are filled by the AI; payment is collected locally.

## Stack
- `app.py` — stdlib Python server + AI builder (OpenAI-compatible endpoint)
- `dashboard.html` — orders/leads/revenue control panel
- `store.template.html` — public storefront with service tiers
- `templates/` — 5 MIT themes (agency, creative, freelancer, grayscale, resume)
- `templates/fetch.py` — re-fetches themes via the jsDelivr CDN mirror of GitHub

## Run
```bash
python3 app.py   # dashboard on http://127.0.0.1:8790
```
Set your ebony/OpenAI-compatible key in ~/.our-free-model/settings.json.
