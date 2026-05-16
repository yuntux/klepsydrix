import asyncio
from backend.app.core.database import SessionLocal
from backend.app.solver.solver import _build_planning_problem, _get_solver_factory
from timefold.solver import SolutionManager

db = SessionLocal()
problem = _build_planning_problem(db)
solver_factory = _get_solver_factory()
solution_manager = SolutionManager.create(solver_factory)
explanation = solution_manager.explain(problem)
print(dir(explanation.score))
db.close()
