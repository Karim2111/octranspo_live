"""
train.py
────────
Trains an XGBoost delay-prediction model on the prepared parquet file.

Run:
    python train.py --data data/training.parquet --out models/delay_model.pkl

Outputs:
    models/delay_model.pkl   – sklearn Pipeline (preprocessor + XGBRegressor)
    models/eval.json         – MAE, RMSE, R² on held-out test set
"""

import argparse
import json
import os
import pickle
from typing import Tuple

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder
from xgboost import XGBRegressor

from features import CATEGORICAL_FEATURES, NUMERIC_FEATURES

TARGET = "label_delay_min"
DROP_COLS = ["target_stop_id", "trip_id", "ping_id", TARGET]


def load(path: str) -> Tuple[pd.DataFrame, pd.Series]:
    df = pd.read_parquet(path)
    print(f"Loaded {len(df):,} rows from {path}")

    # Drop rows where the label is null
    df = df.dropna(subset=[TARGET])
    print(f"  After dropping null labels: {len(df):,} rows")

    y = df[TARGET].astype(float)
    X = df.drop(columns=DROP_COLS, errors="ignore")
    return X, y


def build_pipeline() -> Pipeline:
    # Numeric features pass through as-is (XGBoost handles scale natively)
    # Categorical: OrdinalEncoder so XGBoost can use them directly
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", "passthrough", NUMERIC_FEATURES),
            (
                "cat",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                CATEGORICAL_FEATURES,
            ),
        ]
    )

    model = XGBRegressor(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        reg_alpha=0.1,
        reg_lambda=1.0,
        objective="reg:squarederror",
        n_jobs=-1,
        random_state=42,
        early_stopping_rounds=30,
        eval_metric="mae",
    )

    return Pipeline([("prep", preprocessor), ("model", model)])


def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2 = r2_score(y_true, y_pred)
    return {"mae_min": round(mae, 4), "rmse_min": round(rmse, 4), "r2": round(r2, 4)}


def main(data_path: str, out_path: str):
    X, y = load(data_path)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42
    )
    X_tr, X_val, y_tr, y_val = train_test_split(
        X_train, y_train, test_size=0.15, random_state=42
    )

    print(f"\nTrain: {len(X_tr):,}  Val: {len(X_val):,}  Test: {len(X_test):,}")

    pipeline = build_pipeline()

    # Preprocess val set for early stopping (XGBoost needs it pre-transformed)
    pipeline["prep"].fit(X_tr)
    X_tr_p = pipeline["prep"].transform(X_tr)
    X_val_p = pipeline["prep"].transform(X_val)

    print("\nFitting XGBoost…")
    pipeline["model"].fit(
        X_tr_p,
        y_tr,
        eval_set=[(X_val_p, y_val)],
        verbose=50,
    )

    # Wrap back into the full pipeline for inference
    # (prep is already fitted, model is fitted — pipeline is ready)
    X_test_p = pipeline["prep"].transform(X_test)
    y_pred = pipeline["model"].predict(X_test_p)

    metrics = evaluate(y_test.values, y_pred)
    print(f"\n── Test metrics ──")
    print(f"  MAE  : {metrics['mae_min']:.3f} min")
    print(f"  RMSE : {metrics['rmse_min']:.3f} min")
    print(f"  R²   : {metrics['r2']:.4f}")

    # Feature importance
    feat_names = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    importances = pipeline["model"].feature_importances_
    top = sorted(zip(feat_names, importances), key=lambda x: -x[1])[:10]
    print("\nTop features:")
    for name, imp in top:
        print(f"  {name:<30} {imp:.4f}")

    # Save
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        pickle.dump(pipeline, f)
    print(f"\nModel saved → {out_path}")

    eval_path = out_path.replace(".pkl", "_eval.json")
    with open(eval_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Eval   saved → {eval_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/training.parquet")
    parser.add_argument("--out", default="models/delay_model.pkl")
    args = parser.parse_args()
    main(args.data, args.out)
