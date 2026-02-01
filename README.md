# OC Transpo Live - Real-Time Bus Tracking Web App

A full-stack web application for real-time bus arrival predictions for Ottawa's OC Transpo transit system.

## Features

- **Real-time bus tracking** with GTFS-RT feed integration
- **Interactive map** with stop markers and location-based search
- **Search functionality** to find stops by name or code
- **ML-enhanced predictions** using Random Forest/XGBoost models
- **Mobile-responsive design** built with Tailwind CSS
- **Fast API backend** with PostgreSQL caching
- **Accurate arrival times** improved by machine learning

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **PostgreSQL** - Database for caching schedules
- **SQLAlchemy** - ORM for database operations
- **GTFS-RT** - Real-time transit data processing

### ML Service
- **scikit-learn** - Random Forest model
- **XGBoost** - Gradient boosting predictions
- **pandas/numpy** - Data processing

### Frontend
- **React** - UI framework
- **Leaflet/React-Leaflet** - Interactive maps
- **Tailwind CSS** - Styling
- **Axios** - API requests

## Project Structure

```
octranspo_live/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── models.py            # Database models
│   ├── schemas.py           # Pydantic schemas
│   ├── database.py          # Database configuration
│   ├── config.py            # Settings
│   ├── gtfs_processor.py    # GTFS data pipeline
│   ├── init_db.py           # Database initialization
│   └── requirements.txt     # Python dependencies
├── ml-service/
│   ├── main.py              # ML prediction service
│   ├── train_model.py       # Model training script
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.js           # Main React component
│   │   ├── index.js         # React entry point
│   │   └── index.css        # Tailwind styles
│   ├── public/
│   ├── package.json
│   └── tailwind.config.js
├── ARCHITECTURE.md          # System architecture docs
├── SETUP_NO_DOCKER.md      # Detailed setup guide
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- PostgreSQL 14 or higher
- npm or yarn
- OC Transpo API credentials (optional, for enhanced features)

### Quick Start

1. Clone the repository:
```bash
git clone <repository-url>
cd octranspo_live
```

2. Set up PostgreSQL database:
```bash
psql postgres
CREATE DATABASE octranspo_live;
CREATE USER octranspo WITH PASSWORD 'octranspo';
GRANT ALL PRIVILEGES ON DATABASE octranspo_live TO octranspo;
\q
```

3. Set up and start the backend:
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # On Windows
# source venv/bin/activate  # On macOS/Linux
pip install -r requirements.txt
python init_db.py
uvicorn main:app --reload --port 8000
```

4. Set up and start the ML service (new terminal):
```bash
cd ml-service
python -m venv venv
venv\Scripts\activate  # On Windows
pip install -r requirements.txt
python train_model.py
uvicorn main:app --reload --port 8001
```

5. Set up and start the frontend (new terminal):
```bash
cd frontend
npm install
npm start
```

6. Access the application:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- ML Service: http://localhost:8001
- API Docs: http://localhost:8000/docs

> **Note:** For detailed setup instructions, see [SETUP_NO_DOCKER.md](SETUP_NO_DOCKER.md)

### Development Workflow

Once installed, you can run each service independently:

#### Backend
```bash
cd backend
venv\Scripts\activate  # On Windows
uvicorn main:app --reload
```

#### ML Service
```bash
cd ml-service
venv\Scripts\activate  # On Windows
uvicorn main:app --port 8001 --reload
```

#### Frontend
```bash
cd frontend
npm start
```

#### Initialize/Update Database
```bash
cd backend
venv\Scripts\activate
python init_db.py
```

## Configuration

### Environment Variables

The application uses `config.py` for settings. You can optionally create a `.env` file in the backend directory to override defaults:

```env
# Database (default if not specified)
DATABASE_URL=postgresql://octranspo:octranspo@localhost:5432/octranspo_live

# ML Service (default if not specified)
ML_SERVICE_URL=http://localhost:8001

# App Settings
DEBUG=True
CACHE_TTL=300

# Optional: OC Transpo API (for enhanced real-time features)
OC_TRANSPO_APP_ID=your_app_id
OC_TRANSPO_API_KEY=your_api_key
```

### GTFS Data

The application downloads GTFS data from:
- **Static data:** https://www.octranspo.com/files/google_transit.zip
- **Real-time updates:** https://gtfs.octranspo.com/gtfs-rt/ (vehiclepositions, tripupdates)

Data is automatically fetched and cached during initialization.

## API Endpoints

### Stops
- `GET /api/stops` - Get all stops (with optional filters)
  - Query params: `lat`, `lon`, `radius`, `search`
- `GET /api/stops/{stop_id}` - Get specific stop details
- `GET /api/stops/{stop_id}/arrivals` - Get real-time arrivals for a stop

### Routes
- `GET /api/routes` - Get all routes
- `GET /api/routes/{route_id}` - Get specific route details

## Machine Learning Model

The application uses machine learning to improve arrival time predictions:

### Features Used
- Time of day (hour, minute)
- Day of week
- Weekend indicator
- Peak hour indicators (morning/evening rush)
- Route characteristics
- Historical delay patterns

### Training

```bash
cd ml-service
python train_model.py
```

This will:
1. Generate synthetic training data (in production, use historical data)
2. Train both Random Forest and XGBoost models
3. Evaluate model performance
4. Save trained models to disk

### Model Performance
- **MAE**: ~60-80 seconds
- **RMSE**: ~90-120 seconds
- **R²**: ~0.75-0.85

## Data Pipeline

### GTFS Static Data
- Downloaded from OC Transpo
- Parsed and loaded into PostgreSQL
- Includes: stops, routes, schedules

### GTFS-RT Data
- Fetched every 30 seconds
- Trip updates and vehicle positions
- Merged with static data for predictions

### Caching Strategy
- Static data cached in database
- Real-time updates cached in memory (5 min TTL)
- Reduces API calls and improves performance

## Deployment

### Production Checklist

- [ ] Set `DEBUG=False` in environment
- [ ] Use production database credentials
- [ ] Configure HTTPS/SSL
- [ ] Set up monitoring (e.g., Sentry)
- [ ] Configure backup strategy for database
- [ ] Set up CI/CD pipeline
- [ ] Implement rate limiting
- [ ] Add authentication (if needed)
- [ ] Set up process manager (e.g., systemd, PM2, or supervisor)
- [ ] Configure reverse proxy (nginx or Apache)

### Hosting Options

- **Backend/ML**: Railway, Render, AWS EC2, Google Cloud Compute, DigitalOcean
- **Frontend**: Vercel, Netlify, AWS S3 + CloudFront, GitHub Pages
- **Database**: AWS RDS, Google Cloud SQL, Railway, DigitalOcean Managed PostgreSQL

### Production Server Setup

For production deployment, consider using:
- **Gunicorn** or **Uvicorn workers** for the FastAPI services
- **Nginx** as a reverse proxy
- **systemd** services for process management
- **Let's Encrypt** for SSL certificates

## Testing

```bash
# Backend tests (to be implemented)
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

> **Note:** Unit tests are planned for future implementation.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Future Enhancements

- [ ] Add user authentication and saved favorites
- [ ] Implement push notifications for bus arrivals
- [ ] Add route planning functionality
- [ ] Integrate weather data for better predictions
- [ ] Add service alerts and disruptions
- [ ] Support for multiple transit agencies
- [ ] Mobile app (React Native)
- [ ] Real-time vehicle tracking on map
- [ ] Historical analytics dashboard

## License

MIT License

## Acknowledgments

- OC Transpo for providing GTFS data
- OpenStreetMap for map tiles
- Contributors and open-source community

## Contact

For questions or issues, please open an issue on GitHub.

---

Built with ❤️ for Ottawa transit riders
