"""Locate the warehouse for the dashboard: local file, or a snapshot from Hugging Face Hub.

The deployed app has no pipeline; it downloads the published snapshot once and opens it read-only.
"""

from pathlib import Path

SNAPSHOT_FILE = "warehouse.duckdb"


def resolve_warehouse(local_path: Path, hf_repo: str | None, hf_token: str | None) -> Path:
    """Use `local_path` if it exists; otherwise download `SNAPSHOT_FILE` from the dataset repo."""
    if local_path.exists():
        return local_path
    if not hf_repo:
        raise FileNotFoundError(
            f"No warehouse at {local_path} and no HF_DATASET_REPO configured. "
            "Run the pipeline locally or set HF_DATASET_REPO to a published snapshot."
        )
    from huggingface_hub import hf_hub_download

    return Path(
        hf_hub_download(
            repo_id=hf_repo, filename=SNAPSHOT_FILE, repo_type="dataset", token=hf_token or None
        )
    )
