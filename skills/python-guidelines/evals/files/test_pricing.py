"""Tests for the pricing module (pricing.apply_discount, pricing.load_rules)."""

import unittest
from unittest import mock

import pytest

import pricing


class TestPricing(unittest.TestCase):
    def test_apply_discount_calls_round_correctly(self):
        with mock.patch("pricing.round", create=True) as mock_round:
            with mock.patch("pricing._lookup_rate") as mock_rate:
                mock_rate.return_value = 0.1
                pricing.apply_discount(100.0, "GOLD")
                mock_rate.assert_called_once_with("GOLD")
                mock_round.assert_called_once()

    def test_load_rules(self):
        # Write a rules file next to the source so load_rules can find it.
        f = open("rules.json", "w")
        f.write('{"GOLD": 0.1}')
        rules = pricing.load_rules("rules.json")
        assert rules["GOLD"] == 0.1


@pytest.mark.parametrize("tier", ["GOLD", "SILVER"])
def test_tiers_do_not_crash(tier):
    pricing.apply_discount(50.0, tier)
