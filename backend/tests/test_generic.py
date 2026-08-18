import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker, Session
from backend.app.main import app
from backend.app.core.database import get_db, current_db_user
from backend.app.models.base import Base
from backend.app.models.school import School
from backend.app.models.material import Material
from backend.tests.db_test_utils import make_test_engine, make_admin_user_override

# Voir db_test_utils.py : SQLite en mémoire (StaticPool) par défaut, PostgreSQL local si
# KLEPSYDRIX_TEST_DB_BACKEND=postgres.
test_engine = make_test_engine()
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@pytest.fixture(scope="function", autouse=True)
def setup_dependency_overrides():
    app.dependency_overrides[get_db] = override_get_db
    # Pose un vrai admin plutôt que de neutraliser la dépendance : ces tests passent donc PAR le
    # moteur de droits au lieu de le court-circuiter (voir db_test_utils.make_admin_user_override).
    app.dependency_overrides[current_db_user] = make_admin_user_override(get_db)
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(current_db_user, None)
client = TestClient(app)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)

def test_generic_crud_flow(db_session: Session):
    # 1. Créer un établissement (School) requis pour le partitionnement
    school = School(uai="1234567A", name="Lycée Test")
    school._via_crud_mixin_create = True
    db_session.add(school)
    db_session.commit()
    db_session.refresh(school)
    
    # 2. Tester le list vide de 'materials'
    response = client.get("/api/generic/materials")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
    
    # 3. Créer un 'Material' via POST generic
    new_material_payload = {
        "code": "KIT_IPAD_01",
        "name": "Valise iPad Pro",
        "quantity": 10
    }
    response = client.post("/api/generic/materials", json=new_material_payload)
    assert response.status_code == 200
    created_item = response.json()
    assert created_item["id"] is not None
    assert created_item["code"] == "KIT_IPAD_01"
    assert created_item["name"] == "Valise iPad Pro"
    assert created_item["quantity"] == 10
    
    material_id = created_item["id"]
    
    # 4. Lire le material créé
    response = client.get(f"/api/generic/materials/{material_id}")
    assert response.status_code == 200
    item = response.json()
    assert item["id"] == material_id
    assert item["name"] == "Valise iPad Pro"
    
    # 5. Mettre à jour le material via PATCH generic
    update_payload = {
        "name": "Valise iPad Pro V2",
        "quantity": 12
    }
    response = client.patch(f"/api/generic/materials/{material_id}", json=update_payload)
    assert response.status_code == 200
    updated_item = response.json()
    assert updated_item["name"] == "Valise iPad Pro V2"
    assert updated_item["quantity"] == 12
    
    # 6. Lister de nouveau pour vérifier la pagination et le filtrage
    response = client.get("/api/generic/materials")
    assert response.status_code == 200
    list_data = response.json()
    assert list_data["total"] == 1
    assert list_data["items"][0]["name"] == "Valise iPad Pro V2"
    
    # 7. Supprimer le material via DELETE generic
    response = client.delete(f"/api/generic/materials/{material_id}")
    assert response.status_code == 200
    delete_data = response.json()
    assert delete_data["status"] == "success"
    
    # 8. Vérifier la disparition
    response = client.get(f"/api/generic/materials/{material_id}")
    assert response.status_code == 404


def test_generic_crud_dynamic_filtering(db_session: Session):
    # 1. Créer deux matériels avec des caractéristiques différentes
    m1 = Material(code="KIT_01", name="Kit A", quantity=5)
    m2 = Material(code="KIT_02", name="Kit B", quantity=10)
    m1._via_crud_mixin_create = True
    m2._via_crud_mixin_create = True
    db_session.add_all([m1, m2])
    db_session.commit()

    # 2. Tester le filtrage dynamique sur 'quantity=10'
    response = client.get("/api/generic/materials?quantity=10")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["code"] == "KIT_02"

    # 3. Tester le filtrage dynamique sur 'code=KIT_01'
    response = client.get("/api/generic/materials?code=KIT_01")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Kit A"


def test_generic_dynamic_method_execution(db_session: Session):
    # 1. Créer un établissement de test
    school = School(uai="8888888X", name="Ecole Test Dynamique")
    school._via_crud_mixin_create = True
    db_session.add(school)
    db_session.commit()
    db_session.refresh(school)

    # 2. Méthode de classe NON décorée @requires_access : refusée (403), c'est le refus par défaut
    # du garde-fou RPC (voir generic.py::_check_rpc_access, architecture.md §18.E). Cet appel
    # renvoyait 200 tant que la suite tournait en mode système, moteur de droits désactivé — la
    # substitution de current_db_user par un vrai admin (db_test_utils.make_admin_user_override) a
    # rendu visible le comportement réel : même un admin ne peut pas appeler une méthode non
    # décorée. Le succès du même appel en mode système reste couvert par test_access_control.py.
    class_call_payload = {
        "args": [],
        "kwargs": {"multiplier": 5}
    }
    response = client.post("/api/generic/schools/call/test_class_method", json=class_call_payload)
    assert response.status_code == 403

    # 3. Tester l'appel de la méthode d'instance test_instance_method
    instance_call_payload = {
        "args": [],
        "kwargs": {"prefix": "Bienvenue à"}
    }
    response = client.post(f"/api/generic/schools/{school.id}/call/test_instance_method", json=instance_call_payload)
    assert response.status_code == 200
    assert response.json() == "Bienvenue à Ecole Test Dynamique"


def test_teacher_constraints_crud(db_session: Session):
    # 1. Créer un établissement requis pour le prof
    school = School(uai="9999999Z", name="Lycée de la Forêt")
    school._via_crud_mixin_create = True
    db_session.add(school)
    db_session.commit()
    db_session.refresh(school)
    
    # 2. Créer un prof avec des contraintes via POST generic
    teacher_payload = {
        "code": "MARTINEZ.P",
        "first_name": "Pedro",
        "last_name": "Martinez",
        "name": "M. Martinez",
        "school_id": school.id,
        # Contraintes:
        "max_hours_per_day": 8.0,
        "max_hours_per_am": 4.0,
        "max_presence_days_per_week": 4,
        "late_start_time": "09:00",
        "only_one_half_day_per_day": True,
        "max_gap_hours_per_week": 1
    }
    response = client.post("/api/generic/teachers", json=teacher_payload)
    assert response.status_code == 200
    data = response.json()
    assert data.get("id") is not None
    assert data["max_hours_per_day"] == 8.0
    assert data["max_hours_per_am"] == 4.0
    assert data["max_presence_days_per_week"] == 4
    assert data["late_start_time"] == "09:00"
    assert data["only_one_half_day_per_day"] is True
    assert data["max_gap_hours_per_week"] == 1
    
    teacher_id = data["id"]
    
    # 3. Mettre à jour les contraintes via PATCH generic
    update_payload = {
        "max_hours_per_day": 7.0,
        "late_start_time": "10:00",
        "only_one_half_day_per_day": False
    }
    response = client.patch(f"/api/generic/teachers/{teacher_id}", json=update_payload)
    assert response.status_code == 200
    updated_data = response.json()
    assert updated_data["max_hours_per_day"] == 7.0
    assert updated_data["late_start_time"] == "10:00"
    assert updated_data["only_one_half_day_per_day"] is False
    
    # 4. Charger via GET generic pour s'assurer que c'est bien persistant
    response = client.get(f"/api/generic/teachers/{teacher_id}")
    assert response.status_code == 200
    fetched_data = response.json()
    assert fetched_data["max_hours_per_day"] == 7.0
    assert fetched_data["late_start_time"] == "10:00"
    assert fetched_data["only_one_half_day_per_day"] is False


def test_generic_display_name(db_session: Session):
    # 1. Créer une école de test
    school = School(uai="7777777Y", name="Ecole Test Display")
    school._via_crud_mixin_create = True
    db_session.add(school)
    db_session.commit()
    db_session.refresh(school)

    # L'école a un attribut 'name'. Donc display_name doit renvoyer "Ecole Test Display"
    response = client.get(f"/api/generic/schools/{school.id}")
    assert response.status_code == 200
    assert response.json()["display_name"] == "Ecole Test Display"

    # 2. Créer une matière (Subject), qui a les attributs 'short_name' et 'name'
    from backend.app.models.discipline import Discipline
    discipline = Discipline(code="DISC_TEST", name="Discipline Test")
    discipline._via_crud_mixin_create = True
    db_session.add(discipline)
    db_session.commit()
    db_session.refresh(discipline)

    from backend.app.models.subject import Subject
    subject = Subject(
        code="SUBJ_TEST",
        code_nomenclature="N_TEST",
        short_name="SubjTest",
        name="Subject Test Long Label",
        discipline_id=discipline.id
    )
    subject._via_crud_mixin_create = True
    db_session.add(subject)
    db_session.commit()
    db_session.refresh(subject)

    # Subject a display_name qui renvoie name
    response = client.get(f"/api/generic/subjects/{subject.id}")
    assert response.status_code == 200
    assert response.json()["display_name"] == "Subject Test Long Label"


