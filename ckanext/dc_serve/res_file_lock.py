import os
import tempfile
import pathlib


class CKANResourceFileLock:
    """File-based file lock for CKAN resources

    The lock must be acquired on the same system, because the lock
    location is volatile (on /tmp) by design.

    This is not a conventional lock. You always have to check
    the `is_locked` property to make sure that you have actually
    acquired a lock.
    """

    def __init__(self, resource_id, locker_id="CKAN_resource_lock"):
        """

        Parameters
        ----------
        resource_id: str
            CKAN resource ID
        locker_id: str
            Custom ID to use for the lock. The default is the
        """
        temploc = pathlib.Path(tempfile.gettempdir()) / locker_id
        temploc.mkdir(parents=True, exist_ok=True)

        self.resource_id = resource_id
        self.lockfile = temploc / f"{resource_id}.lock"
        self.is_locked = False

    def acquire(self):
        """Acquire a file lock

        Returns
        -------
        lock_successful: bool
            Returns True if the lock was acquired
        """
        if not self.is_locked and not self.lockfile.exists():
            self.lockfile.touch()
            self.is_locked = True
        return self.is_locked

    def release(self):
        """ Get rid of the lock by deleting the lockfile.
            When working in a `with` statement, this gets automatically
            called at the end.
        """
        if self.is_locked:
            os.unlink(self.lockfile)
            self.is_locked = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, type, value, traceback):
        self.release()

    def __del__(self):
        self.release()
