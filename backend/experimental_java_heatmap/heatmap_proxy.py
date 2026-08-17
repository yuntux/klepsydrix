def calculate_heatmap_java(problem, solver_factory, course_id: int) -> dict:
    target_course = next((c for c in problem.courses if c.id == course_id), None)
    if not target_course:
        return {}

    try:
        import time
        import jpype
        from _jpyinterpreter import convert_to_java_python_like_object

        # Régression (voir attribution_week_type_auto.md) : la Heatmap n'exécute JAMAIS le CH du
        # solveur (elle appelle directement setWorkingSolution()/calculateScore() sur les données
        # telles que chargées) — une @PlanningVariable encore None (non initialisée) exclut son
        # entité de TOUS les flux for_each()/for_each_unique_pair() (pas seulement des contraintes
        # qui s'y intéressent). C'était le cas de `classroom` avant le passage au domaine
        # COURSE_PLACEMENT (voir plan salles §2) : nécessitait une salle virtuelle pour tout cours
        # sans salle, cas fréquent. Devenu sans objet — `classroom` n'est plus une
        # @PlanningVariable de PlanningCourse, `leaf_classroom_ids` (liste, jamais None) et
        # l'absence de PlanningGroupDemand sont des états valides par construction, aucune
        # virtualisation nécessaire pour rendre un cours "visible" aux contraintes de salle.
        # `week_type`, lui, reste concerné (@PlanningVariable propre, cause distincte) :
        # Un cours né Q (week_type=None en entrée du solveur, voir Phase C) reste "non initialisé"
        # pendant tout le calcul — la boucle Java ne fait varier QUE timeslot, jamais week_type.
        # Vérifié empiriquement (SolutionManager.explain) : le cours CIBLE lui-même, une fois
        # virtuellement placé sur un créneau réel par la boucle, reste invisible aux contraintes
        # si week_type reste None — le timeslot seul ne suffit pas à "initialiser" l'entité. Pas
        # besoin d'une valeur hors range ici (contrairement à l'ancienne salle virtuelle) :
        # week_type n'a pas de notion d'unicité globale comparable à un id de salle.
        for c in problem.courses:
            if c.week_type is None:
                c.week_type = c.week_type_range[0]

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
        # Ne JAMAIS avaler ici : un `return {}` est indiscernable d'un résultat légitime
        # ("aucune donnée pour l'instant") côté appelant — l'erreur reste alors invisible en
        # usage normal, seulement visible sur stderr. On journalise pour le débogage local, puis
        # on relève : calculate_course_heatmap (solver.py) a déjà un except qui la transforme
        # proprement en {"error": ..., "traceback": ...} exploitable par l'appelant.
        import traceback
        print("Erreur Heatmap Java:", e)
        traceback.print_exc()
        raise
