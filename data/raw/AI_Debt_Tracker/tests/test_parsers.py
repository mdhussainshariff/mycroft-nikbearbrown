"""The member parser on the real member names the feasibility spike tripped over (DESIGN.md §3.4)."""

import pytest

from ai_debt_tracker.ledger.parsers import parse_member, rates_match, split_camel


@pytest.mark.parametrize("name,label,rate,year,kind", [
    # P20: numbers spelled out
    ("FourPointSixZeroZeroPercentSeniorNotesDueTwoThousandThirty", None, 4.6, 2030, "notes"),
    ("FourPointSixZeroPercentNotesDueTwoThousandTwentySevenMember", None, 4.6, 2027, "notes"),
    ("SeniorNotesFourPointSixZeroPercentDueTwentyThirtyOneMember", None, 4.6, 2031, "notes"),
    # P20: the typo the spike found in Equinix ("Fieve")
    ("ThreePointTwoFieveZeroPercentSeniorNotesDueTwoThousandTwentyNine", None, 3.25, 2029, "notes"),
    # P3: digits in the name
    ("Notes3.30Due2027", None, 3.3, 2027, "notes"),
    ("SeniorNotes3.30Due2027Member", "Senior Notes, 3.30% Due 2027 [Member]", 3.3, 2027, "notes"),
    ("ConvertibleNotes2030Member", "Convertible Notes, 2030 [Member]", None, 2030, "convertible"),
    ("A4.750SeniorNotesDue2031", None, 4.75, 2031, "notes"),
    ("FourPointSixZeroPercentUnsecuredSeniorNotesDue2036InterestPayableJanuary15July15Member", None, 4.6, 2036, "notes"),
])
def test_rate_and_maturity(name, label, rate, year, kind):
    p = parse_member(name, label)
    assert p.rate == rate
    assert p.maturity_year == year
    assert p.kind == kind
    assert not p.offering


@pytest.mark.parametrize("name", ["A2026USDollarNotes", "March2026SeniorUnsecuredNotes", "November2025Debt"])
def test_offerings_are_not_bonds(name):
    """P18: issue-date groups carry an issue year, which must not be read as a maturity."""
    p = parse_member(name)
    assert p.offering
    assert p.maturity_year is None
    assert p.key() is None


@pytest.mark.parametrize("name,kind", [
    ("TwoThousandTwentyFourRevolvingCreditFacility", "revolver"),
    ("DelayedDrawTermLoanFacilityTwo", "delayed_draw"),
    ("TermLoans", "term_loan"),
    ("CommercialPaper", "commercial_paper"),
])
def test_facilities_have_no_invented_maturity(name, kind):
    p = parse_member(name)
    assert p.kind == kind
    assert p.maturity_year is None  # an agreement year is not a due date


def test_label_beats_name_and_disagreement_is_noted():
    p = parse_member("Notes4.75Due2031", "4.875% Notes due 2031")
    assert p.rate == 4.875 and p.source == "label"
    assert any("disagrees" in n for n in p.notes)


def test_currency_and_floating():
    p = parse_member("FloatingRateEuroNotesDue2028")
    assert p.currency == "EUR" and p.floating and p.maturity_year == 2028


def test_typo_fix_never_touches_ordinary_words():
    assert "Notes" in split_camel("SeniorNotesDue2030")
    assert parse_member("SeniorNoteDue2030").rate is None


def test_rate_tolerance_p17():
    assert rates_match(6.125, 6.13)
    assert rates_match(9.625, 9.63)
    assert not rates_match(6.125, 6.25)
    assert not rates_match(None, 6.1)


@pytest.mark.parametrize("name,label,year", [
    ("A2029NotesMember", "2029 Notes [Member]", 2029),
    ("May2029NotesMember", "May 2029 Notes [Member]", 2029),
    ("TwoThousandThirtyThreeSeniorNotesMember", "Two Thousand Thirty Three Senior Notes [Member]", 2033),
    ("NotesPayableMaturityDateOfJune920282Member", "Notes Payable, Maturity Date Of June 9, 2028, 2 [Member]", 2028),
])
def test_undated_years_after_the_report_are_maturities(name, label, year):
    p = parse_member(name, label, as_of_year=2026)
    assert p.maturity_year == year and not p.offering


def test_issue_year_groups_stay_offerings_with_report_year():
    assert parse_member("A2026USDollarNotes", None, as_of_year=2026).offering
    assert parse_member("November2025Debt", None, as_of_year=2026).offering


def test_typo_at_the_edge_of_a_number_run():
    p = parse_member("TwelePointZeroPercentageSeniorUnsecuredConvertibleNotesDue2029")
    assert p.rate == 12.0 and p.maturity_year == 2029 and p.kind == "convertible"


@pytest.mark.parametrize("name,rate,year", [("A20319.00SeniorNotes", 9.0, 2031), ("A20329.625SeniorNotes", 9.625, 2032)])
def test_year_glued_to_coupon(name, rate, year):
    p = parse_member(name, as_of_year=2026)
    assert (p.rate, p.maturity_year) == (rate, year)
