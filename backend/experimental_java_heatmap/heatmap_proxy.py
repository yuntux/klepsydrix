def calculate_heatmap_java(problem, solver_factory, course_id: int) -> dict:
    target_course = next((c for c in problem.courses if c.id == course_id), None)
    if not target_course:
        return {}
        
    try:
        import time
        import jpype
        from _jpyinterpreter import convert_to_java_python_like_object
        
        t0 = time.time()
        java_problem = convert_to_java_python_like_object(problem)
        t1 = time.time()
        print(f"DEBUG: convert_to_java_python_like_object a pris {t1 - t0:.4f}s")
        
        java_target = None
        for c in java_problem.getCourses():
            if c.getId() == course_id:
                java_target = c
                break
                
        java_timeslots = java_problem.getTimeslots()
        
        HeatmapEvaluator = jpype.JClass("org.klepsydrix.heatmap.HeatmapEvaluator")
        sdf = solver_factory._delegate.getScoreDirectorFactory()
        
        t2 = time.time()
        print(f"DEBUG: Setup Java pris {t2 - t1:.4f}s")
        java_heatmap = HeatmapEvaluator.calculateIsofunctionalHeatmap(
            sdf,
            java_problem,
            java_target,
            java_timeslots,
            "timeslot"
        )
        t3 = time.time()
        print(f"DEBUG: calculateIsofunctionalHeatmap (Java pur) a pris {t3 - t2:.4f}s")
        
        heatmap = {}
        for ts_id in java_heatmap.keySet():
            val = java_heatmap.get(ts_id)
            reasons = []
            java_reasons = val.get("reasons")
            if java_reasons:
                for r in java_reasons:
                    reasons.append({
                        "name": str(r.get("name")),
                        "impact_hard": int(r.get("impact_hard")),
                        "impact_soft": int(r.get("impact_soft"))
                    })
                    
            heatmap[str(ts_id)] = {
                "hard": int(val.get("hard")),
                "soft": int(val.get("soft")),
                "reasons": reasons
            }
            
        return heatmap
        
    except Exception as e:
        import traceback
        print("Erreur Heatmap Java:", e)
        traceback.print_exc()
        return {}
