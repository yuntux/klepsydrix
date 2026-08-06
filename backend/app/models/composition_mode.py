"""
Modes de composition des cours complexes pour Klepsydrix.

Ces 9 modes s'appuient obligatoirement sur un "mapping" fourni par
l'utilisateur qui précise la répartition spatiale (qui voit qui, dans quelle salle).
Les modes (1-9) appliquent ensuite la logique temporelle (alternances, décalages, périodes).
"""

from sqlalchemy.orm import Session
from backend.app.models.course import Course


class CompositionError(Exception):
    pass


class CompositionModes:

    @staticmethod
    def _get_second_half_offset(db: Session, course: Course) -> int:
        from backend.app.models.system_setting import SystemSetting
        val = SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION")
        duration = int(val)
        return (course.duration_minutes // 2) // duration

    @staticmethod
    def _next_number_suffix(db: Session, existing_count: int, setting_key: str) -> str:
        from backend.app.models.system_setting import SystemSetting, NUMBER_FORMAT_ALPHABETIC
        number_format = SystemSetting.get_system_setting_value(db, setting_key) or "numerique"
        n = existing_count + 1
        if number_format != NUMBER_FORMAT_ALPHABETIC:
            return str(n)
        # 1 -> A, 2 -> B, ..., 26 -> Z, 27 -> AA, ... (comme la numérotation des colonnes d'un tableur)
        letters = ""
        while n > 0:
            n, rem = divmod(n - 1, 26)
            letters = chr(65 + rem) + letters
        return letters

    @staticmethod
    def _compute_group_name(db: Session, division_id, subject_id, class_part_ids: list) -> str:
        """
        Nom d'un groupe auto-généré, piloté par le paramétrage système GROUP_NAME_* : concaténation
        de la première lettre du code classe (si activé et déterminable — un groupe peut mêler des
        parties de plusieurs divisions, auquel cas division_id vaut None et ce segment est omis), du
        séparateur, du code matière (si activé), puis d'un numéro/lettre rendant le nom unique parmi
        les groupes déjà en base dont le nom commence par ce même préfixe.
        """
        from backend.app.models.system_setting import SystemSetting
        from backend.app.models.division import Division
        from backend.app.models.subject import Subject
        from backend.app.models.group import Group

        has_div_code = SystemSetting.get_system_setting_value(db, "GROUP_NAME_HAS_DIV_CODE") == "true"
        has_subject_code = SystemSetting.get_system_setting_value(db, "GROUP_NAME_HAS_SUBJECT_CODE") == "true"
        separator = SystemSetting.get_system_setting_value(db, "GROUP_NAME_SEPARATOR") or "G"

        prefix = ""
        if has_div_code and division_id:
            division = db.get(Division, division_id)
            if division and division.code:
                prefix += division.code[0]
        prefix += separator
        if has_subject_code and subject_id:
            subject = db.get(Subject, subject_id)
            if subject:
                prefix += subject.code

        existing_count = db.query(Group).filter(Group.name.like(f"{prefix}%")).count()
        return prefix + CompositionModes._next_number_suffix(db, existing_count, "GROUP_NAME_NUMBER_FORMAT")

    @staticmethod
    def _resolve_dynamic_groups(db: Session, course: Course, mapping: list[dict]):
        from backend.app.models.group import Group, ClassPart
        for row in mapping:
            cp_ids = set(row.get('class_part_ids', []))
            if len(cp_ids) > 1 and not row.get('group_ids'):
                existing_groups = db.query(Group).all()
                found_group = None
                for g in existing_groups:
                    g_cp_ids = {cp.id for cp in g.class_parts}
                    if g_cp_ids == cp_ids:
                        found_group = g
                        break

                if found_group:
                    row['group_ids'] = row.get('group_ids', []) + [found_group.id]
                    if found_group not in course.groups:
                        course.update(db, {"group_ids": [g.id for g in course.groups] + [found_group.id]})
                else:
                    class_parts = [db.get(ClassPart, cid) for cid in cp_ids]
                    division_ids = {cp.division_id for cp in class_parts if cp}
                    common_division_id = next(iter(division_ids)) if len(division_ids) == 1 else None
                    new_group = Group.create(db, {
                        "name": CompositionModes._compute_group_name(db, common_division_id, row.get('subject_id'), cp_ids),
                        "class_part_ids": list(cp_ids),
                        "is_system_generated": True,
                    })
                    row['group_ids'] = row.get('group_ids', []) + [new_group.id]
                    course.update(db, {"group_ids": [g.id for g in course.groups] + [new_group.id]})

                db.flush()
                # On vide class_part_ids car le groupe englobe ces parties
                row['class_part_ids'] = []

    @staticmethod
    def _compute_class_part_name(db: Session, division_id, subject_id) -> str:
        """Miroir de _compute_group_name, piloté par le paramétrage système DIVISION_PART_NAME_*."""
        from backend.app.models.system_setting import SystemSetting
        from backend.app.models.division import Division
        from backend.app.models.subject import Subject
        from backend.app.models.group import ClassPart

        has_div_code = SystemSetting.get_system_setting_value(db, "DIVISION_PART_NAME_HAS_DIV_CODE") == "true"
        has_subject_code = SystemSetting.get_system_setting_value(db, "DIVISION_PART_NAME_HAS_SUBJECT_CODE") == "true"
        separator = SystemSetting.get_system_setting_value(db, "DIVISION_PART_NAME_SEPARATOR") or "P"

        prefix = ""
        if has_div_code and division_id:
            division = db.get(Division, division_id)
            if division:
                prefix += division.code[0]
        if has_subject_code and subject_id:
            subject = db.get(Subject, subject_id)
            if subject:
                prefix += subject.code
        prefix += separator

        existing_count = db.query(ClassPart).filter(ClassPart.name.like(f"{prefix}%")).count()
        return prefix + CompositionModes._next_number_suffix(db, existing_count, "DIVISION_PART_NAME_NUMBER_FORMAT")

    @staticmethod
    def _compute_partition_label(db: Session, course: Course, subject_ids: set) -> str:
        """
        Nom (et code) de la partition qui accueille les parties de classe auto-générées pour une
        division donnée : la matière "chapeau" du cours complexe si elle est désignée, sinon la
        concaténation des matières des lignes de répartition qui alimentent cette division.
        """
        from backend.app.models.subject import Subject
        if course.subject_id:
            subject = db.get(Subject, course.subject_id)
            return subject.code if subject else str(course.subject_id)
        codes = sorted(s.code for s in (db.get(Subject, sid) for sid in subject_ids if sid) if s)
        return "+".join(codes) if codes else "AUTO"

    @staticmethod
    def _resolve_dynamic_part_class(db: Session, course: Course, mapping: list[dict]):
        """
        Convertit les lignes de répartition ciblant une classe entière (division_ids) en parties
        de classe (class_part_ids), par clé fonctionnelle {division, matière de la ligne} :
        réutilise une ClassPart existante pour cette clé si elle existe, sinon en crée une nouvelle
        — rattachée à une Partition commune à toutes les matières composées pour cette division
        lors de cet appel (une seule Partition créée par division, réutilisée pour chaque matière).

        Attention : la clé de recherche/création est la matière PROPRE À LA LIGNE de répartition
        (row['subject_id']), jamais la matière "chapeau" du cours complexe (course.subject_id) —
        celle-ci ne sert qu'à nommer la Partition, cf. _compute_partition_label.
        """
        from backend.app.models.group import Partition, ClassPart

        subjects_by_division: dict[int, set] = {}
        for row in mapping:
            if not row.get('division_ids'):
                continue
            if not row.get('subject_id'):
                raise CompositionError("Impossible de générer les parties de classe : une ligne de répartition ciblant une classe entière n'a pas de matière renseignée.")
            for division_id in row['division_ids']:
                subjects_by_division.setdefault(division_id, set()).add(row.get('subject_id'))

        if not subjects_by_division:
            return

        partitions_by_division: dict[int, Partition] = {}

        for row in mapping:
            if not row.get('division_ids'):
                continue

            subject_id = row.get('subject_id')
            class_part_ids = []
            for division_id in row['division_ids']:
                existing = (
                    db.query(ClassPart)
                    .join(Partition, ClassPart.partition_id == Partition.id)
                    .filter(Partition.division_id == division_id, ClassPart.subject_id == subject_id)
                    .first()
                )
                if existing:
                    resolved_class_part = existing
                else:
                    partition = partitions_by_division.get(division_id)
                    if partition is None:
                        label = CompositionModes._compute_partition_label(db, course, subjects_by_division[division_id])
                        partition = Partition.create(db, {"code": label, "name": label, "division_id": division_id, "is_system_generated": True})
                        partitions_by_division[division_id] = partition

                    resolved_class_part = ClassPart.create(db, {
                        "partition_id": partition.id,
                        "name": CompositionModes._compute_class_part_name(db, division_id, subject_id),
                        "subject_id": subject_id,
                        "is_system_generated": True,
                    })

                # Le cours parent doit lister cette ClassPart pour que ses enfants (qui la
                # référencent) passent validate_child_constraints (miroir de _resolve_dynamic_groups).
                if resolved_class_part not in course.class_parts:
                    course.update(db, {"class_part_ids": [cp.id for cp in course.class_parts] + [resolved_class_part.id]})

                class_part_ids.append(resolved_class_part.id)

            row['class_part_ids'] = class_part_ids
            row['division_ids'] = []

    @staticmethod
    def get_available_modes(db: Session, course: Course, mapping: list[dict]) -> list[int]:
        """
        Retourne la liste des IDs des modes (1-9) applicables selon 
        la configuration du cours (ex: nombre de périodes) et le mapping.
        """
        valid_mapping = [
            row for row in (mapping or [])
            if row.get('teacher_ids') and (
                row.get('group_ids') or 
                row.get('class_part_ids') or 
                row.get('division_ids')
            )
        ]
        n = len(valid_mapping)
        periods_count = len(course.periods)
        
        from backend.app.models.system_setting import SystemSetting
        val = SystemSetting.get_system_setting_value(db, "STANDARD_TIMESLOT_DURATION")
        duration = int(val)
        
        available = []
        if n >= 1:
            available.extend([1, 2])
            
        if n >= 2:
            # Modes 3 et 4 coupent le cours en 2, la durée doit donc être au moins 2 * duration et un multiple exact
            if course.duration_minutes % (2 * duration) == 0:
                available.extend([3, 4])
            available.append(5) # Mode 5 ne coupe pas le cours en 2
            
        if n >= 3:
            available.append(6)
            
        if periods_count >= 2 and n >= 2:
            available.extend([7, 8, 9])
            
        return sorted(list(set(available)))

    @staticmethod
    def apply(db: Session, course: Course, mode: int, mapping: list[dict] = None, preview: bool = False) -> list:
        if not course.is_composed:
            raise CompositionError("Le cours doit être un cours composé (is_composed=True).")

        mapping = mapping or []
        if not mapping:
            raise CompositionError("Un mapping (répartition spatiale) est obligatoire pour composer le cours.")

        seen_teachers = set()
        for row in mapping:
            has_teacher = bool(row.get('teacher_ids'))
            has_target = bool(row.get('group_ids') or row.get('class_part_ids') or row.get('division_ids'))

            if not has_teacher or not has_target:
                raise CompositionError("Chaque ligne de répartition doit obligatoirement inclure au moins un professeur ET au moins une cible (groupe, partie de classe ou classe).")

            if not row.get('subject_id'):
                raise CompositionError("Chaque ligne de répartition doit obligatoirement indiquer une matière.")

            # Vérification de l'exclusion mutuelle des cibles
            targets = [bool(row.get('group_ids')), bool(row.get('class_part_ids')), bool(row.get('division_ids'))]
            if sum(targets) > 1:
                raise CompositionError("Un groupe, une partie de classe et une classe ne peuvent pas être affectés simultanément sur la même ligne de répartition.")
                
            # Vérification de l'unicité des profs par ligne
            for teacher_id in (row.get('teacher_ids') or []):
                if teacher_id in seen_teachers:
                    raise CompositionError(f"Le professeur (ID: {teacher_id}) ne peut pas être affecté sur plusieurs lignes de répartition différentes.")
                seen_teachers.add(teacher_id)

        available_modes = CompositionModes.get_available_modes(db, course, mapping)
        if mode not in available_modes:
            raise CompositionError(f"Le mode {mode} n'est pas applicable avec la répartition actuelle (ex: pas assez de lignes, groupes ou périodes). Modes possibles: {available_modes}")

        CompositionModes._resolve_dynamic_part_class(db, course, mapping)
        CompositionModes._resolve_dynamic_groups(db, course, mapping)

        former_class_part_ids: set = set()
        former_group_ids: set = set()
        if not preview:
            # Delete existing children via CRUDMixin pour respecter les callbacks et suppressions en cascade.
            # _skip_resource_cleanup=True : le nettoyage (voir backend/app/models/group.py,
            # cleanup_orphaned_resources) est différé après la recréation des enfants ci-dessous —
            # sans ça, une partie de classe/un groupe réutilisé par le nouveau mapping serait
            # supprimé pour de vrai avant même d'être rattaché au nouvel enfant.
            children_to_delete = db.query(Course).filter(Course.parent_id == course.id).all()
            for child in children_to_delete:
                former_class_part_ids.update(cp.id for cp in child.class_parts)
                former_group_ids.update(g.id for g in child.groups)
                child.delete(db, _skip_resource_cleanup=True)

        method = getattr(CompositionModes, f"_mode_{mode}", None)
        if method is None:
            raise CompositionError(f"Mode {mode} non implémenté (valeurs autorisées : 1-9).")

        vals_list = method(db, course, mapping)
        # Calculé une seule fois ici (plutôt que dans _build_base_vals) car certains modes
        # réaffectent teacher_ids après coup (rotation de profs entre lignes, ex: modes 3/4/5/8) :
        # is_co_teaching doit refléter la liste de profs finale, quel que soit le mode.
        for v in vals_list:
            v['is_co_teaching'] = len(v.get('teacher_ids', [])) > 1

        if preview:
            return vals_list
        else:
            children = []
            for v in vals_list:
                children.append(Course.create(db, v))
            from backend.app.models.group import cleanup_orphaned_resources
            cleanup_orphaned_resources(db, list(former_class_part_ids), list(former_group_ids))
            return children

    @staticmethod
    def _build_base_vals(course: Course, map_row: dict) -> dict:
        """
        Fusionne les données communes du parent avec les ressources spécifiques du mapping.

        subject_id vient en priorité de la ligne de mapping, avec repli sur celui du parent :
        un cours composé parent a souvent subject_id=NULL (ex: un cours "Pôle Sciences" qui
        regroupe SVT/Physique-Chimie/Techno, chaque enfant ayant sa propre matière) — sans ce
        repli sur le mapping, tous les enfants générés hériteraient de ce NULL, alors que chaque
        enfant est un cours "simple" pour lequel une matière est censée être obligatoire.
        """
        return {
            'subject_id': map_row.get('subject_id') or course.subject_id,
            'school_id': course.school_id,
            'duration_minutes': course.duration_minutes,
            'parent_id': course.id,
            'is_composed': False,
            'week_type': course.week_type.value,
            'period_type_id': course.period_type_id,
            'material_ids': [r.id for r in course.materials],
            'non_teaching_staff_ids': [r.id for r in course.non_teaching_staffs],
            # Ressources spatiales fournies par le mapping (ou liste vide si omis)
            'teacher_ids': map_row.get('teacher_ids', []),
            'classroom_ids': map_row.get('classroom_ids', []),
            'division_ids': map_row.get('division_ids', []),
            'class_part_ids': map_row.get('class_part_ids', []),
            'group_ids': map_row.get('group_ids', []),
            'period_ids': map_row.get('period_ids', [r.id for r in course.periods]),
        }

    # ------------------------------------------------------------------ #
    #   Modes 1 & 2 : Répartition simple                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _mode_1(db: Session, course: Course, mapping: list[dict]) -> list[dict]:
        """Mode 1 : Une séance par professeur (1 enfant par ligne de mapping)."""
        children = []
        for row in mapping:
            vals = CompositionModes._build_base_vals(course, row)
            children.append(vals)
        return children

    @staticmethod
    def _mode_2(db: Session, course: Course, mapping: list[dict]) -> list[dict]:
        """Mode 2 : Une séance par professeur pour chaque quinzaine (2 enfants par ligne)."""
        children = []
        for row in mapping:
            for week in ['A', 'B']:
                vals = CompositionModes._build_base_vals(course, row)
                vals['week_type'] = week
                children.append(vals)
        return children

    # ------------------------------------------------------------------ #
    #   Modes 3 & 4 : Barrettes avec rotation de sous-groupes            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _mode_3(db: Session, course: Course, mapping: list[dict]) -> list[dict]:
        """Mode 3 : Barrette - professeurs changent de groupe à mi-cours."""
        children = []
        offset = CompositionModes._get_second_half_offset(db, course)
        n = len(mapping)
        if n == 0:
            return children

        for i, row in enumerate(mapping):
            # 1ère moitié
            vals_1 = CompositionModes._build_base_vals(course, row)
            vals_1['duration_minutes'] = course.duration_minutes // 2
            vals_1['parent_timeslot_offset'] = 0
            children.append(vals_1)
            
            # 2ème moitié (rotation circulaire des professeurs)
            # T[i] prend le groupe de la ligne G[(i+1)%n] (donc on attribue le prof de "n-1-i" ou "i+1")
            next_row = mapping[(i + 1) % n]
            vals_2 = CompositionModes._build_base_vals(course, row)
            vals_2['duration_minutes'] = course.duration_minutes // 2
            vals_2['parent_timeslot_offset'] = offset
            vals_2['teacher_ids'] = next_row.get('teacher_ids', [])
            children.append(vals_2)

        return children

    @staticmethod
    def _mode_4(db: Session, course: Course, mapping: list[dict]) -> list[dict]:
        """Mode 4 : Barrette + alternance quinzaine."""
        children = []
        offset = CompositionModes._get_second_half_offset(db, course)
        n = len(mapping)
        if n == 0:
            return children

        for i, row in enumerate(mapping):
            next_row = mapping[(i + 1) % n]

            # Semaine A
            vals_a1 = CompositionModes._build_base_vals(course, row)
            vals_a1['week_type'] = 'A'
            vals_a1['duration_minutes'] = course.duration_minutes // 2
            vals_a1['parent_timeslot_offset'] = 0
            children.append(vals_a1)

            vals_a2 = CompositionModes._build_base_vals(course, row)
            vals_a2['week_type'] = 'A'
            vals_a2['duration_minutes'] = course.duration_minutes // 2
            vals_a2['parent_timeslot_offset'] = offset
            vals_a2['teacher_ids'] = next_row.get('teacher_ids', [])
            children.append(vals_a2)

            # Semaine B (Inverse de la Semaine A)
            vals_b1 = CompositionModes._build_base_vals(course, row)
            vals_b1['week_type'] = 'B'
            vals_b1['duration_minutes'] = course.duration_minutes // 2
            vals_b1['parent_timeslot_offset'] = 0
            vals_b1['teacher_ids'] = next_row.get('teacher_ids', [])
            children.append(vals_b1)

            vals_b2 = CompositionModes._build_base_vals(course, row)
            vals_b2['week_type'] = 'B'
            vals_b2['duration_minutes'] = course.duration_minutes // 2
            vals_b2['parent_timeslot_offset'] = offset
            children.append(vals_b2)

        return children

    # ------------------------------------------------------------------ #
    #   Mode 5 : Rotation quinzaine croisée                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _mode_5(db: Session, course: Course, mapping: list[dict]) -> list[dict]:
        """Mode 5 : Les professeurs changent de classe à chaque quinzaine."""
        children = []
        n = len(mapping)
        if n == 0:
            return children

        for i, row in enumerate(mapping):
            # Semaine A (direct)
            vals_a = CompositionModes._build_base_vals(course, row)
            vals_a['week_type'] = 'A'
            children.append(vals_a)

            # Semaine B (rotation)
            next_row = mapping[(i + 1) % n]
            vals_b = CompositionModes._build_base_vals(course, row)
            vals_b['week_type'] = 'B'
            vals_b['teacher_ids'] = next_row.get('teacher_ids', [])
            children.append(vals_b)

        return children

    # ------------------------------------------------------------------ #
    #   Mode 6 : Trois groupes / Deux classes                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _mode_6(db: Session, course: Course, mapping: list[dict]) -> list[dict]:
        """
        Mode 6 : Trois groupes pour deux classes.
        Le mapping doit contenir 3 lignes.
        La ligne 0 sera appliquée aux Semaines A et B.
        La ligne 1 en Semaine A.
        La ligne 2 en Semaine B.
        """
        children = []
        if len(mapping) < 3:
            raise CompositionError("Mode 6 : le mapping doit contenir au moins 3 groupes configurés.")

        # G1 (Semaines A et B)
        for week in ['A', 'B']:
            vals = CompositionModes._build_base_vals(course, mapping[0])
            vals['week_type'] = week
            children.append(vals)

        # G2 (Semaine A)
        vals_a = CompositionModes._build_base_vals(course, mapping[1])
        vals_a['week_type'] = 'A'
        children.append(vals_a)

        # G3 (Semaine B)
        vals_b = CompositionModes._build_base_vals(course, mapping[2])
        vals_b['week_type'] = 'B'
        children.append(vals_b)

        return children

    # ------------------------------------------------------------------ #
    #   Modes 7-9 : Variations par période                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _mode_7(db: Session, course: Course, mapping: list[dict]) -> list[dict]:
        """
        Mode 7 : Un groupe a cours au S1, l'autre au S2.
        Le mapping indique quelle ligne va avec quelle période.
        Si la ligne a des period_ids spécifiques, on les utilise, 
        sinon on associe la ligne i avec la période i.
        """
        children = []
        periods = list(course.periods)
        if not periods:
            raise CompositionError("Mode 7 : le cours parent doit être lié à au moins une période.")

        for i, row in enumerate(mapping):
            vals = CompositionModes._build_base_vals(course, row)
            if not row.get('period_ids'):
                period_idx = i % len(periods)
                vals['period_ids'] = [periods[period_idx].id]
            children.append(vals)
        return children

    @staticmethod
    def _mode_8(db: Session, course: Course, mapping: list[dict]) -> list[dict]:
        """Mode 8 : Les professeurs changent de groupe à chaque période."""
        children = []
        periods = list(course.periods)
        n = len(mapping)
        if not periods or n == 0:
            return children

        for pi, period in enumerate(periods):
            for i, row in enumerate(mapping):
                teacher_source_row = mapping[(i + pi) % n]
                vals = CompositionModes._build_base_vals(course, row)
                vals['teacher_ids'] = teacher_source_row.get('teacher_ids', [])
                vals['period_ids'] = [period.id]
                children.append(vals)
        return children

    @staticmethod
    def _mode_9(db: Session, course: Course, mapping: list[dict]) -> list[dict]:
        """Mode 9 : Un groupe unique change de professeur à chaque période."""
        children = []
        periods = list(course.periods)
        n = len(mapping)
        if not periods or n == 0:
            return children

        for pi, period in enumerate(periods):
            # Pour chaque période, on ne crée qu'une seule séance (un seul groupe)
            # On prend le professeur de la ligne de mapping correspondante (modulo n)
            row = mapping[pi % n]
            vals = CompositionModes._build_base_vals(course, row)
            vals['period_ids'] = [period.id]
            children.append(vals)
            
        return children