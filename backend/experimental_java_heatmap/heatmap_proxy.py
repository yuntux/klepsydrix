def calculate_heatmap_java(problem, solver_factory, course_id: int) -> dict:
    target_course = next((c for c in problem.courses if c.id == course_id), None)
    if not target_course:
        return {}

    try:
        import time
        import jpype
        from _jpyinterpreter import convert_to_java_python_like_object
        from backend.app.solver.constraints import PlanningClassroom

        # Régression (voir attribution_week_type_auto.md) : la Heatmap n'exécute JAMAIS le CH du
        # solveur (elle appelle directement setWorkingSolution()/calculateScore() sur les données
        # telles que chargées) — un cours dont classroom vaut encore None (très courant : tout
        # cours non placé, ou placé mais sans salle assignée, cas fréquent dans ce jeu de
        # données) reste donc "non initialisé" pendant TOUTE la durée du calcul, jamais résolu
        # comme il le serait par un CH réel. Or Timefold exclut purement et simplement une entité
        # non initialisée des flux for_each()/for_each_unique_pair() ordinaires — pas seulement
        # pour les contraintes qui s'intéressent à classroom, pour TOUTES (teacher_conflict,
        # resource_preference_*, division_conflict...). Résultat mesuré : la heatmap d'un cours
        # sans salle n'affichait plus AUCUN impact des préférences ni des cours déjà placés,
        # quel que soit le créneau (grille entièrement "verte"). Vérifié par un test direct
        # (SolutionManager.explain) : un cours avec classroom=None ne déclenche aucun match pour
        # "Resource unavailability (strict)" ; avec une salle assignée, la même contrainte
        # redevient visible et pénalise correctement.
        # Correctif : donner une salle VIRTUELLE (id négatif, jamais dans classroomRange, jamais
        # partagée entre deux cours puisque dérivée de l'id du cours lui-même — donc jamais de
        # faux conflit classroom_conflict) à TOUT cours du problème dont classroom est encore
        # None, avant le calcul. Cette valeur reste IDENTIQUE tout au long du calcul (base et
        # chaque créneau testé) : tout bruit de score qu'elle introduirait entre deux AUTRES cours
        # est donc constant et s'annule déjà dans le delta calculé côté Java
        # (currentScore - baseScore) — seul compte ici de rendre les cours visibles aux
        # contraintes, pas la salle précise qui leur est temporairement associée. Purement en
        # mémoire, jamais committé (la Heatmap ne fait aucun commit BDD, voir architecture.md § 13.A).
        for c in problem.courses:
            if c.classroom is None:
                c.classroom = PlanningClassroom(id=-c.id, name="(salle virtuelle — heatmap)", capacity=0)
            # Même mécanisme, même cause, pour week_type : un cours né Q (week_type=None en
            # entrée du solveur, voir Phase C) reste "non initialisé" pendant tout le calcul —
            # la boucle Java ne fait varier QUE timeslot, jamais week_type. Vérifié empiriquement
            # (SolutionManager.explain) : identique au cas classroom, y compris pour le cours
            # CIBLE lui-même une fois virtuellement placé sur un créneau réel par la boucle — le
            # timeslot seul ne suffit pas à "initialiser" l'entité si week_type reste None.
            # Contrairement à classroom, pas besoin d'une valeur hors range : week_type n'a pas
            # de notion d'unicité globale comparable à un id de salle (voir architecture.md § 12.E).
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
