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
"""This file tests the ``qml.circuit_drawer.draw_mpl`` function."""

import pytest
from pytest_mock import mocker
import pennylane as qml

from pennylane.circuit_drawer import draw_mpl
from pennylane.tape import QuantumTape

mpl = pytest.importorskip("matplotlib")
plt = pytest.importorskip("matplotlib.pyplot")

with QuantumTape() as tape1:
    qml.PauliX(0)
    qml.PauliX("a")
    qml.PauliX(1.234)


label_data = [({}, ["0", "a", "1.234"]), # default behaviour
({'wire_order': [1.234, "a", 0]}, ["1.234", "a", "0"]), # provide standard wire order
({'wire_order': ["a", 1.234]}, ["a", "1.234", "0"]), # wire order that doesn't include all active wires
({'wire_order': ["nope", "not there", 3]}, ["0", "a", "1.234"]), # wire order includes unused wires
({'wire_order': ["aux", 0, "a", 1.234], 'show_all_wires': True}, ["aux", "0", "a", ]) # show_all_wires=True
]

class TestLabelling:
    """Test the labels for the wires."""

    @pytest.mark.parametrize("kwargs, labels", label_data)
    def test_labels(self, kwargs, labels):
        """Test produced labels under different settings.  Check both text value and position"""
        _, ax = draw_mpl(tape1, **kwargs)

        for wire, (text_obj, label) in enumerate(zip(ax.texts, labels)):
            assert text_obj.get_text() == label
            assert text_obj.get_position() == (-1.5, wire)

        plt.close()

    def test_label_options(self):
        """Test providing `label_options` alters styling of the text"""

        _, ax = draw_mpl(tape1, label_options={"fontsize": 10})

        for text_obj in ax.texts[0:3]:
            assert text_obj.get_fontsize() == 10.0

        plt.close()


class TestWires:
    """Test wire lines are produced correctly in different situations"""

    def test_empty_tape_wire_order(self):
        """Test situation with empty tape but specified wires."""

        _, ax = draw_mpl(QuantumTape(), wire_order=[0, 1, 2], show_all_wires=True)

        assert len(ax.lines) == 3
        for wire, line in enumerate(ax.lines):
            assert line.get_xdata() == (-1, 1) # from -1 to number of layers
            assert line.get_ydata() == (wire, wire)

        plt.close()

    def test_single_layer(self):
        """Test a single layer with multiple wires."""

        with QuantumTape() as tape:
            qml.PauliX(0)
            qml.PauliY(1)
            qml.PauliZ(2)

        fig, ax = draw_mpl(tape)

        assert len(ax.lines) == 3
        for wire, line in enumerate(ax.lines):
            assert line.get_xdata() == (-1, 1) # from -1 to number of layers
            assert line.get_ydata() == (wire, wire)

        plt.close()

    def test_three_layers(self):
        """Test wire length when circuit has three layers."""

        with QuantumTape() as tape:
            qml.PauliX(0)
            qml.PauliX(0)
            qml.PauliX(0)

        _, ax = draw_mpl(tape)

        assert len(ax.lines) == 1
        assert ax.lines[0].get_xdata() == (-1, 3) # from -1 to number of layers
        assert ax.lines[0].get_ydata() == (0, 0)

        plt.close()

    def test_wire_options(self):
        """Test wires are formatted by provided dictionary."""

        with QuantumTape() as tape:
            qml.PauliX(0)
            qml.PauliX(1)

        rgba_red = (1, 0, 0, 1)
        _, ax = draw_mpl(tape, wire_options={"linewidth": 5, "color": rgba_red})

        for line in ax.lines:
            assert line.get_linewidth() == 5
            assert line.get_color() == rgba_red

        plt.close()


class TestSpecialGates:
    """Tests the gates with special drawing methods."""

    def test_SWAP(self):
        """Test SWAP gate special call"""

        with QuantumTape() as tape:
            qml.SWAP(wires=(0, 1))

        _, ax = draw_mpl(tape)
        layer = 0

        # two wires, SWAP contains 5 lines
        assert len(ax.lines) == 7

        connecting_line = ax.lines[2]
        assert connecting_line.get_data() == ((layer, layer), [0, 1])

        x_lines = ax.lines[3:]
        assert x_lines[0].get_data() == ((layer-0.2, layer+0.2), (-0.2, 0.2))
        assert x_lines[1].get_data() == ((layer-0.2, layer+0.2), (0.2, -0.2))
        assert x_lines[2].get_data() == ((layer-0.2, layer+0.2), (0.8, 1.2))
        assert x_lines[3].get_data() == ((layer-0.2, layer+0.2), (1.2, 0.8))
        plt.close()


    def test_CSWAP(self):
        """Test CSWAP special call"""

        with QuantumTape() as tape:
            qml.CSWAP(wires=(0, 1, 2))

        _, ax = draw_mpl(tape)
        layer = 0

        # three wires, one control, 5 swap
        assert len(ax.lines) == 9

        control_line = ax.lines[3]
        assert control_line.get_data() == ((layer,layer), (0,2))

        # control circle
        assert ax.patches[0].center == (layer,0)

        # SWAP components
        connecting_line = ax.lines[4]
        assert connecting_line.get_data() == ((layer,layer), [1,2])

        x_lines = ax.lines[5:]
        assert x_lines[0].get_data() == ((layer-0.2, layer+0.2), (0.8, 1.2))
        assert x_lines[1].get_data() == ((layer-0.2, layer+0.2), (1.2, 0.8))

        assert x_lines[2].get_data() == ((layer-0.2, layer+0.2), (1.8, 2.2))
        assert x_lines[3].get_data() == ((layer-0.2, layer+0.2), (2.2, 1.8))
        plt.close()

    def test_CNOT(self, mocker):
        """Test CNOT gets a special call"""

        with QuantumTape() as tape:
            qml.CNOT(wires=(0, 1))

        _, ax = draw_mpl(tape)
        layer = 0

        assert len(ax.patches) == 2
        assert ax.patches[0].center == (layer,0)
        assert ax.patches[1].center == (layer,1)

        control_line = ax.lines[2]
        assert control_line.get_data() == ((layer,layer), (0,1))

        assert len(ax.lines) == 5
        plt.close()

    def test_Toffoli(self):
        """Test Toffoli gets a special call."""

        with QuantumTape() as tape:
            qml.Toffoli(wires=(0, 1, 2))

        _, ax = draw_mpl(tape)
        layer = 0

        assert len(ax.patches) == 3
        assert ax.patches[0].center == (layer, 0)
        assert ax.patches[1].center == (layer, 1)
        assert ax.patches[2].center == (layer, 2)

        # three wires, one control line, two target lines
        assert len(ax.lines) == 6
        control_line = ax.lines[3]
        assert control_line.get_data() == ((layer, layer), (0, 2))

        plt.close()

    def test_MultiControlledX_no_control_values(self):
        """Test MultiControlledX gets a special call."""

        with QuantumTape() as tape:
            qml.MultiControlledX(control_wires=[0, 1, 2, 3], wires=4)

        _, ax = draw_mpl(tape)
        layer = 0

        assert len(ax.patches) == 5
        for wire, patch in enumerate(ax.patches):
            assert patch.center == (layer, wire)

        # five wires, one control line, two target lines
        assert len(ax.lines) == 8
        control_line = ax.lines[5]
        assert control_line.get_data() == ((layer, layer), (0, 4))

        plt.close()

    def test_MultiControlledX_control_values(self):
        """Test MultiControlledX with provided control values."""

        with QuantumTape() as tape:
            qml.MultiControlledX(control_wires=[0, 1, 2, 3], wires=4, control_values="0101")

        _, ax = draw_mpl(tape)
        
        assert ax.patches[0].get_facecolor() == (1.0, 1.0, 1.0, 1.0) # white
        assert ax.patches[1].get_facecolor() == mpl.colors.to_rgba(plt.rcParams['lines.color'])
        assert ax.patches[2].get_facecolor() == (1.0, 1.0, 1.0, 1.0)
        assert ax.patches[3].get_facecolor() == mpl.colors.to_rgba(plt.rcParams['lines.color'])

        plt.close()

    def test_CZ(self):
        """Test CZ gets a special call."""

        with QuantumTape() as tape:
            qml.CZ(wires=(0, 1))

        _, ax = draw_mpl(tape)
        layer = 0

        # two wires one control line
        assert len(ax.lines) == 3

        assert ax.lines[2].get_data() == ((layer, layer), (0,1))

        # two control circles
        assert len(ax.patches) == 2
        assert ax.patches[0].center == (layer, 0)
        assert ax.patches[1].center == (layer, 1)

        plt.close()

controlled_data = [(qml.CY(wires=(0,1)), "Y"), 
    (qml.CRX(1.2345, wires=(0,1)), "RX"),
    (qml.CRot(1.2, 2.2, 3.3, wires=(0,1)), "Rot")
]

class TestControlledGates:
    """Tests generic controlled gates"""

    @pytest.mark.parametrize("op, label", controlled_data)
    def test_control_gates(self, op, label):

        with QuantumTape() as tape:
            qml.apply(op)

        _, ax = draw_mpl(tape)
        layer = 0

        assert isinstance(ax.patches[0], mpl.patches.Circle)
        assert ax.patches[0].center == (layer,0)

        control_line = ax.lines[2]
        assert control_line.get_data() == ((layer,layer), (0,1))

        assert isinstance(ax.patches[1], mpl.patches.Rectangle)
        assert ax.patches[1].get_xy() == (layer-0.4, 0.6)

        # two wire labels, so [2] is box gate label
        assert ax.texts[2].get_text() == label

        # box and text must be raised above control wire
        # text raised over box
        assert ax.patches[1].get_zorder() > control_line.get_zorder()
        assert ax.texts[2].get_zorder() > ax.patches[1].get_zorder()

        plt.close()

    def test_CRX_decimals(self):
        """Test a controlled parametric operation with specified decimals."""

        with QuantumTape() as tape:
            qml.CRX(1.234, wires=(0, 1))

        _, ax = draw_mpl(tape, decimals=2)

        # two wire labels, so CRX is third text object
        assert ax.texts[2].get_text() == "RX\n(1.23)"

general_op_data = [(qml.RX(1.234, wires=0), "RX"),
    (qml.IsingXX(1.234, wires=(0,1)), "IsingXX"),

]

class TestGeneralOperations:
    """Tests general operations."""

    def test_RX(self, mocker):
        """Test RX gate"""
        mock_drawer = mocker.patch("pennylane.circuit_drawer.draw.MPLDrawer")

        with QuantumTape() as tape:
            qml.RX(1.234, wires=0)

        draw_mpl(tape)

        mock_drawer().box_gate.assert_called_with(0, [0], "RX")

    def test_RX_decimals(self, mocker):
        """Test RX gate"""
        mock_drawer = mocker.patch("pennylane.circuit_drawer.draw.MPLDrawer")

        with QuantumTape() as tape:
            qml.RX(1.234, wires=0)

        draw_mpl(tape, decimals=2)

        mock_drawer().box_gate.assert_called_with(0, [0], "RX\n(1.23)")

    def test_IsingXX(self, mocker):
        """Test a standard multiwire gate."""
        mock_drawer = mocker.patch("pennylane.circuit_drawer.draw.MPLDrawer")

        with QuantumTape() as tape:
            qml.IsingXX(1.234, wires=(0, 1))

        draw_mpl(tape)

        mock_drawer().box_gate.assert_called_with(0, [0, 1], "IsingXX")

    def test_QFT(self, mocker):
        """Test a template operation"""
        mock_drawer = mocker.patch("pennylane.circuit_drawer.draw.MPLDrawer")

        with QuantumTape() as tape:
            qml.QFT(wires=range(3))

        draw_mpl(tape)

        mock_drawer().box_gate.assert_called_with(0, [0, 1, 2], "QFT")


class TestMeasurements:
    """Tests measurements are drawn correctly"""

    def test_expval(self, mocker):
        """Test expval produce measure boxes"""
        mock_drawer = mocker.patch("pennylane.circuit_drawer.draw.MPLDrawer")

        with QuantumTape() as tape:
            qml.expval(qml.PauliX(0))

        draw_mpl(tape)

        # layer 1 wire 0
        mock_drawer().measure.assert_called_with(1, 0)

    def test_state(self, mocker):
        """Test state produces measurements on all wires."""
        mock_drawer = mocker.patch("pennylane.circuit_drawer.draw.MPLDrawer")

        with QuantumTape() as tape:
            qml.state()

        draw_mpl(tape, wire_order=[0, 1, 2], show_all_wires=True)

        call_list = [((1, 0),), ((1, 1),), ((1, 2),)]
        assert mock_drawer().measure.call_args_list == call_list

    def test_probs(self, mocker):
        """Test probs with wires."""

        mock_drawer = mocker.patch("pennylane.circuit_drawer.draw.MPLDrawer")

        with QuantumTape() as tape:
            qml.probs(wires=(0, 1, 2))

        draw_mpl(tape)

        call_list = [((1, 0),), ((1, 1),), ((1, 2),)]
        assert mock_drawer().measure.call_args_list == call_list

    def test_multiple_measurements(self, mocker):
        """Assert """

        mock_drawer = mocker.patch("pennylane.circuit_drawer.draw.MPLDrawer")

        with QuantumTape() as tape:
            qml.expval(qml.PauliZ(0))
            qml.expval(qml.PauliZ(0) @ qml.PauliY(1))
            qml.state()

        draw_mpl(tape)
        
        call_list = [((1,0),), ((1,1), )]
        assert mock_drawer().measure.call_args_list == call_list

class TestLayering:
    """Tests operations are placed into layers correctly."""

    def test_single_layer_multiple_wires(self, mocker):
        """Tests mulitple gates all in the same layer"""
        mock_drawer = mocker.patch("pennylane.circuit_drawer.draw.MPLDrawer")

        with QuantumTape() as tape:
            qml.PauliX(0)
            qml.PauliX(1)
            qml.PauliX(2)

        draw_mpl(tape)

        # no order in set, so may be called in a different order
        mock_drawer().box_gate.assert_any_call(0, [0], "X")
        mock_drawer().box_gate.assert_any_call(0, [1], "X")
        mock_drawer().box_gate.assert_any_call(0, [2], "X")

    def test_three_layers_one_wire(self, mocker):
        """Tests multiple gates all on the same wire"""

        mock_drawer = mocker.patch("pennylane.circuit_drawer.draw.MPLDrawer")

        with QuantumTape() as tape:
            qml.PauliX(0)
            qml.PauliX(0)
            qml.PauliX(0)

        draw_mpl(tape)

        mock_drawer().box_gate.assert_any_call(0, [0], "X")
        mock_drawer().box_gate.assert_any_call(1, [0], "X")
        mock_drawer().box_gate.assert_any_call(2, [0], "X")

    def test_blocking_IsingXX(self, mocker):
        """Tests a multiwire gate blocking another on its empty wire"""

        mock_drawer = mocker.patch("pennylane.circuit_drawer.draw.MPLDrawer")

        with QuantumTape() as tape:
            qml.PauliX(0)
            qml.IsingXX(1.234, wires=(0, 2))
            qml.PauliX(1)

        draw_mpl(tape, wire_order=[0, 1, 2])

        mock_drawer().box_gate.assert_any_call(0, [0], "X")
        mock_drawer().box_gate.assert_any_call(1, [0, 2], "IsingXX")
        mock_drawer().box_gate.assert_any_call(2, [1], "X")
