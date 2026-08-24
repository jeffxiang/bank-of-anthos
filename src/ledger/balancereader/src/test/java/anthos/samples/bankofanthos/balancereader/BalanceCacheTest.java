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
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.MockitoAnnotations.initMocks;

import com.google.common.cache.LoadingCache;
import com.google.common.util.concurrent.UncheckedExecutionException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.springframework.dao.DataAccessResourceFailureException;

class BalanceCacheTest {

    private LoadingCache<String, Long> cache;

    @Mock
    private TransactionRepository dbRepo;

    private static final String LOCAL_ROUTING_NUM = "123456789";
    private static final String ACCOUNT_NUM = "1234567890";
    private static final int CACHE_SIZE = 8;
    private static final long BALANCE = 100L;

    @BeforeEach
    void setUp() {
        initMocks(this);
        BalanceCache balanceCache = new BalanceCache();
        TestUtil.setField(balanceCache, "dbRepo", dbRepo);
        cache = balanceCache.initializeCache(CACHE_SIZE, LOCAL_ROUTING_NUM);
    }

    @Test
    @DisplayName("Given a balance in the ledger, load it into the cache once")
    void loadReturnsBalanceFromRepository() throws Exception {
        // Given
        when(dbRepo.findBalance(ACCOUNT_NUM, LOCAL_ROUTING_NUM))
            .thenReturn(BALANCE);

        // When
        final Long firstRead = cache.get(ACCOUNT_NUM);
        final Long secondRead = cache.get(ACCOUNT_NUM);

        // Then
        assertEquals(BALANCE, firstRead);
        assertEquals(BALANCE, secondRead);
        verify(dbRepo, times(1)).findBalance(ACCOUNT_NUM, LOCAL_ROUTING_NUM);
    }

    @Test
    @DisplayName("Given an account with no transactions, cache a zero balance")
    void loadReturnsZeroWhenNoTransactionsExist() throws Exception {
        // Given
        when(dbRepo.findBalance(ACCOUNT_NUM, LOCAL_ROUTING_NUM))
            .thenReturn(null);

        // When
        final Long actualResult = cache.get(ACCOUNT_NUM);

        // Then
        assertEquals(0L, actualResult);
    }

    @Test
    @DisplayName("Given the ledger database is unreachable, surface the failure to the caller")
    void loadPropagatesDatabaseFailure() {
        // Given
        when(dbRepo.findBalance(ACCOUNT_NUM, LOCAL_ROUTING_NUM))
            .thenThrow(new DataAccessResourceFailureException("db unreachable"));

        // When / Then
        assertThrows(UncheckedExecutionException.class,
            () -> cache.get(ACCOUNT_NUM));
    }
}
