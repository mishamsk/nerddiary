from nerddiary.core.data.crypto import EncryptionProdiver

import pytest
from cryptography.fernet import InvalidToken


class TestEncryptionProdiver:
    def test_provider(self):

        password = "test password"
        test_data = b"test data"

        encr = EncryptionProdiver(password)
        key = encr.key

        encrypted = encr.encrypt(test_data)
        decrypted = encr.decrypt(encrypted)

        assert encrypted != test_data
        assert decrypted == test_data

        # Test decrypting with the same password, but new provider (new salt & token)
        encr2 = EncryptionProdiver(password)
        with pytest.raises(ValueError) as err:
            encr2.decrypt(encrypted)
        assert err.type == ValueError and err.value.args == ("Salt or iterations mismatch",)

        # Test initialising new provider with init_token allows to decrypt old message
        encr = EncryptionProdiver(password, init_token=encrypted)
        decrypted = encr.decrypt(encrypted)

        assert decrypted == test_data

        encr = EncryptionProdiver(key, init_token=encrypted)
        decrypted = encr.decrypt(encrypted)

        assert decrypted == test_data

        # Test initialising new provider with init_token & control_message
        encr = EncryptionProdiver(password, init_token=encrypted, control_message=test_data)
        decrypted = encr.decrypt(encrypted)

        assert decrypted == test_data

        encr = EncryptionProdiver(key, init_token=encrypted, control_message=test_data)
        decrypted = encr.decrypt(encrypted)

        assert decrypted == test_data

        # Test initialising new provider with init_token & incorrect control_message
        with pytest.raises(ValueError) as err:
            encr = EncryptionProdiver(password, init_token=encrypted, control_message=b"wrong data")
        assert err.type == ValueError and err.value.args == ("Init message didn't match control bytes",)

        # Test initialising new provider with init_token & incorrect password
        with pytest.raises(InvalidToken) as err:
            encr = EncryptionProdiver("wrong password", init_token=encrypted, control_message=test_data)
        assert err.type == InvalidToken

        # Test initialising new provider with key but no init_token
        with pytest.raises(ValueError) as err:
            encr = EncryptionProdiver(key)
        assert err.type == ValueError and err.value.args == ("Key may not be used without an `init_token`",)

        # Test initialising new provider with wrong password_or_key type
        with pytest.raises(ValueError) as err:
            encr = EncryptionProdiver({key})  # type: ignore
        assert err.type == ValueError and err.value.args == (
            "`password_or_key` must be either a `str` password ot `bytes` key",
        )
