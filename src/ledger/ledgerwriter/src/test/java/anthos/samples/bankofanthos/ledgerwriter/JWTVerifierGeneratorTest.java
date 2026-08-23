/*
 * Copyright 2026, Google LLC.
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

package anthos.samples.bankofanthos.ledgerwriter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.auth0.jwt.JWT;
import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.algorithms.Algorithm;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.util.Base64;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class JWTVerifierGeneratorTest {

    private static final String ACCOUNT_NUM = "1234567890";

    @Test
    @DisplayName("Given an ephemeral RSA public key, verify a signed token")
    void generateJWTVerifierWhenPublicKeyIsValidVerifiesToken()
            throws Exception {
        // Given
        KeyPairGenerator keyPairGenerator =
                KeyPairGenerator.getInstance("RSA");
        keyPairGenerator.initialize(2048);
        KeyPair keyPair = keyPairGenerator.generateKeyPair();
        RSAPublicKey publicKey = (RSAPublicKey) keyPair.getPublic();
        RSAPrivateKey privateKey = (RSAPrivateKey) keyPair.getPrivate();
        Path publicKeyFile = writePublicKey(publicKey);

        try {
            String token = JWT.create().withClaim(
                    LedgerWriterController.JWT_ACCOUNT_KEY, ACCOUNT_NUM).sign(
                            Algorithm.RSA256(publicKey, privateKey));

            // When
            JWTVerifier verifier = new JWTVerifierGenerator().
                    generateJWTVerifier(publicKeyFile.toString());

            // Then
            assertEquals(ACCOUNT_NUM, verifier.verify(token).getClaim(
                    LedgerWriterController.JWT_ACCOUNT_KEY).asString());
        } finally {
            Files.deleteIfExists(publicKeyFile);
        }
    }

    @Test
    @DisplayName("Given a missing public key, fail verifier generation")
    void generateJWTVerifierWhenFileIsMissingThrowsGenerateKeyException() {
        // When, Then
        assertThrows(JWTVerifierGenerator.GenerateKeyException.class,
                () -> new JWTVerifierGenerator().generateJWTVerifier(
                        "/missing/synthetic-public-key.pem"));
    }

    private Path writePublicKey(RSAPublicKey publicKey) throws IOException {
        String encodedKey = Base64.getMimeEncoder(
                64, new byte[] {'\n'}).encodeToString(publicKey.getEncoded());
        String pem = "-----BEGIN PUBLIC KEY-----\n" + encodedKey
                + "\n-----END PUBLIC KEY-----\n";
        Path path = Files.createTempFile("ledgerwriter-public-", ".pem");
        Files.write(path, pem.getBytes(StandardCharsets.UTF_8));
        return path;
    }
}
