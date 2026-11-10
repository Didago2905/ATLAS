"""Pure domain regression tests; no live catalog, media, configuration or Telegram."""
from copy import deepcopy
import json
from uuid import UUID
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import sqlite3

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from pydantic import ValidationError

from app.editorial.proposal import Proposal, UnsupportedProposalVersion, validate_proposal
from app.editorial.proposal_v22 import (
    ExistingBeer, IdentitySnapshot, Interaction, Proposal22, VocabularyDecision,
    assess_readiness, assert_identity_current, identity_fingerprint, prepare_for_review, proposal_issues,
)
from app.editorial.patches import CommercialPatch, apply_commercial_patch, correct_patch_field
from app.editorial.navigation_v22 import (
    NavigationState, answer_commercial, callback_context, correct_proposal, navigate,
    reconcile_paths, start_navigation, valid_paths,
)


def uid(number):
    return str(UUID(int=number))


def confirmation():
    return {"method": "human_confirmation", "reference": "offline:interaction:1"}


def existing(number=1, beer_id=7):
    snapshot = {"name": "Cerveza de prueba", "brewery": "Tiburón", "style": "IPA", "origin": None}
    return {"kind": "existing", "id": uid(number), "beer_id": beer_id, "snapshot": snapshot,
            "expected_fingerprint": identity_fingerprint(snapshot, beer_id=beer_id), "confirmation": confirmation()}


def artwork(number=2, source="private", **extra):
    ref = {"kind": "private", "asset_id": "a" * 32} if source == "private" else {"kind": "museum", "artwork_id": uid(90)}
    return {"id": uid(number), "source": ref, "roles": ["tap_board"], **extra}


def payload(**extra):
    return {"schema_version": "2.2", "case_id": uid(100), "intake_origin": "data_only", "revision": 1, **extra}


def commercial_proposal():
    return Proposal22.model_validate(payload(beers=[existing()], actions=[
        {"kind": "commercial_change", "id": uid(3), "beer_identity_id": uid(1), "patch": {"abv": {"op": "set", "value": 6}}}]))


class ContractTests(unittest.TestCase):
    def test_legacy_validation_and_dispatch_are_unchanged(self):
        raw = {"revision": 3, "operation": "board", "targets": ["museum"],
               "museum": {"title": "Legado", "collection": "tap_list"}}
        before = deepcopy(raw)
        self.assertEqual(validate_proposal(raw).model_dump(), Proposal.model_validate(raw).model_dump())
        self.assertEqual(raw, before)
        with self.assertRaises(ValidationError):
            validate_proposal({**raw, "unexpected": True})

    def test_22_roundtrip_has_explicit_dispatch(self):
        p = commercial_proposal()
        raw = json.loads(p.model_dump_json())
        self.assertIsInstance(validate_proposal(raw), Proposal22)
        self.assertEqual(validate_proposal(raw), p)
        with self.assertRaises(ValidationError):
            Proposal.model_validate(raw)

    def test_missing_fields_and_unsupported_versions_fail(self):
        for field in ("case_id", "intake_origin", "revision"):
            raw = payload()
            raw.pop(field)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate_proposal(raw)
        with self.assertRaises(UnsupportedProposalVersion):
            validate_proposal({"schema_version": "9.0"})
        with self.assertRaises(ValueError):
            validate_proposal([])

    def test_existing_identity_requires_id_snapshot_fingerprint_and_human_reference(self):
        self.assertIsInstance(ExistingBeer.model_validate(existing()), ExistingBeer)
        for field in ("beer_id", "snapshot", "expected_fingerprint", "confirmation"):
            raw = existing()
            raw.pop(field)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                ExistingBeer.model_validate(raw)
        for change in ({"beer_id": 0}, {"beer_id": True}, {"beer_id": 2**63}, {"beer_id": 8}, {"expected_fingerprint": "b" * 64},
                       {"confirmation": {"method": "text_match", "reference": "not proof"}}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                ExistingBeer.model_validate({**existing(), **change})

    def test_identity_stale_detection_uses_in_memory_snapshot(self):
        ref = ExistingBeer.model_validate(existing())
        assert_identity_current(ref, ref.snapshot, beer_id=7)
        with self.assertRaises(ValueError):
            assert_identity_current(ref, {**ref.snapshot.model_dump(), "brewery": "Otra"}, beer_id=7)
        with self.assertRaises(ValueError):
            assert_identity_current(ref, {**ref.snapshot.model_dump(), "name": ref.snapshot.name + " "}, beer_id=7)
        with self.assertRaises(ValueError):
            assert_identity_current(ref, ref.snapshot, beer_id=8)

    def test_new_existing_and_unresolved_are_distinct(self):
        p = Proposal22.model_validate(payload(beers=[existing(), {"kind": "new", "id": uid(4)},
                                                                   {"kind": "unresolved", "id": uid(5), "entered_name": "Pendiente"}]))
        self.assertEqual([b.kind for b in p.beers], ["existing", "new", "unresolved"])
        with self.assertRaises(ValidationError):
            Proposal22.model_validate(payload(beers=[existing(), existing()]))

    def test_independent_actions_do_not_invent_other_actions(self):
        p = commercial_proposal()
        self.assertEqual([a.kind for a in p.actions], ["commercial_change"])
        raw = payload(beers=[existing()], artworks=[artwork(roles=["beer_card"])], actions=[
            {"kind": "replace_beer_card", "id": uid(3), "beer_identity_id": uid(1), "artwork_id": uid(2)},
            {"kind": "museum_register", "id": uid(4), "artwork_id": uid(2)}])
        p = Proposal22.model_validate(raw)
        self.assertEqual(len(p.actions), 2)
        self.assertFalse(any(a.kind == "commercial_change" for a in p.actions))

    def test_operational_flags_and_unbounded_values_are_not_accepted(self):
        for key in ("is_available", "tap_position", "is_featured", "published", "approved"):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                Proposal22.model_validate(payload(**{key: True}))

    def test_vocabulary_preserves_input_and_does_not_confirm_identity(self):
        raw = {"id": uid(10), "field": "style", "original_input": "  Ipa  ", "normalized_key": "ipa",
               "candidates": [{"id": uid(11), "value": "IPA", "method": "normalized",
                               "provenance": [{"source": "sql", "beer_id": 7, "field": "style"}]}],
               "decision": "confirmed", "selected_candidate_id": uid(11), "interaction": confirmation()}
        v = VocabularyDecision.model_validate(raw)
        self.assertEqual(v.original_input, "  Ipa  ")
        p = Proposal22.model_validate(payload(vocabulary=[raw], beers=[{"kind": "unresolved", "id": uid(1)}]))
        self.assertEqual(p.beers[0].kind, "unresolved")
        self.assertEqual(p.readiness, "incomplete")
        for change in ({"interaction": None}, {"selected_candidate_id": uid(99)}, {"field": "brewery"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                VocabularyDecision.model_validate({**raw, **change})

    def test_readiness_requires_explicit_closure_and_current_content(self):
        p = commercial_proposal()
        self.assertEqual(p.readiness, "incomplete")
        self.assertFalse(proposal_issues(p))
        p = assess_readiness(p)
        self.assertEqual(p.readiness, "technically_valid")
        with self.assertRaises(ValidationError):
            Proposal22.model_validate({**p.model_dump(mode="json"), "readiness": "prepared_for_review"})
        closed = prepare_for_review(p, Interaction.model_validate(confirmation()), expected_revision=p.revision)
        self.assertEqual(closed.readiness, "prepared_for_review")
        self.assertEqual(p.readiness, "technically_valid")
        with self.assertRaises(ValueError):
            prepare_for_review(p, Interaction.model_validate(confirmation()), expected_revision=99)
        raw = closed.model_dump(mode="json")
        raw["actions"][0]["patch"]["abv"]["value"] = 7
        with self.assertRaises(ValidationError):
            Proposal22.model_validate(raw)

    def test_incomplete_new_beer_and_unknown_operational_identity_cannot_close(self):
        for beer in ({"kind": "new", "id": uid(1)}, {"kind": "unresolved", "id": uid(1)}):
            p = Proposal22.model_validate(payload(beers=[beer], actions=[
                {"kind": "commercial_change", "id": uid(3), "beer_identity_id": uid(1)}]))
            self.assertTrue(proposal_issues(p))
            with self.assertRaises(ValueError):
                prepare_for_review(p, Interaction.model_validate(confirmation()), expected_revision=1)

    def test_complete_new_candidate_is_data_only_and_not_automatically_prepared(self):
        p = Proposal22.model_validate(payload(beers=[{"kind": "new", "id": uid(1),
            "candidate": {"name": "Nueva", "brewery": "Tiburón", "style": "IPA", "prices": {"taster": 0}}}],
            actions=[{"kind": "commercial_change", "id": uid(3), "beer_identity_id": uid(1)}]))
        self.assertEqual(assess_readiness(p).readiness, "technically_valid")
        self.assertEqual(p.readiness, "incomplete")
        self.assertEqual(p.artworks, ())
        self.assertIsNone(p.preparation)

    def test_vocabulary_museum_provenance_and_nonconfirmation_states(self):
        raw = {"id": uid(10), "field": "brewery", "original_input": "Marca", "normalized_key": "marca",
               "candidates": [{"id": uid(11), "value": "Marca", "method": "exact", "provenance": [
                   {"source": "museum", "artwork_id": uid(90), "product_index": 0, "field": "brewery",
                    "confidence": "probable", "evidence": "Atribución de fixture"}]}], "decision": "unresolved"}
        self.assertIsNone(VocabularyDecision.model_validate(raw).selected_candidate_id)
        self.assertEqual(VocabularyDecision.model_validate({**raw, "decision": "rejected", "interaction": confirmation()}).decision, "rejected")
        with self.assertRaises(ValidationError):
            VocabularyDecision.model_validate({**raw, "decision": "rejected"})


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.original = {"name": "Original", "abv": 5, "prices": dict(zip(
            ("taster", "pinta_chica", "pinta_grande", "jarra_chica", "jarra_grande"), (20, 40, 60, 100, 150))),
            "image_url": "/unchanged.jpg", "is_available": False, "tap_position": None, "is_featured": False}

    def test_one_price_preserves_four_prices_and_all_other_fields(self):
        before = deepcopy(self.original)
        for key in self.original["prices"]:
            p = {"prices": {key: {"op": "set", "value": 99}}}
            updated = apply_commercial_patch(self.original, p)
            expected = deepcopy(before)
            expected["prices"][key] = 99
            self.assertEqual(updated, expected)
        self.assertEqual(self.original, before)

    def test_abv_only_preserves_images_and_prices(self):
        updated = apply_commercial_patch(self.original, {"abv": {"op": "set", "value": 6.5}})
        self.assertEqual(updated, {**self.original, "abv": 6.5})

    def test_zero_is_distinct_from_missing_and_explicit_null(self):
        self.assertEqual(apply_commercial_patch(self.original, {"prices": {"taster": {"op": "set", "value": 0}}})["prices"]["taster"], 0)
        for raw in ({"prices": {"taster": None}}, {"prices": None}, {"abv": None}, {"abv": {"op": "set", "value": None}}):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                apply_commercial_patch(self.original, raw)

    def test_noop_intentions_preserve_current_and_previously_entered_values(self):
        self.assertEqual(apply_commercial_patch(self.original, {}), self.original)
        previous = CommercialPatch.model_validate({"abv": {"op": "set", "value": 7}})
        for op in ("keep", "skip", "unknown"):
            self.assertEqual(apply_commercial_patch(self.original, {"abv": {"op": op}, "prices": {"taster": {"op": op}}}), self.original)
            self.assertEqual(correct_patch_field(previous, "abv", {"op": op}), previous)

    def test_clear_requires_explicit_permission_and_is_scoped(self):
        raw = {"prices": {"taster": {"op": "clear"}}}
        with self.assertRaises(ValueError):
            apply_commercial_patch(self.original, raw)
        result = apply_commercial_patch(self.original, raw, allow_clear=frozenset({"prices.taster"}))
        expected = deepcopy(self.original)
        expected["prices"].pop("taster")
        self.assertEqual(result, expected)
        self.assertIsNone(apply_commercial_patch(self.original, {"abv": {"op": "clear"}}, allow_clear=frozenset({"abv"}))["abv"])
        with self.assertRaises(ValidationError):
            apply_commercial_patch(self.original, {"name": {"op": "clear"}}, allow_clear=frozenset({"name"}))

    def test_invalid_keys_values_and_implicit_payloads_fail(self):
        for raw in ({"tap_position": {"op": "set", "value": 1}}, {"prices": {"large": {"op": "set", "value": 1}}},
                    {"abv": 7}, {"abv": {"op": "set", "value": 101}}, {"abv": {"op": "skip", "value": 1}}):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                apply_commercial_patch(self.original, raw)
        for value in (-1, float("nan"), float("inf"), True, "20", 1_000_001):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                apply_commercial_patch(self.original, {"prices": {"taster": {"op": "set", "value": value}}})

    def test_roundtrip_and_copy_are_independent(self):
        patch = CommercialPatch.model_validate({"prices": {"taster": {"op": "set", "value": 1}}})
        self.assertEqual(CommercialPatch.model_validate(json.loads(patch.model_dump_json())), patch)
        result = apply_commercial_patch(self.original, patch)
        result["prices"]["jarra_grande"] = 999
        self.assertEqual(self.original["prices"]["jarra_grande"], 150)

    def test_existing_unrecognized_price_keys_are_preserved_not_editable(self):
        original = deepcopy(self.original)
        original["prices"]["legacy_presentation"] = 77
        result = apply_commercial_patch(original, {"prices": {"taster": {"op": "set", "value": 5}}})
        self.assertEqual(result["prices"]["legacy_presentation"], 77)
        with self.assertRaises(ValidationError):
            apply_commercial_patch(original, {"prices": {"legacy_presentation": {"op": "clear"}}})


class ArtworkTests(unittest.TestCase):
    def test_private_and_museum_references_and_per_artwork_metadata(self):
        p = Proposal22.model_validate(payload(artworks=[artwork(museum={"title": "Tabla", "collection": "tap_list"}),
                                                       artwork(4, "museum", roles=["label"], museum={"title": "Etiqueta", "collection": "etiquetas"})]))
        self.assertEqual([a.source.kind for a in p.artworks], ["private", "museum"])
        self.assertEqual([a.museum.collection for a in p.artworks], ["tap_list", "etiquetas"])
        with self.assertRaises(ValidationError):
            Proposal22.model_validate(payload(artworks=[artwork(source="museum", expected_url="https://arbitrary.invalid")]))

    def test_brewery_representation_and_multi_beer_use_are_independent(self):
        p = Proposal22.model_validate(payload(beers=[existing(), existing(4, 8)], artworks=[artwork(
            represents=[{"kind": "brewery", "id": uid(8), "name": "Cervecería"}], used_for=[uid(1), uid(4)])]))
        self.assertEqual([s.kind for s in p.artworks[0].represents], ["brewery"])
        self.assertEqual(len(p.artworks[0].used_for), 2)
        self.assertEqual(p.actions, ())

    def test_multiple_represented_beers_do_not_imply_operational_reuse(self):
        p = Proposal22.model_validate(payload(beers=[existing(), existing(4, 8)], artworks=[artwork(represents=[
            {"kind": "beer", "id": uid(8), "beer_identity_id": uid(1)},
            {"kind": "beer", "id": uid(9), "beer_identity_id": uid(4)}])]))
        self.assertEqual(len(p.artworks[0].represents), 2)
        self.assertEqual(p.artworks[0].used_for, ())

    def test_unknown_and_empty_semantics_are_honest(self):
        p = Proposal22.model_validate(payload(artworks=[artwork(represents=[{"kind": "unknown", "id": uid(8)}],
            museum={"collection": "tap_list", "title": "Historia"})], actions=[{"kind": "museum_register", "id": uid(3), "artwork_id": uid(2)}]))
        self.assertFalse(proposal_issues(p))
        self.assertEqual(p.artworks[0].museum.semantic_products, [])

    def test_dangling_and_incompatible_relationships_fail(self):
        cases = [payload(artworks=[artwork(used_for=[uid(99)])]),
                 payload(artworks=[artwork(represents=[{"kind": "beer", "id": uid(8), "beer_identity_id": uid(99)}])]),
                 payload(actions=[{"kind": "museum_register", "id": uid(3), "artwork_id": uid(99)}]),
                 payload(artworks=[artwork(source="museum")], actions=[{"kind": "museum_register", "id": uid(3), "artwork_id": uid(2)}]),
                 payload(artworks=[artwork()], actions=[{"kind": "museum_reuse", "id": uid(3), "artwork_id": uid(2)}])]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                Proposal22.model_validate(raw)

    def test_explicit_existing_reuse_and_relationship_actions(self):
        p = Proposal22.model_validate(payload(beers=[existing()], artworks=[artwork(source="museum", used_for=[uid(1)])], actions=[
            {"kind": "museum_reuse", "id": uid(3), "artwork_id": uid(2)},
            {"kind": "artwork_relationship", "id": uid(4), "beer_identity_id": uid(1), "artwork_id": uid(2)}]))
        self.assertEqual(len(p.actions), 2)

    def test_invalid_asset_ids_hashes_and_duplicate_sources_are_rejected(self):
        for ref in ({"kind": "private", "asset_id": "../outside"},
                    {"kind": "museum", "artwork_id": "not-a-uuid"},
                    {"kind": "museum", "artwork_id": uid(90), "expected_sha256": "invalid"}):
            with self.subTest(ref=ref), self.assertRaises(ValidationError):
                Proposal22.model_validate(payload(artworks=[{**artwork(), "source": ref}]))
        with self.assertRaises(ValidationError):
            Proposal22.model_validate(payload(artworks=[artwork(2), artwork(4)]))


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.proposal = commercial_proposal()
        self.state = start_navigation(self.proposal)

    def move(self, state, **kwargs):
        return navigate(self.proposal, state, callback_context(state), **kwargs)

    def test_navigation_does_not_change_content_revision_or_proposal(self):
        before = self.proposal.model_dump_json()
        state = self.state
        for action in ("next", "back", "summary", "skip", "keep", "unknown"):
            state = self.move(state, action=action)
        self.assertEqual(self.proposal.model_dump_json(), before)
        self.assertEqual(state.content_revision, self.proposal.revision)
        self.assertEqual(state.interaction_version, self.state.interaction_version + 6)

    def test_stale_callback_is_rejected_without_mutation(self):
        token = callback_context(self.state)
        newer = self.move(self.state, action="next")
        with self.assertRaises(ValueError):
            navigate(self.proposal, newer, token, action="back")
        self.assertEqual(newer.interaction_version, 2)

    def test_back_after_branch_removal_filters_invalid_paths(self):
        path = f"commercial/{uid(3)}/abv"
        state = self.move(self.state, action="correct", target=path)
        state = self.move(state, action="summary")
        candidate = Proposal22.model_validate({**self.proposal.model_dump(mode="json"), "actions": []})
        updated, state = correct_proposal(self.proposal, state, callback_context(state), candidate)
        state = navigate(updated, state, callback_context(state), action="back")
        self.assertNotIn(path, state.history)
        self.assertIn(state.current_path, valid_paths(updated))

    def test_back_after_subject_removal_uses_stable_identifiers(self):
        p = Proposal22.model_validate(payload(artworks=[artwork(represents=[{"kind": "brewery", "id": uid(8), "name": "Marca"}])]))
        state = start_navigation(p)
        path = f"artwork/{uid(2)}/subject/{uid(8)}/name"
        state = navigate(p, state, callback_context(state), action="correct", target=path)
        state = navigate(p, state, callback_context(state), action="summary")
        raw = p.model_dump(mode="json")
        raw["artworks"][0]["represents"] = []
        p, state = correct_proposal(p, state, callback_context(state), Proposal22.model_validate(raw))
        state = navigate(p, state, callback_context(state), action="back")
        self.assertNotIn(path, state.history)
        self.assertIn(state.current_path, valid_paths(p))

    def test_correction_changes_only_answered_field_and_skip_preserves_it(self):
        path = f"commercial/{uid(3)}/prices.taster"
        state = self.move(self.state, action="correct", target=path)
        p, state = answer_commercial(self.proposal, state, callback_context(state), action_id=UUID(uid(3)),
                                    field="prices.taster", intent={"op": "set", "value": 0})
        self.assertEqual(p.revision, 2)
        self.assertEqual(p.actions[0].patch.abv, self.proposal.actions[0].patch.abv)
        self.assertEqual(p.actions[0].patch.prices.taster.value, 0)
        state = navigate(p, state, callback_context(state), action="correct", target=path)
        p2, state = answer_commercial(p, state, callback_context(state), action_id=UUID(uid(3)),
                                     field="prices.taster", intent={"op": "skip"})
        self.assertEqual(p2, p)
        self.assertEqual(p2.revision, 2)

    def test_restart_resume_and_invalid_state_versions(self):
        p = validate_proposal(json.loads(self.proposal.model_dump_json()))
        state = NavigationState.model_validate(json.loads(self.state.model_dump_json()))
        restored = reconcile_paths(p, state)
        self.assertEqual(restored.content_revision, p.revision)
        self.assertEqual(restored.current_path, state.current_path)
        with self.assertRaises(ValueError):
            navigate(p, restored, callback_context(state), action="next")
        with self.assertRaises(ValidationError):
            NavigationState.model_validate({**state.model_dump(mode="json"), "schema_version": "2.1"})

    def test_invalid_paths_and_wrong_case_fail(self):
        with self.assertRaises(ValueError):
            self.move(self.state, action="correct", target="artwork/0/subject/99/name")
        other = self.state.model_copy(update={"case_id": UUID(uid(500))})
        with self.assertRaises(ValueError):
            reconcile_paths(self.proposal, other)

    def test_content_edit_reopens_prepared_proposal(self):
        p = prepare_for_review(self.proposal, Interaction.model_validate(confirmation()), expected_revision=1)
        state = start_navigation(p)
        state = navigate(p, state, callback_context(state), action="correct", target=f"commercial/{uid(3)}/abv")
        updated, _ = answer_commercial(p, state, callback_context(state), action_id=UUID(uid(3)), field="abv",
                                       intent={"op": "set", "value": 7})
        self.assertEqual(updated.revision, p.revision + 1)
        self.assertEqual(updated.readiness, "incomplete")
        self.assertIsNone(updated.preparation)

    def test_identical_answer_does_not_increment_content_revision(self):
        state = self.move(self.state, action="correct", target=f"commercial/{uid(3)}/abv")
        p, state = answer_commercial(self.proposal, state, callback_context(state), action_id=UUID(uid(3)),
                                     field="abv", intent={"op": "set", "value": 6})
        self.assertEqual(p.revision, self.proposal.revision)
        self.assertGreater(state.interaction_version, self.state.interaction_version)

    def test_answer_cannot_modify_an_unasked_field(self):
        with self.assertRaises(ValueError):
            answer_commercial(self.proposal, self.state, callback_context(self.state), action_id=UUID(uid(3)),
                              field="prices.taster", intent={"op": "set", "value": 4})


from tests import test_editorial as foundation
from app.editorial.models import Draft, Version, Asset, Interview, ProposalRevision
from app.editorial import interview as legacy_interview


class CompatibilityTests(unittest.TestCase):
    setUp = foundation.EditorialTests.setUp
    message = foundation.EditorialTests.message
    dispatch = foundation.EditorialTests.dispatch
    draft = foundation.EditorialTests.draft
    attachment = foundation.EditorialTests.attachment
    start_image = foundation.EditorialTests.start_image
    callback = foundation.EditorialTests.callback
    count = foundation.EditorialTests.count
    assert_catalog_unchanged = foundation.EditorialTests.assert_catalog_unchanged

    def seed22(self, version="2.2"):
        self.start_image()
        p = commercial_proposal()
        state = start_navigation(p)
        with Session(self.engine) as db:
            raw = p.model_dump(mode="json")
            raw["schema_version"] = version
            db.add(ProposalRevision(draft_id=self.draft()["id"], revision=1, payload=raw))
            db.add(Interview(id=self.draft()["id"], revision=state.interaction_version, step="v2.2",
                             history={"schema_version": "2.2", "state": state.model_dump(mode="json")}))
            db.commit()
        return p, state

    def preserved(self):
        with self.engine.connect() as c:
            return {table: c.exec_driver_sql(f'SELECT * FROM "{table}" ORDER BY 1').all() for table in
                    ("editorial_drafts", "editorial_versions", "editorial_assets", "editorial_proposals", "editorial_interviews", "beers")}

    def test_v22_rows_and_assets_cannot_be_processed_by_legacy_editor(self):
        self.seed22()
        before = self.preserved()
        download_count = len(self.transport.downloads)
        with patch("app.services.museum_upload_service.upload_artwork", side_effect=AssertionError("Publication forbidden")):
            for uid_number, command in enumerate(("/obra", "/entrevista", "/continuar", "/corregir", "/cancelar", "/vista"), 10):
                self.dispatch(self.message(uid_number, command))
                self.assertIn("contrato", self.transport.sent[-1]["text"])
                self.assertEqual(self.preserved(), before)
            self.dispatch(self.attachment(uid=20))
            self.dispatch(self.callback(uid=21, operation="new"))
        self.assertEqual(self.preserved(), before)
        self.assertEqual(len(self.transport.downloads), download_count)
        self.assert_catalog_unchanged()

    def test_v22_summary_is_read_only_and_unknown_versions_fail_safely(self):
        for version in ("2.2", "99"):
            if version == "2.2":
                self.seed22(version)
            else:
                # Separate isolated fixture, not an alteration of a historical proposal.
                with Session(self.engine) as db:
                    raw = commercial_proposal().model_dump(mode="json")
                    raw["schema_version"] = version
                    db.add(ProposalRevision(draft_id=self.draft()["id"], revision=2, payload=raw))
                    db.commit()
            before = self.preserved()
            statements = []
            def capture(conn, cursor, statement, parameters, context, many):
                statements.append(statement.strip().split()[0].upper())
            event.listen(self.engine, "before_cursor_execute", capture)
            try:
                self.dispatch(self.message(30 if version == "2.2" else 31, "/resumen"))
            finally:
                event.remove(self.engine, "before_cursor_execute", capture)
            self.assertFalse(set(statements) & {"INSERT", "UPDATE", "DELETE", "REPLACE"})
            self.assertEqual(self.preserved(), before)
            self.assertIn("2.2" if version == "2.2" else "no es compatible", self.transport.sent[-1]["text"])

    def test_serialized_v22_navigation_survives_private_storage_roundtrip(self):
        p, state = self.seed22()
        with Session(self.engine) as db:
            row = db.scalar(select(Interview))
            restored = NavigationState.model_validate(row.history["state"])
            proposal = validate_proposal(db.scalar(select(ProposalRevision)).payload)
        self.assertEqual(restored, state)
        self.assertEqual(proposal, p)
        self.assertEqual(reconcile_paths(proposal, restored).content_revision, p.revision)
        with Session(self.engine) as db:
            with self.assertRaises(ValueError):
                legacy_interview.begin(db, db.scalar(select(Draft)), "board")

    def test_v21_continue_keeps_exact_historical_snapshots_and_asset_references(self):
        self.start_image()
        self.dispatch(self.callback())
        self.dispatch(self.message(4, "/entrevista"))
        before = self.preserved()
        self.dispatch(self.message(5, "/continuar"))
        self.assertEqual(self.preserved(), before)
        self.assertIn("Qué quieres preparar", self.transport.sent[-1]["text"])


class DomainSafetyTests(unittest.TestCase):
    def test_domain_utilities_do_not_connect_write_publish_or_activate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            database = root / "catalog-fixture.sqlite3"
            museum = root / "museum-fixture.json"
            museum.write_text('[{"id":"historical"}]', encoding="utf-8")
            with sqlite3.connect(database) as c:
                c.execute("CREATE TABLE beers(id INTEGER PRIMARY KEY, available BOOLEAN)")
                c.execute("INSERT INTO beers VALUES(1,0)")
            c.close()
            before = database.read_bytes(), museum.read_bytes()
            with patch("sqlite3.connect", side_effect=AssertionError("Operational access forbidden")), \
                    patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")), \
                    patch("app.services.museum_upload_service.upload_artwork", side_effect=AssertionError("Publication forbidden")):
                p = commercial_proposal()
                state = start_navigation(p)
                navigate(p, state, callback_context(state), action="next")
                apply_commercial_patch({"prices": {"taster": 1}, "image_url": "unchanged", "is_available": False},
                                       {"abv": {"op": "set", "value": 5}})
                assess_readiness(p)
                prepare_for_review(p, Interaction.model_validate(confirmation()), expected_revision=1)
            self.assertEqual((database.read_bytes(), museum.read_bytes()), before)


if __name__ == "__main__":
    unittest.main()
