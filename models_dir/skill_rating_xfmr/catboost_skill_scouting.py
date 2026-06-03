"""
CatBoost playtype model with:
- baseline HS recruit features
- scouting report embeddings
- numerical skill-rating features

Install dependencies:
    pip install pandas duckdb catboost optuna sentence-transformers scikit-learn numpy

Notes:
- Uses the same DuckDB query/target/split as the baseline model.
- Uses sentence-transformers/all-MiniLM-L6-v2 on CPU by default.
- Missing scouting reports are represented by a zero embedding vector.
- Adds has_scouting_report_text flag.
- Adds has_skill_ratings_available flag.
- CatBoost can handle NaN numerical skill ratings directly.
"""

import json
from pathlib import Path

import duckdb
import numpy as np
import optuna
import pandas as pd

from catboost import CatBoostClassifier, Pool
from sentence_transformers import SentenceTransformer
from sklearn.metrics import log_loss


# -------------------------
# Config
# -------------------------
path = "/Users/anirudhhaharsha/Desktop/sports_analytics_projects/Basketball/College Basketball Project/uiuc_proj/data_dir/hs_bv_matched.db"

target_col = "bv_role"

base_feature_cols = [
    "hs_year",
    "hs_position",
    "hs_height_in",
    "hs_weight",
    "hs_stars",
    "hs_rating",
    "hs_national_rank",
    "hs_position_rank",
]

cat_features = ["hs_position"]

scouting_report_col = "scouting_report"

# Adjust these names if your joined DB prefixes them differently.
skill_feature_cols = [
    "skill_athleticism",
    "skill_defender",
    "skill_face_up_high_post_scorer",
    "skill_handle",
    "skill_leadership",
    "skill_low_post_scorer",
    "skill_passing",
    "skill_passing_vision",
    "skill_penetration_ability",
    "skill_physicality_motor",
    "skill_rebounding",
    "skill_shooter",
    "skill_size",
    "skill_versatility",
]

# This is the flag you can edit later if your true availability logic differs.
skill_flag_col = "has_skill_ratings_available"

embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
embedding_dim = 384

# Tune this if needed.
n_trials = 50


# -------------------------
# Load data
# -------------------------
con = duckdb.connect(path)
table_name = Path(path).stem

df = con.execute(f"""
SELECT *
FROM {table_name}
WHERE {target_col} IS NOT NULL
""").fetchdf()

print("Rows with label:", len(df))


# -------------------------
# Validate expected columns
# -------------------------
required_cols = set(base_feature_cols + [target_col, scouting_report_col])
missing_required_cols = sorted(required_cols - set(df.columns))
if missing_required_cols:
    raise ValueError(f"Missing required columns from database: {missing_required_cols}")

missing_skill_cols = sorted(set(skill_feature_cols) - set(df.columns))
if missing_skill_cols:
    raise ValueError(
        "Missing skill columns from database. "
        "Edit skill_feature_cols to match your actual DB column names. "
        f"Missing: {missing_skill_cols}"
    )


# -------------------------
# Feature engineering
# -------------------------
# You can change this logic later if your report availability flag should be based on another column.
df["has_scouting_report_text"] = (
    df[scouting_report_col].notna()
    & df[scouting_report_col].astype(str).str.strip().ne("")
)

# You said you will fill in the real meaning later.
# Current placeholder logic:
# True if at least one numerical skill column is non-null.
df[skill_flag_col] = df[skill_feature_cols].notna().any(axis=1)

# Convert skill flags to bool. Skill columns stay numeric and can contain NaN.
df[skill_flag_col] = df[skill_flag_col].astype(bool)

# Stable row id for caching. If player_key exists and is unique enough, use it.
# Otherwise fall back to index.
if "player_key" in df.columns:
    df["_embedding_cache_key"] = df["player_key"].astype(str) + "_" + df["hs_year"].astype(str)
elif "hs_player_key" in df.columns:
    df["_embedding_cache_key"] = df["hs_player_key"].astype(str) + "_" + df["hs_year"].astype(str)
else:
    df["_embedding_cache_key"] = df.index.astype(str)


# -------------------------
# Embedding generation / caching
# -------------------------
artifact_dir = Path(__file__).resolve().parent / "artifacts"
artifact_dir.mkdir(parents=True, exist_ok=True)

safe_model_name = embedding_model_name.replace("/", "__")
embedding_cache_path = artifact_dir / f"scouting_embeddings_{safe_model_name}.parquet"

if embedding_cache_path.exists():
    print("Loading cached embeddings:", embedding_cache_path)
    emb_df = pd.read_parquet(embedding_cache_path)

    df = df.merge(
        emb_df,
        on="_embedding_cache_key",
        how="left",
        validate="one_to_one",
    )

    embedding_cols = [f"scout_emb_{i}" for i in range(embedding_dim)]

    missing_embedding_rows = df[embedding_cols].isna().any(axis=1)
    if missing_embedding_rows.any():
        print("Cache missing rows. Recomputing full embedding cache.")
        embedding_cache_path.unlink()
        emb_df = None
    else:
        emb_df = df[["_embedding_cache_key"] + embedding_cols].copy()

else:
    emb_df = None


if emb_df is None:
    print("Generating scouting report embeddings on CPU...")
    model = SentenceTransformer(embedding_model_name, device="cpu")

    embedding_matrix = np.zeros((len(df), embedding_dim), dtype=np.float32)

    mask = df["has_scouting_report_text"].to_numpy()
    texts = df.loc[mask, scouting_report_col].astype(str).tolist()

    if len(texts) > 0:
        encoded = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=False,
        )
        embedding_matrix[mask] = encoded.astype(np.float32)

    embedding_cols = [f"scout_emb_{i}" for i in range(embedding_dim)]
    emb_df = pd.DataFrame(embedding_matrix, columns=embedding_cols)
    emb_df["_embedding_cache_key"] = df["_embedding_cache_key"].values

    emb_df.to_parquet(embedding_cache_path, index=False)
    print("Saved embedding cache:", embedding_cache_path)

    df = pd.concat([df.reset_index(drop=True), emb_df[embedding_cols].reset_index(drop=True)], axis=1)


embedding_cols = [f"scout_emb_{i}" for i in range(embedding_dim)]

feature_cols = (
    base_feature_cols
    + ["has_scouting_report_text"]
    + embedding_cols
    + [skill_flag_col]
    + skill_feature_cols
)


# -------------------------
# Split data by recruiting year
# -------------------------
train_df = df[(df["hs_year"] >= 2010) & (df["hs_year"] < 2022)].copy()
valid_df = df[(df["hs_year"] >= 2022) & (df["hs_year"] <= 2023)].copy()
test_df = df[(df["hs_year"] >= 2024) & (df["hs_year"] <= 2025)].copy()

# Optional safety: ensure validation/test labels appeared during training.
# If this prints dropped rows, inspect those classes later.
train_classes = set(train_df[target_col].dropna().unique())

before_valid = len(valid_df)
valid_df = valid_df[valid_df[target_col].isin(train_classes)].copy()
if len(valid_df) != before_valid:
    print(f"Dropped {before_valid - len(valid_df)} validation rows with labels unseen in training.")

before_test = len(test_df)
test_df = test_df[test_df[target_col].isin(train_classes)].copy()
if len(test_df) != before_test:
    print(f"Dropped {before_test - len(test_df)} test rows with labels unseen in training.")

X_train = train_df[feature_cols]
y_train = train_df[target_col]

X_valid = valid_df[feature_cols]
y_valid = valid_df[target_col]

X_test = test_df[feature_cols]
y_test = test_df[target_col]

train_pool = Pool(X_train, y_train, cat_features=cat_features)
valid_pool = Pool(X_valid, y_valid, cat_features=cat_features)


# -------------------------
# Optuna objective
# -------------------------
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
        verbose=False,
        use_best_model=True,
    )

    valid_probs = model.predict_proba(X_valid)

    loss = log_loss(
        y_valid,
        valid_probs,
        labels=model.classes_,
    )

    return loss


study = optuna.create_study(direction="minimize")
study.optimize(objective, n_trials=n_trials)

print("Best score:", study.best_value)
print("Best params:")
print(study.best_params)


# -------------------------
# Final model: train on train + validation, evaluate on test
# -------------------------
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
        labels=final_model.classes_,
    )
    print("Test score:", test_loss)
else:
    print("Test score: skipped because test_df is empty")


# -------------------------
# Save artifacts
# -------------------------
model_path = artifact_dir / "catboost_playtype_with_scouting_embeddings_and_skills.cbm"
metadata_path = artifact_dir / "catboost_playtype_with_scouting_embeddings_and_skills_metadata.json"

final_model.save_model(model_path)

metadata = {
    "target_col": target_col,
    "base_feature_cols": base_feature_cols,
    "embedding_cols": embedding_cols,
    "skill_feature_cols": skill_feature_cols,
    "feature_cols": feature_cols,
    "cat_features": cat_features,
    "scouting_report_col": scouting_report_col,
    "scouting_flag_col": "has_scouting_report_text",
    "skill_flag_col": skill_flag_col,
    "embedding_model_name": embedding_model_name,
    "embedding_dim": embedding_dim,
    "embedding_cache_path": str(embedding_cache_path),
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
