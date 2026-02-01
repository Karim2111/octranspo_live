# Setup Without Docker - OC Transpo Live

## Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- PostgreSQL 14 or higher
- npm or yarn

## Step-by-Step Setup

### 1. Install PostgreSQL

#### macOS (using Homebrew)
```bash
brew install postgresql@16
brew services start postgresql@16
```

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### Windows
Download and install from: https://www.postgresql.org/download/windows/

### 2. Create Database

```bash
# Access PostgreSQL
psql postgres

# Create database and user
CREATE DATABASE octranspo_live;
CREATE USER octranspo WITH PASSWORD 'octranspo';
GRANT ALL PRIVILEGES ON DATABASE octranspo_live TO octranspo;

# Exit psql
\q
```

### 3. Setup Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
DATABASE_URL=postgresql://octranspo:octranspo@localhost:5432/octranspo_live
ML_SERVICE_URL=http://localhost:8001
DEBUG=True
CACHE_TTL=300
EOF

# Initialize database
python init_db.py

# Start backend server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be running at: **http://localhost:8000**

### 4. Setup ML Service (New Terminal)

```bash
cd ml-service

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Train the model
python train_model.py

# Start ML service
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

ML Service will be running at: **http://localhost:8001**

### 5. Setup Frontend (New Terminal)

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

Frontend will be running at: **http://localhost:3000**

## Verification

1. **Backend API**: Visit http://localhost:8000/docs
2. **ML Service**: Visit http://localhost:8001
3. **Frontend**: Visit http://localhost:3000

You should see:
- Interactive map with Ottawa centered
- Search bar for stops
- When you click on a stop marker, you'll see arrival predictions

## Troubleshooting

### PostgreSQL Connection Error

If you get database connection errors:

```bash
# Check if PostgreSQL is running
# macOS:
brew services list | grep postgresql

# Linux:
sudo systemctl status postgresql

# Windows:
# Check Services app for PostgreSQL service
```

### Port Already in Use

If ports 8000, 8001, or 3000 are already in use:

**Backend** (change port):
```bash
uvicorn main:app --reload --port 8080
```

**ML Service** (change port):
```bash
uvicorn main:app --reload --port 8002
# Update backend/.env: ML_SERVICE_URL=http://localhost:8002
```

**Frontend** (change port):
```bash
PORT=3001 npm start
```

### Python Version Issues

Check your Python version:
```bash
python --version  # Should be 3.11+
```

If using older Python:
```bash
# Install Python 3.11
# macOS:
brew install python@3.11

# Ubuntu:
sudo apt install python3.11 python3.11-venv
```

### Database Not Loading GTFS Data

The initial `init_db.py` might fail to download GTFS data. This is okay for testing! The app will work with empty data initially.

To manually load data later:
```bash
cd backend
source venv/bin/activate
python init_db.py
```

### Frontend Can't Connect to Backend

Update `frontend/src/App.js` if backend is on different port:

```javascript
const API_BASE_URL = 'http://localhost:8000/api';  // Change port if needed
```

## Running in Production

### Backend

```bash
cd backend
source venv/bin/activate

# Install production server
pip install gunicorn

# Run with Gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### ML Service

```bash
cd ml-service
source venv/bin/activate
gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001
```

### Frontend

```bash
cd frontend

# Build for production
npm run build

# Serve with a static server
npx serve -s build -p 3000

# Or use nginx, apache, etc.
```

## Environment Variables Reference

### Backend (.env)
```env
DATABASE_URL=postgresql://octranspo:octranspo@localhost:5432/octranspo_live
ML_SERVICE_URL=http://localhost:8001
DEBUG=True
CACHE_TTL=300
OC_TRANSPO_APP_ID=  # Optional: Get from OC Transpo
OC_TRANSPO_API_KEY=  # Optional: Get from OC Transpo
```

## Stopping Services

Press `Ctrl+C` in each terminal window to stop the services.

## Next Steps

1. **Test the API**: Visit http://localhost:8000/docs
2. **Load real data**: The GTFS data will be downloaded automatically
3. **Train better ML model**: Add historical data to improve predictions
4. **Customize**: Modify the code to add features

## Quick Reference Commands

```bash
# Start backend
cd backend && source venv/bin/activate && uvicorn main:app --reload

# Start ML service
cd ml-service && source venv/bin/activate && uvicorn main:app --port 8001 --reload

# Start frontend
cd frontend && npm start

# Access PostgreSQL
psql -U octranspo -d octranspo_live

# View logs
# Just watch the terminal output for each service
```

## Need Help?

- Check the main README.md for detailed documentation
- Review DEVELOPMENT.md for development guidelines
- Check ARCHITECTURE.md to understand the system design

**Happy coding! 🚌**
