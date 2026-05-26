package org.klepsydrix.heatmap;

import ai.timefold.solver.core.api.score.Score;
import ai.timefold.solver.core.api.score.constraint.ConstraintMatchTotal;
import ai.timefold.solver.core.impl.score.director.InnerScoreDirector;
import ai.timefold.solver.core.impl.score.director.ScoreDirectorFactory;

import ai.timefold.solver.core.impl.score.constraint.ConstraintMatchPolicy;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class HeatmapEvaluator {

    public static Map<String, Map<String, Object>> calculateIsofunctionalHeatmap(
            ScoreDirectorFactory scoreDirectorFactory,
            Object problem,
            Object targetCourse,
            List<Object> timeslots,
            String variableName) {

        Map<String, Map<String, Object>> heatmap = new HashMap<>();

        // Le ScoreDirector rapide (sans ConstraintMatch)
        InnerScoreDirector fastScoreDirector = (InnerScoreDirector) scoreDirectorFactory.buildScoreDirector();
        
        // Le ScoreDirector détaillé (avec ConstraintMatch), initialisé seulement si nécessaire
        InnerScoreDirector detailedScoreDirector = null;
        Map<String, ConstraintMatchTotal> baseCmtMap = null;

        try {
            fastScoreDirector.setWorkingSolution(problem);

            Method setTimeslotMethod = null;
            for (Method m : targetCourse.getClass().getMethods()) {
                if (m.getName().equals("setTimeslot") && m.getParameterCount() == 1) {
                    setTimeslotMethod = m;
                    break;
                }
            }
            if (setTimeslotMethod == null) {
                throw new NoSuchMethodException("setTimeslot not found");
            }

            // 1. Calculer le score de base (créneau = null)
            Object fastWorkingCourse = findWorkingCourse(fastScoreDirector, targetCourse);
            fastScoreDirector.beforeVariableChanged(fastWorkingCourse, variableName);
            setTimeslotMethod.invoke(fastWorkingCourse, new Object[]{null});
            fastScoreDirector.afterVariableChanged(fastWorkingCourse, variableName);

            Object baseScore = fastScoreDirector.calculateScore();
            int baseHard = extractHardScore(baseScore);
            int baseSoft = extractSoftScore(baseScore);

            // 2. Boucler sur les créneaux
            for (Object ts : timeslots) {
                fastScoreDirector.beforeVariableChanged(fastWorkingCourse, variableName);
                setTimeslotMethod.invoke(fastWorkingCourse, ts);
                fastScoreDirector.afterVariableChanged(fastWorkingCourse, variableName);

                Object currentScore = fastScoreDirector.calculateScore();

                int currentHard = extractHardScore(currentScore);
                int currentSoft = extractSoftScore(currentScore);

                // L'annulation de la pénalité de non-assignation (ONE_HARD) améliore le score de +1 Hard.
                // Le delta de conflit physique réel est donc le score courant moins (baseHard + 1).
                int deltaHard = currentHard - (baseHard + 1);
                int deltaSoft = currentSoft - baseSoft;

                List<Map<String, Object>> reasons = new ArrayList<>();

                // N'expliquer que s'il y a dégradation
                if (deltaHard < 0 || deltaSoft < 0) {
                    if (detailedScoreDirector == null) {
                        detailedScoreDirector = (InnerScoreDirector) scoreDirectorFactory
                                .createScoreDirectorBuilder()
                                .withLookUpEnabled(true)
                                .withConstraintMatchPolicy(ConstraintMatchPolicy.ENABLED)
                                .build();
                        
                        // Recalculer la base pour detailedScoreDirector
                        detailedScoreDirector.setWorkingSolution(problem);
                        Object detailedWorkingCourse = findWorkingCourse(detailedScoreDirector, targetCourse);
                        detailedScoreDirector.beforeVariableChanged(detailedWorkingCourse, variableName);
                        setTimeslotMethod.invoke(detailedWorkingCourse, new Object[]{null});
                        detailedScoreDirector.afterVariableChanged(detailedWorkingCourse, variableName);
                        detailedScoreDirector.calculateScore();
                        baseCmtMap = new HashMap<>(detailedScoreDirector.getConstraintMatchTotalMap());
                        
                        // Remettre sur le TS actuel
                        detailedScoreDirector.beforeVariableChanged(detailedWorkingCourse, variableName);
                        setTimeslotMethod.invoke(detailedWorkingCourse, ts);
                        detailedScoreDirector.afterVariableChanged(detailedWorkingCourse, variableName);
                    } else {
                        // Mettre à jour le detailedScoreDirector
                        Object detailedWorkingCourse = findWorkingCourse(detailedScoreDirector, targetCourse);
                        detailedScoreDirector.beforeVariableChanged(detailedWorkingCourse, variableName);
                        setTimeslotMethod.invoke(detailedWorkingCourse, ts);
                        detailedScoreDirector.afterVariableChanged(detailedWorkingCourse, variableName);
                    }

                    detailedScoreDirector.calculateScore();
                    Map<String, ConstraintMatchTotal> currentCmtMap = detailedScoreDirector.getConstraintMatchTotalMap();

                    for (Map.Entry<String, ConstraintMatchTotal> entry : currentCmtMap.entrySet()) {
                        String constraintName = entry.getKey();
                        ConstraintMatchTotal currentCmt = entry.getValue();
                        ConstraintMatchTotal baseCmt = baseCmtMap.get(constraintName);

                        int curHard = extractHardScore(currentCmt.getScore());
                        int curSoft = extractSoftScore(currentCmt.getScore());

                        int bHard = baseCmt != null ? extractHardScore(baseCmt.getScore()) : 0;
                        int bSoft = baseCmt != null ? extractSoftScore(baseCmt.getScore()) : 0;

                        int diffHard = curHard - bHard;
                        int diffSoft = curSoft - bSoft;

                        if (diffHard < 0 || diffSoft < 0) {
                            Map<String, Object> reason = new HashMap<>();
                            reason.put("name", currentCmt.getConstraintRef().constraintName());
                            reason.put("impact_hard", diffHard);
                            reason.put("impact_soft", diffSoft);
                            reasons.add(reason);
                        }
                    }
                }

                Map<String, Object> tsResult = new HashMap<>();
                tsResult.put("hard", deltaHard);
                tsResult.put("soft", deltaSoft);
                tsResult.put("reasons", reasons);

                Method getIdMethod = ts.getClass().getMethod("getId");
                String tsId = String.valueOf(getIdMethod.invoke(ts));
                
                heatmap.put(tsId, tsResult);
            }
        } catch (Exception e) {
            e.printStackTrace();
        } finally {
            fastScoreDirector.close();
            if (detailedScoreDirector != null) {
                detailedScoreDirector.close();
            }
        }

        return heatmap;
    }

    private static int extractHardScore(Object score) {
        try {
            String s = score.toString();
            // Format can be: "-2hard/0soft" or "-36init/-2hard/0soft"
            int initIdx = s.indexOf("init/");
            if (initIdx != -1) {
                s = s.substring(initIdx + 5);
            }
            int hardIdx = s.indexOf("hard/");
            if (hardIdx != -1) {
                return Integer.parseInt(s.substring(0, hardIdx));
            }
            return 0;
        } catch (Exception e) {
            e.printStackTrace();
            return 0;
        }
    }

    private static int extractSoftScore(Object score) {
        try {
            String s = score.toString();
            int hardIdx = s.indexOf("hard/");
            if (hardIdx != -1) {
                s = s.substring(hardIdx + 5);
            }
            int softIdx = s.indexOf("soft");
            if (softIdx != -1) {
                return Integer.parseInt(s.substring(0, softIdx));
            }
            return 0;
        } catch (Exception e) {
            e.printStackTrace();
            return 0;
        }
    }

    private static Object findWorkingCourse(InnerScoreDirector scoreDirector, Object targetCourse) throws Exception {
        Object workingSolution = scoreDirector.getWorkingSolution();
        Method getCoursesMethod = workingSolution.getClass().getMethod("getCourses");
        List<?> workingCourses = (List<?>) getCoursesMethod.invoke(workingSolution);
        Method getIdMethod = targetCourse.getClass().getMethod("getId");
        Object targetId = getIdMethod.invoke(targetCourse);
        for (Object c : workingCourses) {
            if (getIdMethod.invoke(c).equals(targetId)) {
                return c;
            }
        }
        throw new RuntimeException("Working course clone not found for ID: " + targetId);
    }
}
