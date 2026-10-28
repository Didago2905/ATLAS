"""Focused upload tests: synthetic images, temporary storage, in-memory SQLite.

Never import app.main (it initializes the application's real database).
"""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from PIL import Image, ImageCms
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import admin, public
from app.core.database import Base, get_db
from app.core.security import verify_token
from app.models.beer import Beer
from app.services import museum_upload_service as uploads


def jpeg(color="red", size=(1200, 1600), mode="RGB", exif=None):
    output = BytesIO()
    with Image.new(mode, size, color) as image:
        image.save(output, "JPEG", **({"exif": exif} if exif else {}))
    return output.getvalue()


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(uploads, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.beer = Beer(name="Test beer", brewery="Test brewery", style="Test style",
                         abv=5, is_available=True, tap_position=1,
                         beercard_background_url="/unchanged-background.jpg")
        self.db.add(self.beer)
        self.db.commit()
        self.beer_id = self.beer.id
        self.legacy = {"id": "legacy", "name": "Existing artwork",
                       "type": "fichas/antiguas", "image_url": "/static/museum/legacy.jpg"}
        (self.root / "data").mkdir()
        (self.root / "data/museum.json").write_text(json.dumps([self.legacy]), encoding="utf-8")
        (self.root / "static/museum").mkdir(parents=True)
        (self.root / "static/museum/legacy.jpg").write_bytes(b"unchanged legacy bytes")
        app = FastAPI()
        app.include_router(admin.router)
        app.include_router(public.router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[verify_token] = lambda: "test-admin"
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.red = jpeg()

    def upload(self, source=None, beer_id=None, filename="test.jpg"):
        return self.client.post(f"/admin/beers/{beer_id or self.beer_id}/upload-image",
                                files={"file": (filename, source or self.red, "image/jpeg")})

    def museum(self, source=None, category="fichas/antiguas", filename="art.jpg"):
        return self.client.post("/admin/museum", data={"type": category, "name": "Artwork"},
                                files={"file": (filename, source or self.red, "image/jpeg")})

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file() and p.name != ".museum-upload.lock"}

    def test_first_repeat_and_distinct_upload(self):
        first = self.upload()
        self.assertEqual(first.status_code, 200, first.text)
        data = first.json()
        self.assertTrue(data["operational_updated"] and data["historical_archived"])
        self.assertTrue(data["historical_created"])
        self.assertEqual(data["category"], "tap_list")
        self.assertNotEqual(data["image_url"], data["historical_image_url"])
        history = self.root / data["historical_image_url"].lstrip("/")
        before = history.read_bytes()
        with Image.open(history) as image:
            self.assertEqual(image.size, (750, 1000))
        with Image.open(self.root / f"frontend/public/images/beerTablesTapList/{self.beer_id}.jpg") as image:
            self.assertEqual(image.size, (600, 800))
        repeated = self.upload(filename="different-name.jpg").json()
        self.assertEqual(repeated["id"], data["id"])
        self.assertFalse(repeated["historical_created"])
        self.assertEqual(len(uploads.read_registry()), 2)
        different = self.upload(jpeg("blue")).json()
        self.assertNotEqual(different["id"], data["id"])
        self.assertEqual(len(uploads.read_registry()), 3)
        self.assertEqual(history.read_bytes(), before)
        self.assertEqual((self.root / data["source_path"]).read_bytes(), self.red)
        self.assertEqual(self.db.get(Beer, self.beer_id).beercard_background_url, "/unchanged-background.jpg")

    def test_availability_catalog_edits_and_soft_delete_do_not_change_archive(self):
        self.upload()
        original = uploads.read_registry()
        self.assertEqual(len(self.client.get("/public/tap").json()), 1)
        response = self.client.patch(f"/admin/beers/{self.beer_id}/availability",
                                     json={"is_available": False})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get("/public/tap").json(), [])
        self.beer.name = "Changed catalog name"
        self.beer.is_deleted = True
        self.db.commit()
        self.assertEqual(self.client.get("/public/museum").json(), original)
        self.assertEqual(self.upload().status_code, 404)

    def test_invalid_beer_writes_nothing(self):
        original = self.snapshot()
        self.assertEqual(self.upload(beer_id=9999).status_code, 404)
        self.assertEqual(self.snapshot(), original)

    def test_invalid_data_limits_category_and_collision_safe_names(self):
        self.upload()
        before = self.snapshot()
        self.assertEqual(self.upload(b"not an image").status_code, 400)
        self.assertEqual(self.museum(category="../../escape").status_code, 400)
        with patch.object(uploads, "MAX_BYTES", 10):
            self.assertEqual(self.upload().status_code, 413)
        with patch.object(uploads, "MAX_PIXELS", 10):
            self.assertEqual(self.upload().status_code, 413)
        self.assertEqual(self.snapshot(), before)
        malicious_name = self.museum(filename="../../escaped.jpg")
        self.assertEqual(malicious_name.status_code, 200, malicious_name.text)
        self.assertEqual(malicious_name.json()["source_filename"], "escaped.jpg")
        self.assertFalse((self.root / "escaped.jpg").exists())

    def test_museum_duplicates_editions_aliases_and_existing_records(self):
        first = self.museum().json()
        self.assertFalse(self.museum(filename="renamed.jpg").json()["historical_created"])
        self.assertFalse(self.museum(category="carta_vieja").json()["historical_created"])
        second = self.museum(jpeg("blue")).json()
        self.assertNotEqual(first["id"], second["id"])
        records = uploads.read_registry()
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0], self.legacy)
        self.assertEqual((self.root / "static/museum/legacy.jpg").read_bytes(), b"unchanged legacy bytes")
        self.assertEqual(len(list((self.root / "static/museum/carta_vieja").glob("*.jpg"))), 2)

    def test_publication_failure_restores_every_destination(self):
        self.upload()
        before = self.snapshot()
        old_url = self.beer.image_url
        replace = uploads.os.replace

        def fail_registry_once(src, dst):
            if Path(dst) == self.root / "data/museum.json" and Path(src).read_bytes() != before["data/museum.json"]:
                raise OSError("simulated registry publication failure")
            return replace(src, dst)

        with patch.object(uploads.os, "replace", side_effect=fail_registry_once):
            response = self.upload(jpeg("blue"))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.snapshot(), before)
        self.db.refresh(self.beer)
        self.assertEqual(self.beer.image_url, old_url)

    def test_db_failure_restores_registry_and_images(self):
        self.upload()
        before = self.snapshot()
        old_url = self.beer.image_url
        with patch.object(self.db, "commit", side_effect=RuntimeError("simulated DB failure")):
            self.assertEqual(self.upload(jpeg("blue")).status_code, 500)
        self.assertEqual(self.snapshot(), before)
        self.db.refresh(self.beer)
        self.assertEqual(self.beer.image_url, old_url)

    def test_staging_failure_preserves_previous_state(self):
        self.upload()
        before = self.snapshot()
        stage = uploads._stage

        def fail_registry_staging(path, content):
            if path == self.root / "data/museum.json":
                raise OSError("simulated staging failure")
            return stage(path, content)

        with patch.object(uploads, "_stage", side_effect=fail_registry_staging):
            self.assertEqual(self.upload(jpeg("blue")).status_code, 500)
        self.assertEqual(self.snapshot(), before)

    def test_same_content_for_distinct_beers_gets_independent_records(self):
        first = self.upload().json()
        other = Beer(name=self.beer.name, brewery="Another brewery", style="Other style")
        self.db.add(other)
        self.db.commit()
        second = self.upload(beer_id=other.id).json()
        self.assertNotEqual(first["id"], second["id"])
        self.assertNotEqual(first["historical_image_url"], second["historical_image_url"])
        self.assertEqual(first["source_path"], second["source_path"])
        self.assertEqual(len(uploads.read_registry()), 3)

    def test_generic_upload_keeps_its_no_registry_contract(self):
        before = (self.root / "data/museum.json").read_bytes()
        response = self.client.post("/admin/upload-image?type=packaging",
                                    files={"file": ("box.jpg", self.red, "image/jpeg")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["historical_archived"])
        self.assertTrue((self.root / response.json()["image_url"].lstrip("/")).exists())
        self.assertEqual((self.root / "data/museum.json").read_bytes(), before)

    def test_museum_write_failure_and_corrupt_registry_preserve_previous_state(self):
        before = self.snapshot()
        with patch.object(uploads.os, "replace", side_effect=OSError("simulated write failure")):
            self.assertEqual(self.museum().status_code, 500)
        self.assertEqual(self.snapshot(), before)
        (self.root / "data/museum.json").write_bytes(b"broken JSON")
        before = self.snapshot()
        self.assertEqual(self.upload().status_code, 503)
        self.assertEqual(self.snapshot(), before)

    def test_exif_transparency_cmyk_and_animated_rejection(self):
        exif = Image.Exif()
        exif[274] = 6
        response = self.museum(jpeg(size=(1200, 600), exif=exif))
        with Image.open(self.root / response.json()["image_url"].lstrip("/")) as image:
            self.assertEqual(image.size, (500, 1000))
        self.assertEqual(self.museum(jpeg(color=(0, 0, 0, 0), mode="CMYK")).status_code, 200)
        png = BytesIO()
        with Image.new("RGBA", (10, 10), (255, 0, 0, 0)) as image:
            image.save(png, "PNG")
        transparent = self.museum(png.getvalue()).json()
        with Image.open(self.root / transparent["image_url"].lstrip("/")) as image:
            self.assertGreater(min(image.getpixel((0, 0))), 245)
        gif = BytesIO()
        with Image.new("RGB", (10, 10), "red") as a, Image.new("RGB", (10, 10), "blue") as b:
            a.save(gif, "GIF", save_all=True, append_images=[b])
        self.assertEqual(self.museum(gif.getvalue()).status_code, 415)

    def test_concurrent_registry_writers_keep_both_artworks(self):
        def upload(source):
            return uploads.upload_artwork(UploadFile(filename="art.jpg", file=BytesIO(source)),
                                          "etiquetas", {"name": "Concurrent artwork"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(upload, [self.red, jpeg("blue")]))
        self.assertEqual(len({result["id"] for result in results}), 2)
        self.assertEqual(len(uploads.read_registry()), 3)

    def test_icc_conversion_and_invalid_profile_rejection(self):
        image_data = BytesIO()
        with Image.new("RGB", (100, 100), "green") as image:
            profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
            image.save(image_data, "JPEG", icc_profile=profile)
        self.assertEqual(self.museum(image_data.getvalue()).status_code, 200)
        before = self.snapshot()
        invalid_profile = BytesIO()
        with Image.new("RGB", (100, 100), "green") as image:
            image.save(invalid_profile, "JPEG", icc_profile=b"invalid ICC")
        self.assertEqual(self.museum(invalid_profile.getvalue()).status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_four_canonical_categories_are_accepted_and_preserved(self):
        for category in ("tap_list", "carta_vieja", "carta_nueva", "etiquetas"):
            with self.subTest(category=category):
                response = self.museum(category=category)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["category"], category)
                self.assertEqual(response.json()["type"], category)
        self.assertEqual(uploads.read_registry()[0], self.legacy)


if __name__ == "__main__":
    unittest.main()
