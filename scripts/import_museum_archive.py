"""Local Museum importer. Phase 1 uses --dry-run only; no application/SQL import.

Dry run decodes sequentially through the existing upload processor, in memory.
It never calls the publisher or its directory/lock creation code.
"""
import argparse
from collections import Counter
import csv
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path, PureWindowsPath
import sys
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException, UploadFile
from PIL import Image
from app.services import museum_upload_service as service

APPROVED = {"tap_list": 135, "carta_vieja": 8, "carta_nueva": 101, "etiquetas": 102}
REQUIRED = {"filename", "category", "artwork", "historical_year", "semantic_products"}
STATUSES = ("NEW", "EXACT_DUPLICATE", "POSSIBLE_LEGACY_MATCH", "CONFLICT", "INVALID_SOURCE")


def row_hash(row):
    return sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def select_pilot(report_path, manifest):
    """Deterministic technical variety, using only the existing audit's NEW rows."""
    report_path, manifest = Path(report_path).resolve(), Path(manifest).resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if fingerprint(manifest) != report["manifest_sha256"]:
        raise ValueError("Manifest differs from the audited version")
    _, rows = read_manifest(manifest)
    indexed = {r["filename"]: (i, r) for i, r in enumerate(rows, 1)}
    chosen = []
    for category in ("tap_list", "carta_vieja", "carta_nueva", "etiquetas"):
        candidates = sorted((x for x in report["images"] if x["category"] == category and x["decision"] == "NEW"),
                            key=lambda x: x["filename"])
        if len(candidates) < 3:
            raise ValueError(f"Not enough NEW candidates in {category}")
        features = [[math.log(x["width"]), math.log(x["height"]),
                     math.log(x["width"] / x["height"]), math.log(x["source_bytes"])] for x in candidates]
        low, high = [min(x[j] for x in features) for j in range(4)], [max(x[j] for x in features) for j in range(4)]
        normalized = [[(x[j] - low[j]) / (high[j] - low[j]) if high[j] > low[j] else 0.5
                       for j in range(4)] for x in features]
        distance = lambda a, b: sum((x - y) ** 2 for x, y in zip(a, b))
        selected = [min(range(len(candidates)), key=lambda i: (distance(normalized[i], [0.5] * 4), candidates[i]["filename"]))]
        while len(selected) < 3:
            selected.append(min((i for i in range(len(candidates)) if i not in selected),
                                key=lambda i: (-min(distance(normalized[i], normalized[j]) for j in selected), candidates[i]["filename"])))
        for index in selected:
            item = candidates[index]
            data_row, row = indexed[item["filename"]]
            chosen.append({**{k: item[k] for k in ("filename", "category", "source_sha256", "artwork_id", "width", "height", "source_bytes")},
                           "manifest_data_row": data_row, "manifest_row_sha256": row_hash(row)})
    return {"version": 1, "manifest_sha256": report["manifest_sha256"],
            "audit_report": str(report_path), "audit_report_sha256": fingerprint(report_path),
            "method": "Log width/height/aspect/bytes, min-max normalized; central candidate then farthest-point sampling; filename tie-break",
            "images": chosen}


def read_selection(path, manifest):
    selection = json.loads(Path(path).read_text(encoding="utf-8"))
    if fingerprint(Path(manifest)) != selection["manifest_sha256"]:
        raise ValueError("Pinned manifest hash changed")
    audit_path = Path(selection["audit_report"])
    if fingerprint(audit_path) != selection["audit_report_sha256"]:
        raise ValueError("Pinned baseline audit changed")
    baseline = json.loads(audit_path.read_text(encoding="utf-8"))
    if baseline["manifest_sha256"] != selection["manifest_sha256"]:
        raise ValueError("Selection and baseline refer to different manifests")
    _, rows = read_manifest(Path(manifest))
    pins = selection["images"]
    if not pins or len({x["filename"] for x in pins}) != len(pins) or len({x["artwork_id"] for x in pins}) != len(pins):
        raise ValueError("Selection contains missing or repeated identities")
    baseline_rows = {x["filename"]: x for x in baseline["images"]}
    for pin in pins:
        number = pin["manifest_data_row"]
        if not 1 <= number <= len(rows):
            raise ValueError("Pinned data row does not exist")
        row, original = rows[number - 1], baseline_rows.get(pin["filename"], {})
        if row["filename"] != pin["filename"] or row["category"] != pin["category"] or row_hash(row) != pin["manifest_row_sha256"]:
            raise ValueError("Pinned manifest row changed")
        if original.get("decision") != "NEW" or any(original.get(k) != pin[k] for k in
                ("category", "source_sha256", "artwork_id", "width", "height", "source_bytes")):
            raise ValueError("Selection must pin an unchanged NEW baseline candidate")
    return pins


def fingerprint(path):
    return sha256(path.read_bytes()).hexdigest()


def resolve_source(folder, filename):
    # This manifest is flat: the filename column is the original mapping.
    if not filename or Path(filename).name != filename or PureWindowsPath(filename).name != filename:
        raise ValueError("Expected an original filename, not a path")
    path = (folder / filename).resolve()
    if not path.is_relative_to(folder.resolve()):
        raise ValueError("Source escapes original directory")
    if not path.is_file():
        raise ValueError("Original file is missing; no classified-copy fallback")
    return path


def read_manifest(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Missing or repeated CSV headers")
        missing = REQUIRED - set(reader.fieldnames)
        if missing:
            raise ValueError(f"Missing manifest columns: {sorted(missing)}")
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError("CSV row/header length mismatch")
        return reader.fieldnames, rows


def metadata(row):
    raw = row["semantic_products"]
    if raw and not isinstance(json.loads(raw), list):
        raise ValueError("semantic_products must be a JSON array")
    # Preserve the exact semantic string and all source columns; do not flatten products.
    return {"name": row["artwork"], "style": "", "abv": "", "year": row["historical_year"],
            "semantic_products": raw, "manifest_metadata": dict(row)}


def inspect_registry():
    result, issues = [], []
    for item in service.read_registry():
        info = {"record": item, "id": item.get("id"), "issues": []}
        try:
            url = urlsplit(item.get("image_url", ""))
            if url.scheme or url.netloc or not url.path.startswith("/static/museum/"):
                raise ValueError("Not a local Museum asset URL")
            path = (service.ROOT / unquote(url.path).lstrip("/")).resolve()
            if not path.is_relative_to((service.ROOT / "static/museum").resolve()):
                raise ValueError("Registry asset path escapes Museum")
            info["image_sha256"] = fingerprint(path)
            with Image.open(path) as image:
                info.update(width=image.width, height=image.height, format=image.format)
            if item.get("image_sha256") and item["image_sha256"] != info["image_sha256"]:
                raise ValueError("Registered derivative hash differs from actual asset")
            master = item.get("source_path")
            if master:
                master_path = (service.ROOT / master).resolve()
                if not master_path.is_relative_to((service.ROOT / "data/museum/masters").resolve()):
                    raise ValueError("Master path escapes Museum masters")
                info["verified_source_sha256"] = fingerprint(master_path)
                if item.get("source_sha256") != info["verified_source_sha256"]:
                    raise ValueError("Registered source hash differs from master")
        except (OSError, ValueError) as error:
            info["issues"].append(str(error))
            issues.append({"id": item.get("id"), "issue": str(error)})
        result.append(info)
    ids = [x["id"] for x in result]
    if len(ids) != len(set(ids)):
        issues.append({"issue": "Repeated registry IDs"})
    return result, issues


def runtime_snapshot():
    paths = [service.ROOT / "data/museum.json"]
    for folder in ("static/museum", "data/museum", "frontend/public/images/beerTablesTapList"):
        base = service.ROOT / folder
        if base.exists():
            paths.extend(p for p in base.rglob("*") if p.is_file())
    return {p.relative_to(service.ROOT).as_posix(): fingerprint(p) for p in paths if p.is_file()}


def audit(manifest, source_dir, categories=None, limit=None, progress=None, selection=None):
    manifest, source_dir = Path(manifest).resolve(), Path(source_dir).resolve()
    manifest_hash = fingerprint(manifest)
    before_runtime = runtime_snapshot()
    original_stats = {p.name: (p.stat().st_size, p.stat().st_mtime_ns)
                      for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}}
    columns, rows = read_manifest(manifest)
    registry, registry_issues = inspect_registry()
    approved = [r for r in rows if r["category"] in APPROVED]
    selected = [r for r in approved if not categories or r["category"] in categories]
    selected = sorted(selected, key=lambda r: r["filename"])
    pins = {x["filename"]: x for x in read_selection(selection, manifest)} if selection else {}
    if selection:
        selected = [r for r in selected if r["filename"] in pins]
    repeated_names = {name for name, count in Counter(r["filename"] for r in rows).items() if count > 1}
    decisions, seen = [], {}
    for index, row in enumerate(selected):
        entry = {"filename": row["filename"], "category": row["category"], "decision": "NEW",
                 "reasons": [], "legacy_candidates": [], "metadata_warnings": []}
        decisions.append(entry)
        try:
            source_path = resolve_source(source_dir, row["filename"])
            entry["source_path"] = str(source_path)
            entry["source_bytes"] = source_path.stat().st_size
            entry["source_sha256"] = fingerprint(source_path)
            with Image.open(source_path) as image:
                entry.update(format=image.format, width=image.width, height=image.height)
            for field, actual in (("size_bytes", entry["source_bytes"]), ("width", entry["width"]), ("height", entry["height"])):
                if row.get(field) and int(row[field]) != actual:
                    entry["reasons"].append(f"Manifest {field} differs from source")
            metadata(row)
            products = json.loads(row["semantic_products"]) if row["semantic_products"] else []
            if not products:
                entry["metadata_warnings"].append("No semantic products; preserve empty or blank without invented identities")
            elif len(products) > 1:
                entry["metadata_warnings"].append("Multiple semantic products; preserve array without flattening")
            if not row["historical_year"]:
                entry["metadata_warnings"].append("No historical year; do not infer from EXIF or legacy record")
            with source_path.open("rb") as source:
                raw, extension, derivative, _ = service._prepare(UploadFile(filename=row["filename"], file=source))
            if sha256(raw).hexdigest() != entry["source_sha256"]:
                raise ValueError("Source changed during audit")
            identity, relative = service.artwork_identity(row["category"], entry["source_sha256"])
            entry.update(artwork_id=identity, image_url=f"/static/museum/{relative}",
                         output_bytes=len(derivative), output_sha256=sha256(derivative).hexdigest(),
                         master_path=f"data/museum/masters/{entry['source_sha256']}.{extension}")
            if row["filename"] in pins:
                pin = pins[row["filename"]]
                entry["manifest_data_row"] = pin["manifest_data_row"]
                entry["manifest_row_sha256"] = pin["manifest_row_sha256"]
                if any(entry[k] != pin[k] for k in ("source_sha256", "category", "artwork_id", "width", "height", "source_bytes")):
                    entry["reasons"].append("Source or identity differs from pinned selection")
            exact = []
            for existing in registry:
                record = existing["record"]
                category = record.get("category") or service.CATEGORIES.get(record.get("type"))
                if category != row["category"]:
                    continue
                if existing.get("verified_source_sha256") == entry["source_sha256"] or existing.get("image_sha256") == entry["source_sha256"]:
                    exact.append(existing["id"])
                elif not existing.get("verified_source_sha256"):
                    same_output = existing.get("image_sha256") == entry["output_sha256"]
                    same_name = Path(urlsplit(record.get("image_url", "")).path).name == row["filename"]
                    same_ratio = existing.get("width") and abs(existing["width"] / existing["height"] - entry["width"] / entry["height"]) < 0.02
                    if same_output or (same_name and same_ratio):
                        entry["legacy_candidates"].append({"id": existing["id"], "evidence":
                            "Identical optimized derivative; original provenance unverified" if same_output else
                            "Same original filename and compatible aspect ratio; NOT proof of identity"})
                if record.get("id") == identity and existing.get("verified_source_sha256") != entry["source_sha256"]:
                    entry["reasons"].append("Registry identity has unverified or conflicting source")
            destination = service.ROOT / "static/museum" / relative
            if destination.exists() and fingerprint(destination) != entry["output_sha256"]:
                entry["reasons"].append("Destination exists with different bytes")
            if destination.exists() and not any(x["id"] == identity for x in registry):
                entry["reasons"].append("Unregistered destination already exists")
            master = service.ROOT / entry["master_path"]
            if master.exists() and fingerprint(master) != entry["source_sha256"]:
                entry["reasons"].append("Master path has conflicting bytes")
            if row["filename"] in repeated_names:
                entry["reasons"].append("Repeated original filename in manifest")
            if identity in seen:
                # One category+hash identity cannot preserve two separately classified rows.
                entry["reasons"].append(f"Identity collapses distinct manifest rows: {seen[identity]['filename']}")
                seen[identity]["decision"] = "CONFLICT"
                seen[identity]["reasons"].append(f"Identity also claimed by {row['filename']}")
            seen[identity] = entry
            entry["existing_exact_ids"] = exact
            entry["decision"] = ("CONFLICT" if entry["reasons"] else "EXACT_DUPLICATE" if exact else
                                 "POSSIBLE_LEGACY_MATCH" if entry["legacy_candidates"] else "NEW")
        except (OSError, ValueError, HTTPException, Image.DecompressionBombError) as error:
            entry["decision"] = "INVALID_SOURCE"
            entry["reasons"].append(str(getattr(error, "detail", error)))
        if progress and ((index + 1) % 25 == 0 or index + 1 == len(selected)):
            progress(index + 1, len(selected))
    # Audit the entire chosen category before limiting a pilot; a later row may
    # collide with an earlier row's category+content identity.
    evaluated = decisions
    changed = []
    for entry in decisions:
        if entry.get("source_sha256"):
            try:
                if fingerprint(Path(entry["source_path"])) != entry["source_sha256"]:
                    changed.append(entry["filename"])
            except OSError:
                changed.append(entry["filename"])
    after_stats = {p.name: (p.stat().st_size, p.stat().st_mtime_ns)
                   for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}}
    if limit is not None:
        decisions = decisions[:limit]
    counts = Counter(x["decision"] for x in decisions)
    new = [x for x in decisions if x["decision"] == "NEW"]
    masters = {x["master_path"]: x["source_bytes"] for x in new if not (service.ROOT / x["master_path"]).exists()}
    unique_outputs = {x["artwork_id"]: x["output_bytes"] for x in decisions if "output_bytes" in x}
    summary = {"total_manifest_rows": len(rows), "approved_rows": dict(Counter(r["category"] for r in approved)),
               "excluded_rows": dict(Counter(r["category"] for r in rows if r["category"] not in APPROVED)),
               "selected_rows": len(decisions), "audited_rows": len(evaluated),
               "decisions": {status: counts[status] for status in STATUSES},
               "expected_new_artworks_without_unresolved_candidates": len(new),
               "source_bytes_selected": sum(x.get("source_bytes", 0) for x in decisions),
               "estimated_new_master_bytes": sum(masters.values()),
               "estimated_new_derivative_bytes": sum(x["output_bytes"] for x in new),
               "all_eligible_unique_derivative_bytes_including_unresolved": sum(unique_outputs.values()),
               "metadata_warning_counts": dict(Counter(w for x in decisions for w in x["metadata_warnings"])),
               "registry_issues": registry_issues,
               "expected_manifest_counts_match": len(rows) == 633 and Counter(r["category"] for r in approved) == Counter(APPROVED),
               "unchanged": {"manifest_sha256": fingerprint(manifest) == manifest_hash,
                             "all_original_jpeg_size_mtime": original_stats == after_stats,
                             "original_jpeg_count": len(original_stats),
                             "selected_source_hashes": not changed and all("source_sha256" in x for x in evaluated),
                             "changed_sources": changed, "runtime_content_hashes": runtime_snapshot() == before_runtime}}
    return {"mode": "dry-run", "manifest": str(manifest), "manifest_sha256": manifest_hash,
            "selection_sha256": fingerprint(Path(selection)) if selection else None,
            "columns": columns, "summary": summary, "existing_artworks": registry, "images": decisions}


def publish(report, source_dir):
    """Future explicitly requested pilot: NEW only; each image commits independently."""
    if report["summary"]["registry_issues"]:
        raise ValueError("Resolve registry issues before publishing")
    if not report["summary"]["expected_manifest_counts_match"]:
        raise ValueError("Canonical manifest counts differ from approved totals")
    unchanged = report["summary"]["unchanged"]
    if not all(unchanged[key] for key in ("manifest_sha256", "all_original_jpeg_size_mtime", "selected_source_hashes", "runtime_content_hashes")):
        raise ValueError("Inputs changed during audit; repeat the dry run")
    if fingerprint(Path(report["manifest"])) != report["manifest_sha256"]:
        raise ValueError("Manifest changed since audit")
    _, rows = read_manifest(Path(report["manifest"]))
    by_name = {r["filename"]: r for r in rows}
    results = []
    for entry in report["images"]:
        result = {"filename": entry["filename"], "decision": entry["decision"]}
        if entry["decision"] != "NEW":
            result["result"] = "SKIPPED_REQUIRES_REVIEW" if entry["decision"] != "EXACT_DUPLICATE" else "ALREADY_ARCHIVED"
        else:
            try:
                path = resolve_source(Path(source_dir), entry["filename"])
                raw = path.read_bytes()
                if sha256(raw).hexdigest() != entry["source_sha256"]:
                    raise ValueError("Source changed since audit")
                data = service.upload_artwork(UploadFile(filename=path.name, file=BytesIO(raw)),
                                              entry["category"], metadata(by_name[path.name]))
                result.update(result="ARCHIVED" if data["historical_created"] else "ALREADY_ARCHIVED", id=data["id"])
            except (OSError, ValueError, HTTPException) as error:
                result.update(result="FAILED", error=str(getattr(error, "detail", error)))
        results.append(result)
        print(json.dumps(result, ensure_ascii=True), flush=True)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--publish", action="store_true", help="Future authorized pilot only")
    parser.add_argument("--manifest", type=Path, default=Path("D:/Apps/Tuburon/smash/museum_inventory.csv"))
    parser.add_argument("--source-dir", type=Path, default=Path("D:/Apps/Tuburon/smash"))
    parser.add_argument("--category", action="append", choices=sorted(APPROVED))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--selection", type=Path, help="Pinned explicit source/row/identity JSON")
    parser.add_argument("--selection-sha256", help="Require this exact selection file hash")
    parser.add_argument("--report", type=Path, help="Audit JSON outside source and application directories")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.selection and (args.category or args.limit):
        parser.error("--selection cannot be combined with --category or --limit")
    if args.selection_sha256 and (not args.selection or fingerprint(args.selection) != args.selection_sha256):
        parser.error("Selection file hash mismatch")
    if args.publish and args.selection and not args.selection_sha256:
        parser.error("Pinned publication requires --selection-sha256")
    if args.publish and not args.selection and (not args.limit or not args.category):
        parser.error("Publishing requires explicit --category and --limit")
    if args.report and (args.report.resolve().is_relative_to(args.source_dir.resolve()) or
                        args.report.resolve().is_relative_to(service.ROOT.resolve()) or
                        args.report.resolve() == args.manifest.resolve()):
        parser.error("Report must be outside the source archive and application")
    report = audit(args.manifest, args.source_dir, args.category, args.limit,
                   progress=lambda done, total: print(f"Inspected {done}/{total}", file=sys.stderr, flush=True),
                   selection=args.selection)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report["summary"], ensure_ascii=True, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    if args.publish:
        if args.selection and (report["selection_sha256"] != args.selection_sha256 or fingerprint(args.selection) != args.selection_sha256):
            raise ValueError("Selection changed during audit; nothing published")
        if args.selection and any(x["decision"] not in {"NEW", "EXACT_DUPLICATE"} for x in report["images"]):
            raise ValueError("Pinned preflight failed; nothing published")
        results = publish(report, args.source_dir)
        return int(any(x["result"] in {"FAILED", "SKIPPED_REQUIRES_REVIEW"} for x in results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
