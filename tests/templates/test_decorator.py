# Copyright 2018-2020 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Unit tests for the :mod:`pennylane.template.decorator` module.
Integration tests should be placed into ``test_templates.py``.
"""
import pytest
import pennylane as qml
from pennylane.templates.decorator import template


def expected_queue(wires):
    """Expected queue for the dummy template."""
    return [qml.RX(2 * i, wires=[wire]) for i, wire in enumerate(wires)] + [
        qml.RY(3 * i, wires=[wire]) for i, wire in enumerate(wires)
    ]


def dummy_template(wires):
    """Dummy template for template decorator tests."""
    for i, wire in enumerate(wires):
        qml.RX(2 * i, wires=[wire])

    for i, wire in enumerate(wires):
        qml.RY(3 * i, wires=[wire])


@template
def decorated_dummy_template(wires):
    """Already decorated dummy template for template decorator tests."""
    for i, wire in enumerate(wires):
        qml.RX(2 * i, wires=[wire])

    for i, wire in enumerate(wires):
        qml.RY(3 * i, wires=[wire])


class TestDecorator:
    """Tests the template decorator."""

    def test_dummy_template(self):
        """Test the decorator for a dummy template."""

        @template
        def my_template(wires):
            dummy_template(wires)

        res = my_template([0, 1])
        expected = expected_queue([0, 1])

        for res_op, exp_op in zip(res, expected):
            assert res_op.name == exp_op.name
            assert res_op.wires == exp_op.wires
            assert res_op.data == exp_op.data

    def test_decorated_dummy_template(self):
        """Test the decorator for an already decorated template."""
        res = decorated_dummy_template([0, 1])

        expected = expected_queue([0, 1])

        for res_op, exp_op in zip(res, expected):
            assert res_op.name == exp_op.name
            assert res_op.wires == exp_op.wires
            assert res_op.data == exp_op.data

    def test_decorated_decorated_dummy_template(self):
        """Test the decorator for decorating an already decorated template."""

        @template
        def my_template(wires):
            decorated_dummy_template(wires)

        res = my_template([0, 1])
        expected = expected_queue([0, 1])

        for res_op, exp_op in zip(res, expected):
            assert res_op.name == exp_op.name
            assert res_op.wires == exp_op.wires
            assert res_op.data == exp_op.data

    def test_deprecated_decorator(self):
        """Test that the warning is generated."""

        with pytest.warns(
            UserWarning,
            match="The template decorator is deprecated and will be removed in release v0.20.0",
        ):

            @template
            def my_template(wires):
                decorated_dummy_template(wires)

            my_template([0, 1])

    def test_deprecated_decorator_no_warn_if_not_called(self, recwarn):
        """Test that decorating a function with the template decorator does not
        raise a warning if the function is not being called."""

        @template
        def my_template(wires):
            decorated_dummy_template(wires)

        assert len(recwarn) == 0
