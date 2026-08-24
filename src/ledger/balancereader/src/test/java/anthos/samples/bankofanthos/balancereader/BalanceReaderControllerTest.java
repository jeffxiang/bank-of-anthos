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

import com.google.common.cache.CacheLoader;
import com.google.common.cache.CacheStats;
import io.micrometer.core.instrument.Clock;
import io.micrometer.core.instrument.binder.cache.GuavaCacheMetrics;
import io.micrometer.core.lang.Nullable;
import io.micrometer.stackdriver.StackdriverConfig;
import io.micrometer.stackdriver.StackdriverMeterRegistry;
import java.util.concurrent.ExecutionException;

import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.interfaces.Claim;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.google.common.cache.CacheBuilder;
import com.google.common.cache.LoadingCache;
import com.google.common.util.concurrent.UncheckedExecutionException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.ResourceAccessException;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.MockitoAnnotations.initMocks;

class BalanceReaderControllerTest {

    private BalanceReaderController balanceReaderController;

    @Mock
    private JWTVerifier verifier;
    @Mock
    private LedgerReader ledgerReader;
    @Mock
    private DecodedJWT jwt;
    @Mock
    private Claim claim;
    @Mock
    private Clock clock;
    @Mock
    private LoadingCache<String, Long> cache;
    @Mock
    private CacheStats stats;

    private static final String VERSION = "v0.2.0";
    private static final String LOCAL_ROUTING_NUM = "123456789";
    private static final String OK_CODE = "ok";
    private static final String JWT_ACCOUNT_KEY = "acct";
    private static final long BALANCE = 100l;
    private static final String AUTHED_ACCOUNT_NUM = "1234567890";
    private static final String NON_AUTHED_ACCOUNT_NUM = "9876543210";
    private static final String BEARER_TOKEN = "Bearer abc";
    private static final String TOKEN = "abc";
    private static final String FOREIGN_ROUTING_NUM = "987654321";
    private static final int AMOUNT = 25;

    @BeforeEach
    void setUp() {
        initMocks(this);
        StackdriverMeterRegistry meterRegistry = new StackdriverMeterRegistry(new StackdriverConfig() {
            @Override
            public boolean enabled() {
                return false;
            }

            @Override
            public String projectId() {
                return "test";
            }

            @Override
            @Nullable
            public String get(String key) {
                return null;
            }
        }, clock);

        when(cache.stats()).thenReturn(stats);
        balanceReaderController = new BalanceReaderController(ledgerReader, verifier,
            meterRegistry, cache, LOCAL_ROUTING_NUM, VERSION);

        when(verifier.verify(TOKEN)).thenReturn(jwt);
        when(jwt.getClaim(JWT_ACCOUNT_KEY)).thenReturn(claim);
    }

    @Test
    @DisplayName("Given version number in the environment, " +
            "return a ResponseEntity with the version number")
    void version() {
        // When
        final ResponseEntity actualResult = balanceReaderController.version();

        // Then
        assertNotNull(actualResult);
        assertEquals(VERSION, actualResult.getBody());
        assertEquals(HttpStatus.OK, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the server is serving requests, return HTTP Status 200")
    void readiness() {
        // When
        final String actualResult = balanceReaderController.readiness();

        // Then
        assertNotNull(actualResult);
        assertEquals(OK_CODE, actualResult);
    }

    @Test
    @DisplayName("Given the ledgerReader is alive, return HTTP Status 200")
    void livenessSucceedsWhenLedgerReaderIsAlive() {
        // Given
        when(ledgerReader.isAlive()).thenReturn(true);

        // When
        final ResponseEntity actualResult = balanceReaderController.liveness();

        // Then
        assertNotNull(actualResult);
        assertEquals(OK_CODE, actualResult.getBody());
        assertEquals(HttpStatus.OK, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the ledgerReader is not alive, return HTTP Status 500")
    void livenessFailsWhenLedgerReaderIsNotAlive() {
        // Given
        when(ledgerReader.isAlive()).thenReturn(false);
        
        // When
        final ResponseEntity actualResult = balanceReaderController.liveness();

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the user is authenticated for the account, return HTTP Status 200")
    void getBalanceSucceedsWhenAccountMatchesAuthenticatedUser() throws Exception {
        // Given
        when(verifier.verify(TOKEN)).thenReturn(jwt);
        when(jwt.getClaim(JWT_ACCOUNT_KEY)).thenReturn(claim);
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM)).thenReturn(BALANCE);

        // When
        final ResponseEntity actualResult = balanceReaderController.getBalance(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.OK, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the user is authenticated for the account, return correct balance.")
    void getBalanceIsCorrectWhenAccountMatchesAuthenticatedUser() throws Exception {
        // Given
        when(verifier.verify(TOKEN)).thenReturn(jwt);
        when(jwt.getClaim(JWT_ACCOUNT_KEY)).thenReturn(claim);
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM)).thenReturn(BALANCE);

        // When
        final ResponseEntity actualResult = balanceReaderController.getBalance(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(BALANCE, actualResult.getBody());
    }
    @Test
    @DisplayName("Given the user is authenticated but cannot access the account, return 401")
    void getBalanceFailsWhenAccountDoesNotMatchAuthenticatedUser() {
        // Given
        when(verifier.verify(TOKEN)).thenReturn(jwt);
        when(jwt.getClaim(JWT_ACCOUNT_KEY)).thenReturn(claim);
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);

        // When
        final ResponseEntity actualResult = balanceReaderController.getBalance(BEARER_TOKEN, NON_AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the user is not authenticated, return 401")
    void getBalanceFailsWhenUserNotAuthenticated() {
        // Given
        when(verifier.verify(TOKEN)).thenThrow(JWTVerificationException.class);

        // When
        final ResponseEntity actualResult = balanceReaderController.getBalance(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given an Authorization header without the Bearer prefix, still authorize the user")
    void getBalanceSucceedsWhenTokenHasNoBearerPrefix() throws Exception {
        // Given
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM)).thenReturn(BALANCE);

        // When
        final ResponseEntity actualResult = balanceReaderController.getBalance(TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.OK, actualResult.getStatusCode());
        assertEquals(BALANCE, actualResult.getBody());
    }

    @Test
    @DisplayName("Given no Authorization header, return 401")
    void getBalanceFailsWhenTokenIsNull() {
        // Given
        when(verifier.verify((String) null)).thenThrow(JWTVerificationException.class);

        // When
        final ResponseEntity actualResult = balanceReaderController.getBalance(null, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the token carries no account claim, return 401")
    void getBalanceFailsWhenAccountClaimIsMissing() throws Exception {
        // Given
        when(claim.asString()).thenReturn(null);

        // When
        final ResponseEntity actualResult = balanceReaderController.getBalance(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
        verify(cache, never()).get(anyString());
    }

    @Test
    @DisplayName("Given the cache loader fails unchecked for an authenticated user, return 500")
    void getBalanceFailsWhenCacheThrowsUncheckedError() throws Exception {
        // Given
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM)).thenThrow(
            new UncheckedExecutionException(new DataAccessResourceFailureException("db down")));

        // When
        final ResponseEntity actualResult = balanceReaderController.getBalance(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given a local transaction, debit the sender and credit the receiver in the cache")
    void ledgerCallbackUpdatesCachedBalancesForLocalAccounts() {
        // Given
        final ConcurrentMap<String, Long> cacheContents = new ConcurrentHashMap<>();
        cacheContents.put(AUTHED_ACCOUNT_NUM, BALANCE);
        cacheContents.put(NON_AUTHED_ACCOUNT_NUM, BALANCE);
        when(cache.asMap()).thenReturn(cacheContents);

        // When
        captureLedgerCallback().processTransaction(TestUtil.newTransaction(1L,
            AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM,
            NON_AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM, AMOUNT));

        // Then
        verify(cache).put(AUTHED_ACCOUNT_NUM, BALANCE - AMOUNT);
        verify(cache).put(NON_AUTHED_ACCOUNT_NUM, BALANCE + AMOUNT);
    }

    @Test
    @DisplayName("Given a transaction from another bank, do not debit the sender")
    void ledgerCallbackIgnoresForeignSender() {
        // Given
        final ConcurrentMap<String, Long> cacheContents = new ConcurrentHashMap<>();
        cacheContents.put(AUTHED_ACCOUNT_NUM, BALANCE);
        cacheContents.put(NON_AUTHED_ACCOUNT_NUM, BALANCE);
        when(cache.asMap()).thenReturn(cacheContents);

        // When
        captureLedgerCallback().processTransaction(TestUtil.newTransaction(1L,
            AUTHED_ACCOUNT_NUM, FOREIGN_ROUTING_NUM,
            NON_AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM, AMOUNT));

        // Then
        verify(cache, never()).put(AUTHED_ACCOUNT_NUM, BALANCE - AMOUNT);
        verify(cache).put(NON_AUTHED_ACCOUNT_NUM, BALANCE + AMOUNT);
    }

    @Test
    @DisplayName("Given a transaction to another bank, do not credit the receiver")
    void ledgerCallbackIgnoresForeignReceiver() {
        // Given
        final ConcurrentMap<String, Long> cacheContents = new ConcurrentHashMap<>();
        cacheContents.put(AUTHED_ACCOUNT_NUM, BALANCE);
        cacheContents.put(NON_AUTHED_ACCOUNT_NUM, BALANCE);
        when(cache.asMap()).thenReturn(cacheContents);

        // When
        captureLedgerCallback().processTransaction(TestUtil.newTransaction(1L,
            AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM,
            NON_AUTHED_ACCOUNT_NUM, FOREIGN_ROUTING_NUM, AMOUNT));

        // Then
        verify(cache).put(AUTHED_ACCOUNT_NUM, BALANCE - AMOUNT);
        verify(cache, never()).put(NON_AUTHED_ACCOUNT_NUM, BALANCE + AMOUNT);
    }

    @Test
    @DisplayName("Given accounts that are not cached, do not populate the cache")
    void ledgerCallbackIgnoresUncachedAccounts() {
        // Given
        when(cache.asMap()).thenReturn(new ConcurrentHashMap<>());

        // When
        captureLedgerCallback().processTransaction(TestUtil.newTransaction(1L,
            AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM,
            NON_AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM, AMOUNT));

        // Then
        verify(cache, never()).put(anyString(), anyLong());
    }

    private LedgerReaderCallback captureLedgerCallback() {
        final ArgumentCaptor<LedgerReaderCallback> captor =
            ArgumentCaptor.forClass(LedgerReaderCallback.class);
        verify(ledgerReader).startWithCallback(captor.capture());
        return captor.getValue();
    }

    @Test
    @DisplayName("Given the cache throws an error for an authenticated user, return 500")
    void getBalanceFailsWhenCacheThrowsError() throws Exception {
        // Given
        when(verifier.verify(TOKEN)).thenReturn(jwt);
        when(jwt.getClaim(JWT_ACCOUNT_KEY)).thenReturn(claim);
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM)).thenThrow(ExecutionException.class);

        // When
        final ResponseEntity actualResult = balanceReaderController.getBalance(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, actualResult.getStatusCode());
    }

}
