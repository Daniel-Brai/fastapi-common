class Hasher:
    """
    argon2id password hasher with per-user application-level salt.

    The value stored in hashed_password is:
        argon2id_hash(plaintext + password_salt)

    This combines two independent layers of protection:
      1. argon2id's own internal random salt  — prevents cross-database rainbow tables
      2. password_salt (per-user, stored in DB) — means knowing user A's plaintext
         cannot verify against user B's hash

    argon2 parameters (defaults are OWASP-recommended minimums):
        time_cost    — number of iterations (default 2)
        memory_cost  — KiB of memory (default 65536 = 64 MiB)
        parallelism  — number of parallel threads (default 2)

    Examples:

        # On user creation / password change:
        user.hashed_password = Hasher.hash(plaintext, user.password_salt)

        # On login / password verification:
        ok = Hasher.verify(plaintext, user.password_salt, user.hashed_password)

        # Configuration (call once at startup if you want non-default parameters):
            Hasher.configure(time_cost=3, memory_cost=65536, parallelism=2)

        # Rehashing (call after verify to transparently upgrade hashes):
            if Hasher.needs_rehash(user.hashed_password):
                user.hashed_password = Hasher.hash(plaintext, user.password_salt)
                db.add(user); db.commit()


    """

    _time_cost: int = 2
    _memory_cost: int = 65536  # 64 MiB
    _parallelism: int = 2

    _hasher = None

    @classmethod
    def configure(
        cls,
        *,
        time_cost: int = 2,
        memory_cost: int = 65536,
        parallelism: int = 2,
    ) -> None:
        """
        Override argon2 parameters.  Call once at application startup
        BEFORE any hash or verify call.

            Hasher.configure(time_cost=3, memory_cost=131072, parallelism=4)
        """
        cls._time_cost = time_cost
        cls._memory_cost = memory_cost
        cls._parallelism = parallelism
        cls._hasher = None

    @classmethod
    def _ph(cls):
        """
        Return (or build) the cached PasswordHasher.
        """
        if cls._hasher is None:
            try:
                from argon2 import PasswordHasher
            except ImportError:
                raise ImportError("argon2-cffi is not installed. " "pip install argon2-cffi")
            cls._hasher = PasswordHasher(
                time_cost=cls._time_cost,
                memory_cost=cls._memory_cost,
                parallelism=cls._parallelism,
            )
        return cls._hasher

    @classmethod
    def hash(cls, plaintext: str, user_salt: str) -> str:
        """
        Hash (plaintext + user_salt) with argon2id.

        Parameters
        ----------
        plaintext   Raw password supplied by the user.
        user_salt   The password_salt value from the user's DB row.

        Returns the encoded argon2 hash string to store in hashed_password.
        """
        return cls._ph().hash(plaintext + user_salt)

    @classmethod
    def verify(cls, plaintext: str, user_salt: str, hashed: str) -> bool:
        """
        Verify plaintext against a stored argon2 hash.

        Parameters
        ----------
        plaintext   Raw password supplied by the user.
        user_salt   The password_salt value from the user's DB row.
        hashed      The stored hashed_password value.

        Returns True on success, False on mismatch.
        Never raises — all argon2 exceptions are caught and return False.
        """
        try:
            from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
        except ImportError:
            raise ImportError("pip install argon2-cffi")

        try:
            return cls._ph().verify(hashed, plaintext + user_salt)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    @classmethod
    def needs_rehash(cls, hashed: str) -> bool:
        """
        Return True if the hash was created with different parameters and
        should be transparently upgraded after a successful login.

            ok = Hasher.verify(plaintext, user.password_salt, user.hashed_password)
            if ok and Hasher.needs_rehash(user.hashed_password):
                user.hashed_password = Hasher.hash(plaintext, user.password_salt)
        """
        return cls._ph().check_needs_rehash(hashed)
