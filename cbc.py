from Cryptodome.Cipher import AES

BLOCK_SIZE = 16


class AESCipher(object):
    """This class is compatible with crypto.createCipheriv('aes-256-cbc')"""

    def __init__(self, key=None):
        self.key = key

    def pad(self, data):
        length = BLOCK_SIZE - (len(data) % BLOCK_SIZE)
        return data + (chr(length) * length).encode()

    def unpad(self, data):
        return data[: -(data[-1] if type(data[-1]) == int else ord(data[-1]))]

    def encrypt(self, plain_text):
        cipher = AES.new(self.key, AES.MODE_CBC)
        b = plain_text.encode("UTF-8")
        return cipher.iv, cipher.encrypt(self.pad(b))

    def decrypt(self, iv, enc_text):
        cipher = AES.new(self.key, AES.MODE_CBC, iv=iv)
        return self.unpad(cipher.decrypt(enc_text).decode("UTF-8"))
