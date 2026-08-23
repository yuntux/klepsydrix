from backend.app.models.base import Base
from backend.app.models.user import User, UserIdentityProvider
from backend.app.models.password_reset_token import PasswordResetToken
from backend.app.models.access import ResGroup, IrModelAccess
from backend.app.models.custom_filter import CustomFilter
from backend.app.models.parent import Parent
from backend.app.models.school import School
from backend.app.models.discipline import Discipline
from backend.app.models.family import Family
from backend.app.models.subject import Subject
from backend.app.models.mef import Mef, MefService, MefDivision
from backend.app.models.trmd_budget import TrmdBudget
from backend.app.models.ref_classroom_type import RefClassroomType
from backend.app.models.classroom import Classroom
from backend.app.models.teacher import Teacher, TeacherAra, TeacherAre, TeacherDiscipline, TeacherParticularMission, TeacherPacteMission, TeacherOtherSchool
from backend.app.models.teacher_grade_preference import TeacherGradePreference
from backend.app.models.division import Division
from backend.app.models.material import Material
from backend.app.models.ref_election_method import RefElectionMethod
from backend.app.models.group import Partition, ClassPart, ClassPartLink, Group
from backend.app.models.student import Student, StudentSpecialtyChoice, StudentParentLink, StudentClassPartLink
from backend.app.models.specialty_group_config import SpecialtyGroupConfig
from backend.app.models.period import Period
from backend.app.models.period_type import PeriodType
from backend.app.models.holidays import Holidays
from backend.app.models.week_calendar import WeekCalendar
from backend.app.models.alternation import Alternation
from backend.app.models.modality import Modality
from backend.app.models.ref_weighting_coefficient import RefWeightingCoefficient
from backend.app.models.site import Site, SiteTravelTime
from backend.app.models.timeslot import Timeslot
from backend.app.models.grid_day_settings import GridDaySettings
from backend.app.models.course import Course
from backend.app.models.course_classroom_requirement import CourseClassroomRequirement
from backend.app.models.course_teacher import CourseTeacherWeighting
from backend.app.models.service import Service, ServiceRepartition, Alignment
from backend.app.models.non_teaching_staff import NonTeachingStaff
from backend.app.models.preference import ResourcePreference
from backend.app.models.constraint import ResourceConstraint, CourseToCourseConstraint
from backend.app.models.system_setting import SystemSetting
from backend.app.models.ref_ara import RefAra
from backend.app.models.ref_are import RefAre
from backend.app.models.ref_grade import RefGrade
from backend.app.models.ref_particular_mission import RefParticularMission
from backend.app.models.ref_pacte_mission import RefPacteMission
from backend.app.models.ref_external_school import RefExternalSchool
from backend.app.models.ref_title import RefTitle
from backend.app.models.ref_country import RefCountry
from backend.app.models.ref_exit_reason import RefExitReason
from backend.app.models.ref_regime import RefRegime
from backend.app.models.ref_relative_link import RefRelativeLink
from backend.app.models.ref_legal_guardian import RefLegalGuardian
from backend.app.models.ref_job import RefJob
from backend.app.models.ref_degree import RefDegree
from backend.app.models.ref_administrative_group import RefAdministrativeGroup
from backend.app.models.ref_level import RefLevel
from backend.app.models.ref_affectation_mode import RefAffectationMode
from backend.app.models.ref_inspector import RefInspector
from backend.app.models.ref_service_mode import RefServiceMode
from backend.app.models.ref_function import RefFunction
from backend.app.models.ref_support import RefSupport
from backend.app.models.ref_support_type import RefSupportType
from backend.app.models.ref_city import RefCity
from backend.app.models.ref_academie import RefAcademie

# Table de verrou "mode exclusif" (voir core/exclusive_mode.py) : PAS un modèle ORM (donc jamais
# exposé via /api/generic), mais son import doit tout de même se produire tôt et systématiquement
# pour que le listener before_flush qu'il enregistre soit actif dans tout contexte qui importe ce
# paquet (API, solveur, tests) — exactement pour la même raison que tous les modèles ci-dessus.
import backend.app.core.exclusive_mode  # noqa: E402,F401

# Closure table de l'arbre des groupes de salles (voir classroom_closure.py) : PAS un modèle ORM
# (Table Core brute), même raisonnement que ci-dessus — son import doit se produire tôt pour que
# Base.metadata.create_all() (init_db.py) la crée.
import backend.app.models.classroom_closure  # noqa: E402,F401
