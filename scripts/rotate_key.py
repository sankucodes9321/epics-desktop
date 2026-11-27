"""Rotate all Redis templates to an independently retained replacement AES key."""
import argparse
from dataclasses import replace
import hashlib
import os

import numpy as np
from redis.exceptions import RedisError, WatchError

from privacy.config import decode_key, load_key, redis_client
from privacy.encryption import encrypt
from privacy.errors import PipelineError
from privacy.matching import aad, references
from privacy.runtime import startup
from privacy.store import KEY_ID, REVISION, Store, user_key


def rotate(store: Store, old: bytes, new: bytes) -> int:
    if not isinstance(new, bytes) or len(new) != 32:
        raise PipelineError("Replacement key must contain 32 bytes.")
    if new == old:
        raise PipelineError("Choose a different replacement key.")
    staged = {}
    with store.db.pipeline() as pipe:
        try:
            pipe.watch(REVISION, KEY_ID)
            store.revision(pipe)
            active = pipe.get(KEY_ID)
            if active is not None and active != hashlib.sha256(old).digest():
                raise PipelineError("Configured key differs from active key.")
            for uid in store.users():
                key = user_key(uid)
                pipe.watch(key)
                record = store.load(uid)
                if record is None:
                    raise PipelineError("Enrollment changed during rotation.")
                with references([record], old) as plaintext:
                    blob = encrypt(plaintext, new, aad(uid, record.count))
                    with references([replace(record, blob=blob)], new) as check:
                        if not np.array_equal(plaintext, check):
                            raise PipelineError("Rotated template verification failed.")
                staged[key] = blob
            pipe.multi()
            for key, blob in staged.items():
                pipe.hset(key, "templates", blob)
            pipe.set(KEY_ID, hashlib.sha256(new).digest())
            pipe.incr(REVISION)
            pipe.execute()
        except WatchError as error:
            store.retry_conflict(error, pipe)
            raise PipelineError("Concurrent gallery change. Stop writers before retrying rotation.") from None
    return len(staged)


def main():
    startup()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        encoded = os.getenv("ZKAUTH_NEXT_KEY")
        if not encoded:
            raise PipelineError("Supply ZKAUTH_NEXT_KEY from your secret manager.")
        count = rotate(Store(redis_client()), load_key(), decode_key(encoded))
    except PipelineError as error:
        parser.exit(1, f"{error} Retain both keys.\n")
    except (OSError, RedisError) as error:
        parser.exit(1, f"Rotation failed ({type(error).__name__}). Retain both keys.\n")
    print(f"Rotated {count} records. Configure the replacement as the active key and unset ZKAUTH_NEXT_KEY.")


if __name__ == "__main__":
    main()
