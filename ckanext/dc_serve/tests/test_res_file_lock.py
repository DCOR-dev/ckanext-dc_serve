import uuid
from ckanext.dc_serve import res_file_lock


def test_lock_context():
    res_id = str(uuid.uuid4())
    with res_file_lock.CKANResourceFileLock(
            resource_id=res_id,
            locker_id="collect_apples") as fla:
        assert fla.is_locked
        with res_file_lock.CKANResourceFileLock(
                resource_id=res_id,
                locker_id="stroke_cat") as flc:
            assert fla.is_locked
            assert flc.is_locked
            with res_file_lock.CKANResourceFileLock(
                    resource_id=res_id,
                    locker_id="collect_apples") as fla2:
                assert fla.is_locked
                assert flc.is_locked
                assert not fla2.is_locked

    with res_file_lock.CKANResourceFileLock(
            resource_id=res_id,
            locker_id="collect_apples") as fla3:
        assert fla3.is_locked


def test_lock_delete():
    res_id = str(uuid.uuid4())
    fla = res_file_lock.CKANResourceFileLock(
        resource_id=res_id,
        locker_id="collect_apples")
    assert not fla.is_locked
    fla.acquire()
    assert fla.is_locked

    fla2 = res_file_lock.CKANResourceFileLock(
        resource_id=res_id,
        locker_id="collect_apples")
    assert not fla2.acquire()
    assert not fla2.is_locked
    assert fla.is_locked

    del fla

    assert fla2.acquire()
    assert fla2.is_locked
