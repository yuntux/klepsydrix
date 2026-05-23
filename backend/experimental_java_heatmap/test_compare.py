import sys
import os
from backend.app.core.database import SessionLocal

def test_api():
    db = SessionLocal()
    course_id = 1
    school_id = None
    
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))
    
    from app.solver.solver import _build_planning_problem, _get_solver_factory
    from experimental_java_heatmap.heatmap_proxy import calculate_heatmap_java

    problem = _build_planning_problem(db, school_id)
    solver_factory = _get_solver_factory()
    
    target_course = next((c for c in problem.courses if c.id == course_id), None)
    
    # Check score manually in Python first
    from timefold.solver import SolutionManager
    sm = SolutionManager.create(solver_factory)
    target_course.timeslot = None
    sc1 = sm.update(problem)
    print("Python base score:", sc1.hard_score if hasattr(sc1, 'hard_score') else 0)
    
    target_course.timeslot = problem.timeslots[0]
    sc2 = sm.update(problem)
    print("Python TS1 score:", sc2.hard_score if hasattr(sc2, 'hard_score') else 0)
    
    from _jpyinterpreter import convert_to_java_python_like_object
    import jpype
    import time
    
    java_problem = convert_to_java_python_like_object(problem)
    
    java_target = None
    for c in java_problem.getCourses():
        if c.getId() == course_id:
            java_target = c
            break
            
    sdf = solver_factory._delegate.getScoreDirectorFactory()
    fast_sd = sdf.buildScoreDirector()
    fast_sd.setWorkingSolution(java_problem)
    
    # Test incremental in Python via Java proxy mutation
    t0 = time.time()
    
    fast_sd.beforeVariableChanged(java_target, "timeslot")
    java_target.setTimeslot(None)
    fast_sd.afterVariableChanged(java_target, "timeslot")
    score_base = fast_sd.calculateScore()
    print("Java SD Base Score:", str(score_base))
    
    fast_sd.beforeVariableChanged(java_target, "timeslot")
    java_target.setTimeslot(java_problem.getTimeslots()[0])
    fast_sd.afterVariableChanged(java_target, "timeslot")
    score_ts1 = fast_sd.calculateScore()
    print("Java SD TS1 Score:", str(score_ts1))
    fast_sd.close()

    result = calculate_heatmap_java(problem, solver_factory, course_id)
    print("Java result TS1:", result[str(problem.timeslots[0].id)])
    
test_api()
