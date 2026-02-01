import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import pickle
from datetime import datetime, timedelta

class ArrivalTimePredictor:
    """ML model for predicting bus arrival times"""
    
    def __init__(self, model_type='random_forest'):
        self.model_type = model_type
        self.model = None
        
    def create_features(self, df):
        """Create features from raw data"""
        # Time-based features
        df['hour'] = df['scheduled_time'].dt.hour
        df['minute'] = df['scheduled_time'].dt.minute
        df['day_of_week'] = df['scheduled_time'].dt.dayofweek
        df['month'] = df['scheduled_time'].dt.month
        df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
        
        # Peak hour features
        df['is_morning_peak'] = ((df['hour'] >= 7) & (df['hour'] <= 9)).astype(int)
        df['is_evening_peak'] = ((df['hour'] >= 16) & (df['hour'] <= 18)).astype(int)
        
        # Route features (one-hot encoding would be done for actual routes)
        df['route_encoded'] = df['route_id'].astype('category').cat.codes
        
        # Weather features (placeholder - would integrate with weather API)
        # df['temperature'] = ...
        # df['precipitation'] = ...
        # df['snow'] = ...
        
        # Historical delay features (would be calculated from database)
        # df['avg_delay_route'] = ...
        # df['avg_delay_stop'] = ...
        # df['avg_delay_hour'] = ...
        
        return df
    
    def prepare_training_data(self):
        """Generate synthetic training data for demonstration"""
        # In production, this would query the database for historical data
        np.random.seed(42)
        n_samples = 10000
        
        # Generate synthetic data
        data = {
            'scheduled_time': pd.date_range(start='2024-01-01', periods=n_samples, freq='15min'),
            'route_id': np.random.choice(['1', '2', '7', '95', '97'], n_samples),
            'stop_id': np.random.choice(['1000', '2000', '3000', '4000'], n_samples),
        }
        
        df = pd.DataFrame(data)
        df = self.create_features(df)
        
        # Generate target variable (actual delay in seconds)
        # Base delay
        delays = np.random.normal(60, 120, n_samples)
        
        # Add peak hour effects
        delays += df['is_morning_peak'] * np.random.normal(120, 60, n_samples)
        delays += df['is_evening_peak'] * np.random.normal(180, 80, n_samples)
        
        # Add day of week effects (weekends have less delay)
        delays -= df['is_weekend'] * np.random.normal(30, 20, n_samples)
        
        # Ensure non-negative delays
        delays = np.maximum(delays, 0)
        
        df['actual_delay_seconds'] = delays
        
        return df
    
    def train(self):
        """Train the ML model"""
        print("Preparing training data...")
        df = self.prepare_training_data()
        
        # Select features
        feature_cols = [
            'hour', 'minute', 'day_of_week', 'month', 
            'is_weekend', 'is_morning_peak', 'is_evening_peak',
            'route_encoded'
        ]
        
        X = df[feature_cols]
        y = df['actual_delay_seconds']
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        print(f"Training {self.model_type} model...")
        
        if self.model_type == 'random_forest':
            self.model = RandomForestRegressor(
                n_estimators=100,
                max_depth=15,
                min_samples_split=10,
                random_state=42,
                n_jobs=-1
            )
        elif self.model_type == 'xgboost':
            self.model = XGBRegressor(
                n_estimators=100,
                max_depth=10,
                learning_rate=0.1,
                random_state=42,
                n_jobs=-1
            )
        
        # Train model
        self.model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = self.model.predict(X_test)
        
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)
        
        print(f"\nModel Performance:")
        print(f"MAE: {mae:.2f} seconds")
        print(f"RMSE: {rmse:.2f} seconds")
        print(f"R²: {r2:.4f}")
        
        # Feature importance
        if hasattr(self.model, 'feature_importances_'):
            importance_df = pd.DataFrame({
                'feature': feature_cols,
                'importance': self.model.feature_importances_
            }).sort_values('importance', ascending=False)
            
            print("\nFeature Importance:")
            print(importance_df.to_string(index=False))
        
        return self.model
    
    def save_model(self, filepath='model.pkl'):
        """Save trained model to disk"""
        if self.model is None:
            raise ValueError("Model not trained yet")
        
        with open(filepath, 'wb') as f:
            pickle.dump(self.model, f)
        
        print(f"\nModel saved to {filepath}")
    
    def load_model(self, filepath='model.pkl'):
        """Load trained model from disk"""
        with open(filepath, 'rb') as f:
            self.model = pickle.load(f)
        
        print(f"Model loaded from {filepath}")

if __name__ == "__main__":
    # Train Random Forest model
    print("Training Random Forest model...")
    rf_predictor = ArrivalTimePredictor(model_type='random_forest')
    rf_predictor.train()
    rf_predictor.save_model('random_forest_model.pkl')
    
    print("\n" + "="*50 + "\n")
    
    # Train XGBoost model
    print("Training XGBoost model...")
    xgb_predictor = ArrivalTimePredictor(model_type='xgboost')
    xgb_predictor.train()
    xgb_predictor.save_model('xgboost_model.pkl')
