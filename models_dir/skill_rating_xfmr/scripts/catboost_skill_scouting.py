"""
CatBoost playtype model with structured HS recruit features, scouting report
embeddings, scouting evaluator features, and numerical skill ratings.
"""

import json
import os
from pathlib import Path

os.environ["USE_TF"] = "0"
os.environ["TRANSFORMERS_NO_TF"] = "1"

import duckdb
import numpy as np
import optuna
import pandas as pd
from catboost import CatBoostClassifier, Pool
from sentence_transformers import SentenceTransformer
from sklearn.metrics import log_loss


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = Path(__file__).resolve().parents[1]

DB_PATH = PROJECT_ROOT / "data_dir" / "hs_bv_matched.db"
ARTIFACT_DIR = MODEL_DIR / "artifacts"
TARGET_COL = "bv_role"

BASE_FEATURE_COLS = [
    "hs_year",
    "hs_position",
    "hs_height_in",
    "hs_weight",
    "hs_stars",
    "hs_rating",
    "hs_national_rank",
    "hs_position_rank",
]
SCOUTING_REPORT_COL = "scouting_report"
EVALUATOR_COL = "scouting_report_evaluator_name"
SCOUTING_FLAG_COL = "has_scouting_report_text"
EVALUATOR_FLAG_COL = "has_scouting_report_evaluator"
SKILL_FLAG_COL = "has_skill_ratings_available"
SKILL_FEATURE_COLS = [
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
CAT_FEATURES = ["hs_position", EVALUATOR_COL]

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
N_TRIALS = 50


def load_training_df() -> pd.DataFrame:
    skill_select = ",\n                ".join(
        f"hs_{col} AS {col}" for col in SKILL_FEATURE_COLS
    )
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.execute(
            f"""
            SELECT
                hs_year,
                hs_player_key AS player_key,
                hs_full_name AS full_name,
                hs_position,
                hs_height_in,
                hs_weight,
                hs_stars,
                hs_rating,
                hs_national_rank,
                hs_position_rank,
                hs_scouting_report AS scouting_report,
                hs_scouting_report_evaluator_name AS scouting_report_evaluator_name,
                hs_skill_rating AS skill_rating,
                {skill_select},
                {TARGET_COL}
            FROM hs_bv_matched
            WHERE {TARGET_COL} IS NOT NULL
            """
        ).fetchdf()
    finally:
        con.close()


def add_text_and_skill_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df[SCOUTING_FLAG_COL] = (
        df[SCOUTING_REPORT_COL].notna()
        & df[SCOUTING_REPORT_COL].astype(str).str.strip().ne("")
    )
    df[EVALUATOR_FLAG_COL] = (
        df[EVALUATOR_COL].notna()
        & df[EVALUATOR_COL].astype(str).str.strip().ne("")
    )
    df[EVALUATOR_COL] = df[EVALUATOR_COL].where(df[EVALUATOR_FLAG_COL], "__missing__")
    df[SKILL_FLAG_COL] = df["skill_rating"].fillna(False).astype(bool) | df[SKILL_FEATURE_COLS].notna().any(axis=1)
    df["hs_position"] = df["hs_position"].fillna("__missing__")
    df["_embedding_cache_key"] = df["player_key"].astype(str) + "_" + df["hs_year"].astype(str)
    return df


def add_embeddings(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], Path]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    safe_model_name = EMBEDDING_MODEL_NAME.replace("/", "__")
    embedding_cache_path = ARTIFACT_DIR / f"scouting_embeddings_{safe_model_name}.parquet"
    embedding_cols = [f"scout_emb_{i}" for i in range(EMBEDDING_DIM)]

    if embedding_cache_path.exists():
        print("Loading cached embeddings:", embedding_cache_path, flush=True)
        emb_df = pd.read_parquet(embedding_cache_path)
        merged = df.merge(emb_df, on="_embedding_cache_key", how="left", validate="one_to_one")
        if not merged[embedding_cols].isna().any(axis=1).any():
            return merged, embedding_cols, embedding_cache_path
        print("Cache missing rows. Recomputing full embedding cache.", flush=True)
        embedding_cache_path.unlink()

    print("Generating scouting report embeddings on CPU...", flush=True)
    model = SentenceTransformer(EMBEDDING_MODEL_NAME, device="cpu")
    embedding_matrix = np.zeros((len(df), EMBEDDING_DIM), dtype=np.float32)
    mask = df[SCOUTING_FLAG_COL].to_numpy()
    texts = df.loc[mask, SCOUTING_REPORT_COL].astype(str).tolist()
    if texts:
        encoded = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=False,
        )
        embedding_matrix[mask] = encoded.astype(np.float32)

    emb_df = pd.DataFrame(embedding_matrix, columns=embedding_cols)
    emb_df["_embedding_cache_key"] = df["_embedding_cache_key"].values
    emb_df.to_parquet(embedding_cache_path, index=False)
    print("Saved embedding cache:", embedding_cache_path, flush=True)
    df = pd.concat([df.reset_index(drop=True), emb_df[embedding_cols].reset_index(drop=True)], axis=1)
    return df, embedding_cols, embedding_cache_path


def main() -> None:
    df = add_text_and_skill_features(load_training_df())
    print("Rows with label:", len(df), flush=True)
    df, embedding_cols, embedding_cache_path = add_embeddings(df)

    feature_cols = (
        BASE_FEATURE_COLS
        + [SCOUTING_FLAG_COL, EVALUATOR_COL, EVALUATOR_FLAG_COL]
        + embedding_cols
        + [SKILL_FLAG_COL]
        + SKILL_FEATURE_COLS
    )

    train_df = df[(df["hs_year"] >= 2009) & (df["hs_year"] < 2022)].copy()
    valid_df = df[(df["hs_year"] >= 2022) & (df["hs_year"] <= 2023)].copy()
    test_df = df[(df["hs_year"] >= 2024) & (df["hs_year"] <= 2025)].copy()

    train_classes = set(train_df[TARGET_COL].dropna().unique())
    valid_df = valid_df[valid_df[TARGET_COL].isin(train_classes)].copy()
    test_df = test_df[test_df[TARGET_COL].isin(train_classes)].copy()

    X_train = train_df[feature_cols]
    y_train = train_df[TARGET_COL]
    X_valid = valid_df[feature_cols]
    y_valid = valid_df[TARGET_COL]
    X_test = test_df[feature_cols]
    y_test = test_df[TARGET_COL]

    train_pool = Pool(X_train, y_train, cat_features=CAT_FEATURES)
    valid_pool = Pool(X_valid, y_valid, cat_features=CAT_FEATURES)

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
        return log_loss(y_valid, valid_probs, labels=model.classes_)

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=N_TRIALS)

    print("Best score:", study.best_value, flush=True)
    print("Best params:", flush=True)
    print(study.best_params, flush=True)

    final_params = {
        **study.best_params,
        "loss_function": "MultiClass",
        "eval_metric": "MultiClass",
        "random_seed": 42,
        "verbose": False,
        "allow_writing_files": False,
    }
    train_valid_df = pd.concat([train_df, valid_df], ignore_index=True)
    train_valid_pool = Pool(
        train_valid_df[feature_cols],
        train_valid_df[TARGET_COL],
        cat_features=CAT_FEATURES,
    )
    final_model = CatBoostClassifier(**final_params)
    final_model.fit(train_valid_pool, verbose=False)

    test_loss = None
    if not test_df.empty:
        test_probs = final_model.predict_proba(X_test)
        test_loss = log_loss(y_test, test_probs, labels=final_model.classes_)
        print("Test score:", test_loss, flush=True)
    else:
        print("Test score: skipped because test_df is empty", flush=True)

    model_path = ARTIFACT_DIR / "catboost_playtype_with_scouting_embeddings_and_skills.cbm"
    metadata_path = ARTIFACT_DIR / "catboost_playtype_with_scouting_embeddings_and_skills_metadata.json"
    final_model.save_model(model_path)

    metadata = {
        "target_col": TARGET_COL,
        "base_feature_cols": BASE_FEATURE_COLS,
        "embedding_cols": embedding_cols,
        "skill_feature_cols": SKILL_FEATURE_COLS,
        "feature_cols": feature_cols,
        "cat_features": CAT_FEATURES,
        "scouting_report_col": SCOUTING_REPORT_COL,
        "scouting_flag_col": SCOUTING_FLAG_COL,
        "evaluator_col": EVALUATOR_COL,
        "evaluator_flag_col": EVALUATOR_FLAG_COL,
        "skill_flag_col": SKILL_FLAG_COL,
        "embedding_model_name": EMBEDDING_MODEL_NAME,
        "embedding_dim": EMBEDDING_DIM,
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
    metadata_path.write_text(json.dumps(metadata, indent=2))

    print("Saved model:", model_path, flush=True)
    print("Saved metadata:", metadata_path, flush=True)


if __name__ == "__main__":
    main()
