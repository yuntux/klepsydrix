"""
Modes de composition des cours complexes pour Klepsydrix.

Ces 9 modes s'appuient obligatoirement sur un "mapping" fourni par
l'utilisateur qui précise la répartition spatiale (qui voit qui, dans quelle salle).
Les modes (1-9) appliquent ensuite la logique temporelle (alternances, décalages, périodes).
"""

import json
from sqlalchemy.orm import Session
from backend.app.models.course import Course
from backend.app.models.base import TransientModel


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
    def _partition_token(division_id: int, subject_ids) -> str:
        """Jeton virtuel déterministe identifiant "la Partition de cette division couvrant
        exactement cet ensemble de matières" avant qu'elle n'existe réellement — même division +
        même ensemble de matières (peu importe l'ordre) produit toujours le même jeton, pour que
        régénérer l'aperçu avec un mapping inchangé ne duplique rien."""
        return f"classpart:{division_id}:{'-'.join(str(s) for s in sorted(subject_ids))}"

    @staticmethod
    def _group_token(real_class_part_ids, pending_class_part_tokens) -> str:
        """Jeton virtuel déterministe pour un Group pas encore créé, dérivé de l'ensemble complet
        (réel + en attente) de ses parties de classe — voir _partition_token."""
        parts = sorted(str(i) for i in real_class_part_ids) + sorted(pending_class_part_tokens)
        return f"group:{'-'.join(parts)}"

    @staticmethod
    def _pending_class_part_label(db: Session, division_id: int, subject_id) -> str:
        from backend.app.models.division import Division
        from backend.app.models.subject import Subject
        division = db.get(Division, division_id)
        subject = db.get(Subject, subject_id) if subject_id else None
        div_label = division.name if division else str(division_id)
        subj_label = subject.name if subject else "matière non définie"
        return f"Partie de classe à créer : {div_label} / {subj_label}"

    @staticmethod
    def _pending_group_label() -> str:
        return "Groupe à créer"

    @staticmethod
    def _resolve_dynamic_groups(db: Session, course: Course, mapping: list[dict], materialize: bool):
        """
        materialize=True (chemin direct legacy, compose_by_mode) : comportement historique
        inchangé, écrit réellement en base. materialize=False (aperçu du wizard,
        rpc_preview_composition) : AUCUNE écriture — voir _resolve_dynamic_part_class et
        CompositionModes.materialize_pending_resources (résolution réelle à la sauvegarde).
        """
        from backend.app.models.group import find_group, find_or_create_group
        CompositionModes._resolve_dynamic_part_class(db, course, mapping, materialize)
        for row in mapping:
            real_cp_ids = sorted(set(row.get('class_part_ids', [])))
            pending_class_parts = row.get('pending_class_parts', [])
            pending_tokens = sorted(p["token"] for p in pending_class_parts)
            if len(real_cp_ids) + len(pending_tokens) <= 1 or row.get('group_ids'):
                continue

            if not pending_tokens and materialize:
                group = find_or_create_group(db, real_cp_ids, row.get('subject_id'))
                row['group_ids'] = row.get('group_ids', []) + [group.id]
                if group not in course.groups:
                    course.update(db, {"group_ids": [g.id for g in course.groups] + [group.id]})
                db.flush()
                # On vide class_part_ids : le groupe englobe ces parties, et
                # Course._apply_group_class_part_cascade les réinjecte de toute façon
                # automatiquement sur l'enfant dès que group_ids est appliqué (règle 1).
                row['class_part_ids'] = []
                continue

            if not pending_tokens:
                existing = find_group(db, real_cp_ids)
                if existing:
                    row['group_ids'] = row.get('group_ids', []) + [existing.id]
                    row['class_part_ids'] = []
                    continue

            # Au moins une partie de classe n'existe pas encore : le groupe non plus ne peut pas
            # exister (sa clé d'identité est l'ensemble des ids RÉELS de ses parties de classe) —
            # jamais de recherche ici, uniquement une mise en attente. class_part_ids réels
            # capturés dans le jeton pour que materialize_pending_resources retrouve le lot complet.
            row['pending_group'] = {
                "token": CompositionModes._group_token(real_cp_ids, pending_tokens),
                "class_part_ids": real_cp_ids,
                "label": CompositionModes._pending_group_label(),
            }
            row['class_part_ids'] = []

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
    def _resolve_dynamic_part_class(db: Session, course: Course, mapping: list[dict], materialize: bool):
        """
        Convertit les lignes de répartition ciblant une classe entière (division_ids) en parties
        de classe (class_part_ids) : une Partition par division est trouvée (et, si materialize,
        créée) pour couvrir toutes les matières composées sur cette division lors de cet appel,
        puis chaque ligne y retrouve la ClassPart de sa propre matière.

        materialize=False (aperçu du wizard) : AUCUNE écriture en base. Toute Partition/ClassPart
        qui n'existe pas encore reçoit un jeton virtuel déterministe dans row['pending_class_parts']
        plutôt qu'un id réel — résolu pour de vrai uniquement à la sauvegarde (voir
        rpc_save_composition -> CompositionModes.materialize_pending_resources). materialize=True
        (compose_by_mode legacy, jamais appelé depuis le wizard) : comportement historique inchangé.

        Attention : la clé de recherche/création est la matière PROPRE À LA LIGNE de répartition
        (row['subject_id']), jamais la matière "chapeau" du cours complexe (course.subject_id) —
        celle-ci ne sert qu'à nommer la Partition, cf. _compute_partition_label.
        """
        from backend.app.models.group import find_partition, find_or_create_partition

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

        # Une Partition par division, couvrant AU MOINS toutes les matières nécessaires à cet
        # appel (voir find_or_create_partition) — résolue une seule fois par division, réutilisée
        # pour chaque ligne de mapping ciblant cette division. En aperçu (materialize=False),
        # aucune écriture : une division sans Partition existante correspondante reçoit un jeton.
        partitions_by_division: dict[int, "Partition"] = {}
        pending_by_division: dict[int, tuple] = {}
        for division_id, subject_ids in subjects_by_division.items():
            if materialize:
                partitions_by_division[division_id] = find_or_create_partition(
                    db, division_id,
                    CompositionModes._compute_partition_label(db, course, subject_ids),
                    subject_ids=list(subject_ids),
                )
            else:
                existing = find_partition(db, division_id, subject_ids=list(subject_ids))
                if existing:
                    partitions_by_division[division_id] = existing
                else:
                    pending_by_division[division_id] = (
                        CompositionModes._partition_token(division_id, subject_ids),
                        sorted(subject_ids),
                    )

        for row in mapping:
            if not row.get('division_ids'):
                continue

            subject_id = row.get('subject_id')
            class_part_ids = []
            pending_class_parts = list(row.get('pending_class_parts', []))
            for division_id in row['division_ids']:
                if division_id in partitions_by_division:
                    partition = partitions_by_division[division_id]
                    resolved_class_part = next(cp for cp in partition.class_parts if cp.subject_id == subject_id)

                    # Le cours parent doit lister cette ClassPart pour que ses enfants (qui la
                    # référencent) passent validate_child_constraints (miroir de _resolve_dynamic_groups).
                    if materialize and resolved_class_part not in course.class_parts:
                        course.update(db, {"class_part_ids": [cp.id for cp in course.class_parts] + [resolved_class_part.id]})

                    class_part_ids.append(resolved_class_part.id)
                else:
                    token, partition_subject_ids = pending_by_division[division_id]
                    pending_class_parts.append({
                        "token": token,
                        "division_id": division_id,
                        "subject_id": subject_id,
                        "partition_subject_ids": partition_subject_ids,
                        "label": CompositionModes._pending_class_part_label(db, division_id, subject_id),
                    })

            row['class_part_ids'] = class_part_ids
            row['division_ids'] = []
            if pending_class_parts:
                row['pending_class_parts'] = pending_class_parts

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
    def default_mapping(course: Course) -> list[dict]:
        """
        Mapping initial proposé à l'ouverture du wizard : une ligne par professeur déjà affecté au
        cours, matière pré-remplie depuis sa matière préférée — exposé par Course.composition_mapping
        (course.py), repris tel quel par GenericWizard.vue via draft = {...props.model}.

        `id` : identifiant purement local à ce widget (jamais un id réel de quoi que ce soit, jamais
        relu par le backend — _build_base_vals/apply() n'y touchent pas) mais OBLIGATOIRE : GenericList.
        vue suit chaque ligne éditable par `item.id` (`:key`, Map d'édition en attente `pendingUpdates`
        keyée par id) — sans id unique par ligne, toutes les lignes partagent la même clé `undefined`
        et une édition sur une ligne se répercute sur toutes les autres. ListPreviewField.vue poursuit
        cette même numérotation pour toute ligne ajoutée ensuite via "+ Ajouter une ligne".
        """
        return [
            {
                "id": index + 1,
                "teacher_ids": [teacher.id],
                "subject_id": teacher.preferred_subject_id,
                "group_ids": [], "class_part_ids": [], "division_ids": [], "classroom_ids": [],
            }
            for index, teacher in enumerate(course.teachers)
        ]

    @staticmethod
    def apply(db: Session, course: Course, mode: int, mapping: list[dict] = None, preview: bool = False) -> list:
        # is_composed est désormais purement dérivé de la présence d'enfants (Course._compute_is_composed) :
        # n'importe quel cours peut être décomposé, y compris un cours simple pas encore composé — la
        # décomposition elle-même est ce qui va lui créer des enfants et donc le rendre is_composed=True.
        if course.status == "PLACED":
            raise CompositionError("Un cours déjà placé sur la grille ne peut pas être décomposé, veuillez le dépositionner d'abord.")

        mapping = mapping or []
        if not mapping:
            raise CompositionError("Un mapping (répartition spatiale) est obligatoire pour composer le cours.")

        seen_teachers = set()
        for row in mapping:
            has_teacher = bool(row.get('teacher_ids'))
            has_target = bool(row.get('group_ids') or row.get('class_part_ids') or row.get('division_ids'))

            if not has_teacher or not has_target:
                raise CompositionError("Chaque ligne de répartition doit obligatoirement inclure au moins un professeur ET au moins un ensemble d'élèves (groupe, partie de classe ou classe entière).")

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

        CompositionModes._resolve_dynamic_groups(db, course, mapping, materialize=not preview)

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
            # materialize=True (voir _resolve_dynamic_groups ci-dessus) garantit déjà
            # pending_class_parts/pending_group vides sur ce chemin — mais _build_base_vals les
            # pose malgré tout systématiquement (même absents), et Course.create() (appelé
            # directement ici, PAS via l'endpoint générique/clean_payload qui filtre les clés
            # inconnues côté HTTP) rejette toute clé qui n'est pas une vraie colonne/relation.
            children = []
            for v in vals_list:
                v.pop('pending_class_parts', None)
                v.pop('pending_group', None)
                v.pop('pending_summary', None)
                children.append(Course.create(db, v))
            from backend.app.models.group import cleanup_orphaned_resources
            cleanup_orphaned_resources(db, list(former_class_part_ids), list(former_group_ids))
            return children

    @staticmethod
    def materialize_pending_resources(db: Session, course: Course, children_vals: list[dict]) -> list[dict]:
        """
        Résout pour de vrai (find_or_create_partition/find_or_create_group) tous les jetons
        `pending_class_parts`/`pending_group` portés par les lignes de `children_vals` — appelée
        uniquement par Course.rpc_save_composition, juste avant de créer chaque enfant. Un même
        jeton partagé par plusieurs lignes enfants (ex: mode 2, deux semaines pour la même ligne de
        mapping) n'est résolu qu'une seule fois. Ne mute jamais course.class_parts/course.groups
        directement : Course._cascade_resources_to_parent s'en charge automatiquement dès que
        Course.create() est appelé juste après pour chaque enfant (voir architecture.md).
        """
        from backend.app.models.group import find_or_create_partition, find_or_create_group

        resolved_partitions: dict[str, "Partition"] = {}
        for vals in children_vals:
            for pending in vals.get('pending_class_parts') or []:
                token = pending['token']
                if token not in resolved_partitions:
                    resolved_partitions[token] = find_or_create_partition(
                        db, pending['division_id'],
                        CompositionModes._compute_partition_label(db, course, set(pending['partition_subject_ids'])),
                        subject_ids=pending['partition_subject_ids'],
                    )
                partition = resolved_partitions[token]
                resolved_class_part = next(cp for cp in partition.class_parts if cp.subject_id == pending['subject_id'])
                vals['class_part_ids'] = list(set((vals.get('class_part_ids') or []) + [resolved_class_part.id]))
            vals.pop('pending_class_parts', None)

        resolved_groups: dict[str, "Group"] = {}
        for vals in children_vals:
            pending_group = vals.get('pending_group')
            # pop() inconditionnel (pas seulement dans la branche de résolution ci-dessous) : voir
            # le même piège corrigé pour Course.create() dans apply() — _build_base_vals pose
            # toujours la clé 'pending_group' (à None si absente), un simple `if not pending_group`
            # sans pop laisserait cette clé (valant None) sur `vals`, toujours rejetée par
            # Course.create() même si sa VALEUR ne porte plus aucune information utile.
            vals.pop('pending_group', None)
            if not pending_group:
                continue
            token = pending_group['token']
            if token not in resolved_groups:
                # class_part_ids de la ligne à cet instant = ressources déjà réelles au moment de
                # l'aperçu (capturées dans le jeton) + celles tout juste résolues juste au-dessus.
                all_class_part_ids = set(pending_group.get('class_part_ids') or []) | set(vals.get('class_part_ids') or [])
                resolved_groups[token] = find_or_create_group(db, list(all_class_part_ids), vals.get('subject_id'))
            vals['group_ids'] = list(set((vals.get('group_ids') or []) + [resolved_groups[token].id]))
            vals['class_part_ids'] = []

        for vals in children_vals:
            vals.pop('pending_summary', None)

        return children_vals

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
            'material_ids': [],
            'non_teaching_staff_ids': [],
            # Ressources spatiales fournies par le mapping (ou liste vide si omis)
            'teacher_ids': map_row.get('teacher_ids', []),
            # Le mapping ne porte que des ids de Classroom bruts (colonne "Salles" du wizard,
            # sélection simple sans notion de quantité côté utilisateur) — jamais des ids de
            # CourseClassroomRequirement. _apply_owned_collection_commands (base.py) interprète un
            # entier nu comme "conserver la ligne CourseClassroomRequirement existante ayant CET
            # id" : passer des ids de Classroom tels quels serait au mieux ignoré, au pire un
            # rattachement erroné. Conversion en dicts SANS 'id' pour forcer la création d'une
            # ligne par salle (quantity=1, seule valeur autorisée pour une salle-feuille précise,
            # voir CourseClassroomRequirement._validate_leaf_quantity).
            'classroom_requirement_ids': [{"classroom_id": cid, "quantity": 1} for cid in map_row.get('classroom_ids', [])],
            'division_ids': map_row.get('division_ids', []),
            'class_part_ids': map_row.get('class_part_ids', []),
            'group_ids': map_row.get('group_ids', []),
            'period_ids': map_row.get('period_ids', [r.id for r in course.periods]),
            # Jetons de ressources pas encore créées (aperçu du wizard uniquement, voir
            # _resolve_dynamic_part_class/_resolve_dynamic_groups) — consommés par
            # materialize_pending_resources à la sauvegarde ; ignorés sans risque par clean_payload
            # si ce dict finit directement en Course.create() (chemin legacy compose_by_mode, où
            # ils sont toujours vides puisque materialize=True n'en produit jamais).
            'pending_class_parts': map_row.get('pending_class_parts', []),
            'pending_group': map_row.get('pending_group'),
            'pending_summary': CompositionModes._pending_summary(map_row),
        }

    @staticmethod
    def _pending_summary(map_row: dict) -> str:
        """Résumé lisible des ressources pas encore créées pour cette ligne — affiché tel quel
        dans la colonne en lecture seule `pending_summary` de l'étape aperçu du wizard."""
        labels = [p['label'] for p in map_row.get('pending_class_parts', [])]
        if map_row.get('pending_group'):
            labels.append(map_row['pending_group']['label'])
        return " ; ".join(labels)

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


class CompositionModeOption(TransientModel):
    """
    Ressource virtuelle exposant les modes de composition (1-9) applicables à un mapping donné —
    remplace l'ancien RPC débouncé Course.rpc_get_available_modes : le champ "mode" du wizard de
    composition (course.py, __actions__) le consomme comme un select FK classique, filtré en
    direct par dynamicOptionsFilter (voir GenericForm.vue) sur le mapping en cours de saisie et le
    cours en décomposition. Auto-enregistrée auprès de l'API générique par __tablename__ (voir
    generic.py::MODEL_MAP, aucune registration manuelle nécessaire).
    """
    __tablename__ = "composition_mode_options"
    # "name" (jamais "label") : convention de libellé partagée par tout le reste de l'appli — voir
    # SearchableSelect.vue/SearchableMultiSelect.vue::refreshDynamicOptions et App.vue::
    # fkOptionsCache, qui résolvent TOUS le libellé d'une option via `display_name || name || code
    # || id`, jamais un champ "label" (propre au dict `info={}` des colonnes réelles, une notion
    # différente). Une ressource virtuelle qui n'expose pas l'un de ces noms attendus retombe
    # silencieusement sur l'id nu, sans erreur visible — bug constaté ici (le select n'affichait que
    # le numéro du mode) avant ce renommage.
    _fields = ["id", "name"]
    _field_info = {
        "name": {"label": "Mode de répartition temporelle", "readOnly": True},
    }

    # Absents de _fields (donc jamais exposés en sortie, voir sqla_to_dict) : présents uniquement
    # pour que is_filterable() (generic.py) accepte ces deux query params sur l'endpoint liste.
    course_id = None
    mapping = None

    MODE_LABELS = {
        1: "1 séance par professeur",
        2: "Alternance par quinzaine",
        3: "Barrette (Rotation mi-cours)",
        4: "Barrette + Alternance quinzaine",
        5: "Rotation quinzaine croisée",
        6: "Alternance tri-hebdomadaire",
        7: "Périodes fixes (1 par période)",
        8: "Barrette sur périodes multiples",
        9: "Alternance profs / périodes",
    }

    def __init__(self, id, name):
        self.id = id
        self.name = name

    @classmethod
    def read(cls, db: Session, domain: dict = None, limit: int = None, offset: int = None):
        domain = domain or {}
        course_id = domain.get("course_id")
        if not course_id:
            return []
        course = db.get(Course, int(course_id))
        if not course:
            return []
        mapping_raw = domain.get("mapping")
        mapping = json.loads(mapping_raw) if mapping_raw else []
        mode_ids = CompositionModes.get_available_modes(db, course, mapping)
        return [
            cls(id=mode_id, name=f"{mode_id} - {cls.MODE_LABELS.get(mode_id, f'Mode {mode_id}')}")
            for mode_id in mode_ids
        ]