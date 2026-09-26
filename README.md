# KrishiBandhu v2

Run:
1. `py -m venv .venv`
2. Windows: `.venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env`
5. Add API keys.
6. `python app.py`
7. Open http://127.0.0.1:5000

Live integrations:
- Gemini crop-image analysis: GEMINI_API_KEY
- Open-Meteo weather: no API key required
- Razorpay payments: RAZORPAY_KEY_ID + RAZORPAY_KEY_SECRET
- Market prices: configure an official market-data provider with MARKET_API_URL/MARKET_API_KEY

The app stores users, profiles, expert requests, crop reports, products, orders and transport requests in SQLite.
For deployment, move the database to PostgreSQL and use HTTPS.

AI crop analysis is preliminary decision support, not a confirmed diagnosis.
