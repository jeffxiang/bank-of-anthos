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
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.MockitoAnnotations.initMocks;

import com.google.common.cache.LoadingCache;
import com.google.common.util.concurrent.UncheckedExecutionException;
import java.util.Deque;
import java.util.LinkedList;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.data.domain.Pageable;

class TransactionCacheTest {

    private LoadingCache<String, Deque<Transaction>> cache;

    @Mock
    private TransactionRepository dbRepo;

    private static final String LOCAL_ROUTING_NUM = "123456789";
    private static final String ACCOUNT_NUM = "1234567890";
    private static final int CACHE_SIZE = 8;
    private static final int CACHE_MINUTES = 60;
    private static final int HISTORY_LIMIT = 3;

    @BeforeEach
    void setUp() {
        initMocks(this);
        TransactionCache transactionCache = new TransactionCache();
        TestUtil.setField(transactionCache, "dbRepo", dbRepo);
        cache = transactionCache.initializeCache(CACHE_SIZE, CACHE_MINUTES,
            LOCAL_ROUTING_NUM, HISTORY_LIMIT);
    }

    @Test
    @DisplayName("Given transactions in the ledger, load them into the cache once")
    void loadReturnsTransactionsFromRepository() throws Exception {
        // Given
        final LinkedList<Transaction> transactions = new LinkedList<>();
        transactions.add(TestUtil.newTransaction(1L, ACCOUNT_NUM,
            LOCAL_ROUTING_NUM, ACCOUNT_NUM, LOCAL_ROUTING_NUM, 10));
        when(dbRepo.findForAccount(eq(ACCOUNT_NUM), eq(LOCAL_ROUTING_NUM),
            any(Pageable.class))).thenReturn(transactions);

        // When
        final Deque<Transaction> firstRead = cache.get(ACCOUNT_NUM);
        final Deque<Transaction> secondRead = cache.get(ACCOUNT_NUM);

        // Then
        assertEquals(transactions, firstRead);
        assertEquals(transactions, secondRead);
        verify(dbRepo, times(1)).findForAccount(eq(ACCOUNT_NUM),
            eq(LOCAL_ROUTING_NUM), any(Pageable.class));
    }

    @Test
    @DisplayName("Given a history limit, request at most that many transactions")
    void loadRequestsAtMostTheHistoryLimit() throws Exception {
        // Given
        when(dbRepo.findForAccount(eq(ACCOUNT_NUM), eq(LOCAL_ROUTING_NUM),
            any(Pageable.class))).thenReturn(new LinkedList<>());
        final ArgumentCaptor<Pageable> captor =
            ArgumentCaptor.forClass(Pageable.class);

        // When
        cache.get(ACCOUNT_NUM);

        // Then
        verify(dbRepo).findForAccount(eq(ACCOUNT_NUM), eq(LOCAL_ROUTING_NUM),
            captor.capture());
        assertEquals(HISTORY_LIMIT, captor.getValue().getPageSize());
    }

    @Test
    @DisplayName("Given the ledger database is unreachable, surface the failure to the caller")
    void loadPropagatesDatabaseFailure() {
        // Given
        when(dbRepo.findForAccount(eq(ACCOUNT_NUM), eq(LOCAL_ROUTING_NUM),
            any(Pageable.class)))
            .thenThrow(new DataAccessResourceFailureException("db unreachable"));

        // When / Then
        assertThrows(UncheckedExecutionException.class,
            () -> cache.get(ACCOUNT_NUM));
    }
}
