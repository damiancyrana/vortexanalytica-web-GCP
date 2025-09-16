# Vortex Analytica - Development Setup

## 🚀 Quick Start

```bash
# 1. Clone and navigate to project
cd vortexanalytica-web-GCP

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start development server
./dev-start.sh
```

## 🔧 Development Configuration

This project supports **two modes**:

### Development Mode (`ENVIRONMENT=development`)
- ✅ **No GCP dependencies** - runs locally
- ✅ Uses environment variables for secrets
- ✅ Local Redis (optional)
- ✅ Mock email service

### Production Mode (`ENVIRONMENT=production`)
- 🔐 Google Secret Manager for secrets
- ☁️ GCP Pub/Sub for messaging
- 🔥 Firebase for authentication
- 📧 Real SMTP for emails

## 🌍 Environment Variables

### Required for Development
```bash
ENVIRONMENT=development
SESSION_SECRET_KEY=your-32-char-secret-key-here
REDIS_HOST=localhost
```

### Optional for Development
```bash
SMTP_USER=dev@example.com
SMTP_PASS=dev-password
PROJECT_ID=vortexanalytica-local
REDIS_PORT=6379
```

## 📁 Configuration Files

- `.env` - Environment variables (auto-loaded)
- `dev-start.sh` - Development startup script
- `Backend/core/config.py` - Main configuration

## 🔄 Development Workflow

1. **Start server**: `./dev-start.sh`
2. **Access app**: http://127.0.0.1:8080
3. **Make changes**: Files auto-reload with `--reload`
4. **Debug**: Check console logs

## 🐛 Common Issues

### "Secret Manager client failed"
- **Solution**: Set `ENVIRONMENT=development`
- **Reason**: App tries to use GCP in production mode

### "Redis connection failed"
- **Solution**: Install Redis or set different `REDIS_HOST`
- **Alternative**: Comment out Redis code for basic testing

### "Session secret too short"
- **Solution**: Use 32+ character `SESSION_SECRET_KEY`
- **Example**: `local-dev-secret-key-32-characters`

## 📂 Project Structure

```
Backend/
  ├── core/config.py     # Configuration (dev/prod modes)
  ├── services/          # Business logic
  └── routes/            # API endpoints
Frontend/
  ├── templates/         # Jinja2 templates
  └── static/           # CSS, JS, images
```

## 🧪 Testing

```bash
# Unit tests (if available)
pytest

# Manual testing
curl http://127.0.0.1:8080/

# Form testing
# Visit http://127.0.0.1:8080 and use contact form
```

## 🚢 Production Deployment

For production deployment, ensure:
- `ENVIRONMENT=production`
- GCP credentials configured
- Redis/Firebase services available
- Proper secret management

---

**Happy coding! 🎉**