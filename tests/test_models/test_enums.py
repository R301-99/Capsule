from core.models.enums import ContractType, FailureAction, HumanAction


def test_enum_values_are_strings() -> None:
    assert ContractType.ROLE.value == "role"
    assert FailureAction.HUMAN_ESCALATION.value == "human_escalation"
    assert HumanAction.AMEND_CONTRACT.value == "amend_contract"
