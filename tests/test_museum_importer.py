import csv
from contextlib import redirect_stdout
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid5, NAMESPACE_URL

from PIL import Image
from app.services import museum_upload_service as service
from scripts import import_museum_archive as importer


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.patch = patch.object(service, "ROOT", self.runtime)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.manifest = self.source / "museum_inventory.csv"
        self.fields = ["filename", "category", "artwork", "historical_year", "semantic_products"]
        self.row = dict(zip(self.fields, ["original.jpg", "carta_vieja", "Approved artwork", "", "[]"]))
        output = BytesIO()
        with Image.new("RGB", (100, 150), "blue") as image:
            image.save(output, "JPEG")
        self.raw = output.getvalue()
        (self.source / "original.jpg").write_bytes(self.raw)
        self.write_manifest([self.row])

    def write_manifest(self, rows):
        with self.manifest.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=self.fields)
            writer.writeheader()
            writer.writerows(rows)

    def registry(self, records):
        (self.runtime / "data").mkdir(exist_ok=True)
        (self.runtime / "data/museum.json").write_text(json.dumps(records), encoding="utf-8")

    def test_bom_schema_filter_and_exact_original_resolution(self):
        self.write_manifest([self.row, {**self.row, "filename": "not-opened.jpg", "category": "sin_clasificar"}])
        report = importer.audit(self.manifest, self.source)
        self.assertEqual(report["summary"]["total_manifest_rows"], 2)
        self.assertEqual(report["summary"]["excluded_rows"], {"sin_clasificar": 1})
        self.assertEqual(report["images"][0]["source_path"], str((self.source / "original.jpg").resolve()))
        self.assertEqual(report["images"][0]["decision"], "NEW")
        self.assertEqual(importer.audit(self.manifest, self.source, ["etiquetas"])["images"], [])
        self.manifest.write_text("wrong,columns\na,b\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Missing manifest"):
            importer.read_manifest(self.manifest)

    def test_missing_invalid_and_escaping_sources_never_use_classified_copies(self):
        (self.source / "museum_classified/carta_vieja").mkdir(parents=True)
        (self.source / "museum_classified/carta_vieja/missing.jpg").write_bytes(self.raw)
        (self.source / "bad.jpg").write_bytes(b"not an image")
        self.write_manifest([{**self.row, "filename": name} for name in ["missing.jpg", "bad.jpg", "../original.jpg"]])
        report = importer.audit(self.manifest, self.source)
        self.assertTrue(all(x["decision"] == "INVALID_SOURCE" for x in report["images"]))

    def test_identity_matches_upload_service_without_changing_its_scheme(self):
        digest = sha256(self.raw).hexdigest()
        identity, _ = service.artwork_identity("carta_vieja", digest)
        self.assertEqual(identity, str(uuid5(NAMESPACE_URL, f"atlas:museum:carta_vieja:{digest}")))
        self.assertEqual(importer.audit(self.manifest, self.source)["images"][0]["artwork_id"], identity)

    def test_existing_exact_bytes_are_detected_without_names(self):
        folder = self.runtime / "static/museum"
        folder.mkdir(parents=True)
        (folder / "unrelated-name.jpg").write_bytes(self.raw)
        self.registry([{"id": "legacy", "type": "fichas/antiguas", "name": "Different name",
                        "image_url": "/static/museum/unrelated-name.jpg"}])
        entry = importer.audit(self.manifest, self.source)["images"][0]
        self.assertEqual(entry["decision"], "EXACT_DUPLICATE")
        self.assertEqual(entry["existing_exact_ids"], ["legacy"])

    def test_optimized_legacy_match_is_possible_only_and_never_merged(self):
        self.registry([{"id": "legacy", "type": "fichas/antiguas", "image_url": "/static/museum/original.jpg"}])
        folder = self.runtime / "static/museum"
        folder.mkdir(parents=True)
        with Image.new("RGB", (20, 30), "red") as image:
            image.save(folder / "original.jpg", "JPEG")
        report = importer.audit(self.manifest, self.source)
        self.assertEqual(report["images"][0]["decision"], "POSSIBLE_LEGACY_MATCH")
        self.assertEqual(report["summary"]["expected_new_artworks_without_unresolved_candidates"], 0)

    def test_identity_collisions_preserve_distinct_manifest_rows_for_review(self):
        (self.source / "edition.jpg").write_bytes(self.raw)
        self.write_manifest([self.row, {**self.row, "filename": "edition.jpg", "artwork": "Another edition"}])
        report = importer.audit(self.manifest, self.source)
        self.assertEqual([x["decision"] for x in report["images"]], ["CONFLICT", "CONFLICT"])
        pilot = importer.audit(self.manifest, self.source, limit=1)
        self.assertEqual(pilot["images"][0]["decision"], "CONFLICT")
        self.assertEqual(pilot["summary"]["audited_rows"], 2)

    def test_verified_master_is_exact_but_matching_only_derivative_is_possible(self):
        initial = importer.audit(self.manifest, self.source)["images"][0]
        from fastapi import UploadFile
        _, _, output, _ = service._prepare(UploadFile(filename="original.jpg", file=BytesIO(self.raw)))
        destination = self.runtime / initial["image_url"].lstrip("/")
        destination.parent.mkdir(parents=True)
        destination.write_bytes(output)
        self.registry([{"id": initial["artwork_id"], "category": "carta_vieja",
                        "image_url": initial["image_url"], "image_sha256": sha256(output).hexdigest()}])
        # An identity with no verifiable original is deliberately a conflict.
        self.assertEqual(importer.audit(self.manifest, self.source)["images"][0]["decision"], "CONFLICT")
        master = self.runtime / initial["master_path"]
        master.parent.mkdir(parents=True)
        master.write_bytes(self.raw)
        records = service.read_registry()
        records[0].update(source_path=initial["master_path"], source_sha256=initial["source_sha256"])
        self.registry(records)
        self.assertEqual(importer.audit(self.manifest, self.source)["images"][0]["decision"], "EXACT_DUPLICATE")

    def test_identical_optimized_output_is_not_original_identity_proof(self):
        from fastapi import UploadFile
        _, _, output, _ = service._prepare(UploadFile(filename="original.jpg", file=BytesIO(self.raw)))
        destination = self.runtime / "static/museum/another-name.jpg"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(output)
        self.registry([{"id": "legacy", "type": "fichas/antiguas", "image_url": "/static/museum/another-name.jpg"}])
        entry = importer.audit(self.manifest, self.source)["images"][0]
        self.assertEqual(entry["decision"], "POSSIBLE_LEGACY_MATCH")
        self.assertIn("Identical optimized derivative", entry["legacy_candidates"][0]["evidence"])

    def test_dry_run_is_read_only_consistent_and_keeps_operational_assets(self):
        operational = self.runtime / "frontend/public/images/beerTablesTapList/1.jpg"
        operational.parent.mkdir(parents=True)
        operational.write_bytes(b"operational unchanged")
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with patch.object(service, "upload_artwork", side_effect=AssertionError("Cannot publish in dry run")), \
             patch.object(service, "_stage", side_effect=AssertionError("Cannot stage in dry run")), \
             patch.object(service, "_publication_lock", side_effect=AssertionError("Cannot lock in dry run")):
            one = importer.audit(self.manifest, self.source)
            two = importer.audit(self.manifest, self.source)
        self.assertEqual(one, two)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertFalse((self.runtime / "data").exists())
        self.assertFalse((self.runtime / "static").exists())

    def test_metadata_keeps_semantics_and_unknown_dates_without_flattening(self):
        raw = '[{"beer_name":{"value":null,"confidence":"unknown"}}, {"beer_name":{"value":"Other"}}]'
        result = importer.metadata({**self.row, "semantic_products": raw})
        self.assertEqual(result["semantic_products"], raw)
        self.assertEqual(result["year"], "")
        self.assertEqual(result["style"], "")
        self.assertEqual(result["manifest_metadata"]["semantic_products"], raw)

    def test_publication_requires_explicit_mode_pilot_limit_and_safe_report_path(self):
        for args in [[], ["--publish"], ["--publish", "--limit", "1"],
                     ["--dry-run", "--report", str(self.source / "report.json"), "--source-dir", str(self.source)]]:
            with self.subTest(args=args), self.assertRaises(SystemExit):
                importer.main(args)

    def pinned_fixture(self):
        rows, images = [], []
        for category in importer.APPROVED:
            for i, size in enumerate([(80, 120), (120, 80), (100, 100)]):
                filename = f"{category}-{i}.jpg"
                path = self.source / filename
                with Image.new("RGB", size, ["red", "blue", "green"][i]) as image:
                    image.save(path, "JPEG")
                digest = importer.fingerprint(path)
                identity, _ = service.artwork_identity(category, digest)
                rows.append({**self.row, "filename": filename, "category": category})
                images.append({"filename": filename, "category": category, "decision": "NEW",
                               "source_sha256": digest, "artwork_id": identity,
                               "width": size[0], "height": size[1], "source_bytes": path.stat().st_size})
        self.write_manifest(rows)
        baseline = self.root / "baseline.json"
        baseline.write_text(json.dumps({"manifest_sha256": importer.fingerprint(self.manifest), "images": images}), encoding="utf-8")
        selection = importer.select_pilot(baseline, self.manifest)
        pinned = self.root / "selection.json"
        pinned.write_text(json.dumps(selection), encoding="utf-8")
        return pinned, baseline

    def test_pilot_is_deterministic_pins_twelve_rows_and_dry_run_never_publishes(self):
        selection, baseline = self.pinned_fixture()
        one = importer.select_pilot(baseline, self.manifest)
        self.assertEqual(one, importer.select_pilot(baseline, self.manifest))
        self.assertEqual(importer.Counter(x["category"] for x in one["images"]), {x: 3 for x in importer.APPROVED})
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with patch.object(service, "upload_artwork", side_effect=AssertionError("Cannot publish")):
            report = importer.audit(self.manifest, self.source, selection=selection)
        self.assertEqual(len(report["images"]), 12)
        self.assertEqual(report["summary"]["audited_rows"], 12)
        self.assertEqual(report["summary"]["decisions"]["NEW"], 12)
        self.assertEqual({x["filename"] for x in report["images"]}, {x["filename"] for x in one["images"]})
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_pilot_rejects_changed_rows_baseline_and_source_bytes(self):
        selection, baseline = self.pinned_fixture()
        pinned = json.loads(selection.read_text(encoding="utf-8"))
        first = pinned["images"][0]
        path = self.source / first["filename"]
        path.write_bytes(self.raw)
        report = importer.audit(self.manifest, self.source, selection=selection)
        self.assertEqual(next(x for x in report["images"] if x["filename"] == path.name)["decision"], "CONFLICT")
        pinned["images"][0]["manifest_data_row"] = 9999
        selection.write_text(json.dumps(pinned), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "row does not exist"):
            importer.read_selection(selection, self.manifest)
        baseline.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "baseline audit changed"):
            importer.read_selection(selection, self.manifest)

    def test_pilot_never_selects_non_new_candidates(self):
        selection, baseline = self.pinned_fixture()
        report = json.loads(baseline.read_text(encoding="utf-8"))
        report["images"][0]["decision"] = "POSSIBLE_LEGACY_MATCH"
        baseline.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Not enough NEW"):
            importer.select_pilot(baseline, self.manifest)

    def test_future_pinned_publication_calls_only_twelve_independent_artworks(self):
        selection, _ = self.pinned_fixture()
        report = importer.audit(self.manifest, self.source, selection=selection)
        # Synthetic fixture has 12 rows, not the real 633; bypass only that count guard.
        report["summary"]["expected_manifest_counts_match"] = True
        with patch.object(service, "upload_artwork", return_value={"historical_created": True, "id": "synthetic"}) as upload, redirect_stdout(StringIO()):
            results = importer.publish(report, self.source)
        self.assertEqual(len(results), 12)
        self.assertEqual(upload.call_count, 12)
        self.assertEqual({call.args[0].filename for call in upload.call_args_list},
                         {x["filename"] for x in report["images"]})
        self.assertTrue(all(call.kwargs == {} for call in upload.call_args_list))
        # No beer or DB argument: service cannot update operational images/availability.


if __name__ == "__main__":
    unittest.main()
