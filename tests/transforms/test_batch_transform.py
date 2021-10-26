# Copyright 2018-2021 Xanadu Quantum Technologies Inc.

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
Unit tests for the batch transform.
"""

import functools
import pytest

import pennylane as qml
from pennylane import numpy as np


class TestBatchTransform:
    """Unit tests for the batch_transform class"""

    @staticmethod
    @qml.batch_transform
    def my_transform(tape, a, b):
        """Generates two tapes, one with all RX replaced with RY,
        and the other with all RX replaced with RZ."""

        tape1 = qml.tape.QuantumTape()
        tape2 = qml.tape.QuantumTape()

        # loop through all operations on the input tape
        for op in tape.operations + tape.measurements:
            if op.name == "RX":
                wires = op.wires
                param = op.parameters[0]

                with tape1:
                    qml.RY(a * qml.math.abs(param), wires=wires)

                with tape2:
                    qml.RZ(b * qml.math.sin(param), wires=wires)
            else:
                for t in [tape1, tape2]:
                    with t:
                        qml.apply(op)

        def processing_fn(results):
            return qml.math.sum(qml.math.stack(results))

        return [tape1, tape2], processing_fn

    @staticmethod
    def phaseshift_expand(tape):
        return tape.expand(stop_at=lambda obj: obj.name != "PhaseShift")

    @staticmethod
    def expand_logic_with_kwarg(tape, perform_expansion=None, **kwargs):
        if perform_expansion:
            return TestBatchTransform.phaseshift_expand(tape)
        return tape

    def test_error_invalid_callable(self):
        """Test that an error is raised if the transform
        is applied to an invalid function"""

        with pytest.raises(ValueError, match="does not appear to be a valid Python function"):
            qml.batch_transform(5)

    def test_sphinx_build(self, monkeypatch):
        """Test that batch transforms are not created during Sphinx builds"""

        @qml.batch_transform
        def my_transform(tape):
            tape1 = tape.copy()
            tape2 = tape.copy()
            return [tape1, tape2], None

        assert isinstance(my_transform, qml.batch_transform)

        monkeypatch.setenv("SPHINX_BUILD", "1")

        with pytest.warns(UserWarning, match="Batch transformations have been disabled"):

            @qml.batch_transform
            def my_transform(tape):
                tape1 = tape.copy()
                tape2 = tape.copy()
                return [tape1, tape2], None

        assert not isinstance(my_transform, qml.batch_transform)

    def test_none_processing(self):
        """Test that a transform that returns None for a processing function applies
        the identity as the processing function"""

        @qml.batch_transform
        def my_transform(tape):
            tape1 = tape.copy()
            tape2 = tape.copy()
            return [tape1, tape2], None

        with qml.tape.QuantumTape() as tape:
            qml.Hadamard(wires=0)
            qml.expval(qml.PauliX(0))

        tapes, fn = my_transform(tape)
        assert fn(5) == 5

    def test_not_differentiable(self):
        """Test that a non-differentiable transform cannot be differentiated"""

        def my_transform(tape):
            tape1 = tape.copy()
            tape2 = tape.copy()
            return [tape1, tape2], qml.math.sum

        my_transform = qml.batch_transform(my_transform, differentiable=False)

        dev = qml.device("default.qubit", wires=2)

        @my_transform
        @qml.qnode(dev)
        def circuit(x):
            qml.Hadamard(wires=0)
            qml.RY(x, wires=0)
            return qml.expval(qml.PauliX(0))

        res = circuit(0.5)
        assert isinstance(res, float)
        assert not np.allclose(res, 0)

        with pytest.warns(UserWarning, match="Output seems independent of input"):
            qml.grad(circuit)(0.5)

    def test_use_qnode_execution_options(self, mocker):
        """Test that a QNodes execution options are used by the
        batch transform"""
        dev = qml.device("default.qubit", wires=2)
        cache = {}

        @qml.beta.qnode(dev, max_diff=3, cache=cache)
        def circuit(x):
            qml.Hadamard(wires=0)
            qml.RY(x, wires=0)
            return qml.expval(qml.PauliX(0))

        a = 0.1
        b = 0.4
        x = 0.543

        fn = self.my_transform(circuit, a, b)

        spy = mocker.spy(qml, "execute")
        fn(x)
        assert spy.call_args[1]["max_diff"] == 3
        assert spy.call_args[1]["cache"] is cache

    def test_expand_fn(self, mocker):
        """Test that if an expansion function is provided,
        that the input tape is expanded before being transformed."""

        class MyTransform:
            """Dummy class to allow spying to work"""

            def my_transform(self, tape):
                tape1 = tape.copy()
                tape2 = tape.copy()
                return [tape1, tape2], None

        spy_transform = mocker.spy(MyTransform, "my_transform")
        transform_fn = qml.batch_transform(
            MyTransform().my_transform, expand_fn=self.phaseshift_expand
        )

        with qml.tape.QuantumTape() as tape:
            qml.PhaseShift(0.5, wires=0)
            qml.expval(qml.PauliX(0))

        spy_expand = mocker.spy(transform_fn, "expand_fn")

        transform_fn(tape)

        spy_transform.assert_called()
        spy_expand.assert_called()

        input_tape = spy_transform.call_args[0][1]
        assert len(input_tape.operations) == 1
        assert input_tape.operations[0].name == "RZ"
        assert input_tape.operations[0].parameters == [0.5]

    @pytest.mark.parametrize("perform_expansion", [True, False])
    def test_expand_fn_with_kwarg(self, mocker, perform_expansion):
        """Test that kwargs are respected in the expansion."""

        class MyTransform:
            """Dummy class to allow spying to work"""

            def my_transform(self, tape, **kwargs):
                tape1 = tape.copy()
                tape2 = tape.copy()
                return [tape1, tape2], None

        spy_transform = mocker.spy(MyTransform, "my_transform")
        transform_fn = qml.batch_transform(
            MyTransform().my_transform, expand_fn=self.expand_logic_with_kwarg
        )
        with qml.tape.QuantumTape() as tape:
            qml.PhaseShift(0.5, wires=0)
            qml.expval(qml.PauliX(0))

        spy_expand = mocker.spy(transform_fn, "expand_fn")

        transform_fn(tape, perform_expansion=perform_expansion)

        spy_transform.assert_called()
        spy_expand.assert_called()  # The expand_fn of transform_fn always is called

        input_tape = spy_transform.call_args[0][1]
        assert len(input_tape.operations) == 1
        assert input_tape.operations[0].name == ("RZ" if perform_expansion else "PhaseShift")
        assert input_tape.operations[0].parameters == [0.5]

    @pytest.mark.parametrize("perform_expansion", [True, False])
    def test_expand_qnode_with_kwarg(self, mocker, perform_expansion):
        """Test that kwargs are respected in the expansion."""

        class MyTransform:
            """Dummy class to allow spying to work"""

            def my_transform(self, tape, **kwargs):
                tape1 = tape.copy()
                tape2 = tape.copy()
                return [tape1, tape2], None

        spy_transform = mocker.spy(MyTransform, "my_transform")
        transform_fn = qml.batch_transform(
            MyTransform().my_transform, expand_fn=self.expand_logic_with_kwarg
        )

        spy_expand = mocker.spy(transform_fn, "expand_fn")
        dev = qml.device("default.qubit", wires=2)

        @functools.partial(transform_fn, perform_expansion=perform_expansion)
        @qml.qnode(dev)
        def qnode(x):
            qml.PhaseShift(0.5, wires=0)
            return qml.expval(qml.PauliX(0))

        qnode(0.2)

        spy_transform.assert_called()
        spy_expand.assert_called()  # The expand_fn of transform_fn always is called
        input_tape = spy_transform.call_args[0][1]
        assert len(input_tape.operations) == 1
        assert input_tape.operations[0].name == ("RZ" if perform_expansion else "PhaseShift")
        assert input_tape.operations[0].parameters == [0.5]

    def test_parametrized_transform_tape(self):
        """Test that a parametrized transform can be applied
        to a tape"""

        a = 0.1
        b = 0.4
        x = 0.543

        with qml.tape.QuantumTape() as tape:
            qml.Hadamard(wires=0)
            qml.RX(x, wires=0)
            qml.expval(qml.PauliX(0))

        tapes, fn = self.my_transform(tape, a, b)

        assert len(tapes[0].operations) == 2
        assert tapes[0].operations[0].name == "Hadamard"
        assert tapes[0].operations[1].name == "RY"
        assert tapes[0].operations[1].parameters == [a * np.abs(x)]

        assert len(tapes[1].operations) == 2
        assert tapes[1].operations[0].name == "Hadamard"
        assert tapes[1].operations[1].name == "RZ"
        assert tapes[1].operations[1].parameters == [b * np.sin(x)]

    def test_parametrized_transform_qnode(self, mocker):
        """Test that a parametrized transform can be applied
        to a QNode"""

        a = 0.1
        b = 0.4
        x = 0.543

        dev = qml.device("default.qubit", wires=2)

        @qml.qnode(dev)
        def circuit(x):
            qml.Hadamard(wires=0)
            qml.RX(x, wires=0)
            return qml.expval(qml.PauliX(0))

        transform_fn = self.my_transform(circuit, a, b)

        spy = mocker.spy(self.my_transform, "construct")
        res = transform_fn(x)

        spy.assert_called()
        tapes, fn = spy.spy_return

        assert len(tapes[0].operations) == 2
        assert tapes[0].operations[0].name == "Hadamard"
        assert tapes[0].operations[1].name == "RY"
        assert tapes[0].operations[1].parameters == [a * np.abs(x)]

        assert len(tapes[1].operations) == 2
        assert tapes[1].operations[0].name == "Hadamard"
        assert tapes[1].operations[1].name == "RZ"
        assert tapes[1].operations[1].parameters == [b * np.sin(x)]

        expected = fn(dev.batch_execute(tapes))
        assert res == expected

    def test_parametrized_transform_qnode_decorator(self, mocker):
        """Test that a parametrized transform can be applied
        to a QNode as a decorator"""
        a = 0.1
        b = 0.4
        x = 0.543

        dev = qml.device("default.qubit", wires=2)

        @self.my_transform(a, b)
        @qml.qnode(dev)
        def circuit(x):
            qml.Hadamard(wires=0)
            qml.RX(x, wires=0)
            return qml.expval(qml.PauliX(0))

        spy = mocker.spy(self.my_transform, "construct")
        res = circuit(x)

        spy.assert_called()
        tapes, fn = spy.spy_return

        assert len(tapes[0].operations) == 2
        assert tapes[0].operations[0].name == "Hadamard"
        assert tapes[0].operations[1].name == "RY"
        assert tapes[0].operations[1].parameters == [a * np.abs(x)]

        assert len(tapes[1].operations) == 2
        assert tapes[1].operations[0].name == "Hadamard"
        assert tapes[1].operations[1].name == "RZ"
        assert tapes[1].operations[1].parameters == [b * np.sin(x)]

        expected = fn(dev.batch_execute(tapes))
        assert res == expected

    def test_custom_qnode_wrapper(self, capsys):
        """Test that the QNode execution wrapper can be overridden
        if required."""
        a = 0.654
        x = 0.543

        dev = qml.device("default.qubit", wires=2)

        @qml.batch_transform
        def my_transform(tape, a):
            tape1 = tape.copy()
            tape2 = tape.copy()
            return [tape1, tape2], lambda res: a * qml.math.sum(res)

        @my_transform.custom_qnode_wrapper
        def qnode_wrapper(self, qnode, targs, tkwargs):
            wrapper = self.default_qnode_wrapper(qnode, targs, tkwargs)
            assert targs == (a,)
            assert tkwargs == {}
            print("custom wrapper called")
            return wrapper

        @my_transform(a)
        @qml.qnode(dev)
        def circuit(x):
            qml.Hadamard(wires=0)
            qml.RX(x, wires=0)
            return qml.expval(qml.PauliX(0))

        circuit(x)

        captured = capsys.readouterr()
        assert captured.out == "custom wrapper called\n"


@pytest.mark.parametrize("diff_method", ["parameter-shift", "backprop", "finite-diff"])
class TestBatchTransformGradients:
    """Tests for the batch_transform decorator differentiability"""

    @staticmethod
    @qml.batch_transform
    def my_transform(tape, weights):
        """Generates two tapes, one with all RX replaced with RY,
        and the other with all RX replaced with RZ."""

        tape1 = qml.tape.JacobianTape()
        tape2 = qml.tape.JacobianTape()

        # loop through all operations on the input tape
        for op in tape.operations + tape.measurements:
            if op.name == "RX":
                wires = op.wires
                param = op.parameters[0]

                with tape1:
                    qml.RY(weights[0] * qml.math.sin(param), wires=wires)

                with tape2:
                    qml.RZ(weights[1] * qml.math.cos(param), wires=wires)
            else:
                for t in [tape1, tape2]:
                    with t:
                        qml.apply(op)

        def processing_fn(results):
            return qml.math.sum(qml.math.stack(results))

        return [tape1, tape2], processing_fn

    @staticmethod
    def circuit(x):
        """Test ansatz"""
        qml.Hadamard(wires=0)
        qml.RX(x, wires=0)
        return qml.expval(qml.PauliX(0))

    @staticmethod
    def expval(x, weights):
        """Analytic expectation value of the above circuit qfunc"""
        return np.cos(weights[1] * np.cos(x)) + np.cos(weights[0] * np.sin(x))

    def test_differentiable_autograd(self, diff_method):
        """Test that a batch transform is differentiable when using
        autograd"""
        dev = qml.device("default.qubit", wires=2)
        qnode = qml.QNode(self.circuit, dev, interface="autograd", diff_method=diff_method)

        def cost(x, weights):
            return self.my_transform(qnode, weights)(x)

        weights = np.array([0.1, 0.2], requires_grad=True)
        x = np.array(0.543, requires_grad=True)

        res = cost(x, weights)
        assert np.allclose(res, self.expval(x, weights))

        grad = qml.grad(cost)(x, weights)
        expected = qml.grad(self.expval)(x, weights)
        assert all(np.allclose(g, e) for g, e in zip(grad, expected))

    def test_differentiable_tf(self, diff_method):
        """Test that a batch transform is differentiable when using
        TensorFlow"""
        tf = pytest.importorskip("tensorflow")
        dev = qml.device("default.qubit", wires=2)
        qnode = qml.QNode(self.circuit, dev, interface="tf", diff_method=diff_method)

        weights = tf.Variable([0.1, 0.2], dtype=tf.float64)
        x = tf.Variable(0.543, dtype=tf.float64)

        with tf.GradientTape() as tape:
            res = self.my_transform(qnode, weights)(x)

        assert np.allclose(res, self.expval(x, weights))

        grad = tape.gradient(res, [x, weights])
        expected = qml.grad(self.expval)(x.numpy(), weights.numpy())
        assert all(np.allclose(g, e) for g, e in zip(grad, expected))

    def test_differentiable_torch(self, diff_method):
        """Test that a batch transform is differentiable when using
        PyTorch"""
        torch = pytest.importorskip("torch")
        dev = qml.device("default.qubit", wires=2)
        qnode = qml.QNode(self.circuit, dev, interface="torch", diff_method=diff_method)

        weights = torch.tensor([0.1, 0.2], requires_grad=True)
        x = torch.tensor(0.543, requires_grad=True)

        res = self.my_transform(qnode, weights)(x)
        expected = self.expval(x.detach().numpy(), weights.detach().numpy())
        assert np.allclose(res.detach().numpy(), expected)

        res.backward()
        expected = qml.grad(self.expval)(x.detach().numpy(), weights.detach().numpy())
        assert np.allclose(x.grad, expected[0])
        assert np.allclose(weights.grad, expected[1])

    def test_differentiable_jax(self, diff_method):
        """Test that a batch transform is differentiable when using
        jax"""
        jax = pytest.importorskip("jax")
        dev = qml.device("default.qubit", wires=2)
        qnode = qml.QNode(self.circuit, dev, interface="jax", diff_method=diff_method)

        def cost(x, weights):
            return self.my_transform(qnode, weights, max_diff=1)(x)

        weights = jax.numpy.array([0.1, 0.2])
        x = jax.numpy.array(0.543)

        res = cost(x, weights)
        assert np.allclose(res, self.expval(x, weights))

        grad = jax.grad(cost, argnums=[0, 1])(x, weights)
        expected = qml.grad(self.expval)(np.array(x), np.array(weights))
        assert all(np.allclose(g, e) for g, e in zip(grad, expected))
