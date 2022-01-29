from nerddiary.core.data.crypto import EncryptionProdiver

import pytest
from cryptography.fernet import InvalidToken


class TestEncryptionProdiver:
    def test_provider(self):

        password = "test password"
        test_data = b"test data"

        encr = EncryptionProdiver(password)

        encrypted = encr.encrypt(test_data)
        decrypted = encr.decrypt(encrypted)

        assert encrypted != test_data
        assert decrypted == test_data

        # Test decrypting with the same password, but new provider (new salt & token)
        encr2 = EncryptionProdiver(password)
        with pytest.raises(ValueError) as err:
            encr2.decrypt(encrypted)
        assert err.type == ValueError

        # Test initialising new provider with init_token allows to decrypt old message
        encr = EncryptionProdiver(password, init_token=encrypted)
        decrypted = encr.decrypt(encrypted)

        assert decrypted == test_data

        # Test initialising new provider with init_token & control_message
        encr = EncryptionProdiver(password, init_token=encrypted, control_message=test_data)
        decrypted = encr.decrypt(encrypted)

        assert decrypted == test_data

        # Test initialising new provider with init_token & incorrect control_message
        with pytest.raises(ValueError) as err:
            encr = EncryptionProdiver(password, init_token=encrypted, control_message=b"wrong data")
        assert err.type == ValueError

        # Test initialising new provider with init_token & incorrect password
        with pytest.raises(InvalidToken) as err:
            encr = EncryptionProdiver("wrong password", init_token=encrypted, control_message=test_data)
        assert err.type == InvalidToken
