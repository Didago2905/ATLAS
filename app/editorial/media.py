"""Private content-addressed assets; reuse ATLAS validation/derivatives and staging."""
from hashlib import sha256
from io import BytesIO
import os
from types import SimpleNamespace
from PIL import Image
from app.editorial.config import private_root
from app.services.museum_upload_service import prepare_artwork, _stage


class MediaStore:
    def __init__(self, root):
        self.root = private_root(root)

    def path(self, digest, suffix):
        path = self.root / (digest + suffix)
        if path.resolve().parent != self.root:
            raise ValueError("Unsafe asset path")
        return path

    def prepare(self, content):
        source, extension, preview, _ = prepare_artwork(SimpleNamespace(file=BytesIO(content)))
        digest = sha256(source).hexdigest()
        # Dimensions describe the normalized preview, not an inferred device/artwork identity.
        with Image.open(BytesIO(preview)) as image:
            width, height = image.size
        self.root.mkdir(parents=True, exist_ok=True)
        for suffix, data in (("." + extension, source), (".preview.jpg", preview)):
            path = self.path(digest, suffix)
            if path.exists():
                if path.read_bytes() != data:
                    raise ValueError("Private asset identity conflict")
            else:
                candidate = _stage(path, data)
                try:
                    os.replace(candidate, path)
                finally:
                    candidate.unlink(missing_ok=True)
        return dict(digest=digest, extension=extension, byte_count=len(source), width=width, height=height)
