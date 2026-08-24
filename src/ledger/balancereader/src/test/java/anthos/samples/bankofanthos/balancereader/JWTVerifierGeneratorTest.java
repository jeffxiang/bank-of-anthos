/*
 * Copyright 2020, Google LLC.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package anthos.samples.bankofanthos.balancereader;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.auth0.jwt.JWT;
import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.SignatureVerificationException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.util.Base64;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class JWTVerifierGeneratorTest {

    private JWTVerifierGenerator generator;
    private KeyPair keyPair;

    @TempDir
    Path tempDir;

    private static final String JWT_ACCOUNT_KEY = "acct";
    private static final String ACCOUNT_NUM = "1234567890";
    private static final int KEY_SIZE = 2048;

    @BeforeEach
    void setUp() throws Exception {
        generator = new JWTVerifierGenerator();
        // Ephemeral keypair: no key material is ever committed.
        KeyPairGenerator keyPairGenerator = KeyPairGenerator.getInstance("RSA");
        keyPairGenerator.initialize(KEY_SIZE);
        keyPair = keyPairGenerator.generateKeyPair();
    }

    @Test
    @DisplayName("Given a PEM public key, build a verifier that accepts tokens signed with its private key")
    void generateJWTVerifierVerifiesTokensSignedWithMatchingKey() throws Exception {
        // Given
        final Path publicKeyPath = writePublicKey(keyPair.getPublic().getEncoded());
        final String token = JWT.create()
            .withClaim(JWT_ACCOUNT_KEY, ACCOUNT_NUM)
            .sign(Algorithm.RSA256(null, (RSAPrivateKey) keyPair.getPrivate()));

        // When
        final JWTVerifier verifier =
            generator.generateJWTVerifier(publicKeyPath.toString());

        // Then
        assertEquals(ACCOUNT_NUM,
            verifier.verify(token).getClaim(JWT_ACCOUNT_KEY).asString());
    }

    @Test
    @DisplayName("Given a token signed by a different key, reject it")
    void generateJWTVerifierRejectsTokensSignedWithOtherKey() throws Exception {
        // Given
        final Path publicKeyPath = writePublicKey(keyPair.getPublic().getEncoded());
        final KeyPairGenerator otherGenerator =
            KeyPairGenerator.getInstance("RSA");
        otherGenerator.initialize(KEY_SIZE);
        final RSAPrivateKey otherPrivateKey =
            (RSAPrivateKey) otherGenerator.generateKeyPair().getPrivate();
        final String token = JWT.create()
            .withClaim(JWT_ACCOUNT_KEY, ACCOUNT_NUM)
            .sign(Algorithm.RSA256(null, otherPrivateKey));
        final JWTVerifier verifier =
            generator.generateJWTVerifier(publicKeyPath.toString());

        // When / Then
        assertThrows(SignatureVerificationException.class,
            () -> verifier.verify(token));
    }

    @Test
    @DisplayName("Given a missing public key file, fail to build the verifier")
    void generateJWTVerifierFailsWhenKeyFileMissing() {
        // Given
        final Path missing = tempDir.resolve("absent.pub");

        // When / Then
        assertThrows(JWTVerifierGenerator.GenerateKeyException.class,
            () -> generator.generateJWTVerifier(missing.toString()));
    }

    @Test
    @DisplayName("Given a public key file that is not an RSA key, fail to build the verifier")
    void generateJWTVerifierFailsWhenKeyIsNotRsa() throws Exception {
        // Given
        final Path publicKeyPath = writePublicKey("not a key".getBytes());

        // When / Then
        assertThrows(JWTVerifierGenerator.GenerateKeyException.class,
            () -> generator.generateJWTVerifier(publicKeyPath.toString()));
    }

    private Path writePublicKey(byte[] keyBytes) throws IOException {
        final Path publicKeyPath = tempDir.resolve("jwtRS256.key.pub");
        final String pem = "-----BEGIN PUBLIC KEY-----\n"
            + Base64.getMimeEncoder().encodeToString(keyBytes)
            + "\n-----END PUBLIC KEY-----\n";
        Files.write(publicKeyPath, pem.getBytes());
        return publicKeyPath;
    }
}
