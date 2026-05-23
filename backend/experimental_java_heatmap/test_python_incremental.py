import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))
from backend.app.core.database import SessionLocal
from backend.app.solver.solver import _build_planning_problem, _get_solver_factory
from timefold.solver._timefold_java_interop import get_class

db = SessionLocal()
problem = _build_planning_problem(db)
solver_factory = _get_solver_factory()

# Accès au factory interne Java
sdf = solver_factory._delegate.getScoreDirectorFactory()
sd = sdf.buildScoreDirector(True, True)

print("ScoreDirector créé!")
print("Conversion du problème vers Java (fait par jpype automatiquement en général)...")

# Mais sd.setWorkingSolution(problem) demande un objet Java Solution_.
# Dans Timefold Python, SolutionManager utilise _solution_manager.py qui fait:
# delegate.update(solution) où delegate attend le type solution.
# Essayons directement avec le problème python:
try:
    sd.setWorkingSolution(problem)
    print("setWorkingSolution a fonctionné avec l'objet Python !")
except Exception as e:
    print("Erreur:", e)

