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
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
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
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.web.client.ResourceAccessException;

class TransactionCacheTest {

    @Mock
    private TransactionRepository dbRepo;

    @InjectMocks
    private TransactionCache transactionCache;

    @BeforeEach
    void setUp() {
        initMocks(this);
    }

    @Test
    @DisplayName("Given history in the repository, load it into the cache")
    void initializeCacheLoadsHistoryWhenRepositoryFindsValue() throws Exception {
        // Given
        LinkedList<Transaction> expected = new LinkedList<>();
        when(dbRepo.findForAccount(
            "account", "routing", PageRequest.of(0, 25))).thenReturn(expected);
        LoadingCache<String, Deque<Transaction>> cache =
            transactionCache.initializeCache(10, 60, "routing", 25);

        // When
        Deque<Transaction> history = cache.get("account");

        // Then
        assertEquals(expected, history);
        ArgumentCaptor<Pageable> pageCaptor =
            ArgumentCaptor.forClass(Pageable.class);
        verify(dbRepo).findForAccount(
            eq("account"), eq("routing"), pageCaptor.capture());
        assertEquals(0, pageCaptor.getValue().getPageNumber());
        assertEquals(25, pageCaptor.getValue().getPageSize());
    }

    @Test
    @DisplayName("Given a resource error, surface an unchecked cache error")
    void initializeCacheFailsWhenRepositoryThrowsResourceError() {
        // Given
        when(dbRepo.findForAccount(
            anyString(), anyString(), any(Pageable.class)))
            .thenThrow(new ResourceAccessException("database unavailable"));
        LoadingCache<String, Deque<Transaction>> cache =
            transactionCache.initializeCache(10, 60, "routing", 25);

        // When
        UncheckedExecutionException exception = assertThrows(
            UncheckedExecutionException.class, () -> cache.get("account"));

        // Then
        assertEquals(ResourceAccessException.class,
            exception.getCause().getClass());
    }

    @Test
    @DisplayName("Given a data access failure, surface an unchecked cache error")
    void initializeCacheFailsWhenRepositoryThrowsDataAccessError() {
        // Given
        when(dbRepo.findForAccount(
            anyString(), anyString(), any(Pageable.class)))
            .thenThrow(new DataAccessResourceFailureException(
                "database unavailable"));
        LoadingCache<String, Deque<Transaction>> cache =
            transactionCache.initializeCache(10, 60, "routing", 25);

        // When
        UncheckedExecutionException exception = assertThrows(
            UncheckedExecutionException.class, () -> cache.get("account"));

        // Then
        assertEquals(DataAccessResourceFailureException.class,
            exception.getCause().getClass());
    }
}
