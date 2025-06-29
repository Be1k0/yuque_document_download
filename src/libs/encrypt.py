import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

from .log import Log
from .tools import gen_timestamp

# 语雀的RSA公钥
RSA_2048_PUB_PEM = """
-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCfwyOyncSrUTmkaUPsXT6UUdXx
TQ6a0wgPShvebfwq8XeNj575bUlXxVa/ExIn4nOUwx6iR7vJ2fvz5Ls750D051S7
q70sevcmc8SsBNoaMQtyF/gETPBSsyWv3ccBJFrzZ5hxFdlVUfg6tXARtEI8rbIH
su6TBkVjk+n1Pw/ihQIDAQAB
-----END PUBLIC KEY-----
"""


def encrypt_password(target_str: str) -> str:
    """
    使用RSA公钥加密密码
    
    Args:
        target_str: 要加密的密码字符串
        
    Returns:
        base64编码的加密结果
    """
    try:
        # 加载公钥
        public_key = serialization.load_pem_public_key(RSA_2048_PUB_PEM.encode())

        # 构造要加密的内容：时间戳:密码
        timestamp = str(gen_timestamp())
        password_with_timestamp = f"{timestamp}:{target_str}"

        # 使用PKCS1v15填充进行加密
        encrypted_data = public_key.encrypt(
            password_with_timestamp.encode('utf-8'),
            padding.PKCS1v15()
        )

        # 返回base64编码的结果
        return base64.b64encode(encrypted_data).decode('utf-8')

    except Exception as e:
        Log.error(f"密码加密失败: {e}")
        return target_str


def generate_rsa_keypair():
    """
    生成RSA密钥对（用于测试）
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    public_key = private_key.public_key()

    # 序列化私钥
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # 序列化公钥
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return private_pem.decode(), public_pem.decode()


if __name__ == "__main__":
    # 模块测试功能（非CLI接口）
    test_password = "hello"
    encrypted = encrypt_password(test_password)
    Log.info(f"原始密码: {test_password}")
    Log.info(f"加密结果: {encrypted}")
