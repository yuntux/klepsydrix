import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.app.main import app
from backend.app.core.database import get_db
from backend.app.models.base import Base
from backend.app.models.school import School
from backend.app.models.material import Material

# Utilisation d'une base SQLite fichier pour éviter le gotcha des connexions multiples en mémoire
TEST_SQLALCHEMY_DATABASE_URL = "sqlite:///./test_generic.db"
test_engine = create_engine(
    TEST_SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(scope="function", autouse=True)
def setup_dependency_overrides():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
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
    school = School(uai="1234567A", name="Lycée Test", standard_timeslot_duration=30)
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
    
    # 5. Mettre à jour le material via PUT generic
    update_payload = {
        "name": "Valise iPad Pro V2",
        "quantity": 12
    }
    response = client.put(f"/api/generic/materials/{material_id}", json=update_payload)
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
