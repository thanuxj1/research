"""
Train the TF-IDF + RandomForest scam classifier.
Uses the auto-labeled training data from generate_training_data.py.
IT22629180
"""
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, confusion_matrix
import joblib
import os


def train_model():
    print("=" * 55)
    print("  Training Scam Classifier — IT22629180")
    print("=" * 55)

    # Load training data
    dataset_path = os.path.join(os.path.dirname(__file__), "dataset", "sample_data.csv")
    df = pd.read_csv(dataset_path, encoding="utf-8")
    print(f"\nDataset: {len(df)} rows")
    print(f"  Scam (1): {df['is_scam'].sum()}")
    print(f"  Safe (0): {(df['is_scam'] == 0).sum()}")

    X = df['text'].fillna("")
    y = df['is_scam']

    # 80/20 split with stratification
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\n  Train: {len(X_train)} | Test: {len(X_test)}")

    # Build pipeline
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(
            stop_words='english',
            max_features=3000,
            ngram_range=(1, 2),      # unigrams + bigrams
            min_df=2,
            max_df=0.95,
            sublinear_tf=True,
        )),
        ('clf', RandomForestClassifier(
            n_estimators=200,
            max_depth=20,
            min_samples_leaf=3,
            class_weight='balanced',  # handle imbalance
            random_state=42,
            n_jobs=-1,
        ))
    ])

    # Train
    print("\nTraining...")
    pipeline.fit(X_train, y_train)

    # Evaluate
    y_pred = pipeline.predict(X_test)
    print("\n--- Classification Report ---")
    print(classification_report(y_test, y_pred, target_names=["Safe", "Scam"]))

    print("--- Confusion Matrix ---")
    cm = confusion_matrix(y_test, y_pred)
    print(f"  TN={cm[0][0]}  FP={cm[0][1]}")
    print(f"  FN={cm[1][0]}  TP={cm[1][1]}")

    accuracy = (cm[0][0] + cm[1][1]) / cm.sum()
    print(f"\n  Accuracy: {accuracy:.1%}")

    # Save model
    model_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app", "ml", "models")
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "scam_classifier.joblib")

    joblib.dump(pipeline, model_path)
    print(f"\nModel saved: {model_path}")
    print(f"Model size: {os.path.getsize(model_path) / 1024:.0f} KB")
    print("=" * 55)


if __name__ == "__main__":
    train_model()
