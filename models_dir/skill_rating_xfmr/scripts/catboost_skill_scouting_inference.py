import json
import os
from pathlib import Path

os.environ["USE_TF"] = "0"
os.environ["TRANSFORMERS_NO_TF"] = "1"

import duckdb
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = Path(__file__).resolve().parents[1]

DB_PATH = PROJECT_ROOT / "data_dir" / "hs_complete.db"
MODEL_PATH = MODEL_DIR / "artifacts" / "catboost_playtype_with_scouting_embeddings_and_skills.cbm"
METADATA_PATH = MODEL_DIR / "artifacts" / "catboost_playtype_with_scouting_embeddings_and_skills_metadata.json"
OUTPUT_DIR = MODEL_DIR / "outputs"
OUTPUT_PATH = OUTPUT_DIR / "catboost_skill_scouting_2026_top3_predictions.csv"


def load_inference_df() -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.execute(
            """
            SELECT
                year AS hs_year,
                player_key,
                full_name,
                signed_school,
                enrolled_institution_247,
                COALESCE(signed_school, enrolled_institution_247) AS signed_or_enrolled,
                position AS hs_position,
                height_in AS hs_height_in,
                weight AS hs_weight,
                stars AS hs_stars,
                rating AS hs_rating,
                national_rank AS hs_national_rank,
                position_rank AS hs_position_rank,
                scouting_report,
                scouting_report_evaluator_name,
                skill_rating,
                skill_athleticism,
                skill_defender,
                skill_face_up_high_post_scorer,
                skill_handle,
                skill_leadership,
                skill_low_post_scorer,
                skill_passing,
                skill_passing_vision,
                skill_penetration_ability,
                skill_physicality_motor,
                skill_rebounding,
                skill_shooter,
                skill_size,
                skill_versatility
            FROM hs_complete
            WHERE full_name IS NOT NULL
              AND year = 2026
            """
        ).fetchdf()
    finally:
        con.close()


def add_features(df: pd.DataFrame, metadata: dict) -> pd.DataFrame:
    df = df.copy()
    scouting_col = metadata["scouting_report_col"]
    evaluator_col = metadata["evaluator_col"]
    scouting_flag_col = metadata["scouting_flag_col"]
    evaluator_flag_col = metadata["evaluator_flag_col"]
    skill_flag_col = metadata["skill_flag_col"]
    skill_cols = metadata["skill_feature_cols"]
    embedding_cols = metadata["embedding_cols"]

    df[scouting_flag_col] = (
        df[scouting_col].notna()
        & df[scouting_col].astype(str).str.strip().ne("")
    )
    df[evaluator_flag_col] = (
        df[evaluator_col].notna()
        & df[evaluator_col].astype(str).str.strip().ne("")
    )
    df[evaluator_col] = df[evaluator_col].where(df[evaluator_flag_col], "__missing__")
    df[skill_flag_col] = df["skill_rating"].fillna(False).astype(bool) | df[skill_cols].notna().any(axis=1)
    df["hs_position"] = df["hs_position"].fillna("__missing__")

    model = SentenceTransformer(metadata["embedding_model_name"], device="cpu")
    embedding_dim = int(metadata["embedding_dim"])
    embedding_matrix = np.zeros((len(df), embedding_dim), dtype=np.float32)
    mask = df[scouting_flag_col].to_numpy()
    texts = df.loc[mask, scouting_col].astype(str).tolist()
    if texts:
        encoded = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=False,
        )
        embedding_matrix[mask] = encoded.astype(np.float32)

    for i, col in enumerate(embedding_cols):
        df[col] = embedding_matrix[:, i]
    return df


def add_top_predictions(df: pd.DataFrame, probs, class_order: list[str], skill_cols: list[str]) -> pd.DataFrame:
    prob_df = pd.DataFrame(probs, columns=[f"prob_{role}" for role in class_order], index=df.index)
    ranked = probs.argsort(axis=1)[:, ::-1][:, :3]
    top_df = pd.DataFrame(
        {
            "pred_role_1": [class_order[i] for i in ranked[:, 0]],
            "pred_prob_1": probs[df.index, ranked[:, 0]],
            "pred_role_2": [class_order[i] for i in ranked[:, 1]],
            "pred_prob_2": probs[df.index, ranked[:, 1]],
            "pred_role_3": [class_order[i] for i in ranked[:, 2]],
            "pred_prob_3": probs[df.index, ranked[:, 2]],
        },
        index=df.index,
    )
    id_cols = [
        "hs_year",
        "player_key",
        "full_name",
        "signed_or_enrolled",
        "signed_school",
        "enrolled_institution_247",
        "hs_position",
        "hs_height_in",
        "hs_weight",
        "hs_stars",
        "hs_rating",
        "hs_national_rank",
        "hs_position_rank",
        "has_scouting_report_text",
        "scouting_report_evaluator_name",
        "has_scouting_report_evaluator",
        "has_skill_ratings_available",
        *skill_cols,
    ]
    return pd.concat([df[id_cols], top_df, prob_df], axis=1)


def main() -> None:
    metadata = json.loads(METADATA_PATH.read_text())
    feature_cols = metadata["feature_cols"]
    class_order = metadata["class_order"]
    skill_cols = metadata["skill_feature_cols"]

    df = add_features(load_inference_df(), metadata)
    X = df[feature_cols]

    model = CatBoostClassifier()
    model.load_model(str(MODEL_PATH))
    model_class_order = [str(role) for role in model.classes_]
    if model_class_order != class_order:
        raise RuntimeError(
            f"Metadata class order {class_order} does not match model class order {model_class_order}"
        )

    probs = model.predict_proba(X)
    output = add_top_predictions(df, probs, class_order, skill_cols)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output.to_csv(OUTPUT_PATH, index=False)

    print(f"Rows scored: {len(output)}")
    print(f"Saved predictions: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
