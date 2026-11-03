# Deriv 24/7 Multi-Asset Cloud Trading Terminal

Automated trading bot and live web terminal specialized in **Volatility 75 Index (`R_75`)** and **Bitcoin (`cryBTCUSD`)** on Deriv using the empirically verified **Bollinger Bands Mean Reversion** strategy.

---

## Deploy to Render (Zero-Friction Guide)

### 1. Push to GitHub
1. Create a new empty repository on **[github.com](https://github.com/new)** named `deriv-trading-bot`.
2. Push this repository to GitHub:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/deriv-trading-bot.git
   git branch -M main
   git push -u origin main
   ```

### 2. Deploy on Render
1. Go to **[dashboard.render.com](https://dashboard.render.com)**.
2. Click **New +** -> **Web Service**.
3. Connect your `deriv-trading-bot` GitHub repository.
4. Render will auto-detect Python. Fill in the following settings:
   - **Name**: `deriv-trading-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
5. Under **Environment Variables**, add:
   - `DERIV_APP_ID`: `34RboqpEHbA165Ak2BIHZ`
   - `DERIV_API_TOKEN`: `pat_944e8f7a9ae3c376024ba8b777f3af28dd6ff12bb96b304720aaacd0040f6c49`
   - `DERIV_ACCOUNT_ID`: `DOT94309357`
6. Click **Deploy Web Service**!

---

## Running Locally

To run the web dashboard locally:
```bash
uvicorn app:app --host 127.0.0.1 --port 8080 --reload
```
Then visit **http://127.0.0.1:8080** in your browser.
