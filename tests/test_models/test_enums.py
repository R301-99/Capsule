from core.models.enums import ContractType, GateResult


def test_enum_values_are_strings() -> None:
    assert ContractType.ROLE.value == "role"
    assert GateResult.PASS.value == "pass"
