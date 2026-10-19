"""The instrument matcher on the rename patterns the spike found (P3, P17, P20)."""

from ai_debt_tracker.ledger.matcher import match, norm_label


def test_stages_in_order():
    a = [{"member": "Notes2027", "rate": 3.3, "maturity_year": 2027},
         {"member": "OldName", "label": "4.600% Senior Notes due 2030 [Member]", "rate": 4.6, "maturity_year": 2030},
         {"member": "A20329.625SeniorNotes", "rate": 9.625, "maturity_year": 2032},
         {"member": "TermLoanA", "maturity_year": 2028, "face": 1_000_000_000}]
    b = [{"member": "Notes2027", "rate": 3.3, "maturity_year": 2027},
         {"member": "FourPointSixZeroZeroPercentSeniorNotesDueTwoThousandThirty", "label": "4.600% Senior Notes due 2030"},
         {"member": "SeniorNotes2032", "rate": 9.63, "maturity_year": 2032},            # P17: rounded in the bulk data
         {"member": "TermLoans2028", "maturity_year": 2028, "carrying": 1_005_000_000}]
    r = match(a, b)
    assert sorted(r.pairs) == [(0, 0, "name"), (1, 1, "label"), (2, 2, "key"), (3, 3, "year+amount")]
    assert r.unmatched_a == [] and r.unmatched_b == []


def test_ambiguous_keys_are_not_guessed():
    """Intel has 5.000% notes due 2031 *and* 2033; two bonds with one key must not be paired."""
    a = [{"member": "x", "rate": 5.0, "maturity_year": 2033}]
    b = [{"member": "y", "rate": 5.0, "maturity_year": 2033}, {"member": "z", "rate": 5.0, "maturity_year": 2033}]
    r = match(a, b)
    assert r.pairs == [] and r.ambiguous_a == [0] and r.unmatched_b == [0, 1]


def test_currency_must_agree():
    a = [{"member": "x", "rate": 3.5, "maturity_year": 2030, "currency": "EUR"}]
    b = [{"member": "y", "rate": 3.5, "maturity_year": 2030, "currency": "USD"}]
    assert match(a, b).pairs == []


def test_new_and_removed_instruments_are_reported():
    a = [{"member": "Matured2026", "rate": 1.0, "maturity_year": 2026}]
    b = [{"member": "New2036", "rate": 5.3, "maturity_year": 2036}]
    r = match(a, b)
    assert r.pairs == [] and r.unmatched_a == [0] and r.unmatched_b == [0]


def test_norm_label():
    assert norm_label("Senior Notes, 3.30% Due 2027 [Member]") == norm_label("senior notes 3.30% due 2027")


def test_normalised_names():
    a = [{"member": "A2017SeniorNotesMember"}, {"member": "ESUNBankTermLoanFacilityDueAugust152027"}]
    b = [{"member": "E.SUNBankTermLoanFacilityDueAugust152027"}, {"member": "A2017SeniorNotes"}]
    assert sorted(match(a, b).pairs) == [(0, 1, "name"), (1, 0, "name")]
