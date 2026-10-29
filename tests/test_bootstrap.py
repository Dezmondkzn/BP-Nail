import pytest
from bp_bot.domain import BusinessError
from bp_bot.models import Base, database
from bp_bot.service import Quotes


@pytest.fixture
def empty_service(tmp_path):
    engine, sessions = database(f"sqlite:///{tmp_path}/bootstrap.db")
    Base.metadata.create_all(engine)
    yield Quotes(sessions, None)
    engine.dispose()


def test_initial_roles_and_revocation_survive_restart(empty_service):
    svc = empty_service
    svc.bootstrap(100, "Chief", 200, "Manager")
    assert svc.user(100).role == "chief"
    assert svc.user(200).role == "manager"
    with pytest.raises(BusinessError):
        svc.set_user(200, 300, "chief", "main", "Other")
    svc.set_user(100, 200, "manager", "main", "Disabled", False)
    svc.bootstrap(100, "Chief", 200, "Manager")
    with pytest.raises(BusinessError):
        svc.user(200)
    svc.bootstrap(100, "Chief", 300, "Another manager")
    with pytest.raises(BusinessError):
        svc.user(300)


@pytest.mark.parametrize("chief,manager", [(100, 100), (0, 200), (-1, 200), (100, -1)])
def test_invalid_initial_ids_are_rejected(empty_service, chief, manager):
    with pytest.raises(BusinessError):
        empty_service.bootstrap(chief, "Chief", manager, "Manager")


def test_existing_users_are_not_modified(empty_service):
    from bp_bot.models import User
    with empty_service.sessions.begin() as session:
        session.add(User(telegram_id=100, name="Existing", role="manager", department="main"))
    empty_service.bootstrap(100, "Chief", 200, "Manager")
    assert empty_service.user(100).role == "manager"
    with pytest.raises(BusinessError):
        empty_service.user(200)
