import optuna
import pandas as pd
import duckdb
import json
from pathlib import Path

from catboost import CatBoostClassifier, Pool
from sklearn.metrics import log_loss

# TODO: query db with hs matched data

# Path to hs matched db file
path = "/Users/anirudhhaharsha/Desktop/sports_analytics_projects/Basketball/College Basketball Project/uiuc_proj/data_dir/hs_bv_matched.db"  # change this

con = duckdb.connect(path)

table_name = Path(path).stem

# Fetch column where bv_role is labelled
df = con.execute(f"""
SELECT *
FROM {table_name}
WHERE bv_role IS NOT NULL
""").fetchdf()

print(len(df))

target_col = "bv_role"

feature_cols = [
    "hs_position",
    "hs_height_in",
    "hs_weight",
    "hs_stars",
    "hs_rating",
    "hs_national_rank",
    "hs_position_rank",
]

cat_features = ['hs_position']

# Train and val on older recruiting years, test on most recent years
train_df = df[(df["hs_year"] >= 2010) & (df["hs_year"] < 2022)].copy()
valid_df = df[(df["hs_year"] >= 2022) & (df["hs_year"] <= 2023)].copy()
test_df = df[(df["hs_year"] >= 2024) & (df["hs_year"] <= 2025)].copy()

X_train = train_df[feature_cols]
y_train = train_df[target_col]

X_valid = valid_df[feature_cols]
y_valid = valid_df[target_col]

X_test = test_df[feature_cols]
y_test = test_df[target_col]

train_pool = Pool(X_train, y_train, cat_features=cat_features)
valid_pool = Pool(X_valid, y_valid, cat_features=cat_features)

def objective(trial):
    params = {
        "loss_function": "MultiClass",
        "eval_metric": "MultiClass",
        "iterations": trial.suggest_int("iterations", 500, 2500),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
        "depth": trial.suggest_int("depth", 4, 8),
        "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 15.0, log=True),
        "bagging_temperature": trial.suggest_float("bagging_temperature", 0.0, 1.0),
        "random_seed": 42,
        "verbose": False,
        "allow_writing_files": False,
    }

    model = CatBoostClassifier(**params)

    model.fit(
        train_pool,
        eval_set=valid_pool,
        early_stopping_rounds=100,
        verbose=False
    )

    valid_probs = model.predict_proba(X_valid)

    loss = log_loss(
        y_valid,
        valid_probs,
        labels=model.classes_
    )

    return loss


study = optuna.create_study(direction="minimize")
study.optimize(objective, n_trials=50)

print("Best score:", study.best_value)
print("Best params:")
print(study.best_params)

final_params = {
    **study.best_params,
    "loss_function": "MultiClass",
    "eval_metric": "MultiClass",
    "random_seed": 42,
    "verbose": False,
    "allow_writing_files": False,
}

train_valid_df = pd.concat([train_df, valid_df], ignore_index=True)
X_train_valid = train_valid_df[feature_cols]
y_train_valid = train_valid_df[target_col]
train_valid_pool = Pool(X_train_valid, y_train_valid, cat_features=cat_features)

final_model = CatBoostClassifier(**final_params)
final_model.fit(train_valid_pool, verbose=False)

test_loss = None
if not test_df.empty:
    test_probs = final_model.predict_proba(X_test)
    test_loss = log_loss(
        y_test,
        test_probs,
        labels=final_model.classes_
    )
    print("Test score:", test_loss)
else:
    print("Test score: skipped because test_df is empty")

artifact_dir = Path(__file__).resolve().parent / "artifacts_remove_year"
artifact_dir.mkdir(parents=True, exist_ok=True)

model_path = artifact_dir / "catboost_baseline_playtype_model.cbm"
metadata_path = artifact_dir / "catboost_baseline_playtype_metadata.json"

final_model.save_model(model_path)

metadata = {
    "target_col": target_col,
    "feature_cols": feature_cols,
    "cat_features": cat_features,
    "class_order": [str(class_name) for class_name in final_model.classes_],
    "best_valid_log_loss": float(study.best_value),
    "test_log_loss": None if test_loss is None else float(test_loss),
    "best_params": study.best_params,
    "final_params": final_params,
    "train_hs_year_range": [int(train_df["hs_year"].min()), int(train_df["hs_year"].max())],
    "valid_hs_year_range": [int(valid_df["hs_year"].min()), int(valid_df["hs_year"].max())],
    "test_hs_year_range": None if test_df.empty else [int(test_df["hs_year"].min()), int(test_df["hs_year"].max())],
    "train_rows": int(len(train_df)),
    "valid_rows": int(len(valid_df)),
    "test_rows": int(len(test_df)),
}

with metadata_path.open("w") as f:
    json.dump(metadata, f, indent=2)

print("Saved model:", model_path)
print("Saved metadata:", metadata_path)
