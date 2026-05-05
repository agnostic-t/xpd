from crypto.rsa import RSACrypto

crypto = RSACrypto(key_size=4096)

keys = crypto.gen_keys()
crypto.save_keys("keys.json", keys)

crypto.load_keys("keys.json")
print(crypto.get_max_len() * "a")

encrypted = crypto.encrypt("Secret message!")
decrypted = crypto.decrypt(encrypted)

signature = crypto.sign("Important document")
is_valid = crypto.verify("Important document", signature)
