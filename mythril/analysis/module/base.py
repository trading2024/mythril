""" Base DetectionModule python module

The main interface specified in this module is DetectionModule.
This is  the interface extended by all mythril detection modules, which permit the detection of vulnerabilities
and bugs in smart contracts.
"""
import logging
from typing import List, Set, Optional

from mythril.analysis.report import Issue
from abc import ABC, abstractmethod
from enum import Enum

# Get logger instance
log = logging.getLogger(__name__)


class EntryPoint(Enum):
    POST = 1
    CALLBACK = 2


class DetectionModule(ABC):
    """The base detection module.

    All custom-built detection modules must inherit from this class.

    There are several class properties that expose information about the detection modules
    - name: The name of the detection module
    - swc_id: The SWC ID associated with the weakness that the module detects
    - description: A description of the detection module, and what it detects
    - entry_point: Mythril can run callback style detection modules, or modules that search the statespace.
                [IMPORTANT] POST entry points severely slow down the analysis, try to always use callback style modules
    - pre_hooks: A list of instructions to hook the laser vm for (pre execution of the instruction)
    - post_hooks: A list of instructions to hook the laser vm for (post execution of the instruction)
    """

    name = "Detection Module Name"
    swc_id = "SWC-000"
    description = "Detection module description"
    entry_point = EntryPoint.POST  # type: EntryPoint
    pre_hooks = []  # type: List[str]
    post_hooks = []  # type: List[str]

    def __init__(self) -> None:
        self.issues = []  # type: List[Issue]
        self.cache = set()  # type: Set[int]

    def reset_module(self):
        """
        Resets issues
        """
        self.issues = []

    def execute(self, statespace) -> Optional[List[Issue]]:
        """The entry point for execution, which is being called by Mythril.

        :param statespace:
        :return:
        """

        log.debug("Entering analysis module: {}".format(self.__class__.__name__))

        self._execute(statespace)

        log.debug("Exiting analysis module: {}".format(self.__class__.__name__))

        return None

    def _execute(self, statespace):
        """Module main method (override this)

        :param statespace:
        :return:
        """

        raise NotImplementedError()

    def __repr__(self) -> str:
        return (
            "<"
            "DetectionModule "
            "name={0.name} "
            "swc_id={0.swc_id} "
            "pre_hooks={0.pre_hooks} "
            "post_hooks={0.post_hooks} "
            "description={0.description}"
            ">"
        ).format(self)
