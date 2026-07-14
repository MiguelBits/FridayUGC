from __future__ import annotations

from pathlib import Path

from ..config import get_settings
from .schemas import GalleryAsset, GalleryManifest

# Bundled sample gallery for mock/dev when S3 is not configured.
_DEV_MANIFEST = Path(__file__).resolve().parents[2] / "data" / "gallery" / "manifest.json"


def _load_local_manifest(path: Path) -> GalleryManifest:
    if not path.is_file():
        return GalleryManifest()
    return GalleryManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _save_local_manifest(path: Path, manifest: GalleryManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


def _s3_client():
    import boto3

    return boto3.client("s3", region_name=get_settings().gallery_s3_region)


class GalleryStore:
    """Read/write the media gallery manifest (S3 JSON or local file for dev)."""

    def __init__(self) -> None:
        s = get_settings()
        self._backend = s.gallery_backend.lower()
        self._bucket = s.gallery_s3_bucket
        self._key = s.gallery_s3_manifest_key
        self._local = Path(s.gallery_local_path) if s.gallery_local_path else _DEV_MANIFEST

    def load(self) -> GalleryManifest:
        if self._backend == "s3" and self._bucket:
            return self._load_s3()
        return _load_local_manifest(self._local)

    def save(self, manifest: GalleryManifest) -> None:
        if self._backend == "s3" and self._bucket:
            self._save_s3(manifest)
        else:
            _save_local_manifest(self._local, manifest)

    def list_unposted(self) -> list[GalleryAsset]:
        return [a for a in self.load().assets if not a.posted]

    def mark_posted(self, asset_ids: list[str]) -> None:
        manifest = self.load()
        ids = set(asset_ids)
        for asset in manifest.assets:
            if asset.id in ids:
                asset.posted = True
        self.save(manifest)

    def _load_s3(self) -> GalleryManifest:
        try:
            obj = _s3_client().get_object(Bucket=self._bucket, Key=self._key)
            return GalleryManifest.model_validate_json(obj["Body"].read().decode("utf-8"))
        except Exception:
            return GalleryManifest()

    def _save_s3(self, manifest: GalleryManifest) -> None:
        _s3_client().put_object(
            Bucket=self._bucket,
            Key=self._key,
            Body=manifest.model_dump_json(indent=2).encode("utf-8"),
            ContentType="application/json",
        )

    def asset_urls(self, asset: GalleryAsset) -> str:
        """Presigned URL or local path hint for the phone/agent."""
        if self._backend == "s3" and self._bucket and asset.s3_key:
            return _s3_client().generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": asset.s3_key},
                ExpiresIn=3600,
            )
        return asset.local_path or asset.s3_key

    def _gallery_root(self) -> Path:
        return self._local.parent if self._local.is_file() else self._local

    def read_asset_bytes(self, asset: GalleryAsset) -> bytes | None:
        """Load raw media bytes from S3 or local gallery folder."""
        if self._backend == "s3" and self._bucket and asset.s3_key:
            try:
                obj = _s3_client().get_object(Bucket=self._bucket, Key=asset.s3_key)
                return obj["Body"].read()
            except Exception:
                return None
        if asset.local_path:
            path = Path(asset.local_path)
            if not path.is_file():
                path = self._gallery_root() / asset.local_path
            if path.is_file():
                return path.read_bytes()
        return None

    def read_thumbnail_bytes(self, asset: GalleryAsset) -> bytes | None:
        if self._backend == "s3" and self._bucket and asset.thumbnail_key:
            try:
                obj = _s3_client().get_object(Bucket=self._bucket, Key=asset.thumbnail_key)
                return obj["Body"].read()
            except Exception:
                return None
        if asset.thumbnail_key:
            path = self._gallery_root() / asset.thumbnail_key
            if path.is_file():
                return path.read_bytes()
        return None
