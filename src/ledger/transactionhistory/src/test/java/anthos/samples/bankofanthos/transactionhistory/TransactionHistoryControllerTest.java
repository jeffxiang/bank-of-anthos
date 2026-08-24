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
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.MockitoAnnotations.initMocks;

import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.interfaces.Claim;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.google.common.cache.CacheStats;
import com.google.common.cache.LoadingCache;
import com.google.common.util.concurrent.UncheckedExecutionException;
import io.micrometer.core.instrument.Clock;
import io.micrometer.core.lang.Nullable;
import io.micrometer.stackdriver.StackdriverConfig;
import io.micrometer.stackdriver.StackdriverMeterRegistry;
import java.util.ArrayDeque;
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
    private static final String BEARER_TOKEN = "Bearer abc";
    private static final String TOKEN = "abc";
    private static final String PUBLIC_KEY_PATH = "path/";
    private static final String FOREIGN_ROUTING_NUM = "987654321";
    private static final int AMOUNT = 25;
    private static final int DEFAULT_HISTORY_LIMIT = 100;
    private static final int HISTORY_LIMIT = 2;
    private static final int EXTRA_LATENCY_MILLIS = 5;

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

        TestUtil.setField(transactionHistoryController, "historyLimit",
            DEFAULT_HISTORY_LIMIT);

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
    @DisplayName("Given an Authorization header without the Bearer prefix, still authorize the user")
    void getTransactionsSucceedsWhenTokenHasNoBearerPrefix() throws Exception {
        // Given
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM)).thenReturn(transactions);

        // When
        final ResponseEntity actualResult = transactionHistoryController
            .getTransactions(TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.OK, actualResult.getStatusCode());
        assertSame(transactions, actualResult.getBody());
    }

    @Test
    @DisplayName("Given no Authorization header, return 401")
    void getTransactionsFailsWhenTokenIsNull() {
        // Given
        when(verifier.verify((String) null)).thenThrow(JWTVerificationException.class);

        // When
        final ResponseEntity actualResult = transactionHistoryController
            .getTransactions(null, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the token carries no account claim, return 401")
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
    @DisplayName("Given extra latency is configured, still return the history")
    void getTransactionsSucceedsWithExtraLatency() throws Exception {
        // Given
        TestUtil.setField(transactionHistoryController, "extraLatencyMillis",
            EXTRA_LATENCY_MILLIS);
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
    @DisplayName("Given the artificial latency is interrupted, still return the history")
    void getTransactionsSucceedsWhenLatencySleepIsInterrupted() throws Exception {
        // Given
        TestUtil.setField(transactionHistoryController, "extraLatencyMillis",
            EXTRA_LATENCY_MILLIS);
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM)).thenReturn(transactions);
        Thread.currentThread().interrupt();

        // When
        final ResponseEntity actualResult = transactionHistoryController
            .getTransactions(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.OK, actualResult.getStatusCode());
        assertFalse(Thread.interrupted(), "interrupt flag should be consumed");
    }

    @Test
    @DisplayName("Given the cache loader fails unchecked for an authenticated user, return 500")
    void getTransactionsFailsWhenCacheThrowsUncheckedError() throws Exception {
        // Given
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM)).thenThrow(
            new UncheckedExecutionException(new DataAccessResourceFailureException("db down")));

        // When
        final ResponseEntity actualResult = transactionHistoryController
            .getTransactions(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given a local transaction, prepend it to both cached account histories")
    void ledgerCallbackAddsTransactionToCachedHistories() {
        // Given
        final Deque<Transaction> senderHistory = new ArrayDeque<>();
        final Deque<Transaction> receiverHistory = new ArrayDeque<>();
        stubCacheContents(senderHistory, receiverHistory);
        final Transaction transaction = TestUtil.newTransaction(1L,
            AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM,
            NON_AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM, AMOUNT);

        // When
        captureLedgerCallback().processTransaction(transaction);

        // Then
        assertSame(transaction, senderHistory.peekFirst());
        assertSame(transaction, receiverHistory.peekFirst());
    }

    @Test
    @DisplayName("Given the history limit is reached, drop the oldest transaction")
    void ledgerCallbackDropsOldestTransactionBeyondHistoryLimit() {
        // Given
        TestUtil.setField(transactionHistoryController, "historyLimit",
            HISTORY_LIMIT);
        final Transaction oldest = TestUtil.newTransaction(1L,
            AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM,
            NON_AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM, AMOUNT);
        final Transaction newer = TestUtil.newTransaction(2L,
            AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM,
            NON_AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM, AMOUNT);
        final Deque<Transaction> senderHistory = new ArrayDeque<>();
        senderHistory.add(newer);
        senderHistory.add(oldest);
        stubCacheContents(senderHistory, new ArrayDeque<>());
        final Transaction newest = TestUtil.newTransaction(3L,
            AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM,
            NON_AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM, AMOUNT);

        // When
        captureLedgerCallback().processTransaction(newest);

        // Then
        assertEquals(HISTORY_LIMIT, senderHistory.size());
        assertSame(newest, senderHistory.peekFirst());
        assertSame(newer, senderHistory.peekLast());
    }

    @Test
    @DisplayName("Given a transaction from another bank, do not touch the sender history")
    void ledgerCallbackIgnoresForeignSender() {
        // Given
        final Deque<Transaction> senderHistory = new ArrayDeque<>();
        final Deque<Transaction> receiverHistory = new ArrayDeque<>();
        stubCacheContents(senderHistory, receiverHistory);

        // When
        captureLedgerCallback().processTransaction(TestUtil.newTransaction(1L,
            AUTHED_ACCOUNT_NUM, FOREIGN_ROUTING_NUM,
            NON_AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM, AMOUNT));

        // Then
        assertEquals(0, senderHistory.size());
        assertEquals(1, receiverHistory.size());
    }

    @Test
    @DisplayName("Given a transaction to another bank, do not touch the receiver history")
    void ledgerCallbackIgnoresForeignReceiver() {
        // Given
        final Deque<Transaction> senderHistory = new ArrayDeque<>();
        final Deque<Transaction> receiverHistory = new ArrayDeque<>();
        stubCacheContents(senderHistory, receiverHistory);

        // When
        captureLedgerCallback().processTransaction(TestUtil.newTransaction(1L,
            AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM,
            NON_AUTHED_ACCOUNT_NUM, FOREIGN_ROUTING_NUM, AMOUNT));

        // Then
        assertEquals(1, senderHistory.size());
        assertEquals(0, receiverHistory.size());
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
        verify(cache, never()).put(anyString(), org.mockito.ArgumentMatchers.any());
    }

    private void stubCacheContents(Deque<Transaction> senderHistory,
            Deque<Transaction> receiverHistory) {
        final ConcurrentMap<String, Deque<Transaction>> cacheContents =
            new ConcurrentHashMap<>();
        cacheContents.put(AUTHED_ACCOUNT_NUM, senderHistory);
        cacheContents.put(NON_AUTHED_ACCOUNT_NUM, receiverHistory);
        when(cache.asMap()).thenReturn(cacheContents);
    }

    private LedgerReaderCallback captureLedgerCallback() {
        final ArgumentCaptor<LedgerReaderCallback> captor =
            ArgumentCaptor.forClass(LedgerReaderCallback.class);
        verify(ledgerReader).startWithCallback(captor.capture());
        return captor.getValue();
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

}
