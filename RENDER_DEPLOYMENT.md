# Deploying SlothClerk to Render ☁️🚀

SlothClerk is fully configured for deployment on [Render](https://render.com) using **Render Blueprints (`render.yaml`)** or standard Web Service configuration.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

---

## ⚡ Option 1: One-Click Blueprint Deployment (Recommended)

1. Push your changes to your GitHub repository:
   ```bash
   git push origin main
   ```
2. In your Render Dashboard, click **New +** -> **Blueprint**.
3. Connect your `slothclerk` GitHub repository.
4. Render will automatically detect `render.yaml` and configure:
   - **Service Name:** `slothclerk`
   - **Runtime:** `Python 3.11`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Path:** `/health`
5. (Optional) Add your `ELEVENLABS_API_KEY` in Render Environment Variables if you want cloud voice synthesis.
6. Click **Apply** to deploy!

---

## 🛠️ Option 2: Manual Web Service Setup on Render

1. Log in to [dashboard.render.com](https://dashboard.render.com).
2. Click **New +** -> **Web Service**.
3. Select your repository: `SidakSethi-Singh/slothclerk`.
4. Configure the settings:
   - **Name:** `slothclerk`
   - **Region:** Any (e.g. Oregon, Frankfurt)
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** `Free` or `Starter`
5. Set Environment Variables:
   - `DEMO_MODE_IF_NO_OLLAMA`: `true`
   - `RENDER`: `true`
   - `OFFLINE_MODE_ONLY`: `false`
   - `ELEVENLABS_API_KEY`: *(Optional)* Your ElevenLabs API key.
6. Click **Create Web Service**.

---

## 💡 Cloud Demo Fallback Mode

Render free and standard instances do not have local Ollama daemons pre-installed. SlothClerk includes an automated **Deterministic Clause Engine & Verbatim Citation Fallback**:
- When deployed on Render without a local Ollama daemon, SlothClerk detects the environment and activates its high-performance deterministic clause scanner (`DEMO_MODE_IF_NO_OLLAMA=true`).
- It extracts contract text, chunks it, validates citations verbatim against the source chunk text, and returns full audit results without crashing.
- Full UI, ElevenLabs voice narration, and citation popovers operate smoothly on Render.
