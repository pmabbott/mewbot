#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: 2021 - 2023 Mewbot Developers <mewbot@quicksilver.london>
#
# SPDX-License-Identifier: BSD-2-Clause

"""
The core interface definitions for mewbot.

This module provides a set of types that can be checked at runtime, allowing
components to be developed.

This module contains:

 - Interfaces for IO components (IOConfig, Input, Output)
 - Interfaces for behaviours (Behaviour, Trigger, Condition, Action)
 - Base classes for InputEvent and OutputEvent, and type hints for the event queues.
 - Component helper, including an enum of component types and a mapping to the interfaces
 - TypedDict mapping to the YAML schema for components.
"""

from __future__ import annotations

from typing import (
    Any,
    Dict,
    List,
    Protocol,
    Sequence,
    Set,
    Type,
    Union,
    TypedDict,
    runtime_checkable,
)

import asyncio
import enum
import dataclasses


@dataclasses.dataclass
class InputEvent:
    """Base class for all events being generated by :class:`~mewbot.core.Input`

    Events are put on the :class:`~mewbot.core.InputQueue` and are then processed
    by :class:`~mewbot.core.Behaviour`

    This base event has no data or properties. Events must be immutable.
    """


@dataclasses.dataclass
class OutputEvent:
    """Base class for all events accepted by :class:`~mewbot.core.Output`

    :class:`~mewbot.core.Action`s (inside :class:`~mewbot.core.Behaviour`s)
    may emit output events via the :class:`~mewbot.core.EventQueue`

    This base event has no data or properties. Events must be immutable.
    """


InputQueue = asyncio.Queue[InputEvent]
OutputQueue = asyncio.Queue[OutputEvent]


@runtime_checkable
class IOConfigInterface(Protocol):
    """Configuration component that defines a service that mewbot can connect to.

    An IOConfig is a loadable component with configuration for interacting
    with an external system. The config provides :class:`~mewbot.core.Input`
    and/or :class:`~mewbot.core.Output` objects to the bot, which interact
    with that system via the event queues.

    For example, an IOConfig for a chat system would take a single set of
    login credentials, and provide an Input that reads messages and an Output
    that sends messages."""

    def get_inputs(self) -> Sequence[InputInterface]:
        """Gets the Inputs that are used to read events from the service

        :return: The Inputs that are used to read events from the service (if any)
        """

    def get_outputs(self) -> Sequence[OutputInterface]:
        """Gets the Outputs that are used to send events to the service

        :return: The Outputs that are used to send events to the service (if any)
        """


@runtime_checkable
class InputInterface(Protocol):
    """Class for performing read from a service

    Inputs connect to a system, ingest events in some way, and put them
    into the bot's event queue for processing by the behaviour."""

    @staticmethod
    def produces_inputs() -> Set[Type[InputEvent]]:
        """List the types of Events this Input class could produce."""

    def bind(self, queue: InputQueue) -> None:
        """Allows a Bot to attach the active input queue to this input."""

    async def run(self) -> None:
        """Function called for this Input to interact with the service.

        The input should not attach to the service until this function is
        called.

        Note:
         - This function will be run as an asyncio Task.
         - This function should be run after bind() is called.
         - This function may be run in a different loop to __init__.
        """


@runtime_checkable
class OutputInterface(Protocol):
    """Class for performing read from a service

    The bot's output processor takes events from the behaviours off
    the output queue, and passes it to all Outputs that declare that
    they can consume it."""

    @staticmethod
    def consumes_outputs() -> Set[Type[OutputEvent]]:
        """Defines the types of Event that this Output class can consume"""

    async def output(self, event: OutputEvent) -> bool:
        """Send the given event to the service.

        :param event: The event to transmit.
        :return: Whether the event was successfully written.
        """


@runtime_checkable
class TriggerInterface(Protocol):
    """A Trigger determines if a behaviour should be activated for a given event.

    A Behaviour is activated if any of its trigger conditions are met.

    Triggers should refrain from adding too many sub-clauses and conditions.
    Filtering behaviours is the role of the Condition Component."""

    @staticmethod
    def consumes_inputs() -> Set[Type[InputEvent]]:
        """The subtypes of InputEvent that this component accepts.

        This is used to save computational overhead by skipping events of the wrong type.
        Subclasses of the events specified here will also be processed."""

    def matches(self, event: InputEvent) -> bool:
        """Whether the event matches this trigger condition"""


@runtime_checkable
class ConditionInterface(Protocol):
    """A Condition determines whether an event accepted by the Behaviour's
    Triggers will be passed to the Actions.

    Each condition makes its decision independently based on the InputEvent.
    The behaviour combines the results to determine if it should take the actions.

    Note that the bot implementation may 'fail-fast', and a condition may not
    see all events."""

    @staticmethod
    def consumes_inputs() -> Set[Type[InputEvent]]:
        """The subtypes of InputEvent that this component accepts.

        This is used to save computational overhead by skipping events of the wrong type.
        Subclasses of the events specified here will also be processed."""

    def allows(self, event: InputEvent) -> bool:
        """Whether the event is retained after passing through this filter."""


@runtime_checkable
class ActionInterface(Protocol):
    """Actions are executed when a Behaviour is Triggered, and meets all its Conditions

    Actions are executed in order, and will do some combination of:
     - Interact with DataSource and DataStores
     - Emit OutputEvents to the queue
     - Add data to the state, which will be available to the other actions in the behaviour
    """

    @staticmethod
    def consumes_inputs() -> Set[Type[InputEvent]]:
        """The subtypes of InputEvent that this component accepts.

        This is used to save computational overhead by skipping events of the wrong type.
        Subclasses of the events specified here will also be processed."""

    @staticmethod
    def produces_outputs() -> Set[Type[OutputEvent]]:
        """The subtypes of OutputEvent that this component could generate

        This may be checked by the bot to drop unexpected events.
        It may also be used to verify that the overall bot config has the required
        outputs to function as intended."""

    def bind(self, queue: OutputQueue) -> None:
        """Attaches the output to the bot's output queue.

        A queue processor will distribute output events put on this queue
        to the outputs that are able to process them."""

    async def act(self, event: InputEvent, state: Dict[str, Any]) -> None:
        """Performs the action.

        The event is provided, along with the state object from any actions
        that have already run for this event. Data added to or removed from
        `state` will be available for any further actions that process this event.
        No functionality is provided to prevent processing more actions.
        """


@runtime_checkable
class BehaviourInterface(Protocol):
    def add(
        self, component: Union[TriggerInterface, ConditionInterface, ActionInterface]
    ) -> None:
        """Adds on of the components to this behaviour.

        Note that the order of Actions being added must be preserved."""

    def consumes_inputs(self) -> Set[Type[InputEvent]]:
        """The set of InputEvents which are acceptable to one or more triggers.

        These events are not guaranteed to cause the Behaviour to be activated,
        but instead save processing overhead by pre-filtering events by their
        type without having to invoke the matching methods, which may be complex."""

    def bind_output(self, output: OutputQueue) -> None:
        """Wrapper to bind the output queue to all actions in this behaviour.
        See :meth:`mewbow.core.ActionInterface:bind_output`"""

    async def process(self, event: InputEvent) -> None:
        """
        Processes an event.
         - Check whether one (or more) Triggers match the event.
         - Check whether all conditions accept the event
         - Run the actions in order
        """


Component = Union[
    IOConfigInterface,
    TriggerInterface,
    ConditionInterface,
    ActionInterface,
    BehaviourInterface,
]


# pylint: disable=C0103
class ComponentKind(str, enum.Enum):
    """Enumeration of all the meta-types of Component that a bot is built
    out of. These all have a matching interface above (except for DataSource
    and Template which are not yet implemented, but in the specification)"""

    Behaviour = "Behaviour"
    Trigger = "Trigger"
    Condition = "Condition"
    Action = "Action"
    IOConfig = "IOConfig"
    Template = "Template"
    DataSource = "DataSource"

    @classmethod
    def values(cls) -> List[str]:
        """List of named values"""
        return list(e for e in cls)

    @classmethod
    def interface(cls, value: ComponentKind) -> Type[Component]:
        """Maps a value in this enum to the Interface for that component type"""

        _map: Dict[ComponentKind, Type[Component]] = {
            cls.Behaviour: BehaviourInterface,
            cls.Trigger: TriggerInterface,
            cls.Condition: ConditionInterface,
            cls.Action: ActionInterface,
            cls.IOConfig: IOConfigInterface,
        }

        if value in _map:
            return _map[value]

        raise ValueError(f"Invalid value {value}")


class ConfigBlock(TypedDict):
    """Common YAML Block for all components"""

    kind: str
    implementation: str
    uuid: str
    properties: Dict[str, Any]


class BehaviourConfigBlock(ConfigBlock):
    """YAML block for a behaviour, which includes the subcomponents"""

    triggers: List[ConfigBlock]
    conditions: List[ConfigBlock]
    actions: List[ConfigBlock]


__all__ = [
    "ComponentKind",
    "Component",
    "IOConfigInterface",
    "InputInterface",
    "OutputInterface",
    "BehaviourInterface",
    "TriggerInterface",
    "ConditionInterface",
    "ActionInterface",
    "InputEvent",
    "OutputEvent",
    "InputQueue",
    "OutputQueue",
    "ConfigBlock",
    "BehaviourConfigBlock",
]