"""Pipeline Service Tests."""
from controller import controller

CONTROLLER = controller.Controller()


def test_test_method():
    """Test test method."""

    entry = "parameter value"
    expected = "result : " + entry

    result = CONTROLLER.test_method(entry)
    assert expected == result

