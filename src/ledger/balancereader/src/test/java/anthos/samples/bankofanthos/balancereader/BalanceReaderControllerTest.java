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
import com.google.common.util.concurrent.UncheckedExecutionException;
import io.micrometer.core.instrument.Clock;
import io.micrometer.core.instrument.binder.cache.GuavaCacheMetrics;
import io.micrometer.core.lang.Nullable;
import io.micrometer.stackdriver.StackdriverConfig;
import io.micrometer.stackdriver.StackdriverMeterRegistry;
import java.util.concurrent.ExecutionException;

import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.exceptions.TokenExpiredException;
import com.auth0.jwt.interfaces.Claim;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.google.common.cache.CacheBuilder;
import com.google.common.cache.LoadingCache;
import java.lang.reflect.Field;
import java.time.Instant;
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
    @Mock
    private TransactionRepository dbRepo;
    @Mock
    private Transaction transaction;

    private StackdriverMeterRegistry meterRegistry;

    private static final String VERSION = "v0.2.0";
    private static final String LOCAL_ROUTING_NUM = "123456789";
    private static final String OK_CODE = "ok";
    private static final String JWT_ACCOUNT_KEY = "acct";
    private static final long BALANCE = 100l;
    private static final String AUTHED_ACCOUNT_NUM = "1234567890";
    private static final String NON_AUTHED_ACCOUNT_NUM = "9876543210";
    private static final String BEARER_TOKEN = "Bearer abc";
    private static final String TOKEN = "abc";
    private static final String EXTERNAL_ROUTING_NUM = "987654321";
    private static final int TRANSACTION_AMOUNT = 25;
    private static final int CACHE_SIZE = 100;

    @BeforeEach
    void setUp() {
        initMocks(this);
        meterRegistry = new StackdriverMeterRegistry(new StackdriverConfig() {
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
    @DisplayName("Given no Authorization header, return 401")
    void getBalanceFailsWhenAuthorizationHeaderIsMissing() {
        // Given
        when(verifier.verify((String) null)).thenThrow(JWTVerificationException.class);

        // When
        final ResponseEntity actualResult = balanceReaderController.getBalance(null, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given an expired token, return 401")
    void getBalanceFailsWhenTokenIsExpired() {
        // Given
        when(verifier.verify(TOKEN)).thenThrow(
            new TokenExpiredException("token expired", Instant.EPOCH));

        // When
        final ResponseEntity actualResult = balanceReaderController.getBalance(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.UNAUTHORIZED, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given a token sent without the Bearer prefix, still authorize the request")
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
    @DisplayName("Given the cache wraps a database failure in an unchecked exception, return 500")
    void getBalanceFailsWhenCacheThrowsUncheckedExecutionException() throws Exception {
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
    @DisplayName("Given the ledger database is unreachable, the real cache loader surfaces a 500")
    void getBalanceFailsWhenLedgerDatabaseIsUnreachable() throws Exception {
        // Given
        when(dbRepo.findBalance(AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM))
            .thenThrow(new ResourceAccessException("ledger unreachable"));
        final BalanceReaderController controller = controllerWithRealCache();
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);

        // When
        final ResponseEntity actualResult = controller.getBalance(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, actualResult.getStatusCode());
    }

    @Test
    @DisplayName("Given the ledger has no rows for the account, the real cache loader returns a zero balance")
    void getBalanceReturnsZeroWhenLedgerHasNoRowsForAccount() throws Exception {
        // Given
        when(dbRepo.findBalance(AUTHED_ACCOUNT_NUM, LOCAL_ROUTING_NUM)).thenReturn(null);
        final BalanceReaderController controller = controllerWithRealCache();
        when(claim.asString()).thenReturn(AUTHED_ACCOUNT_NUM);

        // When
        final ResponseEntity actualResult = controller.getBalance(BEARER_TOKEN, AUTHED_ACCOUNT_NUM);

        // Then
        assertNotNull(actualResult);
        assertEquals(HttpStatus.OK, actualResult.getStatusCode());
        assertEquals(0L, actualResult.getBody());
    }

    @Test
    @DisplayName("Given a transaction for accounts absent from the cache, do not populate the cache")
    void ledgerCallbackLeavesUncachedAccountsAlone() throws Exception {
        // Given
        final LoadingCache<String, Long> realCache = newRealCache();
        final LedgerReaderCallback callback = callbackOf(realCache);
        when(transaction.getFromAccountNum()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(transaction.getFromRoutingNum()).thenReturn(LOCAL_ROUTING_NUM);
        when(transaction.getToAccountNum()).thenReturn(NON_AUTHED_ACCOUNT_NUM);
        when(transaction.getToRoutingNum()).thenReturn(LOCAL_ROUTING_NUM);
        when(transaction.getAmount()).thenReturn(TRANSACTION_AMOUNT);

        // When
        callback.processTransaction(transaction);

        // Then
        assertTrue(realCache.asMap().isEmpty());
        verifyNoInteractions(dbRepo);
    }

    @Test
    @DisplayName("Given a transaction routed to another bank, leave cached balances untouched")
    void ledgerCallbackIgnoresExternalRoutingNumbers() throws Exception {
        // Given
        final LoadingCache<String, Long> realCache = newRealCache();
        final LedgerReaderCallback callback = callbackOf(realCache);
        realCache.put(AUTHED_ACCOUNT_NUM, BALANCE);
        realCache.put(NON_AUTHED_ACCOUNT_NUM, BALANCE);
        when(transaction.getFromAccountNum()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(transaction.getFromRoutingNum()).thenReturn(EXTERNAL_ROUTING_NUM);
        when(transaction.getToAccountNum()).thenReturn(NON_AUTHED_ACCOUNT_NUM);
        when(transaction.getToRoutingNum()).thenReturn(EXTERNAL_ROUTING_NUM);
        when(transaction.getAmount()).thenReturn(TRANSACTION_AMOUNT);

        // When
        callback.processTransaction(transaction);

        // Then
        assertEquals(BALANCE, realCache.asMap().get(AUTHED_ACCOUNT_NUM));
        assertEquals(BALANCE, realCache.asMap().get(NON_AUTHED_ACCOUNT_NUM));
    }

    @Test
    @DisplayName("Given a local transaction between cached accounts, move the amount between them")
    void ledgerCallbackUpdatesCachedLocalAccounts() throws Exception {
        // Given
        final LoadingCache<String, Long> realCache = newRealCache();
        final LedgerReaderCallback callback = callbackOf(realCache);
        realCache.put(AUTHED_ACCOUNT_NUM, BALANCE);
        realCache.put(NON_AUTHED_ACCOUNT_NUM, BALANCE);
        when(transaction.getFromAccountNum()).thenReturn(AUTHED_ACCOUNT_NUM);
        when(transaction.getFromRoutingNum()).thenReturn(LOCAL_ROUTING_NUM);
        when(transaction.getToAccountNum()).thenReturn(NON_AUTHED_ACCOUNT_NUM);
        when(transaction.getToRoutingNum()).thenReturn(LOCAL_ROUTING_NUM);
        when(transaction.getAmount()).thenReturn(TRANSACTION_AMOUNT);

        // When
        callback.processTransaction(transaction);

        // Then
        assertEquals(BALANCE - TRANSACTION_AMOUNT, realCache.asMap().get(AUTHED_ACCOUNT_NUM));
        assertEquals(BALANCE + TRANSACTION_AMOUNT, realCache.asMap().get(NON_AUTHED_ACCOUNT_NUM));
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

    /** Builds the production Guava cache backed by the mocked repository. */
    private LoadingCache<String, Long> newRealCache() throws Exception {
        final BalanceCache balanceCache = new BalanceCache();
        final Field repoField = BalanceCache.class.getDeclaredField("dbRepo");
        repoField.setAccessible(true);
        repoField.set(balanceCache, dbRepo);
        return balanceCache.initializeCache(CACHE_SIZE, LOCAL_ROUTING_NUM);
    }

    private BalanceReaderController controllerWithRealCache() throws Exception {
        return new BalanceReaderController(ledgerReader, verifier, meterRegistry,
            newRealCache(), LOCAL_ROUTING_NUM, VERSION);
    }

    /** Captures the ledger callback registered by a controller using the given cache. */
    private LedgerReaderCallback callbackOf(LoadingCache<String, Long> realCache) {
        clearInvocations(ledgerReader);
        new BalanceReaderController(ledgerReader, verifier, meterRegistry,
            realCache, LOCAL_ROUTING_NUM, VERSION);
        final ArgumentCaptor<LedgerReaderCallback> captor =
            ArgumentCaptor.forClass(LedgerReaderCallback.class);
        verify(ledgerReader).startWithCallback(captor.capture());
        return captor.getValue();
    }
}
