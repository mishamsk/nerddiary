from nerddiary.core.data.crypto import EncryptionProdiver


class TestEncryptionProdiver:
    def test_provider(self):

        password = "test password"
        test_data = b"test data"

        encr = EncryptionProdiver(password)

        encrypted = encr.encrypt(test_data)
        decrypted = encr.decrypt(encrypted)

        assert encrypted != test_data
        assert decrypted == test_data
