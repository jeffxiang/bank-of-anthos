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

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.MockitoAnnotations.initMocks;

import java.lang.reflect.Field;
import java.util.Collections;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.web.client.ResourceAccessException;

class LedgerReaderTest {

    private static final String LOCAL_ROUTING_NUM = "123456789";

    @Mock
    private TransactionRepository dbRepo;
    @Mock
    private LedgerReaderCallback callback;

    @InjectMocks
    private LedgerReader ledgerReader;

    @BeforeEach
    void setUp() {
        initMocks(this);
        setField(ledgerReader, "pollMs", 2);
        setField(ledgerReader, "localRoutingNum", LOCAL_ROUTING_NUM);
    }

    @Test
    @DisplayName("Given a null callback, reject reader startup")
    void startWithCallbackFailsWhenCallbackIsNull() {
        // When / Then
        assertThrows(IllegalStateException.class,
            () -> ledgerReader.startWithCallback(null));
        assertTrue(ledgerReader.isAlive());
    }

    @Test
    @DisplayName("Given no startup, report the reader as alive")
    void isAliveReturnsTrueWhenReaderHasNotStarted() {
        // When
        boolean alive = ledgerReader.isAlive();

        // Then
        assertTrue(alive);
    }

    @Test
    @DisplayName("Given an unavailable database at startup, still start")
    void startWithCallbackStartsWhenInitialDatabaseIsUnavailable()
        throws Exception {
        // Given
        when(dbRepo.latestTransactionId())
            .thenThrow(new ResourceAccessException("database unavailable"))
            .thenReturn(-1L)
            .thenReturn(-2L);

        // When
        ledgerReader.startWithCallback(callback);

        // Then
        awaitNotAlive();
        verify(dbRepo, atLeastOnce()).latestTransactionId();
    }

    @Test
    @DisplayName("Given a data access failure at startup, still start")
    void startWithCallbackStartsWhenInitialDataAccessFails() throws Exception {
        // Given
        when(dbRepo.latestTransactionId())
            .thenThrow(new DataAccessResourceFailureException(
                "database unavailable"))
            .thenReturn(-1L)
            .thenReturn(-2L);

        // When
        ledgerReader.startWithCallback(callback);

        // Then
        awaitNotAlive();
    }

    @Test
    @DisplayName("Given no latest transaction, start from minus one")
    void startWithCallbackUsesMinusOneWhenLatestTransactionIsNull()
        throws Exception {
        // Given
        when(dbRepo.latestTransactionId()).thenReturn(null).thenReturn(null)
            .thenReturn(-2L);

        // When
        ledgerReader.startWithCallback(callback);

        // Then
        awaitNotAlive();
    }

    @Test
    @DisplayName("Given new transactions, forward them to the callback")
    void startWithCallbackForwardsNewTransactions() throws Exception {
        // Given
        Transaction transaction = transaction(7L);
        when(dbRepo.latestTransactionId()).thenReturn(6L).thenReturn(7L)
            .thenReturn(6L);
        when(dbRepo.findLatest(6L))
            .thenReturn(Collections.singletonList(transaction));

        // When
        ledgerReader.startWithCallback(callback);

        // Then
        awaitNotAlive();
        verify(callback).processTransaction(transaction);
        verify(dbRepo).findLatest(6L);
    }

    @Test
    @DisplayName("Given no rows for a new remote id, keep the current id")
    void startWithCallbackKeepsIdWhenPollReturnsNoTransactions()
        throws Exception {
        // Given
        when(dbRepo.latestTransactionId()).thenReturn(6L).thenReturn(7L)
            .thenReturn(5L);
        when(dbRepo.findLatest(6L)).thenReturn(Collections.emptyList());

        // When
        ledgerReader.startWithCallback(callback);

        // Then
        awaitNotAlive();
        verify(dbRepo).findLatest(6L);
    }

    @Test
    @DisplayName("Given an unavailable database while polling, continue")
    void startWithCallbackContinuesWhenPollingDatabaseIsUnavailable()
        throws Exception {
        // Given
        when(dbRepo.latestTransactionId()).thenReturn(5L)
            .thenThrow(new ResourceAccessException("database unavailable"))
            .thenReturn(4L);

        // When
        ledgerReader.startWithCallback(callback);

        // Then
        awaitNotAlive();
    }

    @Test
    @DisplayName("Given a data access failure while polling, continue")
    void startWithCallbackContinuesWhenPollingDataAccessFails()
        throws Exception {
        // Given
        when(dbRepo.latestTransactionId()).thenReturn(5L)
            .thenThrow(new DataAccessResourceFailureException(
                "database unavailable"))
            .thenReturn(4L);

        // When
        ledgerReader.startWithCallback(callback);

        // Then
        awaitNotAlive();
    }

    @Test
    @DisplayName("Given a lower remote id, stop the reader")
    void startWithCallbackStopsWhenRemoteTransactionIdIsLower()
        throws Exception {
        // Given
        when(dbRepo.latestTransactionId()).thenReturn(5L).thenReturn(4L);

        // When
        ledgerReader.startWithCallback(callback);

        // Then
        awaitNotAlive();
        assertFalse(ledgerReader.isAlive());
    }

    private Transaction transaction(long id) {
        Transaction transaction = new Transaction();
        setField(transaction, "transactionId", id);
        setField(transaction, "fromAccountNum", "from");
        setField(transaction, "fromRoutingNum",
            LOCAL_ROUTING_NUM);
        setField(transaction, "toAccountNum", "to");
        setField(transaction, "toRoutingNum", "remote");
        setField(transaction, "amount", 10);
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

    private void awaitNotAlive() throws InterruptedException {
        long deadline = System.nanoTime()
            + TimeUnit.SECONDS.toNanos(3);
        while (ledgerReader.isAlive() && System.nanoTime() < deadline) {
            Thread.sleep(5);
        }
        assertFalse(ledgerReader.isAlive());
    }
}
