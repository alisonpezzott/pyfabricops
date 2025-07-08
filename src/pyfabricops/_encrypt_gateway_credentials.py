# Adapted from https://github.com/microsoft/PowerBI-Developer-Samples/tree/master/Python/Encrypt%20credentials
# Available on Fabric API Rest Connections method: https://learn.microsoft.com/pt-br/rest/api/fabric/core/connections/create-connection?tabs=HTTP
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import base64
import json
import logging
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, hmac, padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.padding import MGF1, OAEP
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ._gateways import get_gateway_public_key

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class _AuthenticatedEncryption:

    Aes256CbcPkcs7 = 0
    HMACSHA256 = 0

    algorithm_choices = [Aes256CbcPkcs7, HMACSHA256]

    def _encrypt(self, key_enc, key_mac, message):
        """Encrypts the message with AES, CBC padding and PKCS7

        Args:
            key_enc (bytes): Encryption Key
            key_mac (bytes): MAC Key
            message (bytes): message to get encrypted

        Returns:
            String: Encrypted credentials
        """

        if len(key_enc) < 32:
            raise ValueError(
                'Encryption Key must be at least 256 bits (32 bytes)'
            )

        if len(key_mac) < 32:
            raise ValueError('Mac Key must be at least 256 bits (32 bytes)')

        if not message:
            raise TypeError('Credentials cannot be null')

        # Initialization vector
        iv = os.urandom(16)

        # PKC7 Padding
        padder = padding.PKCS7(128).padder()

        # Apply padding to the test data
        padded_data = padder.update(message) + padder.finalize()

        # Cipher object with CBC mode
        cipher = Cipher(
            algorithms.AES(key_enc), modes.CBC(iv), backend=default_backend()
        )
        encryptor = cipher.encryptor()

        # Cipher text
        cipher_text = encryptor.update(padded_data) + encryptor.finalize()

        # Prepare the data on which MAC will be executed
        tag_data = bytearray(
            [0] * (len(self.algorithm_choices) + len(iv) + len(cipher_text))
        )
        tag_data_offset = 0

        # Copy algorithm choices array in tag_data
        tag_data[0 : len(self.algorithm_choices)] = self.algorithm_choices[
            0 : len(self.algorithm_choices)
        ]
        tag_data_offset = len(self.algorithm_choices) + tag_data_offset

        # Copy initialization vector in tag_data
        tag_data[tag_data_offset : len(iv) + tag_data_offset] = iv[0 : len(iv)]
        tag_data_offset = len(iv) + tag_data_offset

        # Copy cipher text vector in tag_data
        tag_data[
            tag_data_offset : len(cipher_text) + tag_data_offset
        ] = cipher_text[0 : len(cipher_text)]
        tag_data_offset = len(cipher_text) + tag_data_offset

        # Pass random generated key and hash algorithm to calculate authentication code
        hmac_instance = hmac.HMAC(
            key_mac, hashes.SHA256(), backend=default_backend()
        )

        # Pass the bytes to hash and authenticate
        hmac_instance.update(tag_data)

        # Finalize the current context and return the message digest as bytes
        mac = hmac_instance.finalize()

        # Build the final result as the concatenation of everything except the keys
        output = bytearray(
            [0]
            * (
                len(self.algorithm_choices)
                + len(mac)
                + len(iv)
                + len(cipher_text)
            )
        )
        output_offset = 0

        output[0 : len(self.algorithm_choices)] = self.algorithm_choices[
            0 : len(self.algorithm_choices)
        ]
        output_offset = len(self.algorithm_choices) + output_offset

        output[output_offset : len(mac) + output_offset] = mac[0 : len(mac)]
        output_offset = len(mac) + output_offset

        output[output_offset : len(iv) + output_offset] = iv[0 : len(iv)]
        output_offset = len(iv) + output_offset

        output[output_offset : len(cipher_text) + output_offset] = cipher_text[
            0 : len(cipher_text)
        ]
        output_offset = len(cipher_text) + output_offset

        return output


class _AsymmetricHigherKeyEncryptionHelper:

    KEY_LENGTHS_PREFIX = 2
    HMAC_KEY_SIZE_BYTES = 64
    AES_KEY_SIZE_BYTES = 32

    KEY_LENGTH_32 = 0
    KEY_LENGTH_64 = 1

    def _encrypt(self, plain_text_bytes, modulus_bytes, exponent_bytes):
        """Encrypts the message with RSA, MGF and SHA hashes

        Args:
            plain_text_bytes (bytes): Message to be encrypted
            modulus_bytes (bytes): Modulus bytes returned from GET gateway API
            exponent_bytes (bytes): Exponent bytes returned from GET gateway API

        Returns:
            String: Encrypted credentials
        """

        # Generate ephemeral random keys for encryption (32 bytes), hmac (64 bytes)
        key_enc = os.urandom(self.AES_KEY_SIZE_BYTES)
        key_mac = os.urandom(self.HMAC_KEY_SIZE_BYTES)

        authenticated_encryption = _AuthenticatedEncryption()

        # Encrypt message using ephemeral keys and Authenticated Encryption
        # Symmetric algorithm and encryptor
        cipher_text = authenticated_encryption._encrypt(
            key_enc, key_mac, plain_text_bytes
        )

        # Encrypt ephemeral keys using RSA
        keys = bytearray(
            [0] * (len(key_enc) + len(key_mac) + self.KEY_LENGTHS_PREFIX)
        )

        # Prefixing length of Keys. Symmetric Key length followed by HMAC key length
        keys[0] = self.KEY_LENGTH_32
        keys[1] = self.KEY_LENGTH_64

        # Copy key enc and key mac into keys array
        keys[2 : len(key_enc) + 2] = key_enc[0 : len(key_enc)]
        keys[len(key_enc) + 2 : len(key_enc) + len(key_mac) + 2] = key_mac[
            0 : len(key_mac)
        ]

        # Convert exponent and modulus byte arrays to integers
        exponent = int.from_bytes(exponent_bytes, 'big')
        modulus = int.from_bytes(modulus_bytes, 'big')

        # Generate public key based on modulus and exponent returned by the API
        public_key = rsa.RSAPublicNumbers(exponent, modulus).public_key(
            default_backend()
        )

        # Encrypt the data
        # Pass padding algorithm, mask generation function and hashing algorithm
        encrypted_bytes = public_key.encrypt(
            bytes(keys),
            OAEP(
                mgf=MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        # Return final output
        return (
            base64.b64encode(encrypted_bytes).decode()
            + base64.b64encode(cipher_text).decode()
        )


def _get_encrypt_gateway_credentials(
    gateway_id: str, username: str, password: str
) -> str:
    """
    Encrypts the JSON-serialized credentials list using RSA-OAEP and returns
    a base64 string suitable for Power BI on-prem gateway.
    Args:
        gateway_id (str): The ID or name of the gateway.
        username (str): The username for the credentials.
        password (str): The password for the credentials.
    Returns:
        str: Base64-encoded encrypted credentials.
    Raises:
        ValueError: If the gateway is not found or credentials are invalid.
    """
    # Load database credentials from environment
    gateway_resp = get_gateway_public_key(gateway_id)

    if not gateway_resp:
        raise ValueError(
            'Gateway not found. Please check the gateway ID or name.'
        )

    # Decode exponent and modulus from base64 to integers
    e = base64.b64decode(gateway_resp['exponent'])
    n = base64.b64decode(gateway_resp['modulus'])

    # Serialize credentials to the compact JSON form
    credentials = {
        'credentialData': [
            {'name': 'username', 'value': username},
            {'name': 'password', 'value': password},
        ]
    }
    plaintext = json.dumps(credentials, separators=(',', ':')).encode('utf-8')

    # Encrypt the plaintext using RSA-OAEP
    # Create an instance of the _AsymmetricHigherKeyEncryptionHelper
    helper = _AsymmetricHigherKeyEncryptionHelper()
    encrypted_credentials = helper._encrypt(plaintext, n, e)

    return encrypted_credentials
