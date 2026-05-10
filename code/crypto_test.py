from crypto.api import ClientStorage, EncryptedChannel, LongTermKey

if __name__ == "__main__":
    storage = ClientStorage(key_dir="./runtime/keys/test", password="qw9010Kiwipa44")

    print(storage.gen_uid())
