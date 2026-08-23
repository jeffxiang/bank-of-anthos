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
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.interfaces.DecodedJWT;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.util.Base64;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class JWTVerifierGeneratorTest {

    @TempDir
    private Path temporaryDirectory;

    @Test
    @DisplayName("Given a matching RSA key, verify a token and read its claim")
    void generateJWTVerifierVerifiesTokenWhenKeyMatches() throws Exception {
        // Given
        KeyPair keyPair = keyPair();
        Path publicKey = writePublicKey(keyPair);
        String token = JWT.create().withClaim("acct", "synthetic-account")
            .sign(Algorithm.RSA256((RSAPublicKey) keyPair.getPublic(),
                (RSAPrivateKey) keyPair.getPrivate()));
        JWTVerifier verifier = new JWTVerifierGenerator().generateJWTVerifier(
            publicKey.toString());

        // When
        DecodedJWT decoded = verifier.verify(token);

        // Then
        assertEquals("synthetic-account", decoded.getClaim("acct").asString());
    }

    @Test
    @DisplayName("Given a different RSA key, reject the signed token")
    void generateJWTVerifierRejectsTokenWhenKeyDoesNotMatch() throws Exception {
        // Given
        KeyPair keyPair = keyPair();
        KeyPair otherKeyPair = keyPair();
        Path publicKey = writePublicKey(keyPair);
        String token = JWT.create().withClaim("acct", "synthetic-account")
            .sign(Algorithm.RSA256((RSAPublicKey) otherKeyPair.getPublic(),
                (RSAPrivateKey) otherKeyPair.getPrivate()));
        JWTVerifier verifier = new JWTVerifierGenerator().generateJWTVerifier(
            publicKey.toString());

        // When / Then
        assertThrows(JWTVerificationException.class, () -> verifier.verify(token));
    }

    @Test
    @DisplayName("Given a nonexistent key path, throw GenerateKeyException")
    void generateJWTVerifierFailsWhenKeyPathDoesNotExist() {
        // Given
        Path missingPath = temporaryDirectory.resolve("missing.pem");

        // When / Then
        assertThrows(JWTVerifierGenerator.GenerateKeyException.class,
            () -> new JWTVerifierGenerator().generateJWTVerifier(
                missingPath.toString()));
    }

    @Test
    @DisplayName("Given malformed key content, throw GenerateKeyException")
    void generateJWTVerifierFailsWhenKeyContentIsMalformed() throws Exception {
        // Given
        Path malformedKey = temporaryDirectory.resolve("malformed.pem");
        Files.writeString(malformedKey,
            "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n");

        // When / Then
        assertThrows(JWTVerifierGenerator.GenerateKeyException.class,
            () -> new JWTVerifierGenerator().generateJWTVerifier(
                malformedKey.toString()));
    }

    private KeyPair keyPair() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    private Path writePublicKey(KeyPair keyPair) throws Exception {
        String encoded = Base64.getMimeEncoder(64, new byte[] {'\n'})
            .encodeToString(keyPair.getPublic().getEncoded());
        Path path = temporaryDirectory.resolve("public.pem");
        Files.writeString(path, "-----BEGIN PUBLIC KEY-----\n" + encoded
            + "\n-----END PUBLIC KEY-----\n");
        return path;
    }
}
