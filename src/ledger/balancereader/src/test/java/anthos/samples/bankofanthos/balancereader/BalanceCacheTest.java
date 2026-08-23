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
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.MockitoAnnotations.initMocks;

import com.google.common.cache.LoadingCache;
import com.google.common.util.concurrent.UncheckedExecutionException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.web.client.ResourceAccessException;

class BalanceCacheTest {

    @Mock
    private TransactionRepository dbRepo;

    @InjectMocks
    private BalanceCache balanceCache;

    @BeforeEach
    void setUp() {
        initMocks(this);
    }

    @Test
    @DisplayName("Given a balance in the repository, load it into the cache")
    void initializeCacheLoadsBalanceWhenRepositoryFindsValue() throws Exception {
        // Given
        when(dbRepo.findBalance("account", "routing")).thenReturn(123L);
        LoadingCache<String, Long> cache =
            balanceCache.initializeCache(10, "routing");

        // When
        Long balance = cache.get("account");

        // Then
        assertEquals(123L, balance);
        verify(dbRepo).findBalance("account", "routing");
    }

    @Test
    @DisplayName("Given no balance in the repository, load zero")
    void initializeCacheLoadsZeroWhenRepositoryReturnsNull() throws Exception {
        // Given
        when(dbRepo.findBalance("account", "routing")).thenReturn(null);
        LoadingCache<String, Long> cache =
            balanceCache.initializeCache(10, "routing");

        // When
        Long balance = cache.get("account");

        // Then
        assertEquals(0L, balance);
    }

    @Test
    @DisplayName("Given a resource error, surface an unchecked cache error")
    void initializeCacheFailsWhenRepositoryThrowsResourceError() {
        // Given
        when(dbRepo.findBalance("account", "routing"))
            .thenThrow(new ResourceAccessException("database unavailable"));
        LoadingCache<String, Long> cache =
            balanceCache.initializeCache(10, "routing");

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
        when(dbRepo.findBalance("account", "routing"))
            .thenThrow(new DataAccessResourceFailureException(
                "database unavailable"));
        LoadingCache<String, Long> cache =
            balanceCache.initializeCache(10, "routing");

        // When
        UncheckedExecutionException exception = assertThrows(
            UncheckedExecutionException.class, () -> cache.get("account"));

        // Then
        assertEquals(DataAccessResourceFailureException.class,
            exception.getCause().getClass());
    }
}
