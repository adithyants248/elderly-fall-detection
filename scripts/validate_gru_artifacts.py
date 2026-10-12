"""Reproduce Cell 6 without fitting a scaler or modifying reference artifacts.

Default is read-only validation. --reconstruct saves verified training medians
and provenance under models/fall_detection, only after reference arrays match.
"""
import argparse
import hashlib
import json
import random
import zipfile

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from src.core.fall_detection.model_schema import ArtifactPaths, FEATURE_NAMES, ROOT
from src.core.fall_detection.preprocessing import ModelPreprocessor, interpolate_sequence


def reconstruct_training_data(csv_path):
    df = pd.read_csv(csv_path)
    stats = df.groupby(["sequence_id", "label"]).agg(
        total_frames=("frame", "count"), detected_frames=("person_detected", "sum")
    ).reset_index()
    valid = stats.loc[stats.detected_frames / stats.total_frames >= 0.70, "sequence_id"]
    df = df[df.sequence_id.isin(valid)].copy()
    info = df[["sequence_id", "label"]].drop_duplicates()
    groups = []
    for label in (1, 0):
        ids = info.loc[info.label == label, "sequence_id"].tolist()
        train, temp = train_test_split(ids, test_size=0.30, random_state=42)
        val, test = train_test_split(temp, test_size=0.50, random_state=42)
        groups.append((train, val, test))
    rng = random.Random(42)
    splits = {}
    for i, name in enumerate(("train", "val", "test")):
        splits[name] = groups[0][i] + groups[1][i]
        rng.shuffle(splits[name])
    # Cell 6 interpolates in input row order, before the later frame sort.
    df["person_detected"] = df["person_detected"].astype(float)
    for _, group in df.groupby("sequence_id", sort=False):
        df.loc[group.index, list(FEATURE_NAMES)] = interpolate_sequence(group).to_numpy()
    medians = df.loc[df.sequence_id.isin(splits["train"]), list(FEATURE_NAMES)].median()
    return df, medians, splits


def validate(reconstruct=False):
    paths = ArtifactPaths()
    reference = ROOT / "colab_reference"
    df, medians, splits = reconstruct_training_data(reference / "UR_features_all.csv")
    scaler = joblib.load(paths.scaler)
    assert scaler.n_features_in_ == 20
    assert tuple(scaler.feature_names_in_) == FEATURE_NAMES
    train = df.loc[df.sequence_id.isin(splits["train"]), list(FEATURE_NAMES)].fillna(medians)
    np.testing.assert_allclose(train.mean().to_numpy(), scaler.mean_, rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(train.var(ddof=0).to_numpy(), scaler.var_, rtol=1e-10, atol=1e-10)
    assert int(scaler.n_samples_seen_) == len(train)
    # Validate through the production transform using reconstructed values in memory.
    preprocessor = ModelPreprocessor.__new__(ModelPreprocessor)
    preprocessor.scaler, preprocessor.medians = scaler, medians
    report = {}
    for split, count in (("train", 341), ("val", 64), ("test", 69)):
        windows, labels = [], []
        for sequence_id in splits[split]:
            seq = df[df.sequence_id == sequence_id].sort_values("frame")
            current = preprocessor.offline_windows(seq, interpolated=True)
            windows.extend(current)
            labels.extend([int(seq.label.iloc[0])] * len(current))
        actual = np.asarray(windows, dtype=np.float32)
        expected = np.load(reference / f"X_{split}.npy")
        assert actual.shape == expected.shape == (count, 60, 20)
        np.testing.assert_array_equal(np.asarray(labels, dtype=np.int64), np.load(reference / f"y_{split}.npy"))
        np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-6)
        report[split] = {"shape": list(actual.shape), "max_abs_error": float(np.max(np.abs(actual - expected)))}
    with zipfile.ZipFile(paths.model) as archive:
        config = json.loads(archive.read("config.json"))
    assert config["config"]["layers"][0]["config"]["batch_shape"] == [None, 60, 20]
    assert float(paths.threshold.read_text().strip()) == 0.30
    if paths.medians.exists():
        pd.testing.assert_series_equal(joblib.load(paths.medians), medians)
    if reconstruct:
        paths.medians.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(medians, paths.medians)
        sources = [reference / "Fall_Detection_Dataset.ipynb", reference / "UR_features_all.csv", paths.scaler]
        provenance = {
            "origin": "Reconstructed from notebook Cell 6 and CSV; original median pickle unavailable",
            "sources_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            "splits": splits, "features": FEATURE_NAMES, "window": 60, "stride": 15,
            "validation": report,
        }
        (paths.medians.parent / "reconstruction.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconstruct", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(args.reconstruct), indent=2))


if __name__ == "__main__":
    main()
