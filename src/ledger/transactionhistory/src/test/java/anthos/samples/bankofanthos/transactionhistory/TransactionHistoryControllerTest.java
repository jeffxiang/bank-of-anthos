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

package anthos.samples.bankofanthos.transactionhistory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.MockitoAnnotations.initMocks;

import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.exceptions.TokenExpiredException;
import com.auth0.jwt.interfaces.Claim;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.google.common.cache.CacheStats;
import com.google.common.cache.LoadingCache;
import com.google.common.util.concurrent.UncheckedExecutionException;
import io.micrometer.core.instrument.Clock;
import io.micrometer.core.lang.Nullable;
import io.micrometer.stackdriver.StackdriverConfig;
import io.micrometer.stackdriver.StackdriverMeterRegistry;
import java.lang.reflect.Field;
import java.time.Instant;
import java.util.Deque;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ExecutionException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.ResourceAccessException;

class TransactionHistoryControllerTest {

    private TransactionHistoryController transactionHistoryController;

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
    private LoadingCache<String, Deque<Transaction>> cache;
    @Mock
    private CacheStats stats;
    @Mock
    private Deque<Transaction> transactions;

    private static final String VERSION = "v0.2.0";
    private static final String LOCAL_ROUTING_NUM = "123456789";
    private static final String OK_CODE = "ok";
    private static final String JWT_ACCOUNT_KEY = "acct";
    private static final String AUTHED_ACCOUNT_NUM = "1234567890";
    private static final String NON_AUTHED_ACCOUNT_NUM = "9876543210";
    private static final String REMOTE_ROUTING_NUM = "987654321";
    private static final int HISTORY_LIMIT = 100;
    private static final String BEARER_TOKEN = "Bearer abc";
    private static final String TOKEN = "abc";
    private static final String MALFORMED_TOKEN = "Basic abc";
    private static final String NOT_AUTHORIZED = "not authorized";
    private static final String CACHE_ERROR = "cache error";
    private static final String PUBLIC_KEY_PATH = "path/";

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
        transactionHistoryController = new TransactionHistoryController(ledgerReader,
            meterRegistry, verifier, PUBLIC_KEY_PATH, cache, LOCAL_ROUTING_NUM, VERSION);

        when(verifier.verify(TOKEN)).thenReturn(jwt);
        when(jwt.getClaim(JWT_ACCOUNT_KEY)).thenReturn(claim);
    }

    @Test
    @DisplayName("Given version number in the environment, " +
            "return a ResponseEntity with the version number")
    void version() {
        // When
        final ResponseEntity actualResult = transactionHistoryController.version();

        // Then
        assertNotNull(actualResult);
        assertEquals(VERSION, actualResult.getBody());
        assertEquals(HttpStatus.OK, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the server is serving requests, return HTTP Status 200")
    void readiness() {
        // When
        final String actualResult = transactionHistoryController.readiness();

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
        final ResponseEntity actualResult = transactionHistoryController.liveness();

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
        final ResponseEntity actualResult = transactionHistoryController.liveness();

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the user is authenticated for the account, return HTTP Status 200")
    void getTransactionsSucceedsWhenAccountMatchesAuthenticatedUser() throws Exception {
        // Given
        when(verifier.verify(TOKEN)).thenReturn(jwt);
        when(jwt.getClaim(JWT_ACCOUNT_KEY)).thenReturn(claim);
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM)).thenReturn(transactions);

        // When
        final ResponseEntity actualResult = transactionHistoryController
            .getTransactions(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.OK, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the user is authenticated but cannot access the account, return 401")
    void getTransactionsFailsWhenAccountDoesNotMatchAuthenticatedUser() {
        // Given
        when(verifier.verify(TOKEN)).thenReturn(jwt);
        when(jwt.getClaim(JWT_ACCOUNT_KEY)).thenReturn(claim);
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);

        // When
        final ResponseEntity actualResult = transactionHistoryController.getTransactions(BEARER_TOKEN, NON_AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the user is not authenticated, return 401")
    void getTransactionsFailsWhenUserNotAuthenticated() {
        // Given
        when(verifier.verify(TOKEN)).thenThrow(JWTVerificationException.class);

        // When
        final ResponseEntity actualResult = transactionHistoryController.getTransactions(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the cache throws an error for an authenticated user, return 500")
    void getTransactionsFailsWhenCacheThrowsError() throws Exception {
        // Given
        when(verifier.verify(TOKEN)).thenReturn(jwt);
        when(jwt.getClaim(JWT_ACCOUNT_KEY)).thenReturn(claim);
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM)).thenThrow(ExecutionException.class);

        // When
        final ResponseEntity actualResult = transactionHistoryController
            .getTransactions(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given no Authorization header, return 401 without touching the cache")
    void getTransactionsFailsWhenTokenIsMissing() throws Exception {
        // Given
        when(verifier.verify((String) null)).thenThrow(JWTVerificationException.class);

        // When
        final ResponseEntity actualResult = transactionHistoryController
            .getTransactions(null, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
        assertEquals(NOT_AUTHORIZED, actualResult.getBody());
        verify(cache, never()).get(anyString());
    }

    @Test
    @DisplayName("Given an Authorization header without the Bearer prefix, return 401")
    void getTransactionsFailsWhenTokenIsMalformed() {
        // Given
        when(verifier.verify(MALFORMED_TOKEN)).thenThrow(JWTVerificationException.class);

        // When
        final ResponseEntity actualResult = transactionHistoryController
            .getTransactions(MALFORMED_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
        assertEquals(NOT_AUTHORIZED, actualResult.getBody());
    }

    @Test
    @DisplayName("Given an expired token, return 401")
    void getTransactionsFailsWhenTokenIsExpired() throws Exception {
        // Given
        when(verifier.verify(TOKEN))
            .thenThrow(new TokenExpiredException("token expired", Instant.EPOCH));

        // When
        final ResponseEntity actualResult = transactionHistoryController
            .getTransactions(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
        verify(cache, never()).get(anyString());
    }

    @Test
    @DisplayName("Given a valid token with no account claim, return 401")
    void getTransactionsFailsWhenAccountClaimIsMissing() throws Exception {
        // Given
        when(claim.asString()).thenReturn(null);

        // When
        final ResponseEntity actualResult = transactionHistoryController
            .getTransactions(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
        verify(cache, never()).get(anyString());
    }

    @Test
    @DisplayName("Given the cache loader cannot reach the database, return 500")
    void getTransactionsFailsWhenCacheLoaderCannotReachDatabase() throws Exception {
        // Given
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM)).thenThrow(new ExecutionException(
            new DataAccessResourceFailureException("ledger-db unreachable")));

        // When
        final ResponseEntity actualResult = transactionHistoryController
            .getTransactions(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, actualResult.getStatusCode());
        assertEquals(CACHE_ERROR, actualResult.getBody());
    }

    @Test
    @DisplayName("Given the cache loader throws an unchecked database error, return 500")
    void getTransactionsFailsWhenCacheLoaderThrowsUncheckedError() throws Exception {
        // Given
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM)).thenThrow(new UncheckedExecutionException(
            new ResourceAccessException("ledger-db connection reset")));

        // When
        final ResponseEntity actualResult = transactionHistoryController
            .getTransactions(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, actualResult.getStatusCode());
        assertEquals(CACHE_ERROR, actualResult.getBody());
    }

    @Test
    @DisplayName("Given an incoming transaction for an uncached account, "
            + "leave the cache untouched")
    void ledgerCallbackIgnoresTransactionsForUncachedAccounts() {
        // Given
        final ConcurrentMap<String, Deque<Transaction>> cacheMap =
            new ConcurrentHashMap<>();
        when(cache.asMap()).thenReturn(cacheMap);
        final Transaction transaction = mock(Transaction.class);
        when(transaction.getFromAccountNum()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(transaction.getFromRoutingNum()).thenReturn(LOCAL_ROUTING_NUM);
        when(transaction.getToAccountNum()).thenReturn(NON_AUTHED_ACCOUNT_NUM);
        when(transaction.getToRoutingNum()).thenReturn(REMOTE_ROUTING_NUM);

        // When
        captureLedgerCallback().processTransaction(transaction);

        // Then
        assertTrue(cacheMap.isEmpty());
    }

    @Test
    @DisplayName("Given an incoming local transaction for a cached account, "
            + "prepend it and drop history beyond the limit")
    void ledgerCallbackUpdatesCachedAccountAndTrimsHistory() throws Exception {
        // Given
        setHistoryLimit(HISTORY_LIMIT);
        final ConcurrentMap<String, Deque<Transaction>> cacheMap =
            new ConcurrentHashMap<>();
        cacheMap.put(AUTHED_ACCOUNT_NUM, transactions);
        when(cache.asMap()).thenReturn(cacheMap);
        when(transactions.size()).thenReturn(HISTORY_LIMIT + 1);
        final Transaction transaction = mock(Transaction.class);
        when(transaction.getFromAccountNum()).thenReturn(NON_AUTHED_ACCOUNT_NUM);
        when(transaction.getFromRoutingNum()).thenReturn(REMOTE_ROUTING_NUM);
        when(transaction.getToAccountNum()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(transaction.getToRoutingNum()).thenReturn(LOCAL_ROUTING_NUM);

        // When
        captureLedgerCallback().processTransaction(transaction);

        // Then
        verify(transactions).addFirst(transaction);
        verify(transactions).removeLast();
    }

    private void setHistoryLimit(int limit) throws Exception {
        final Field field = TransactionHistoryController.class
            .getDeclaredField("historyLimit");
        field.setAccessible(true);
        field.set(transactionHistoryController, limit);
    }

    private LedgerReaderCallback captureLedgerCallback() {
        final ArgumentCaptor<LedgerReaderCallback> captor =
            ArgumentCaptor.forClass(LedgerReaderCallback.class);
        verify(ledgerReader).startWithCallback(captor.capture());
        return captor.getValue();
    }

}
