# OC Transpo Live - Project Architecture

## System Overview

```
┌─────────────┐
│   Browser   │
│  (React)    │
└──────┬──────┘
       │ HTTP/WebSocket
       ↓
┌─────────────────────────────────────┐
│     Frontend (React + Leaflet)      │
│  - Interactive map                  │
│  - Stop search                      │
│  - Real-time arrivals display       │
└──────────────┬──────────────────────┘
               │ REST API
               ↓
┌─────────────────────────────────────┐
│       Backend (FastAPI)             │
│  - RESTful endpoints                │
│  - GTFS-RT data ingestion          │
│  - Schedule caching                 │
│  - Data processing pipeline         │
└──────┬──────────────┬───────────────┘
       │              │
       │              └─────────┐
       ↓                        ↓
┌─────────────┐      ┌──────────────────┐
│ PostgreSQL  │      │   ML Service     │
│             │      │  (FastAPI)       │
│ - Stops     │      │  - Random Forest │
│ - Routes    │      │  - XGBoost       │
│ - Schedules │      │  - Predictions   │
│ - Cache     │      └──────────────────┘
└─────────────┘
       ↑
       │
┌─────────────┐
│  GTFS Data  │
│  - Static   │
│  - Real-time│
└─────────────┘
```

## Component Details

### Frontend Architecture

**Technology Stack:**
- React 18 for UI components
- Leaflet for map rendering
- Tailwind CSS for styling
- Axios for HTTP requests

**Key Features:**
1. **Interactive Map**
   - OpenStreetMap tiles
   - Custom markers for stops
   - Real-time position updates
   - Clustering for performance

2. **Search System**
   - Autocomplete for stop names
   - Code-based search
   - Location-based filtering
   - Debounced input

3. **Arrival Display**
   - Real-time countdown
   - Route information
   - Confidence indicators
   - Refresh mechanism

### Backend Architecture

**Technology Stack:**
- FastAPI for async API
- SQLAlchemy ORM
- PostgreSQL database
- GTFS-RT bindings

**Data Flow:**

1. **GTFS Static Data**
   ```
   Download → Parse → Transform → Store in DB
   ```

2. **GTFS-RT Data**
   ```
   Fetch (30s interval) → Parse → Merge with static → Cache → Serve
   ```

3. **Prediction Pipeline**
   ```
   Request → Query DB → Fetch RT → ML Enhancement → Response
   ```

**API Design:**

```
/api/stops
  GET  - List stops (with filters)
  
/api/stops/{id}
  GET  - Get stop details
  
/api/stops/{id}/arrivals
  GET  - Get predictions
  
/api/routes
  GET  - List routes
  
/api/routes/{id}
  GET  - Get route details
```

### ML Service Architecture

**Model Pipeline:**

1. **Feature Engineering**
   ```python
   Raw Data → Features → Model → Predictions
   ```

2. **Features Used:**
   - Temporal: hour, minute, day_of_week, month
   - Categorical: route_id, stop_id, direction
   - Contextual: is_peak_hour, is_weekend
   - Historical: avg_delay_route, avg_delay_stop

3. **Model Types:**
   - **Random Forest**: Better for interpretability
   - **XGBoost**: Better for accuracy

4. **Training Process:**
   ```
   Historical Data → Feature Extraction → Train/Test Split
   → Model Training → Validation → Deployment
   ```

### Database Schema

```sql
-- Stops table
CREATE TABLE stops (
    id SERIAL PRIMARY KEY,
    stop_id VARCHAR UNIQUE NOT NULL,
    code VARCHAR,
    name VARCHAR NOT NULL,
    lat FLOAT NOT NULL,
    lon FLOAT NOT NULL,
    INDEX idx_stop_id (stop_id),
    INDEX idx_location (lat, lon)
);

-- Routes table
CREATE TABLE routes (
    id SERIAL PRIMARY KEY,
    route_id VARCHAR UNIQUE NOT NULL,
    short_name VARCHAR,
    long_name VARCHAR,
    route_type INTEGER,
    color VARCHAR,
    INDEX idx_route_id (route_id)
);

-- Schedules table
CREATE TABLE schedules (
    id SERIAL PRIMARY KEY,
    stop_id VARCHAR REFERENCES stops(stop_id),
    route_id VARCHAR REFERENCES routes(route_id),
    trip_id VARCHAR NOT NULL,
    arrival_time VARCHAR,
    departure_time VARCHAR,
    stop_sequence INTEGER,
    INDEX idx_stop_route (stop_id, route_id)
);

-- Predictions table
CREATE TABLE predictions (
    id SERIAL PRIMARY KEY,
    stop_id VARCHAR REFERENCES stops(stop_id),
    route_id VARCHAR REFERENCES routes(route_id),
    trip_id VARCHAR,
    arrival_time TIMESTAMP,
    predicted_arrival TIMESTAMP,
    delay_seconds INTEGER,
    confidence FLOAT,
    timestamp TIMESTAMP DEFAULT NOW(),
    INDEX idx_timestamp (timestamp)
);
```

## Performance Considerations

### Caching Strategy

1. **Static Data**: Stored in PostgreSQL, refreshed daily
2. **Real-time Data**: Cached in memory for 30 seconds
3. **Predictions**: Cached for 1 minute per stop

### Optimization Techniques

1. **Database**
   - Indexes on frequently queried columns
   - Connection pooling
   - Query optimization

2. **API**
   - Async operations
   - Response compression
   - Rate limiting

3. **Frontend**
   - Lazy loading
   - Component memoization
   - Virtual scrolling for long lists
   - Map marker clustering

## Scalability

### Horizontal Scaling

- **Backend**: Stateless design allows multiple instances
- **Frontend**: CDN distribution
- **Database**: Read replicas for queries
- **ML Service**: Multiple instances with load balancing

### Vertical Scaling

- Optimize database queries
- Increase cache size
- Upgrade server resources

## Security

### API Security
- CORS configuration
- Rate limiting
- Input validation
- SQL injection prevention (SQLAlchemy)

### Data Security
- Database encryption at rest
- HTTPS in production
- Environment variable protection
- No sensitive data in logs

## Monitoring & Observability

### Metrics to Track
- API response times
- Database query performance
- ML prediction accuracy
- Error rates
- Cache hit rates

### Logging
- Structured logging (JSON)
- Log levels (DEBUG, INFO, WARNING, ERROR)
- Request/response logging
- Error stack traces

### Alerting
- High error rates
- Slow response times
- Database connection issues
- ML model degradation

## Future Enhancements

### Phase 1 (MVP) ✅
- Basic stop search
- Real-time arrivals
- Map integration
- ML predictions

### Phase 2
- User accounts
- Favorite stops
- Push notifications
- Route planning

### Phase 3
- Multi-agency support
- Historical analytics
- Mobile app
- Service alerts

### Phase 4
- Crowdsourced data
- Real-time vehicle tracking
- Advanced ML models
- Predictive analytics

## Development Workflow

```
Feature Branch → Local Testing → PR → Review → Merge
→ CI Tests → Build → Deploy to Staging → Integration Tests
→ Deploy to Production → Monitor
```

## Deployment Architecture

### Development
```
Docker Compose on local machine
```

### Staging
```
Docker Compose on cloud VM
```

### Production
```
Kubernetes cluster:
- Backend pods (3 replicas)
- ML service pods (2 replicas)
- Frontend (Vercel/Netlify)
- Database (managed service)
- Redis cache
- Load balancer
```

## Technology Choices Rationale

### Why FastAPI?
- Modern async support
- Automatic API documentation
- Type hints and validation
- High performance

### Why PostgreSQL?
- Robust and reliable
- Excellent geospatial support (PostGIS)
- ACID compliance
- Strong ecosystem

### Why React?
- Component-based architecture
- Large ecosystem
- Great developer experience
- Performance optimizations

### Why Random Forest/XGBoost?
- Handle non-linear relationships
- Feature importance insights
- Robust to outliers
- Good performance with limited data

## Contributing Guidelines

1. Fork the repository
2. Create a feature branch
3. Write tests
4. Ensure all tests pass
5. Update documentation
6. Submit pull request

## License

MIT License - See LICENSE file for details
