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
Unit tests for the metric tensor transform.
"""
import pytest
from pennylane import numpy as np
from scipy.linalg import block_diag

import pennylane as qml
from gate_data import Y, Z


class TestMetricTensor:
    """Tests for metric tensor subcircuit construction and evaluation"""

    @pytest.mark.parametrize("diff_method", ["parameter-shift", "backprop"])
    def test_rot_decomposition(self, diff_method):
        """Test that the rotation gate is correctly decomposed"""
        dev = qml.device("default.qubit", wires=1)
        params = np.array([1.0, 2.0, 3.0], requires_grad=True)

        with qml.tape.QuantumTape() as circuit:
            qml.Rot(params[0], params[1], params[2], wires=0)
            qml.expval(qml.PauliX(0))

        tapes, _ = qml.metric_tensor(circuit, approx="block-diag")
        assert len(tapes) == 3

        # first parameter subcircuit
        assert len(tapes[0].operations) == 0

        # Second parameter subcircuit
        assert len(tapes[1].operations) == 4
        assert isinstance(tapes[1].operations[0], qml.RZ)
        assert tapes[1].operations[0].data == [1]
        # PauliY decomp
        assert isinstance(tapes[1].operations[1], qml.PauliZ)
        assert isinstance(tapes[1].operations[2], qml.S)
        assert isinstance(tapes[1].operations[3], qml.Hadamard)

        # Third parameter subcircuit
        assert len(tapes[2].operations) == 2
        assert isinstance(tapes[2].operations[0], qml.RZ)
        assert isinstance(tapes[2].operations[1], qml.RY)
        assert tapes[2].operations[0].data == [1]
        assert tapes[2].operations[1].data == [2]

    @pytest.mark.parametrize("diff_method", ["parameter-shift", "backprop"])
    def test_multirz_decomposition(self, diff_method):
        """Test that the MultiRZ gate is correctly decomposed"""
        dev = qml.device("default.qubit", wires=3)

        def circuit(a, b):
            qml.RX(a, wires=0)
            qml.MultiRZ(b, wires=[0, 1, 2])
            return qml.expval(qml.PauliX(0))

        circuit = qml.QNode(circuit, dev, diff_method=diff_method)
        params = [0.1, 0.2]
        result = qml.metric_tensor(circuit, approx="block-diag")(*params)
        assert result.shape == (2, 2)

    @pytest.mark.parametrize("diff_method", ["parameter-shift", "backprop"])
    def test_parameter_fan_out(self, diff_method):
        """The metric tensor is always with respect to the quantum circuit. Any
        classical processing is not taken into account. As a result, if there is
        parameter fan-out, the returned metric tensor will be larger than
        expected.
        """
        dev = qml.device("default.qubit", wires=2)

        def circuit(a):
            qml.RX(a, wires=0)
            qml.RX(a, wires=0)
            return qml.expval(qml.PauliX(0))

        circuit = qml.QNode(circuit, dev, diff_method=diff_method)
        params = [0.1]
        result = qml.metric_tensor(circuit, hybrid=False, approx="block-diag")(*params)
        assert result.shape == (2, 2)

    def test_construct_subcircuit(self):
        """Test correct subcircuits constructed"""
        dev = qml.device("default.qubit", wires=2)

        with qml.tape.QuantumTape() as tape:
            qml.RX(np.array(1.0, requires_grad=True), wires=0)
            qml.RY(np.array(1.0, requires_grad=True), wires=0)
            qml.CNOT(wires=[0, 1])
            qml.PhaseShift(np.array(1.0, requires_grad=True), wires=1)
            return qml.expval(qml.PauliX(0)), qml.expval(qml.PauliX(1))

        tapes, _ = qml.metric_tensor(tape, approx="block-diag")
        assert len(tapes) == 3

        # first parameter subcircuit
        assert len(tapes[0].operations) == 1
        assert isinstance(tapes[0].operations[0], qml.Hadamard)  # PauliX decomp

        # second parameter subcircuit
        assert len(tapes[1].operations) == 4
        assert isinstance(tapes[1].operations[0], qml.RX)
        # PauliY decomp
        assert isinstance(tapes[1].operations[1], qml.PauliZ)
        assert isinstance(tapes[1].operations[2], qml.S)
        assert isinstance(tapes[1].operations[3], qml.Hadamard)

        # third parameter subcircuit
        assert len(tapes[2].operations) == 4
        assert isinstance(tapes[2].operations[0], qml.RX)
        assert isinstance(tapes[2].operations[1], qml.RY)
        assert isinstance(tapes[2].operations[2], qml.CNOT)
        # Phase shift generator
        assert isinstance(tapes[2].operations[3], qml.QubitUnitary)

    def test_construct_subcircuit_layers(self):
        """Test correct subcircuits constructed
        when a layer structure exists"""
        dev = qml.device("default.qubit", wires=3)
        params = np.ones([8])

        with qml.tape.QuantumTape() as tape:
            # section 1
            qml.RX(params[0], wires=0)
            # section 2
            qml.RY(params[1], wires=0)
            qml.CNOT(wires=[0, 1])
            qml.CNOT(wires=[1, 2])
            # section 3
            qml.RX(params[2], wires=0)
            qml.RY(params[3], wires=1)
            qml.RZ(params[4], wires=2)
            qml.CNOT(wires=[0, 1])
            qml.CNOT(wires=[1, 2])
            # section 4
            qml.RX(params[5], wires=0)
            qml.RY(params[6], wires=1)
            qml.RZ(params[7], wires=2)
            qml.CNOT(wires=[0, 1])
            qml.CNOT(wires=[1, 2])
            return qml.expval(qml.PauliX(0)), qml.expval(qml.PauliX(1)), qml.expval(qml.PauliX(2))

        tapes, _ = qml.metric_tensor(tape, approx="block-diag")

        # this circuit should split into 4 independent
        # sections or layers when constructing subcircuits
        assert len(tapes) == 4

        # first layer subcircuit
        assert len(tapes[0].operations) == 1
        assert isinstance(tapes[0].operations[0], qml.Hadamard)  # PauliX decomp

        # second layer subcircuit
        assert len(tapes[1].operations) == 4
        assert isinstance(tapes[1].operations[0], qml.RX)
        # PauliY decomp
        assert isinstance(tapes[1].operations[1], qml.PauliZ)
        assert isinstance(tapes[1].operations[2], qml.S)
        assert isinstance(tapes[1].operations[3], qml.Hadamard)

        # # third layer subcircuit
        assert len(tapes[2].operations) == 8
        assert isinstance(tapes[2].operations[0], qml.RX)
        assert isinstance(tapes[2].operations[1], qml.RY)
        assert isinstance(tapes[2].operations[2], qml.CNOT)
        assert isinstance(tapes[2].operations[3], qml.CNOT)
        # PauliX decomp
        assert isinstance(tapes[2].operations[4], qml.Hadamard)
        # PauliY decomp
        assert isinstance(tapes[2].operations[5], qml.PauliZ)
        assert isinstance(tapes[2].operations[6], qml.S)
        assert isinstance(tapes[2].operations[7], qml.Hadamard)

        # # fourth layer subcircuit
        assert len(tapes[3].operations) == 13
        assert isinstance(tapes[3].operations[0], qml.RX)
        assert isinstance(tapes[3].operations[1], qml.RY)
        assert isinstance(tapes[3].operations[2], qml.CNOT)
        assert isinstance(tapes[3].operations[3], qml.CNOT)
        assert isinstance(tapes[3].operations[4], qml.RX)
        assert isinstance(tapes[3].operations[5], qml.RY)
        assert isinstance(tapes[3].operations[6], qml.RZ)
        assert isinstance(tapes[3].operations[7], qml.CNOT)
        assert isinstance(tapes[3].operations[8], qml.CNOT)
        # PauliX decomp
        assert isinstance(tapes[3].operations[9], qml.Hadamard)
        # PauliY decomp
        assert isinstance(tapes[3].operations[10], qml.PauliZ)
        assert isinstance(tapes[3].operations[11], qml.S)
        assert isinstance(tapes[3].operations[12], qml.Hadamard)

    def test_evaluate_diag_metric_tensor(self, tol):
        """Test that a diagonal metric tensor evaluates correctly for
        block-diagonal and diagonal setting."""
        dev = qml.device("default.qubit", wires=2)

        def circuit(a, b, c):
            qml.RX(a, wires=0)
            qml.RY(b, wires=0)
            qml.CNOT(wires=[0, 1])
            qml.PhaseShift(c, wires=1)
            return qml.expval(qml.PauliX(0)), qml.expval(qml.PauliX(1))

        circuit = qml.QNode(circuit, dev)

        a = 0.432
        b = 0.12
        c = -0.432

        # evaluate metric tensor
        g_diag = qml.metric_tensor(circuit, approx="diag")(a, b, c)
        g_blockdiag = qml.metric_tensor(circuit, approx="block-diag")(a, b, c)

        # check that the metric tensor is correct
        expected = (
            np.array(
                [1, np.cos(a) ** 2, (3 - 2 * np.cos(a) ** 2 * np.cos(2 * b) - np.cos(2 * a)) / 4]
            )
            / 4
        )
        assert np.allclose(g_diag, np.diag(expected), atol=tol, rtol=0)
        assert np.allclose(g_blockdiag, np.diag(expected), atol=tol, rtol=0)

    @pytest.mark.parametrize("strategy", ["gradient", "device"])
    def test_template_integration(self, strategy, tol):
        """Test that the metric tensor transform acts on QNodes
        correctly when the QNode contains a template"""
        dev = qml.device("default.qubit", wires=3)

        @qml.beta.qnode(dev, expansion_strategy=strategy)
        def circuit(weights):
            qml.templates.StronglyEntanglingLayers(weights, wires=[0, 1, 2])
            return qml.probs(wires=[0, 1])

        weights = np.ones([2, 3, 3], dtype=np.float64, requires_grad=True)
        res = qml.metric_tensor(circuit, approx="block-diag")(weights)
        assert res.shape == (2, 3, 3, 2, 3, 3)

    def test_evaluate_diag_metric_tensor_classical_processing(self, tol):
        """Test that a diagonal metric tensor evaluates correctly
        when the QNode includes classical processing."""
        dev = qml.device("default.qubit", wires=2)

        def circuit(a, b):
            # The classical processing function is
            #     f: ([a0, a1], b) -> (a1, a0, b)
            # So the classical Jacobians will be a permutation matrix and an identity matrix:
            #     classical_jacobian(circuit)(a, b) == ([[0, 1], [1, 0]], [[1]])
            qml.RX(a[1], wires=0)
            qml.RY(a[0], wires=0)
            qml.CNOT(wires=[0, 1])
            qml.PhaseShift(b, wires=1)
            return qml.expval(qml.PauliX(0)), qml.expval(qml.PauliX(1))

        circuit = qml.QNode(circuit, dev)

        a = np.array([0.432, 0.1])
        b = 0.12

        # evaluate metric tensor
        g = qml.metric_tensor(circuit, approx="block-diag")(a, b)
        assert isinstance(g, tuple)
        assert len(g) == 2
        assert g[0].shape == (len(a), len(a))
        assert g[1].shape == tuple()

        # check that the metric tensor is correct
        expected = np.array([np.cos(a[1]) ** 2, 1]) / 4
        assert np.allclose(g[0], np.diag(expected), atol=tol, rtol=0)

        expected = (3 - 2 * np.cos(a[1]) ** 2 * np.cos(2 * a[0]) - np.cos(2 * a[1])) / 16
        assert np.allclose(g[1], expected, atol=tol, rtol=0)

    @pytest.fixture(params=["parameter-shift", "backprop"])
    def sample_circuit(self, request):
        """Sample variational circuit fixture used in the
        next couple of tests"""
        dev = qml.device("default.qubit", wires=3)

        def non_parametrized_layer(a, b, c):
            qml.RX(a, wires=0)
            qml.RX(b, wires=1)
            qml.RX(c, wires=1)
            qml.CNOT(wires=[0, 1])
            qml.CNOT(wires=[1, 2])
            qml.RZ(a, wires=0)
            qml.Hadamard(wires=1)
            qml.CNOT(wires=[0, 1])
            qml.RZ(b, wires=1)
            qml.Hadamard(wires=0)

        a = 0.5
        b = 0.1
        c = 0.5

        def final(x, y, z, h, g, f):
            non_parametrized_layer(a, b, c)
            qml.RX(x, wires=0)
            qml.RY(y, wires=1)
            qml.RZ(z, wires=2)
            non_parametrized_layer(a, b, c)
            qml.RY(f, wires=1)
            qml.RZ(g, wires=2)
            qml.RX(h, wires=1)
            return qml.expval(qml.PauliX(0)), qml.expval(qml.PauliX(1)), qml.expval(qml.PauliX(2))

        final = qml.QNode(final, dev, diff_method=request.param)

        return dev, final, non_parametrized_layer, a, b, c

    def test_evaluate_block_diag_metric_tensor(self, sample_circuit, tol):
        """Test that a block-diagonal metric tensor evaluates correctly,
        by comparing it to a known analytic result as well as numerical
        computation."""
        dev, circuit, non_parametrized_layer, a, b, c = sample_circuit

        params = [-0.282203, 0.145554, 0.331624, -0.163907, 0.57662, 0.081272]
        x, y, z, h, g, f = params

        G = qml.metric_tensor(circuit, approx="block-diag")(*params)

        # ============================================
        # Test block-diag metric tensor of first layer is correct.
        # We do this by comparing against the known analytic result.
        # First layer includes the non_parametrized_layer,
        # followed by observables corresponding to generators of:
        #   qml.RX(x, wires=0)
        #   qml.RY(y, wires=1)
        #   qml.RZ(z, wires=2)

        G1 = np.zeros([3, 3])

        # diag elements
        G1[0, 0] = np.sin(a) ** 2 / 4
        G1[1, 1] = (
            16 * np.cos(a) ** 2 * np.sin(b) ** 3 * np.cos(b) * np.sin(2 * c)
            + np.cos(2 * b) * (2 - 8 * np.cos(a) ** 2 * np.sin(b) ** 2 * np.cos(2 * c))
            + np.cos(2 * (a - b))
            + np.cos(2 * (a + b))
            - 2 * np.cos(2 * a)
            + 14
        ) / 64
        G1[2, 2] = (3 - np.cos(2 * a) - 2 * np.cos(a) ** 2 * np.cos(2 * (b + c))) / 16

        # off diag elements
        G1[0, 1] = np.sin(a) ** 2 * np.sin(b) * np.cos(b + c) / 4
        G1[0, 2] = np.sin(a) ** 2 * np.cos(b + c) / 4
        G1[1, 2] = (
            -np.sin(b)
            * (
                np.cos(2 * (a - b - c))
                + np.cos(2 * (a + b + c))
                + 2 * np.cos(2 * a)
                + 2 * np.cos(2 * (b + c))
                - 6
            )
            / 32
        )

        G1[1, 0] = G1[0, 1]
        G1[2, 0] = G1[0, 2]
        G1[2, 1] = G1[1, 2]

        assert np.allclose(G[:3, :3], G1, atol=tol, rtol=0)

        # =============================================
        # Test block-diag metric tensor of second layer is correct.
        # We do this by computing the required expectation values
        # numerically using multiple circuits.
        # The second layer includes the non_parametrized_layer,
        # RX, RY, RZ gates (x, y, z params), and a 2nd non_parametrized_layer.
        #
        # Observables are the generators of:
        #   qml.RY(f, wires=1)
        #   qml.RZ(g, wires=2)
        G2 = np.zeros([2, 2])

        def layer2_diag(x, y, z, h, g, f):
            non_parametrized_layer(a, b, c)
            qml.RX(x, wires=0)
            qml.RY(y, wires=1)
            qml.RZ(z, wires=2)
            non_parametrized_layer(a, b, c)
            return qml.var(qml.PauliZ(2)), qml.var(qml.PauliY(1))

        layer2_diag = qml.QNode(layer2_diag, dev)

        def layer2_off_diag_first_order(x, y, z, h, g, f):
            non_parametrized_layer(a, b, c)
            qml.RX(x, wires=0)
            qml.RY(y, wires=1)
            qml.RZ(z, wires=2)
            non_parametrized_layer(a, b, c)
            return qml.expval(qml.PauliZ(2)), qml.expval(qml.PauliY(1))

        layer2_off_diag_first_order = qml.QNode(layer2_off_diag_first_order, dev)

        def layer2_off_diag_second_order(x, y, z, h, g, f):
            non_parametrized_layer(a, b, c)
            qml.RX(x, wires=0)
            qml.RY(y, wires=1)
            qml.RZ(z, wires=2)
            non_parametrized_layer(a, b, c)
            return qml.expval(qml.Hermitian(np.kron(Z, Y), wires=[2, 1]))

        layer2_off_diag_second_order = qml.QNode(layer2_off_diag_second_order, dev)

        # calculate the diagonal terms
        varK0, varK1 = layer2_diag(x, y, z, h, g, f)
        G2[0, 0] = varK0 / 4
        G2[1, 1] = varK1 / 4

        # calculate the off-diagonal terms
        exK0, exK1 = layer2_off_diag_first_order(x, y, z, h, g, f)
        exK01 = layer2_off_diag_second_order(x, y, z, h, g, f)

        G2[0, 1] = (exK01 - exK0 * exK1) / 4
        G2[1, 0] = (exK01 - exK0 * exK1) / 4

        assert np.allclose(G[4:6, 4:6], G2, atol=tol, rtol=0)

        # =============================================
        # Test block-diag metric tensor of third layer is correct.
        # We do this by computing the required expectation values
        # numerically.
        # The third layer includes the non_parametrized_layer,
        # RX, RY, RZ gates (x, y, z params), a 2nd non_parametrized_layer,
        # followed by the qml.RY(f, wires=2) operation.
        #
        # Observable is simply generator of:
        #   qml.RY(f, wires=2)
        #
        # Note: since this layer only consists of a single parameter,
        # only need to compute a single diagonal element.

        def layer3_diag(x, y, z, h, g, f):
            non_parametrized_layer(a, b, c)
            qml.RX(x, wires=0)
            qml.RY(y, wires=1)
            qml.RZ(z, wires=2)
            non_parametrized_layer(a, b, c)
            qml.RY(f, wires=2)
            return qml.var(qml.PauliX(1))

        layer3_diag = qml.QNode(layer3_diag, dev)
        G3 = layer3_diag(x, y, z, h, g, f) / 4
        assert np.allclose(G[3:4, 3:4], G3, atol=tol, rtol=0)

        # ============================================
        # Finally, double check that the entire metric
        # tensor is as computed.

        G_expected = block_diag(G1, G3, G2)
        assert np.allclose(G, G_expected, atol=tol, rtol=0)

    def test_evaluate_diag_approx_metric_tensor(self, sample_circuit, tol):
        """Test that a metric tensor under the
        diagonal approximation evaluates correctly and that the old option
        ``diag_approx`` raises a Warning."""
        dev, circuit, non_parametrized_layer, a, b, c = sample_circuit
        params = [-0.282203, 0.145554, 0.331624, -0.163907, 0.57662, 0.081272]
        x, y, z, h, g, f = params

        G = qml.metric_tensor(circuit, approx="diag")(*params)
        with pytest.warns(UserWarning):
            G_alias = qml.metric_tensor(circuit, diag_approx=True)(*params)

        # ============================================
        # Test block-diag metric tensor of first layer is correct.
        # We do this by comparing against the known analytic result.
        # First layer includes the non_parametrized_layer,
        # followed by observables corresponding to generators of:
        #   qml.RX(x, wires=0)
        #   qml.RY(y, wires=1)
        #   qml.RZ(z, wires=2)

        G1 = np.zeros([3, 3])

        # diag elements
        G1[0, 0] = np.sin(a) ** 2 / 4
        G1[1, 1] = (
            16 * np.cos(a) ** 2 * np.sin(b) ** 3 * np.cos(b) * np.sin(2 * c)
            + np.cos(2 * b) * (2 - 8 * np.cos(a) ** 2 * np.sin(b) ** 2 * np.cos(2 * c))
            + np.cos(2 * (a - b))
            + np.cos(2 * (a + b))
            - 2 * np.cos(2 * a)
            + 14
        ) / 64
        G1[2, 2] = (3 - np.cos(2 * a) - 2 * np.cos(a) ** 2 * np.cos(2 * (b + c))) / 16

        assert np.allclose(G[:3, :3], G1, atol=tol, rtol=0)
        assert np.allclose(G_alias[:3, :3], G1, atol=tol, rtol=0)

        # =============================================
        # Test block-diag metric tensor of second layer is correct.
        # We do this by computing the required expectation values
        # numerically using multiple circuits.
        # The second layer includes the non_parametrized_layer,
        # RX, RY, RZ gates (x, y, z params), and a 2nd non_parametrized_layer.
        #
        # Observables are the generators of:
        #   qml.RY(f, wires=1)
        #   qml.RZ(g, wires=2)
        G2 = np.zeros([2, 2])

        def layer2_diag(x, y, z, h, g, f):
            non_parametrized_layer(a, b, c)
            qml.RX(x, wires=0)
            qml.RY(y, wires=1)
            qml.RZ(z, wires=2)
            non_parametrized_layer(a, b, c)
            return qml.var(qml.PauliZ(2)), qml.var(qml.PauliY(1))

        layer2_diag = qml.QNode(layer2_diag, dev)

        # calculate the diagonal terms
        varK0, varK1 = layer2_diag(x, y, z, h, g, f)
        G2[0, 0] = varK0 / 4
        G2[1, 1] = varK1 / 4

        assert np.allclose(G[4:6, 4:6], G2, atol=tol, rtol=0)
        assert np.allclose(G_alias[4:6, 4:6], G2, atol=tol, rtol=0)

        # =============================================
        # Test metric tensor of third layer is correct.
        # We do this by computing the required expectation values
        # numerically.
        # The third layer includes the non_parametrized_layer,
        # RX, RY, RZ gates (x, y, z params), a 2nd non_parametrized_layer,
        # followed by the qml.RY(f, wires=2) operation.
        #
        # Observable is simply generator of:
        #   qml.RY(f, wires=2)
        #
        # Note: since this layer only consists of a single parameter,
        # only need to compute a single diagonal element.

        def layer3_diag(x, y, z, h, g, f):
            non_parametrized_layer(a, b, c)
            qml.RX(x, wires=0)
            qml.RY(y, wires=1)
            qml.RZ(z, wires=2)
            non_parametrized_layer(a, b, c)
            qml.RY(f, wires=2)
            return qml.var(qml.PauliX(1))

        layer3_diag = qml.QNode(layer3_diag, dev)
        G3 = layer3_diag(x, y, z, h, g, f) / 4
        assert np.allclose(G[3:4, 3:4], G3, atol=tol, rtol=0)
        assert np.allclose(G_alias[3:4, 3:4], G3, atol=tol, rtol=0)

        # ============================================
        # Finally, double check that the entire metric
        # tensor is as computed.

        G_expected = block_diag(G1, G3, G2)
        assert np.allclose(G, G_expected, atol=tol, rtol=0)
        assert np.allclose(G_alias, G_expected, atol=tol, rtol=0)

    def test_multi_qubit_gates(self):
        """Test that a tape with Ising gates has the correct metric tensor tapes."""

        dev = qml.device("default.qubit", wires=3)
        with qml.tape.JacobianTape() as tape:
            qml.Hadamard(0)
            qml.Hadamard(2)
            qml.IsingXX(0.2, wires=[0, 1])
            qml.IsingXX(-0.6, wires=[1, 2])
            qml.IsingZZ(1.02, wires=[0, 1])
            qml.IsingZZ(-4.2, wires=[1, 2])

        tapes, proc_fn = qml.metric_tensor(tape, approx="block-diag")
        assert len(tapes) == 4
        assert [len(tape.operations) for tape in tapes] == [2, 4, 5, 6]
        assert [len(tape.measurements) for tape in tapes] == [1] * 4
        expected_ops = [
            [qml.Hadamard, qml.QubitUnitary],
            [qml.Hadamard, qml.Hadamard, qml.IsingXX, qml.QubitUnitary],
            [qml.Hadamard, qml.Hadamard, qml.IsingXX, qml.IsingXX, qml.QubitUnitary],
            [qml.Hadamard, qml.Hadamard, qml.IsingXX, qml.IsingXX, qml.IsingZZ, qml.QubitUnitary],
        ]
        assert [[type(op) for op in tape.operations] for tape in tapes] == expected_ops


fixed_pars = np.array([-0.2, 0.2, 0.5, 0.3, 0.7], requires_grad=False)


def fubini_ansatz0(params, wires=None):
    qml.RX(params[0], wires=0)
    qml.RY(fixed_pars[0], wires=0)
    qml.CNOT(wires=[wires[0], wires[1]])
    qml.RZ(params[1], wires=0)
    qml.CNOT(wires=[wires[0], wires[1]])


def fubini_ansatz1(params, wires=None):
    qml.RX(fixed_pars[1], wires=0)
    for wire in wires:
        qml.Rot(*params[0][wire], wires=wire)
    qml.CNOT(wires=[0, 1])
    qml.RY(fixed_pars[1], wires=0)
    qml.CNOT(wires=[1, 2])
    for wire in wires:
        qml.Rot(*params[1][wire], wires=wire)
    qml.CNOT(wires=[1, 2])
    qml.RX(fixed_pars[2], wires=1)


def fubini_ansatz2(params0, params1, wires=None):
    qml.RX(fixed_pars[1], wires=0)
    qml.RX(fixed_pars[3], wires=1)
    qml.CNOT(wires=[0, 1])
    qml.RY(params0, wires=0)
    qml.RY(params0, wires=1)
    qml.CNOT(wires=[0, 1])
    qml.RX(params1, wires=0)
    qml.RX(params1, wires=1)


def fubini_ansatz3(params0, params1, params2, wires=None):
    qml.RX(fixed_pars[1], wires=0)
    qml.RX(fixed_pars[3], wires=1)
    qml.CNOT(wires=[0, 1])
    qml.CNOT(wires=[1, 2])
    qml.RX(params0, wires=0)
    qml.RX(params0, wires=1)
    qml.CNOT(wires=[0, 1])
    qml.CNOT(wires=[1, 2])
    qml.CNOT(wires=[2, 0])
    qml.RY(params1, wires=0)
    qml.RY(params1, wires=1)
    qml.RY(params1, wires=2)
    qml.RZ(params2, wires=0)
    qml.RZ(params2, wires=1)
    qml.RZ(params2, wires=2)


def fubini_ansatz4(params00, params01, params10, params11, wires=None):
    qml.RY(fixed_pars[3], wires=0)
    qml.RY(fixed_pars[2], wires=1)
    qml.CNOT(wires=[0, 1])
    qml.CNOT(wires=[1, 2])
    qml.RY(fixed_pars[4], wires=0)
    qml.RX(params00, wires=0)
    qml.CNOT(wires=[0, 1])
    qml.RX(params01, wires=1)
    qml.RZ(params10, wires=1)
    qml.CNOT(wires=[0, 1])
    qml.RZ(params11, wires=1)


def fubini_ansatz5(params0, params1, wires=None):
    fubini_ansatz4(params0, params0, params1, params1, wires=wires)


def fubini_ansatz6(params0, params1, wires=None):
    fubini_ansatz4(params0, params0, params1, -params1, wires=wires)


def fubini_ansatz7(params0, params1, wires=None):
    qml.RX(fixed_pars[1], wires=[0])
    qml.RY(fixed_pars[3], wires=[0])
    qml.RZ(fixed_pars[2], wires=[0])
    qml.RX(fixed_pars[2], wires=[1])
    qml.RY(fixed_pars[2], wires=[1])
    qml.RZ(fixed_pars[4], wires=[1])
    qml.CNOT(wires=[0, 1])
    qml.RX(fixed_pars[0], wires=[0])
    qml.RY(fixed_pars[1], wires=[0])
    qml.RZ(fixed_pars[3], wires=[0])
    qml.RX(fixed_pars[1], wires=[1])
    qml.RY(fixed_pars[2], wires=[1])
    qml.RZ(fixed_pars[0], wires=[1])
    qml.CNOT(wires=[0, 1])
    qml.RX(params0, wires=[0])
    qml.RX(params0, wires=[1])
    qml.CNOT(wires=[0, 1])
    qml.RY(fixed_pars[4], wires=[1])
    qml.RY(params1, wires=[0])
    qml.RY(params1, wires=[1])
    qml.CNOT(wires=[0, 1])
    qml.RX(fixed_pars[2], wires=[1])


fubini_ansatze = [
    fubini_ansatz0,
    fubini_ansatz1,
    fubini_ansatz2,
    fubini_ansatz3,
    fubini_ansatz4,
    fubini_ansatz5,
    fubini_ansatz6,
    fubini_ansatz7,
]

fubini_params = [
    (np.array([0.3434, -0.7245345]),),
    (
        np.reshape(
            [
                0.73,
                0.49,
                0.04,
                0.29,
                0.45,
                0.59,
                0.64,
                0.06,
                0.26,
                0.93,
                0.14,
                0.46,
                0.31,
                0.83,
                0.79,
                0.25,
                0.40,
                0.16,
            ],
            (2, 3, 3),
        ),
    ),
    (-0.1111, -0.2222),
    (-0.1111, -0.2222, 0.4554),
    (-0.1735, -0.1735, -0.2846, -0.2846),
    (-0.1735, -0.2846),
    (-0.1735, -0.2846),
    (-0.1111, 0.3333),
]


def autodiff_metric_tensor(ansatz, num_wires):
    """Compute the metric tensor by full state vector
    differentiation via autograd."""
    dev = qml.device("default.qubit", wires=num_wires)

    @qml.qnode(dev)
    def qnode(*params):
        ansatz(*params, wires=dev.wires)
        return qml.state()

    def mt(*params):
        state = qnode(*params)
        rqnode = lambda *params: np.real(qnode(*params))
        iqnode = lambda *params: np.imag(qnode(*params))
        jac = qml.jacobian(rqnode)(*params) + 1j * qml.jacobian(iqnode)(*params)
        psidpsi = np.tensordot(np.conj(state), jac, axes=([0], [0]))
        return np.real(
            np.tensordot(np.conj(jac), jac, axes=([0], [0]))
            - np.tensordot(np.conj(psidpsi), psidpsi, axes=0)
        )

    return mt


class TestFullMetricTensor:

    num_wires = 3

    @pytest.mark.parametrize("ansatz, params", zip(fubini_ansatze, fubini_params))
    def test_correct_output_autograd(self, ansatz, params):
        expected = autodiff_metric_tensor(ansatz, self.num_wires)(*params)
        dev = qml.device("default.qubit.autograd", wires=self.num_wires + 1)

        @qml.qnode(dev, interface="autograd")
        def circuit(*params):
            """Circuit with dummy output to create a QNode."""
            ansatz(*params, dev.wires[:-1])
            return qml.expval(qml.PauliZ(0))

        mt = qml.metric_tensor(circuit, approx=None)(*params)

        assert np.allclose(mt, expected)

    @pytest.mark.xfail(reason="JAX does not support the forward pass metric tensor.")
    @pytest.mark.parametrize("ansatz, params", zip(fubini_ansatze, fubini_params))
    def test_correct_output_jax(self, ansatz, params):
        jax = pytest.importorskip("jax")
        from jax import numpy as jnp

        expected = autodiff_metric_tensor(ansatz, self.num_wires)(*params)
        dev = qml.device("default.qubit.jax", wires=self.num_wires + 1)

        params = tuple(jnp.array(p) for p in params)

        @qml.qnode(dev, interface="jax")
        def circuit(*params):
            """Circuit with dummy output to create a QNode."""
            ansatz(*params, dev.wires[:-1])
            return qml.expval(qml.PauliZ(0))

        mt = qml.metric_tensor(circuit, approx=None)(*params)

        assert np.allclose(mt, expected)

    @pytest.mark.xfail(
        reason="The torch implementation is not adapted to the forward pass metric tensor yet."
    )
    @pytest.mark.parametrize("ansatz, params", zip(fubini_ansatze, fubini_params))
    def test_correct_output_torch(self, ansatz, params):
        torch = pytest.importorskip("torch")
        expected = autodiff_metric_tensor(ansatz, self.num_wires)(*params)
        dev = qml.device("default.qubit.torch", wires=self.num_wires + 1)

        params = tuple(torch.tensor(p, dtype=torch.float64, requires_grad=True) for p in params)

        @qml.qnode(dev, interface="torch")
        def circuit(*params):
            """Circuit with dummy output to create a QNode."""
            ansatz(*params, dev.wires[:-1])
            return qml.expval(qml.PauliZ(0))

        qml.metric_tensor(circuit, approx="block-diag")(*params)
        mt = qml.metric_tensor(circuit, approx=None)(*params)

        assert np.allclose(mt, expected)

    @pytest.mark.xfail(
        reason="The tensorflow implementation is not adapted to the forward pass metric tensor yet."
    )
    @pytest.mark.parametrize("ansatz, params", zip(fubini_ansatze, fubini_params))
    def test_correct_output_tf(self, ansatz, params):
        tf = pytest.importorskip("tensorflow")
        expected = autodiff_metric_tensor(ansatz, self.num_wires)(*params)
        dev = qml.device("default.qubit.tf", wires=self.num_wires + 1)

        params = tuple(tf.Variable(p, dtype=tf.float64) for p in params)

        @qml.qnode(dev, interface="tf")
        def circuit(*params):
            """Circuit with dummy output to create a QNode."""
            ansatz(*params, dev.wires[:-1])
            return qml.expval(qml.PauliZ(0))

        with tf.GradientTape() as t:
            qml.metric_tensor(circuit, approx="block-diag")(*params)
            mt = qml.metric_tensor(circuit, approx=None)(*params)

        assert np.allclose(mt, expected)


@pytest.mark.parametrize("diff_method", ["backprop", "parameter-shift"])
class TestDifferentiability:
    """Test for metric tensor differentiability"""

    def ansatz(self, weights, wires=None):
        qml.RX(weights[0], wires=0)
        qml.RY(weights[1], wires=0)
        qml.CNOT(wires=[0, 1])
        qml.RZ(weights[2], wires=1)

    def circuit(self, weights):
        self.ansatz(weights)
        return qml.expval(qml.PauliX(0)), qml.expval(qml.PauliX(1))

    dev = qml.device("default.qubit", wires=3)
    weights = np.array([0.432, 0.12, -0.292], requires_grad=True)
    a, b, c = weights
    expected_diag = np.array(
        [
            [0, 0, 0],
            [-np.sin(2 * a) / 4, 0, 0],
            [np.cos(a) * np.cos(b) ** 2 * np.sin(a) / 2, np.cos(a) ** 2 * np.sin(2 * b) / 4, 0],
        ]
    )

    def test_autograd(self, diff_method, tol):
        """Test metric tensor differentiability in the autograd interface"""
        qnode = qml.QNode(self.circuit, self.dev, interface="autograd", diff_method=diff_method)

        def cost_diag(weights):
            mt = qml.metric_tensor(qnode, approx="block-diag")(weights)
            return np.diag(mt)

        jac = qml.jacobian(cost_diag)(self.weights)
        print(jac, self.expected_diag)
        assert np.allclose(jac, self.expected_diag, atol=tol, rtol=0)

        def cost_full(weights):
            return qml.metric_tensor(qnode, approx=None)(weights)

        _cost_full = lambda weights: autodiff_metric_tensor(self.ansatz, num_wires=3)(weights)
        print(np.round(_cost_full(self.weights), 6))
        print(cost_full(self.weights))
        assert np.allclose(_cost_full(self.weights), cost_full(self.weights))
        jac = qml.jacobian(cost_full)(self.weights)
        expected_full = qml.jacobian(_cost_full)(self.weights)
        print(np.round(expected_full, 6))
        print(jac)
        assert np.allclose(expected_full, jac)

    def test_jax(self, diff_method, tol):
        """Test metric tensor differentiability in the JAX interface"""
        if diff_method == "parameter-shift":
            pytest.skip("Does not support parameter-shift")

        jax = pytest.importorskip("jax")
        from jax import numpy as jnp

        qnode = qml.QNode(self.circuit, self.dev, interface="jax", diff_method=diff_method)

        def cost_diag(weights):
            return qml.metric_tensor(qnode, approx="block-diag")(weights)[2, 2]

        grad = jax.grad(cost_diag)(jnp.array(self.weights))
        assert np.allclose(grad, self.expected_diag, atol=tol, rtol=0)

        def cost_full(weights):
            return jnp.sum(qml.metric_tensor(qnode, approx=None)(weights))

        grad = jax.grad(cost_full)(jnp.array(self.weights))

    def test_tf(self, diff_method, tol):
        """Test metric tensor differentiability in the TF interface"""
        tf = pytest.importorskip("tensorflow", minversion="2.0")
        qnode = qml.QNode(self.circuit, self.dev, interface="tf", diff_method=diff_method)

        weights_t = tf.Variable(self.weights)
        with tf.GradientTape() as tape:
            loss_diag = qml.metric_tensor(qnode, approx="block-diag")(weights_t)[2, 2]
        grad = tape.gradient(loss_diag, weights_t)
        assert np.allclose(grad, self.expected_diag, atol=tol, rtol=0)

        with tf.GradientTape() as tape:
            loss_full = qml.math.sum(qml.metric_tensor(qnode, approx=None)(weights_t))
        grad = tape.gradient(loss_full, weights_t)

    def test_torch(self, diff_method, tol):
        """Test metric tensor differentiability in the torch interface"""
        torch = pytest.importorskip("torch")

        qnode = qml.QNode(self.circuit, self.dev, interface="torch", diff_method=diff_method)

        weights_t = torch.tensor(self.weights, requires_grad=True)
        loss_diag = qml.metric_tensor(qnode, approx="block-diag")(weights_t)[2, 2]
        loss_diag.backward()

        grad = weights_t.grad
        assert np.allclose(grad, self.expected_diag, atol=tol, rtol=0)

        weights_t = torch.tensor(self.weights, requires_grad=True)
        loss_full = qml.math.sum(qml.metric_tensor(qnode, approx=None)(weights_t))
        loss_full.backward()

        grad = weights_t.grad


def test_generator_no_expval(monkeypatch):
    """Test exception is raised if subcircuit contains an
    operation with generator object that is not an observable"""
    with monkeypatch.context() as m:
        m.setattr("pennylane.RX.generator", [qml.RX, 1])

        with qml.tape.QuantumTape() as tape:
            qml.RX(np.array(0.5, requires_grad=True), wires=0)
            qml.expval(qml.PauliX(0))

        with pytest.raises(qml.QuantumFunctionError, match="no corresponding observable"):
            qml.metric_tensor(tape, approx="block-diag")


def test_error_missing_aux_wire():
    """Tests that a special error is raised if the requested (or default, if not given)
    auxiliary wire for the Hadamard test is missing."""
    dev = qml.device("default.qubit", wires=qml.wires.Wires(["wire1", "wire2"]))

    @qml.qnode(dev)
    def circuit(x, z):
        qml.RX(x, wires="wire1")
        qml.RZ(z, wires="wire2")
        qml.CNOT(wires=["wire1", "wire2"])
        qml.RX(x, wires="wire1")
        qml.RZ(z, wires="wire2")
        return qml.expval(qml.PauliZ("wire2"))

    x = np.array(0.5, requires_grad=True)
    z = np.array(0.1, requires_grad=True)

    with pytest.raises(qml.wires.WireError, match="Hadamard tests"):
        qml.metric_tensor(circuit, approx=None)(x, z)
    with pytest.raises(qml.wires.WireError, match="Hadamard tests"):
        qml.metric_tensor(circuit, approx=None, aux_wire=None)(x, z)


def test_no_error_missing_aux_wire_not_used():
    """Tests that a no error is raised if the requested (or default, if not given)
    auxiliary wire for the Hadamard test is missing but it is not used, either
    because ``approx`` is used or because there only is a diagonal contribution."""
    dev = qml.device("default.qubit", wires=qml.wires.Wires(["wire1", "wire2"]))

    @qml.qnode(dev)
    def circuit_single_block(x, z):
        """This circuit has a metric tensor that consists
        of a single block in the block diagonal "approximation"."""
        qml.RX(x, wires="wire1")
        qml.RZ(z, wires="wire2")
        qml.CNOT(wires=["wire1", "wire2"])
        return qml.expval(qml.PauliZ("wire2"))

    @qml.qnode(dev)
    def circuit_multi_block(x, z):
        """This circuit has a metric tensor that consists
        of multiple blocks and thus is approximated when only
        computing the block diagonal."""
        qml.RX(x, wires="wire1")
        qml.RZ(z, wires="wire2")
        qml.CNOT(wires=["wire1", "wire2"])
        qml.RX(x, wires="wire1")
        qml.RZ(z, wires="wire2")
        return qml.expval(qml.PauliZ("wire2"))

    x = np.array(0.5, requires_grad=True)
    z = np.array(0.1, requires_grad=True)

    qml.metric_tensor(circuit_single_block, approx=None)(x, z)
    qml.metric_tensor(circuit_single_block, approx=None, aux_wire="aux_wire")(x, z)
    qml.metric_tensor(circuit_multi_block, approx="block-diag")(x, z)
    qml.metric_tensor(circuit_multi_block, approx="block-diag", aux_wire="aux_wire")(x, z)


class TestDeprecatedQNodeMethod:
    """The QNode.metric_tensor method has been deprecated.
    These tests ensure it still works, but raises a deprecation
    warning. These tests can be deleted when the method is removed."""

    def test_warning(self, tol):
        """Test that a warning is emitted"""
        dev = qml.device("default.qubit", wires=2)

        @qml.qnode(dev)
        def circuit(a, b, c):
            qml.RX(a, wires=0)
            qml.RY(b, wires=0)
            qml.CNOT(wires=[0, 1])
            qml.PhaseShift(c, wires=1)
            return qml.expval(qml.PauliX(0)), qml.expval(qml.PauliX(1))

        a = 0.432
        b = 0.12
        c = -0.432

        # evaluate metric tensor
        with pytest.warns(UserWarning, match="has been deprecated"):
            g = circuit.metric_tensor(a, b, c, approx="block-diag")

        # check that the metric tensor is correct
        expected = (
            np.array(
                [1, np.cos(a) ** 2, (3 - 2 * np.cos(a) ** 2 * np.cos(2 * b) - np.cos(2 * a)) / 4]
            )
            / 4
        )
        assert np.allclose(g, np.diag(expected), atol=tol, rtol=0)

    def test_tapes_returned(self, tol):
        """Test that a warning is emitted"""
        dev = qml.device("default.qubit", wires=2)

        @qml.qnode(dev)
        def circuit(a, b, c):
            qml.RX(a, wires=0)
            qml.RY(b, wires=0)
            qml.CNOT(wires=[0, 1])
            qml.PhaseShift(c, wires=1)
            return qml.expval(qml.PauliX(0)), qml.expval(qml.PauliX(1))

        a = 0.432
        b = 0.12
        c = -0.432

        # evaluate metric tensor
        with pytest.warns(UserWarning, match="has been deprecated"):
            tapes, fn = circuit.metric_tensor(a, b, c, approx="block-diag", only_construct=True)

        assert len(tapes) == 3
