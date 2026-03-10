# Deployment Guide

## Option 1: Railway (Easiest - Recommended)

1. **Sign up at [Railway](https://railway.app/)**
   - Use your GitHub account

2. **Create New Project**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository

3. **Configure**
   - Railway auto-detects Flask
   - It will use `Procfile` automatically
   - Database persists in volume

4. **Deploy**
   - Push to GitHub → Auto-deploys
   - Get your URL: `yourapp.railway.app`

## Option 2: Heroku (GitHub Student Pack)

1. **Install Heroku CLI**
   ```bash
   curl https://cli-assets.heroku.com/install.sh | sh
   ```

2. **Login and Create App**
   ```bash
   heroku login
   heroku create your-app-name
   ```

3. **Deploy**
   ```bash
   git add .
   git commit -m "Prepare for deployment"
   git push heroku main
   ```

4. **Initialize Database**
   ```bash
   heroku run python create_users.py
   heroku run python create_admin.py
   ```

## Option 3: DigitalOcean ($200 Credit from GitHub Pack)

1. **Claim Credits**
   - Go to education.github.com
   - Claim DigitalOcean credits

2. **Create Droplet**
   - Choose Ubuntu 22.04
   - Basic plan ($6/month)

3. **SSH and Setup**
   ```bash
   ssh root@your-server-ip
   
   # Install dependencies
   apt update
   apt install python3-pip python3-venv nginx -y
   
   # Clone your repo
   git clone your-repo-url
   cd AnnotationsProject
   
   # Setup Python environment
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   
   # Create users
   python3 create_users.py
   python3 create_admin.py
   
   # Setup systemd service (production)
   # Setup nginx as reverse proxy
   ```

## Option 4: Render (Free Tier)

1. **Sign up at [Render](https://render.com/)**

2. **New Web Service**
   - Connect GitHub repo
   - Environment: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`

3. **Configure**
   - Add environment variables if needed
   - Database persists in disk

## Important Notes

### Before Deploying:

1. **Change Secret Key** in `app.py`:
   ```python
   app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-secret-key')
   ```

2. **Create Users on Server**:
   - After first deploy, run:
   - `python3 create_users.py`
   - `python3 create_admin.py`

3. **Database**:
   - SQLite works for small deployments
   - For production, consider PostgreSQL

### Security Checklist:
- [ ] Change admin password
- [ ] Set strong SECRET_KEY
- [ ] Use environment variables
- [ ] Enable HTTPS
- [ ] Configure CORS if needed

## Recommended Workflow:

1. **Start with Railway** (fastest, free)
2. **If need more control** → DigitalOcean (GitHub credits)
3. **For team/production** → Heroku or Azure

## GitHub Setup:

```bash
# Initialize git (if not done)
git init
git add .
git commit -m "Initial commit"

# Create GitHub repo and push
git remote add origin your-repo-url
git push -u origin main
```

## Need Help?
- Railway: https://docs.railway.app/
- Heroku: https://devcenter.heroku.com/
- DigitalOcean: https://www.digitalocean.com/community/tutorials
