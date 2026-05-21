"""SQLite persistence for profiles, children, and measurements.

The store enforces per-profile isolation: every read returns only rows
that belong to the calling profile, and writes go to the calling
profile's tenant."""

from __future__ import annotations

from datetime import date

import pytest

from growth import auth, store


@pytest.fixture
def alice(tmp_db):
    return store.create_profile("Alice", "alice-passcode")


@pytest.fixture
def bob(tmp_db, alice):
    # `alice` already triggered tmp_db; reuse the same DB for bob.
    return store.create_profile("Bob", "bob-passcode")


class TestProfiles:
    def test_create_and_authenticate(self, tmp_db):
        p = store.create_profile("Carol", "carol123")
        signed_in = store.authenticate("Carol", "carol123")
        assert signed_in is not None
        assert signed_in.id == p.id

    def test_authenticate_is_case_insensitive_on_name(self, tmp_db):
        store.create_profile("Carol", "carol123")
        assert store.authenticate("carol", "carol123") is not None
        assert store.authenticate("CAROL", "carol123") is not None

    def test_authenticate_rejects_wrong_passcode(self, tmp_db):
        store.create_profile("Carol", "carol123")
        assert store.authenticate("Carol", "wrong-one") is None

    def test_authenticate_rejects_unknown_name(self, tmp_db):
        assert store.authenticate("Dave", "anything") is None

    def test_authenticate_rejects_empty(self, tmp_db):
        store.create_profile("Carol", "carol123")
        assert store.authenticate("", "carol123") is None
        assert store.authenticate("Carol", "") is None

    def test_duplicate_profile_name_rejected(self, tmp_db):
        store.create_profile("Carol", "carol123")
        with pytest.raises(ValueError):
            store.create_profile("Carol", "different456")

    def test_duplicate_profile_name_rejected_case_insensitive(self, tmp_db):
        store.create_profile("Carol", "carol123")
        with pytest.raises(ValueError):
            store.create_profile("carol", "different456")

    def test_short_passcode_rejected(self, tmp_db):
        with pytest.raises(auth.InvalidPasscode):
            store.create_profile("Carol", "abc")  # too short

    def test_blank_name_rejected(self, tmp_db):
        with pytest.raises(ValueError):
            store.create_profile("   ", "carol123")


class TestChildrenScoping:
    def test_child_visible_only_to_owning_profile(self, tmp_db, alice, bob):
        cid = store.add_child(alice.id, "Ada", "girl", date(2025, 1, 1))
        # Alice sees Ada; Bob sees nothing.
        assert [c.name for c in store.list_children(alice.id)] == ["Ada"]
        assert store.list_children(bob.id) == []
        # Direct id lookup is also scoped: Bob can't reach Alice's child.
        assert store.get_child(cid, alice.id) is not None
        assert store.get_child(cid, bob.id) is None

    def test_delete_child_only_works_within_profile(self, tmp_db, alice, bob):
        cid = store.add_child(alice.id, "Ada", "girl", date(2025, 1, 1))
        # Bob tries to delete Alice's child — should be a no-op.
        store.delete_child(cid, bob.id)
        assert store.get_child(cid, alice.id) is not None

        store.delete_child(cid, alice.id)
        assert store.get_child(cid, alice.id) is None

    def test_list_children_sorted_by_name_within_profile(self, tmp_db, alice):
        store.add_child(alice.id, "Zoe", "girl", date(2025, 1, 1))
        store.add_child(alice.id, "Amir", "boy", date(2025, 2, 1))
        names = [c.name for c in store.list_children(alice.id)]
        assert names == ["Amir", "Zoe"]


class TestMeasurementsScoping:
    def test_add_measurement_for_other_profiles_child_rejected(self, tmp_db, alice, bob):
        cid = store.add_child(alice.id, "Ada", "girl", date(2025, 1, 1))
        with pytest.raises(ValueError):
            store.add_measurement(bob.id, cid, date(2025, 6, 1), 6.5, 65.0, 42.0)

    def test_list_measurements_blocks_cross_profile_reads(self, tmp_db, alice, bob):
        cid = store.add_child(alice.id, "Ada", "girl", date(2025, 1, 1))
        store.add_measurement(alice.id, cid, date(2025, 6, 1), 6.5, 65.0, 42.0)
        assert len(store.list_measurements(alice.id, cid)) == 1
        # Bob asking for Alice's child returns nothing, not an error.
        assert store.list_measurements(bob.id, cid) == []

    def test_delete_measurement_blocks_cross_profile_writes(self, tmp_db, alice, bob):
        cid = store.add_child(alice.id, "Ada", "girl", date(2025, 1, 1))
        mid = store.add_measurement(alice.id, cid, date(2025, 6, 1), 6.5, 65.0, 42.0)
        # Bob tries to delete Alice's measurement — should not affect anything.
        store.delete_measurement(bob.id, mid)
        assert len(store.list_measurements(alice.id, cid)) == 1
        # Owner can delete normally.
        store.delete_measurement(alice.id, mid)
        assert store.list_measurements(alice.id, cid) == []

    def test_measurements_sorted_by_date(self, tmp_db, alice):
        cid = store.add_child(alice.id, "Iris", "girl", date(2025, 1, 1))
        store.add_measurement(alice.id, cid, date(2025, 5, 1), 5.0, None, None)
        store.add_measurement(alice.id, cid, date(2025, 3, 1), 4.0, None, None)
        store.add_measurement(alice.id, cid, date(2025, 4, 1), 4.5, None, None)
        dates = [m.taken_on for m in store.list_measurements(alice.id, cid)]
        assert dates == [date(2025, 3, 1), date(2025, 4, 1), date(2025, 5, 1)]

    def test_partial_measurement_allows_none(self, tmp_db, alice):
        cid = store.add_child(alice.id, "Tom", "boy", date(2025, 1, 1))
        store.add_measurement(alice.id, cid, date(2025, 3, 1), 4.0, None, None)
        m = store.list_measurements(alice.id, cid)[0]
        assert m.weight_kg == 4.0
        assert m.length_cm is None
        assert m.head_circ_cm is None

    def test_delete_child_cascades_to_measurements(self, tmp_db, alice):
        cid = store.add_child(alice.id, "Mira", "girl", date(2025, 1, 1))
        store.add_measurement(alice.id, cid, date(2025, 6, 1), 6.5, 65.0, 42.0)
        store.delete_child(cid, alice.id)
        # Re-list with a re-issued id (will be None — child gone).
        assert store.list_measurements(alice.id, cid) == []


class TestSchema:
    def test_sex_check_constraint(self, tmp_db, alice):
        with pytest.raises(Exception):
            store.add_child(alice.id, "X", "unknown", date(2025, 1, 1))  # type: ignore[arg-type]
