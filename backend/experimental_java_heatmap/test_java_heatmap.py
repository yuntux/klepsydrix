import sys
import os
import time

from backend.app.core.database import SessionLocal
from backend.app.solver.solver import _build_planning_problem, _get_solver_factory

db = SessionLocal()
problem = _build_planning_problem(db)
solver_factory = _get_solver_factory()

# 3. Accès au HeatmapEvaluator compilé en Java
HeatmapEvaluator = jpype.JClass("org.klepsydrix.heatmap.HeatmapEvaluator")

sdf = solver_factory._delegate.getScoreDirectorFactory()
target_course = problem.courses[0]

print("Appel de la méthode Java...")
start = time.time()
heatmap = HeatmapEvaluator.calculateHeatmap(
    sdf,
    problem,
    target_course,
    problem.timeslots,
    "timeslot"
)
end = time.time()

print(f"L'évaluation de {len(problem.timeslots)} créneaux a pris {end - start:.4f}s")
