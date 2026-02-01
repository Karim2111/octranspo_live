from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict
import numpy as np
from datetime import datetime
import pickle
import os

app = FastAPI(title="OC Transpo ML Prediction Service")

# Placeholder for trained model
# In production, you'd load a trained Random Forest or XGBoost model
class MLPredictor:
    def __init__(self):
        self.model = None
        self.load_model()
    
    def load_model(self):
        """Load pre-trained model or create a simple predictor"""
        # Check if model exists
        if os.path.exists('model.pkl'):
            with open('model.pkl', 'rb') as f:
                self.model = pickle.load(f)
        else:
            # For demo purposes, we'll use a simple heuristic
            self.model = None
    
    def predict_delay(self, features: Dict) -> Dict:
        """Predict delay based on features"""
        # Extract features
        hour = features.get('hour', 12)
        day_of_week = features.get('day_of_week', 0)
        route_id = features.get('route_id', '')
        current_delay = features.get('current_delay', 0)
        
        # Simple heuristic-based prediction (replace with actual ML model)
        # Peak hours tend to have more delays
        base_delay = current_delay
        
        # Add peak hour factor
        if 7 <= hour <= 9 or 16 <= hour <= 18:
            peak_factor = 1.2
        else:
            peak_factor = 1.0
        
        # Weather factor (random for demo - would use actual weather data)
        weather_factor = np.random.uniform(0.9, 1.1)
        
        predicted_delay = int(base_delay * peak_factor * weather_factor)
        
        # Confidence based on data availability
        confidence = 0.85 if current_delay > 0 else 0.65
        
        return {
            'predicted_delay': predicted_delay,
            'confidence': round(confidence, 2)
        }

predictor = MLPredictor()

class PredictionRequest(BaseModel):
    predictions: List[Dict]

class PredictionResponse(BaseModel):
    enhanced_predictions: List[Dict]

@app.get("/")
async def root():
    return {"message": "ML Prediction Service", "status": "running"}

@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    """Enhance predictions with ML model"""
    enhanced = []
    
    for pred in request.predictions:
        # Extract time features
        try:
            scheduled_time = datetime.fromisoformat(pred['scheduled_arrival'])
            hour = scheduled_time.hour
            day_of_week = scheduled_time.weekday()
        except:
            hour = 12
            day_of_week = 0
        
        # Create features dict
        features = {
            'hour': hour,
            'day_of_week': day_of_week,
            'route_id': pred.get('route_id', ''),
            'current_delay': pred.get('delay_seconds', 0)
        }
        
        # Get ML prediction
        ml_result = predictor.predict_delay(features)
        
        # Update prediction
        enhanced_pred = pred.copy()
        enhanced_pred['delay_seconds'] = ml_result['predicted_delay']
        enhanced_pred['confidence'] = ml_result['confidence']
        
        # Recalculate predicted arrival
        if 'scheduled_arrival' in pred:
            try:
                scheduled = datetime.fromisoformat(pred['scheduled_arrival'])
                from datetime import timedelta
                predicted = scheduled + timedelta(seconds=ml_result['predicted_delay'])
                enhanced_pred['predicted_arrival'] = predicted.isoformat()
                
                # Recalculate minutes until arrival
                now = datetime.now()
                minutes = int((predicted - now).total_seconds() / 60)
                enhanced_pred['minutes_until_arrival'] = max(0, minutes)
            except:
                pass
        
        enhanced.append(enhanced_pred)
    
    return PredictionResponse(enhanced_predictions=enhanced)

@app.post("/train")
async def train_model():
    """Endpoint to trigger model training with new data"""
    # In production, this would:
    # 1. Fetch historical data from database
    # 2. Extract features (time, weather, route, etc.)
    # 3. Train Random Forest or XGBoost model
    # 4. Evaluate and save model
    return {"status": "Model training initiated"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
