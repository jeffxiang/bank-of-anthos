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

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.MockitoAnnotations.initMocks;

import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.interfaces.Claim;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.google.common.cache.CacheBuilder;
import com.google.common.cache.CacheLoader;
import com.google.common.cache.CacheStats;
import com.google.common.cache.LoadingCache;
import com.google.common.util.concurrent.UncheckedExecutionException;
import io.micrometer.core.instrument.Clock;
import io.micrometer.core.instrument.binder.cache.GuavaCacheMetrics;
import io.micrometer.core.lang.Nullable;
import io.micrometer.stackdriver.StackdriverConfig;
import io.micrometer.stackdriver.StackdriverMeterRegistry;
import java.lang.reflect.Field;
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
    private ConcurrentMap<String, Long> balances;
    private LedgerReaderCallback callback;

    private static final String VERSION = "v0.2.0";
    private static final String LOCAL_ROUTING_NUM = "123456789";
    private static final String OK_CODE = "ok";
    private static final String JWT_ACCOUNT_KEY = "acct";
    private static final long BALANCE = 100l;
    private static final String AUTHED_ACCOUNT_NUM = "1234567890";
    private static final String NON_AUTHED_ACCOUNT_NUM = "9876543210";
    private static final String BEARER_TOKEN = "Bearer abc";
    private static final String TOKEN = "abc";

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
        balances = new ConcurrentHashMap<>();
        when(cache.asMap()).thenReturn(balances);
        doAnswer(invocation -> balances.put(invocation.getArgument(0),
            invocation.getArgument(1))).when(cache).put(anyString(), anyLong());
        balanceReaderController = new BalanceReaderController(ledgerReader, verifier,
            meterRegistry, cache, LOCAL_ROUTING_NUM, VERSION);
        ArgumentCaptor<LedgerReaderCallback> callbackCaptor =
            ArgumentCaptor.forClass(LedgerReaderCallback.class);
        verify(ledgerReader).startWithCallback(callbackCaptor.capture());
        callback = callbackCaptor.getValue();

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

    @Test
    @DisplayName("Given an unchecked cache error, return 500")
    void getBalanceFailsWhenCacheThrowsUncheckedError() throws Exception {
        // Given
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(cache.get(AUTHED_ACCOUNT_NUM))
            .thenThrow(new UncheckedExecutionException(new RuntimeException()));

        // When
        ResponseEntity actualResult = balanceReaderController.getBalance(
            BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given a missing authorization header, return 401")
    void getBalanceFailsWhenAuthorizationHeaderIsNull() {
        // Given
        when(verifier.verify((String) null)).thenThrow(JWTVerificationException.class);

        // When
        ResponseEntity actualResult = balanceReaderController.getBalance(
            null, AUTHED_ACCOUNT_NUM);

        // Then
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given a raw token without a Bearer prefix, return 401")
    void getBalanceFailsWhenAuthorizationHeaderHasNoBearerPrefix() {
        // Given
        when(verifier.verify("raw-token")).thenThrow(JWTVerificationException.class);

        // When
        ResponseEntity actualResult = balanceReaderController.getBalance(
            "raw-token", AUTHED_ACCOUNT_NUM);

        // Then
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given a token with a null account claim, return 401")
    void getBalanceFailsWhenAuthenticatedAccountClaimIsNull() {
        // Given
        when(claim.asString()).thenReturn(null);

        // When
        ResponseEntity actualResult = balanceReaderController.getBalance(
            BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given a token with an empty account claim, return 401")
    void getBalanceFailsWhenAuthenticatedAccountClaimIsEmpty() {
        // Given
        when(claim.asString()).thenReturn("");

        // When
        ResponseEntity actualResult = balanceReaderController.getBalance(
            BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given a local debit and credit, update both cached balances")
    void callbackUpdatesBalancesWhenBothTransactionSidesAreLocal() {
        // Given
        Transaction transaction = transaction(11L, "from", LOCAL_ROUTING_NUM,
            "to", LOCAL_ROUTING_NUM, 25);
        balances.put("from", 100L);
        balances.put("to", 200L);

        // When
        callback.processTransaction(transaction);

        // Then
        assertEquals(75L, balances.get("from"));
        assertEquals(225L, balances.get("to"));
    }

    @Test
    @DisplayName("Given a foreign transaction, do not change cached balances")
    void callbackDoesNotUpdateBalancesWhenTransactionIsForeign() {
        // Given
        Transaction transaction = transaction(12L, "from", "foreign",
            "to", "remote", 25);
        balances.put("from", 100L);
        balances.put("to", 200L);

        // When
        callback.processTransaction(transaction);

        // Then
        assertEquals(100L, balances.get("from"));
        assertEquals(200L, balances.get("to"));
        verify(cache, never()).put(anyString(), anyLong());
    }

    @Test
    @DisplayName("Given a local side absent from cache, do not update it")
    void callbackDoesNotUpdateMissingCachedAccount() {
        // Given
        Transaction transaction = transaction(13L, "missing", LOCAL_ROUTING_NUM,
            "to", "remote", 25);
        balances.put("to", 200L);

        // When
        callback.processTransaction(transaction);

        // Then
        assertFalse(balances.containsKey("missing"));
        assertEquals(200L, balances.get("to"));
        verify(cache, never()).put(anyString(), anyLong());
    }

    private Transaction transaction(long id, String fromAccount,
        String fromRouting, String toAccount, String toRouting, int amount) {
        Transaction transaction = new Transaction();
        setField(transaction, "transactionId", id);
        setField(transaction, "fromAccountNum", fromAccount);
        setField(transaction, "fromRoutingNum", fromRouting);
        setField(transaction, "toAccountNum", toAccount);
        setField(transaction, "toRoutingNum", toRouting);
        setField(transaction, "amount", amount);
        return transaction;
    }

    private static void setField(Object target, String name, Object value) {
        try {
            Field field = target.getClass().getDeclaredField(name);
            field.setAccessible(true);
            field.set(target, value);
        } catch (ReflectiveOperationException e) {
            throw new AssertionError(e);
        }
    }

}
