"""Вердикт сверки хранит согласие отдельно от факта измерения."""

from torrcast.adapters.stream_pack.key_agreement import KeyAgreement


def test_an_unmeasured_agreement_is_not_a_measured_agreement() -> None:
    verdict = KeyAgreement(True, False)

    assert verdict and not verdict.measured
