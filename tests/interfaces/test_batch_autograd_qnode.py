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
"""Integration tests for using the autograd interface with a QNode"""
import pytest
from pennylane import numpy as np

import pennylane as qml
from pennylane.new_qnode import qnode, QNode
from pennylane.tape import JacobianTape

qubit_device_and_diff_method = [
    ["default.qubit", "finite-diff", "backward"],
    ["default.qubit", "parameter-shift", "backward"],
    ["default.qubit", "backprop", "forward"],
    ["default.qubit", "adjoint", "forward"],
    ["default.qubit", "adjoint", "backward"],
]


@pytest.mark.parametrize("dev_name,diff_method,mode", qubit_device_and_diff_method)
class TestQNode:
    """Test that using the QNode with Autograd integrates with the PennyLane stack"""

    def test_nondiff_param_unwrapping(self, dev_name, diff_method, mode, mocker):
        """Test that non-differentiable parameters are correctly unwrapped
        to NumPy ndarrays or floats (if 0-dimensional)"""
        if diff_method != "parameter-shift":
            pytest.skip("Test only supports parameter-shift")

        dev = qml.device("default.qubit", wires=1)

        @qnode(dev, interface="autograd", diff_method="parameter-shift")
        def circuit(x, y):
            qml.RX(x[0], wires=0)
            qml.Rot(*x[1:], wires=0)
            qml.RY(y[0], wires=0)
            return qml.expval(qml.PauliZ(0))

        x = np.array([0.1, 0.2, 0.3, 0.4], requires_grad=False)
        y = np.array([0.5], requires_grad=True)

        param_data = []

        def mock_apply(*args, **kwargs):
            for op in args[0]:
                param_data.extend(op.data.copy())

        mocker.patch.object(dev, "apply", side_effect=mock_apply)
        circuit(x, y)
        assert param_data == [0.1, 0.2, 0.3, 0.4, 0.5]
        assert not any(isinstance(p, np.tensor) for p in param_data)

        # test the jacobian works correctly
        param_data = []
        qml.grad(circuit)(x, y)
        assert param_data == [
            0.1,
            0.2,
            0.3,
            0.4,
            0.5,
            0.1,
            0.2,
            0.3,
            0.4,
            0.5 + np.pi / 2,
            0.1,
            0.2,
            0.3,
            0.4,
            0.5 - np.pi / 2,
        ]
        assert not any(isinstance(p, np.tensor) for p in param_data)

    def test_execution_no_interface(self, dev_name, diff_method, mode):
        """Test execution works without an interface"""
        if diff_method == "backprop":
            pytest.skip("Test does not support backprop")

        dev = qml.device(dev_name, wires=1)

        @qnode(dev, interface=None)
        def circuit(a):
            qml.RY(a, wires=0)
            qml.RX(0.2, wires=0)
            return qml.expval(qml.PauliZ(0))

        a = np.array(0.1, requires_grad=True)

        res = circuit(a)

        assert circuit.qtape.interface == None

        # without the interface, the QNode simply returns a scalar array
        assert isinstance(res, np.ndarray)
        assert res.shape == tuple()

        # gradients should cause an error
        with pytest.raises(TypeError, match="must be real number, not ArrayBox"):
            qml.grad(circuit)(a)

    def test_execution_with_interface(self, dev_name, diff_method, mode):
        """Test execution works with the interface"""
        if diff_method == "backprop":
            pytest.skip("Test does not support backprop")

        dev = qml.device(dev_name, wires=1)

        @qnode(dev, interface="autograd", diff_method=diff_method)
        def circuit(a):
            qml.RY(a, wires=0)
            qml.RX(0.2, wires=0)
            return qml.expval(qml.PauliZ(0))

        a = np.array(0.1, requires_grad=True)
        circuit(a)

        assert circuit.interface == "autograd"

        # the tape is able to deduce trainable parameters
        assert circuit.qtape.trainable_params == {0}

        # gradients should work
        grad = qml.grad(circuit)(a)
        assert isinstance(grad, float)
        assert grad.shape == tuple()

    def test_jacobian(self, dev_name, diff_method, mode, mocker, tol):
        """Test jacobian calculation"""
        if diff_method == "parameter-shift":
            spy = mocker.spy(qml.gradients.param_shift, "transform_fn")
        elif diff_method == "finite-diff":
            spy = mocker.spy(qml.gradients.finite_diff, "transform_fn")

        a = np.array(0.1, requires_grad=True)
        b = np.array(0.2, requires_grad=True)

        dev = qml.device(dev_name, wires=2)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit(a, b):
            qml.RY(a, wires=0)
            qml.RX(b, wires=1)
            qml.CNOT(wires=[0, 1])
            return [qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliY(1))]

        res = circuit(a, b)

        assert circuit.qtape.trainable_params == {0, 1}
        assert res.shape == (2,)

        expected = [np.cos(a), -np.cos(a) * np.sin(b)]
        assert np.allclose(res, expected, atol=tol, rtol=0)

        res = qml.jacobian(circuit)(a, b)
        expected = [[-np.sin(a), 0], [np.sin(a) * np.sin(b), -np.cos(a) * np.cos(b)]]
        assert np.allclose(res, expected, atol=tol, rtol=0)

        if diff_method in ("parameter-shift", "finite-diff"):
            spy.assert_called()

    def test_jacobian_no_evaluate(self, dev_name, diff_method, mode, mocker, tol):
        """Test jacobian calculation when no prior circuit evaluation has been performed"""
        if diff_method == "parameter-shift":
            spy = mocker.spy(qml.gradients.param_shift, "transform_fn")
        elif diff_method == "finite-diff":
            spy = mocker.spy(qml.gradients.finite_diff, "transform_fn")

        a = np.array(0.1, requires_grad=True)
        b = np.array(0.2, requires_grad=True)

        dev = qml.device(dev_name, wires=2)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit(a, b):
            qml.RY(a, wires=0)
            qml.RX(b, wires=1)
            qml.CNOT(wires=[0, 1])
            return [qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliY(1))]

        jac_fn = qml.jacobian(circuit)
        res = jac_fn(a, b)
        expected = [[-np.sin(a), 0], [np.sin(a) * np.sin(b), -np.cos(a) * np.cos(b)]]
        assert np.allclose(res, expected, atol=tol, rtol=0)

        if diff_method in ("parameter-shift", "finite-diff"):
            spy.assert_called()

        # call the Jacobian with new parameters
        a = np.array(0.6, requires_grad=True)
        b = np.array(0.832, requires_grad=True)

        res = jac_fn(a, b)
        expected = [[-np.sin(a), 0], [np.sin(a) * np.sin(b), -np.cos(a) * np.cos(b)]]
        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_jacobian_options(self, dev_name, diff_method, mode, mocker, tol):
        """Test setting jacobian options"""
        if diff_method == "backprop":
            pytest.skip("Test does not support backprop")

        spy = mocker.spy(qml.gradients.finite_diff, "transform_fn")

        a = np.array([0.1, 0.2], requires_grad=True)

        dev = qml.device("default.qubit", wires=1)

        @qnode(dev, interface="autograd", h=1e-8, order=2)
        def circuit(a):
            qml.RY(a[0], wires=0)
            qml.RX(a[1], wires=0)
            return qml.expval(qml.PauliZ(0))

        qml.jacobian(circuit)(a)

        for args in spy.call_args_list:
            assert args[1]["order"] == 2
            assert args[1]["h"] == 1e-8

    def test_changing_trainability(self, dev_name, diff_method, mode, mocker, tol):
        """Test changing the trainability of parameters changes the
        number of differentiation requests made"""
        if diff_method != "parameter-shift":
            pytest.skip("Test only supports parameter-shift")

        a = np.array(0.1, requires_grad=True)
        b = np.array(0.2, requires_grad=True)

        dev = qml.device("default.qubit", wires=2)

        @qnode(dev, interface="autograd", diff_method="parameter-shift")
        def circuit(a, b):
            qml.RY(a, wires=0)
            qml.RX(b, wires=1)
            qml.CNOT(wires=[0, 1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliY(1))

        def loss(a, b):
            return np.sum(circuit(a, b))

        grad_fn = qml.grad(loss)
        spy = mocker.spy(qml.gradients.param_shift, "transform_fn")
        res = grad_fn(a, b)

        # the tape has reported both arguments as trainable
        assert circuit.qtape.trainable_params == {0, 1}

        expected = [-np.sin(a) + np.sin(a) * np.sin(b), -np.cos(a) * np.cos(b)]
        assert np.allclose(res, expected, atol=tol, rtol=0)

        # The parameter-shift rule has been called for each argument
        assert len(spy.spy_return[0]) == 4

        # make the second QNode argument a constant
        a = np.array(0.54, requires_grad=True)
        b = np.array(0.8, requires_grad=False)

        res = grad_fn(a, b)

        # the tape has reported only the first argument as trainable
        assert circuit.qtape.trainable_params == {0}

        expected = [-np.sin(a) + np.sin(a) * np.sin(b)]
        assert np.allclose(res, expected, atol=tol, rtol=0)

        # The parameter-shift rule has been called only once
        assert len(spy.spy_return[0]) == 2

        # trainability also updates on evaluation
        a = np.array(0.54, requires_grad=False)
        b = np.array(0.8, requires_grad=True)
        circuit(a, b)
        assert circuit.qtape.trainable_params == {1}

    def test_classical_processing(self, dev_name, diff_method, mode, tol):
        """Test classical processing within the quantum tape"""
        a = np.array(0.1, requires_grad=True)
        b = np.array(0.2, requires_grad=False)
        c = np.array(0.3, requires_grad=True)

        dev = qml.device(dev_name, wires=1)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit(a, b, c):
            qml.RY(a * c, wires=0)
            qml.RZ(b, wires=0)
            qml.RX(c + c ** 2 + np.sin(a), wires=0)
            return qml.expval(qml.PauliZ(0))

        res = qml.jacobian(circuit)(a, b, c)

        if diff_method == "finite-diff":
            assert circuit.qtape.trainable_params == {0, 2}
            tape_params = np.array(circuit.qtape.get_parameters())
            assert np.all(tape_params == [a * c, c + c ** 2 + np.sin(a)])

        assert res.shape == (2,)

    def test_no_trainable_parameters(self, dev_name, diff_method, mode, tol):
        """Test evaluation and Jacobian if there are no trainable parameters"""
        dev = qml.device(dev_name, wires=2)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit(a, b):
            qml.RY(a, wires=0)
            qml.RX(b, wires=0)
            qml.CNOT(wires=[0, 1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        a = np.array(0.1, requires_grad=False)
        b = np.array(0.2, requires_grad=False)

        res = circuit(a, b)

        if diff_method == "finite-diff":
            assert circuit.qtape.trainable_params == set()

        assert res.shape == (2,)
        assert isinstance(res, np.ndarray)

        assert not qml.jacobian(circuit)(a, b)

        def cost(a, b):
            return np.sum(circuit(a, b))

        with pytest.warns(UserWarning, match="Output seems independent of input"):
            grad = qml.grad(cost)(a, b)

        assert grad == tuple()

    def test_matrix_parameter(self, dev_name, diff_method, mode, tol):
        """Test that the autograd interface works correctly
        with a matrix parameter"""
        U = np.array([[0, 1], [1, 0]], requires_grad=False)
        a = np.array(0.1, requires_grad=True)

        dev = qml.device(dev_name, wires=2)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit(U, a):
            qml.QubitUnitary(U, wires=0)
            qml.RY(a, wires=0)
            return qml.expval(qml.PauliZ(0))

        res = circuit(U, a)

        if diff_method == "finite-diff":
            assert circuit.qtape.trainable_params == {1}

        res = qml.grad(circuit)(U, a)
        assert np.allclose(res, np.sin(a), atol=tol, rtol=0)

    def test_gradient_non_differentiable_exception(self, dev_name, diff_method, mode):
        """Test that an exception is raised if non-differentiable data is
        differentiated"""
        dev = qml.device(dev_name, wires=2)

        @qnode(dev, interface="autograd", diff_method=diff_method)
        def circuit(data1):
            qml.templates.AmplitudeEmbedding(data1, wires=[0, 1])
            return qml.expval(qml.PauliZ(0))

        grad_fn = qml.grad(circuit, argnum=0)
        data1 = np.array([0, 1, 1, 0], requires_grad=False) / np.sqrt(2)

        with pytest.raises(qml.numpy.NonDifferentiableError, match="is non-differentiable"):
            grad_fn(data1)

    @pytest.mark.xfail
    def test_differentiable_expand(self, dev_name, diff_method, mode, tol):
        """Test that operation and nested tapes expansion
        is differentiable"""

        class U3(qml.U3):
            def expand(self):
                theta, phi, lam = self.data
                wires = self.wires

                with JacobianTape() as tape:
                    qml.Rot(lam, theta, -lam, wires=wires)
                    qml.PhaseShift(phi + lam, wires=wires)

                return tape

        dev = qml.device(dev_name, wires=1)
        a = np.array(0.1, requires_grad=False)
        p = np.array([0.1, 0.2, 0.3], requires_grad=True)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit(a, p):
            qml.RX(a, wires=0)
            U3(p[0], p[1], p[2], wires=0)
            return qml.expval(qml.PauliX(0))

        res = circuit(a, p)

        if diff_method == "finite-diff":
            assert circuit.qtape.trainable_params == {1, 2, 3, 4}
        elif diff_method == "backprop":
            # For a backprop device, no interface wrapping is performed, and JacobianTape.jacobian()
            # is never called. As a result, JacobianTape.trainable_params is never set --- the ML
            # framework uses its own backprop logic and its own bookkeeping re: trainable parameters.
            assert circuit.qtape.trainable_params == {0, 1, 2, 3, 4}

        assert [i.name for i in circuit.qtape.operations] == ["RX", "Rot", "PhaseShift"]

        if diff_method == "finite-diff":
            assert np.all(circuit.qtape.get_parameters() == [p[2], p[0], -p[2], p[1] + p[2]])
        elif diff_method == "backprop":
            # In backprop mode, all parameters are returned.
            assert np.all(circuit.qtape.get_parameters() == [a, p[2], p[0], -p[2], p[1] + p[2]])

        expected = np.cos(a) * np.cos(p[1]) * np.sin(p[0]) + np.sin(a) * (
            np.cos(p[2]) * np.sin(p[1]) + np.cos(p[0]) * np.cos(p[1]) * np.sin(p[2])
        )
        assert np.allclose(res, expected, atol=tol, rtol=0)

        res = qml.grad(circuit)(a, p)
        expected = np.array(
            [
                np.cos(p[1]) * (np.cos(a) * np.cos(p[0]) - np.sin(a) * np.sin(p[0]) * np.sin(p[2])),
                np.cos(p[1]) * np.cos(p[2]) * np.sin(a)
                - np.sin(p[1])
                * (np.cos(a) * np.sin(p[0]) + np.cos(p[0]) * np.sin(a) * np.sin(p[2])),
                np.sin(a)
                * (np.cos(p[0]) * np.cos(p[1]) * np.cos(p[2]) - np.sin(p[1]) * np.sin(p[2])),
            ]
        )
        assert np.allclose(res, expected, atol=tol, rtol=0)


class TestShotsIntegration:
    """Test that the QNode correctly changes shot value, and
    differentiates it."""

    def test_changing_shots(self, mocker, tol):
        """Test that changing shots works on execution"""
        dev = qml.device("default.qubit", wires=2, shots=None)
        a, b = np.array([0.543, -0.654], requires_grad=True)

        @qnode(dev, diff_method=qml.gradients.param_shift)
        def circuit(a, b):
            qml.RY(a, wires=0)
            qml.RX(b, wires=1)
            qml.CNOT(wires=[0, 1])
            return qml.expval(qml.PauliY(1))

        spy = mocker.spy(dev, "sample")

        # execute with device default shots (None)
        res = circuit(a, b)
        assert np.allclose(res, -np.cos(a) * np.sin(b), atol=tol, rtol=0)
        spy.assert_not_called()

        # execute with shots=100
        res = circuit(a, b, shots=100)
        spy.assert_called()
        assert spy.spy_return.shape == (100,)

        # device state has been unaffected
        assert dev.shots is None
        spy = mocker.spy(dev, "sample")
        res = circuit(a, b)
        assert np.allclose(res, -np.cos(a) * np.sin(b), atol=tol, rtol=0)
        spy.assert_not_called()

    def test_gradient_integration(self, tol):
        """Test that temporarily setting the shots works
        for gradient computations"""
        dev = qml.device("default.qubit", wires=2, shots=None)
        a, b = np.array([0.543, -0.654], requires_grad=True)

        @qnode(dev, diff_method=qml.gradients.param_shift)
        def cost_fn(a, b):
            qml.RY(a, wires=0)
            qml.RX(b, wires=1)
            qml.CNOT(wires=[0, 1])
            return qml.expval(qml.PauliY(1))

        res = qml.jacobian(cost_fn)(a, b, shots=[10000, 10000, 10000])
        assert dev.shots is None
        assert len(res) == 3

        expected = [np.sin(a) * np.sin(b), -np.cos(a) * np.cos(b)]
        assert np.allclose(np.mean(res, axis=0), expected, atol=0.1, rtol=0)

    def test_update_diff_method(self, mocker, tol):
        """Test that temporarily setting the shots updates the diff method"""
        dev = qml.device("default.qubit", wires=2, shots=100)
        a, b = np.array([0.543, -0.654], requires_grad=True)

        spy = mocker.spy(qml, "execute")

        @qnode(dev)
        def cost_fn(a, b):
            qml.RY(a, wires=0)
            qml.RX(b, wires=1)
            qml.CNOT(wires=[0, 1])
            return qml.expval(qml.PauliY(1))

        # since we are using finite shots, parameter-shift will
        # be chosen
        assert cost_fn.gradient_fn is qml.gradients.param_shift

        cost_fn(a, b)
        assert spy.call_args[1]["gradient_fn"] is qml.gradients.param_shift

        # if we set the shots to None, backprop can now be used
        cost_fn(a, b, shots=None)
        assert spy.call_args[1]["gradient_fn"] == "backprop"

        # original QNode settings are unaffected
        assert cost_fn.gradient_fn is qml.gradients.param_shift
        cost_fn(a, b)
        assert spy.call_args[1]["gradient_fn"] is qml.gradients.param_shift


@pytest.mark.parametrize("dev_name,diff_method,mode", qubit_device_and_diff_method)
class TestQubitIntegration:
    """Tests that ensure various qubit circuits integrate correctly"""

    def test_probability_differentiation(self, dev_name, diff_method, mode, tol):
        """Tests correct output shape and evaluation for a tape
        with a single prob output"""

        if diff_method == "adjoint":
            pytest.skip("The adjoint method does not currently support returning probabilities")

        dev = qml.device(dev_name, wires=2)
        x = np.array(0.543, requires_grad=True)
        y = np.array(-0.654, requires_grad=True)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit(x, y):
            qml.RX(x, wires=[0])
            qml.RY(y, wires=[1])
            qml.CNOT(wires=[0, 1])
            return qml.probs(wires=[1])

        res = qml.jacobian(circuit)(x, y)

        expected = np.array(
            [
                [-np.sin(x) * np.cos(y) / 2, -np.cos(x) * np.sin(y) / 2],
                [np.cos(y) * np.sin(x) / 2, np.cos(x) * np.sin(y) / 2],
            ]
        )
        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_multiple_probability_differentiation(self, dev_name, diff_method, mode, tol):
        """Tests correct output shape and evaluation for a tape
        with multiple prob outputs"""

        if diff_method == "adjoint":
            pytest.skip("The adjoint method does not currently support returning probabilities")

        dev = qml.device(dev_name, wires=2)
        x = np.array(0.543, requires_grad=True)
        y = np.array(-0.654, requires_grad=True)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit(x, y):
            qml.RX(x, wires=[0])
            qml.RY(y, wires=[1])
            qml.CNOT(wires=[0, 1])
            return qml.probs(wires=[0]), qml.probs(wires=[1])

        res = circuit(x, y)

        expected = np.array(
            [
                [np.cos(x / 2) ** 2, np.sin(x / 2) ** 2],
                [(1 + np.cos(x) * np.cos(y)) / 2, (1 - np.cos(x) * np.cos(y)) / 2],
            ]
        )
        assert np.allclose(res, expected, atol=tol, rtol=0)

        res = qml.jacobian(circuit)(x, y)
        expected = np.array(
            [
                [[-np.sin(x) / 2, 0], [-np.sin(x) * np.cos(y) / 2, -np.cos(x) * np.sin(y) / 2]],
                [
                    [np.sin(x) / 2, 0],
                    [np.cos(y) * np.sin(x) / 2, np.cos(x) * np.sin(y) / 2],
                ],
            ]
        )

        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_ragged_differentiation(self, dev_name, diff_method, mode, tol):
        """Tests correct output shape and evaluation for a tape
        with prob and expval outputs"""
        if diff_method == "adjoint":
            pytest.skip("The adjoint method does not currently support returning probabilities")

        dev = qml.device(dev_name, wires=2)
        x = np.array(0.543, requires_grad=True)
        y = np.array(-0.654, requires_grad=True)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit(x, y):
            qml.RX(x, wires=[0])
            qml.RY(y, wires=[1])
            qml.CNOT(wires=[0, 1])
            return [qml.expval(qml.PauliZ(0)), qml.probs(wires=[1])]

        res = circuit(x, y)

        expected = np.array(
            [np.cos(x), (1 + np.cos(x) * np.cos(y)) / 2, (1 - np.cos(x) * np.cos(y)) / 2]
        )
        assert np.allclose(res, expected, atol=tol, rtol=0)

        res = qml.jacobian(circuit)(x, y)
        expected = np.array(
            [
                [-np.sin(x), 0],
                [-np.sin(x) * np.cos(y) / 2, -np.cos(x) * np.sin(y) / 2],
                [np.cos(y) * np.sin(x) / 2, np.cos(x) * np.sin(y) / 2],
            ]
        )
        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_ragged_differentiation_variance(self, dev_name, diff_method, mode, tol):
        """Tests correct output shape and evaluation for a tape
        with prob and variance outputs"""
        if diff_method == "adjoint":
            pytest.skip("The adjoint method does not currently support returning probabilities")

        dev = qml.device(dev_name, wires=2)
        x = np.array(0.543, requires_grad=True)
        y = np.array(-0.654, requires_grad=True)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit(x, y):
            qml.RX(x, wires=[0])
            qml.RY(y, wires=[1])
            qml.CNOT(wires=[0, 1])
            return [qml.var(qml.PauliZ(0)), qml.probs(wires=[1])]

        res = circuit(x, y)

        expected = np.array(
            [np.sin(x) ** 2, (1 + np.cos(x) * np.cos(y)) / 2, (1 - np.cos(x) * np.cos(y)) / 2]
        )
        assert np.allclose(res, expected, atol=tol, rtol=0)

        res = qml.jacobian(circuit)(x, y)
        expected = np.array(
            [
                [2 * np.cos(x) * np.sin(x), 0],
                [-np.sin(x) * np.cos(y) / 2, -np.cos(x) * np.sin(y) / 2],
                [np.cos(y) * np.sin(x) / 2, np.cos(x) * np.sin(y) / 2],
            ]
        )
        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_sampling(self, dev_name, diff_method, mode):
        """Test sampling works as expected"""

        if diff_method in ("backprop", "adjoint"):
            pytest.skip("Sampling not possible with backprop differentiation.")

        dev = qml.device(dev_name, wires=2, shots=10)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit():
            qml.Hadamard(wires=[0])
            qml.CNOT(wires=[0, 1])
            return [qml.sample(qml.PauliZ(0)), qml.sample(qml.PauliX(1))]

        res = circuit()

        assert res.shape == (2, 10)
        assert isinstance(res, np.ndarray)

    @pytest.mark.xfail
    def test_chained_qnodes(self, dev_name, diff_method, mode):
        """Test that the gradient of chained QNodes works without error"""
        dev = qml.device(dev_name, wires=2)

        @qnode(dev, interface="autograd", diff_method=diff_method)
        def circuit1(weights):
            qml.templates.StronglyEntanglingLayers(weights, wires=[0, 1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        @qnode(dev, interface="autograd", diff_method=diff_method)
        def circuit2(data, weights):
            qml.templates.AngleEmbedding(data, wires=[0, 1])
            qml.templates.StronglyEntanglingLayers(weights, wires=[0, 1])
            return qml.expval(qml.PauliX(0))

        def cost(weights):
            w1, w2 = weights
            c1 = circuit1(w1)
            c2 = circuit2(c1, w2)
            return np.sum(c2) ** 2

        w1 = qml.init.strong_ent_layers_normal(n_wires=2, n_layers=3)
        w2 = qml.init.strong_ent_layers_normal(n_wires=2, n_layers=4)

        weights = [w1, w2]

        grad_fn = qml.grad(cost)
        res = grad_fn(weights)

        assert len(res) == 2

    def test_chained_gradient_value(self, dev_name, diff_method, mode, tol):
        """Test that the returned gradient value for two chained qubit QNodes
        is correct."""
        dev1 = qml.device(dev_name, wires=3)

        @qnode(dev1, diff_method=diff_method)
        def circuit1(a, b, c):
            qml.RX(a, wires=0)
            qml.RX(b, wires=1)
            qml.RX(c, wires=2)
            qml.CNOT(wires=[0, 1])
            qml.CNOT(wires=[1, 2])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliY(2))

        dev2 = qml.device("default.qubit", wires=2)

        @qnode(dev2, diff_method=diff_method)
        def circuit2(data, weights):
            qml.RX(data[0], wires=0)
            qml.RX(data[1], wires=1)
            qml.CNOT(wires=[0, 1])
            qml.RZ(weights[0], wires=0)
            qml.RZ(weights[1], wires=1)
            qml.CNOT(wires=[0, 1])
            return qml.expval(qml.PauliX(0) @ qml.PauliY(1))

        def cost(a, b, c, weights):
            return circuit2(circuit1(a, b, c), weights)

        grad_fn = qml.grad(cost)

        # Set the first parameter of circuit1 as non-differentiable.
        a = np.array(0.4, requires_grad=False)

        # The remaining free parameters are all differentiable.
        b = 0.5
        c = 0.1
        weights = np.array([0.2, 0.3])

        res = grad_fn(a, b, c, weights)

        # Output should have shape [dcost/db, dcost/dc, dcost/dw],
        # where b,c are scalars, and w is a vector of length 2.
        assert len(res) == 3
        assert res[0].shape == tuple()  # scalar
        assert res[1].shape == tuple()  # scalar
        assert res[2].shape == (2,)  # vector

        cacbsc = np.cos(a) * np.cos(b) * np.sin(c)

        expected = np.array(
            [
                # analytic expression for dcost/db
                -np.cos(a)
                * np.sin(b)
                * np.sin(c)
                * np.cos(cacbsc)
                * np.sin(weights[0])
                * np.sin(np.cos(a)),
                # analytic expression for dcost/dc
                np.cos(a)
                * np.cos(b)
                * np.cos(c)
                * np.cos(cacbsc)
                * np.sin(weights[0])
                * np.sin(np.cos(a)),
                # analytic expression for dcost/dw[0]
                np.sin(cacbsc) * np.cos(weights[0]) * np.sin(np.cos(a)),
                # analytic expression for dcost/dw[1]
                0,
            ]
        )

        # np.hstack 'flattens' the ragged gradient array allowing it
        # to be compared with the expected result
        assert np.allclose(np.hstack(res), expected, atol=tol, rtol=0)

        if diff_method != "backprop":
            # Check that the gradient was computed
            # for all parameters in circuit2
            assert circuit2.qtape.trainable_params == {0, 1, 2, 3}

            # Check that the parameter-shift rule was not applied
            # to the first parameter of circuit1.
            assert circuit1.qtape.trainable_params == {1, 2}

    def test_second_derivative(self, dev_name, diff_method, mode, tol):
        """Test second derivative calculation of a scalar valued QNode"""
        if diff_method not in {"parameter-shift", "backprop"}:
            pytest.skip("Test only supports parameter-shift or backprop")

        dev = qml.device(dev_name, wires=1)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode, max_diff=2)
        def circuit(x):
            qml.RY(x[0], wires=0)
            qml.RX(x[1], wires=0)
            return qml.expval(qml.PauliZ(0))

        x = np.array([1.0, 2.0], requires_grad=True)
        res = circuit(x)
        g = qml.grad(circuit)(x)
        g2 = qml.grad(lambda x: np.sum(qml.grad(circuit)(x)))(x)

        a, b = x

        expected_res = np.cos(a) * np.cos(b)
        assert np.allclose(res, expected_res, atol=tol, rtol=0)

        expected_g = [-np.sin(a) * np.cos(b), -np.cos(a) * np.sin(b)]
        assert np.allclose(g, expected_g, atol=tol, rtol=0)

        expected_g2 = [
            -np.cos(a) * np.cos(b) + np.sin(a) * np.sin(b),
            np.sin(a) * np.sin(b) - np.cos(a) * np.cos(b),
        ]
        assert np.allclose(g2, expected_g2, atol=tol, rtol=0)

    def test_hessian(self, dev_name, diff_method, mode, tol):
        """Test hessian calculation of a scalar valued QNode"""
        if diff_method not in {"parameter-shift", "backprop"}:
            pytest.skip("Test only supports parameter-shift or backprop")

        dev = qml.device(dev_name, wires=1)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode, max_diff=2)
        def circuit(x):
            qml.RY(x[0], wires=0)
            qml.RX(x[1], wires=0)
            return qml.expval(qml.PauliZ(0))

        x = np.array([1.0, 2.0], requires_grad=True)
        res = circuit(x)

        a, b = x

        expected_res = np.cos(a) * np.cos(b)
        assert np.allclose(res, expected_res, atol=tol, rtol=0)

        grad_fn = qml.grad(circuit)
        g = grad_fn(x)

        expected_g = [-np.sin(a) * np.cos(b), -np.cos(a) * np.sin(b)]
        assert np.allclose(g, expected_g, atol=tol, rtol=0)

        hess = qml.jacobian(grad_fn)(x)

        expected_hess = [
            [-np.cos(a) * np.cos(b), np.sin(a) * np.sin(b)],
            [np.sin(a) * np.sin(b), -np.cos(a) * np.cos(b)],
        ]
        assert np.allclose(hess, expected_hess, atol=tol, rtol=0)

    def test_hessian_unused_parameter(self, dev_name, diff_method, mode, tol):
        """Test hessian calculation of a scalar valued QNode"""
        if diff_method not in {"parameter-shift", "backprop"}:
            pytest.skip("Test only supports parameter-shift or backprop")

        dev = qml.device(dev_name, wires=1)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode, max_diff=2)
        def circuit(x):
            qml.RY(x[0], wires=0)
            return qml.expval(qml.PauliZ(0))

        x = np.array([1.0, 2.0], requires_grad=True)
        res = circuit(x)

        a, b = x

        expected_res = np.cos(a)
        assert np.allclose(res, expected_res, atol=tol, rtol=0)

        grad_fn = qml.grad(circuit)
        g = grad_fn(x)

        expected_g = [-np.sin(a), 0]
        assert np.allclose(g, expected_g, atol=tol, rtol=0)

        hess = qml.jacobian(grad_fn)(x)

        expected_hess = [
            [-np.cos(a), 0],
            [0, 0],
        ]
        assert np.allclose(hess, expected_hess, atol=tol, rtol=0)

    def test_hessian_vector_valued(self, dev_name, diff_method, mode, tol):
        """Test hessian calculation of a vector valued QNode"""
        if diff_method not in {"parameter-shift", "backprop"}:
            pytest.skip("Test only supports parameter-shift or backprop")

        dev = qml.device(dev_name, wires=1)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode, max_diff=2)
        def circuit(x):
            qml.RY(x[0], wires=0)
            qml.RX(x[1], wires=0)
            return qml.probs(wires=0)

        x = np.array([1.0, 2.0], requires_grad=True)
        res = circuit(x)

        a, b = x

        expected_res = [0.5 + 0.5 * np.cos(a) * np.cos(b), 0.5 - 0.5 * np.cos(a) * np.cos(b)]
        assert np.allclose(res, expected_res, atol=tol, rtol=0)

        jac_fn = qml.jacobian(circuit)
        g = jac_fn(x)

        expected_g = [
            [-0.5 * np.sin(a) * np.cos(b), -0.5 * np.cos(a) * np.sin(b)],
            [0.5 * np.sin(a) * np.cos(b), 0.5 * np.cos(a) * np.sin(b)],
        ]
        assert np.allclose(g, expected_g, atol=tol, rtol=0)

        hess = qml.jacobian(jac_fn)(x)

        expected_hess = [
            [
                [-0.5 * np.cos(a) * np.cos(b), 0.5 * np.sin(a) * np.sin(b)],
                [0.5 * np.sin(a) * np.sin(b), -0.5 * np.cos(a) * np.cos(b)],
            ],
            [
                [0.5 * np.cos(a) * np.cos(b), -0.5 * np.sin(a) * np.sin(b)],
                [-0.5 * np.sin(a) * np.sin(b), 0.5 * np.cos(a) * np.cos(b)],
            ],
        ]
        assert np.allclose(hess, expected_hess, atol=tol, rtol=0)

    def test_hessian_vector_valued_postprocessing(self, dev_name, diff_method, mode, tol):
        """Test hessian calculation of a vector valued QNode with post-processing"""
        if diff_method not in {"parameter-shift", "backprop"}:
            pytest.skip("Test only supports parameter-shift or backprop")

        dev = qml.device(dev_name, wires=1)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode, max_diff=2)
        def circuit(x):
            qml.RX(x[0], wires=0)
            qml.RY(x[1], wires=0)
            return [qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(0))]

        def cost_fn(x):
            return x @ circuit(x)

        x = np.array([0.76, -0.87], requires_grad=True)
        res = cost_fn(x)

        a, b = x

        expected_res = x @ [np.cos(a) * np.cos(b), np.cos(a) * np.cos(b)]
        assert np.allclose(res, expected_res, atol=tol, rtol=0)

        grad_fn = qml.grad(cost_fn)
        g = grad_fn(x)

        expected_g = [
            np.cos(b) * (np.cos(a) - (a + b) * np.sin(a)),
            np.cos(a) * (np.cos(b) - (a + b) * np.sin(b)),
        ]
        assert np.allclose(g, expected_g, atol=tol, rtol=0)
        hess = qml.jacobian(grad_fn)(x)

        expected_hess = [
            [
                -(np.cos(b) * ((a + b) * np.cos(a) + 2 * np.sin(a))),
                -(np.cos(b) * np.sin(a)) + (-np.cos(a) + (a + b) * np.sin(a)) * np.sin(b),
            ],
            [
                -(np.cos(b) * np.sin(a)) + (-np.cos(a) + (a + b) * np.sin(a)) * np.sin(b),
                -(np.cos(a) * ((a + b) * np.cos(b) + 2 * np.sin(b))),
            ],
        ]

        assert np.allclose(hess, expected_hess, atol=tol, rtol=0)

    def test_hessian_vector_valued_separate_args(self, dev_name, diff_method, mode, mocker, tol):
        """Test hessian calculation of a vector valued QNode that has separate input arguments"""
        if diff_method not in {"parameter-shift", "backprop"}:
            pytest.skip("Test only supports parameter-shift or backprop")

        dev = qml.device(dev_name, wires=1)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode, max_diff=2)
        def circuit(a, b):
            qml.RY(a, wires=0)
            qml.RX(b, wires=0)
            return qml.probs(wires=0)

        a = np.array(1.0, requires_grad=True)
        b = np.array(2.0, requires_grad=True)
        res = circuit(a, b)

        expected_res = [0.5 + 0.5 * np.cos(a) * np.cos(b), 0.5 - 0.5 * np.cos(a) * np.cos(b)]
        assert np.allclose(res, expected_res, atol=tol, rtol=0)

        jac_fn = qml.jacobian(circuit)
        g = jac_fn(a, b)

        expected_g = [
            [-0.5 * np.sin(a) * np.cos(b), -0.5 * np.cos(a) * np.sin(b)],
            [0.5 * np.sin(a) * np.cos(b), 0.5 * np.cos(a) * np.sin(b)],
        ]
        assert np.allclose(g, expected_g, atol=tol, rtol=0)

        spy = mocker.spy(qml.gradients.param_shift, "transform_fn")
        hess = qml.jacobian(jac_fn)(a, b)

        if diff_method == "backprop":
            spy.assert_not_called()
        elif diff_method == "parameter-shift":
            spy.assert_called()

        expected_hess = [
            [
                [-0.5 * np.cos(a) * np.cos(b), 0.5 * np.sin(a) * np.sin(b)],
                [0.5 * np.cos(a) * np.cos(b), -0.5 * np.sin(a) * np.sin(b)],
            ],
            [
                [0.5 * np.sin(a) * np.sin(b), -0.5 * np.cos(a) * np.cos(b)],
                [-0.5 * np.sin(a) * np.sin(b), 0.5 * np.cos(a) * np.cos(b)],
            ],
        ]
        assert np.allclose(hess, expected_hess, atol=tol, rtol=0)

    def test_hessian_ragged(self, dev_name, diff_method, mode, tol):
        """Test hessian calculation of a ragged QNode"""
        if diff_method not in {"parameter-shift", "backprop"}:
            pytest.skip("Test only supports parameter-shift or backprop")

        dev = qml.device(dev_name, wires=2)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode, max_diff=2)
        def circuit(x):
            qml.RY(x[0], wires=0)
            qml.RX(x[1], wires=0)
            qml.RY(x[0], wires=1)
            qml.RX(x[1], wires=1)
            return qml.expval(qml.PauliZ(0)), qml.probs(wires=1)

        x = np.array([1.0, 2.0], requires_grad=True)
        res = circuit(x)

        a, b = x

        expected_res = [
            np.cos(a) * np.cos(b),
            0.5 + 0.5 * np.cos(a) * np.cos(b),
            0.5 - 0.5 * np.cos(a) * np.cos(b),
        ]
        assert np.allclose(res, expected_res, atol=tol, rtol=0)

        jac_fn = qml.jacobian(circuit)
        g = jac_fn(x)

        expected_g = [
            [-np.sin(a) * np.cos(b), -np.cos(a) * np.sin(b)],
            [-0.5 * np.sin(a) * np.cos(b), -0.5 * np.cos(a) * np.sin(b)],
            [0.5 * np.sin(a) * np.cos(b), 0.5 * np.cos(a) * np.sin(b)],
        ]
        assert np.allclose(g, expected_g, atol=tol, rtol=0)

        hess = qml.jacobian(jac_fn)(x)
        expected_hess = [
            [
                [-np.cos(a) * np.cos(b), np.sin(a) * np.sin(b)],
                [np.sin(a) * np.sin(b), -np.cos(a) * np.cos(b)],
            ],
            [
                [-0.5 * np.cos(a) * np.cos(b), 0.5 * np.sin(a) * np.sin(b)],
                [0.5 * np.sin(a) * np.sin(b), -0.5 * np.cos(a) * np.cos(b)],
            ],
            [
                [0.5 * np.cos(a) * np.cos(b), -0.5 * np.sin(a) * np.sin(b)],
                [-0.5 * np.sin(a) * np.sin(b), 0.5 * np.cos(a) * np.cos(b)],
            ],
        ]
        assert np.allclose(hess, expected_hess, atol=tol, rtol=0)

    def test_state(self, dev_name, diff_method, mode, tol):
        """Test that the state can be returned and differentiated"""
        if diff_method == "adjoint":
            pytest.skip("Adjoint does not support states")

        dev = qml.device(dev_name, wires=2)

        x = np.array(0.543, requires_grad=True)
        y = np.array(-0.654, requires_grad=True)

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit(x, y):
            qml.RX(x, wires=[0])
            qml.RY(y, wires=[1])
            qml.CNOT(wires=[0, 1])
            return qml.state()

        def cost_fn(x, y):
            res = circuit(x, y)
            assert res.dtype is np.dtype("complex128")
            probs = np.abs(res) ** 2
            return probs[0] + probs[2]

        res = cost_fn(x, y)

        if diff_method not in {"backprop"}:
            pytest.skip("Test only supports backprop")

        res = qml.jacobian(cost_fn)(x, y)
        expected = np.array([-np.sin(x) * np.cos(y) / 2, -np.cos(x) * np.sin(y) / 2])
        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_projector(self, dev_name, diff_method, mode, tol):
        """Test that the variance of a projector is correctly returned"""
        if diff_method == "adjoint":
            pytest.skip("Adjoint does not support projectors")

        dev = qml.device(dev_name, wires=2)
        P = np.array([1], requires_grad=False)
        x, y = 0.765, -0.654

        @qnode(dev, diff_method=diff_method, interface="autograd", mode=mode)
        def circuit(x, y):
            qml.RX(x, wires=0)
            qml.RY(y, wires=1)
            qml.CNOT(wires=[0, 1])
            return qml.var(qml.Projector(P, wires=0) @ qml.PauliX(1))

        res = circuit(x, y)
        expected = 0.25 * np.sin(x / 2) ** 2 * (3 + np.cos(2 * y) + 2 * np.cos(x) * np.sin(y) ** 2)
        assert np.allclose(res, expected, atol=tol, rtol=0)

        res = qml.jacobian(circuit)(x, y)
        expected = np.array(
            [
                [
                    0.5 * np.sin(x) * (np.cos(x / 2) ** 2 + np.cos(2 * y) * np.sin(x / 2) ** 2),
                    -2 * np.cos(y) * np.sin(x / 2) ** 4 * np.sin(y),
                ]
            ]
        )
        assert np.allclose(res, expected, atol=tol, rtol=0)


@pytest.mark.parametrize(
    "diff_method,kwargs",
    [["finite-diff", {}], ("parameter-shift", {}), ("parameter-shift", {"force_order2": True})],
)
class TestCV:
    """Tests for CV integration"""

    def test_first_order_observable(self, diff_method, kwargs, tol):
        """Test variance of a first order CV observable"""
        dev = qml.device("default.gaussian", wires=1)

        r = 0.543
        phi = -0.654

        @qnode(dev, diff_method=diff_method, **kwargs)
        def circuit(r, phi):
            qml.Squeezing(r, 0, wires=0)
            qml.Rotation(phi, wires=0)
            return qml.var(qml.X(0))

        res = circuit(r, phi)
        expected = np.exp(2 * r) * np.sin(phi) ** 2 + np.exp(-2 * r) * np.cos(phi) ** 2
        assert np.allclose(res, expected, atol=tol, rtol=0)

        # circuit jacobians
        res = qml.jacobian(circuit)(r, phi)
        expected = np.array(
            [
                [
                    2 * np.exp(2 * r) * np.sin(phi) ** 2 - 2 * np.exp(-2 * r) * np.cos(phi) ** 2,
                    2 * np.sinh(2 * r) * np.sin(2 * phi),
                ]
            ]
        )
        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_second_order_observable(self, diff_method, kwargs, tol):
        """Test variance of a second order CV expectation value"""
        dev = qml.device("default.gaussian", wires=1)

        n = 0.12
        a = 0.765

        @qnode(dev, diff_method=diff_method, **kwargs)
        def circuit(n, a):
            qml.ThermalState(n, wires=0)
            qml.Displacement(a, 0, wires=0)
            return qml.var(qml.NumberOperator(0))

        res = circuit(n, a)
        expected = n ** 2 + n + np.abs(a) ** 2 * (1 + 2 * n)
        assert np.allclose(res, expected, atol=tol, rtol=0)

        # circuit jacobians
        res = qml.jacobian(circuit)(n, a)
        expected = np.array([[2 * a ** 2 + 2 * n + 1, 2 * a * (2 * n + 1)]])
        assert np.allclose(res, expected, atol=tol, rtol=0)


def test_adjoint_reuse_device_state(mocker):
    """Tests that the autograd interface reuses the device state for adjoint differentiation"""
    dev = qml.device("default.qubit", wires=1)

    @qnode(dev, diff_method="adjoint")
    def circ(x):
        qml.RX(x, wires=0)
        return qml.expval(qml.PauliZ(0))

    spy = mocker.spy(dev, "adjoint_jacobian")

    grad = qml.grad(circ)(1.0)
    assert circ.device.num_executions == 1

    spy.assert_called_with(mocker.ANY, use_device_state=True)