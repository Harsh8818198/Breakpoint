"""Breakpoint: evolutionary adversarial-user simulation engine."""
from .models import Blueprint, Agent, Finding, Flow
from .llm import LLMClient
from .blueprint import build_blueprint, interrogate
from .agents import build_population
from .evolution import simulate
from .report import render_report, evolution_tree

__all__ = [
    "Blueprint", "Agent", "Finding", "Flow", "LLMClient",
    "build_blueprint", "interrogate", "build_population", "simulate",
    "render_report", "evolution_tree",
]
