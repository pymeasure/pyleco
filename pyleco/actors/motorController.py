# -*- coding: utf-8 -*-
"""Control motors


Created on Tue Nov 29 17:34:36 2022

@author: moneke
"""

from typing import Any, Optional

# import PyTrinamic
from pytrinamic.connections import ConnectionManager  # type: ignore
from pytrinamic.modules import TMCM6110  # type: ignore

from .actor import BaseController
from devices import motors  # type: ignore  # TODO implement differently


class MotorController(BaseController):
    """Control a motorcard.

    You may supply any value as a motor argument. Either the motor number as an
    integer or a valid key of the motorDict dictionary.

    :param str name: Name to listen to and to publish values with.
    :param port: Port of the motor card to connect to. Or name, if stored.
    :param dict motorDict: Dictionary with motor names.

    :variable configs: Dictionary of the motor configurations.
    :variable motorDict: Contain mappings of names to motor numbers.
    """

    def __init__(self, name: str, port: str | int, motorDict: Optional[dict] = None,
                 **kwargs) -> None:
        super().__init__(name, **kwargs)
        if isinstance(port, str):
            port = motors.getPort(port)
        self.connectionManager = ConnectionManager(f"--port COM{port}")
        self.card = TMCM6110(self.connectionManager.connect())
        self.configs: dict[str | int, dict] = {}
        self.motorDict: dict[str, int] = {} if motorDict is None else motorDict

    def _get_motor_number(self, motor: int | str) -> int:
        """Get a motor number from the input, using the dictionary."""
        if isinstance(motor, int):
            return motor
        else:
            motor_2 = self.motorDict.get(motor)
            if motor_2 is None:
                raise ValueError(f"Motor name '{motor}' is not known.")
            else:
                return motor_2

    # General methods
    def disconnect(self) -> None:
        """Disconnect the card."""
        self.connectionManager.disconnect()

    def configure_motor(self, config: dict) -> None:
        """Configure a motor according to the dictionary."""
        try:
            motors.configureMotor(self.card, config)
        except KeyError:
            pass
        try:
            self.configs[config['motorNumber']] = config
        except KeyError:
            pass

    def get_configuration(self, motor: int | str) -> dict:
        motor = self._get_motor_number(motor)
        return self.configs.get(motor, {'motorNumber': motor})

    def get_global_parameter(self, gp_type: int, bank: int, signed: bool = False) -> Any:
        return self.card.get_global_parameter(gp_type=gp_type, bank=bank, signed=signed)

    def set_global_parameter(self, gp_type: int, bank: int, value) -> None:
        return self.card.set_global_parameter(gp_type=gp_type, bank=bank, value=value)

    def get_axis_parameter(self, ap_type: int, axis: int, signed: bool = False) -> Any:
        return self.card.get_axis_parameter(ap_type=ap_type, axis=axis, signed=signed)

    def set_axis_parameter(self, ap_type: int, axis: int, value) -> None:
        return self.card.set_axis_parameter(ap_type=ap_type, axis=axis, value=value)

    # Motor controls
    def stop(self, motor: int | str) -> None:
        motor = self._get_motor_number(motor)
        self.card.stop(motor)

    def get_actual_velocity(self, motor: int | str) -> int:
        motor = self._get_motor_number(motor)
        return self.card.motors[motor].get_actual_velocity()

    def get_actual_position(self, motor: int | str) -> int:
        motor = self._get_motor_number(motor)
        return self.card.motors[motor].actual_position

    def get_actual_units(self, motor: int | str) -> float:
        """Get the actual position in units."""
        motor = self._get_motor_number(motor)
        return motors.stepsToUnits(self.get_actual_position(motor), self.configs[motor])

    def set_actual_position(self, motor: int | str, steps: int) -> None:
        """Set the current position in steps."""
        motor = self._get_motor_number(motor)
        self.card.stop(motor)
        self.card.motors[motor].actual_position = steps

    def move_to(self, motor: int | str, position: int, velocity: int | None = None) -> None:
        """Move to a specific position."""
        motor = self._get_motor_number(motor)
        self.card.move_to(motor, position, velocity)

    def move_by(self, motor: int | str, difference: int, velocity: int | None = None) -> None:
        motor = self._get_motor_number(motor)
        self.card.move_by(motor, difference, velocity)

    def move_to_units(self, motor: int | str, position: float, velocity: int | None = None) -> None:
        """Move to a specific position in units."""
        motor = self._get_motor_number(motor)
        try:
            position = motors.unitsToSteps(position, self.configs[motor])
        except KeyError:
            self.log.exception(f"Unsufficient configuration for motor {motor} to move to.")
            raise ValueError(f"Unsufficient configuration for motor {motor} to move to.")
        else:
            self.card.move_to(motor, position, velocity)

    def move_by_units(self, motor: int | str, difference: float,
                      velocity: int | None = None) -> None:
        motor = self._get_motor_number(motor)
        try:
            difference = motors.unitsToSteps(difference, self.configs[motor])
        except KeyError:
            self.log.exception(f"Unsufficient configuration for motor {motor} to move by.")
            raise ValueError(f"Unsufficient configuration for motor {motor} to move by.")
        else:
            self.card.move_by(motor, difference, velocity)

    def rotate(self, motor: int | str, velocity: int) -> None:
        motor = self._get_motor_number(motor)
        self.card.rotate(motor, velocity)

    def get_position_reached(self, motor: int | str) -> bool:
        motor = self._get_motor_number(motor)
        return self.card.motors[motor].get_position_reached()

    def get_motor_dict(self) -> dict[str, int]:
        return self.motorDict

    def set_motor_dict(self, motorDict: dict[str, int]) -> None:
        self.motorDict = motorDict

    # In/outs
    def get_analog_input(self, connection: int) -> float:
        return self.card.get_analog_input(connection)

    def get_digital_input(self, connection: int) -> bool:
        return self.card.get_digital_input(connection)

    def get_digital_output(self, connection: int) -> bool:
        return self.card.get_digital_output(connection)

    def set_digital_output(self, connection: int, enabled: bool) -> None:
        if enabled:
            self.card.set_digital_output(connection)
        else:
            self.card.clear_digital_output(connection)
