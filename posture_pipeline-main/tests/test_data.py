import pytest
from posture.data import validate_split


def test_split_rejects_same_person_and_duplicate_rows():
    split = {"train": [0], "val": [1], "calibration": [2], "test": [3]}
    validate_split(split, ["a", "b", "c", "d"], 4)
    with pytest.raises(ValueError, match="Participant"):
        validate_split(split, ["a", "a", "c", "d"], 4)
    split["test"] = [0]
    with pytest.raises(ValueError, match="overlap"):
        validate_split(split, ["a", "b", "c", "d"], 4)
