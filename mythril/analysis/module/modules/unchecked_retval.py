"""This module contains detection code to find occurrences of calls whose
return value remains unchecked."""

import logging
from copy import copy
from typing import List, cast

from typing_extensions import TypedDict

from mythril.analysis import solver
from mythril.analysis.issue_annotation import IssueAnnotation
from mythril.analysis.module.base import DetectionModule, EntryPoint
from mythril.analysis.report import Issue
from mythril.analysis.swc_data import UNCHECKED_RET_VAL
from mythril.exceptions import UnsatError
from mythril.laser.ethereum.state.annotation import StateAnnotation
from mythril.laser.ethereum.state.global_state import GlobalState
from mythril.laser.smt import And
from mythril.laser.smt.bitvec import BitVec

log = logging.getLogger(__name__)


class RetVal(TypedDict):
    address: int
    retval: BitVec


class UncheckedRetvalAnnotation(StateAnnotation):
    def __init__(self) -> None:
        self.retvals: List[RetVal] = []

    def __copy__(self):
        result = UncheckedRetvalAnnotation()
        result.retvals = copy(self.retvals)
        return result


class UncheckedRetval(DetectionModule):
    """A detection module to test whether CALL return value is checked."""

    name = "Return value of an external call is not checked"
    swc_id = UNCHECKED_RET_VAL
    description = (
        "Test whether CALL return value is checked. "
        "For direct calls, the Solidity compiler auto-generates this check. E.g.:\n"
        "    Alice c = Alice(address);\n"
        "    c.ping(42);\n"
        "Here the CALL will be followed by IZSERO(retval), if retval = ZERO then state is reverted. "
        "For low-level-calls this check is omitted. E.g.:\n"
        '    c.call.value(0)(bytes4(sha3("ping(uint256)")),1);'
    )
    entry_point = EntryPoint.CALLBACK
    pre_hooks = ["STOP", "RETURN"]
    post_hooks = ["CALL", "DELEGATECALL", "STATICCALL", "CALLCODE"]

    def _execute(self, state: GlobalState) -> List[Issue]:
        """

        :param state:
        :return:
        """
        return self._analyze_state(state)

    def _analyze_state(self, state: GlobalState) -> list:
        instruction = state.get_current_instruction()

        annotations = cast(
            List[UncheckedRetvalAnnotation],
            [a for a in state.get_annotations(UncheckedRetvalAnnotation)],
        )
        if len(annotations) == 0:
            state.annotate(UncheckedRetvalAnnotation())
            annotations = cast(
                List[UncheckedRetvalAnnotation],
                [a for a in state.get_annotations(UncheckedRetvalAnnotation)],
            )

        retvals = annotations[0].retvals

        if instruction["opcode"] in ("STOP", "RETURN"):
            issues = []
            for retval in retvals:
                try:
                    """
                    To check whether retval is unconstrained we are checking it against retval = 0 and retval = 1
                    """
                    solver.get_transaction_sequence(
                        state, state.world_state.constraints + [retval["retval"] == 1]
                    )
                    transaction_sequence = solver.get_transaction_sequence(
                        state, state.world_state.constraints + [retval["retval"] == 0]
                    )
                except UnsatError:
                    continue

                description_tail = (
                    "External calls return a boolean value. If the callee halts with an exception, 'false' is "
                    "returned and execution continues in the caller. "
                    "The caller should check whether an exception happened and react accordingly to avoid unexpected behavior. "
                    "For example it is often desirable to wrap external calls in require() so the transaction is reverted if the call fails."
                )

                issue = Issue(
                    contract=state.environment.active_account.contract_name,
                    function_name=state.environment.active_function_name,
                    address=retval["address"],
                    bytecode=state.environment.code.bytecode,
                    title="Unchecked return value from external call.",
                    swc_id=UNCHECKED_RET_VAL,
                    severity="Medium",
                    description_head="The return value of a message call is not checked.",
                    description_tail=description_tail,
                    gas_used=(state.mstate.min_gas_used, state.mstate.max_gas_used),
                    transaction_sequence=transaction_sequence,
                )
                conditions = [
                    And(*(state.world_state.constraints + [retval["retval"] == 1])),
                    And(*(state.world_state.constraints + [retval["retval"] == 0])),
                ]

                state.annotate(
                    IssueAnnotation(conditions=conditions, issue=issue, detector=self)
                )

                issues.append(issue)

            return issues
        else:
            log.debug("End of call, extracting retval")

            if state.environment.code.instruction_list[state.mstate.pc - 1][
                "opcode"
            ] not in ["CALL", "DELEGATECALL", "STATICCALL", "CALLCODE"]:
                # Return is pointless with OOG. The pc does not get updated in such cases
                return []

            return_value = state.mstate.stack[-1]
            retvals.append(
                {"address": state.instruction["address"] - 1, "retval": return_value}
            )

        return []


detector = UncheckedRetval()
