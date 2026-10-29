"""A judge that runs a proof against a library and says what happened. A script decides, never a model."""

from .node_judge import Verdict, check_pair, judge_proof

__all__ = ["Verdict", "check_pair", "judge_proof"]
